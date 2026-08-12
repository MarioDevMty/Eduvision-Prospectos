import email
import imaplib
import re
import ssl

from email.header import decode_header
from email.utils import getaddresses

from database.repositories.mail_tracking import (
    find_attempt_by_message_ids,
    find_latest_attempt_by_recipient_email,
    find_latest_campaign_recipient_by_email,
    mark_attempt_bounce,
    mark_attempt_response,
)

from database.repositories.mailbox_state import (
    acquire_mailbox_sync_lock,
    complete_mailbox_sync,
    fail_mailbox_sync,
    get_mailbox_sync_state,
    is_message_processed,
    record_processed_message,
)

from database.repositories.marketing import (
    update_recipient_status,
)


BOUNCE_SUBJECT_MARKERS = (
    "undelivered",
    "delivery status notification",
    "delivery failure",
    "mail delivery failed",
    "returned mail",
    "failure notice",
)

BOUNCE_SENDER_MARKERS = (
    "mailer-daemon",
    "postmaster",
)

EMAIL_PATTERN = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE,
)

ENHANCED_STATUS_PATTERN = re.compile(
    r"\b([245]\.\d\.\d)\b"
)

MESSAGE_ID_PATTERN = re.compile(
    r"<[^<>@\s]+@[^<>\s]+>"
)


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""

    parts = []

    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            parts.append(
                part.decode(
                    charset or "utf-8",
                    errors="replace",
                )
            )
        else:
            parts.append(part)

    return "".join(parts)


def _extract_message_text(message) -> str:
    chunks = []

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()

            if content_type not in {
                "text/plain",
                "message/delivery-status",
                "message/rfc822",
            }:
                continue

            try:
                payload = part.get_payload(decode=True)

                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(
                        payload.decode(
                            charset,
                            errors="replace",
                        )
                    )
                    continue

                raw_payload = part.get_payload()

                if isinstance(raw_payload, str):
                    chunks.append(raw_payload)
                elif isinstance(raw_payload, list):
                    for item in raw_payload:
                        try:
                            chunks.append(item.as_string())
                        except Exception:
                            pass

            except Exception:
                pass

    else:
        try:
            payload = message.get_payload(decode=True)

            if payload:
                charset = message.get_content_charset() or "utf-8"
                chunks.append(
                    payload.decode(
                        charset,
                        errors="replace",
                    )
                )
            else:
                raw_payload = message.get_payload()

                if isinstance(raw_payload, str):
                    chunks.append(raw_payload)

        except Exception:
            pass

    return "\n".join(chunks)


def _is_bounce(
    from_header: str,
    subject: str,
    text: str,
) -> bool:
    from_lower = from_header.lower()
    subject_lower = subject.lower()
    text_lower = text.lower()

    if any(marker in from_lower for marker in BOUNCE_SENDER_MARKERS):
        return True

    if any(marker in subject_lower for marker in BOUNCE_SUBJECT_MARKERS):
        return True

    if "final-recipient:" in text_lower and "status:" in text_lower:
        return True

    return False


def _extract_bounce_recipient(
    text: str,
    own_email: str,
) -> str:
    patterns = [
        r"Final-Recipient:\s*[^;]+;\s*([^\s<>]+@[^\s<>]+)",
        r"Original-Recipient:\s*[^;]+;\s*([^\s<>]+@[^\s<>]+)",
        r"<([^<>@\s]+@[^<>\s]+)>",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            candidate = (
                match.group(1)
                .strip(" <>.,;:")
                .lower()
            )

            if candidate != own_email.lower():
                return candidate

    for candidate in EMAIL_PATTERN.findall(text):
        normalized = (
            candidate
            .strip(" <>.,;:")
            .lower()
        )

        if normalized != own_email.lower():
            return normalized

    return ""


def _extract_bounce_code(text: str) -> str:
    match = ENHANCED_STATUS_PATTERN.search(text)
    return match.group(1) if match else ""


def _extract_bounce_reason(
    text: str,
    code: str,
) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    markers = (
        "diagnostic-code:",
        "said:",
        "recipient address rejected",
        "no such person",
        "user unknown",
        "mailbox unavailable",
        "access denied",
    )

    for line in lines:
        line_lower = line.lower()

        if any(marker in line_lower for marker in markers):
            return line[:500]

    if code:
        for line in lines:
            if code in line:
                return line[:500]

    return "Aviso de no entrega detectado."


def _extract_reply_message_ids(message) -> list[str]:
    values = []

    for header_name in (
        "In-Reply-To",
        "References",
    ):
        raw_value = message.get(header_name, "")
        values.extend(
            MESSAGE_ID_PATTERN.findall(raw_value)
        )

    seen = set()
    result = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)

    return result


def scan_mailbox(
    host: str,
    port: int,
    user: str,
    password: str,
    user_id: int,
    limit: int = 500,
    apply_changes: bool = True,
    mailbox: str = "INBOX",
    incremental: bool = True,
    source: str = "MANUAL",
) -> dict:
    """
    Sincroniza el buzón y procesa únicamente UID nuevos.

    Cuando incremental=True, usa mailbox_sync_state y evita
    analizar dos veces el mismo mensaje.
    """

    lock = acquire_mailbox_sync_lock(
        mailbox=mailbox,
        source=source,
    )

    if not lock["acquired"]:
        return {
            "success": False,
            "locked": True,
            "message": lock["message"],
            "scanned": 0,
            "applied_bounces": 0,
            "applied_replies": 0,
            "bounces": [],
            "replies": [],
            "unmatched": [],
            "errors": [],
        }

    run_id = lock["run_id"]
    context = ssl.create_default_context()
    connection = None

    results = {
        "success": True,
        "locked": False,
        "message": "Sincronización completada.",
        "scanned": 0,
        "applied_bounces": 0,
        "applied_replies": 0,
        "bounces": [],
        "replies": [],
        "unmatched": [],
        "errors": [],
    }

    try:
        state = get_mailbox_sync_state(mailbox)
        last_uid = int(state["last_uid_processed"] or 0)

        connection = imaplib.IMAP4_SSL(
            host=host,
            port=int(port),
            ssl_context=context,
            timeout=30,
        )

        connection.login(user, password)

        status, _ = connection.select(
            mailbox,
            readonly=True,
        )

        if status != "OK":
            raise RuntimeError(
                f"No fue posible abrir {mailbox}."
            )

        if incremental:
            start_uid = last_uid + 1
            status, data = connection.uid(
                "search",
                None,
                f"UID {start_uid}:*",
            )
        else:
            status, data = connection.uid(
                "search",
                None,
                "ALL",
            )

        if status != "OK":
            raise RuntimeError(
                "No fue posible consultar el buzón."
            )

        uids = (
            data[0].split()
            if data and data[0]
            else []
        )

        uid_values = sorted(
            {
                int(raw_uid)
                for raw_uid in uids
                if raw_uid
            }
        )

        if incremental:
            uid_values = [
                uid
                for uid in uid_values
                if uid > last_uid
            ]

        if limit > 0:
            uid_values = uid_values[:int(limit)]

        for uid_value in uid_values:
            uid = str(uid_value)

            if is_message_processed(mailbox, uid):
                record_processed_message(
                    mailbox=mailbox,
                    message_uid=uid,
                    message_id="",
                    message_type="ALREADY_PROCESSED",
                    matched_recipient_id=None,
                    processing_result="UID ya registrado.",
                    subject="",
                    sender_email="",
                )
                continue

            status, message_data = connection.uid(
                "fetch",
                uid.encode("ascii"),
                "(RFC822)",
            )

            if status != "OK":
                results["errors"].append(
                    {
                        "uid": uid,
                        "error": "No fue posible leer el mensaje.",
                    }
                )
                break

            raw_message = None

            for item in message_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw_message = item[1]
                    break

            if not raw_message:
                results["errors"].append(
                    {
                        "uid": uid,
                        "error": "El mensaje no contiene datos legibles.",
                    }
                )
                break

            message = email.message_from_bytes(raw_message)
            results["scanned"] += 1

            subject = _decode_header_value(
                message.get("Subject")
            )

            from_header = _decode_header_value(
                message.get("From")
            )

            from_addresses = [
                address.lower()
                for _, address in getaddresses([from_header])
                if address
            ]

            sender_email = (
                from_addresses[0]
                if from_addresses
                else ""
            )

            message_id = message.get("Message-ID", "")
            text = _extract_message_text(message)

            message_type = "OTHER"
            matched_recipient_id = None
            processing_result = "Mensaje sin relación comprobable."

            if _is_bounce(from_header, subject, text):
                message_type = "BOUNCE"

                bounce_email = _extract_bounce_recipient(
                    text=text,
                    own_email=user,
                )

                bounce_code = _extract_bounce_code(text)
                bounce_reason = _extract_bounce_reason(
                    text,
                    bounce_code,
                )

                attempt = (
                    find_latest_attempt_by_recipient_email(
                        bounce_email
                    )
                    if bounce_email
                    else None
                )

                recipient_id = None
                campus = ""
                current_status = ""
                attempt_id = None

                if attempt:
                    attempt_id = int(attempt["id"])
                    recipient_id = int(
                        attempt["campaign_recipient_id"]
                    )
                    campus = attempt["campus_name_snapshot"] or ""
                    current_status = attempt["recipient_status"] or ""

                elif bounce_email:
                    recipient = (
                        find_latest_campaign_recipient_by_email(
                            bounce_email
                        )
                    )

                    if recipient:
                        recipient_id = int(recipient["id"])
                        campus = recipient["campus_name_snapshot"] or ""
                        current_status = recipient["status"] or ""

                matched = recipient_id is not None
                matched_recipient_id = recipient_id
                applied = False

                if (
                    apply_changes
                    and matched
                    and current_status != "REBOTE"
                ):
                    update_recipient_status(
                        recipient_id=recipient_id,
                        status="REBOTE",
                        user_id=user_id,
                        details=(
                            "Rebote detectado automáticamente por IMAP. "
                            f"UID: {uid}. "
                            f"Código: {bounce_code or 'N/D'}. "
                            f"Motivo: {bounce_reason}"
                        ),
                    )

                    if attempt_id is not None:
                        mark_attempt_bounce(
                            attempt_id=attempt_id,
                            bounce_code=bounce_code,
                            bounce_reason=bounce_reason,
                            message_uid=uid,
                        )

                    applied = True
                    results["applied_bounces"] += 1

                processing_result = (
                    f"Rebote {'aplicado' if applied else 'detectado'}. "
                    f"Correo: {bounce_email or 'N/D'}. "
                    f"Código: {bounce_code or 'N/D'}."
                )

                results["bounces"].append(
                    {
                        "uid": uid,
                        "subject": subject,
                        "rejected_email": bounce_email,
                        "code": bounce_code,
                        "reason": bounce_reason,
                        "matched": matched,
                        "recipient_id": recipient_id,
                        "attempt_id": attempt_id,
                        "campus": campus,
                        "current_status": current_status,
                        "applied": applied,
                    }
                )

                if not matched:
                    results["unmatched"].append(
                        {
                            "uid": uid,
                            "type": "BOUNCE",
                            "subject": subject,
                            "from": sender_email,
                            "reason": (
                                "Rebote sin destinatario de campaña coincidente."
                            ),
                        }
                    )

            else:
                reply_ids = _extract_reply_message_ids(message)

                if reply_ids:
                    attempt = find_attempt_by_message_ids(reply_ids)

                    if attempt:
                        message_type = "REPLY"
                        recipient_id = int(
                            attempt["campaign_recipient_id"]
                        )
                        matched_recipient_id = recipient_id
                        current_status = attempt["recipient_status"] or ""
                        applied = False

                        if (
                            apply_changes
                            and current_status not in {
                                "RESPONDIO",
                                "CONTACTO_REFERIDO",
                                "NO_INTERESADO",
                                "REBOTE",
                            }
                        ):
                            update_recipient_status(
                                recipient_id=recipient_id,
                                status="RESPONDIO",
                                user_id=user_id,
                                details=(
                                    "Respuesta detectada automáticamente por IMAP. "
                                    f"UID: {uid}. "
                                    f"De: {sender_email}. "
                                    f"Asunto: {subject}"
                                ),
                            )

                            mark_attempt_response(
                                attempt_id=int(attempt["id"]),
                                message_uid=uid,
                            )

                            applied = True
                            results["applied_replies"] += 1

                        processing_result = (
                            "Respuesta vinculada "
                            f"{'y aplicada' if applied else 'sin cambio de estado'}."
                        )

                        results["replies"].append(
                            {
                                "uid": uid,
                                "subject": subject,
                                "from": sender_email,
                                "matched": True,
                                "recipient_id": recipient_id,
                                "attempt_id": int(attempt["id"]),
                                "campus": attempt["campus_name_snapshot"] or "",
                                "current_status": current_status,
                                "applied": applied,
                            }
                        )

                    else:
                        message_type = "UNMATCHED_REPLY"
                        processing_result = (
                            "Tiene In-Reply-To o References, pero no coincide "
                            "con un Message-ID registrado."
                        )

                        results["unmatched"].append(
                            {
                                "uid": uid,
                                "type": "REPLY",
                                "subject": subject,
                                "from": sender_email,
                                "reason": processing_result,
                            }
                        )

            record_processed_message(
                mailbox=mailbox,
                message_uid=uid,
                message_id=message_id,
                message_type=message_type,
                matched_recipient_id=matched_recipient_id,
                processing_result=processing_result,
                subject=subject,
                sender_email=sender_email,
            )

        complete_mailbox_sync(
            mailbox=mailbox,
            run_id=run_id,
            results=results,
        )

        return results

    except Exception as exc:
        results["success"] = False
        results["message"] = str(exc)

        try:
            fail_mailbox_sync(
                mailbox=mailbox,
                run_id=run_id,
                error_message=str(exc),
            )
        except Exception:
            pass

        return results

    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass
