from database.connection import get_connection


def column_exists(
    connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        row["name"] == column_name
        for row in rows
    )


def main() -> None:
    with get_connection() as connection:

        if not column_exists(
            connection,
            "campaign_recipients",
            "is_active",
        ):
            connection.execute(
                """
                ALTER TABLE campaign_recipients
                ADD COLUMN is_active INTEGER
                NOT NULL DEFAULT 1
                CHECK (is_active IN (0, 1))
                """
            )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_campaign_recipients_active
            ON campaign_recipients(
                campaign_id,
                is_active,
                status
            )
            """
        )

        connection.commit()

    print(
        "MIGRATION OK: campaign_recipients.is_active"
    )


if __name__ == "__main__":
    main()
