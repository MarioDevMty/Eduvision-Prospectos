from __future__ import annotations

import pandas as pd
import streamlit as st

from database.repositories.prospecting import (
    add_email,
    add_phone,
    analyze_campus_duplicates,
    analyze_contact_duplicates,
    create_campus,
    create_contact,
    find_organization_by_normalized_name,
    get_campus_detail,
    get_campuses,
    get_contact_detail,
    merge_campus_data,
    merge_contact_data,
)

from database.repositories.staging import (
    discard_staging_row,
    get_pending_import_rows,
    get_staging_detail,
    resolve_staging_row,
)

from services.normalization import (
    normalize_text,
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
    "validation_selected_id": None,
    "validation_merge_campus_id": None,
    "validation_merge_contact_id": None,
    "validation_message": None,
}


for key, value in DEFAULTS.items():

    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# UTILIDADES
# =========================================================

def safe_text(
    value,
) -> str:

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


def set_validation_message(
    message_type: str,
    text: str,
) -> None:

    st.session_state[
        "validation_message"
    ] = {
        "type": message_type,
        "text": text,
    }


def show_validation_message() -> None:

    message = st.session_state.get(
        "validation_message"
    )

    if not message:
        return

    if message["type"] == "success":

        st.success(
            message["text"]
        )

    elif message["type"] == "warning":

        st.warning(
            message["text"]
        )

    elif message["type"] == "error":

        st.error(
            message["text"]
        )

    else:

        st.info(
            message["text"]
        )

    st.session_state[
        "validation_message"
    ] = None


def clear_validation_state() -> None:

    st.session_state[
        "validation_merge_campus_id"
    ] = None

    st.session_state[
        "validation_merge_contact_id"
    ] = None


# =========================================================
# RESOLVER ORGANIZACIÓN
# =========================================================

def resolve_organization_id(
    organization_name: str,
) -> int | None:

    name = safe_text(
        organization_name
    )

    if not name:
        return None

    organization = (
        find_organization_by_normalized_name(
            normalize_text(
                name
            )
        )
    )

    if organization is None:
        return None

    return int(
        organization["id"]
    )


# =========================================================
# RESOLVER PLANTEL EXACTO
# =========================================================

def resolve_exact_campus_id(
    organization_id: int,
    campus_name: str,
) -> int | None:

    normalized_name = (
        normalize_text(
            campus_name
        )
    )

    if not normalized_name:
        return None

    campuses = get_campuses(
        organization_id
    )

    exact_matches = [
        row

        for row in campuses

        if normalize_text(
            safe_text(
                row["campus_name"]
            )
        )
        ==
        normalized_name
    ]

    if len(exact_matches) != 1:
        return None

    return int(
        exact_matches[0]["id"]
    )


# =========================================================
# CONSTRUIR DATOS DE PLANTEL
# =========================================================

def build_campus_data(
    data: dict,
) -> dict:

    return {
        "campus_name":
            safe_text(
                data.get(
                    "campus_name"
                )
            ),

        "campus_type":
            safe_text(
                data.get(
                    "campus_type"
                )
            )
            or
            "PLANTEL",

        "municipality":
            safe_text(
                data.get(
                    "municipality"
                )
            ),

        "state":
            safe_text(
                data.get(
                    "state"
                )
            ),

        "address":
            safe_text(
                data.get(
                    "address"
                )
            ),

        "phone":
            safe_text(
                data.get(
                    "institutional_phone"
                )
            ),

        "email":
            safe_text(
                data.get(
                    "institutional_email"
                )
            ),

        "status":
            safe_text(
                data.get(
                    "status"
                )
            )
            or
            "REQUIERE_REVISION",
    }


# =========================================================
# CONSTRUIR DATOS DE CONTACTO
# =========================================================

def build_contact_data(
    data: dict,
    campus_id: int,
) -> dict:

    direct_phone = safe_text(
        data.get(
            "contact_phone"
        )
    )

    whatsapp = safe_text(
        data.get(
            "contact_whatsapp"
        )
    )

    return {
        "campus_id":
            campus_id,

        "full_name":
            safe_text(
                data.get(
                    "contact_name"
                )
            ),

        "position":
            safe_text(
                data.get(
                    "contact_position"
                )
            ),

        "area":
            safe_text(
                data.get(
                    "contact_area"
                )
            ),

        "phone":
            direct_phone
            or
            whatsapp,

        "email":
            safe_text(
                data.get(
                    "contact_email"
                )
            ),

        "notes":
            safe_text(
                data.get(
                    "notes"
                )
            ),

        "status":
            safe_text(
                data.get(
                    "status"
                )
            )
            or
            "REQUIERE_REVISION",
    }


# =========================================================
# CREAR PLANTEL DESDE STAGING
# =========================================================

def create_campus_from_staging(
    staging_id: int,
    organization_id: int,
    incoming: dict,
) -> None:

    campus_id = create_campus(
        organization_id=organization_id,
        campus_name=(
            incoming[
                "campus_name"
            ]
        ),
        campus_type=(
            incoming[
                "campus_type"
            ]
        ),
        municipality=(
            incoming[
                "municipality"
            ]
        ),
        state=(
            incoming[
                "state"
            ]
        ),
        address=(
            incoming[
                "address"
            ]
        ),
        status=(
            incoming[
                "status"
            ]
        ),
        user_id=user_id,
    )


    if incoming["phone"]:

        add_phone(
            entity_type="CAMPUS",
            entity_id=campus_id,
            phone=(
                incoming[
                    "phone"
                ]
            ),
            phone_type="INSTITUCIONAL",
            user_id=user_id,
            is_primary=True,
        )


    if incoming["email"]:

        add_email(
            entity_type="CAMPUS",
            entity_id=campus_id,
            email=(
                incoming[
                    "email"
                ]
            ),
            email_type="INSTITUCIONAL",
            user_id=user_id,
            is_primary=True,
        )


    resolve_staging_row(
        staging_id,
        user_id,
    )


# =========================================================
# CREAR CONTACTO DESDE STAGING
# =========================================================

def create_contact_from_staging(
    staging_id: int,
    incoming: dict,
) -> None:

    contact_id = create_contact(
        campus_id=(
            incoming[
                "campus_id"
            ]
        ),
        full_name=(
            incoming[
                "full_name"
            ]
        ),
        position=(
            incoming[
                "position"
            ]
        ),
        area=(
            incoming[
                "area"
            ]
        ),
        notes=(
            incoming[
                "notes"
            ]
        ),
        status=(
            incoming[
                "status"
            ]
        ),
        user_id=user_id,
    )


    if incoming["phone"]:

        add_phone(
            entity_type="CONTACT",
            entity_id=contact_id,
            phone=(
                incoming[
                    "phone"
                ]
            ),
            phone_type="DIRECTO",
            user_id=user_id,
            is_primary=True,
        )


    if incoming["email"]:

        add_email(
            entity_type="CONTACT",
            entity_id=contact_id,
            email=(
                incoming[
                    "email"
                ]
            ),
            email_type="DIRECTO",
            user_id=user_id,
            is_primary=True,
        )


    resolve_staging_row(
        staging_id,
        user_id,
    )


# =========================================================
# CABECERA
# =========================================================

st.title(
    "Validación"
)

st.caption(
    "Resuelve los registros ambiguos antes de "
    "incorporarlos o fusionarlos con la base maestra."
)


show_validation_message()


# =========================================================
# OBTENER PENDIENTES
# =========================================================

try:

    pending_rows = (
        get_pending_import_rows()
    )

except Exception as exc:

    st.error(
        "No fue posible consultar los pendientes."
    )

    st.exception(
        exc
    )

    st.stop()


st.metric(
    "Pendientes de validación",
    len(pending_rows),
)


if not pending_rows:

    st.success(
        "No existen registros pendientes."
    )

    st.stop()


# =========================================================
# TABLA GENERAL
# =========================================================

display_rows = []


for item in pending_rows:

    review_type = safe_text(
        item.get(
            "review_type"
        )
    )

    review_label = {
        "CAMPUS":
            "Plantel",

        "CONTACT":
            "Contacto",

    }.get(
        review_type,
        review_type,
    )


    display_rows.append(
        {
            "ID":
                item.get(
                    "id"
                ),

            "Tipo":
                review_label,

            "Archivo":
                item.get(
                    "source_filename"
                ),

            "Hoja":
                item.get(
                    "source_sheet"
                ),

            "Fila":
                item.get(
                    "source_row"
                ),

            "Organización":
                item.get(
                    "organization_name"
                ),

            "Plantel":
                item.get(
                    "campus_name"
                ),

            "Contacto":
                item.get(
                    "contact_name"
                ),

            "Motivo":
                item.get(
                    "reason"
                ),
        }
    )


st.dataframe(
    pd.DataFrame(
        display_rows
    ),
    width="stretch",
    hide_index=True,
)


# =========================================================
# SELECCIÓN
# =========================================================

st.divider()

st.subheader(
    "Revisar registro"
)


options = {}


for item in pending_rows:

    label = (
        f"Fila {item.get('source_row', '')} · "
        f"{item.get('review_type', '')} · "
        f"{item.get('campus_name') or 'Sin plantel'} · "
        f"{item.get('contact_name') or 'Sin contacto'}"
    )

    options[
        label
    ] = item["id"]


selected_label = st.selectbox(
    "Registro pendiente",
    options=list(
        options.keys()
    ),
    width="stretch",
)


if not selected_label:
    st.stop()


selected_id = (
    options[
        selected_label
    ]
)


if (
    st.session_state.get(
        "validation_selected_id"
    )
    !=
    selected_id
):

    st.session_state[
        "validation_selected_id"
    ] = selected_id

    clear_validation_state()


detail = (
    get_staging_detail(
        selected_id
    )
)


if detail is None:

    st.error(
        "El registro ya no está disponible."
    )

    st.stop()


data = detail.get(
    "data",
    {},
)


review_type = safe_text(
    detail.get(
        "review_type"
    )
)


# =========================================================
# ORIGEN
# =========================================================

st.divider()

o1, o2, o3, o4 = (
    st.columns(4)
)


with o1:

    st.write(
        "**Archivo**"
    )

    st.write(
        detail.get(
            "source_filename"
        )
        or
        "—"
    )


with o2:

    st.write(
        "**Hoja**"
    )

    st.write(
        detail.get(
            "source_sheet"
        )
        or
        "—"
    )


with o3:

    st.write(
        "**Fila**"
    )

    st.write(
        detail.get(
            "source_row"
        )
        or
        "—"
    )


with o4:

    st.write(
        "**Tipo**"
    )

    st.write(
        review_type
        or
        "—"
    )


st.warning(
    detail.get(
        "reason"
    )
    or
    "Requiere revisión manual."
)


# =========================================================
# DATOS RECIBIDOS
# =========================================================

st.subheader(
    "Datos recibidos"
)


if data:

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Campo":
                        field,

                    "Valor":
                        value,
                }

                for field, value
                in data.items()
            ]
        ),
        width="stretch",
        hide_index=True,
    )


# =========================================================
# RESOLVER PLANTEL
# =========================================================

if review_type == "CAMPUS":

    st.divider()

    st.header(
        "Resolver plantel"
    )


    incoming = (
        build_campus_data(
            data
        )
    )


    organization_name = safe_text(
        data.get(
            "organization_name"
        )
    )


    organization_id = (
        resolve_organization_id(
            organization_name
        )
    )


    if organization_id is None:

        st.error(
            "La organización no pudo resolverse "
            "de forma exacta."
        )

        st.stop()


    if not incoming[
        "campus_name"
    ]:

        st.error(
            "El registro no tiene nombre de plantel."
        )

        st.stop()


    candidates = (
        analyze_campus_duplicates(
            organization_id=(
                organization_id
            ),
            campus_name=(
                incoming[
                    "campus_name"
                ]
            ),
            municipality=(
                incoming[
                    "municipality"
                ]
            ),
            phone=(
                incoming[
                    "phone"
                ]
            ),
        )
    )


    st.write(
        "**Plantel recibido:** "
        f"{incoming['campus_name']}"
    )


    if candidates:

        st.subheader(
            "Posibles coincidencias"
        )


        st.dataframe(
            pd.DataFrame(
                candidates
            ),
            width="stretch",
            hide_index=True,
        )


        campus_options = {
            (
                f"{candidate['campus_name']} "
                f"— {candidate.get('municipality') or 'Sin municipio'} "
                f"— {candidate.get('level') or ''}"
            ):
            candidate["id"]

            for candidate
            in candidates
        }


        selected_candidate = (
            st.selectbox(
                "Comparar con",
                options=list(
                    campus_options.keys()
                ),
                key=(
                    f"validation_campus_candidate_"
                    f"{selected_id}"
                ),
            )
        )


        candidate_id = (
            campus_options[
                selected_candidate
            ]
        )


        c1, c2, c3 = (
            st.columns(3)
        )


        with c1:

            if st.button(
                "Es el mismo plantel",
                type="primary",
                width="stretch",
                key=(
                    f"same_campus_"
                    f"{selected_id}"
                ),
            ):

                st.session_state[
                    "validation_merge_campus_id"
                ] = candidate_id

                st.rerun()


        with c2:

            if st.button(
                "Es otro plantel",
                width="stretch",
                key=(
                    f"different_campus_"
                    f"{selected_id}"
                ),
            ):

                create_campus_from_staging(
                    selected_id,
                    organization_id,
                    incoming,
                )

                set_validation_message(
                    "success",
                    "Plantel nuevo creado."
                )

                st.rerun()


        with c3:

            st.button(
                "Mantener pendiente",
                width="stretch",
                key=(
                    f"keep_campus_"
                    f"{selected_id}"
                ),
            )


    else:

        st.success(
            "No se encontraron coincidencias."
        )


        if st.button(
            "Crear como plantel nuevo",
            type="primary",
            width="stretch",
            key=(
                f"create_campus_"
                f"{selected_id}"
            ),
        ):

            create_campus_from_staging(
                selected_id,
                organization_id,
                incoming,
            )

            set_validation_message(
                "success",
                "Plantel creado."
            )

            st.rerun()


    # =====================================================
    # FUSIÓN PLANTEL
    # =====================================================

    merge_campus_id = (
        st.session_state.get(
            "validation_merge_campus_id"
        )
    )


    if merge_campus_id:

        existing = (
            get_campus_detail(
                merge_campus_id
            )
        )


        st.divider()

        st.subheader(
            "Fusión controlada"
        )


        comparison = pd.DataFrame(
            [
                {
                    "Campo": "Nombre",
                    "BD actual":
                        existing[
                            "campus_name"
                        ],
                    "Dato recibido":
                        incoming[
                            "campus_name"
                        ],
                },
                {
                    "Campo": "Tipo",
                    "BD actual":
                        existing[
                            "campus_type"
                        ],
                    "Dato recibido":
                        incoming[
                            "campus_type"
                        ],
                },
                {
                    "Campo": "Municipio",
                    "BD actual":
                        existing[
                            "municipality"
                        ],
                    "Dato recibido":
                        incoming[
                            "municipality"
                        ],
                },
                {
                    "Campo": "Estado",
                    "BD actual":
                        existing[
                            "state"
                        ],
                    "Dato recibido":
                        incoming[
                            "state"
                        ],
                },
                {
                    "Campo": "Domicilio",
                    "BD actual":
                        existing[
                            "address"
                        ],
                    "Dato recibido":
                        incoming[
                            "address"
                        ],
                },
                {
                    "Campo": "Teléfono",
                    "BD actual":
                        ", ".join(
                            existing[
                                "phones"
                            ]
                        ),
                    "Dato recibido":
                        incoming[
                            "phone"
                        ],
                },
                {
                    "Campo": "Correo",
                    "BD actual":
                        ", ".join(
                            existing[
                                "emails"
                            ]
                        ),
                    "Dato recibido":
                        incoming[
                            "email"
                        ],
                },
            ]
        )


        st.dataframe(
            comparison,
            width="stretch",
            hide_index=True,
        )


        selected_fields = []


        if st.checkbox(
            "Usar tipo recibido",
            key=(
                f"merge_campus_type_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "campus_type"
            )


        if st.checkbox(
            "Usar municipio recibido",
            key=(
                f"merge_campus_municipality_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "municipality"
            )


        if st.checkbox(
            "Usar estado recibido",
            key=(
                f"merge_campus_state_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "state"
            )


        if st.checkbox(
            "Usar domicilio recibido",
            key=(
                f"merge_campus_address_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "address"
            )


        save_alias = st.checkbox(
            "Guardar nombre recibido como alias",
            value=True,
            key=(
                f"merge_campus_alias_"
                f"{selected_id}"
            ),
        )


        st.info(
            "Teléfono y correo no se sustituyen. "
            "Si son nuevos, se agregan."
        )


        if st.button(
            "Confirmar fusión",
            type="primary",
            width="stretch",
            key=(
                f"confirm_campus_merge_"
                f"{selected_id}"
            ),
        ):

            merge_campus_data(
                campus_id=(
                    merge_campus_id
                ),
                incoming_data=incoming,
                selected_fields=(
                    selected_fields
                ),
                user_id=user_id,
                save_alias=(
                    save_alias
                ),
            )


            resolve_staging_row(
                selected_id,
                user_id,
            )


            clear_validation_state()


            set_validation_message(
                "success",
                (
                    "Plantel fusionado. "
                    "El pendiente quedó resuelto."
                ),
            )


            st.rerun()


# =========================================================
# RESOLVER CONTACTO
# =========================================================

elif review_type == "CONTACT":

    st.divider()

    st.header(
        "Resolver contacto"
    )


    organization_id = (
        resolve_organization_id(
            data.get(
                "organization_name",
                "",
            )
        )
    )


    if organization_id is None:

        st.error(
            "No se pudo resolver la organización."
        )

        st.stop()


    campus_id = (
        resolve_exact_campus_id(
            organization_id,
            data.get(
                "campus_name",
                "",
            ),
        )
    )


    if campus_id is None:

        st.error(
            "No se pudo resolver exactamente "
            "el plantel del contacto."
        )

        st.stop()


    incoming = (
        build_contact_data(
            data,
            campus_id,
        )
    )


    if not incoming[
        "full_name"
    ]:

        st.error(
            "El contacto no contiene nombre."
        )

        st.stop()


    candidates = (
        analyze_contact_duplicates(
            campus_id=campus_id,
            full_name=(
                incoming[
                    "full_name"
                ]
            ),
            phone=(
                incoming[
                    "phone"
                ]
            ),
            email=(
                incoming[
                    "email"
                ]
            ),
        )
    )


    st.write(
        "**Contacto recibido:** "
        f"{incoming['full_name']}"
    )


    if candidates:

        contact_options = {
            (
                f"{candidate['full_name']} "
                f"— {candidate.get('position') or 'Sin puesto'} "
                f"— {candidate.get('level')}"
            ):
            candidate["id"]

            for candidate
            in candidates
        }


        selected_contact = (
            st.selectbox(
                "Comparar con",
                list(
                    contact_options.keys()
                ),
                key=(
                    f"contact_candidate_"
                    f"{selected_id}"
                ),
            )
        )


        selected_contact_id = (
            contact_options[
                selected_contact
            ]
        )


        st.dataframe(
            pd.DataFrame(
                candidates
            ),
            width="stretch",
            hide_index=True,
        )


        c1, c2, c3 = (
            st.columns(3)
        )


        with c1:

            if st.button(
                "Es la misma persona",
                type="primary",
                width="stretch",
                key=(
                    f"same_contact_"
                    f"{selected_id}"
                ),
            ):

                st.session_state[
                    "validation_merge_contact_id"
                ] = selected_contact_id

                st.rerun()


        with c2:

            if st.button(
                "Es otra persona",
                width="stretch",
                key=(
                    f"different_contact_"
                    f"{selected_id}"
                ),
            ):

                create_contact_from_staging(
                    selected_id,
                    incoming,
                )

                set_validation_message(
                    "success",
                    "Contacto nuevo creado."
                )

                st.rerun()


        with c3:

            st.button(
                "Mantener pendiente",
                width="stretch",
                key=(
                    f"keep_contact_"
                    f"{selected_id}"
                ),
            )


    else:

        st.success(
            "No se encontraron contactos similares."
        )


        if st.button(
            "Crear como contacto nuevo",
            type="primary",
            width="stretch",
            key=(
                f"create_contact_"
                f"{selected_id}"
            ),
        ):

            create_contact_from_staging(
                selected_id,
                incoming,
            )

            set_validation_message(
                "success",
                "Contacto creado."
            )

            st.rerun()


    # =====================================================
    # FUSIÓN CONTACTO
    # =====================================================

    merge_contact_id = (
        st.session_state.get(
            "validation_merge_contact_id"
        )
    )


    if merge_contact_id:

        existing = (
            get_contact_detail(
                merge_contact_id
            )
        )


        st.divider()

        st.subheader(
            "Fusión controlada de contacto"
        )


        comparison = pd.DataFrame(
            [
                {
                    "Campo": "Nombre",
                    "BD actual":
                        existing[
                            "full_name"
                        ],
                    "Dato recibido":
                        incoming[
                            "full_name"
                        ],
                },
                {
                    "Campo": "Puesto",
                    "BD actual":
                        existing[
                            "position"
                        ],
                    "Dato recibido":
                        incoming[
                            "position"
                        ],
                },
                {
                    "Campo": "Área",
                    "BD actual":
                        existing[
                            "area"
                        ],
                    "Dato recibido":
                        incoming[
                            "area"
                        ],
                },
                {
                    "Campo": "Teléfono",
                    "BD actual":
                        ", ".join(
                            existing[
                                "phones"
                            ]
                        ),
                    "Dato recibido":
                        incoming[
                            "phone"
                        ],
                },
                {
                    "Campo": "Correo",
                    "BD actual":
                        ", ".join(
                            existing[
                                "emails"
                            ]
                        ),
                    "Dato recibido":
                        incoming[
                            "email"
                        ],
                },
            ]
        )


        st.dataframe(
            comparison,
            width="stretch",
            hide_index=True,
        )


        selected_fields = []


        if st.checkbox(
            "Usar nombre recibido",
            key=(
                f"merge_contact_name_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "full_name"
            )


        if st.checkbox(
            "Usar puesto recibido",
            key=(
                f"merge_contact_position_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "position"
            )


        if st.checkbox(
            "Usar área recibida",
            key=(
                f"merge_contact_area_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "area"
            )


        if st.checkbox(
            "Usar notas recibidas",
            key=(
                f"merge_contact_notes_"
                f"{selected_id}"
            ),
        ):

            selected_fields.append(
                "notes"
            )


        st.info(
            "Teléfono y correo se agregan si son nuevos; "
            "no sustituyen los existentes."
        )


        if st.button(
            "Confirmar fusión",
            type="primary",
            width="stretch",
            key=(
                f"confirm_contact_merge_"
                f"{selected_id}"
            ),
        ):

            merge_contact_data(
                contact_id=(
                    merge_contact_id
                ),
                incoming_data=incoming,
                selected_fields=(
                    selected_fields
                ),
                user_id=user_id,
            )


            resolve_staging_row(
                selected_id,
                user_id,
            )


            clear_validation_state()


            set_validation_message(
                "success",
                (
                    "Contacto fusionado. "
                    "El pendiente quedó resuelto."
                ),
            )


            st.rerun()


else:

    st.error(
        "Tipo de revisión no reconocido."
    )


# =========================================================
# DESCARTAR
# =========================================================

st.divider()

st.subheader(
    "Descartar registro"
)


st.caption(
    "El registro no se elimina físicamente. "
    "Su estado cambia a DESCARTADO."
)


confirm_discard = (
    st.checkbox(
        "Confirmo que este registro debe descartarse",
        key=(
            f"confirm_discard_"
            f"{selected_id}"
        ),
    )
)


if st.button(
    "Descartar registro",
    width="stretch",
    disabled=(
        not confirm_discard
    ),
    key=(
        f"discard_"
        f"{selected_id}"
    ),
):

    discard_staging_row(
        selected_id,
        user_id,
    )


    clear_validation_state()


    set_validation_message(
        "success",
        "Registro marcado como DESCARTADO.",
    )


    st.rerun()