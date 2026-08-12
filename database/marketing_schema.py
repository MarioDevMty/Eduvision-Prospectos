from database.connection import get_connection


MARKETING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,

    campaign_type TEXT NOT NULL DEFAULT 'CONTACTO_FRIO'
        CHECK (
            campaign_type IN (
                'CONTACTO_FRIO',
                'SEGUIMIENTO',
                'INFORMATIVA'
            )
        ),

    objective TEXT,
    subject TEXT,
    body_text TEXT,

    status TEXT NOT NULL DEFAULT 'BORRADOR'
        CHECK (
            status IN (
                'BORRADOR',
                'ACTIVA',
                'FINALIZADA',
                'CANCELADA'
            )
        ),

    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (created_by)
        REFERENCES users(id)
);


CREATE TABLE IF NOT EXISTS campaign_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    campaign_id INTEGER NOT NULL,
    campus_id INTEGER NOT NULL,
    contact_id INTEGER,

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

    FOREIGN KEY (campus_id)
        REFERENCES campuses(id),

    FOREIGN KEY (contact_id)
        REFERENCES contacts(id),

    UNIQUE (
        campaign_id,
        email_address
    )
);


CREATE TABLE IF NOT EXISTS email_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    campaign_recipient_id INTEGER NOT NULL,

    event_type TEXT NOT NULL
        CHECK (
            event_type IN (
                'AGREGADO',
                'PREPARADO',
                'ENVIADO',
                'RESPONDIO',
                'CONTACTO_REFERIDO',
                'SIN_RESPUESTA',
                'REBOTE',
                'NO_INTERESADO',
                'ERROR',
                'NOTA'
            )
        ),

    details TEXT,

    created_by INTEGER,
    event_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_recipient_id)
        REFERENCES campaign_recipients(id),

    FOREIGN KEY (created_by)
        REFERENCES users(id)
);


-- ========================================================
-- INTENTOS DE ENVÍO
-- ========================================================

CREATE TABLE IF NOT EXISTS email_send_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    campaign_recipient_id INTEGER NOT NULL,

    attempt_number INTEGER NOT NULL DEFAULT 1,

    message_id TEXT NOT NULL,
    envelope_from TEXT NOT NULL,
    recipient_email TEXT NOT NULL,

    smtp_status TEXT NOT NULL DEFAULT 'PREPARADO'
        CHECK (
            smtp_status IN (
                'PREPARADO',
                'ACEPTADO',
                'ERROR'
            )
        ),

    smtp_response TEXT,

    sent_folder_saved INTEGER NOT NULL DEFAULT 0
        CHECK (
            sent_folder_saved IN (0, 1)
        ),

    sent_folder_name TEXT,

    bounce_detected INTEGER NOT NULL DEFAULT 0
        CHECK (
            bounce_detected IN (0, 1)
        ),

    bounce_code TEXT,
    bounce_reason TEXT,
    bounce_message_uid TEXT,
    bounced_at TEXT,

    response_detected INTEGER NOT NULL DEFAULT 0
        CHECK (
            response_detected IN (0, 1)
        ),

    response_message_uid TEXT,
    responded_at TEXT,

    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_recipient_id)
        REFERENCES campaign_recipients(id),

    FOREIGN KEY (created_by)
        REFERENCES users(id),

    UNIQUE (message_id)
);


CREATE INDEX IF NOT EXISTS idx_campaigns_status
ON campaigns(status);


CREATE INDEX IF NOT EXISTS idx_campaign_recipients_campaign
ON campaign_recipients(campaign_id);


CREATE INDEX IF NOT EXISTS idx_campaign_recipients_campus
ON campaign_recipients(campus_id);


CREATE INDEX IF NOT EXISTS idx_campaign_recipients_status
ON campaign_recipients(status);


CREATE INDEX IF NOT EXISTS idx_campaign_recipients_email
ON campaign_recipients(email_address);


CREATE INDEX IF NOT EXISTS idx_email_activity_recipient
ON email_activity(campaign_recipient_id);


CREATE INDEX IF NOT EXISTS idx_send_attempts_recipient
ON email_send_attempts(campaign_recipient_id);


CREATE INDEX IF NOT EXISTS idx_send_attempts_message_id
ON email_send_attempts(message_id);


CREATE INDEX IF NOT EXISTS idx_send_attempts_recipient_email
ON email_send_attempts(recipient_email);


CREATE INDEX IF NOT EXISTS idx_send_attempts_bounce
ON email_send_attempts(bounce_detected);


CREATE INDEX IF NOT EXISTS idx_send_attempts_response
ON email_send_attempts(response_detected);
"""


def create_marketing_schema() -> None:
    """
    Crea las tablas necesarias para campañas,
    destinatarios, actividad e intentos de envío.
    """

    with get_connection() as connection:
        connection.executescript(
            MARKETING_SCHEMA_SQL
        )
        connection.commit()


if __name__ == "__main__":
    create_marketing_schema()
    print("MARKETING SCHEMA OK")