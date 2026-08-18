from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "eduvision.db"
BACKUP_DIR = BASE_DIR / "backups"
MIGRATION_ID = "20260818_crud_bloque1_contacts_org_scope"


def table_columns(connection: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    return {
        row["name"]: row
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def create_consistent_backup(db_path: Path) -> Path:
    """Crea un backup SQLite consistente, incluso si la base usa WAL."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"eduvision_antes_crud_bloque1_{stamp}.db"

    source = sqlite3.connect(db_path, timeout=30)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    return backup_path


def validate_preconditions(connection: sqlite3.Connection) -> None:
    required = {"users", "organizations", "campuses", "contacts"}
    existing = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing = required - existing
    if missing:
        raise RuntimeError(
            "Faltan tablas requeridas: " + ", ".join(sorted(missing))
        )

    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(
            f"PRAGMA integrity_check falló antes de migrar: {integrity}"
        )


def ensure_organization_type(connection: sqlite3.Connection) -> None:
    columns = table_columns(connection, "organizations")
    if "organization_type" not in columns:
        connection.execute(
            "ALTER TABLE organizations ADD COLUMN organization_type TEXT"
        )


def contacts_already_migrated(connection: sqlite3.Connection) -> bool:
    columns = table_columns(connection, "contacts")
    if "organization_id" not in columns or "campus_id" not in columns:
        return False
    # PRAGMA table_info.notnull == 0 => permite NULL.
    return int(columns["campus_id"]["notnull"]) == 0


def validate_contact_ownership(connection: sqlite3.Connection) -> None:
    missing_org = connection.execute(
        "SELECT COUNT(*) FROM contacts WHERE organization_id IS NULL"
    ).fetchone()[0]
    if missing_org:
        raise RuntimeError(f"Hay {missing_org} contactos sin organization_id.")

    invalid_org = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts co
        LEFT JOIN organizations o ON o.id = co.organization_id
        WHERE o.id IS NULL
        """
    ).fetchone()[0]
    if invalid_org:
        raise RuntimeError(
            f"Hay {invalid_org} contactos con organization_id inválido."
        )

    invalid_campus = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts co
        LEFT JOIN campuses c ON c.id = co.campus_id
        WHERE co.campus_id IS NOT NULL AND c.id IS NULL
        """
    ).fetchone()[0]
    if invalid_campus:
        raise RuntimeError(
            f"Hay {invalid_campus} contactos con campus_id inválido."
        )

    mismatch = connection.execute(
        """
        SELECT COUNT(*)
        FROM contacts co
        JOIN campuses c ON c.id = co.campus_id
        WHERE co.campus_id IS NOT NULL
          AND co.organization_id <> c.organization_id
        """
    ).fetchone()[0]
    if mismatch:
        raise RuntimeError(
            f"Hay {mismatch} contactos cuyo plantel pertenece a otra organización."
        )


def migrate_contacts(connection: sqlite3.Connection) -> tuple[int, int]:
    columns = table_columns(connection, "contacts")
    has_org_id = "organization_id" in columns

    total_before = connection.execute(
        "SELECT COUNT(*) FROM contacts"
    ).fetchone()[0]

    if has_org_id:
        unresolved = connection.execute(
            """
            SELECT COUNT(*)
            FROM contacts co
            LEFT JOIN campuses c ON c.id = co.campus_id
            LEFT JOIN organizations o
              ON o.id = COALESCE(co.organization_id, c.organization_id)
            WHERE COALESCE(co.organization_id, c.organization_id) IS NULL
               OR o.id IS NULL
               OR (co.campus_id IS NOT NULL AND c.id IS NULL)
               OR (
                    co.campus_id IS NOT NULL
                    AND co.organization_id IS NOT NULL
                    AND co.organization_id <> c.organization_id
                  )
            """
        ).fetchone()[0]
    else:
        unresolved = connection.execute(
            """
            SELECT COUNT(*)
            FROM contacts co
            LEFT JOIN campuses c ON c.id = co.campus_id
            LEFT JOIN organizations o ON o.id = c.organization_id
            WHERE co.campus_id IS NULL
               OR c.id IS NULL
               OR o.id IS NULL
            """
        ).fetchone()[0]

    if unresolved:
        raise RuntimeError(
            f"No se puede migrar: {unresolved} contactos históricos no tienen "
            "una relación Plantel -> Organización válida."
        )

    connection.execute("DROP TABLE IF EXISTS contacts_crud1_new")
    connection.execute(
        """
        CREATE TABLE contacts_crud1_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            campus_id INTEGER,
            full_name TEXT NOT NULL,
            position TEXT,
            area TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'REQUIERE_REVISION',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_by INTEGER,
            FOREIGN KEY (organization_id) REFERENCES organizations(id),
            FOREIGN KEY (campus_id) REFERENCES campuses(id),
            FOREIGN KEY (created_by) REFERENCES users(id),
            FOREIGN KEY (updated_by) REFERENCES users(id)
        )
        """
    )

    if has_org_id:
        connection.execute(
            """
            INSERT INTO contacts_crud1_new (
                id, organization_id, campus_id, full_name, position, area,
                notes, status, created_at, updated_at, created_by, updated_by
            )
            SELECT
                co.id,
                COALESCE(co.organization_id, c.organization_id),
                co.campus_id,
                co.full_name,
                co.position,
                co.area,
                co.notes,
                co.status,
                co.created_at,
                co.updated_at,
                co.created_by,
                co.updated_by
            FROM contacts co
            LEFT JOIN campuses c ON c.id = co.campus_id
            ORDER BY co.id
            """
        )
    else:
        connection.execute(
            """
            INSERT INTO contacts_crud1_new (
                id, organization_id, campus_id, full_name, position, area,
                notes, status, created_at, updated_at, created_by, updated_by
            )
            SELECT
                co.id,
                c.organization_id,
                co.campus_id,
                co.full_name,
                co.position,
                co.area,
                co.notes,
                co.status,
                co.created_at,
                co.updated_at,
                co.created_by,
                co.updated_by
            FROM contacts co
            JOIN campuses c ON c.id = co.campus_id
            ORDER BY co.id
            """
        )

    total_staged = connection.execute(
        "SELECT COUNT(*) FROM contacts_crud1_new"
    ).fetchone()[0]
    if total_staged != total_before:
        raise RuntimeError(
            f"La copia no conserva contactos: antes={total_before}, copia={total_staged}."
        )

    missing_org = connection.execute(
        "SELECT COUNT(*) FROM contacts_crud1_new WHERE organization_id IS NULL"
    ).fetchone()[0]
    if missing_org:
        raise RuntimeError(
            "La tabla nueva contiene contactos sin organization_id."
        )

    # NO renombrar contacts a un nombre temporal: SQLite podría reescribir
    # las FK de campaign_recipients. Con foreign_keys=OFF reemplazamos la tabla
    # y conservamos el nombre final 'contacts' y todos los IDs históricos.
    connection.execute("DROP TABLE contacts")
    connection.execute("ALTER TABLE contacts_crud1_new RENAME TO contacts")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_organization ON contacts(organization_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_campus ON contacts(campus_id)"
    )

    total_after = connection.execute(
        "SELECT COUNT(*) FROM contacts"
    ).fetchone()[0]
    return total_before, total_after


def record_migration(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)",
        (MIGRATION_ID,),
    )


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: no existe la base de datos: {DB_PATH}")
        return 1

    print("Eduvision Prospectos — CRUD Bloque 1")
    print(f"Base: {DB_PATH}")
    print("IMPORTANTE: Streamlit debe estar detenido durante la migración.")

    backup_path = create_consistent_backup(DB_PATH)
    print(f"Backup consistente creado: {backup_path}")

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row

    try:
        # Debe configurarse antes de BEGIN.
        connection.execute("PRAGMA foreign_keys = OFF")
        validate_preconditions(connection)

        connection.execute("BEGIN IMMEDIATE")
        ensure_organization_type(connection)

        if contacts_already_migrated(connection):
            validate_contact_ownership(connection)
            total_before = connection.execute(
                "SELECT COUNT(*) FROM contacts"
            ).fetchone()[0]
            total_after = total_before
            print("La tabla contacts ya está en el modelo CRUD Bloque 1.")
        else:
            total_before, total_after = migrate_contacts(connection)

        record_migration(connection)

        # foreign_key_check funciona aunque la aplicación de FK esté desactivada.
        fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            sample = [tuple(row) for row in fk_errors[:5]]
            raise RuntimeError(
                f"PRAGMA foreign_key_check detectó {len(fk_errors)} error(es). "
                f"Muestra: {sample}"
            )

        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(
                f"PRAGMA integrity_check falló después de migrar: {integrity}"
            )

        validate_contact_ownership(connection)
        connection.execute("COMMIT")
        connection.execute("PRAGMA foreign_keys = ON")

        print(f"Contactos antes:   {total_before}")
        print(f"Contactos después: {total_after}")
        print("Migración completada correctamente.")
        print("Marketing no fue modificado.")
        return 0

    except Exception as exc:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

        print(f"ERROR: {exc}")
        print(f"Backup disponible en: {backup_path}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
