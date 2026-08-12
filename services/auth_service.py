import hashlib
import hmac
import os

from database.connection import get_connection


PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """
    Generate a PBKDF2-HMAC hash for a password.

    Returns:
        tuple:
            password_hash_hex,
            salt_hex
    """

    if not password:
        raise ValueError("La contraseña no puede estar vacía.")

    if salt is None:
        salt = os.urandom(32)

    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    return derived_key.hex(), salt.hex()


def verify_password(
    password: str,
    stored_hash: str,
    stored_salt: str,
) -> bool:
    """Verify a password against the stored hash."""

    salt = bytes.fromhex(stored_salt)

    calculated_hash, _ = hash_password(
        password=password,
        salt=salt,
    )

    return hmac.compare_digest(
        calculated_hash,
        stored_hash,
    )


def authenticate_user(
    username: str,
    password: str,
) -> dict | None:
    """
    Authenticate an active user.

    Returns a dictionary containing basic user information
    when credentials are valid.
    """

    username = username.strip().lower()

    if not username or not password:
        return None

    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT
                id,
                username,
                full_name,
                password_hash,
                password_salt,
                role,
                active
            FROM users
            WHERE LOWER(username) = ?
            LIMIT 1
            """,
            (username,),
        ).fetchone()

        if user is None:
            return None

        if not user["active"]:
            return None

        if not verify_password(
            password=password,
            stored_hash=user["password_hash"],
            stored_salt=user["password_salt"],
        ):
            return None

        connection.execute(
            """
            UPDATE users
            SET last_login = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user["id"],),
        )

        connection.commit()

        return {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
        }