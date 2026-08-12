from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from database.repositories.import_reporting import (
    get_import_batch_snapshot,
    summarize_import_actions,
)

from database.repositories.prospecting import (
    create_organization,
    get_organizations,
)

from importers.excel_importer import (
    dataframe_for_display,
    dataframe_summary,
    get_dataframe_profile,
    get_sheet_names,
    read_excel_sheet,
    validate_excel_file,
)

from services.field_mapping import (
    build_preview_dataframe,
    get_core_fields,
    get_source_options,
    get_system_fields,
    source_option_label,
)

from services.import_service import (
    analyze_import_dataframe,
    import_safe_dataframe,
)


# =========================================================
# SEGURIDAD
# =========================================================

if not st.session_state.get(
    "authenticated",
    False,
):
    st.error(
        "La sesión no está activa."
    )
    st.stop()


user_id = st.session_state.get(
    "user_id"
)

if user_id is None:

    st.error(
        "No se encontró el usuario de la sesión."
    )

    st.stop()


# =========================================================
# SESSION STATE
# =========================================================

DEFAULTS = {
    "import_file_hash": None,
    "import_file_name": None,
    "import_file_bytes": None,
    "import_sheet_names": None,
    "import_dataframe": None,
    "import_selected_sheet": None,
    "import_header_row": 1,
    "import_field_config": None,
    "import_preview": None,
    "import_analysis": None,
    "import_results": None,
}


for key, value in DEFAULTS.items():

    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# UTILIDADES
# =========================================================

def clear_mapping_widget_state() -> None:
    """
    Elimina widgets asociados al mapeo
    de la hoja anterior.
    """

    prefixes_to_clear = (
        "map_source_",
        "fixed_",
        "existing_organization",
        "new_import_org_",
    )

    exact_keys_to_clear = {
        "organization_fixed_mode",
        "confirm_import_checkbox",
    }

    keys_to_delete = []

    for key in list(
        st.session_state.keys()
    ):

        if (
            key.startswith(
                prefixes_to_clear
            )
            or key in exact_keys_to_clear
        ):
            keys_to_delete.append(
                key
            )

    for key in keys_to_delete:

        del st.session_state[
            key
        ]


def calculate_hash(
    file_bytes: bytes,
) -> str:

    return hashlib.sha256(
        file_bytes
    ).hexdigest()


def reset_import_analysis() -> None:
    """
    Limpia el procesamiento de una importación.
    """

    st.session_state[
        "import_sheet_names"
    ] = None

    st.session_state[
        "import_dataframe"
    ] = None

    st.session_state[
        "import_selected_sheet"
    ] = None

    st.session_state[
        "import_field_config"
    ] = None

    st.session_state[
        "import_preview"
    ] = None

    st.session_state[
        "import_analysis"
    ] = None

    st.session_state[
        "import_results"
    ] = None

    clear_mapping_widget_state()


def get_existing_organization_options() -> dict:
    """
    Organizaciones existentes en SQLite.
    """

    rows = get_organizations()

    return {
        row["official_name"]:
            row["id"]

        for row in rows
    }


def safe_display_value(
    value,
) -> str:
    """
    Convierte un valor en texto para mostrarlo
    sin convertir NA en un dato real.
    """

    if value is None:
        return ""

    try:

        if pd.isna(value):
            return ""

    except (TypeError, ValueError):
        pass

    return str(
        value
    ).strip()


# =========================================================
# CABECERA
# =========================================================

st.title(
    "Importar datos"
)

st.caption(
    "Carga una hoja, relaciona sus columnas "
    "con la estructura de la base y revisa "
    "los registros antes de importar."
)


# =========================================================
# PASO 1 - ARCHIVO
# =========================================================

st.header(
    "1. Cargar archivo"
)


uploaded_file = st.file_uploader(
    "Archivo Excel",
    type=[
        "xlsx",
        "xls",
    ],
)


if uploaded_file is None:

    st.info(
        "Selecciona un archivo Excel "
        "para comenzar."
    )

    st.stop()


file_bytes = (
    uploaded_file.getvalue()
)

file_hash = calculate_hash(
    file_bytes
)


valid_file, validation_message = (
    validate_excel_file(
        uploaded_file.name
    )
)


if not valid_file:

    st.error(
        validation_message
    )

    st.stop()


# ---------------------------------------------------------
# ARCHIVO NUEVO
# ---------------------------------------------------------

if (
    st.session_state[
        "import_file_hash"
    ]
    !=
    file_hash
):

    reset_import_analysis()

    st.session_state[
        "import_file_hash"
    ] = file_hash

    st.session_state[
        "import_file_name"
    ] = uploaded_file.name

    st.session_state[
        "import_file_bytes"
    ] = file_bytes


st.success(
    f"Archivo: **{uploaded_file.name}**"
)


# =========================================================
# PASO 2 - HOJA
# =========================================================

st.divider()

st.header(
    "2. Seleccionar hoja"
)


if (
    st.session_state[
        "import_sheet_names"
    ]
    is None
):

    try:

        st.session_state[
            "import_sheet_names"
        ] = get_sheet_names(
            file_bytes,
            uploaded_file.name,
        )

    except Exception as exc:

        st.error(
            "No se pudieron leer "
            "las hojas del archivo."
        )

        st.exception(
            exc
        )

        st.stop()


sheet_names = (
    st.session_state[
        "import_sheet_names"
    ]
)


if not sheet_names:

    st.error(
        "El archivo no contiene hojas legibles."
    )

    st.stop()


selected_sheet = st.selectbox(
    "Hoja",
    options=sheet_names,
    width="stretch",
    key="import_sheet_selector",
)


# ---------------------------------------------------------
# CAMBIO DE HOJA
# ---------------------------------------------------------

previous_sheet = (
    st.session_state.get(
        "import_selected_sheet"
    )
)


if (
    previous_sheet is not None
    and previous_sheet != selected_sheet
):

    st.session_state[
        "import_dataframe"
    ] = None

    st.session_state[
        "import_field_config"
    ] = None

    st.session_state[
        "import_preview"
    ] = None

    st.session_state[
        "import_analysis"
    ] = None

    st.session_state[
        "import_results"
    ] = None

    clear_mapping_widget_state()


header_row = st.number_input(
    "Fila de encabezados",
    min_value=1,
    max_value=50,
    value=1,
    step=1,
)


if st.button(
    "Extraer campos de la hoja",
    type="primary",
    width="stretch",
):

    try:

        dataframe = read_excel_sheet(
            file_bytes=file_bytes,
            filename=uploaded_file.name,
            sheet_name=selected_sheet,
            header_row=(
                int(header_row)
                - 1
            ),
        )

    except Exception as exc:

        st.error(
            "No fue posible leer "
            "la hoja."
        )

        st.exception(
            exc
        )

        st.stop()


    st.session_state[
        "import_dataframe"
    ] = dataframe

    st.session_state[
        "import_selected_sheet"
    ] = selected_sheet

    st.session_state[
        "import_header_row"
    ] = int(
        header_row
    )

    st.session_state[
        "import_field_config"
    ] = None

    st.session_state[
        "import_preview"
    ] = None

    st.session_state[
        "import_analysis"
    ] = None

    st.session_state[
        "import_results"
    ] = None

    clear_mapping_widget_state()

    st.rerun()


# =========================================================
# NECESITAMOS DATAFRAME PARA CONTINUAR
# =========================================================

dataframe = (
    st.session_state.get(
        "import_dataframe"
    )
)


if dataframe is None:
    st.stop()


# =========================================================
# PASO 3 - CAMPOS ENCONTRADOS
# =========================================================

st.divider()

st.header(
    "3. Campos encontrados en la hoja"
)


summary = dataframe_summary(
    dataframe
)


col1, col2, col3 = (
    st.columns(3)
)


with col1:

    st.metric(
        "Hoja",
        st.session_state[
            "import_selected_sheet"
        ],
    )


with col2:

    st.metric(
        "Registros",
        summary["rows"],
    )


with col3:

    st.metric(
        "Campos encontrados",
        summary["columns"],
    )


st.write(
    "Estos son los campos físicos encontrados "
    "en la hoja. Un campo se considera existente "
    "aunque actualmente no contenga datos."
)


# ---------------------------------------------------------
# PERFIL DE CAMPOS
# ---------------------------------------------------------

column_profiles = (
    get_dataframe_profile(
        dataframe,
        sample_size=3,
    )
)


found_columns_df = pd.DataFrame(
    [
        {
            "Campo encontrado":
                profile[
                    "column"
                ],

            "Registros con dato":
                profile[
                    "filled_rows"
                ],

            "Registros vacíos":
                profile[
                    "empty_rows"
                ],

            "% llenado":
                profile[
                    "fill_percentage"
                ],

            "Ejemplos":
                " | ".join(
                    profile[
                        "samples"
                    ]
                ),
        }

        for profile
        in column_profiles
    ]
)


st.dataframe(
    dataframe_for_display(
        found_columns_df
    ),
    width="stretch",
    hide_index=True,
)


st.caption(
    "Una columna con 0% de llenado sigue siendo "
    "una columna válida y puede relacionarse "
    "con un campo del sistema."
)


# ---------------------------------------------------------
# DATOS ORIGINALES
# ---------------------------------------------------------

with st.expander(
    "Ver datos originales de la hoja",
    expanded=False,
):

    st.dataframe(
        dataframe_for_display(
            dataframe.head(20)
        ),
        width="stretch",
        hide_index=True,
    )


# =========================================================
# PASO 4 - RELACIONAR CAMPOS
# =========================================================

st.divider()

st.header(
    "4. Relacionar campos"
)


st.write(
    "A la izquierda están los campos "
    "que necesita nuestra base. "
    "A la derecha selecciona la columna "
    "del Excel que contiene ese dato, "
    "un valor fijo o Sin dato."
)


system_fields = (
    get_system_fields()
)

core_fields = (
    get_core_fields()
)

excel_columns = list(
    dataframe.columns
)

source_options = (
    get_source_options(
        excel_columns
    )
)


field_configuration = {}


header_left, header_right = (
    st.columns(
        [1, 1.4]
    )
)


with header_left:

    st.markdown(
        "**Campo que necesita el sistema**"
    )


with header_right:

    st.markdown(
        "**Campo encontrado en Excel / Valor fijo**"
    )


# =========================================================
# MAPEO CAMPO POR CAMPO
# =========================================================

for field_code in core_fields:

    field_label = (
        system_fields.get(
            field_code,
            field_code,
        )
    )

    col_left, col_right = (
        st.columns(
            [1, 1.4]
        )
    )


    with col_left:

        st.markdown(
            f"**{field_label}**"
        )


    with col_right:

        selected_source = (
            st.selectbox(
                (
                    f"Fuente para "
                    f"{field_label}"
                ),
                options=source_options,
                format_func=(
                    source_option_label
                ),
                key=(
                    f"map_source_"
                    f"{field_code}"
                ),
                label_visibility="collapsed",
                width="stretch",
            )
        )


    # =====================================================
    # SIN DATO
    # =====================================================

    if (
        selected_source
        ==
        "SIN_DATO"
    ):

        field_configuration[
            field_code
        ] = {
            "source_type":
                "NONE",
        }


    # =====================================================
    # VALOR FIJO
    # =====================================================

    elif (
        selected_source
        ==
        "VALOR_FIJO"
    ):

        # -------------------------------------------------
        # ORGANIZACIÓN
        # -------------------------------------------------

        if (
            field_code
            ==
            "organization_name"
        ):

            organization_options = (
                get_existing_organization_options()
            )


            organization_mode = (
                st.radio(
                    "Organización",
                    [
                        "Seleccionar existente",
                        "Crear nueva",
                    ],
                    horizontal=True,
                    key=(
                        "organization_fixed_mode"
                    ),
                )
            )


            # =============================================
            # ORGANIZACIÓN EXISTENTE
            # =============================================

            if (
                organization_mode
                ==
                "Seleccionar existente"
            ):

                if organization_options:

                    selected_org = (
                        st.selectbox(
                            "Organización existente",
                            options=list(
                                organization_options.keys()
                            ),
                            width="stretch",
                            key=(
                                "existing_organization"
                            ),
                        )
                    )


                    field_configuration[
                        field_code
                    ] = {
                        "source_type":
                            "FIXED",

                        "value":
                            selected_org,

                        "organization_id":
                            organization_options[
                                selected_org
                            ],
                    }


                else:

                    st.warning(
                        "Todavía no existen "
                        "organizaciones registradas."
                    )

                    field_configuration[
                        field_code
                    ] = {
                        "source_type":
                            "NONE",
                    }


            # =============================================
            # CREAR ORGANIZACIÓN
            # =============================================

            else:

                st.markdown(
                    "**Crear organización sin salir "
                    "de la importación**"
                )


                new_org_name = (
                    st.text_input(
                        "Nombre oficial",
                        key=(
                            "new_import_org_name"
                        ),
                    )
                )


                new_org_subsystem = (
                    st.text_input(
                        "Subsistema",
                        key=(
                            "new_import_org_subsystem"
                        ),
                    )
                )


                new_org_sector = (
                    st.selectbox(
                        "Sector",
                        [
                            "",
                            "PÚBLICO",
                            "PRIVADO",
                        ],
                        key=(
                            "new_import_org_sector"
                        ),
                    )
                )


                if st.button(
                    "Crear organización",
                    key=(
                        "create_org_from_import"
                    ),
                    width="content",
                ):

                    if not new_org_name.strip():

                        st.error(
                            "El nombre de la organización "
                            "es obligatorio."
                        )

                    else:

                        result = (
                            create_organization(
                                official_name=(
                                    new_org_name
                                ),
                                subsystem=(
                                    new_org_subsystem
                                ),
                                sector=(
                                    new_org_sector
                                ),
                                relationship_type="",
                                status=(
                                    "REQUIERE_REVISION"
                                ),
                                user_id=user_id,
                            )
                        )


                        if result[
                            "created"
                        ]:

                            st.success(
                                "Organización creada."
                            )

                        else:

                            st.warning(
                                "La organización ya existía."
                            )

                        st.rerun()


                field_configuration[
                    field_code
                ] = {
                    "source_type":
                        "NONE",
                }


        # -------------------------------------------------
        # OTROS VALORES FIJOS
        # -------------------------------------------------

        else:

            fixed_value = (
                st.text_input(
                    (
                        f"Valor fijo para "
                        f"{field_label}"
                    ),
                    key=(
                        f"fixed_"
                        f"{field_code}"
                    ),
                )
            )


            field_configuration[
                field_code
            ] = {
                "source_type":
                    "FIXED",

                "value":
                    fixed_value,
            }


    # =====================================================
    # COLUMNA EXCEL
    # =====================================================

    else:

        field_configuration[
            field_code
        ] = {
            "source_type":
                "COLUMN",

            "column":
                selected_source,
        }


# =========================================================
# CAMPOS DEL EXCEL IGNORADOS
# =========================================================

used_excel_columns = {
    config["column"]

    for config
    in field_configuration.values()

    if (
        config.get(
            "source_type"
        )
        ==
        "COLUMN"
    )
}


ignored_excel_columns = [
    column

    for column
    in excel_columns

    if column
    not in used_excel_columns
]


st.subheader(
    "Campos del Excel que serán ignorados"
)


if ignored_excel_columns:

    st.write(
        ", ".join(
            ignored_excel_columns
        )
    )

else:

    st.caption(
        "Todas las columnas del Excel "
        "están relacionadas."
    )


# =========================================================
# PASO 5 - PREVISUALIZAR
# =========================================================

st.divider()

st.header(
    "5. Previsualizar registros"
)


if st.button(
    "Construir previsualización",
    type="primary",
    width="stretch",
):

    organization_config = (
        field_configuration.get(
            "organization_name",
            {}
        )
    )

    campus_config = (
        field_configuration.get(
            "campus_name",
            {}
        )
    )


    # -----------------------------------------------------
    # NECESITAMOS CONTEXTO DE ORGANIZACIÓN / PLANTEL
    # -----------------------------------------------------

    if (
        organization_config.get(
            "source_type"
        )
        ==
        "NONE"
        and
        campus_config.get(
            "source_type"
        )
        ==
        "NONE"
    ):

        st.error(
            "Debes identificar al menos "
            "Organización o Plantel / Unidad."
        )

    else:

        preview = (
            build_preview_dataframe(
                dataframe,
                field_configuration,
            )
        )


        st.session_state[
            "import_field_config"
        ] = field_configuration

        st.session_state[
            "import_preview"
        ] = preview

        st.session_state[
            "import_analysis"
        ] = None

        st.session_state[
            "import_results"
        ] = None

        st.rerun()


# =========================================================
# PREVISUALIZACIÓN RESULTANTE
# =========================================================

preview = (
    st.session_state.get(
        "import_preview"
    )
)


if preview is None:
    st.stop()


st.success(
    (
        f"Se construyeron "
        f"{len(preview)} registros "
        "para revisión."
    )
)


display_preview = (
    preview.rename(
        columns=system_fields
    )
)


st.dataframe(
    dataframe_for_display(
        display_preview
    ),
    width="stretch",
    hide_index=True,
)


st.caption(
    "Los campos sin información permanecen vacíos. "
    "No se generan ni deducen datos faltantes."
)


# =========================================================
# PASO 6 - IMPORTACIÓN
# =========================================================

st.divider()

st.header(
    "6. Importar"
)


st.write(
    "Antes de escribir en SQLite, "
    "el sistema comprobará los planteles "
    "y contactos existentes."
)


# =========================================================
# ANALIZAR IMPORTACIÓN
# =========================================================

if st.button(
    "Revisar e importar registros",
    type="primary",
    width="stretch",
    key="analyze_import_button",
):

    with st.spinner(
        "Analizando coincidencias..."
    ):

        analysis_results = (
            analyze_import_dataframe(
                preview
            )
        )


    st.session_state[
        "import_analysis"
    ] = analysis_results

    st.session_state[
        "import_results"
    ] = None

    st.rerun()


# =========================================================
# RESULTADO DEL ANÁLISIS
# =========================================================

analysis_results = (
    st.session_state.get(
        "import_analysis"
    )
)


if analysis_results:

    st.subheader(
        "Resultado de la revisión"
    )


    analysis_display = []


    for item in analysis_results:

        campus_match = (
            item.get(
                "campus_match"
            )
        )

        matched_name = ""

        match_level = ""


        if campus_match:

            matched_name = (
                campus_match.get(
                    "campus_name",
                    "",
                )
            )

            match_level = (
                campus_match.get(
                    "level",
                    "",
                )
            )


        analysis_display.append(
            {
                "Fila":
                    item.get(
                        "row_number",
                        "",
                    ),

                "Grupo":
                    item.get(
                        "group_number",
                        "",
                    ),

                "Organización":
                    item.get(
                        "organization_name",
                        "",
                    ),

                "Plantel":
                    item.get(
                        "campus_name",
                        "",
                    ),

                "Contacto":
                    item.get(
                        "contact_name",
                        "",
                    ),

                "Resultado":
                    item.get(
                        "status",
                        "",
                    ),

                "Coincidencia":
                    matched_name,

                "Nivel":
                    match_level,

                "Error crítico":
                    (
                        "Sí"
                        if item.get(
                            "critical_error",
                            False,
                        )
                        else "No"
                    ),

                "Observación":
                    item.get(
                        "message",
                        "",
                    ),
            }
        )


    analysis_df = pd.DataFrame(
        analysis_display
    )


    st.dataframe(
        dataframe_for_display(
            analysis_df
        ),
        width="stretch",
        hide_index=True,
    )


    # =====================================================
    # RESUMEN DEL ANÁLISIS
    # =====================================================

    total = len(
        analysis_results
    )


    new_count = sum(
        1

        for item
        in analysis_results

        if item.get(
            "status"
        ) == "NUEVO"
    )


    same_batch_count = sum(
        1

        for item
        in analysis_results

        if item.get(
            "status"
        ) == "MISMO_PLANTEL_LOTE"
    )


    existing_count = sum(
        1

        for item
        in analysis_results

        if item.get(
            "status"
        ) == "PLANTEL_EXISTENTE"
    )


    review_count = sum(
        1

        for item
        in analysis_results

        if item.get(
            "status"
        ) == "REQUIERE_REVISION"
    )


    critical_count = sum(
        1

        for item
        in analysis_results

        if item.get(
            "critical_error",
            False,
        )
    )


    m1, m2, m3, m4, m5, m6 = (
        st.columns(6)
    )


    with m1:

        st.metric(
            "Filas",
            total,
        )


    with m2:

        st.metric(
            "Planteles nuevos",
            new_count,
        )


    with m3:

        st.metric(
            "Filas mismo plantel",
            same_batch_count,
        )


    with m4:

        st.metric(
            "Plantel existente",
            existing_count,
        )


    with m5:

        st.metric(
            "Requieren revisión",
            review_count,
        )


    with m6:

        st.metric(
            "Errores críticos",
            critical_count,
        )


    # =====================================================
    # ADVERTENCIA
    # =====================================================

    if critical_count:

        st.error(
            (
                f"{critical_count} fila(s) contienen "
                "correos con formato inválido. "
                "La importación completa está bloqueada. "
                "Corrige el archivo o el mapeo y vuelve "
                "a construir la previsualización."
            )
        )

    elif review_count:

        st.warning(
            (
                f"{review_count} registros "
                "tienen coincidencias ambiguas "
                "o información insuficiente. "
                "Esos registros NO se escribirán "
                "en SQLite."
            )
        )

    else:

        st.success(
            "No se encontraron errores críticos "
            "ni registros ambiguos."
        )


    st.info(
        "Los planteles repetidos dentro de la misma "
        "hoja se agrupan. Un plantel se crea o resuelve "
        "una sola vez y puede recibir varios contactos."
    )


    # =====================================================
    # CONFIRMAR ESCRITURA
    # =====================================================

    confirm_import = st.checkbox(
        (
            "He revisado la previsualización "
            "y el resultado de coincidencias."
        ),
        disabled=(
            critical_count > 0
        ),
        key="confirm_import_checkbox",
    )


    if st.button(
        "Confirmar importación a SQLite",
        type="primary",
        width="stretch",
        disabled=(
            not confirm_import
            or critical_count > 0
        ),
        key="confirm_sqlite_import",
    ):

        with st.spinner(
            "Importando registros..."
        ):

            import_results = (
                import_safe_dataframe(
                    dataframe=preview,
                    analysis_results=(
                        analysis_results
                    ),
                    user_id=user_id,
                    source_filename=(
                        st.session_state.get(
                            "import_file_name",
                            "",
                        )
                    ),
                    source_sheet=(
                        st.session_state.get(
                            "import_selected_sheet",
                            "",
                        )
                    ),
                )
            )

        st.session_state[
            "import_results"
        ] = import_results

        st.rerun()


# =========================================================
# RESULTADO FINAL
# =========================================================

import_results = (
    st.session_state.get(
        "import_results"
    )
)


if import_results:

    st.divider()

    st.header(
        "Resultado de la importación"
    )


    result_df = pd.DataFrame(
        [
            {
                "Fila":
                    item.get(
                        "row_number",
                        "",
                    ),

                "Importado":
                    (
                        "Sí"
                        if item.get(
                            "imported",
                            False,
                        )
                        else "No"
                    ),

                "Acción":
                    item.get(
                        "action",
                        "",
                    ),

                "Resultado":
                    item.get(
                        "message",
                        "",
                    ),
            }

            for item
            in import_results
        ]
    )


    st.dataframe(
        dataframe_for_display(
            result_df
        ),
        width="stretch",
        hide_index=True,
    )


    imported_count = sum(
        1

        for item
        in import_results

        if item.get(
            "imported",
            False,
        )
    )


    omitted_count = (
        len(
            import_results
        )
        -
        imported_count
    )


    c1, c2 = (
        st.columns(2)
    )


    with c1:

        st.metric(
            "Procesados",
            imported_count,
        )


    with c2:

        st.metric(
            "No importados",
            omitted_count,
        )


    if imported_count:

        st.success(
            (
                f"{imported_count} registros "
                "fueron procesados en SQLite."
            )
        )


    if omitted_count:

        st.warning(
            (
                f"{omitted_count} registros "
                "quedaron pendientes de revisión."
            )
        )


    # =====================================================
    # RESUMEN DE IMPORTACIÓN
    # =====================================================

    st.divider()

    st.header(
        "Resumen de importación"
    )


    action_summary = (
        summarize_import_actions(
            import_results
        )
    )


    # =====================================================
    # INFORMACIÓN DEL ARCHIVO
    # =====================================================

    info1, info2 = (
        st.columns(2)
    )


    with info1:

        st.metric(
            "Archivo",
            st.session_state.get(
                "import_file_name",
                "",
            ),
        )


    with info2:

        st.metric(
            "Hoja",
            st.session_state.get(
                "import_selected_sheet",
                "",
            ),
        )


    # =====================================================
    # RESULTADO DEL LOTE
    # =====================================================

    st.subheader(
        "Resultado del lote"
    )


    r1, r2, r3, r4 = (
        st.columns(4)
    )


    with r1:

        st.metric(
            "Filas procesadas",
            action_summary.get(
                "processed",
                0,
            ),
        )


    with r2:

        st.metric(
            "Planteles creados",
            action_summary.get(
                "campuses_created",
                0,
            ),
        )


    with r3:

        st.metric(
            "Contactos creados",
            action_summary.get(
                "contacts_created",
                0,
            ),
        )


    with r4:

        st.metric(
            "Contactos existentes",
            action_summary.get(
                "contacts_existing",
                0,
            ),
        )


    r5, r6, r7 = (
        st.columns(3)
    )


    with r5:

        st.metric(
            "Contactos pendientes",
            action_summary.get(
                "contacts_pending",
                0,
            ),
        )


    with r6:

        st.metric(
            "No importados",
            action_summary.get(
                "not_imported",
                0,
            ),
        )


    with r7:

        st.metric(
            "Errores",
            action_summary.get(
                "errors",
                0,
            ),
        )


    # =====================================================
    # CONSTRUIR REFERENCIAS DE PLANTELES
    # =====================================================

    campus_references = []


    if preview is not None:

        for _, row in (
            preview.iterrows()
        ):

            organization_value = (
                safe_display_value(
                    row.get(
                        "organization_name",
                        "",
                    )
                )
            )

            campus_value = (
                safe_display_value(
                    row.get(
                        "campus_name",
                        "",
                    )
                )
            )


            if (
                organization_value
                and campus_value
            ):

                campus_references.append(
                    {
                        "organization_name":
                            organization_value,

                        "campus_name":
                            campus_value,
                    }
                )


    # =====================================================
    # VALIDACIÓN CONTRA SQLITE
    # =====================================================

    st.subheader(
        "Validación contra SQLite"
    )


    database_snapshot = (
        get_import_batch_snapshot(
            campus_references
        )
    )


    if database_snapshot:

        verified_campuses = sum(
            1

            for item
            in database_snapshot

            if item.get(
                "exists",
                False,
            )
        )


        missing_campuses = sum(
            1

            for item
            in database_snapshot

            if not item.get(
                "exists",
                False,
            )
        )


        total_contacts_sqlite = sum(
            item.get(
                "contacts",
                0,
            )

            for item
            in database_snapshot

            if item.get(
                "exists",
                False,
            )
        )


        v1, v2, v3 = (
            st.columns(3)
        )


        with v1:

            st.metric(
                "Planteles encontrados",
                verified_campuses,
            )


        with v2:

            st.metric(
                "Planteles no encontrados",
                missing_campuses,
            )


        with v3:

            st.metric(
                "Contactos actuales",
                total_contacts_sqlite,
            )


        snapshot_df = pd.DataFrame(
            [
                {
                    "Organización":
                        item.get(
                            "organization",
                            "",
                        ),

                    "Plantel":
                        item.get(
                            "campus",
                            "",
                        ),

                    "Existe en SQLite":
                        (
                            "Sí"
                            if item.get(
                                "exists",
                                False,
                            )
                            else "No"
                        ),

                    "Contactos":
                        item.get(
                            "contacts",
                            0,
                        ),

                    "Teléfonos institucionales":
                        item.get(
                            "phones",
                            0,
                        ),

                    "Correos institucionales":
                        item.get(
                            "emails",
                            0,
                        ),

                    "Estatus":
                        item.get(
                            "status",
                            "",
                        ),
                }

                for item
                in database_snapshot
            ]
        )


        st.dataframe(
            dataframe_for_display(
                snapshot_df
            ),
            width="stretch",
            hide_index=True,
        )


        if missing_campuses == 0:

            st.success(
                "Todos los planteles del lote "
                "fueron localizados en SQLite."
            )

        else:

            st.warning(
                (
                    f"{missing_campuses} planteles "
                    "del lote no pudieron localizarse "
                    "en SQLite."
                )
            )


    else:

        st.warning(
            "No fue posible construir "
            "la validación de planteles del lote."
        )