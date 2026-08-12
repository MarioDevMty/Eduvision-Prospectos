import re


EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


def validate_email_address(
    email_address: str,
) -> tuple[bool, str]:
    value = (
        email_address or ""
    ).strip()

    if not value:
        return False, "El correo está vacío."

    if " " in value:
        return False, "El correo contiene espacios."

    if len(value) > 254:
        return False, "El correo excede la longitud permitida."

    if not EMAIL_PATTERN.fullmatch(value):
        return (
            False,
            "El valor no tiene una estructura válida de correo.",
        )

    return True, ""
