from database.connection import get_connection


STALE_LOCK_MINUTES = 10


def get_mailbox_sync_state(
    mailbox: str = "INBOX",
):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM mailbox_sync_state
            WHERE mailbox = ?
            """,
            (mailbox,),
        ).fetchone()


def get_recent_mailbox_sync_runs(
    limit: int = 10,
) -> list:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM mailbox_sync_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(int(limit), 1),),
        ).fetchall()


def acquire_mailbox_sync_lock(
    mailbox: str,
    source: str,
) -> dict:
    """
    Adquiere un bloqueo persistente para impedir dos
    sincronizaciones simultáneas.
    """

    with get_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")

            connection.execute(
                """
                INSERT OR IGNORE INTO mailbox_sync_state (
                    mailbox,
                    last_uid_processed,
                    is_running
                )
                VALUES (?, 0, 0)
                """,
                (mailbox,),
            )

            state = connection.execute(
                """
                SELECT *
                FROM mailbox_sync_state
                WHERE mailbox = ?
                """,
                (mailbox,),
            ).fetchone()

            locked = bool(state["is_running"])

            if locked:
                stale = connection.execute(
                    """
                    SELECT CASE
                        WHEN lock_started_at IS NULL THEN 1
                        WHEN datetime(lock_started_at) <=
                             datetime('now', ?)
                        THEN 1 ELSE 0
                    END AS is_stale
                    """,
                    (f"-{STALE_LOCK_MINUTES} minutes",),
                ).fetchone()["is_stale"]

                if not stale:
                    connection.rollback()
                    return {
                        "acquired": False,
                        "run_id": None,
                        "message": (
                            "Ya existe una sincronización del buzón "
                            "en ejecución."
                        ),
                    }

            connection.execute(
                """
                UPDATE mailbox_sync_state
                SET
                    is_running = 1,
                    lock_started_at = CURRENT_TIMESTAMP,
                    last_error = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mailbox = ?
                """,
                (mailbox,),
            )

            cursor = connection.execute(
                """
                INSERT INTO mailbox_sync_runs (
                    mailbox,
                    source,
                    status,
                    started_at
                )
                VALUES (?, ?, 'RUNNING', CURRENT_TIMESTAMP)
                """,
                (mailbox, source),
            )

            run_id = int(cursor.lastrowid)
            connection.commit()

            return {
                "acquired": True,
                "run_id": run_id,
                "message": "Bloqueo adquirido.",
            }

        except Exception:
            connection.rollback()
            raise


def is_message_processed(
    mailbox: str,
    message_uid: str,
) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM mailbox_processed_messages
            WHERE mailbox = ?
              AND message_uid = ?
            LIMIT 1
            """,
            (mailbox, str(message_uid)),
        ).fetchone()

    return row is not None


def record_processed_message(
    mailbox: str,
    message_uid: str,
    message_id: str,
    message_type: str,
    matched_recipient_id,
    processing_result: str,
    subject: str,
    sender_email: str,
) -> None:
    """
    Registra el mensaje y avanza el último UID en una sola
    transacción. Un UID ya registrado no se duplica.
    """

    uid_int = int(message_uid)

    with get_connection() as connection:
        try:
            connection.execute("BEGIN")

            connection.execute(
                """
                INSERT OR IGNORE INTO mailbox_processed_messages (
                    mailbox,
                    message_uid,
                    message_id,
                    message_type,
                    matched_recipient_id,
                    processing_result,
                    subject,
                    sender_email
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mailbox,
                    str(message_uid),
                    message_id or None,
                    message_type,
                    matched_recipient_id,
                    processing_result,
                    subject or None,
                    sender_email or None,
                ),
            )

            connection.execute(
                """
                UPDATE mailbox_sync_state
                SET
                    last_uid_processed = CASE
                        WHEN last_uid_processed < ? THEN ?
                        ELSE last_uid_processed
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mailbox = ?
                """,
                (uid_int, uid_int, mailbox),
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise


def complete_mailbox_sync(
    mailbox: str,
    run_id: int,
    results: dict,
) -> None:
    with get_connection() as connection:
        try:
            connection.execute("BEGIN")

            connection.execute(
                """
                UPDATE mailbox_sync_state
                SET
                    is_running = 0,
                    lock_started_at = NULL,
                    last_sync_at = CURRENT_TIMESTAMP,
                    last_success_at = CURRENT_TIMESTAMP,
                    last_error = NULL,
                    last_scanned = ?,
                    last_bounces = ?,
                    last_replies = ?,
                    last_unmatched = ?,
                    last_errors = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mailbox = ?
                """,
                (
                    int(results.get("scanned", 0)),
                    int(results.get("applied_bounces", 0)),
                    int(results.get("applied_replies", 0)),
                    len(results.get("unmatched", [])),
                    len(results.get("errors", [])),
                    mailbox,
                ),
            )

            connection.execute(
                """
                UPDATE mailbox_sync_runs
                SET
                    status = 'SUCCESS',
                    finished_at = CURRENT_TIMESTAMP,
                    scanned = ?,
                    bounces = ?,
                    replies = ?,
                    unmatched = ?,
                    errors = ?
                WHERE id = ?
                """,
                (
                    int(results.get("scanned", 0)),
                    int(results.get("applied_bounces", 0)),
                    int(results.get("applied_replies", 0)),
                    len(results.get("unmatched", [])),
                    len(results.get("errors", [])),
                    run_id,
                ),
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise


def fail_mailbox_sync(
    mailbox: str,
    run_id: int | None,
    error_message: str,
) -> None:
    with get_connection() as connection:
        try:
            connection.execute("BEGIN")

            connection.execute(
                """
                UPDATE mailbox_sync_state
                SET
                    is_running = 0,
                    lock_started_at = NULL,
                    last_sync_at = CURRENT_TIMESTAMP,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE mailbox = ?
                """,
                (error_message[:1000], mailbox),
            )

            if run_id is not None:
                connection.execute(
                    """
                    UPDATE mailbox_sync_runs
                    SET
                        status = 'ERROR',
                        finished_at = CURRENT_TIMESTAMP,
                        error_message = ?
                    WHERE id = ?
                    """,
                    (error_message[:1000], run_id),
                )

            connection.commit()

        except Exception:
            connection.rollback()
            raise
