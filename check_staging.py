from database.connection import get_connection

c = get_connection()

row = c.execute(
    """
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    AND name = 'import_staging'
    """
).fetchone()

print(row)

c.close()