from database.connection import get_connection
from services.auth_service import hash_password


DEFAULT_USERNAME = "superadmin"
DEFAULT_PASSWORD = "Cambiar123!"
DEFAULT_FULL_NAME = "Superadministrador"


def create_initial_superadmin() -> bool:
    """
    Create the initial superadmin if no users exist.

    Returns:
        True if a user was created.
        False if users already exist.
    """

    with get_connection() as connection:
        user_count = connection.execute(
            "SELECT COUNT(*) AS total FROM users"
        ).fetchone()["total"]

        if user_count > 0:
            return False

        password_hash, password_salt = hash_password(
            DEFAULT_PASSWORD
        )

        connection.execute(
            """
            INSERT INTO users (
                username,
                full_name,
                password_hash,
                password_salt,
                role,
                active
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                DEFAULT_USERNAME,
                DEFAULT_FULL_NAME,
                password_hash,
                password_salt,
                "SUPERADMIN",
            ),
        )

        connection.commit()

        return True