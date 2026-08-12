from database.connection import get_connection


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS mailbox_sync_state (
    mailbox TEXT PRIMARY KEY,
    last_uid_processed INTEGER NOT NULL DEFAULT 0,
    is_running INTEGER NOT NULL DEFAULT 0
        CHECK (is_running IN (0, 1)),
    lock_started_at TEXT,
    last_sync_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    last_scanned INTEGER NOT NULL DEFAULT 0,
    last_bounces INTEGER NOT NULL DEFAULT 0,
    last_replies INTEGER NOT NULL DEFAULT 0,
    last_unmatched INTEGER NOT NULL DEFAULT 0,
    last_errors INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mailbox_processed_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mailbox TEXT NOT NULL,
    message_uid TEXT NOT NULL,
    message_id TEXT,
    message_type TEXT NOT NULL,
    matched_recipient_id INTEGER,
    processing_result TEXT,
    subject TEXT,
    sender_email TEXT,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matched_recipient_id)
        REFERENCES campaign_recipients(id),
    UNIQUE (mailbox, message_uid)
);

CREATE TABLE IF NOT EXISTS mailbox_sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mailbox TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCESS', 'ERROR')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    scanned INTEGER NOT NULL DEFAULT 0,
    bounces INTEGER NOT NULL DEFAULT 0,
    replies INTEGER NOT NULL DEFAULT 0,
    unmatched INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_mailbox_processed_uid
ON mailbox_processed_messages(mailbox, message_uid);

CREATE INDEX IF NOT EXISTS idx_mailbox_processed_recipient
ON mailbox_processed_messages(matched_recipient_id);

CREATE INDEX IF NOT EXISTS idx_mailbox_runs_started
ON mailbox_sync_runs(started_at DESC);

INSERT OR IGNORE INTO mailbox_sync_state (
    mailbox,
    last_uid_processed,
    is_running
)
VALUES ('INBOX', 0, 0);
"""


def main() -> None:
    with get_connection() as connection:
        connection.executescript(MIGRATION_SQL)
        connection.commit()

    print("MIGRATION OK: mailbox automatic sync")


if __name__ == "__main__":
    main()
