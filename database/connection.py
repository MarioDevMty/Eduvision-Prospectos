from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "eduvision.db"


def ensure_data_directory() -> None:
    """Create the data directory when it doesn't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """
    Return a configured SQLite connection.

    row_factory allows accessing values as:
        row["username"]
    instead of only:
        row[0]
    """
    ensure_data_directory()

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    # Referential integrity.
    connection.execute("PRAGMA foreign_keys = ON;")

    return connection