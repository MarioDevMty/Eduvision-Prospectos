from database.connection import get_connection
from services.data_validation import validate_email_address
from services.normalization import normalize_email, normalize_text


def _audit(connection, user_id, entity_type, entity_id, action,
           field_name="", old_value=None, new_value=None):
    connection.execute(
        """
        INSERT INTO audit_log (
            user_id, entity_type, entity_id, action,
            field_name, old_value, new_value
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            entity_type,
            entity_id,
            action,
            field_name or None,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
        ),
    )


def get_organization_management_summary(organization_id: int) -> dict | None:
    with get_connection() as connection:
        organization = connection.execute(
            "SELECT * FROM organizations WHERE id = ?",
            (organization_id,),
        ).fetchone()

        if organization is None:
            return None

        counts = connection.execute(
            """
            SELECT
                COUNT(*) AS campuses_total,
                SUM(CASE WHEN status <> 'BAJA' THEN 1 ELSE 0 END)
                    AS campuses_active,
                SUM(CASE WHEN status = 'BAJA' THEN 1 ELSE 0 END)
                    AS campuses_inactive
            FROM campuses
            WHERE organization_id = ?
            """,
            (organization_id,),
        ).fetchone()

        active_emails = connection.execute(
            """
            SELECT COUNT(*)
            FROM emails e
            JOIN campuses c
              ON c.id = e.entity_id
             AND e.entity_type = 'CAMPUS'
            WHERE c.organization_id = ?
              AND e.status = 'ACTIVO'
            """,
            (organization_id,),
        ).fetchone()[0]

        inactive_emails = connection.execute(
            """
            SELECT COUNT(*)
            FROM emails e
            JOIN campuses c
              ON c.id = e.entity_id
             AND e.entity_type = 'CAMPUS'
            WHERE c.organization_id = ?
              AND e.status <> 'ACTIVO'
            """,
            (organization_id,),
        ).fetchone()[0]

    result = dict(organization)
    result.update(
        {
            "campuses_total": counts["campuses_total"] or 0,
            "campuses_active": counts["campuses_active"] or 0,
            "campuses_inactive": counts["campuses_inactive"] or 0,
            "active_emails": active_emails or 0,
            "inactive_emails": inactive_emails or 0,
        }
    )
    return result


def get_organization_campuses(
    organization_id: int,
    include_inactive: bool = True,
) -> list:
    query = """
        SELECT
            c.id,
            c.organization_id,
            c.campus_name,
            c.campus_type,
            c.campus_code,
            c.address,
            c.neighborhood,
            c.postal_code,
            c.municipality,
            c.state,
            c.website,
            c.status,
            (
                SELECT GROUP_CONCAT(e.email, ' | ')
                FROM emails e
                WHERE e.entity_type = 'CAMPUS'
                  AND e.entity_id = c.id
                  AND e.status = 'ACTIVO'
            ) AS active_emails
        FROM campuses c
        WHERE c.organization_id = ?
    """

    if not include_inactive:
        query += " AND c.status <> 'BAJA' "

    query += " ORDER BY c.campus_name "

    with get_connection() as connection:
        return connection.execute(
            query,
            (organization_id,),
        ).fetchall()


def get_campus_management_detail(campus_id: int) -> dict | None:
    with get_connection() as connection:
        campus = connection.execute(
            """
            SELECT c.*, o.official_name
            FROM campuses c
            JOIN organizations o
              ON o.id = c.organization_id
            WHERE c.id = ?
            """,
            (campus_id,),
        ).fetchone()

        if campus is None:
            return None

        emails = connection.execute(
            """
            SELECT
                id, email, normalized_email, email_type,
                is_primary, status, created_at
            FROM emails
            WHERE entity_type = 'CAMPUS'
              AND entity_id = ?
            ORDER BY
                CASE WHEN status = 'ACTIVO' THEN 0 ELSE 1 END,
                is_primary DESC,
                id
            """,
            (campus_id,),
        ).fetchall()

    result = dict(campus)
    result["emails"] = [dict(row) for row in emails]
    return result


def update_campus(
    campus_id: int,
    campus_name: str,
    campus_type: str,
    campus_code: str,
    address: str,
    neighborhood: str,
    postal_code: str,
    municipality: str,
    state: str,
    website: str,
    status: str,
    user_id: int,
) -> None:
    campus_name = (campus_name or "").strip()

    if not campus_name:
        raise ValueError("El nombre del plantel es obligatorio.")

    with get_connection() as connection:
        current = connection.execute(
            "SELECT * FROM campuses WHERE id = ?",
            (campus_id,),
        ).fetchone()

        if current is None:
            raise ValueError("El plantel no existe.")

        values = {
            "campus_name": campus_name,
            "normalized_name": normalize_text(campus_name),
            "campus_type": (campus_type or "").strip() or None,
            "campus_code": (campus_code or "").strip() or None,
            "address": (address or "").strip() or None,
            "neighborhood": (neighborhood or "").strip() or None,
            "postal_code": (postal_code or "").strip() or None,
            "municipality": (municipality or "").strip() or None,
            "state": (state or "").strip() or None,
            "website": (website or "").strip() or None,
            "status": status,
        }

        for field, new_value in values.items():
            if current[field] != new_value:
                _audit(
                    connection,
                    user_id,
                    "CAMPUS",
                    campus_id,
                    "UPDATE",
                    field,
                    current[field],
                    new_value,
                )

        connection.execute(
            """
            UPDATE campuses
            SET
                campus_name = ?,
                normalized_name = ?,
                campus_type = ?,
                campus_code = ?,
                address = ?,
                neighborhood = ?,
                postal_code = ?,
                municipality = ?,
                state = ?,
                website = ?,
                status = ?,
                updated_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                values["campus_name"],
                values["normalized_name"],
                values["campus_type"],
                values["campus_code"],
                values["address"],
                values["neighborhood"],
                values["postal_code"],
                values["municipality"],
                values["state"],
                values["website"],
                values["status"],
                user_id,
                campus_id,
            ),
        )
        connection.commit()


def add_validated_email(
    campus_id: int,
    email_address: str,
    email_type: str,
    is_primary: bool,
    user_id: int,
) -> int:
    valid, reason = validate_email_address(email_address)
    if not valid:
        raise ValueError(reason)

    normalized = normalize_email(email_address)

    with get_connection() as connection:
        duplicate = connection.execute(
            """
            SELECT id
            FROM emails
            WHERE entity_type = 'CAMPUS'
              AND entity_id = ?
              AND normalized_email = ?
              AND status = 'ACTIVO'
            LIMIT 1
            """,
            (campus_id, normalized),
        ).fetchone()

        if duplicate:
            raise ValueError(
                "El correo ya existe como activo en este plantel."
            )

        if is_primary:
            connection.execute(
                """
                UPDATE emails
                SET is_primary = 0
                WHERE entity_type = 'CAMPUS'
                  AND entity_id = ?
                """,
                (campus_id,),
            )

        cursor = connection.execute(
            """
            INSERT INTO emails (
                entity_type, entity_id, email, normalized_email,
                email_type, is_primary, status, created_by
            )
            VALUES (
                'CAMPUS', ?, ?, ?, ?, ?, 'ACTIVO', ?
            )
            """,
            (
                campus_id,
                email_address.strip().lower(),
                normalized,
                email_type or "INSTITUCIONAL",
                int(is_primary),
                user_id,
            ),
        )

        email_id = int(cursor.lastrowid)

        _audit(
            connection,
            user_id,
            "EMAIL",
            email_id,
            "CREATE",
            "email",
            None,
            email_address.strip().lower(),
        )

        connection.commit()
        return email_id


def update_email(
    email_id: int,
    email_address: str,
    email_type: str,
    is_primary: bool,
    status: str,
    user_id: int,
) -> None:
    valid, reason = validate_email_address(email_address)
    if not valid:
        raise ValueError(reason)

    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM emails
            WHERE id = ?
              AND entity_type = 'CAMPUS'
            """,
            (email_id,),
        ).fetchone()

        if current is None:
            raise ValueError("El correo no existe.")

        normalized = normalize_email(email_address)

        duplicate = connection.execute(
            """
            SELECT id
            FROM emails
            WHERE entity_type = 'CAMPUS'
              AND entity_id = ?
              AND normalized_email = ?
              AND status = 'ACTIVO'
              AND id <> ?
            LIMIT 1
            """,
            (
                current["entity_id"],
                normalized,
                email_id,
            ),
        ).fetchone()

        if duplicate:
            raise ValueError(
                "El correo ya existe como activo en este plantel."
            )

        if is_primary:
            connection.execute(
                """
                UPDATE emails
                SET is_primary = 0
                WHERE entity_type = 'CAMPUS'
                  AND entity_id = ?
                  AND id <> ?
                """,
                (
                    current["entity_id"],
                    email_id,
                ),
            )

        new_values = {
            "email": email_address.strip().lower(),
            "normalized_email": normalized,
            "email_type": email_type or "INSTITUCIONAL",
            "is_primary": int(is_primary),
            "status": status,
        }

        for field, new_value in new_values.items():
            if current[field] != new_value:
                _audit(
                    connection,
                    user_id,
                    "EMAIL",
                    email_id,
                    "UPDATE",
                    field,
                    current[field],
                    new_value,
                )

        connection.execute(
            """
            UPDATE emails
            SET
                email = ?,
                normalized_email = ?,
                email_type = ?,
                is_primary = ?,
                status = ?
            WHERE id = ?
            """,
            (
                new_values["email"],
                new_values["normalized_email"],
                new_values["email_type"],
                new_values["is_primary"],
                new_values["status"],
                email_id,
            ),
        )
        connection.commit()


def deactivate_email(
    email_id: int,
    user_id: int,
    reason: str,
) -> None:
    reason = (reason or "").strip()

    if not reason:
        raise ValueError("El motivo es obligatorio.")

    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM emails
            WHERE id = ?
              AND entity_type = 'CAMPUS'
            """,
            (email_id,),
        ).fetchone()

        if current is None:
            raise ValueError("El correo no existe.")

        connection.execute(
            """
            UPDATE emails
            SET status = 'INACTIVO',
                is_primary = 0
            WHERE id = ?
            """,
            (email_id,),
        )

        _audit(
            connection,
            user_id,
            "EMAIL",
            email_id,
            "DEACTIVATE",
            "status",
            current["status"],
            f"INACTIVO | Motivo: {reason}",
        )

        connection.commit()


def reactivate_email(
    email_id: int,
    user_id: int,
) -> None:
    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM emails
            WHERE id = ?
              AND entity_type = 'CAMPUS'
            """,
            (email_id,),
        ).fetchone()

        if current is None:
            raise ValueError("El correo no existe.")

        valid, reason = validate_email_address(
            current["email"]
        )
        if not valid:
            raise ValueError(
                f"No puede reactivarse: {reason}"
            )

        connection.execute(
            "UPDATE emails SET status = 'ACTIVO' WHERE id = ?",
            (email_id,),
        )

        _audit(
            connection,
            user_id,
            "EMAIL",
            email_id,
            "REACTIVATE",
            "status",
            current["status"],
            "ACTIVO",
        )

        connection.commit()


def set_primary_email(
    email_id: int,
    user_id: int,
) -> None:
    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM emails
            WHERE id = ?
              AND entity_type = 'CAMPUS'
            """,
            (email_id,),
        ).fetchone()

        if current is None:
            raise ValueError("El correo no existe.")

        if current["status"] != "ACTIVO":
            raise ValueError(
                "Solo un correo activo puede ser principal."
            )

        connection.execute(
            """
            UPDATE emails
            SET is_primary = 0
            WHERE entity_type = 'CAMPUS'
              AND entity_id = ?
            """,
            (current["entity_id"],),
        )

        connection.execute(
            "UPDATE emails SET is_primary = 1 WHERE id = ?",
            (email_id,),
        )

        _audit(
            connection,
            user_id,
            "EMAIL",
            email_id,
            "SET_PRIMARY",
            "is_primary",
            current["is_primary"],
            1,
        )

        connection.commit()


def reset_organization_data(
    organization_id: int,
    user_id: int,
    reason: str,
) -> dict:
    reason = (reason or "").strip()

    if not reason:
        raise ValueError(
            "El motivo del reinicio es obligatorio."
        )

    with get_connection() as connection:
        organization = connection.execute(
            "SELECT * FROM organizations WHERE id = ?",
            (organization_id,),
        ).fetchone()

        if organization is None:
            raise ValueError(
                "La organización no existe."
            )

        campus_rows = connection.execute(
            """
            SELECT id, status
            FROM campuses
            WHERE organization_id = ?
              AND status <> 'BAJA'
            """,
            (organization_id,),
        ).fetchall()

        campus_ids = [
            int(row["id"])
            for row in campus_rows
        ]

        if not campus_ids:
            return {
                "organization": organization["official_name"],
                "campuses_deactivated": 0,
                "emails_deactivated": 0,
                "phones_deactivated": 0,
                "contacts_deactivated": 0,
            }

        placeholders = ",".join(
            "?"
            for _ in campus_ids
        )

        email_rows = connection.execute(
            f"""
            SELECT id, status
            FROM emails
            WHERE (
                    entity_type = 'CAMPUS'
                    AND entity_id IN ({placeholders})
                  )
               OR (
                    entity_type = 'CONTACT'
                    AND entity_id IN (
                        SELECT id
                        FROM contacts
                        WHERE campus_id IN ({placeholders})
                    )
                  )
            """,
            campus_ids + campus_ids,
        ).fetchall()

        phone_rows = connection.execute(
            f"""
            SELECT id, status
            FROM phones
            WHERE (
                    entity_type = 'CAMPUS'
                    AND entity_id IN ({placeholders})
                  )
               OR (
                    entity_type = 'CONTACT'
                    AND entity_id IN (
                        SELECT id
                        FROM contacts
                        WHERE campus_id IN ({placeholders})
                    )
                  )
            """,
            campus_ids + campus_ids,
        ).fetchall()

        contact_rows = connection.execute(
            f"""
            SELECT id, status
            FROM contacts
            WHERE campus_id IN ({placeholders})
              AND status <> 'BAJA'
            """,
            campus_ids,
        ).fetchall()

        try:
            connection.execute("BEGIN")

            connection.execute(
                f"""
                UPDATE emails
                SET status = 'INACTIVO',
                    is_primary = 0
                WHERE (
                        entity_type = 'CAMPUS'
                        AND entity_id IN ({placeholders})
                      )
                   OR (
                        entity_type = 'CONTACT'
                        AND entity_id IN (
                            SELECT id
                            FROM contacts
                            WHERE campus_id IN ({placeholders})
                        )
                      )
                """,
                campus_ids + campus_ids,
            )

            connection.execute(
                f"""
                UPDATE phones
                SET status = 'INACTIVO',
                    is_primary = 0
                WHERE (
                        entity_type = 'CAMPUS'
                        AND entity_id IN ({placeholders})
                      )
                   OR (
                        entity_type = 'CONTACT'
                        AND entity_id IN (
                            SELECT id
                            FROM contacts
                            WHERE campus_id IN ({placeholders})
                        )
                      )
                """,
                campus_ids + campus_ids,
            )

            connection.execute(
                f"""
                UPDATE contacts
                SET status = 'BAJA',
                    updated_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE campus_id IN ({placeholders})
                  AND status <> 'BAJA'
                """,
                [user_id] + campus_ids,
            )

            connection.execute(
                f"""
                UPDATE campuses
                SET status = 'BAJA',
                    updated_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
                """,
                [user_id] + campus_ids,
            )

            for row in campus_rows:
                _audit(
                    connection,
                    user_id,
                    "CAMPUS",
                    int(row["id"]),
                    "ORGANIZATION_RESET",
                    "status",
                    row["status"],
                    f"BAJA | Motivo: {reason}",
                )

            for row in email_rows:
                _audit(
                    connection,
                    user_id,
                    "EMAIL",
                    int(row["id"]),
                    "ORGANIZATION_RESET",
                    "status",
                    row["status"],
                    f"INACTIVO | Motivo: {reason}",
                )

            for row in phone_rows:
                _audit(
                    connection,
                    user_id,
                    "PHONE",
                    int(row["id"]),
                    "ORGANIZATION_RESET",
                    "status",
                    row["status"],
                    f"INACTIVO | Motivo: {reason}",
                )

            for row in contact_rows:
                _audit(
                    connection,
                    user_id,
                    "CONTACT",
                    int(row["id"]),
                    "ORGANIZATION_RESET",
                    "status",
                    row["status"],
                    f"BAJA | Motivo: {reason}",
                )

            _audit(
                connection,
                user_id,
                "ORGANIZATION",
                organization_id,
                "RESET_DATA",
                "organization",
                organization["official_name"],
                reason,
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    return {
        "organization": organization["official_name"],
        "campuses_deactivated": len(campus_rows),
        "emails_deactivated": len(email_rows),
        "phones_deactivated": len(phone_rows),
        "contacts_deactivated": len(contact_rows),
    }
