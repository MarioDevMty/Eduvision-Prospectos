from database.connection import get_connection


# Correo que falló en la campaña.
OLD_EMAIL = "cetis163.dir@dgti.sems.gob.mx"

# Sustituye este valor por el correo correcto confirmado.
NEW_EMAIL = "cetis163.dir@dgeti.sems.gob.mx"


def main() -> None:

    old_email = OLD_EMAIL.strip().lower()
    new_email = NEW_EMAIL.strip().lower()

    if not old_email or not new_email:
        print("ERROR: Los correos no pueden estar vacíos.")
        return

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                cr.id,
                cr.campaign_id,
                cr.campus_name_snapshot,
                cr.email_address,
                cr.status,
                c.name AS campaign_name
            FROM campaign_recipients cr
            JOIN campaigns c
              ON c.id = cr.campaign_id
            WHERE LOWER(cr.email_address) = LOWER(?)
              AND cr.status = 'ERROR'
            ORDER BY cr.id DESC
            """,
            (old_email,),
        ).fetchall()

        if not rows:
            print()
            print("No se encontró un destinatario en ERROR")
            print(f"con el correo: {old_email}")
            return

        print()
        print("=" * 65)
        print("CORRECCIÓN DE CORREO DE CAMPAÑA")
        print("=" * 65)

        for row in rows:
            print()
            print(f"ID destinatario : {row['id']}")
            print(f"Campaña         : {row['campaign_name']}")
            print(f"Plantel         : {row['campus_name_snapshot']}")
            print(f"Correo anterior : {row['email_address']}")
            print(f"Correo nuevo    : {new_email}")
            print(f"Estado actual   : {row['status']}")

        print()
        confirmation = input(
            'Escribe "CORREGIR" para actualizar y dejarlo PENDIENTE: '
        ).strip()

        if confirmation != "CORREGIR":
            print()
            print("Operación cancelada.")
            return

        try:
            connection.execute("BEGIN")

            for row in rows:

                connection.execute(
                    """
                    UPDATE campaign_recipients
                    SET
                        email_address = ?,
                        status = 'PENDIENTE',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        new_email,
                        row["id"],
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO email_activity (
                        campaign_recipient_id,
                        event_type,
                        details,
                        created_by
                    )
                    VALUES (?, 'NOTA', ?, NULL)
                    """,
                    (
                        row["id"],
                        (
                            "Correo corregido después de un error de envío. "
                            f"Anterior: {old_email}. "
                            f"Nuevo: {new_email}. "
                            "Destinatario devuelto a PENDIENTE."
                        ),
                    ),
                )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    print()
    print("Correo corregido.")
    print("El destinatario quedó nuevamente en estado PENDIENTE.")
    print()


if __name__ == "__main__":
    main()