import time

from database.repositories.marketing import (
    create_email_send_attempt,
    get_campaign,
    get_campaign_recipient,
    get_campaign_recipients,
    mark_email_send_attempt_accepted,
    mark_email_send_attempt_error,
    update_recipient_status,
)

from services.smtp_service import (
    build_campaign_message,
    send_campaign_email,
)


def _recipient_label(
    recipient,
) -> str:
    return (
        (
            recipient["recipient_name_snapshot"]
            or ""
        ).strip()
        or
        (
            recipient["campus_name_snapshot"]
            or ""
        ).strip()
        or
        (
            recipient["organization_name_snapshot"]
            or ""
        ).strip()
        or
        (
            recipient["email_address"]
            or ""
        ).strip()
    )


def _send_recipient(
    campaign,
    recipient,
    user_id: int,
    smtp_config: dict,
    imap_config: dict | None = None,
) -> dict:

    recipient_id = int(
        recipient["id"]
    )

    email = (
        recipient["email_address"]
        or ""
    ).strip()

    recipient_name = _recipient_label(
        recipient
    )

    organization = (
        recipient[
            "organization_name_snapshot"
        ]
        or ""
    ).strip()

    campus = (
        recipient[
            "campus_name_snapshot"
        ]
        or ""
    ).strip()

    recipient_type = (
        recipient["recipient_type"]
        or ""
    ).strip()

    try:
        message = build_campaign_message(
            recipient=email,
            subject=campaign["subject"],
            body_text=campaign["body_text"],
            sender_email=smtp_config["user"],
            attachment_paths=[],
        )

        message_id = str(
            message["Message-ID"]
        )

        attempt_id = create_email_send_attempt(
            recipient_id=recipient_id,
            message_id=message_id,
            envelope_from=smtp_config["user"],
            recipient_email=email,
            user_id=user_id,
        )

    except Exception as exc:
        error = (
            "No fue posible preparar el mensaje: "
            f"{exc}"
        )

        update_recipient_status(
            recipient_id=recipient_id,
            status="ERROR",
            user_id=user_id,
            details=error,
        )

        return {
            "success":
                False,
            "destinatario":
                recipient_name,
            "organizacion":
                organization,
            "plantel":
                campus,
            "tipo":
                recipient_type,
            "email":
                email,
            "status":
                "ERROR",
            "message":
                error,
            "message_id":
                "",
            "sent_folder_saved":
                False,
        }

    result = send_campaign_email(
        smtp_host=smtp_config["host"],
        smtp_port=smtp_config["port"],
        smtp_user=smtp_config["user"],
        smtp_password=smtp_config[
            "password"
        ],
        smtp_security=smtp_config.get(
            "security",
            "starttls",
        ),
        recipient=email,
        subject=campaign["subject"],
        body_text=campaign["body_text"],
        attachment_paths=[],
        imap_config=imap_config,
        prepared_message=message,
    )

    if result["success"]:
        mark_email_send_attempt_accepted(
            attempt_id=attempt_id,
            smtp_response=result["message"],
            sent_folder_saved=result[
                "sent_folder_saved"
            ],
            sent_folder_name=result[
                "sent_folder_name"
            ],
        )

        update_recipient_status(
            recipient_id=recipient_id,
            status="ENVIADO",
            user_id=user_id,
            details=(
                "Aceptado por SMTP. "
                f"Message-ID: {message_id}. "
                f"{result['sent_folder_message']}"
            ),
        )

        status = "ENVIADO"

    else:
        mark_email_send_attempt_error(
            attempt_id=attempt_id,
            error_message=result["message"],
        )

        update_recipient_status(
            recipient_id=recipient_id,
            status="ERROR",
            user_id=user_id,
            details=(
                f"{result['message']} "
                f"Message-ID: {message_id}"
            ),
        )

        status = "ERROR"

    return {
        "success":
            result["success"],
        "destinatario":
            recipient_name,
        "organizacion":
            organization,
        "plantel":
            campus,
        "tipo":
            recipient_type,
        "email":
            email,
        "status":
            status,
        "message":
            result["message"],
        "message_id":
            message_id,
        "sent_folder_saved":
            result[
                "sent_folder_saved"
            ],
    }


def send_single_campaign_recipient(
    campaign_id: int,
    recipient_id: int,
    user_id: int,
    smtp_config: dict,
    imap_config: dict | None = None,
) -> dict:

    campaign = get_campaign(
        campaign_id
    )

    recipient = get_campaign_recipient(
        recipient_id
    )

    if campaign is None:
        return {
            "success": False,
            "message": "La campaña no existe.",
        }

    if recipient is None:
        return {
            "success": False,
            "message": "El destinatario no existe.",
        }

    if int(
        recipient["campaign_id"]
    ) != int(
        campaign_id
    ):
        return {
            "success":
                False,
            "message":
                "El destinatario no pertenece a esta campaña.",
        }

    if recipient["status"] != "PENDIENTE":
        return {
            "success":
                False,
            "message":
                "Solo se envían registros PENDIENTES.",
        }

    return _send_recipient(
        campaign,
        recipient,
        user_id,
        smtp_config,
        imap_config,
    )


def send_next_campaign_batch(
    campaign_id: int,
    user_id: int,
    smtp_config: dict,
    batch_size: int = 5,
    interval_seconds: int = 45,
    imap_config: dict | None = None,
) -> dict:

    campaign = get_campaign(
        campaign_id
    )

    if campaign is None:
        return {
            "success":
                False,
            "message":
                "La campaña no existe.",
            "processed":
                0,
            "sent":
                0,
            "errors":
                0,
            "remaining":
                0,
            "sent_copies":
                0,
            "results":
                [],
        }

    recipients = get_campaign_recipients(
        campaign_id
    )

    selected = [
        row
        for row in recipients
        if row["status"] == "PENDIENTE"
    ][
        :batch_size
    ]

    if not selected:
        return {
            "success":
                True,
            "message":
                "No existen destinatarios pendientes.",
            "processed":
                0,
            "sent":
                0,
            "errors":
                0,
            "remaining":
                0,
            "sent_copies":
                0,
            "results":
                [],
        }

    results = []
    sent = 0
    errors = 0
    sent_copies = 0

    for index, recipient in enumerate(
        selected
    ):
        result = _send_recipient(
            campaign,
            recipient,
            user_id,
            smtp_config,
            imap_config,
        )

        sent += (
            1
            if result["success"]
            else 0
        )

        errors += (
            0
            if result["success"]
            else 1
        )

        sent_copies += (
            1
            if result.get(
                "sent_folder_saved"
            )
            else 0
        )

        results.append(
            {
                "Destinatario":
                    result.get(
                        "destinatario",
                        "",
                    ),
                "Organización":
                    result.get(
                        "organizacion",
                        "",
                    ),
                "Plantel":
                    result.get(
                        "plantel",
                        "",
                    ),
                "Tipo":
                    result.get(
                        "tipo",
                        "",
                    ),
                "Correo":
                    result.get(
                        "email",
                        "",
                    ),
                "Estado":
                    result.get(
                        "status",
                        "ERROR",
                    ),
                "Message-ID":
                    result.get(
                        "message_id",
                        "",
                    ),
                "Copia en enviados":
                    (
                        "Sí"
                        if result.get(
                            "sent_folder_saved"
                        )
                        else "No"
                    ),
                "Resultado":
                    result["message"],
            }
        )

        if index < len(
            selected
        ) - 1:
            time.sleep(
                max(
                    int(
                        interval_seconds
                    ),
                    0,
                )
            )

    remaining = sum(
        1
        for row in get_campaign_recipients(
            campaign_id
        )
        if row["status"] == "PENDIENTE"
    )

    return {
        "success":
            True,
        "message":
            "Lote procesado.",
        "processed":
            len(
                selected
            ),
        "sent":
            sent,
        "errors":
            errors,
        "remaining":
            remaining,
        "sent_copies":
            sent_copies,
        "results":
            results,
    }
