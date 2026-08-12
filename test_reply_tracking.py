import argparse
import email
import imaplib
import json
import ssl
import tomllib

from email.header import decode_header
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

TEST_DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "reply_tracking_test.json"
)


SUBJECT = (
    "Prueba técnica de respuesta - Eduvision"
)

BODY = """Hola:

Este mensaje es una prueba técnica para validar la detección
de respuestas mediante Message-ID, In-Reply-To y References.

Por favor utiliza la función Responder de tu cliente de correo.

Este mensaje no pertenece a ninguna campaña comercial.

Saludos cordiales,"""


def decode_header_value(
    value,
) -> str:

    if not value:
        return ""

    result = []

    for part, charset in decode_header(
        value
    ):

        if isinstance(
            part,
            bytes,
        ):

            result.append(
                part.decode(
                    charset or "utf-8",
                    errors="replace",
                )
            )

        else:
            result.append(
                part
            )

    return "".join(
        result
    )


def load_configuration():

    with open(
        SECRETS_PATH,
        "rb",
    ) as file:

        secrets = tomllib.load(
            file
        )

    smtp = secrets["smtp"]
    imap = secrets["imap"]

    smtp_config = {
        "host": smtp["host"],
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
        "user": smtp["user"],
        "password": smtp["password"],
    }

    imap_config = {
        "host": imap["host"],
        "port": int(
            imap.get(
                "port",
                993,
            )
        ),
        "user": imap["user"],
        "password": imap["password"],
        "sent_folder": imap.get(
            "sent_folder",
            "INBOX.Sent",
        ),
    }

    return (
        smtp_config,
        imap_config,
    )


def send_test(
    recipient: str,
) -> None:

    smtp_config, imap_config = (
        load_configuration()
    )

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
        prepared_message[
            "Message-ID"
        ]
    )

    print()
    print("=" * 72)
    print("PRUEBA DE RESPUESTA - ENVÍO")
    print("=" * 72)

    print(
        f"Destinatario: {recipient}"
    )

    print(
        f"Message-ID:   {message_id}"
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

    print()
    print(
        f"SMTP: {result['success']}"
    )

    print(
        result["message"]
    )

    print(
        "Copia en enviados: "
        f"{result.get('sent_folder_saved', False)}"
    )

    if not result["success"]:
        return

    TEST_DATA_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = {
        "recipient": recipient,
        "message_id": message_id,
        "subject": SUBJECT,
    }

    with open(
        TEST_DATA_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "Message-ID guardado para la prueba."
    )

    print()
    print(
        "Ahora abre el correo recibido y pulsa RESPONDER."
    )

    print(
        "Después ejecuta:"
    )

    print()
    print(
        "python test_reply_tracking.py --check"
    )


def check_reply() -> None:

    if not TEST_DATA_PATH.exists():

        print(
            "No existe una prueba de envío registrada."
        )
        return

    with open(
        TEST_DATA_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        test_data = json.load(
            file
        )

    original_message_id = (
        test_data["message_id"]
    )

    _, imap_config = (
        load_configuration()
    )

    context = (
        ssl.create_default_context()
    )

    connection = None

    try:

        connection = (
            imaplib.IMAP4_SSL(
                host=(
                    imap_config[
                        "host"
                    ]
                ),
                port=(
                    imap_config[
                        "port"
                    ]
                ),
                ssl_context=context,
                timeout=30,
            )
        )

        connection.login(
            imap_config["user"],
            imap_config["password"],
        )

        status, _ = (
            connection.select(
                "INBOX",
                readonly=True,
            )
        )

        if status != "OK":
            print(
                "No fue posible abrir INBOX."
            )
            return

        status, data = (
            connection.uid(
                "search",
                None,
                "ALL",
            )
        )

        if status != "OK":
            print(
                "No fue posible consultar INBOX."
            )
            return

        uids = (
            data[0].split()
            if data and data[0]
            else []
        )

        print()
        print("=" * 72)
        print(
            "PRUEBA DE RESPUESTA - REVISIÓN"
        )
        print("=" * 72)

        print()
        print(
            "Buscando respuesta a:"
        )

        print(
            original_message_id
        )

        found = False

        for raw_uid in reversed(
            uids[-100:]
        ):

            status, message_data = (
                connection.uid(
                    "fetch",
                    raw_uid,
                    "(RFC822)",
                )
            )

            if status != "OK":
                continue

            raw_message = None

            for item in message_data:

                if (
                    isinstance(
                        item,
                        tuple,
                    )
                    and len(item) >= 2
                ):
                    raw_message = (
                        item[1]
                    )
                    break

            if not raw_message:
                continue

            message = (
                email.message_from_bytes(
                    raw_message
                )
            )

            in_reply_to = (
                message.get(
                    "In-Reply-To",
                    "",
                )
            )

            references = (
                message.get(
                    "References",
                    "",
                )
            )

            if (
                original_message_id
                not in in_reply_to
                and original_message_id
                not in references
            ):
                continue

            found = True

            uid = raw_uid.decode(
                "ascii",
                errors="replace",
            )

            subject = (
                decode_header_value(
                    message.get(
                        "Subject"
                    )
                )
            )

            from_header = (
                decode_header_value(
                    message.get(
                        "From"
                    )
                )
            )

            print()
            print(
                "RESPUESTA ENCONTRADA"
            )

            print(
                f"UID:          {uid}"
            )

            print(
                f"De:           {from_header}"
            )

            print(
                f"Asunto:       {subject}"
            )

            print(
                f"In-Reply-To:  {in_reply_to}"
            )

            print(
                f"References:   {references}"
            )

            print()
            print(
                "RESULTADO: VINCULACIÓN CORRECTA."
            )

            break

        if not found:

            print()
            print(
                "No se encontró todavía una respuesta "
                "vinculada al Message-ID."
            )

    finally:

        if connection is not None:

            try:
                connection.logout()
            except Exception:
                pass


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--send",
        metavar="EMAIL",
        help=(
            "Envía la prueba al correo indicado."
        ),
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Busca una respuesta a la última prueba."
        ),
    )

    args = parser.parse_args()

    if args.send:

        send_test(
            args.send.strip()
        )

    elif args.check:

        check_reply()

    else:

        print()
        print(
            "Para enviar:"
        )

        print(
            "python test_reply_tracking.py "
            "--send correo@dominio.com"
        )

        print()
        print(
            "Para revisar la respuesta:"
        )

        print(
            "python test_reply_tracking.py --check"
        )


if __name__ == "__main__":
    main()