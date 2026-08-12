import argparse
import tomllib
from pathlib import Path

from services.mailbox_sync import scan_mailbox


PROJECT_ROOT = Path(__file__).resolve().parent
SECRETS_PATH = PROJECT_ROOT / ".streamlit" / "secrets.toml"


def load_imap() -> dict:
    with open(SECRETS_PATH, "rb") as file:
        secrets = tomllib.load(file)

    imap = secrets["imap"]

    return {
        "host": imap["host"],
        "port": int(imap.get("port", 993)),
        "user": imap["user"],
        "password": imap["password"],
    }


def print_results(results: dict) -> None:
    print()
    print("=" * 78)
    print("SINCRONIZACIÓN MANUAL DE BANDEJA - EDUVISION")
    print("=" * 78)

    if results.get("locked"):
        print()
        print(results["message"])
        return

    print()
    print(f"Éxito:                    {results.get('success', False)}")
    print(f"Mensajes nuevos revisados:{results.get('scanned', 0)}")
    print(f"Rebotes aplicados:        {results.get('applied_bounces', 0)}")
    print(f"Respuestas aplicadas:     {results.get('applied_replies', 0)}")
    print(f"Sin coincidencia:         {len(results.get('unmatched', []))}")
    print(f"Errores de lectura:       {len(results.get('errors', []))}")

    if not results.get("success", False):
        print()
        print(f"ERROR: {results.get('message', '')}")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica cambios en SQLite.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=500,
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Revisa todos los mensajes, ignorando el último UID.",
    )

    parser.add_argument(
        "--source",
        default="CLI",
    )

    args = parser.parse_args()
    config = load_imap()

    results = scan_mailbox(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        user_id=args.user_id,
        limit=args.limit,
        apply_changes=args.apply,
        mailbox="INBOX",
        incremental=not args.full,
        source=args.source,
    )

    print_results(results)


if __name__ == "__main__":
    main()
