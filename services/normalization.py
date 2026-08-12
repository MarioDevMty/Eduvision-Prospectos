import re
import unicodedata


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = value.strip().lower()

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(r"\D", "", value)


def normalize_email(value: str | None) -> str:
    if not value:
        return ""

    return value.strip().lower()