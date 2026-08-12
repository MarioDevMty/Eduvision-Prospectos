from database.connection import get_connection


SCHEMA_SQL = """

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    role TEXT NOT NULL
        CHECK (role IN ('CURADOR', 'ADMIN', 'SUPERADMIN')),
    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TEXT
);


CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    official_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    organization_type TEXT,
    subsystem TEXT,
    sector TEXT,
    relationship_type TEXT,
    status TEXT NOT NULL DEFAULT 'REQUIERE_REVISION',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    updated_by INTEGER,

    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (updated_by) REFERENCES users(id)
);


CREATE INDEX IF NOT EXISTS idx_organizations_normalized_name
ON organizations(normalized_name);


CREATE TABLE IF NOT EXISTS campuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    parent_campus_id INTEGER,

    campus_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    campus_type TEXT,

    campus_code TEXT,
    address TEXT,
    neighborhood TEXT,
    postal_code TEXT,
    municipality TEXT,
    state TEXT,
    website TEXT,

    status TEXT NOT NULL DEFAULT 'REQUIERE_REVISION',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    updated_by INTEGER,

    FOREIGN KEY (organization_id)
        REFERENCES organizations(id),

    FOREIGN KEY (parent_campus_id)
        REFERENCES campuses(id),

    FOREIGN KEY (created_by)
        REFERENCES users(id),

    FOREIGN KEY (updated_by)
        REFERENCES users(id)
);


CREATE INDEX IF NOT EXISTS idx_campuses_organization
ON campuses(organization_id);

CREATE INDEX IF NOT EXISTS idx_campuses_normalized_name
ON campuses(normalized_name);


CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campus_id INTEGER NOT NULL,

    full_name TEXT NOT NULL,
    position TEXT,
    area TEXT,
    notes TEXT,

    status TEXT NOT NULL DEFAULT 'REQUIERE_REVISION',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    updated_by INTEGER,

    FOREIGN KEY (campus_id)
        REFERENCES campuses(id),

    FOREIGN KEY (created_by)
        REFERENCES users(id),

    FOREIGN KEY (updated_by)
        REFERENCES users(id)
);


CREATE TABLE IF NOT EXISTS phones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('ORGANIZATION', 'CAMPUS', 'CONTACT')),

    entity_id INTEGER NOT NULL,

    phone TEXT NOT NULL,
    normalized_phone TEXT NOT NULL,

    phone_type TEXT,
    extension TEXT,

    is_primary INTEGER NOT NULL DEFAULT 0
        CHECK (is_primary IN (0, 1)),

    status TEXT NOT NULL DEFAULT 'ACTIVO',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,

    FOREIGN KEY (created_by)
        REFERENCES users(id)
);


CREATE INDEX IF NOT EXISTS idx_phones_normalized
ON phones(normalized_phone);


CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('ORGANIZATION', 'CAMPUS', 'CONTACT')),

    entity_id INTEGER NOT NULL,

    email TEXT NOT NULL,
    normalized_email TEXT NOT NULL,

    email_type TEXT,

    is_primary INTEGER NOT NULL DEFAULT 0
        CHECK (is_primary IN (0, 1)),

    status TEXT NOT NULL DEFAULT 'ACTIVO',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,

    FOREIGN KEY (created_by)
        REFERENCES users(id)
);


CREATE INDEX IF NOT EXISTS idx_emails_normalized
ON emails(normalized_email);


CREATE TABLE IF NOT EXISTS organization_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    organization_id INTEGER,
    campus_id INTEGER,

    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,

    source TEXT,

    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1)),

    confirmed_by INTEGER,
    confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (organization_id)
        REFERENCES organizations(id),

    FOREIGN KEY (campus_id)
        REFERENCES campuses(id),

    FOREIGN KEY (confirmed_by)
        REFERENCES users(id)
);


CREATE INDEX IF NOT EXISTS idx_aliases_normalized
ON organization_aliases(normalized_alias);


CREATE TABLE IF NOT EXISTS dynamic_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL UNIQUE,

    data_type TEXT NOT NULL DEFAULT 'TEXT',
    category TEXT,

    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,

    FOREIGN KEY (created_by)
        REFERENCES users(id)
);


CREATE TABLE IF NOT EXISTS dynamic_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    field_id INTEGER NOT NULL,

    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('ORGANIZATION', 'CAMPUS', 'CONTACT')),

    entity_id INTEGER NOT NULL,

    value TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_by INTEGER,
    updated_by INTEGER,

    FOREIGN KEY (field_id)
        REFERENCES dynamic_fields(id),

    FOREIGN KEY (created_by)
        REFERENCES users(id),

    FOREIGN KEY (updated_by)
        REFERENCES users(id)
);


CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER,

    entity_type TEXT,
    entity_id INTEGER,

    action TEXT NOT NULL,

    field_name TEXT,
    old_value TEXT,
    new_value TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
);


CREATE TABLE IF NOT EXISTS import_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_filename TEXT,
    source_sheet TEXT,
    source_row INTEGER,

    organization_name TEXT,
    campus_name TEXT,
    contact_name TEXT,

    row_data TEXT NOT NULL,

    reason TEXT,
    review_type TEXT,

    status TEXT NOT NULL DEFAULT 'PENDIENTE'
        CHECK (
            status IN (
                'PENDIENTE',
                'RESUELTO',
                'DESCARTADO'
            )
        ),

    created_by INTEGER,
    resolved_by INTEGER,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,

    FOREIGN KEY (created_by)
        REFERENCES users(id),

    FOREIGN KEY (resolved_by)
        REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS import_staging (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_filename TEXT,
    source_sheet TEXT,
    source_row INTEGER,

    organization_name TEXT,
    campus_name TEXT,
    contact_name TEXT,

    row_data TEXT NOT NULL,

    reason TEXT,
    review_type TEXT,

    status TEXT NOT NULL DEFAULT 'PENDIENTE'
        CHECK (
            status IN (
                'PENDIENTE',
                'RESUELTO',
                'DESCARTADO'
            )
        ),

    created_by INTEGER,
    resolved_by INTEGER,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,

    FOREIGN KEY (created_by)
        REFERENCES users(id),

    FOREIGN KEY (resolved_by)
        REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_import_staging_status
ON import_staging(status);
"""


def create_schema() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()