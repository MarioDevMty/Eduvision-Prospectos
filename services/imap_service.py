import imaplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.policy import SMTP


def test_imap_connection(host: str, port: int, user: str, password: str) -> dict:
    connection = None
    try:
        connection = imaplib.IMAP4_SSL(
            host=host,
            port=int(port),
            ssl_context=ssl.create_default_context(),
            timeout=30,
        )
        connection.login(user, password)
        status, data = connection.list()
        folders = [
            item.decode("utf-8", errors="replace")
            for item in (data or [])
            if item
        ]
        return {
            "success": status == "OK",
            "message": "Conexión y autenticación IMAP correctas.",
            "folders": folders,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"Error IMAP: {exc}",
            "folders": [],
        }
    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass


def find_sent_folder(folders: list[str]) -> str | None:
    for folder in folders:
        if "\\sent" in folder.lower():
            return folder.split()[-1].strip('"')
    return None


def save_message_to_sent(
    host: str,
    port: int,
    user: str,
    password: str,
    sent_folder: str,
    message: EmailMessage,
) -> dict:
    connection = None
    try:
        connection = imaplib.IMAP4_SSL(
            host=host,
            port=int(port),
            ssl_context=ssl.create_default_context(),
            timeout=30,
        )
        connection.login(user, password)
        status, response = connection.append(
            sent_folder,
            r"(\Seen)",
            imaplib.Time2Internaldate(datetime.now().astimezone()),
            message.as_bytes(policy=SMTP),
        )
        if status != "OK":
            return {
                "success": False,
                "message": f"IMAP no aceptó la copia: {response}",
                "folder": sent_folder,
            }
        return {
            "success": True,
            "message": f"Copia guardada en {sent_folder}.",
            "folder": sent_folder,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"No se pudo guardar la copia IMAP: {exc}",
            "folder": sent_folder,
        }
    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass
