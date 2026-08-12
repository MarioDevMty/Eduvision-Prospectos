from database.connection import get_connection

from services.matching import (
    campus_match_score,
    contact_match_score,
)

from services.normalization import (
    normalize_email,
    normalize_phone,
    normalize_text,
)

from services.data_validation import (
    validate_email_address,
)


# =========================================================
# AUXILIARES
# =========================================================

def get_entity_phones(
    entity_type: str,
    entity_id: int,
) -> list[str]:

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT phone
            FROM phones
            WHERE entity_type = ?
              AND entity_id = ?
              AND status = 'ACTIVO'
            ORDER BY is_primary DESC, id
            """,
            (
                entity_type,
                entity_id,
            ),
        ).fetchall()

    return [
        row["phone"]
        for row in rows
    ]


def get_entity_emails(
    entity_type: str,
    entity_id: int,
) -> list[str]:

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT email
            FROM emails
            WHERE entity_type = ?
              AND entity_id = ?
              AND status = 'ACTIVO'
            ORDER BY is_primary DESC, id
            """,
            (
                entity_type,
                entity_id,
            ),
        ).fetchall()

    return [
        row["email"]
        for row in rows
    ]


def phone_exists(
    entity_type: str,
    entity_id: int,
    phone: str,
) -> bool:

    normalized = normalize_phone(
        phone
    )

    if not normalized:
        return False

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT id
            FROM phones
            WHERE entity_type = ?
              AND entity_id = ?
              AND normalized_phone = ?
              AND status = 'ACTIVO'
            LIMIT 1
            """,
            (
                entity_type,
                entity_id,
                normalized,
            ),
        ).fetchone()

    return row is not None


def email_exists(
    entity_type: str,
    entity_id: int,
    email: str,
) -> bool:

    normalized = normalize_email(
        email
    )

    if not normalized:
        return False

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT id
            FROM emails
            WHERE entity_type = ?
              AND entity_id = ?
              AND normalized_email = ?
              AND status = 'ACTIVO'
            LIMIT 1
            """,
            (
                entity_type,
                entity_id,
                normalized,
            ),
        ).fetchone()

    return row is not None


# =========================================================
# ORGANIZACIONES
# =========================================================

def find_organization_by_normalized_name(
    normalized_name: str,
):

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT *
            FROM organizations
            WHERE normalized_name = ?
            LIMIT 1
            """,
            (normalized_name,),
        ).fetchone()


def create_organization(
    official_name: str,
    subsystem: str | None,
    sector: str | None,
    relationship_type: str | None,
    status: str,
    user_id: int,
) -> dict:

    normalized_name = normalize_text(
        official_name
    )

    existing = (
        find_organization_by_normalized_name(
            normalized_name
        )
    )

    if existing:

        return {
            "created": False,
            "id": existing["id"],
            "existing_name":
                existing["official_name"],
        }

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO organizations (
                official_name,
                normalized_name,
                subsystem,
                sector,
                relationship_type,
                status,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                official_name.strip(),
                normalized_name,
                subsystem or None,
                sector or None,
                relationship_type or None,
                status,
                user_id,
                user_id,
            ),
        )

        organization_id = (
            cursor.lastrowid
        )

        connection.commit()

    return {
        "created": True,
        "id": organization_id,
        "existing_name": None,
    }


# =========================================================
# PLANTELES
# =========================================================

def get_campus_detail(
    campus_id: int,
) -> dict | None:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT
                c.*,
                o.official_name
            FROM campuses c

            JOIN organizations o
                ON o.id = c.organization_id

            WHERE c.id = ?
            LIMIT 1
            """,
            (campus_id,),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    result["phones"] = (
        get_entity_phones(
            "CAMPUS",
            campus_id,
        )
    )

    result["emails"] = (
        get_entity_emails(
            "CAMPUS",
            campus_id,
        )
    )

    return result


def analyze_campus_duplicates(
    organization_id: int,
    campus_name: str,
    municipality: str | None,
    phone: str | None,
) -> list[dict]:

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT *
            FROM campuses
            WHERE organization_id = ?
              AND status <> 'BAJA'
            """,
            (organization_id,),
        ).fetchall()

    candidates = []

    for row in rows:

        phones = get_entity_phones(
            "CAMPUS",
            row["id"],
        )

        analysis = campus_match_score(
            new_name=campus_name,
            new_municipality=municipality,
            new_phone=phone,
            existing_name=row["campus_name"],
            existing_municipality=(
                row["municipality"]
            ),
            existing_phones=phones,
        )

        if analysis["level"] != "BAJA":

            candidates.append(
                {
                    "id": row["id"],
                    "campus_name":
                        row["campus_name"],
                    "campus_type":
                        row["campus_type"],
                    "municipality":
                        row["municipality"],
                    "state":
                        row["state"],
                    "address":
                        row["address"],
                    "phones":
                        ", ".join(phones),
                    "status":
                        row["status"],
                    **analysis,
                }
            )

    return candidates


def create_campus(
    organization_id: int,
    campus_name: str,
    campus_type: str | None,
    municipality: str | None,
    state: str | None,
    address: str | None,
    status: str,
    user_id: int,
    parent_campus_id: int | None = None,
) -> int:

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO campuses (
                organization_id,
                parent_campus_id,
                campus_name,
                normalized_name,
                campus_type,
                municipality,
                state,
                address,
                status,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                parent_campus_id,
                campus_name.strip(),
                normalize_text(
                    campus_name
                ),
                campus_type or None,
                municipality or None,
                state or None,
                address or None,
                status,
                user_id,
                user_id,
            ),
        )

        campus_id = (
            cursor.lastrowid
        )

        connection.commit()

    return campus_id


def add_campus_alias(
    campus_id: int,
    alias: str,
    user_id: int,
) -> bool:

    campus = get_campus_detail(
        campus_id
    )

    if not campus:
        return False

    normalized_alias = normalize_text(
        alias
    )

    if not normalized_alias:
        return False

    if (
        normalize_text(
            campus["campus_name"]
        )
        ==
        normalized_alias
    ):
        return False

    with get_connection() as connection:

        existing = connection.execute(
            """
            SELECT id
            FROM organization_aliases
            WHERE campus_id = ?
              AND normalized_alias = ?
              AND active = 1
            """,
            (
                campus_id,
                normalized_alias,
            ),
        ).fetchone()

        if existing:
            return False

        connection.execute(
            """
            INSERT INTO organization_aliases (
                organization_id,
                campus_id,
                alias,
                normalized_alias,
                source,
                active,
                confirmed_by
            )
            VALUES (
                ?, ?, ?, ?, 'FUSION_MANUAL', 1, ?
            )
            """,
            (
                campus["organization_id"],
                campus_id,
                alias.strip(),
                normalized_alias,
                user_id,
            ),
        )

        connection.commit()

    return True


def merge_campus_data(
    campus_id: int,
    incoming_data: dict,
    selected_fields: list[str],
    user_id: int,
    save_alias: bool = True,
) -> dict:

    existing = get_campus_detail(
        campus_id
    )

    if not existing:

        raise ValueError(
            "El plantel no existe."
        )

    allowed_fields = {
        "campus_type",
        "municipality",
        "state",
        "address",
        "status",
    }

    updated = []

    with get_connection() as connection:

        for field in selected_fields:

            if field not in allowed_fields:
                continue

            new_value = (
                incoming_data.get(field)
                or None
            )

            old_value = (
                existing.get(field)
            )

            if new_value == old_value:
                continue

            connection.execute(
                f"""
                UPDATE campuses
                SET {field} = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    new_value,
                    user_id,
                    campus_id,
                ),
            )

            updated.append(
                field
            )

        connection.commit()

    phone_added = False

    if (
        incoming_data.get("phone")
        and not phone_exists(
            "CAMPUS",
            campus_id,
            incoming_data["phone"],
        )
    ):

        add_phone(
            "CAMPUS",
            campus_id,
            incoming_data["phone"],
            "INSTITUCIONAL",
            user_id,
            False,
        )

        phone_added = True

    email_added = False

    if (
        incoming_data.get("email")
        and not email_exists(
            "CAMPUS",
            campus_id,
            incoming_data["email"],
        )
    ):

        add_email(
            "CAMPUS",
            campus_id,
            incoming_data["email"],
            "INSTITUCIONAL",
            user_id,
            False,
        )

        email_added = True

    alias_added = False

    if save_alias:

        alias_added = add_campus_alias(
            campus_id,
            incoming_data.get(
                "campus_name",
                "",
            ),
            user_id,
        )

    return {
        "fields_updated": updated,
        "phone_added": phone_added,
        "email_added": email_added,
        "alias_added": alias_added,
    }


# =========================================================
# CONTACTOS
# =========================================================

def get_contact_detail(
    contact_id: int,
) -> dict | None:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT
                co.id,
                co.campus_id,
                co.full_name,
                co.position,
                co.area,
                co.notes,
                co.status,
                ca.campus_name,
                org.official_name
            FROM contacts co

            JOIN campuses ca
                ON ca.id = co.campus_id

            JOIN organizations org
                ON org.id = ca.organization_id

            WHERE co.id = ?
            LIMIT 1
            """,
            (contact_id,),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    result["phones"] = (
        get_entity_phones(
            "CONTACT",
            contact_id,
        )
    )

    result["emails"] = (
        get_entity_emails(
            "CONTACT",
            contact_id,
        )
    )

    return result


def analyze_contact_duplicates(
    campus_id: int,
    full_name: str,
    phone: str | None,
    email: str | None,
) -> list[dict]:

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                full_name,
                position,
                area,
                status
            FROM contacts
            WHERE campus_id = ?
            """,
            (campus_id,),
        ).fetchall()

    candidates = []

    for row in rows:

        phones = get_entity_phones(
            "CONTACT",
            row["id"],
        )

        emails = get_entity_emails(
            "CONTACT",
            row["id"],
        )

        analysis = contact_match_score(
            new_name=full_name,
            new_phone=phone,
            new_email=email,
            existing_name=(
                row["full_name"]
            ),
            existing_phones=phones,
            existing_emails=emails,
        )

        if analysis["level"] != "BAJA":

            candidates.append(
                {
                    "id":
                        row["id"],

                    "full_name":
                        row["full_name"],

                    "position":
                        row["position"],

                    "area":
                        row["area"],

                    "phones":
                        ", ".join(phones),

                    "emails":
                        ", ".join(emails),

                    "status":
                        row["status"],

                    **analysis,
                }
            )

    # Ordenar candidatos por relevancia.
    ranking = {
        "EXACTA": 1,
        "MUY_ALTA": 2,
        "ALTA": 3,
        "POSIBLE": 4,
    }

    candidates.sort(
        key=lambda item: (
            ranking.get(
                item["level"],
                99,
            ),
            -item["name_score"],
        )
    )

    return candidates


def create_contact(
    campus_id: int,
    full_name: str,
    position: str | None,
    area: str | None,
    notes: str | None,
    status: str,
    user_id: int,
) -> int:

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO contacts (
                campus_id,
                full_name,
                position,
                area,
                notes,
                status,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campus_id,
                full_name.strip(),
                position or None,
                area or None,
                notes or None,
                status,
                user_id,
                user_id,
            ),
        )

        contact_id = (
            cursor.lastrowid
        )

        connection.commit()

    return contact_id


def merge_contact_data(
    contact_id: int,
    incoming_data: dict,
    selected_fields: list[str],
    user_id: int,
) -> dict:
    """
    Fusiona información con un contacto existente.

    El teléfono y correo nunca sustituyen automáticamente.
    Si son nuevos, se agregan.
    """

    existing = get_contact_detail(
        contact_id
    )

    if not existing:

        raise ValueError(
            "El contacto seleccionado no existe."
        )

    allowed_fields = {
        "full_name",
        "position",
        "area",
        "notes",
        "status",
    }

    updated_fields = []

    with get_connection() as connection:

        for field in selected_fields:

            if field not in allowed_fields:
                continue

            new_value = (
                incoming_data.get(field)
                or None
            )

            old_value = (
                existing.get(field)
            )

            if new_value == old_value:
                continue

            connection.execute(
                f"""
                UPDATE contacts
                SET {field} = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = ?
                WHERE id = ?
                """,
                (
                    new_value,
                    user_id,
                    contact_id,
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
                    'CONTACT',
                    ?,
                    'UPDATE',
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    user_id,
                    contact_id,
                    field,
                    old_value,
                    new_value,
                ),
            )

            updated_fields.append(
                field
            )

        connection.commit()

    # -----------------------------------------------------
    # TELÉFONO
    # -----------------------------------------------------

    incoming_phone = (
        incoming_data.get("phone")
        or ""
    ).strip()

    phone_added = False

    if (
        incoming_phone
        and not phone_exists(
            "CONTACT",
            contact_id,
            incoming_phone,
        )
    ):

        add_phone(
            entity_type="CONTACT",
            entity_id=contact_id,
            phone=incoming_phone,
            phone_type="DIRECTO",
            user_id=user_id,
            is_primary=False,
        )

        phone_added = True

    # -----------------------------------------------------
    # CORREO
    # -----------------------------------------------------

    incoming_email = (
        incoming_data.get("email")
        or ""
    ).strip()

    email_added = False

    if (
        incoming_email
        and not email_exists(
            "CONTACT",
            contact_id,
            incoming_email,
        )
    ):

        add_email(
            entity_type="CONTACT",
            entity_id=contact_id,
            email=incoming_email,
            email_type="DIRECTO",
            user_id=user_id,
            is_primary=False,
        )

        email_added = True

    return {
        "fields_updated":
            updated_fields,

        "phone_added":
            phone_added,

        "email_added":
            email_added,
    }


# =========================================================
# TELÉFONO / EMAIL
# =========================================================

def add_phone(
    entity_type: str,
    entity_id: int,
    phone: str,
    phone_type: str,
    user_id: int,
    is_primary: bool = False,
) -> int:

    if phone_exists(
        entity_type,
        entity_id,
        phone,
    ):
        return 0

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO phones (
                entity_type,
                entity_id,
                phone,
                normalized_phone,
                phone_type,
                is_primary,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                phone.strip(),
                normalize_phone(phone),
                phone_type,
                int(is_primary),
                user_id,
            ),
        )

        connection.commit()

    return cursor.lastrowid


def add_email(
    entity_type: str,
    entity_id: int,
    email: str,
    email_type: str,
    user_id: int,
    is_primary: bool = False,
) -> int:

    is_valid, validation_reason = (
        validate_email_address(
            email
        )
    )

    if not is_valid:
        raise ValueError(
            validation_reason
        )

    if email_exists(
        entity_type,
        entity_id,
        email,
    ):
        return 0

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO emails (
                entity_type,
                entity_id,
                email,
                normalized_email,
                email_type,
                is_primary,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                email.strip(),
                normalize_email(email),
                email_type,
                int(is_primary),
                user_id,
            ),
        )

        connection.commit()

    return cursor.lastrowid


# =========================================================
# CONSULTAS
# =========================================================

def get_organizations() -> list:

    with get_connection() as connection:

        return connection.execute(
            """
            SELECT
                id,
                official_name,
                subsystem,
                sector,
                relationship_type,
                status
            FROM organizations
            ORDER BY official_name
            """
        ).fetchall()


def get_campuses(
    organization_id: int | None = None,
) -> list:

    with get_connection() as connection:

        query = """
            SELECT
                c.id,
                c.organization_id,
                c.campus_name,
                c.campus_type,
                c.municipality,
                c.state,
                c.status,
                o.official_name
            FROM campuses c
            JOIN organizations o
                ON o.id = c.organization_id
        """

        params = ()

        if organization_id is not None:

            query += """
                WHERE c.organization_id = ?
            """

            params = (
                organization_id,
            )

        query += """
            ORDER BY
                o.official_name,
                c.campus_name
        """

        return connection.execute(
            query,
            params,
        ).fetchall()


def get_contacts(
    campus_id: int | None = None,
) -> list:

    with get_connection() as connection:

        if campus_id is not None:

            return connection.execute(
                """
                SELECT
                    id,
                    campus_id,
                    full_name,
                    position,
                    area,
                    status
                FROM contacts
                WHERE campus_id = ?
                ORDER BY full_name
                """,
                (
                    campus_id,
                ),
            ).fetchall()

        return connection.execute(
            """
            SELECT
                co.id,
                co.full_name,
                co.position,
                co.area,
                co.status,
                ca.campus_name,
                org.official_name
            FROM contacts co
            JOIN campuses ca
                ON ca.id = co.campus_id
            JOIN organizations org
                ON org.id = ca.organization_id
            ORDER BY
                org.official_name,
                ca.campus_name,
                co.full_name
            """
        ).fetchall()