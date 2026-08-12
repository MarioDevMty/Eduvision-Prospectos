import tomllib
from pathlib import Path

from services.smtp_service import (
    build_campaign_message,
    send_campaign_email,
)


PROJECT_ROOT = Path(__file__).resolve().parent

SECRETS_PATH = (
    PROJECT_ROOT
    / ".streamlit"
    / "secrets.toml"
)


SUBJECT = (
    "Prueba técnica de rastreo de correo - Eduvision"
)

BODY = """Hola:

Este es un correo de prueba técnica para validar:

• aceptación SMTP;
• generación de Message-ID;
• guardado de copia en INBOX.Sent;
• comportamiento ante una dirección válida o inválida.

Este mensaje no forma parte de una campaña comercial.

Saludos cordiales,"""


def load_configuration() -> tuple[dict, dict]:

    if not SECRETS_PATH.exists():
        raise FileNotFoundError(
            "No se encontró .streamlit/secrets.toml"
        )

    with open(
        SECRETS_PATH,
        "rb",
    ) as secrets_file:

        secrets = tomllib.load(
            secrets_file
        )

    smtp = secrets.get(
        "smtp",
        {},
    )

    imap = secrets.get(
        "imap",
        {},
    )

    smtp_config = {
        "host": smtp.get(
            "host",
            "",
        ),
        "port": int(
            smtp.get(
                "port",
                587,
            )
        ),
        "security": smtp.get(
            "security",
            "starttls",
        ),
        "user": smtp.get(
            "user",
            "",
        ),
        "password": smtp.get(
            "password",
            "",
        ),
    }

    imap_config = {
        "host": imap.get(
            "host",
            "",
        ),
        "port": int(
            imap.get(
                "port",
                993,
            )
        ),
        "user": imap.get(
            "user",
            "",
        ),
        "password": imap.get(
            "password",
            "",
        ),
        "sent_folder": imap.get(
            "sent_folder",
            "INBOX.Sent",
        ),
    }

    required_smtp = [
        smtp_config["host"],
        smtp_config["user"],
        smtp_config["password"],
    ]

    required_imap = [
        imap_config["host"],
        imap_config["user"],
        imap_config["password"],
    ]

    if not all(
        required_smtp
    ):
        raise ValueError(
            "La configuración SMTP está incompleta."
        )

    if not all(
        required_imap
    ):
        raise ValueError(
            "La configuración IMAP está incompleta."
        )

    return (
        smtp_config,
        imap_config,
    )


def send_test(
    label: str,
    recipient: str,
    smtp_config: dict,
    imap_config: dict,
) -> None:

    recipient = (
        recipient or ""
    ).strip()

    if not recipient:
        print()
        print(
            f"{label}: no se capturó correo."
        )
        return

    print()
    print("=" * 72)
    print(label)
    print("=" * 72)
    print(
        f"Destinatario: {recipient}"
    )

    try:

        prepared_message = (
            build_campaign_message(
                recipient=recipient,
                subject=SUBJECT,
                body_text=BODY,
                sender_email=(
                    smtp_config["user"]
                ),
                attachment_paths=[],
            )
        )

        message_id = str(
            prepared_message.get(
                "Message-ID",
                "",
            )
        )

        print(
            f"Message-ID preparado: {message_id}"
        )

        result = send_campaign_email(
            smtp_host=(
                smtp_config["host"]
            ),
            smtp_port=(
                smtp_config["port"]
            ),
            smtp_user=(
                smtp_config["user"]
            ),
            smtp_password=(
                smtp_config["password"]
            ),
            smtp_security=(
                smtp_config["security"]
            ),
            recipient=recipient,
            subject=SUBJECT,
            body_text=BODY,
            attachment_paths=[],
            imap_config=imap_config,
            prepared_message=(
                prepared_message
            ),
        )

    except Exception as exc:

        print(
            f"ERROR AL PREPARAR: {exc}"
        )
        return

    print()
    print(
        f"Éxito SMTP: {result['success']}"
    )

    print(
        f"Resultado: {result['message']}"
    )

    print(
        "Message-ID devuelto: "
        f"{result.get('message_id', '')}"
    )

    print(
        "Copia en enviados: "
        f"{result.get('sent_folder_saved', False)}"
    )

    print(
        "Carpeta: "
        f"{result.get('sent_folder_name', '')}"
    )

    print(
        "Resultado IMAP: "
        f"{result.get('sent_folder_message', '')}"
    )

    if result["success"]:

        print()
        print(
            "INTERPRETACIÓN:"
        )

        print(
            "El servidor SMTP aceptó el mensaje."
        )

        print(
            "Esto todavía no confirma que el servidor "
            "final lo haya entregado."
        )

        if result.get(
            "sent_folder_saved",
            False,
        ):
            print(
                "La copia quedó guardada en INBOX.Sent."
            )
        else:
            print(
                "La copia no quedó guardada "
                "en la carpeta de enviados."
            )

    else:

        print()
        print(
            "INTERPRETACIÓN:"
        )

        print(
            "El servidor rechazó el mensaje "
            "durante la sesión SMTP."
        )


def main() -> None:

    print()
    print("=" * 72)
    print(
        "PRUEBA TÉCNICA DE CORREO - EDUVISION"
    )
    print("=" * 72)

    try:
        smtp_config, imap_config = (
            load_configuration()
        )

    except Exception as exc:

        print()
        print(
            f"ERROR DE CONFIGURACIÓN: {exc}"
        )
        return

    print()
    valid_email = input(
        "Correo válido controlado: "
    ).strip()

    invalid_email = input(
        "Correo inválido de prueba: "
    ).strip()

    print()
    confirmation = input(
        'Escribe "ENVIAR PRUEBAS" para continuar: '
    ).strip()

    if confirmation != "ENVIAR PRUEBAS":

        print()
        print(
            "Prueba cancelada."
        )
        return

    send_test(
        label="PRUEBA 1 - CORREO VÁLIDO",
        recipient=valid_email,
        smtp_config=smtp_config,
        imap_config=imap_config,
    )

    send_test(
        label="PRUEBA 2 - CORREO INVÁLIDO",
        recipient=invalid_email,
        smtp_config=smtp_config,
        imap_config=imap_config,
    )

    print()
    print("=" * 72)
    print(
        "PRUEBAS FINALIZADAS"
    )
    print("=" * 72)

    print()
    print(
        "Revisa ahora:"
    )

    print(
        "1. La recepción del correo válido."
    )

    print(
        "2. La carpeta INBOX.Sent."
    )

    print(
        "3. La bandeja de entrada de soluciones@grupoasercom.com."
    )

    print(
        "4. Si llega posteriormente un mensaje de MAILER-DAEMON."
    )


if __name__ == "__main__":
    main()