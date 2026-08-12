from database.connection import get_connection


def main() -> None:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                esa.id,
                esa.attempt_number,
                esa.message_id,
                esa.recipient_email,
                esa.smtp_status,
                esa.sent_folder_saved,
                esa.sent_folder_name,
                esa.smtp_response,
                esa.created_at
            FROM email_send_attempts esa
            ORDER BY esa.id DESC
            LIMIT 10
            """
        ).fetchall()

    if not rows:
        print("Todavía no existen intentos de envío.")
        return

    print()
    print("=" * 90)
    print("ÚLTIMOS INTENTOS DE ENVÍO")
    print("=" * 90)

    for row in rows:
        print()
        print(f"ID:                 {row['id']}")
        print(f"Intento:            {row['attempt_number']}")
        print(f"Destinatario:       {row['recipient_email']}")
        print(f"Message-ID:         {row['message_id']}")
        print(f"Estado SMTP:        {row['smtp_status']}")
        print(f"Copia en enviados:  {row['sent_folder_saved']}")
        print(f"Carpeta:            {row['sent_folder_name']}")
        print(f"Respuesta SMTP:     {row['smtp_response']}")
        print(f"Fecha:              {row['created_at']}")


if __name__ == "__main__":
    main()