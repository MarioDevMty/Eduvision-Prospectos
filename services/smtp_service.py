import html
import mimetypes
import smtplib
import ssl

from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from services.imap_service import save_message_to_sent


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

DEFAULT_SMTP_HOST = "mail.grupoasercom.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_USER = "soluciones@grupoasercom.com"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SIGNATURE_IMAGE_PATH = (
    PROJECT_ROOT
    / "assets"
    / "email"
    / "firma_patricia_aguirre.jpeg"
)


# =========================================================
# UTILIDADES HTML
# =========================================================

def plain_text_to_html(
    body_text: str,
) -> str:
    """
    Convierte texto simple en HTML conservando párrafos
    y saltos de línea.
    """

    body_text = (
        body_text or ""
    ).strip()

    escaped = html.escape(
        body_text
    )

    paragraphs = []

    for block in escaped.split("\n\n"):

        block = block.strip()

        if not block:
            continue

        block = block.replace(
            "\n",
            "<br>",
        )

        paragraphs.append(
            f"""
            <p style="
                margin:0 0 16px 0;
                line-height:1.6;
            ">
                {block}
            </p>
            """
        )

    return "\n".join(
        paragraphs
    )


# =========================================================
# CONSTRUIR MENSAJE
# =========================================================

def build_campaign_message(
    recipient: str,
    subject: str,
    body_text: str,
    sender_email: str,
    attachment_paths=None,
) -> EmailMessage:
    """
    Construye un correo de campaña.

    Incluye:
    - versión texto simple
    - versión HTML
    - cintilla Patricia Aguirre
    - PDF u otros adjuntos opcionales
    """

    recipient = (
        recipient or ""
    ).strip()

    subject = (
        subject or ""
    ).strip()

    body_text = (
        body_text or ""
    ).strip()

    sender_email = (
        sender_email or ""
    ).strip()

    attachment_paths = (
        attachment_paths or []
    )

    if not recipient:
        raise ValueError(
            "El destinatario está vacío."
        )

    if not subject:
        raise ValueError(
            "El asunto está vacío."
        )

    if not body_text:
        raise ValueError(
            "El cuerpo del correo está vacío."
        )

    if not sender_email:
        raise ValueError(
            "El remitente está vacío."
        )

    if not SIGNATURE_IMAGE_PATH.exists():
        raise FileNotFoundError(
            "No se encontró la cintilla en: "
            f"{SIGNATURE_IMAGE_PATH}"
        )

    message = EmailMessage()

    message["From"] = sender_email
    message["To"] = recipient
    message["Reply-To"] = sender_email
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    sender_domain = sender_email.split("@", 1)[1] if "@" in sender_email else None
    message["Message-ID"] = make_msgid(domain=sender_domain)

    # =====================================================
    # TEXTO SIMPLE
    # =====================================================

    plain_signature = """

Patricia Aguirre
Soluciones Educativas
Grupo Asercom
81.1077.6606
soluciones@grupoasercom.com
81.1442.4000
grupoasercom.com
""".strip()

    plain_content = (
        f"{body_text}\n\n"
        f"{plain_signature}"
    )

    message.set_content(
        plain_content
    )

    # =====================================================
    # HTML
    # =====================================================

    body_html = plain_text_to_html(
        body_text
    )

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>

<body style="
    margin:0;
    padding:0;
    background-color:#ffffff;
    font-family:Arial, Helvetica, sans-serif;
    color:#222222;
">

    <div style="
        max-width:700px;
        margin:0;
        padding:20px;
        font-size:15px;
        line-height:1.6;
    ">

        {body_html}

        <div style="
            margin-top:22px;
            padding-top:5px;
        ">

            <img
                src="cid:firma_patricia"
                alt="Patricia Aguirre - Grupo Asercom"
                style="
                    display:block;
                    width:75%;
                    max-width:488px;
                    height:auto;
                    border:0;
                "
            >

        </div>

    </div>

</body>
</html>
""".strip()

    message.add_alternative(
        html_content,
        subtype="html",
    )

    # =====================================================
    # CINTILLA CID
    # =====================================================

    html_part = message.get_payload()[-1]

    with open(
        SIGNATURE_IMAGE_PATH,
        "rb",
    ) as image_file:

        image_data = image_file.read()

    html_part.add_related(
        image_data,
        maintype="image",
        subtype="jpeg",
        cid="<firma_patricia>",
        filename="firma_patricia_aguirre.jpeg",
    )

    # =====================================================
    # ADJUNTOS OPCIONALES
    # =====================================================

    for attachment_path in attachment_paths:

        path = Path(
            attachment_path
        )

        if not path.exists():
            raise FileNotFoundError(
                f"No existe el archivo adjunto: {path}"
            )

        mime_type, _ = mimetypes.guess_type(
            path.name
        )

        if mime_type:
            maintype, subtype = mime_type.split(
                "/",
                1,
            )
        else:
            maintype = "application"
            subtype = "octet-stream"

        with open(
            path,
            "rb",
        ) as attachment_file:

            message.add_attachment(
                attachment_file.read(),
                maintype=maintype,
                subtype=subtype,
                filename=path.name,
            )

    return message


# =========================================================
# ENVÍO
# =========================================================

def send_campaign_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    recipient: str,
    subject: str,
    body_text: str,
    attachment_paths=None,
    smtp_security: str = "starttls",
    imap_config: dict | None = None,
    prepared_message: EmailMessage | None = None,
) -> dict:
    """
    success=True significa que el servidor SMTP de salida
    aceptó el mensaje. No confirma entrega final.
    """

    if not smtp_password:
        return {
            "success": False,
            "message": "No existe contraseña SMTP.",
            "message_id": "",
            "sent_folder_saved": False,
            "sent_folder_name": "",
            "sent_folder_message": "",
        }

    message = prepared_message

    try:
        message = message or build_campaign_message(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            sender_email=smtp_user,
            attachment_paths=attachment_paths,
        )

        message_id = str(message.get("Message-ID", ""))
        context = ssl.create_default_context()
        security = (smtp_security or "starttls").strip().lower()

        if security == "ssl" or int(smtp_port) == 465:
            with smtplib.SMTP_SSL(
                smtp_host,
                int(smtp_port),
                timeout=30,
                context=context,
            ) as server:
                server.login(smtp_user, smtp_password)
                refused = server.send_message(message)
        else:
            with smtplib.SMTP(
                smtp_host,
                int(smtp_port),
                timeout=30,
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_user, smtp_password)
                refused = server.send_message(message)

        if refused:
            return {
                "success": False,
                "message": f"SMTP rechazó destinatarios: {refused}",
                "message_id": message_id,
                "sent_folder_saved": False,
                "sent_folder_name": "",
                "sent_folder_message": "",
            }

        sent_saved = False
        sent_name = ""
        sent_message = "No se configuró guardado IMAP."

        if imap_config:
            imap_result = save_message_to_sent(
                host=imap_config["host"],
                port=int(imap_config.get("port", 993)),
                user=imap_config["user"],
                password=imap_config["password"],
                sent_folder=imap_config.get(
                    "sent_folder",
                    "INBOX.Sent",
                ),
                message=message,
            )
            sent_saved = bool(imap_result["success"])
            sent_name = imap_result.get("folder", "")
            sent_message = imap_result["message"]

        return {
            "success": True,
            "message": (
                "Mensaje aceptado por el servidor SMTP "
                f"para {recipient}."
            ),
            "message_id": message_id,
            "sent_folder_saved": sent_saved,
            "sent_folder_name": sent_name,
            "sent_folder_message": sent_message,
        }

    except smtplib.SMTPAuthenticationError:
        error = "El servidor rechazó las credenciales SMTP."
    except smtplib.SMTPRecipientsRefused as exc:
        error = f"Destinatario rechazado: {exc}"
    except smtplib.SMTPSenderRefused as exc:
        error = f"Remitente rechazado: {exc}"
    except smtplib.SMTPException as exc:
        error = f"Error SMTP: {exc}"
    except Exception as exc:
        error = f"Error durante el envío: {exc}"

    return {
        "success": False,
        "message": error,
        "message_id": str(message.get("Message-ID", "")) if message else "",
        "sent_folder_saved": False,
        "sent_folder_name": "",
        "sent_folder_message": "",
    }
