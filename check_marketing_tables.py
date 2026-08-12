from database.connection import get_connection


def main():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                  'campaigns',
                  'campaign_recipients',
                  'email_activity'
              )
            ORDER BY name
            """
        ).fetchall()

    print("Tablas encontradas:")
    for row in rows:
        print("-", row[0])


if __name__ == "__main__":
    main()