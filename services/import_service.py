from __future__ import annotations

from typing import Any

import pandas as pd

from database.repositories.prospecting import (
    add_email,
    add_phone,
    analyze_campus_duplicates,
    analyze_contact_duplicates,
    create_campus,
    create_contact,
    find_organization_by_normalized_name,
)

from database.repositories.staging import (
    save_pending_import_row,
)

from services.normalization import (
    normalize_text,
)

from services.data_validation import (
    validate_email_address,
)


# =========================================================
# VALORES VACÍOS
# =========================================================

EMPTY_VALUES = {
    "",
    "nan",
    "none",
    "null",
    "n/a",
    "na",
    "s/d",
    "sin dato",
    "sin datos",
    "no disponible",
    "no público",
    "no publico",
    "no aplica",
}


NORMALIZED_EMPTY_VALUES = {
    normalize_text(value)
    for value in EMPTY_VALUES
}


# =========================================================
# UTILIDADES
# =========================================================

def safe_text(value: Any) -> str:
    """
    Convierte un valor en texto seguro.

    Valores como:
    - No público
    - N/A
    - Sin dato
    - NaN

    se consideran ausencia de información.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value).strip()

    if normalize_text(text) in NORMALIZED_EMPTY_VALUES:
        return ""

    return text


def row_value(
    row: pd.Series,
    field: str,
) -> str:
    """
    Obtiene un campo de una fila sin inventar datos.
    """

    if field not in row.index:
        return ""

    return safe_text(
        row[field]
    )


def has_contact_data(
    row: pd.Series,
) -> bool:
    """
    Un contacto existe solamente cuando existe
    un nombre de persona.

    La ausencia de contacto NO impide importar
    un plantel.
    """

    return bool(
        row_value(
            row,
            "contact_name",
        )
    )



def validate_row_emails(
    row: pd.Series,
) -> list[str]:
    """
    Valida los correos presentes antes de analizar
    coincidencias o escribir en SQLite.

    Un correo vacío es permitido. Un valor presente
    con formato inválido es un error crítico.
    """

    errors = []

    email_fields = [
        (
            "institutional_email",
            "Correo institucional",
        ),
        (
            "contact_email",
            "Correo del contacto",
        ),
    ]

    for field_name, field_label in email_fields:

        email_value = row_value(
            row,
            field_name,
        )

        if not email_value:
            continue

        is_valid, reason = (
            validate_email_address(
                email_value
            )
        )

        if not is_valid:

            errors.append(
                (
                    f"{field_label}: "
                    f"'{email_value}'. "
                    f"{reason}"
                )
            )

    return errors


# =========================================================
# CLAVE DE PLANTEL EN EL MISMO LOTE
# =========================================================

def build_batch_campus_key(
    organization_name: str,
    campus_name: str,
    municipality: str = "",
) -> str:
    """
    Agrupa filas que corresponden al mismo plantel
    dentro de una importación.

    Esto NO fusiona registros en SQLite.
    """

    organization = normalize_text(
        organization_name
    )

    campus = normalize_text(
        campus_name
    )

    municipality_value = normalize_text(
        municipality
    )

    return (
        f"{organization}"
        f"||{campus}"
        f"||{municipality_value}"
    )


# =========================================================
# ORGANIZACIÓN
# =========================================================

def resolve_organization(
    organization_name: str,
) -> dict:
    """
    Busca la organización en SQLite.

    No crea automáticamente organizaciones.
    """

    name = safe_text(
        organization_name
    )

    if not name:
        return {
            "resolved": False,
            "organization_id": None,
            "organization_name": "",
            "reason": (
                "No se identificó la organización. "
                "Debe seleccionarse o asignarse "
                "antes de importar."
            ),
        }

    existing = (
        find_organization_by_normalized_name(
            normalize_text(
                name
            )
        )
    )

    if existing is None:
        return {
            "resolved": False,
            "organization_id": None,
            "organization_name": name,
            "reason": (
                f"La organización '{name}' "
                "no existe actualmente en SQLite."
            ),
        }

    return {
        "resolved": True,
        "organization_id":
            existing["id"],
        "organization_name":
            existing["official_name"],
        "reason": "",
    }


# =========================================================
# ANÁLISIS DEL PLANTEL
# =========================================================

def analyze_campus_group(
    first_row_number: int,
    row: pd.Series,
) -> dict:
    """
    Analiza un plantel independientemente
    de que tenga o no contactos.
    """

    organization_name = row_value(
        row,
        "organization_name",
    )

    campus_name = row_value(
        row,
        "campus_name",
    )

    municipality = row_value(
        row,
        "municipality",
    )

    institutional_phone = row_value(
        row,
        "institutional_phone",
    )

    organization = resolve_organization(
        organization_name
    )

    result = {
        "first_row_number":
            first_row_number,

        "organization_name":
            organization_name,

        "organization_id":
            None,

        "campus_name":
            campus_name,

        "campus_id":
            None,

        "status":
            "",

        "message":
            "",

        "campus_match":
            None,
    }

    # -----------------------------------------------------
    # ORGANIZACIÓN NO RESUELTA
    # -----------------------------------------------------

    if not organization["resolved"]:

        result["status"] = (
            "REQUIERE_REVISION"
        )

        result["message"] = (
            organization["reason"]
        )

        return result

    organization_id = (
        organization[
            "organization_id"
        ]
    )

    result[
        "organization_id"
    ] = organization_id

    # -----------------------------------------------------
    # PLANTEL VACÍO
    # -----------------------------------------------------

    if not campus_name:

        result["status"] = (
            "REQUIERE_REVISION"
        )

        result["message"] = (
            "No se identificó Plantel / Unidad. "
            "El contacto es opcional, pero el nombre "
            "del plantel es necesario para incorporar "
            "este registro."
        )

        return result

    # -----------------------------------------------------
    # BUSCAR POSIBLES DUPLICADOS
    # -----------------------------------------------------

    candidates = (
        analyze_campus_duplicates(
            organization_id=(
                organization_id
            ),
            campus_name=(
                campus_name
            ),
            municipality=(
                municipality
            ),
            phone=(
                institutional_phone
            ),
        )
    )

    # -----------------------------------------------------
    # PLANTEL NUEVO
    # -----------------------------------------------------

    if not candidates:

        result["status"] = (
            "NUEVO"
        )

        result["message"] = (
            "Plantel nuevo. Puede importarse "
            "aunque todavía no tenga contactos."
        )

        return result

    # -----------------------------------------------------
    # POSIBLE COINCIDENCIA
    # -----------------------------------------------------

    best_candidate = (
        candidates[0]
    )

    result[
        "campus_match"
    ] = best_candidate

    result[
        "campus_id"
    ] = best_candidate["id"]

    level = best_candidate.get(
        "level",
        "",
    )

    if level == "EXACTA":

        result["status"] = (
            "PLANTEL_EXISTENTE"
        )

        result["message"] = (
            "Coincidencia exacta con "
            f"{best_candidate['campus_name']}."
        )

    else:

        result["status"] = (
            "REQUIERE_REVISION"
        )

        result["message"] = (
            "Existe una posible coincidencia "
            f"de plantel ({level}). "
            "Debe revisarse manualmente."
        )

    return result


# =========================================================
# ANÁLISIS DEL LOTE
# =========================================================

def analyze_import_dataframe(
    dataframe: pd.DataFrame,
) -> list[dict]:
    """
    Analiza el lote completo.

    Varias filas del mismo plantel se agrupan.

    La ausencia de contacto NO bloquea
    la importación del plantel.
    """

    results = []

    campus_groups: dict[
        str,
        dict,
    ] = {}

    group_numbers: dict[
        str,
        int,
    ] = {}

    next_group_number = 1

    for index, row in dataframe.iterrows():

        row_number = index + 1

        critical_errors = (
            validate_row_emails(
                row
            )
        )

        organization_name = row_value(
            row,
            "organization_name",
        )

        campus_name = row_value(
            row,
            "campus_name",
        )

        municipality = row_value(
            row,
            "municipality",
        )

        contact_name = row_value(
            row,
            "contact_name",
        )

        contact_present = (
            has_contact_data(
                row
            )
        )

        batch_key = (
            build_batch_campus_key(
                organization_name,
                campus_name,
                municipality,
            )
        )

        # -------------------------------------------------
        # PRIMERA FILA DEL PLANTEL EN EL LOTE
        # -------------------------------------------------

        if batch_key not in campus_groups:

            group_analysis = (
                analyze_campus_group(
                    first_row_number=(
                        row_number
                    ),
                    row=row,
                )
            )

            campus_groups[
                batch_key
            ] = group_analysis

            group_numbers[
                batch_key
            ] = next_group_number

            next_group_number += 1

            is_first_row = True

        else:

            group_analysis = (
                campus_groups[
                    batch_key
                ]
            )

            is_first_row = False

        group_number = (
            group_numbers[
                batch_key
            ]
        )

        base_status = (
            group_analysis[
                "status"
            ]
        )

        # -------------------------------------------------
        # FILAS REPETIDAS DEL MISMO PLANTEL
        # -------------------------------------------------

        if (
            not is_first_row
            and base_status
            in {
                "NUEVO",
                "PLANTEL_EXISTENTE",
            }
        ):

            row_status = (
                "MISMO_PLANTEL_LOTE"
            )

            message = (
                "Pertenece al mismo plantel "
                f"identificado desde la fila "
                f"{group_analysis['first_row_number']}."
            )

        else:

            row_status = (
                base_status
            )

            message = (
                group_analysis[
                    "message"
                ]
            )

        # -------------------------------------------------
        # CONTACTO OPCIONAL
        # -------------------------------------------------

        if (
            base_status
            != "REQUIERE_REVISION"
            and not contact_present
        ):

            message = (
                f"{message} "
                "La fila no contiene contacto; "
                "el plantel sí puede procesarse."
            )

        # -------------------------------------------------
        # ERROR CRÍTICO DE CORREO
        # -------------------------------------------------

        if critical_errors:

            row_status = (
                "ERROR_VALIDACION"
            )

            message = (
                "La fila contiene uno o más correos "
                "inválidos. Corrige el archivo o el "
                "mapeo antes de importar. "
                + " | ".join(
                    critical_errors
                )
            )

        results.append(
            {
                "row_number":
                    row_number,

                "group_number":
                    group_number,

                "batch_campus_key":
                    batch_key,

                "group_first_row":
                    group_analysis[
                        "first_row_number"
                    ],

                "is_group_first_row":
                    is_first_row,

                "organization_name":
                    organization_name,

                "organization_id":
                    group_analysis[
                        "organization_id"
                    ],

                "campus_name":
                    campus_name,

                "campus_id":
                    group_analysis[
                        "campus_id"
                    ],

                "contact_name":
                    contact_name,

                "contact_present":
                    contact_present,

                "record_type":
                    (
                        "PLANTEL_CON_CONTACTO"
                        if contact_present
                        else
                        "PLANTEL_SIN_CONTACTO"
                    ),

                "status":
                    row_status,

                "critical_error":
                    bool(
                        critical_errors
                    ),

                "critical_errors":
                    critical_errors,

                "campus_group_status":
                    base_status,

                "message":
                    message,

                "campus_match":
                    group_analysis[
                        "campus_match"
                    ],
            }
        )

    return results


# =========================================================
# RESOLVER PLANTEL DURANTE IMPORTACIÓN
# =========================================================

def resolve_batch_campus_for_import(
    row: pd.Series,
    analysis: dict,
    user_id: int,
    campus_cache: dict,
) -> dict:
    """
    Resuelve el campus_id para una fila.

    campus_cache evita crear varias veces
    el mismo plantel dentro del mismo lote.
    """

    batch_key = (
        analysis[
            "batch_campus_key"
        ]
    )

    # -----------------------------------------------------
    # YA RESUELTO EN EL LOTE
    # -----------------------------------------------------

    if batch_key in campus_cache:

        return {
            "resolved": True,
            "campus_id":
                campus_cache[
                    batch_key
                ],
            "created": False,
            "from_batch_cache": True,
        }

    group_status = (
        analysis[
            "campus_group_status"
        ]
    )

    # -----------------------------------------------------
    # REQUIERE REVISIÓN
    # -----------------------------------------------------

    if (
        group_status
        ==
        "REQUIERE_REVISION"
    ):

        return {
            "resolved": False,
            "campus_id": None,
            "created": False,
            "from_batch_cache": False,
        }

    # -----------------------------------------------------
    # PLANTEL EXISTENTE
    # -----------------------------------------------------

    if (
        group_status
        ==
        "PLANTEL_EXISTENTE"
    ):

        campus_id = (
            analysis[
                "campus_id"
            ]
        )

        campus_cache[
            batch_key
        ] = campus_id

        return {
            "resolved": True,
            "campus_id":
                campus_id,
            "created": False,
            "from_batch_cache": False,
        }

    # -----------------------------------------------------
    # CREAR NUEVO PLANTEL
    # -----------------------------------------------------

    organization_id = (
        analysis[
            "organization_id"
        ]
    )

    campus_name = row_value(
        row,
        "campus_name",
    )

    campus_type = row_value(
        row,
        "campus_type",
    )

    municipality = row_value(
        row,
        "municipality",
    )

    state = row_value(
        row,
        "state",
    )

    address = row_value(
        row,
        "address",
    )

    campus_id = create_campus(
        organization_id=(
            organization_id
        ),
        campus_name=(
            campus_name
        ),
        campus_type=(
            campus_type
            or "PLANTEL"
        ),
        municipality=(
            municipality
        ),
        state=(
            state
        ),
        address=(
            address
        ),
        status=(
            "REQUIERE_REVISION"
        ),
        user_id=user_id,
    )

    campus_cache[
        batch_key
    ] = campus_id

    return {
        "resolved": True,
        "campus_id":
            campus_id,
        "created": True,
        "from_batch_cache": False,
    }


# =========================================================
# DATOS INSTITUCIONALES
# =========================================================

def add_institutional_data(
    campus_id: int,
    row: pd.Series,
    user_id: int,
    primary: bool,
) -> None:
    """
    Añade teléfono y correo institucional
    cuando existan.

    No son obligatorios.
    """

    institutional_phone = row_value(
        row,
        "institutional_phone",
    )

    institutional_email = row_value(
        row,
        "institutional_email",
    )

    if institutional_phone:

        add_phone(
            entity_type="CAMPUS",
            entity_id=campus_id,
            phone=institutional_phone,
            phone_type="INSTITUCIONAL",
            user_id=user_id,
            is_primary=primary,
        )

    if institutional_email:

        add_email(
            entity_type="CAMPUS",
            entity_id=campus_id,
            email=institutional_email,
            email_type="INSTITUCIONAL",
            user_id=user_id,
            is_primary=primary,
        )


# =========================================================
# CONTACTOS
# =========================================================

def process_contact(
    campus_id: int,
    row: pd.Series,
    user_id: int,
) -> dict:
    """
    Procesa el contacto únicamente cuando
    existe un nombre.

    Un plantel sin contacto es válido.
    """

    contact_name = row_value(
        row,
        "contact_name",
    )

    # -----------------------------------------------------
    # SIN CONTACTO
    # -----------------------------------------------------

    if not contact_name:

        return {
            "created": False,
            "existing": False,
            "pending": False,
            "skipped": True,
            "message": (
                "Plantel procesado sin contacto. "
                "Puede enriquecerse posteriormente."
            ),
        }

    contact_position = row_value(
        row,
        "contact_position",
    )

    contact_area = row_value(
        row,
        "contact_area",
    )

    contact_phone = row_value(
        row,
        "contact_phone",
    )

    contact_whatsapp = row_value(
        row,
        "contact_whatsapp",
    )

    contact_email = row_value(
        row,
        "contact_email",
    )

    notes = row_value(
        row,
        "notes",
    )

    match_phone = (
        contact_phone
        or contact_whatsapp
    )

    candidates = (
        analyze_contact_duplicates(
            campus_id=campus_id,
            full_name=contact_name,
            phone=match_phone,
            email=contact_email,
        )
    )

    exact_contacts = [
        candidate
        for candidate in candidates
        if candidate.get(
            "level"
        ) == "EXACTA"
    ]

    # -----------------------------------------------------
    # CONTACTO EXISTENTE
    # -----------------------------------------------------

    if exact_contacts:

        contact_id = (
            exact_contacts[0]["id"]
        )

        if contact_phone:

            add_phone(
                entity_type="CONTACT",
                entity_id=contact_id,
                phone=contact_phone,
                phone_type="DIRECTO",
                user_id=user_id,
                is_primary=False,
            )

        if contact_whatsapp:

            add_phone(
                entity_type="CONTACT",
                entity_id=contact_id,
                phone=contact_whatsapp,
                phone_type="WHATSAPP",
                user_id=user_id,
                is_primary=False,
            )

        if contact_email:

            add_email(
                entity_type="CONTACT",
                entity_id=contact_id,
                email=contact_email,
                email_type="DIRECTO",
                user_id=user_id,
                is_primary=False,
            )

        return {
            "created": False,
            "existing": True,
            "pending": False,
            "skipped": False,
            "message": (
                "Contacto existente. "
                "Solo se agregaron medios de "
                "contacto nuevos."
            ),
        }

    # -----------------------------------------------------
    # CONTACTO POSIBLE / AMBIGUO
    # -----------------------------------------------------

    if candidates:

        return {
            "created": False,
            "existing": False,
            "pending": True,
            "skipped": False,
            "message": (
                "Existe una posible coincidencia "
                "de contacto. No se creó "
                "automáticamente."
            ),
        }

    # -----------------------------------------------------
    # CONTACTO NUEVO
    # -----------------------------------------------------

    contact_id = create_contact(
        campus_id=campus_id,
        full_name=contact_name,
        position=contact_position,
        area=contact_area,
        notes=notes,
        status="REQUIERE_REVISION",
        user_id=user_id,
    )

    if contact_phone:

        add_phone(
            entity_type="CONTACT",
            entity_id=contact_id,
            phone=contact_phone,
            phone_type="DIRECTO",
            user_id=user_id,
            is_primary=True,
        )

    if contact_whatsapp:

        add_phone(
            entity_type="CONTACT",
            entity_id=contact_id,
            phone=contact_whatsapp,
            phone_type="WHATSAPP",
            user_id=user_id,
            is_primary=(
                not contact_phone
            ),
        )

    if contact_email:

        add_email(
            entity_type="CONTACT",
            entity_id=contact_id,
            email=contact_email,
            email_type="DIRECTO",
            user_id=user_id,
            is_primary=True,
        )

    return {
        "created": True,
        "existing": False,
        "pending": False,
        "skipped": False,
        "message": (
            "Contacto nuevo creado."
        ),
    }


# =========================================================
# IMPORTACIÓN SEGURA
# =========================================================

def import_safe_dataframe(
    dataframe: pd.DataFrame,
    analysis_results: list[dict],
    user_id: int,
    source_filename: str = "",
    source_sheet: str = "",
) -> list[dict]:
    """
    Importa los registros seguros.

    Los registros ambiguos NO se incorporan
    a las tablas maestras.

    En su lugar se almacenan en import_staging
    para revisión humana.
    """

    critical_items = [
        item
        for item in analysis_results
        if item.get(
            "critical_error",
            False,
        )
    ]

    if critical_items:

        return [
            {
                "row_number":
                    item.get(
                        "row_number",
                        "",
                    ),

                "imported":
                    False,

                "action":
                    "ERROR_VALIDACION",

                "message":
                    item.get(
                        "message",
                        (
                            "La importación fue bloqueada "
                            "por errores críticos."
                        ),
                    ),
            }
            for item in critical_items
        ]

    results = []

    analysis_by_row = {
        item["row_number"]: item
        for item in analysis_results
    }

    campus_cache: dict[
        str,
        int,
    ] = {}

    for index, row in dataframe.iterrows():

        row_number = index + 1

        analysis = (
            analysis_by_row.get(
                row_number
            )
        )

        # -------------------------------------------------
        # ERROR: NO EXISTE ANÁLISIS
        # -------------------------------------------------

        if analysis is None:

            results.append(
                {
                    "row_number":
                        row_number,

                    "imported":
                        False,

                    "action":
                        "ERROR",

                    "message":
                        (
                            "No existe análisis "
                            "para esta fila."
                        ),
                }
            )

            continue

        # =================================================
        # REQUIERE REVISIÓN → STAGING
        # =================================================

        if (
            analysis.get(
                "campus_group_status"
            )
            ==
            "REQUIERE_REVISION"
        ):

            try:

                staging_id = (
                    save_pending_import_row(
                        row=row,
                        source_filename=(
                            source_filename
                        ),
                        source_sheet=(
                            source_sheet
                        ),
                        source_row=(
                            row_number
                        ),
                        reason=(
                            analysis.get(
                                "message",
                                "Requiere revisión.",
                            )
                        ),
                        review_type="CAMPUS",
                        user_id=user_id,
                    )
                )

                if staging_id:

                    message = (
                        "El registro no se incorporó "
                        "a la base maestra. "
                        "Fue enviado a la bandeja "
                        "de Validación."
                    )

                else:

                    message = (
                        "El registro no se incorporó "
                        "a la base maestra porque "
                        "ya existe como pendiente "
                        "en Validación."
                    )

                results.append(
                    {
                        "row_number":
                            row_number,

                        "imported":
                            False,

                        "action":
                            "ENVIADO_A_VALIDACION",

                        "message":
                            message,
                    }
                )

            except Exception as exc:

                results.append(
                    {
                        "row_number":
                            row_number,

                        "imported":
                            False,

                        "action":
                            "ERROR_STAGING",

                        "message":
                            (
                                "No fue posible guardar "
                                "el registro en Validación: "
                                f"{exc}"
                            ),
                    }
                )

            continue

        # =================================================
        # REGISTRO SEGURO
        # =================================================

        try:

            # ---------------------------------------------
            # RESOLVER PLANTEL
            # ---------------------------------------------

            campus_resolution = (
                resolve_batch_campus_for_import(
                    row=row,
                    analysis=analysis,
                    user_id=user_id,
                    campus_cache=campus_cache,
                )
            )

            if not campus_resolution[
                "resolved"
            ]:

                # Caso defensivo:
                # si no se pudo resolver aquí,
                # también debe ir a staging.

                staging_id = (
                    save_pending_import_row(
                        row=row,
                        source_filename=(
                            source_filename
                        ),
                        source_sheet=(
                            source_sheet
                        ),
                        source_row=(
                            row_number
                        ),
                        reason=(
                            "No fue posible resolver "
                            "el plantel durante "
                            "la importación."
                        ),
                        review_type="CAMPUS",
                        user_id=user_id,
                    )
                )

                results.append(
                    {
                        "row_number":
                            row_number,

                        "imported":
                            False,

                        "action":
                            "ENVIADO_A_VALIDACION",

                        "message":
                            (
                                "El plantel no pudo "
                                "resolverse y fue enviado "
                                "a Validación."
                                if staging_id
                                else
                                "El plantel ya estaba "
                                "pendiente en Validación."
                            ),
                    }
                )

                continue

            campus_id = (
                campus_resolution[
                    "campus_id"
                ]
            )

            campus_created = (
                campus_resolution[
                    "created"
                ]
            )

            # ---------------------------------------------
            # DATOS INSTITUCIONALES
            # ---------------------------------------------

            add_institutional_data(
                campus_id=campus_id,
                row=row,
                user_id=user_id,
                primary=campus_created,
            )

            # ---------------------------------------------
            # CONTACTO
            # ---------------------------------------------

            contact_result = (
                process_contact(
                    campus_id=campus_id,
                    row=row,
                    user_id=user_id,
                )
            )

            # ---------------------------------------------
            # CONTACTO AMBIGUO
            # ---------------------------------------------

            if contact_result[
                "pending"
            ]:

                staging_id = (
                    save_pending_import_row(
                        row=row,
                        source_filename=(
                            source_filename
                        ),
                        source_sheet=(
                            source_sheet
                        ),
                        source_row=(
                            row_number
                        ),
                        reason=(
                            contact_result[
                                "message"
                            ]
                        ),
                        review_type="CONTACT",
                        user_id=user_id,
                    )
                )

                results.append(
                    {
                        "row_number":
                            row_number,

                        "imported":
                            True,

                        "action":
                            (
                                "PLANTEL_PROCESADO_"
                                "CONTACTO_A_VALIDACION"
                            ),

                        "message":
                            (
                                "El plantel fue procesado, "
                                "pero el contacto quedó "
                                "pendiente de Validación."
                                if staging_id
                                else
                                "El plantel fue procesado. "
                                "El contacto ya estaba "
                                "pendiente en Validación."
                            ),
                    }
                )

                continue

            # ---------------------------------------------
            # SIN CONTACTO
            # ---------------------------------------------

            if contact_result[
                "skipped"
            ]:

                if campus_created:

                    action = (
                        "PLANTEL_CREADO_SIN_CONTACTO"
                    )

                else:

                    action = (
                        "PLANTEL_PROCESADO_SIN_CONTACTO"
                    )

            # ---------------------------------------------
            # NUEVO PLANTEL + NUEVO CONTACTO
            # ---------------------------------------------

            elif (
                campus_created
                and contact_result[
                    "created"
                ]
            ):

                action = (
                    "PLANTEL_Y_CONTACTO_CREADOS"
                )

            # ---------------------------------------------
            # NUEVO PLANTEL
            # ---------------------------------------------

            elif campus_created:

                action = (
                    "PLANTEL_CREADO"
                )

            # ---------------------------------------------
            # NUEVO CONTACTO
            # ---------------------------------------------

            elif contact_result[
                "created"
            ]:

                action = (
                    "CONTACTO_CREADO"
                )

            # ---------------------------------------------
            # CONTACTO EXISTENTE
            # ---------------------------------------------

            elif contact_result[
                "existing"
            ]:

                action = (
                    "CONTACTO_EXISTENTE"
                )

            else:

                action = (
                    "PLANTEL_PROCESADO"
                )

            results.append(
                {
                    "row_number":
                        row_number,

                    "imported":
                        True,

                    "action":
                        action,

                    "message":
                        contact_result[
                            "message"
                        ],
                }
            )

        except Exception as exc:

            results.append(
                {
                    "row_number":
                        row_number,

                    "imported":
                        False,

                    "action":
                        "ERROR",

                    "message":
                        str(exc),
                }
            )

    return results