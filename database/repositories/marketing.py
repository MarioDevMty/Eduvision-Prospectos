from database.connection import get_connection

from services.data_validation import (
    validate_email_address,
)

from services.normalization import (
    normalize_email,
)


# =========================================================
# CAMPAÑAS
# =========================================================

def create_campaign(
    name: str,
    campaign_type: str,
    objective: str,
    subject: str,
    body_text: str,
    user_id: int,
) -> int:

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO campaigns (
                name,
                campaign_type,
                objective,
                subject,
                body_text,
                status,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, 'BORRADOR', ?)
            """,
            (
                name,
                campaign_type,
                objective,
                subject,
                body_text,
                user_id,
            ),
        )

        connection.commit()

        return cursor.lastrowid


def get_campaigns() -> list:

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT
                id,
                name,
                campaign_type,
                objective,
                subject,
                status,
                created_at
            FROM campaigns
            ORDER BY id DESC
            """
        ).fetchall()


def get_campaign(
    campaign_id: int,
):

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT *
            FROM campaigns
            WHERE id = ?
            """,
            (
                campaign_id,
            ),
        ).fetchone()


def update_campaign_status(
    campaign_id: int,
    status: str,
) -> None:

    valid_statuses = {
        "BORRADOR",
        "ACTIVA",
        "FINALIZADA",
        "CANCELADA",
    }

    if status not in valid_statuses:
        raise ValueError(
            f"Estado de campaña no válido: {status}"
        )

    with get_connection() as connection:

        connection.execute(
            """
            UPDATE campaigns
            SET
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                campaign_id,
            ),
        )

        connection.commit()


# =========================================================
# PLANTELES ELEGIBLES
# =========================================================

def get_eligible_campuses() -> list:
    """
    Devuelve planteles que tienen al menos
    un correo institucional activo.

    No requiere que exista un contacto personal.
    """

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                c.id AS campus_id,
                c.campus_name,
                c.campus_type,
                c.municipality,
                c.state,
                c.status AS campus_status,

                o.id AS organization_id,
                o.official_name,
                o.subsystem,
                o.sector,

                e.id AS email_id,
                e.email,
                e.email_type,
                e.is_primary

            FROM campuses c

            JOIN organizations o
                ON o.id = c.organization_id

            JOIN emails e
                ON e.entity_type = 'CAMPUS'
               AND e.entity_id = c.id
               AND e.status = 'ACTIVO'

            WHERE c.status <> 'BAJA'

            ORDER BY
                o.official_name,
                c.campus_name,
                e.is_primary DESC,
                e.id
            """
        ).fetchall()

    return rows


def get_eligible_campuses_count() -> int:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM campuses c

            JOIN emails e
                ON e.entity_type = 'CAMPUS'
               AND e.entity_id = c.id
               AND e.status = 'ACTIVO'

            WHERE c.status <> 'BAJA'
            """
        ).fetchone()

    return row[0] if row else 0


def get_eligible_email_count() -> int:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM emails e

            JOIN campuses c
                ON c.id = e.entity_id
               AND e.entity_type = 'CAMPUS'

            WHERE e.status = 'ACTIVO'
              AND c.status <> 'BAJA'
            """
        ).fetchone()

    return row[0] if row else 0


# =========================================================
# DESTINATARIOS
# =========================================================

def recipient_exists(
    campaign_id: int,
    email_address: str,
) -> bool:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT id
            FROM campaign_recipients
            WHERE campaign_id = ?
              AND LOWER(email_address) = LOWER(?)
            LIMIT 1
            """,
            (
                campaign_id,
                email_address,
            ),
        ).fetchone()

    return row is not None


def add_campaign_recipient(
    campaign_id: int,
    campus_id: int,
    campus_name: str,
    email_address: str,
    user_id: int,
    contact_id=None,
    email_type: str = "INSTITUCIONAL",
) -> int:

    email_address = (
        email_address or ""
    ).strip().lower()

    if not email_address:
        return 0

    if recipient_exists(
        campaign_id,
        email_address,
    ):
        return 0

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO campaign_recipients (
                campaign_id,
                campus_id,
                contact_id,
                campus_name_snapshot,
                email_address,
                email_type,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE')
            """,
            (
                campaign_id,
                campus_id,
                contact_id,
                campus_name,
                email_address,
                email_type,
            ),
        )

        recipient_id = cursor.lastrowid

        connection.execute(
            """
            INSERT INTO email_activity (
                campaign_recipient_id,
                event_type,
                details,
                created_by
            )
            VALUES (
                ?,
                'AGREGADO',
                ?,
                ?
            )
            """,
            (
                recipient_id,
                "Destinatario agregado a la campaña",
                user_id,
            ),
        )

        connection.commit()

    return recipient_id


def add_multiple_campaign_recipients(
    campaign_id: int,
    recipients: list[dict],
    user_id: int,
) -> dict:

    added = 0
    skipped = 0

    for recipient in recipients:

        recipient_id = add_campaign_recipient(
            campaign_id=campaign_id,
            campus_id=recipient["campus_id"],
            campus_name=recipient["campus_name"],
            email_address=recipient["email"],
            user_id=user_id,
            contact_id=recipient.get(
                "contact_id"
            ),
            email_type=recipient.get(
                "email_type",
                "INSTITUCIONAL",
            ),
        )

        if recipient_id:
            added += 1
        else:
            skipped += 1

    return {
        "added": added,
        "skipped": skipped,
    }


def get_campaign_recipients(
    campaign_id: int,
) -> list:

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT
                cr.id,
                cr.campaign_id,
                cr.campus_id,
                cr.contact_id,
                cr.campus_name_snapshot,
                cr.email_address,
                cr.email_type,
                cr.status,
                cr.sent_at,
                cr.responded_at,
                cr.referred_name,
                cr.referred_position,
                cr.referred_email,
                cr.referred_phone,
                cr.notes,
                cr.created_at
            FROM campaign_recipients cr
            WHERE cr.campaign_id = ?
              AND COALESCE(cr.is_active, 1) = 1
            ORDER BY
                cr.campus_name_snapshot,
                cr.email_address
            """,
            (
                campaign_id,
            ),
        ).fetchall()


# =========================================================
# ESTADOS Y ACTIVIDAD
# =========================================================

def update_recipient_status(
    recipient_id: int,
    status: str,
    user_id: int,
    details: str = "",
) -> None:

    valid_statuses = {
        "PENDIENTE",
        "ENVIADO",
        "RESPONDIO",
        "CONTACTO_REFERIDO",
        "SIN_RESPUESTA",
        "REBOTE",
        "NO_INTERESADO",
        "ERROR",
    }

    if status not in valid_statuses:
        raise ValueError(
            f"Estado no válido: {status}"
        )

    with get_connection() as connection:

        if status == "ENVIADO":

            connection.execute(
                """
                UPDATE campaign_recipients
                SET
                    status = ?,
                    sent_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    recipient_id,
                ),
            )

        elif status in {
            "RESPONDIO",
            "CONTACTO_REFERIDO",
        }:

            connection.execute(
                """
                UPDATE campaign_recipients
                SET
                    status = ?,
                    responded_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    recipient_id,
                ),
            )

        else:

            connection.execute(
                """
                UPDATE campaign_recipients
                SET
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    recipient_id,
                ),
            )

        connection.execute(
            """
            INSERT INTO email_activity (
                campaign_recipient_id,
                event_type,
                details,
                created_by
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                recipient_id,
                status,
                details or status,
                user_id,
            ),
        )

        connection.commit()


def register_referred_contact(
    recipient_id: int,
    name: str,
    position: str,
    email: str,
    phone: str,
    notes: str,
    user_id: int,
) -> None:

    with get_connection() as connection:

        connection.execute(
            """
            UPDATE campaign_recipients
            SET
                status = 'CONTACTO_REFERIDO',
                responded_at = CURRENT_TIMESTAMP,
                referred_name = ?,
                referred_position = ?,
                referred_email = ?,
                referred_phone = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name,
                position,
                email,
                phone,
                notes,
                recipient_id,
            ),
        )

        connection.execute(
            """
            INSERT INTO email_activity (
                campaign_recipient_id,
                event_type,
                details,
                created_by
            )
            VALUES (
                ?,
                'CONTACTO_REFERIDO',
                ?,
                ?
            )
            """,
            (
                recipient_id,
                f"Contacto referido: {name}",
                user_id,
            ),
        )

        connection.commit()


def get_recipient_activity(
    recipient_id: int,
) -> list:

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT
                id,
                event_type,
                details,
                event_at,
                created_by
            FROM email_activity
            WHERE campaign_recipient_id = ?
            ORDER BY event_at DESC, id DESC
            """,
            (
                recipient_id,
            ),
        ).fetchall()


# =========================================================
# MÉTRICAS
# =========================================================

def get_campaign_metrics(
    campaign_id: int,
):

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,

                SUM(
                    CASE
                        WHEN status = 'PENDIENTE'
                        THEN 1 ELSE 0
                    END
                ) AS pendientes,

                SUM(
                    CASE
                        WHEN status = 'ENVIADO'
                        THEN 1 ELSE 0
                    END
                ) AS enviados,

                SUM(
                    CASE
                        WHEN status IN (
                            'RESPONDIO',
                            'CONTACTO_REFERIDO',
                            'NO_INTERESADO'
                        )
                        THEN 1 ELSE 0
                    END
                ) AS respuestas,

                SUM(
                    CASE
                        WHEN status = 'CONTACTO_REFERIDO'
                        THEN 1 ELSE 0
                    END
                ) AS contactos_referidos,

                SUM(
                    CASE
                        WHEN status = 'SIN_RESPUESTA'
                        THEN 1 ELSE 0
                    END
                ) AS sin_respuesta,

                SUM(
                    CASE
                        WHEN status = 'REBOTE'
                        THEN 1 ELSE 0
                    END
                ) AS rebotes,

                SUM(
                    CASE
                        WHEN status = 'ERROR'
                        THEN 1 ELSE 0
                    END
                ) AS errores

            FROM campaign_recipients
            WHERE campaign_id = ?
            """,
            (
                campaign_id,
            ),
        ).fetchone()

    return row

# =========================================================
# INTENTOS DE ENVÍO Y RASTREO
# =========================================================

def get_campaign_recipient(recipient_id: int):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM campaign_recipients
            WHERE id = ?
              AND COALESCE(is_active, 1) = 1
            """,
            (recipient_id,),
        ).fetchone()


def create_email_send_attempt(
    recipient_id: int,
    message_id: str,
    envelope_from: str,
    recipient_email: str,
    user_id: int,
) -> int:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(attempt_number), 0) + 1
            FROM email_send_attempts
            WHERE campaign_recipient_id = ?
            """,
            (recipient_id,),
        ).fetchone()
        attempt_number = int(row[0]) if row else 1
        cursor = connection.execute(
            """
            INSERT INTO email_send_attempts (
                campaign_recipient_id,
                attempt_number,
                message_id,
                envelope_from,
                recipient_email,
                smtp_status,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, 'PREPARADO', ?)
            """,
            (
                recipient_id,
                attempt_number,
                message_id,
                envelope_from,
                recipient_email,
                user_id,
            ),
        )
        connection.commit()
        return cursor.lastrowid


def mark_email_send_attempt_accepted(
    attempt_id: int,
    smtp_response: str,
    sent_folder_saved: bool,
    sent_folder_name: str = "",
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE email_send_attempts
            SET smtp_status = 'ACEPTADO',
                smtp_response = ?,
                sent_folder_saved = ?,
                sent_folder_name = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                smtp_response,
                1 if sent_folder_saved else 0,
                sent_folder_name or None,
                attempt_id,
            ),
        )
        connection.commit()


def mark_email_send_attempt_error(
    attempt_id: int,
    error_message: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE email_send_attempts
            SET smtp_status = 'ERROR',
                smtp_response = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error_message, attempt_id),
        )
        connection.commit()


# =========================================================
# ARCHIVO Y CORRECCIÓN DE DESTINATARIOS
# =========================================================

def get_archived_campaign_recipients(
    campaign_id: int,
) -> list:
    """
    Devuelve destinatarios archivados para consulta histórica.
    """

    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                id,
                campaign_id,
                campus_id,
                campus_name_snapshot,
                email_address,
                status,
                sent_at,
                created_at
            FROM campaign_recipients
            WHERE campaign_id = ?
              AND COALESCE(is_active, 1) = 0
            ORDER BY campus_name_snapshot, email_address
            """,
            (campaign_id,),
        ).fetchall()


def get_active_delivery_incidents(
    campaign_id: int,
) -> list:
    """
    Devuelve errores y rebotes activos con el diagnóstico
    técnico más reciente disponible.
    """

    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                cr.id,
                cr.campaign_id,
                cr.campus_id,
                cr.campus_name_snapshot,
                cr.email_address,
                cr.status,

                COUNT(DISTINCT esa.id) AS attempt_count,

                (
                    SELECT esa2.smtp_status
                    FROM email_send_attempts esa2
                    WHERE esa2.campaign_recipient_id = cr.id
                    ORDER BY esa2.id DESC
                    LIMIT 1
                ) AS smtp_status,

                (
                    SELECT esa2.smtp_response
                    FROM email_send_attempts esa2
                    WHERE esa2.campaign_recipient_id = cr.id
                    ORDER BY esa2.id DESC
                    LIMIT 1
                ) AS smtp_response,

                (
                    SELECT esa2.bounce_code
                    FROM email_send_attempts esa2
                    WHERE esa2.campaign_recipient_id = cr.id
                      AND esa2.bounce_detected = 1
                    ORDER BY esa2.id DESC
                    LIMIT 1
                ) AS bounce_code,

                (
                    SELECT esa2.bounce_reason
                    FROM email_send_attempts esa2
                    WHERE esa2.campaign_recipient_id = cr.id
                      AND esa2.bounce_detected = 1
                    ORDER BY esa2.id DESC
                    LIMIT 1
                ) AS bounce_reason,

                (
                    SELECT ea.details
                    FROM email_activity ea
                    WHERE ea.campaign_recipient_id = cr.id
                      AND ea.event_type IN ('ERROR', 'REBOTE')
                    ORDER BY ea.id DESC
                    LIMIT 1
                ) AS activity_details

            FROM campaign_recipients cr

            LEFT JOIN email_send_attempts esa
              ON esa.campaign_recipient_id = cr.id

            WHERE cr.campaign_id = ?
              AND COALESCE(cr.is_active, 1) = 1
              AND cr.status IN ('ERROR', 'REBOTE')

            GROUP BY
                cr.id,
                cr.campaign_id,
                cr.campus_id,
                cr.campus_name_snapshot,
                cr.email_address,
                cr.status

            ORDER BY
                CASE
                    WHEN cr.status = 'ERROR' THEN 0
                    ELSE 1
                END,
                cr.campus_name_snapshot
            """,
            (campaign_id,),
        ).fetchall()


def archive_invalid_error_recipients(
    campaign_id: int,
    user_id: int,
    reason: str,
) -> dict:
    """
    Archiva errores cuyo valor no tiene formato de correo.

    Conserva intentos y actividad. Solo deja de mostrarlos
    en la operación activa de la campaña.
    """

    reason = (reason or "").strip()

    if not reason:
        raise ValueError(
            "El motivo es obligatorio."
        )

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                email_address,
                campus_name_snapshot
            FROM campaign_recipients
            WHERE campaign_id = ?
              AND COALESCE(is_active, 1) = 1
              AND status = 'ERROR'
            """,
            (campaign_id,),
        ).fetchall()

        invalid_rows = []

        for row in rows:
            is_valid, _ = validate_email_address(
                row["email_address"]
            )

            if not is_valid:
                invalid_rows.append(row)

        if not invalid_rows:
            return {
                "archived": 0,
            }

        try:
            connection.execute("BEGIN")

            for row in invalid_rows:
                connection.execute(
                    """
                    UPDATE campaign_recipients
                    SET
                        is_active = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                )

                connection.execute(
                    """
                    INSERT INTO audit_log (
                        user_id,
                        entity_type,
                        entity_id,
                        action,
                        field_name,
                        old_value,
                        new_value
                    )
                    VALUES (
                        ?,
                        'CAMPAIGN_RECIPIENT',
                        ?,
                        'ARCHIVE_INVALID_EMAIL',
                        'is_active',
                        '1',
                        ?
                    )
                    """,
                    (
                        user_id,
                        int(row["id"]),
                        (
                            "0 | Motivo: "
                            f"{reason}"
                        ),
                    ),
                )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    return {
        "archived":
            len(invalid_rows),
    }


def correct_campaign_recipient_email(
    recipient_id: int,
    new_email: str,
    user_id: int,
    reason: str,
    update_master: bool = True,
) -> dict:
    """
    Conserva el destinatario anterior como historial,
    corrige el correo maestro del plantel y crea un nuevo
    destinatario PENDIENTE para reenvío individual.
    """

    reason = (reason or "").strip()

    if not reason:
        raise ValueError(
            "El motivo de la corrección es obligatorio."
        )

    is_valid, validation_reason = (
        validate_email_address(
            new_email
        )
    )

    if not is_valid:
        raise ValueError(
            validation_reason
        )

    new_email = new_email.strip().lower()
    normalized = normalize_email(new_email)

    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM campaign_recipients
            WHERE id = ?
              AND COALESCE(is_active, 1) = 1
            """,
            (recipient_id,),
        ).fetchone()

        if current is None:
            raise ValueError(
                "El destinatario activo no existe."
            )

        if current["status"] not in {
            "ERROR",
            "REBOTE",
        }:
            raise ValueError(
                "Solo se corrigen destinatarios en ERROR o REBOTE."
            )

        duplicate = connection.execute(
            """
            SELECT
                id,
                campus_name_snapshot,
                email_address,
                status,
                COALESCE(is_active, 1) AS is_active
            FROM campaign_recipients
            WHERE campaign_id = ?
              AND LOWER(TRIM(email_address)) = LOWER(TRIM(?))
              AND id <> ?
            ORDER BY
                COALESCE(is_active, 1) DESC,
                id DESC
            LIMIT 1
            """,
            (
                current["campaign_id"],
                new_email,
                recipient_id,
            ),
        ).fetchone()

        if duplicate:
            activity = (
                "activo"
                if int(duplicate["is_active"] or 0) == 1
                else "archivado"
            )

            raise ValueError(
                "El correo corregido ya existe en esta campaña. "
                f"Plantel: {duplicate['campus_name_snapshot']}. "
                f"Estado: {duplicate['status']} ({activity}). "
                "Selecciona esa incidencia o captura otro correo "
                "validado. No se realizó ningún cambio."
            )

        try:
            connection.execute("BEGIN")

            master_updated = False

            if update_master:
                master_email = connection.execute(
                    """
                    SELECT id, email, status
                    FROM emails
                    WHERE entity_type = 'CAMPUS'
                      AND entity_id = ?
                      AND LOWER(email) = LOWER(?)
                    ORDER BY
                        CASE WHEN status = 'ACTIVO' THEN 0 ELSE 1 END,
                        id DESC
                    LIMIT 1
                    """,
                    (
                        current["campus_id"],
                        current["email_address"],
                    ),
                ).fetchone()

                if master_email:
                    connection.execute(
                        """
                        UPDATE emails
                        SET
                            email = ?,
                            normalized_email = ?,
                            status = 'ACTIVO'
                        WHERE id = ?
                        """,
                        (
                            new_email,
                            normalized,
                            int(master_email["id"]),
                        ),
                    )

                    connection.execute(
                        """
                        INSERT INTO audit_log (
                            user_id,
                            entity_type,
                            entity_id,
                            action,
                            field_name,
                            old_value,
                            new_value
                        )
                        VALUES (
                            ?,
                            'EMAIL',
                            ?,
                            'CORRECT_CAMPAIGN_ERROR',
                            'email',
                            ?,
                            ?
                        )
                        """,
                        (
                            user_id,
                            int(master_email["id"]),
                            master_email["email"],
                            (
                                f"{new_email} | "
                                f"Motivo: {reason}"
                            ),
                        ),
                    )

                    master_updated = True

                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO emails (
                            entity_type,
                            entity_id,
                            email,
                            normalized_email,
                            email_type,
                            is_primary,
                            status,
                            created_by
                        )
                        VALUES (
                            'CAMPUS',
                            ?, ?, ?, 'INSTITUCIONAL',
                            1, 'ACTIVO', ?
                        )
                        """,
                        (
                            current["campus_id"],
                            new_email,
                            normalized,
                            user_id,
                        ),
                    )

                    master_email_id = int(
                        cursor.lastrowid
                    )

                    connection.execute(
                        """
                        INSERT INTO audit_log (
                            user_id,
                            entity_type,
                            entity_id,
                            action,
                            field_name,
                            old_value,
                            new_value
                        )
                        VALUES (
                            ?,
                            'EMAIL',
                            ?,
                            'CREATE_FROM_CAMPAIGN_CORRECTION',
                            'email',
                            NULL,
                            ?
                        )
                        """,
                        (
                            user_id,
                            master_email_id,
                            (
                                f"{new_email} | "
                                f"Motivo: {reason}"
                            ),
                        ),
                    )

                    master_updated = True

            connection.execute(
                """
                UPDATE campaign_recipients
                SET
                    is_active = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (recipient_id,),
            )

            connection.execute(
                """
                INSERT INTO audit_log (
                    user_id,
                    entity_type,
                    entity_id,
                    action,
                    field_name,
                    old_value,
                    new_value
                )
                VALUES (
                    ?,
                    'CAMPAIGN_RECIPIENT',
                    ?,
                    'ARCHIVE_AFTER_EMAIL_CORRECTION',
                    'is_active',
                    '1',
                    ?
                )
                """,
                (
                    user_id,
                    recipient_id,
                    (
                        "0 | Sustituido por "
                        f"{new_email}. Motivo: {reason}"
                    ),
                ),
            )

            cursor = connection.execute(
                """
                INSERT INTO campaign_recipients (
                    campaign_id,
                    campus_id,
                    contact_id,
                    campus_name_snapshot,
                    email_address,
                    email_type,
                    status,
                    is_active
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, 'PENDIENTE', 1
                )
                """,
                (
                    current["campaign_id"],
                    current["campus_id"],
                    current["contact_id"],
                    current["campus_name_snapshot"],
                    new_email,
                    current["email_type"],
                ),
            )

            new_recipient_id = int(
                cursor.lastrowid
            )

            connection.execute(
                """
                INSERT INTO email_activity (
                    campaign_recipient_id,
                    event_type,
                    details,
                    created_by
                )
                VALUES (
                    ?,
                    'AGREGADO',
                    ?,
                    ?
                )
                """,
                (
                    new_recipient_id,
                    (
                        "Destinatario creado después de "
                        "corregir un error de correo. "
                        f"Anterior: {current['email_address']}. "
                        f"Motivo: {reason}"
                    ),
                    user_id,
                ),
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    return {
        "old_email":
            current["email_address"],

        "new_email":
            new_email,

        "new_recipient_id":
            new_recipient_id,

        "master_updated":
            master_updated,
    }


def get_active_campaign_status_counts(
    campaign_id: int,
) -> dict:
    """
    Conteos operativos de destinatarios activos.
    """

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                status,
                COUNT(*) AS total
            FROM campaign_recipients
            WHERE campaign_id = ?
              AND COALESCE(is_active, 1) = 1
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()

    counts = {
        "PENDIENTE": 0,
        "ENVIADO": 0,
        "RESPONDIO": 0,
        "CONTACTO_REFERIDO": 0,
        "SIN_RESPUESTA": 0,
        "REBOTE": 0,
        "NO_INTERESADO": 0,
        "ERROR": 0,
    }

    for row in rows:
        counts[row["status"]] = int(
            row["total"] or 0
        )

    counts["TOTAL"] = sum(counts.values())

    return counts
