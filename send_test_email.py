import os

from services.smtp_service import (
    send_test_email,
)


def main():

    password = os.environ.get(
        "SMTP_TEST_PASSWORD",
        "",
    )

    recipient = input(
        "Correo destinatario de prueba: "
    ).strip()

    if not password:

        print()
        print(
            "ERROR: No existe SMTP_TEST_PASSWORD."
        )

        print(
            "Primero define la variable de entorno."
        )

        return

    print()
    print(
        "Se enviará UN correo de prueba."
    )

    print(
        f"Destinatario: {recipient}"
    )

    print()

    confirmation = input(
        'Escribe "ENVIAR" para confirmar: '
    ).strip()

    if confirmation != "ENVIAR":

        print()
        print(
            "Envío cancelado."
        )

        return

    print()
    print(
        "Enviando..."
    )

    result = send_test_email(
        password=password,
        recipient=recipient,
    )

    print()
    print(
        result["message"]
    )


if __name__ == "__main__":
    main()