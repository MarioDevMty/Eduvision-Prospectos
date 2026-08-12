from __future__ import annotations


SYSTEM_FIELDS = {
    "organization_name": "Organización",
    "campus_name": "Plantel / Unidad",
    "campus_type": "Tipo de plantel",
    "contact_name": "Nombre del contacto",
    "contact_position": "Puesto",
    "contact_area": "Área",
    "institutional_phone": "Teléfono institucional",
    "institutional_email": "Correo institucional",
    "contact_phone": "Teléfono del contacto",
    "contact_whatsapp": "WhatsApp del contacto",
    "contact_email": "Correo del contacto",
    "address": "Domicilio",
    "municipality": "Municipio",
    "state": "Estado",
    "postal_code": "Código postal",
    "website": "Sitio web",
    "campus_code": "Clave de plantel",
    "subsystem": "Subsistema",
    "sector": "Sector",
    "relationship_type": "Tipo de relación",
    "study_plan": "Plan de estudios",
    "modality": "Modalidad",
    "status": "Estatus",
    "notes": "Notas",
}


# Campos mínimos que nos interesa revisar
# antes de construir registros.
CORE_FIELDS = [
    "organization_name",
    "campus_name",
    "campus_type",
    "contact_name",
    "contact_position",
    "contact_area",
    "institutional_phone",
    "institutional_email",
    "contact_phone",
    "contact_whatsapp",
    "contact_email",
    "address",
    "municipality",
    "state",
    "subsystem",
    "status",
    "notes",
]


def get_system_fields() -> dict[str, str]:
    """
    Devuelve:
    código interno -> etiqueta visible
    """

    return SYSTEM_FIELDS.copy()


def get_core_fields() -> list[str]:
    """
    Campos principales que se muestran
    en la pantalla de relación.
    """

    return CORE_FIELDS.copy()


def get_source_options(
    excel_columns: list[str],
) -> list[str]:
    """
    Opciones disponibles para cada campo del sistema.

    Cada campo puede provenir de:
    - una columna Excel;
    - un valor fijo;
    - no utilizarse.
    """

    options = [
        "SIN_DATO",
        "VALOR_FIJO",
    ]

    options.extend(
        excel_columns
    )

    return options


def source_option_label(
    option: str,
) -> str:
    """
    Etiqueta amigable para Streamlit.
    """

    if option == "SIN_DATO":
        return "— Sin dato / No usar"

    if option == "VALOR_FIJO":
        return "+ Valor fijo"

    return option


def build_preview_dataframe(
    dataframe,
    field_configuration: dict,
):
    """
    Construye el DataFrame transformado a partir
    de la relación confirmada por el usuario.

    No escribe nada en SQLite.
    """

    import pandas as pd

    result = pd.DataFrame(
        index=dataframe.index
    )

    for system_field, configuration in (
        field_configuration.items()
    ):

        source_type = configuration.get(
            "source_type"
        )

        if source_type == "COLUMN":

            column = configuration.get(
                "column"
            )

            if (
                column
                and column in dataframe.columns
            ):
                result[
                    system_field
                ] = dataframe[
                    column
                ]

        elif source_type == "FIXED":

            value = configuration.get(
                "value",
                "",
            )

            result[
                system_field
            ] = value

        elif source_type == "NONE":

            result[
                system_field
            ] = pd.NA

    return result