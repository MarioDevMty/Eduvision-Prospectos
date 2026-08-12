from database.connection import get_connection


def find_attempt_by_message_ids(message_ids: list[str]):
    cleaned = [value.strip() for value in message_ids if value and value.strip()]
    if not cleaned:
        return None

    placeholders = ",".join("?" for _ in cleaned)

    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT
                esa.*,
                cr.campaign_id,
                cr.campus_name_snapshot,
                cr.email_address,
                cr.status AS recipient_status
            FROM email_send_attempts esa
            JOIN campaign_recipients cr
              ON cr.id = esa.campaign_recipient_id
            WHERE esa.message_id IN ({placeholders})
            ORDER BY esa.id DESC
            LIMIT 1
            """,
            cleaned,
        ).fetchone()


def find_latest_attempt_by_recipient_email(email_address: str):
    email_address = (email_address or "").strip().lower()
    if not email_address:
        return None

    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                esa.*,
                cr.campaign_id,
                cr.campus_name_snapshot,
                cr.email_address,
                cr.status AS recipient_status
            FROM email_send_attempts esa
            JOIN campaign_recipients cr
              ON cr.id = esa.campaign_recipient_id
            WHERE LOWER(esa.recipient_email) = LOWER(?)
            ORDER BY
                COALESCE(cr.is_active, 1) DESC,
                esa.id DESC
            LIMIT 1
            """,
            (email_address,),
        ).fetchone()


def find_latest_campaign_recipient_by_email(email_address: str):
    email_address = (email_address or "").strip().lower()
    if not email_address:
        return None

    with get_connection() as connection:
        return connection.execute(
            """
            SELECT cr.*
            FROM campaign_recipients cr
            WHERE LOWER(cr.email_address) = LOWER(?)
            ORDER BY
                COALESCE(cr.is_active, 1) DESC,
                COALESCE(cr.sent_at, cr.created_at) DESC,
                cr.id DESC
            LIMIT 1
            """,
            (email_address,),
        ).fetchone()


def mark_attempt_bounce(
    attempt_id: int,
    bounce_code: str,
    bounce_reason: str,
    message_uid: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE email_send_attempts
            SET
                bounce_detected = 1,
                bounce_code = ?,
                bounce_reason = ?,
                bounce_message_uid = ?,
                bounced_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                bounce_code or None,
                bounce_reason or None,
                message_uid or None,
                attempt_id,
            ),
        )
        connection.commit()


def mark_attempt_response(
    attempt_id: int,
    message_uid: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE email_send_attempts
            SET
                response_detected = 1,
                response_message_uid = ?,
                responded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                message_uid or None,
                attempt_id,
            ),
        )
        connection.commit()
