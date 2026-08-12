from rapidfuzz import fuzz

from services.normalization import (
    normalize_email,
    normalize_phone,
    normalize_text,
)


def text_similarity(
    value_a: str | None,
    value_b: str | None,
) -> float:
    """
    Calcula similitud de texto entre 0 y 100.
    """

    a = normalize_text(value_a)
    b = normalize_text(value_b)

    if not a or not b:
        return 0.0

    return float(
        fuzz.token_set_ratio(a, b)
    )


# =========================================================
# COINCIDENCIAS DE PLANTELES
# =========================================================

def campus_match_score(
    new_name: str,
    new_municipality: str | None,
    new_phone: str | None,
    existing_name: str,
    existing_municipality: str | None,
    existing_phones: list[str] | None = None,
) -> dict:

    name_score = text_similarity(
        new_name,
        existing_name,
    )

    normalized_new_name = normalize_text(
        new_name
    )

    normalized_existing_name = normalize_text(
        existing_name
    )

    exact_name = (
        normalized_new_name
        ==
        normalized_existing_name
    )

    municipality_match = False

    new_municipality_normalized = normalize_text(
        new_municipality
    )

    existing_municipality_normalized = normalize_text(
        existing_municipality
    )

    if (
        new_municipality_normalized
        and existing_municipality_normalized
    ):
        municipality_match = (
            new_municipality_normalized
            ==
            existing_municipality_normalized
        )

    phone_match = False

    normalized_new_phone = normalize_phone(
        new_phone
    )

    if normalized_new_phone:

        for phone in existing_phones or []:

            if (
                normalize_phone(phone)
                ==
                normalized_new_phone
            ):
                phone_match = True
                break

    # Clasificación.
    if exact_name and (
        municipality_match
        or phone_match
    ):
        level = "EXACTA"

    elif phone_match and name_score >= 60:
        level = "MUY_ALTA"

    elif municipality_match and name_score >= 85:
        level = "ALTA"

    elif exact_name:
        level = "ALTA"

    elif name_score >= 90:
        level = "ALTA"

    elif name_score >= 75:
        level = "POSIBLE"

    else:
        level = "BAJA"

    return {
        "name_score": round(
            name_score,
            1,
        ),
        "municipality_match": municipality_match,
        "phone_match": phone_match,
        "exact_name": exact_name,
        "level": level,
    }


# =========================================================
# COINCIDENCIAS DE CONTACTOS
# =========================================================

def contact_match_score(
    new_name: str,
    new_phone: str | None,
    new_email: str | None,
    existing_name: str,
    existing_phones: list[str] | None = None,
    existing_emails: list[str] | None = None,
) -> dict:
    """
    Evalúa si dos contactos podrían representar
    a la misma persona.

    IMPORTANTE:
    Incluso una coincidencia EXACTA requiere
    decisión humana antes de fusionarse.
    """

    name_score = text_similarity(
        new_name,
        existing_name,
    )

    exact_name = (
        normalize_text(new_name)
        ==
        normalize_text(existing_name)
    )

    # -----------------------------------------------------
    # TELÉFONO
    # -----------------------------------------------------

    phone_match = False

    normalized_new_phone = normalize_phone(
        new_phone
    )

    if normalized_new_phone:

        for phone in existing_phones or []:

            if (
                normalize_phone(phone)
                ==
                normalized_new_phone
            ):
                phone_match = True
                break

    # -----------------------------------------------------
    # CORREO
    # -----------------------------------------------------

    email_match = False

    normalized_new_email = normalize_email(
        new_email
    )

    if normalized_new_email:

        for email in existing_emails or []:

            if (
                normalize_email(email)
                ==
                normalized_new_email
            ):
                email_match = True
                break

    # -----------------------------------------------------
    # CLASIFICACIÓN
    # -----------------------------------------------------

    if exact_name and (
        phone_match
        or email_match
    ):
        level = "EXACTA"

    elif phone_match or email_match:
        level = "MUY_ALTA"

    elif exact_name:
        level = "ALTA"

    elif name_score >= 90:
        level = "ALTA"

    elif name_score >= 75:
        level = "POSIBLE"

    else:
        level = "BAJA"

    return {
        "name_score": round(
            name_score,
            1,
        ),
        "phone_match": phone_match,
        "email_match": email_match,
        "exact_name": exact_name,
        "level": level,
    }