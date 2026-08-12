import os

from services.smtp_service import (
    SIGNATURE_IMAGE_PATH,
    send_html_test_email,
)


def main():

    print()
    print("=" * 60)
    print("PRUEBA CORREO HTML - EDUVISION")
    print("=" * 60)
    print()

    print(
        f"Cintilla: {SIGNATURE_IMAGE_PATH}"
    )

    if not SIGNATURE_IMAGE_PATH.exists():

        print()
        print("ERROR:")
        print(
            "No se encontró la imagen de la cintilla."
        )

        return

    password = os.environ.get(
        "SMTP_TEST_PASSWORD",
        "",
    )

    if not password:

        print()
        print(
            "ERROR: No existe SMTP_TEST_PASSWORD."
        )

        return

    recipient = input(
        "Correo destinatario de prueba: "
    ).strip()

    print()
    print(
        "Se enviará UN correo HTML de prueba."
    )

    print(
        f"Destinatario: {recipient}"
    )

    print(
        "La cintilla de Patricia Aguirre "
        "se insertará dentro del correo."
    )

    print()

    confirmation = input(
        'Escribe "ENVIAR" para confirmar: '
    ).strip()

    if confirmation != "ENVIAR":

        print()
        print("Envío cancelado.")
        return

    print()
    print("Enviando...")

    result = send_html_test_email(
        password=password,
        recipient=recipient,
    )

    print()
    print(result["message"])
    print()


if __name__ == "__main__":
    main()