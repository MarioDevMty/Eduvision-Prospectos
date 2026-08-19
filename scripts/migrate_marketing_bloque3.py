from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "eduvision.db"
BACKUP_DIR = BASE_DIR / "backups"

MIGRATION_ID = "20260818_marketing_bloque3_recipients"


def columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> dict[str, sqlite3.Row]:
    return {
        row["name"]: row
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


def backup_database() -> Path:
    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    target = (
        BACKUP_DIR
        / f"eduvision_antes_marketing_bloque3_{timestamp}.db"
    )

    source = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )
    destination = sqlite3.connect(
        target
    )

    try:
        source.backup(
            destination
        )
    finally:
        destination.close()
        source.close()

    return target


def validate_base(
    connection: sqlite3.Connection,
) -> None:
    required = {
        "campaigns",
        "campaign_recipients",
        "organizations",
        "campuses",
        "contacts",
        "email_activity",
        "email_send_attempts",
    }

    existing = {
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    }

    missing = required - existing

    if missing:
        raise RuntimeError(
            "Faltan tablas requeridas: "
            + ", ".join(
                sorted(missing)
            )
        )

    integrity = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    if integrity != "ok":
        raise RuntimeError(
            f"integrity_check previo falló: {integrity}"
        )

    contact_columns = columns(
        connection,
        "contacts",
    )

    if "organization_id" not in contact_columns:
        raise RuntimeError(
            "CRUD Bloque 1 no está aplicado: "
            "contacts.organization_id no existe."
        )

    if int(
        contact_columns["campus_id"]["notnull"]
    ) != 0:
        raise RuntimeError(
            "CRUD Bloque 1 no está aplicado: "
            "contacts.campus_id todavía es obligatorio."
        )


def already_migrated(
    connection: sqlite3.Connection,
) -> bool:
    current = columns(
        connection,
        "campaign_recipients",
    )

    required = {
        "recipient_type",
        "organization_id",
        "organization_name_snapshot",
        "recipient_name_snapshot",
        "is_active",
    }

    if not required.issubset(
        current.keys()
    ):
        return False

    return (
        int(
            current["campus_id"]["notnull"]
        )
        == 0
    )


def validate_historical_rows(
    connection: sqlite3.Connection,
) -> None:
    unresolved = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_recipients cr
        LEFT JOIN campuses c
          ON c.id = cr.campus_id
        LEFT JOIN organizations o
          ON o.id = c.organization_id
        WHERE cr.campus_id IS NULL
           OR c.id IS NULL
           OR o.id IS NULL
        """
    ).fetchone()[0]

    if unresolved:
        raise RuntimeError(
            f"Hay {unresolved} destinatarios históricos "
            "sin una relación válida Plantel -> Organización."
        )

    invalid_contacts = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_recipients cr
        LEFT JOIN contacts co
          ON co.id = cr.contact_id
        WHERE cr.contact_id IS NOT NULL
          AND co.id IS NULL
        """
    ).fetchone()[0]

    if invalid_contacts:
        raise RuntimeError(
            f"Hay {invalid_contacts} destinatarios históricos "
            "con contact_id inválido."
        )


def create_new_table(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "DROP TABLE IF EXISTS campaign_recipients_b3_new"
    )

    connection.execute(
        """
        CREATE TABLE campaign_recipients_b3_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            campaign_id INTEGER NOT NULL,

            recipient_type TEXT NOT NULL
                CHECK (
                    recipient_type IN (
                        'INSTITUCIONAL',
                        'CONTACTO'
                    )
                ),

            organization_id INTEGER NOT NULL,
            campus_id INTEGER,
            contact_id INTEGER,

            organization_name_snapshot TEXT NOT NULL,
            recipient_name_snapshot TEXT,
            campus_name_snapshot TEXT,

            email_address TEXT NOT NULL,

            email_type TEXT NOT NULL DEFAULT 'INSTITUCIONAL'
                CHECK (
                    email_type IN (
                        'INSTITUCIONAL',
                        'CONTACTO'
                    )
                ),

            status TEXT NOT NULL DEFAULT 'PENDIENTE'
                CHECK (
                    status IN (
                        'PENDIENTE',
                        'ENVIADO',
                        'RESPONDIO',
                        'CONTACTO_REFERIDO',
                        'SIN_RESPUESTA',
                        'REBOTE',
                        'NO_INTERESADO',
                        'ERROR'
                    )
                ),

            is_active INTEGER NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1)),

            sent_at TEXT,
            responded_at TEXT,

            referred_name TEXT,
            referred_position TEXT,
            referred_email TEXT,
            referred_phone TEXT,

            notes TEXT,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (campaign_id)
                REFERENCES campaigns(id),

            FOREIGN KEY (organization_id)
                REFERENCES organizations(id),

            FOREIGN KEY (campus_id)
                REFERENCES campuses(id),

            FOREIGN KEY (contact_id)
                REFERENCES contacts(id),

            CHECK (
                (
                    recipient_type = 'INSTITUCIONAL'
                    AND contact_id IS NULL
                )
                OR
                (
                    recipient_type = 'CONTACTO'
                    AND contact_id IS NOT NULL
                )
            ),

            UNIQUE (
                campaign_id,
                email_address
            )
        )
        """
    )


def migrate(
    connection: sqlite3.Connection,
) -> tuple[int, int]:
    validate_historical_rows(
        connection
    )

    current_columns = columns(
        connection,
        "campaign_recipients",
    )

    has_is_active = (
        "is_active" in current_columns
    )

    before = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_recipients
        """
    ).fetchone()[0]

    create_new_table(
        connection
    )

    is_active_expr = (
        "COALESCE(cr.is_active, 1)"
        if has_is_active
        else "1"
    )

    sql = f"""
        INSERT INTO campaign_recipients_b3_new (
            id,
            campaign_id,
            recipient_type,
            organization_id,
            campus_id,
            contact_id,
            organization_name_snapshot,
            recipient_name_snapshot,
            campus_name_snapshot,
            email_address,
            email_type,
            status,
            is_active,
            sent_at,
            responded_at,
            referred_name,
            referred_position,
            referred_email,
            referred_phone,
            notes,
            created_at,
            updated_at
        )
        SELECT
            cr.id,
            cr.campaign_id,
            CASE
                WHEN cr.contact_id IS NOT NULL
                THEN 'CONTACTO'
                ELSE 'INSTITUCIONAL'
            END,
            c.organization_id,
            cr.campus_id,
            cr.contact_id,
            o.official_name,
            CASE
                WHEN cr.contact_id IS NOT NULL
                THEN co.full_name
                ELSE COALESCE(
                    cr.campus_name_snapshot,
                    c.campus_name
                )
            END,
            COALESCE(
                cr.campus_name_snapshot,
                c.campus_name
            ),
            cr.email_address,
            cr.email_type,
            cr.status,
            {is_active_expr},
            cr.sent_at,
            cr.responded_at,
            cr.referred_name,
            cr.referred_position,
            cr.referred_email,
            cr.referred_phone,
            cr.notes,
            cr.created_at,
            cr.updated_at
        FROM campaign_recipients cr
        JOIN campuses c
          ON c.id = cr.campus_id
        JOIN organizations o
          ON o.id = c.organization_id
        LEFT JOIN contacts co
          ON co.id = cr.contact_id
        ORDER BY cr.id
    """

    connection.execute(
        sql
    )

    copied = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_recipients_b3_new
        """
    ).fetchone()[0]

    if copied != before:
        raise RuntimeError(
            "El número de destinatarios no coincide "
            f"(antes={before}, copia={copied})."
        )

    connection.execute(
        "DROP TABLE campaign_recipients"
    )

    connection.execute(
        """
        ALTER TABLE campaign_recipients_b3_new
        RENAME TO campaign_recipients
        """
    )

    index_statements = [
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_campaign
        ON campaign_recipients(campaign_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_organization
        ON campaign_recipients(organization_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_campus
        ON campaign_recipients(campus_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_contact
        ON campaign_recipients(contact_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_type
        ON campaign_recipients(recipient_type)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_status
        ON campaign_recipients(status)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_recipients_email
        ON campaign_recipients(email_address)
        """,
    ]

    for statement in index_statements:
        connection.execute(
            statement
        )

    after = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_recipients
        """
    ).fetchone()[0]

    return before, after


def validate_new_model(
    connection: sqlite3.Connection,
) -> None:
    invalid = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_recipients
        WHERE organization_id IS NULL
           OR organization_name_snapshot IS NULL
           OR (
                recipient_type = 'CONTACTO'
                AND contact_id IS NULL
              )
           OR (
                recipient_type = 'INSTITUCIONAL'
                AND contact_id IS NOT NULL
              )
        """
    ).fetchone()[0]

    if invalid:
        raise RuntimeError(
            f"Hay {invalid} destinatarios incompatibles "
            "con el nuevo modelo."
        )

    orphan_activity = connection.execute(
        """
        SELECT COUNT(*)
        FROM email_activity ea
        LEFT JOIN campaign_recipients cr
          ON cr.id = ea.campaign_recipient_id
        WHERE cr.id IS NULL
        """
    ).fetchone()[0]

    orphan_attempts = connection.execute(
        """
        SELECT COUNT(*)
        FROM email_send_attempts esa
        LEFT JOIN campaign_recipients cr
          ON cr.id = esa.campaign_recipient_id
        WHERE cr.id IS NULL
        """
    ).fetchone()[0]

    if orphan_activity or orphan_attempts:
        raise RuntimeError(
            "La migración dejó referencias huérfanas: "
            f"actividad={orphan_activity}, intentos={orphan_attempts}."
        )


def record_migration(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (id)
        VALUES (?)
        """,
        (MIGRATION_ID,),
    )


def main() -> int:
    if not DB_PATH.exists():
        print(
            f"ERROR: no existe {DB_PATH}"
        )
        return 1

    print(
        "Eduvision - Marketing Bloque 3"
    )
    print(
        f"Base: {DB_PATH}"
    )
    print(
        "Streamlit debe estar detenido."
    )

    backup = backup_database()

    print(
        f"Backup creado: {backup}"
    )

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute(
            "PRAGMA foreign_keys = OFF"
        )

        validate_base(
            connection
        )

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        if already_migrated(
            connection
        ):
            before = connection.execute(
                """
                SELECT COUNT(*)
                FROM campaign_recipients
                """
            ).fetchone()[0]
            after = before
            print(
                "campaign_recipients ya utiliza el modelo Bloque 3."
            )
        else:
            before, after = migrate(
                connection
            )

        validate_new_model(
            connection
        )

        record_migration(
            connection
        )

        connection.execute(
            "COMMIT"
        )

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        fk_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if fk_errors:
            raise RuntimeError(
                "foreign_key_check encontró "
                f"{len(fk_errors)} error(es)."
            )

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                f"integrity_check posterior falló: {integrity}"
            )

        validate_new_model(
            connection
        )

        print(
            f"Destinatarios antes: {before}"
        )
        print(
            f"Destinatarios después: {after}"
        )
        print(
            "Migración completada correctamente."
        )
        return 0

    except Exception as exc:
        try:
            connection.execute(
                "ROLLBACK"
            )
        except sqlite3.Error:
            pass

        print(
            f"ERROR: {exc}"
        )
        print(
            f"Backup disponible: {backup}"
        )
        return 1

    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(
        main()
    )
