import tomllib
from pathlib import Path

from services.imap_service import (
    find_sent_folder,
    test_imap_connection,
)


PROJECT_ROOT = Path(__file__).resolve().parent

SECRETS_PATH = (
    PROJECT_ROOT
    / ".streamlit"
    / "secrets.toml"
)


def main() -> None:

    print()
    print("=" * 60)
    print("PRUEBA IMAP - EDUVISION")
    print("=" * 60)

    if not SECRETS_PATH.exists():

        print()
        print(
            "ERROR: No se encontró .streamlit/secrets.toml"
        )
        return

    with open(
        SECRETS_PATH,
        "rb",
    ) as secrets_file:

        secrets = tomllib.load(
            secrets_file
        )

    imap_config = secrets.get(
        "imap",
        {},
    )

    result = test_imap_connection(
        host=imap_config.get(
            "host",
            "",
        ),
        port=int(
            imap_config.get(
                "port",
                993,
            )
        ),
        user=imap_config.get(
            "user",
            "",
        ),
        password=imap_config.get(
            "password",
            "",
        ),
    )

    print()
    print(result["message"])

    if not result["success"]:
        return

    print()
    print("Carpetas encontradas:")

    for folder in result["folders"]:
        print(f"- {folder}")

    sent_folder = find_sent_folder(
        result["folders"]
    )

    print()

    if sent_folder:
        print(
            "Carpeta probable de enviados: "
            f"{sent_folder}"
        )
    else:
        print(
            "No fue posible identificar automáticamente "
            "la carpeta de enviados."
        )


if __name__ == "__main__":
    main()