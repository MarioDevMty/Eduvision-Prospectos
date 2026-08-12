import pandas as pd
import streamlit as st

from database.repositories.prospecting import (
    add_email,
    add_phone,
    analyze_campus_duplicates,
    analyze_contact_duplicates,
    create_campus,
    create_contact,
    create_organization,
    get_campus_detail,
    get_campuses,
    get_contact_detail,
    get_contacts,
    get_organizations,
    merge_campus_data,
    merge_contact_data,
)

from database.repositories.data_admin import (
    add_validated_email,
    deactivate_email,
    get_campus_management_detail,
    get_organization_campuses,
    get_organization_management_summary,
    reactivate_email,
    reset_organization_data,
    set_primary_email,
    update_campus,
    update_email,
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
        "No se encontró el usuario "
        "de la sesión."
    )

    st.stop()


# =========================================================
# SESSION STATE
# =========================================================

DEFAULTS = {
    "db_message": None,

    "pending_campus": None,
    "pending_campus_candidates": None,
    "merge_campus_id": None,

    "pending_contact": None,
    "pending_contact_candidates": None,
    "merge_contact_id": None,
}


for key, value in DEFAULTS.items():

    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# UTILIDADES UI
# =========================================================

def set_message(
    message_type: str,
    text: str,
) -> None:

    st.session_state[
        "db_message"
    ] = {
        "type":
            message_type,

        "text":
            text,
    }


def show_message() -> None:

    message = st.session_state.get(
        "db_message"
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
        "db_message"
    ] = None


def clear_pending_campus() -> None:

    st.session_state[
        "pending_campus"
    ] = None

    st.session_state[
        "pending_campus_candidates"
    ] = None

    st.session_state[
        "merge_campus_id"
    ] = None


def clear_pending_contact() -> None:

    st.session_state[
        "pending_contact"
    ] = None

    st.session_state[
        "pending_contact_candidates"
    ] = None

    st.session_state[
        "merge_contact_id"
    ] = None


# =========================================================
# GUARDAR PLANTEL NUEVO
# =========================================================

def save_pending_campus() -> None:

    data = st.session_state.get(
        "pending_campus"
    )

    if not data:
        return

    campus_id = create_campus(
        organization_id=(
            data["organization_id"]
        ),
        campus_name=(
            data["campus_name"]
        ),
        campus_type=(
            data["campus_type"]
        ),
        municipality=(
            data["municipality"]
        ),
        state=(
            data["state"]
        ),
        address=(
            data["address"]
        ),
        status=(
            data["status"]
        ),
        user_id=user_id,
    )

    if data["phone"].strip():

        add_phone(
            "CAMPUS",
            campus_id,
            data["phone"],
            "INSTITUCIONAL",
            user_id,
            True,
        )

    if data["email"].strip():

        add_email(
            "CAMPUS",
            campus_id,
            data["email"],
            "INSTITUCIONAL",
            user_id,
            True,
        )

    name = data[
        "campus_name"
    ]

    clear_pending_campus()

    set_message(
        "success",
        (
            "Plantel registrado: "
            f"{name}"
        ),
    )

    st.rerun()


# =========================================================
# GUARDAR CONTACTO NUEVO
# =========================================================

def save_pending_contact() -> None:

    data = st.session_state.get(
        "pending_contact"
    )

    if not data:
        return

    contact_id = create_contact(
        campus_id=(
            data["campus_id"]
        ),
        full_name=(
            data["full_name"]
        ),
        position=(
            data["position"]
        ),
        area=(
            data["area"]
        ),
        notes=(
            data["notes"]
        ),
        status=(
            data["status"]
        ),
        user_id=user_id,
    )

    if data["phone"].strip():

        add_phone(
            "CONTACT",
            contact_id,
            data["phone"],
            "DIRECTO",
            user_id,
            True,
        )

    if data["email"].strip():

        add_email(
            "CONTACT",
            contact_id,
            data["email"],
            "DIRECTO",
            user_id,
            True,
        )

    name = data[
        "full_name"
    ]

    clear_pending_contact()

    set_message(
        "success",
        (
            "Contacto registrado: "
            f"{name}"
        ),
    )

    st.rerun()


# =========================================================
# CABECERA
# =========================================================

st.title(
    "Base de datos"
)

show_message()


(
    tab_admin,
    tab_consulta,
    tab_organizacion,
    tab_plantel,
    tab_contacto,
) = st.tabs(
    [
        "Administrar",
        "Consultar",
        "Nueva organización",
        "Nuevo plantel / unidad",
        "Nuevo contacto",
    ]
)



# =========================================================
# ADMINISTRAR
# =========================================================

with tab_admin:

    st.subheader(
        "Administrar instituciones"
    )

    st.caption(
        "Corrige planteles y correos o reinicia "
        "una institución mediante baja lógica."
    )

    admin_organizations = get_organizations()

    if not admin_organizations:

        st.info(
            "No existen organizaciones."
        )

    else:

        admin_org_options = {
            (
                f"{row['official_name']} "
                f"— {row['subsystem'] or 'Sin subsistema'}"
            ):
                int(row["id"])
            for row in admin_organizations
        }

        admin_org_label = st.selectbox(
            "Institución",
            options=list(
                admin_org_options.keys()
            ),
            key="admin_organization_selector",
        )

        admin_org_id = (
            admin_org_options[
                admin_org_label
            ]
        )

        summary = (
            get_organization_management_summary(
                admin_org_id
            )
        )

        if summary is None:

            st.error(
                "No fue posible cargar la institución."
            )

        else:

            metric1, metric2, metric3, metric4 = (
                st.columns(4)
            )

            metric1.metric(
                "Planteles activos",
                summary["campuses_active"],
            )

            metric2.metric(
                "Planteles en baja",
                summary["campuses_inactive"],
            )

            metric3.metric(
                "Correos activos",
                summary["active_emails"],
            )

            metric4.metric(
                "Correos inactivos",
                summary["inactive_emails"],
            )

            campuses_admin = (
                get_organization_campuses(
                    admin_org_id,
                    include_inactive=True,
                )
            )

            st.divider()

            if not campuses_admin:

                st.info(
                    "La institución no tiene planteles."
                )

            else:

                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "ID": row["id"],
                                "Plantel":
                                    row["campus_name"],
                                "Municipio":
                                    row["municipality"],
                                "Correos activos":
                                    row["active_emails"]
                                    or "",
                                "Estatus":
                                    row["status"],
                            }
                            for row in campuses_admin
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )

                campus_options = {
                    (
                        f"{row['campus_name']} "
                        f"— {row['municipality'] or ''} "
                        f"[{row['status']}]"
                    ):
                        int(row["id"])
                    for row in campuses_admin
                }

                campus_label = st.selectbox(
                    "Plantel para administrar",
                    options=list(
                        campus_options.keys()
                    ),
                    key="admin_campus_selector",
                )

                campus_id = campus_options[
                    campus_label
                ]

                detail = (
                    get_campus_management_detail(
                        campus_id
                    )
                )

                if detail:

                    with st.expander(
                        "Editar datos del plantel"
                    ):

                        with st.form(
                            f"admin_campus_form_{campus_id}"
                        ):

                            edit_name = st.text_input(
                                "Nombre",
                                value=(
                                    detail[
                                        "campus_name"
                                    ]
                                    or ""
                                ),
                            )

                            edit_type = st.text_input(
                                "Tipo",
                                value=(
                                    detail[
                                        "campus_type"
                                    ]
                                    or ""
                                ),
                            )

                            edit_code = st.text_input(
                                "Clave / código",
                                value=(
                                    detail[
                                        "campus_code"
                                    ]
                                    or ""
                                ),
                            )

                            edit_address = st.text_area(
                                "Domicilio",
                                value=(
                                    detail["address"]
                                    or ""
                                ),
                            )

                            edit_neighborhood = (
                                st.text_input(
                                    "Colonia",
                                    value=(
                                        detail[
                                            "neighborhood"
                                        ]
                                        or ""
                                    ),
                                )
                            )

                            edit_postal_code = (
                                st.text_input(
                                    "Código postal",
                                    value=(
                                        detail[
                                            "postal_code"
                                        ]
                                        or ""
                                    ),
                                )
                            )

                            edit_municipality = (
                                st.text_input(
                                    "Municipio",
                                    value=(
                                        detail[
                                            "municipality"
                                        ]
                                        or ""
                                    ),
                                )
                            )

                            edit_state = st.text_input(
                                "Estado",
                                value=(
                                    detail["state"]
                                    or ""
                                ),
                            )

                            edit_website = st.text_input(
                                "Sitio web",
                                value=(
                                    detail["website"]
                                    or ""
                                ),
                            )

                            campus_statuses = [
                                "REQUIERE_REVISION",
                                "PENDIENTE",
                                "INCOMPLETO",
                                "VALIDADO",
                                "BAJA",
                            ]

                            current_status = (
                                detail["status"]
                                if detail["status"]
                                in campus_statuses
                                else
                                "REQUIERE_REVISION"
                            )

                            edit_status = st.selectbox(
                                "Estatus",
                                options=campus_statuses,
                                index=(
                                    campus_statuses.index(
                                        current_status
                                    )
                                ),
                            )

                            save_campus = (
                                st.form_submit_button(
                                    "Guardar cambios",
                                    type="primary",
                                    width="stretch",
                                )
                            )

                        if save_campus:

                            try:

                                update_campus(
                                    campus_id=campus_id,
                                    campus_name=(
                                        edit_name
                                    ),
                                    campus_type=(
                                        edit_type
                                    ),
                                    campus_code=(
                                        edit_code
                                    ),
                                    address=(
                                        edit_address
                                    ),
                                    neighborhood=(
                                        edit_neighborhood
                                    ),
                                    postal_code=(
                                        edit_postal_code
                                    ),
                                    municipality=(
                                        edit_municipality
                                    ),
                                    state=edit_state,
                                    website=(
                                        edit_website
                                    ),
                                    status=edit_status,
                                    user_id=user_id,
                                )

                                set_message(
                                    "success",
                                    (
                                        "Plantel actualizado "
                                        "correctamente."
                                    ),
                                )

                                st.rerun()

                            except Exception as exc:

                                st.error(
                                    str(exc)
                                )

                    with st.expander(
                        "Administrar correos",
                        expanded=True,
                    ):

                        email_rows = detail[
                            "emails"
                        ]

                        if email_rows:

                            st.dataframe(
                                pd.DataFrame(
                                    [
                                        {
                                            "ID":
                                                row["id"],
                                            "Correo":
                                                row["email"],
                                            "Tipo":
                                                row[
                                                    "email_type"
                                                ],
                                            "Principal":
                                                bool(
                                                    row[
                                                        "is_primary"
                                                    ]
                                                ),
                                            "Estatus":
                                                row["status"],
                                        }
                                        for row in email_rows
                                    ]
                                ),
                                hide_index=True,
                                width="stretch",
                            )

                            email_options = {
                                (
                                    f"{row['email']} "
                                    f"[{row['status']}]"
                                ):
                                    row
                                for row in email_rows
                            }

                            email_label = (
                                st.selectbox(
                                    "Correo para editar",
                                    options=list(
                                        email_options.keys()
                                    ),
                                    key=(
                                        f"admin_email_"
                                        f"{campus_id}"
                                    ),
                                )
                            )

                            selected_email = (
                                email_options[
                                    email_label
                                ]
                            )

                            email_id = int(
                                selected_email["id"]
                            )

                            with st.form(
                                f"edit_email_{email_id}"
                            ):

                                edited_email = (
                                    st.text_input(
                                        "Correo",
                                        value=(
                                            selected_email[
                                                "email"
                                            ]
                                        ),
                                    )
                                )

                                edited_type = (
                                    st.text_input(
                                        "Tipo",
                                        value=(
                                            selected_email[
                                                "email_type"
                                            ]
                                            or
                                            "INSTITUCIONAL"
                                        ),
                                    )
                                )

                                edited_primary = (
                                    st.checkbox(
                                        "Principal",
                                        value=bool(
                                            selected_email[
                                                "is_primary"
                                            ]
                                        ),
                                    )
                                )

                                edited_status = (
                                    st.selectbox(
                                        "Estatus",
                                        options=[
                                            "ACTIVO",
                                            "INACTIVO",
                                        ],
                                        index=(
                                            0
                                            if selected_email[
                                                "status"
                                            ]
                                            == "ACTIVO"
                                            else 1
                                        ),
                                    )
                                )

                                save_email = (
                                    st.form_submit_button(
                                        "Guardar correo",
                                        type="primary",
                                        width="stretch",
                                    )
                                )

                            if save_email:

                                try:

                                    update_email(
                                        email_id=email_id,
                                        email_address=(
                                            edited_email
                                        ),
                                        email_type=(
                                            edited_type
                                        ),
                                        is_primary=(
                                            edited_primary
                                        ),
                                        status=(
                                            edited_status
                                        ),
                                        user_id=user_id,
                                    )

                                    set_message(
                                        "success",
                                        "Correo actualizado.",
                                    )

                                    st.rerun()

                                except Exception as exc:

                                    st.error(
                                        str(exc)
                                    )

                            deactivate_reason = (
                                st.text_input(
                                    "Motivo para desactivar",
                                    key=(
                                        f"deactivate_reason_"
                                        f"{email_id}"
                                    ),
                                )
                            )

                            action1, action2, action3 = (
                                st.columns(3)
                            )

                            with action1:

                                if st.button(
                                    "Desactivar",
                                    width="stretch",
                                    disabled=(
                                        selected_email[
                                            "status"
                                        ]
                                        != "ACTIVO"
                                    ),
                                    key=(
                                        f"deactivate_"
                                        f"{email_id}"
                                    ),
                                ):

                                    try:

                                        deactivate_email(
                                            email_id=(
                                                email_id
                                            ),
                                            user_id=(
                                                user_id
                                            ),
                                            reason=(
                                                deactivate_reason
                                            ),
                                        )

                                        set_message(
                                            "success",
                                            (
                                                "Correo "
                                                "desactivado."
                                            ),
                                        )

                                        st.rerun()

                                    except Exception as exc:

                                        st.error(
                                            str(exc)
                                        )

                            with action2:

                                if st.button(
                                    "Reactivar",
                                    width="stretch",
                                    disabled=(
                                        selected_email[
                                            "status"
                                        ]
                                        == "ACTIVO"
                                    ),
                                    key=(
                                        f"reactivate_"
                                        f"{email_id}"
                                    ),
                                ):

                                    try:

                                        reactivate_email(
                                            email_id=(
                                                email_id
                                            ),
                                            user_id=(
                                                user_id
                                            ),
                                        )

                                        set_message(
                                            "success",
                                            (
                                                "Correo "
                                                "reactivado."
                                            ),
                                        )

                                        st.rerun()

                                    except Exception as exc:

                                        st.error(
                                            str(exc)
                                        )

                            with action3:

                                if st.button(
                                    "Hacer principal",
                                    width="stretch",
                                    disabled=(
                                        selected_email[
                                            "status"
                                        ]
                                        != "ACTIVO"
                                    ),
                                    key=(
                                        f"primary_"
                                        f"{email_id}"
                                    ),
                                ):

                                    try:

                                        set_primary_email(
                                            email_id=(
                                                email_id
                                            ),
                                            user_id=(
                                                user_id
                                            ),
                                        )

                                        set_message(
                                            "success",
                                            (
                                                "Correo principal "
                                                "actualizado."
                                            ),
                                        )

                                        st.rerun()

                                    except Exception as exc:

                                        st.error(
                                            str(exc)
                                        )

                        else:

                            st.info(
                                "El plantel no tiene correos."
                            )

                        st.markdown(
                            "#### Agregar correo"
                        )

                        with st.form(
                            f"add_email_{campus_id}"
                        ):

                            new_email = st.text_input(
                                "Nuevo correo"
                            )

                            new_type = st.text_input(
                                "Tipo",
                                value="INSTITUCIONAL",
                            )

                            new_primary = st.checkbox(
                                "Marcar como principal"
                            )

                            add_email_button = (
                                st.form_submit_button(
                                    "Agregar correo",
                                    type="primary",
                                    width="stretch",
                                )
                            )

                        if add_email_button:

                            try:

                                add_validated_email(
                                    campus_id=(
                                        campus_id
                                    ),
                                    email_address=(
                                        new_email
                                    ),
                                    email_type=(
                                        new_type
                                    ),
                                    is_primary=(
                                        new_primary
                                    ),
                                    user_id=user_id,
                                )

                                set_message(
                                    "success",
                                    "Correo agregado.",
                                )

                                st.rerun()

                            except Exception as exc:

                                st.error(
                                    str(exc)
                                )

            st.divider()

            st.subheader(
                "Reiniciar institución"
            )

            st.warning(
                "La organización y las campañas se conservarán. "
                "Los planteles se marcarán como BAJA y sus "
                "correos, teléfonos y contactos quedarán inactivos."
            )

            reset_reason = st.text_area(
                "Motivo obligatorio",
                key=f"reset_reason_{admin_org_id}",
            )

            expected_text = (
                "REINICIAR "
                + summary["official_name"].upper()
            )

            reset_confirmation = st.text_input(
                f"Escribe exactamente: {expected_text}",
                key=(
                    f"reset_confirmation_"
                    f"{admin_org_id}"
                ),
            )

            reset_enabled = (
                reset_confirmation.strip()
                == expected_text
                and bool(
                    reset_reason.strip()
                )
            )

            if st.button(
                "Confirmar reinicio",
                type="primary",
                width="stretch",
                disabled=not reset_enabled,
                key=f"reset_org_{admin_org_id}",
            ):

                try:

                    result = (
                        reset_organization_data(
                            organization_id=(
                                admin_org_id
                            ),
                            user_id=user_id,
                            reason=(
                                reset_reason
                            ),
                        )
                    )

                    set_message(
                        "success",
                        (
                            "Institución reiniciada. "
                            f"Planteles: "
                            f"{result['campuses_deactivated']}; "
                            f"correos: "
                            f"{result['emails_deactivated']}; "
                            f"teléfonos: "
                            f"{result['phones_deactivated']}; "
                            f"contactos: "
                            f"{result['contacts_deactivated']}."
                        ),
                    )

                    st.rerun()

                except Exception as exc:

                    st.error(
                        str(exc)
                    )


# =========================================================
# CONSULTA
# =========================================================

with tab_consulta:

    st.subheader(
        "Organizaciones"
    )

    organizations = (
        get_organizations()
    )

    if organizations:

        st.dataframe(
            pd.DataFrame(
                [
                    dict(row)
                    for row in organizations
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    else:

        st.info(
            "No existen organizaciones."
        )


    st.divider()


    st.subheader(
        "Planteles y unidades"
    )

    campuses = get_campuses()

    if campuses:

        st.dataframe(
            pd.DataFrame(
                [
                    dict(row)
                    for row in campuses
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    else:

        st.info(
            "No existen planteles."
        )


    st.divider()


    st.subheader(
        "Contactos"
    )

    contacts = get_contacts()

    if contacts:

        st.dataframe(
            pd.DataFrame(
                [
                    dict(row)
                    for row in contacts
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    else:

        st.info(
            "No existen contactos."
        )


# =========================================================
# ORGANIZACIÓN
# =========================================================

with tab_organizacion:

    st.subheader(
        "Registrar organización"
    )

    with st.form(
        "organization_form",
        clear_on_submit=True,
    ):

        official_name = (
            st.text_input(
                "Nombre oficial *"
            )
        )

        subsystem = (
            st.text_input(
                "Subsistema"
            )
        )

        sector = st.selectbox(
            "Sector",
            [
                "",
                "PÚBLICO",
                "PRIVADO",
            ],
        )

        relationship_type = (
            st.selectbox(
                "Tipo de relación",
                [
                    "",
                    "PROPIO",
                    "INCORPORADO",
                    "AFILIADO",
                    "DESCENTRALIZADO",
                    "AUTÓNOMO",
                    "OTRO",
                ],
            )
        )

        status = st.selectbox(
            "Estatus",
            [
                "REQUIERE_REVISION",
                "PENDIENTE",
                "INCOMPLETO",
                "VALIDADO",
            ],
        )

        submit = (
            st.form_submit_button(
                "Guardar organización",
                width="stretch",
            )
        )


    if submit:

        if not official_name.strip():

            st.error(
                "El nombre es obligatorio."
            )

        else:

            result = create_organization(
                official_name,
                subsystem,
                sector,
                relationship_type,
                status,
                user_id,
            )

            if result["created"]:

                set_message(
                    "success",
                    "Organización registrada.",
                )

                st.rerun()

            else:

                st.warning(
                    "La organización ya existe: "
                    f"**{result['existing_name']}**"
                )


# =========================================================
# PLANTEL
# =========================================================

with tab_plantel:

    st.subheader(
        "Registrar plantel / unidad"
    )

    organizations = (
        get_organizations()
    )

    if not organizations:

        st.warning(
            "Primero registra una organización."
        )

    else:

        organization_options = {
            row["official_name"]:
            row["id"]

            for row in organizations
        }


        with st.form(
            "campus_form"
        ):

            organization_name = (
                st.selectbox(
                    "Organización *",
                    list(
                        organization_options.keys()
                    ),
                )
            )

            campus_name = (
                st.text_input(
                    "Nombre del plantel / unidad *"
                )
            )

            campus_type = (
                st.selectbox(
                    "Tipo",
                    [
                        "PLANTEL",
                        "UNIDAD",
                        "CAMPUS",
                        "EXTENSIÓN",
                        "SEDE",
                        "OTRO",
                    ],
                )
            )

            municipality = (
                st.text_input(
                    "Municipio"
                )
            )

            state = st.text_input(
                "Estado",
                value="Nuevo León",
            )

            address = st.text_area(
                "Domicilio"
            )

            campus_phone = (
                st.text_input(
                    "Teléfono institucional"
                )
            )

            campus_email = (
                st.text_input(
                    "Correo institucional"
                )
            )

            campus_status = (
                st.selectbox(
                    "Estatus",
                    [
                        "REQUIERE_REVISION",
                        "PENDIENTE",
                        "INCOMPLETO",
                        "VALIDADO",
                    ],
                    key="campus_status_input",
                )
            )

            analyze_campus = (
                st.form_submit_button(
                    "Revisar coincidencias",
                    width="stretch",
                )
            )


        if analyze_campus:

            if not campus_name.strip():

                st.error(
                    "El nombre del plantel "
                    "es obligatorio."
                )

            else:

                organization_id = (
                    organization_options[
                        organization_name
                    ]
                )

                candidates = (
                    analyze_campus_duplicates(
                        organization_id,
                        campus_name,
                        municipality,
                        campus_phone,
                    )
                )

                st.session_state[
                    "pending_campus"
                ] = {
                    "organization_id":
                        organization_id,

                    "campus_name":
                        campus_name,

                    "campus_type":
                        campus_type,

                    "municipality":
                        municipality,

                    "state":
                        state,

                    "address":
                        address,

                    "phone":
                        campus_phone,

                    "email":
                        campus_email,

                    "status":
                        campus_status,
                }

                st.session_state[
                    "pending_campus_candidates"
                ] = candidates

                st.session_state[
                    "merge_campus_id"
                ] = None

                st.rerun()


        pending_campus = (
            st.session_state.get(
                "pending_campus"
            )
        )

        campus_candidates = (
            st.session_state.get(
                "pending_campus_candidates"
            )
        )


        if pending_campus:

            st.divider()

            st.subheader(
                "Revisión de coincidencias"
            )

            if campus_candidates:

                st.dataframe(
                    pd.DataFrame(
                        campus_candidates
                    ),
                    width="stretch",
                    hide_index=True,
                )

                options = {
                    (
                        f"{c['campus_name']} "
                        f"— {c['municipality'] or ''} "
                        f"— {c['level']}"
                    ):
                    c["id"]

                    for c
                    in campus_candidates
                }

                selected = (
                    st.selectbox(
                        "Selecciona una coincidencia",
                        list(
                            options.keys()
                        ),
                        key="campus_candidate_selector",
                    )
                )

                selected_id = (
                    options[selected]
                )

                c1, c2, c3 = (
                    st.columns(3)
                )

                with c1:

                    if st.button(
                        "Es el mismo plantel",
                        type="primary",
                        width="stretch",
                        key="campus_same",
                    ):

                        st.session_state[
                            "merge_campus_id"
                        ] = selected_id

                        st.rerun()

                with c2:

                    if st.button(
                        "Es otro plantel",
                        width="stretch",
                        key="campus_different",
                    ):

                        save_pending_campus()

                with c3:

                    if st.button(
                        "Cancelar",
                        width="stretch",
                        key="campus_cancel",
                    ):

                        clear_pending_campus()
                        st.rerun()

            else:

                st.success(
                    "No se encontraron coincidencias."
                )

                c1, c2 = (
                    st.columns(2)
                )

                with c1:

                    if st.button(
                        "Crear plantel",
                        type="primary",
                        width="stretch",
                        key="campus_create",
                    ):

                        save_pending_campus()

                with c2:

                    if st.button(
                        "Cancelar",
                        width="stretch",
                        key="campus_create_cancel",
                    ):

                        clear_pending_campus()
                        st.rerun()


        merge_campus_id = (
            st.session_state.get(
                "merge_campus_id"
            )
        )


        if (
            pending_campus
            and merge_campus_id
        ):

            existing = (
                get_campus_detail(
                    merge_campus_id
                )
            )

            st.divider()

            st.header(
                "Fusionar plantel"
            )

            comparison = pd.DataFrame(
                [
                    {
                        "Campo": "Nombre",
                        "BD actual":
                            existing["campus_name"],
                        "Dato recibido":
                            pending_campus["campus_name"],
                    },
                    {
                        "Campo": "Municipio",
                        "BD actual":
                            existing["municipality"],
                        "Dato recibido":
                            pending_campus["municipality"],
                    },
                    {
                        "Campo": "Estado",
                        "BD actual":
                            existing["state"],
                        "Dato recibido":
                            pending_campus["state"],
                    },
                    {
                        "Campo": "Domicilio",
                        "BD actual":
                            existing["address"],
                        "Dato recibido":
                            pending_campus["address"],
                    },
                    {
                        "Campo": "Teléfono",
                        "BD actual":
                            ", ".join(
                                existing["phones"]
                            ),
                        "Dato recibido":
                            pending_campus["phone"],
                    },
                    {
                        "Campo": "Correo",
                        "BD actual":
                            ", ".join(
                                existing["emails"]
                            ),
                        "Dato recibido":
                            pending_campus["email"],
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
                "Usar municipio recibido",
                key="campus_merge_municipality",
            ):
                selected_fields.append(
                    "municipality"
                )

            if st.checkbox(
                "Usar estado recibido",
                key="campus_merge_state",
            ):
                selected_fields.append(
                    "state"
                )

            if st.checkbox(
                "Usar domicilio recibido",
                key="campus_merge_address",
            ):
                selected_fields.append(
                    "address"
                )

            save_alias = st.checkbox(
                "Guardar nombre recibido como alias",
                value=True,
                key="campus_merge_alias",
            )

            c1, c2 = (
                st.columns(2)
            )

            with c1:

                if st.button(
                    "Confirmar fusión",
                    type="primary",
                    width="stretch",
                    key="campus_merge_confirm",
                ):

                    merge_campus_data(
                        merge_campus_id,
                        pending_campus,
                        selected_fields,
                        user_id,
                        save_alias,
                    )

                    clear_pending_campus()

                    set_message(
                        "success",
                        "Plantel fusionado correctamente.",
                    )

                    st.rerun()

            with c2:

                if st.button(
                    "Cancelar fusión",
                    width="stretch",
                    key="campus_merge_cancel",
                ):

                    st.session_state[
                        "merge_campus_id"
                    ] = None

                    st.rerun()


# =========================================================
# CONTACTOS
# =========================================================

with tab_contacto:

    st.subheader(
        "Registrar contacto"
    )

    campuses = get_campuses()

    if not campuses:

        st.warning(
            "Primero registra un plantel."
        )

    else:

        campus_options = {
            (
                f"{row['official_name']} — "
                f"{row['campus_name']}"
            ):
            row["id"]

            for row in campuses
        }


        with st.form(
            "contact_form"
        ):

            campus_label = (
                st.selectbox(
                    "Plantel / unidad *",
                    list(
                        campus_options.keys()
                    ),
                )
            )

            full_name = (
                st.text_input(
                    "Nombre del contacto *"
                )
            )

            position = (
                st.text_input(
                    "Puesto"
                )
            )

            area = (
                st.text_input(
                    "Área"
                )
            )

            contact_phone = (
                st.text_input(
                    "Teléfono / celular"
                )
            )

            contact_email = (
                st.text_input(
                    "Correo"
                )
            )

            notes = (
                st.text_area(
                    "Notas"
                )
            )

            contact_status = (
                st.selectbox(
                    "Estatus",
                    [
                        "REQUIERE_REVISION",
                        "PENDIENTE",
                        "INCOMPLETO",
                        "VALIDADO",
                    ],
                    key="contact_status_input",
                )
            )

            analyze_contact = (
                st.form_submit_button(
                    "Revisar coincidencias",
                    width="stretch",
                )
            )


        # -------------------------------------------------
        # BUSCAR COINCIDENCIAS
        # -------------------------------------------------

        if analyze_contact:

            if not full_name.strip():

                st.error(
                    "El nombre del contacto "
                    "es obligatorio."
                )

            else:

                campus_id = (
                    campus_options[
                        campus_label
                    ]
                )

                candidates = (
                    analyze_contact_duplicates(
                        campus_id,
                        full_name,
                        contact_phone,
                        contact_email,
                    )
                )

                st.session_state[
                    "pending_contact"
                ] = {
                    "campus_id":
                        campus_id,

                    "full_name":
                        full_name,

                    "position":
                        position,

                    "area":
                        area,

                    "phone":
                        contact_phone,

                    "email":
                        contact_email,

                    "notes":
                        notes,

                    "status":
                        contact_status,
                }

                st.session_state[
                    "pending_contact_candidates"
                ] = candidates

                st.session_state[
                    "merge_contact_id"
                ] = None

                st.rerun()


        pending_contact = (
            st.session_state.get(
                "pending_contact"
            )
        )

        contact_candidates = (
            st.session_state.get(
                "pending_contact_candidates"
            )
        )


        # -------------------------------------------------
        # MOSTRAR COINCIDENCIAS
        # -------------------------------------------------

        if pending_contact:

            st.divider()

            st.subheader(
                "Revisión del contacto"
            )

            st.write(
                "**Contacto propuesto:** "
                f"{pending_contact['full_name']}"
            )


            if contact_candidates:

                display_data = []

                for candidate in contact_candidates:

                    display_data.append(
                        {
                            "ID":
                                candidate["id"],

                            "Nombre":
                                candidate["full_name"],

                            "Puesto":
                                candidate["position"],

                            "Área":
                                candidate["area"],

                            "Teléfonos":
                                candidate["phones"],

                            "Correos":
                                candidate["emails"],

                            "Similitud":
                                candidate["name_score"],

                            "Teléfono coincide":
                                candidate["phone_match"],

                            "Correo coincide":
                                candidate["email_match"],

                            "Nombre exacto":
                                candidate["exact_name"],

                            "Nivel":
                                candidate["level"],
                        }
                    )


                st.dataframe(
                    pd.DataFrame(
                        display_data
                    ),
                    width="stretch",
                    hide_index=True,
                )


                contact_options = {
                    (
                        f"{candidate['full_name']} "
                        f"— "
                        f"{candidate['position'] or 'Sin puesto'} "
                        f"— "
                        f"{candidate['level']}"
                    ):
                    candidate["id"]

                    for candidate
                    in contact_candidates
                }


                selected_contact = (
                    st.selectbox(
                        "Selecciona el contacto "
                        "con el que deseas comparar",
                        list(
                            contact_options.keys()
                        ),
                        key="contact_candidate_selector",
                    )
                )

                selected_contact_id = (
                    contact_options[
                        selected_contact
                    ]
                )


                st.warning(
                    "Se encontró al menos una "
                    "posible coincidencia. "
                    "El sistema no tomará ninguna "
                    "decisión automáticamente."
                )


                # MUY IMPORTANTE:
                # Siempre mostramos los 3 botones,
                # incluso para coincidencias EXACTAS.

                c1, c2, c3 = (
                    st.columns(3)
                )


                with c1:

                    if st.button(
                        "Es la misma persona",
                        type="primary",
                        width="stretch",
                        key="contact_same_person",
                    ):

                        st.session_state[
                            "merge_contact_id"
                        ] = (
                            selected_contact_id
                        )

                        st.rerun()


                with c2:

                    if st.button(
                        "Es otra persona",
                        width="stretch",
                        key="contact_different_person",
                    ):

                        save_pending_contact()


                with c3:

                    if st.button(
                        "Cancelar",
                        width="stretch",
                        key="contact_cancel_candidate",
                    ):

                        clear_pending_contact()

                        st.rerun()


            else:

                st.success(
                    "No se encontraron "
                    "contactos similares."
                )


                c1, c2 = (
                    st.columns(2)
                )


                with c1:

                    if st.button(
                        "Crear contacto",
                        type="primary",
                        width="stretch",
                        key="contact_create_new",
                    ):

                        save_pending_contact()


                with c2:

                    if st.button(
                        "Cancelar",
                        width="stretch",
                        key="contact_cancel_new",
                    ):

                        clear_pending_contact()

                        st.rerun()


        # =================================================
        # FUSIONAR CONTACTO
        # =================================================

        merge_contact_id = (
            st.session_state.get(
                "merge_contact_id"
            )
        )


        if (
            pending_contact
            and merge_contact_id
        ):

            existing_contact = (
                get_contact_detail(
                    merge_contact_id
                )
            )

            if existing_contact:

                st.divider()

                st.header(
                    "Fusionar contacto"
                )

                st.warning(
                    "Confirma qué información "
                    "debe quedar en el registro. "
                    "Nada se modifica todavía."
                )


                comparison = (
                    pd.DataFrame(
                        [
                            {
                                "Campo":
                                    "Nombre",

                                "BD actual":
                                    existing_contact[
                                        "full_name"
                                    ],

                                "Dato recibido":
                                    pending_contact[
                                        "full_name"
                                    ],
                            },
                            {
                                "Campo":
                                    "Puesto",

                                "BD actual":
                                    existing_contact[
                                        "position"
                                    ],

                                "Dato recibido":
                                    pending_contact[
                                        "position"
                                    ],
                            },
                            {
                                "Campo":
                                    "Área",

                                "BD actual":
                                    existing_contact[
                                        "area"
                                    ],

                                "Dato recibido":
                                    pending_contact[
                                        "area"
                                    ],
                            },
                            {
                                "Campo":
                                    "Teléfono",

                                "BD actual":
                                    ", ".join(
                                        existing_contact[
                                            "phones"
                                        ]
                                    ),

                                "Dato recibido":
                                    pending_contact[
                                        "phone"
                                    ],
                            },
                            {
                                "Campo":
                                    "Correo",

                                "BD actual":
                                    ", ".join(
                                        existing_contact[
                                            "emails"
                                        ]
                                    ),

                                "Dato recibido":
                                    pending_contact[
                                        "email"
                                    ],
                            },
                            {
                                "Campo":
                                    "Notas",

                                "BD actual":
                                    existing_contact[
                                        "notes"
                                    ],

                                "Dato recibido":
                                    pending_contact[
                                        "notes"
                                    ],
                            },
                            {
                                "Campo":
                                    "Estatus",

                                "BD actual":
                                    existing_contact[
                                        "status"
                                    ],

                                "Dato recibido":
                                    pending_contact[
                                        "status"
                                    ],
                            },
                        ]
                    )
                )


                st.dataframe(
                    comparison,
                    width="stretch",
                    hide_index=True,
                )


                st.subheader(
                    "Datos que deseas actualizar"
                )


                selected_fields = []


                use_name = st.checkbox(
                    (
                        "Usar nombre recibido: "
                        f"{pending_contact['full_name']}"
                    ),
                    value=False,
                    key="contact_merge_name",
                )

                if use_name:

                    selected_fields.append(
                        "full_name"
                    )


                use_position = st.checkbox(
                    (
                        "Usar puesto recibido: "
                        f"{pending_contact['position'] or 'Vacío'}"
                    ),
                    value=False,
                    key="contact_merge_position",
                )

                if use_position:

                    selected_fields.append(
                        "position"
                    )


                use_area = st.checkbox(
                    (
                        "Usar área recibida: "
                        f"{pending_contact['area'] or 'Vacío'}"
                    ),
                    value=False,
                    key="contact_merge_area",
                )

                if use_area:

                    selected_fields.append(
                        "area"
                    )


                use_notes = st.checkbox(
                    "Usar notas recibidas",
                    value=False,
                    key="contact_merge_notes",
                )

                if use_notes:

                    selected_fields.append(
                        "notes"
                    )


                use_status = st.checkbox(
                    (
                        "Usar estatus recibido: "
                        f"{pending_contact['status']}"
                    ),
                    value=False,
                    key="contact_merge_status",
                )

                if use_status:

                    selected_fields.append(
                        "status"
                    )


                st.info(
                    "Teléfono y correo funcionan "
                    "de forma distinta: si el dato recibido "
                    "es nuevo, se agrega al contacto. "
                    "Si ya existe, no se duplica."
                )


                c1, c2 = (
                    st.columns(2)
                )


                with c1:

                    if st.button(
                        "Confirmar fusión de contacto",
                        type="primary",
                        width="stretch",
                        key="contact_merge_confirm",
                    ):

                        result = (
                            merge_contact_data(
                                contact_id=(
                                    merge_contact_id
                                ),
                                incoming_data=(
                                    pending_contact
                                ),
                                selected_fields=(
                                    selected_fields
                                ),
                                user_id=user_id,
                            )
                        )


                        details = []


                        if result[
                            "fields_updated"
                        ]:

                            details.append(
                                "Campos actualizados: "
                                + ", ".join(
                                    result[
                                        "fields_updated"
                                    ]
                                )
                            )


                        if result[
                            "phone_added"
                        ]:

                            details.append(
                                "teléfono agregado"
                            )


                        if result[
                            "email_added"
                        ]:

                            details.append(
                                "correo agregado"
                            )


                        clear_pending_contact()


                        if details:

                            message = (
                                "Contacto fusionado. "
                                + "; ".join(
                                    details
                                )
                                + "."
                            )

                        else:

                            message = (
                                "Se confirmó que corresponde "
                                "a la misma persona. "
                                "No había información nueva."
                            )


                        set_message(
                            "success",
                            message,
                        )

                        st.rerun()


                with c2:

                    if st.button(
                        "Cancelar fusión",
                        width="stretch",
                        key="contact_merge_cancel",
                    ):

                        st.session_state[
                            "merge_contact_id"
                        ] = None

                        st.rerun()