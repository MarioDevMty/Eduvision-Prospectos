import pandas as pd
import streamlit as st

from database.repositories.prospecting import (
    ORGANIZATION_TYPES,
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
    add_validated_contact_email,
    add_validated_email,
    deactivate_contact_email,
    deactivate_email,
    get_campus_management_detail,
    get_contact_management_detail,
    get_organization_campuses,
    get_organization_contacts,
    get_organization_management_summary,
    reactivate_contact_email,
    reactivate_email,
    reset_organization_data,
    set_primary_contact_email,
    set_primary_email,
    update_campus,
    update_contact,
    update_contact_email,
    update_email,
    update_organization,
)


ENTITY_STATUSES = [
    "REQUIERE_REVISION",
    "PENDIENTE",
    "INCOMPLETO",
    "VALIDADO",
    "BAJA",
]

ENTRY_STATUSES = ENTITY_STATUSES[:-1]


# =========================================================
# SEGURIDAD
# =========================================================

if not st.session_state.get("authenticated", False):
    st.error("La sesión no está activa.")
    st.stop()

user_id = st.session_state.get("user_id")
if user_id is None:
    st.error("No se encontró el usuario de la sesión.")
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
# UTILIDADES
# =========================================================

def set_message(message_type: str, text: str) -> None:
    st.session_state["db_message"] = {
        "type": message_type,
        "text": text,
    }


def show_message() -> None:
    message = st.session_state.get("db_message")
    if not message:
        return

    renderer = {
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
    }.get(message["type"], st.info)

    renderer(message["text"])
    st.session_state["db_message"] = None


def clear_pending_campus() -> None:
    st.session_state["pending_campus"] = None
    st.session_state["pending_campus_candidates"] = None
    st.session_state["merge_campus_id"] = None


def clear_pending_contact() -> None:
    st.session_state["pending_contact"] = None
    st.session_state["pending_contact_candidates"] = None
    st.session_state["merge_contact_id"] = None


def option_index(options: list[str], value: str | None) -> int:
    return options.index(value) if value in options else 0


def organization_label(row) -> str:
    org_type = row["organization_type"] or "SIN_CLASIFICAR"
    return f"{row['official_name']} — {org_type}"


def save_pending_campus() -> None:
    data = st.session_state.get("pending_campus")
    if not data:
        return

    campus_id = create_campus(
        organization_id=data["organization_id"],
        campus_name=data["campus_name"],
        campus_type=data["campus_type"],
        municipality=data["municipality"],
        state=data["state"],
        address=data["address"],
        status=data["status"],
        user_id=user_id,
    )

    if data["phone"].strip():
        add_phone(
            "CAMPUS", campus_id, data["phone"],
            "INSTITUCIONAL", user_id, True,
        )

    if data["email"].strip():
        add_email(
            "CAMPUS", campus_id, data["email"],
            "INSTITUCIONAL", user_id, True,
        )

    name = data["campus_name"]
    clear_pending_campus()
    set_message("success", f"Plantel registrado: {name}")
    st.rerun()


def save_pending_contact() -> None:
    data = st.session_state.get("pending_contact")
    if not data:
        return

    contact_id = create_contact(
        campus_id=data["campus_id"],
        organization_id=data["organization_id"],
        full_name=data["full_name"],
        position=data["position"],
        area=data["area"],
        notes=data["notes"],
        status=data["status"],
        user_id=user_id,
    )

    if data["phone"].strip():
        add_phone(
            "CONTACT", contact_id, data["phone"],
            "DIRECTO", user_id, True,
        )

    if data["email"].strip():
        add_email(
            "CONTACT", contact_id, data["email"],
            "DIRECTO", user_id, True,
        )

    name = data["full_name"]
    clear_pending_contact()
    set_message("success", f"Contacto registrado: {name}")
    st.rerun()


# =========================================================
# CABECERA
# =========================================================

st.title("Base de datos")
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
    st.subheader("Administrar organizaciones")
    st.caption(
        "Edición y baja lógica. No se eliminan físicamente organizaciones, "
        "planteles ni contactos."
    )

    admin_organizations = get_organizations()

    if not admin_organizations:
        st.info("No existen organizaciones.")
    else:
        org_options = {
            organization_label(row): int(row["id"])
            for row in admin_organizations
        }
        org_label = st.selectbox(
            "Organización",
            list(org_options.keys()),
            key="admin_org_selector",
        )
        organization_id = org_options[org_label]
        summary = get_organization_management_summary(organization_id)

        if summary is None:
            st.error("No fue posible cargar la organización.")
        else:
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Planteles activos", summary["campuses_active"])
            m2.metric("Contactos activos", summary["contacts_active"])
            m3.metric("Contactos directos", summary["direct_contacts_active"])
            m4.metric("Correos activos", summary["active_emails"])
            m5.metric("Correos inactivos", summary["inactive_emails"])

            with st.expander("Editar organización"):
                org_type_options = ["", *ORGANIZATION_TYPES]
                sector_options = ["", "PÚBLICO", "PRIVADO"]
                relationship_options = [
                    "", "PROPIO", "INCORPORADO", "AFILIADO",
                    "DESCENTRALIZADO", "AUTÓNOMO", "OTRO",
                ]

                with st.form(f"edit_org_{organization_id}"):
                    edit_name = st.text_input(
                        "Nombre oficial",
                        value=summary["official_name"] or "",
                    )
                    edit_type = st.selectbox(
                        "Tipo de organización",
                        org_type_options,
                        index=option_index(org_type_options, summary["organization_type"]),
                    )
                    edit_subsystem = st.text_input(
                        "Subsistema",
                        value=summary["subsystem"] or "",
                    )
                    edit_sector = st.selectbox(
                        "Sector",
                        sector_options,
                        index=option_index(sector_options, summary["sector"]),
                    )
                    edit_relationship = st.selectbox(
                        "Tipo de relación",
                        relationship_options,
                        index=option_index(
                            relationship_options,
                            summary["relationship_type"],
                        ),
                    )
                    edit_status = st.selectbox(
                        "Estatus",
                        ENTITY_STATUSES,
                        index=option_index(ENTITY_STATUSES, summary["status"]),
                    )
                    save_org = st.form_submit_button(
                        "Guardar organización",
                        type="primary",
                        width="stretch",
                    )

                if save_org:
                    try:
                        update_organization(
                            organization_id=organization_id,
                            official_name=edit_name,
                            organization_type=edit_type,
                            subsystem=edit_subsystem,
                            sector=edit_sector,
                            relationship_type=edit_relationship,
                            status=edit_status,
                            user_id=user_id,
                        )
                        set_message("success", "Organización actualizada.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

            st.divider()
            admin_entity = st.radio(
                "Administrar",
                ["Planteles / unidades", "Contactos"],
                horizontal=True,
                key=f"admin_entity_{organization_id}",
            )

            # -------------------------------------------------
            # PLANTELES
            # -------------------------------------------------
            if admin_entity == "Planteles / unidades":
                campus_rows = get_organization_campuses(
                    organization_id,
                    include_inactive=True,
                )

                if not campus_rows:
                    st.info("La organización no tiene planteles.")
                else:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "ID": row["id"],
                                    "Plantel": row["campus_name"],
                                    "Municipio": row["municipality"] or "",
                                    "Correos activos": row["active_emails"] or "",
                                    "Estatus": row["status"],
                                }
                                for row in campus_rows
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )

                    campus_options = {
                        f"{row['campus_name']} — {row['municipality'] or ''} [{row['status']}]": int(row["id"])
                        for row in campus_rows
                    }
                    campus_label = st.selectbox(
                        "Plantel para administrar",
                        list(campus_options.keys()),
                        key=f"admin_campus_{organization_id}",
                    )
                    campus_id = campus_options[campus_label]
                    detail = get_campus_management_detail(campus_id)

                    if detail:
                        with st.expander("Editar datos del plantel", expanded=True):
                            with st.form(f"edit_campus_{campus_id}"):
                                c_name = st.text_input("Nombre", value=detail["campus_name"] or "")
                                c_type = st.text_input("Tipo", value=detail["campus_type"] or "")
                                c_code = st.text_input("Clave / código", value=detail["campus_code"] or "")
                                c_address = st.text_area("Domicilio", value=detail["address"] or "")
                                c_neighborhood = st.text_input("Colonia", value=detail["neighborhood"] or "")
                                c_postal = st.text_input("Código postal", value=detail["postal_code"] or "")
                                c_municipality = st.text_input("Municipio", value=detail["municipality"] or "")
                                c_state = st.text_input("Estado", value=detail["state"] or "")
                                c_website = st.text_input("Sitio web", value=detail["website"] or "")
                                c_status = st.selectbox(
                                    "Estatus",
                                    ENTITY_STATUSES,
                                    index=option_index(ENTITY_STATUSES, detail["status"]),
                                )
                                save_campus = st.form_submit_button(
                                    "Guardar cambios", type="primary", width="stretch"
                                )

                            if save_campus:
                                try:
                                    update_campus(
                                        campus_id=campus_id,
                                        campus_name=c_name,
                                        campus_type=c_type,
                                        campus_code=c_code,
                                        address=c_address,
                                        neighborhood=c_neighborhood,
                                        postal_code=c_postal,
                                        municipality=c_municipality,
                                        state=c_state,
                                        website=c_website,
                                        status=c_status,
                                        user_id=user_id,
                                    )
                                    set_message("success", "Plantel actualizado.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))

                        with st.expander("Administrar correos del plantel"):
                            email_rows = detail["emails"]
                            if email_rows:
                                email_options = {
                                    f"{row['email']} [{row['status']}]": row
                                    for row in email_rows
                                }
                                st.dataframe(
                                    pd.DataFrame(email_rows),
                                    hide_index=True,
                                    width="stretch",
                                )
                                email_label = st.selectbox(
                                    "Correo",
                                    list(email_options.keys()),
                                    key=f"campus_email_{campus_id}",
                                )
                                selected = email_options[email_label]
                                email_id = int(selected["id"])

                                with st.form(f"edit_campus_email_{email_id}"):
                                    e_address = st.text_input("Correo", value=selected["email"])
                                    e_type = st.text_input("Tipo", value=selected["email_type"] or "INSTITUCIONAL")
                                    e_primary = st.checkbox("Principal", value=bool(selected["is_primary"]))
                                    e_status = st.selectbox(
                                        "Estatus",
                                        ["ACTIVO", "INACTIVO"],
                                        index=0 if selected["status"] == "ACTIVO" else 1,
                                    )
                                    save_email = st.form_submit_button("Guardar correo", width="stretch")

                                if save_email:
                                    try:
                                        update_email(
                                            email_id, e_address, e_type,
                                            e_primary, e_status, user_id,
                                        )
                                        set_message("success", "Correo actualizado.")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(str(exc))

                                reason = st.text_input(
                                    "Motivo para desactivar",
                                    key=f"campus_email_reason_{email_id}",
                                )
                                b1, b2, b3 = st.columns(3)
                                with b1:
                                    if st.button(
                                        "Desactivar",
                                        disabled=selected["status"] != "ACTIVO",
                                        width="stretch",
                                        key=f"campus_email_off_{email_id}",
                                    ):
                                        try:
                                            deactivate_email(email_id, user_id, reason)
                                            st.rerun()
                                        except Exception as exc:
                                            st.error(str(exc))
                                with b2:
                                    if st.button(
                                        "Reactivar",
                                        disabled=selected["status"] == "ACTIVO",
                                        width="stretch",
                                        key=f"campus_email_on_{email_id}",
                                    ):
                                        try:
                                            reactivate_email(email_id, user_id)
                                            st.rerun()
                                        except Exception as exc:
                                            st.error(str(exc))
                                with b3:
                                    if st.button(
                                        "Hacer principal",
                                        disabled=selected["status"] != "ACTIVO",
                                        width="stretch",
                                        key=f"campus_email_primary_{email_id}",
                                    ):
                                        try:
                                            set_primary_email(email_id, user_id)
                                            st.rerun()
                                        except Exception as exc:
                                            st.error(str(exc))
                            else:
                                st.info("El plantel no tiene correos.")

                            with st.form(f"add_campus_email_{campus_id}"):
                                new_email = st.text_input("Nuevo correo")
                                new_email_type = st.text_input("Tipo", value="INSTITUCIONAL")
                                new_primary = st.checkbox("Marcar como principal")
                                add_button = st.form_submit_button("Agregar correo", width="stretch")
                            if add_button:
                                try:
                                    add_validated_email(
                                        campus_id, new_email, new_email_type,
                                        new_primary, user_id,
                                    )
                                    set_message("success", "Correo agregado.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))

            # -------------------------------------------------
            # CONTACTOS
            # -------------------------------------------------
            else:
                contact_rows = get_organization_contacts(
                    organization_id,
                    include_inactive=True,
                )

                if not contact_rows:
                    st.info("La organización no tiene contactos.")
                else:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "ID": row["id"],
                                    "Nombre": row["full_name"],
                                    "Ámbito": "ORGANIZACIÓN" if row["campus_id"] is None else "PLANTEL",
                                    "Plantel": row["campus_name"] or "",
                                    "Puesto": row["position"] or "",
                                    "Correos activos": row["active_emails"] or "",
                                    "Estatus": row["status"],
                                }
                                for row in contact_rows
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )

                    contact_options = {
                        f"{row['full_name']} — {row['campus_name'] or 'Contacto directo'} [{row['status']}]": int(row["id"])
                        for row in contact_rows
                    }
                    contact_label = st.selectbox(
                        "Contacto para administrar",
                        list(contact_options.keys()),
                        key=f"admin_contact_{organization_id}",
                    )
                    contact_id = contact_options[contact_label]
                    detail = get_contact_management_detail(contact_id)

                    if detail:
                        scope = (
                            "Contacto directo de la organización"
                            if detail["campus_id"] is None
                            else f"Contacto de plantel: {detail['campus_name']}"
                        )
                        st.caption(scope)

                        with st.expander("Editar contacto", expanded=True):
                            with st.form(f"edit_contact_{contact_id}"):
                                p_name = st.text_input("Nombre", value=detail["full_name"] or "")
                                p_position = st.text_input("Puesto", value=detail["position"] or "")
                                p_area = st.text_input("Área", value=detail["area"] or "")
                                p_notes = st.text_area("Notas", value=detail["notes"] or "")
                                p_status = st.selectbox(
                                    "Estatus",
                                    ENTITY_STATUSES,
                                    index=option_index(ENTITY_STATUSES, detail["status"]),
                                )
                                save_contact = st.form_submit_button(
                                    "Guardar contacto", type="primary", width="stretch"
                                )

                            if save_contact:
                                try:
                                    update_contact(
                                        contact_id, p_name, p_position,
                                        p_area, p_notes, p_status, user_id,
                                    )
                                    set_message("success", "Contacto actualizado.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))

                        with st.expander("Administrar correos del contacto"):
                            email_rows = detail["emails"]
                            if email_rows:
                                email_options = {
                                    f"{row['email']} [{row['status']}]": row
                                    for row in email_rows
                                }
                                st.dataframe(
                                    pd.DataFrame(email_rows),
                                    hide_index=True,
                                    width="stretch",
                                )
                                email_label = st.selectbox(
                                    "Correo",
                                    list(email_options.keys()),
                                    key=f"contact_email_{contact_id}",
                                )
                                selected = email_options[email_label]
                                email_id = int(selected["id"])

                                with st.form(f"edit_contact_email_{email_id}"):
                                    e_address = st.text_input("Correo", value=selected["email"])
                                    e_type = st.text_input("Tipo", value=selected["email_type"] or "DIRECTO")
                                    e_primary = st.checkbox("Principal", value=bool(selected["is_primary"]))
                                    e_status = st.selectbox(
                                        "Estatus",
                                        ["ACTIVO", "INACTIVO"],
                                        index=0 if selected["status"] == "ACTIVO" else 1,
                                    )
                                    save_email = st.form_submit_button("Guardar correo", width="stretch")

                                if save_email:
                                    try:
                                        update_contact_email(
                                            email_id, e_address, e_type,
                                            e_primary, e_status, user_id,
                                        )
                                        set_message("success", "Correo actualizado.")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(str(exc))

                                reason = st.text_input(
                                    "Motivo para desactivar",
                                    key=f"contact_email_reason_{email_id}",
                                )
                                b1, b2, b3 = st.columns(3)
                                with b1:
                                    if st.button(
                                        "Desactivar",
                                        disabled=selected["status"] != "ACTIVO",
                                        width="stretch",
                                        key=f"contact_email_off_{email_id}",
                                    ):
                                        try:
                                            deactivate_contact_email(email_id, user_id, reason)
                                            st.rerun()
                                        except Exception as exc:
                                            st.error(str(exc))
                                with b2:
                                    if st.button(
                                        "Reactivar",
                                        disabled=selected["status"] == "ACTIVO",
                                        width="stretch",
                                        key=f"contact_email_on_{email_id}",
                                    ):
                                        try:
                                            reactivate_contact_email(email_id, user_id)
                                            st.rerun()
                                        except Exception as exc:
                                            st.error(str(exc))
                                with b3:
                                    if st.button(
                                        "Hacer principal",
                                        disabled=selected["status"] != "ACTIVO",
                                        width="stretch",
                                        key=f"contact_email_primary_{email_id}",
                                    ):
                                        try:
                                            set_primary_contact_email(email_id, user_id)
                                            st.rerun()
                                        except Exception as exc:
                                            st.error(str(exc))
                            else:
                                st.info("El contacto no tiene correos.")

                            with st.form(f"add_contact_email_{contact_id}"):
                                new_email = st.text_input("Nuevo correo")
                                new_email_type = st.text_input("Tipo", value="DIRECTO")
                                new_primary = st.checkbox("Marcar como principal")
                                add_button = st.form_submit_button("Agregar correo", width="stretch")
                            if add_button:
                                try:
                                    add_validated_contact_email(
                                        contact_id, new_email, new_email_type,
                                        new_primary, user_id,
                                    )
                                    set_message("success", "Correo agregado.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))

            st.divider()
            st.subheader("Reiniciar organización")
            st.warning(
                "La organización y las campañas se conservan. Planteles y contactos "
                "se marcan como BAJA; sus correos y teléfonos quedan inactivos."
            )
            reason = st.text_area(
                "Motivo obligatorio",
                key=f"reset_reason_{organization_id}",
            )
            expected = f"REINICIAR {summary['official_name'].upper()}"
            confirmation = st.text_input(
                f"Escribe exactamente: {expected}",
                key=f"reset_confirmation_{organization_id}",
            )
            enabled = confirmation.strip() == expected and bool(reason.strip())
            if st.button(
                "Confirmar reinicio",
                type="primary",
                width="stretch",
                disabled=not enabled,
                key=f"reset_org_{organization_id}",
            ):
                try:
                    result = reset_organization_data(
                        organization_id, user_id, reason
                    )
                    set_message(
                        "success",
                        "Organización reiniciada. "
                        f"Planteles: {result['campuses_deactivated']}; "
                        f"contactos: {result['contacts_deactivated']}; "
                        f"correos: {result['emails_deactivated']}; "
                        f"teléfonos: {result['phones_deactivated']}.",
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


# =========================================================
# CONSULTA
# =========================================================

with tab_consulta:
    st.subheader("Organizaciones")
    organizations = get_organizations()
    if organizations:
        st.dataframe(
            pd.DataFrame([dict(row) for row in organizations]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No existen organizaciones.")

    st.divider()
    st.subheader("Planteles y unidades")
    campuses = get_campuses()
    if campuses:
        st.dataframe(
            pd.DataFrame([dict(row) for row in campuses]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No existen planteles.")

    st.divider()
    st.subheader("Contactos")
    contacts = get_contacts()
    if contacts:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": row["id"],
                        "Organización": row["official_name"],
                        "Ámbito": "ORGANIZACIÓN" if row["campus_id"] is None else "PLANTEL",
                        "Plantel": row["campus_name"] or "",
                        "Nombre": row["full_name"],
                        "Puesto": row["position"] or "",
                        "Área": row["area"] or "",
                        "Estatus": row["status"],
                    }
                    for row in contacts
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No existen contactos.")


# =========================================================
# NUEVA ORGANIZACIÓN
# =========================================================

with tab_organizacion:
    st.subheader("Registrar organización")

    with st.form("organization_form", clear_on_submit=True):
        official_name = st.text_input("Nombre oficial *")
        organization_type = st.selectbox(
            "Tipo de organización *",
            ORGANIZATION_TYPES,
        )
        subsystem = st.text_input("Subsistema")
        sector = st.selectbox("Sector", ["", "PÚBLICO", "PRIVADO"])
        relationship_type = st.selectbox(
            "Tipo de relación",
            [
                "", "PROPIO", "INCORPORADO", "AFILIADO",
                "DESCENTRALIZADO", "AUTÓNOMO", "OTRO",
            ],
        )
        status = st.selectbox("Estatus", ENTRY_STATUSES)
        submit = st.form_submit_button(
            "Guardar organización",
            width="stretch",
        )

    if submit:
        if not official_name.strip():
            st.error("El nombre es obligatorio.")
        else:
            try:
                result = create_organization(
                    official_name=official_name,
                    subsystem=subsystem,
                    sector=sector,
                    relationship_type=relationship_type,
                    status=status,
                    user_id=user_id,
                    organization_type=organization_type,
                )
                if result["created"]:
                    set_message("success", "Organización registrada.")
                    st.rerun()
                else:
                    st.warning(
                        "La organización ya existe: "
                        f"**{result['existing_name']}**"
                    )
            except Exception as exc:
                st.error(str(exc))


# =========================================================
# NUEVO PLANTEL / UNIDAD
# =========================================================

with tab_plantel:
    st.subheader("Registrar plantel / unidad")
    organizations = get_organizations()

    if not organizations:
        st.warning("Primero registra una organización.")
    else:
        org_options = {
            organization_label(row): int(row["id"])
            for row in organizations
        }

        with st.form("campus_form"):
            org_label = st.selectbox("Organización *", list(org_options.keys()))
            campus_name = st.text_input("Nombre del plantel / unidad *")
            campus_type = st.selectbox(
                "Tipo",
                ["PLANTEL", "UNIDAD", "CAMPUS", "EXTENSIÓN", "SEDE", "OTRO"],
            )
            municipality = st.text_input("Municipio")
            state = st.text_input("Estado", value="Nuevo León")
            address = st.text_area("Domicilio")
            campus_phone = st.text_input("Teléfono institucional")
            campus_email = st.text_input("Correo institucional")
            campus_status = st.selectbox(
                "Estatus", ENTRY_STATUSES, key="campus_status_input"
            )
            analyze = st.form_submit_button(
                "Revisar coincidencias", width="stretch"
            )

        if analyze:
            if not campus_name.strip():
                st.error("El nombre del plantel es obligatorio.")
            else:
                organization_id = org_options[org_label]
                candidates = analyze_campus_duplicates(
                    organization_id,
                    campus_name,
                    municipality,
                    campus_phone,
                )
                st.session_state["pending_campus"] = {
                    "organization_id": organization_id,
                    "campus_name": campus_name,
                    "campus_type": campus_type,
                    "municipality": municipality,
                    "state": state,
                    "address": address,
                    "phone": campus_phone,
                    "email": campus_email,
                    "status": campus_status,
                }
                st.session_state["pending_campus_candidates"] = candidates
                st.session_state["merge_campus_id"] = None
                st.rerun()

        pending = st.session_state.get("pending_campus")
        candidates = st.session_state.get("pending_campus_candidates")

        if pending:
            st.divider()
            st.subheader("Revisión de coincidencias")

            if candidates:
                st.dataframe(
                    pd.DataFrame(candidates),
                    width="stretch",
                    hide_index=True,
                )
                options = {
                    f"{item['campus_name']} — {item['municipality'] or ''} — {item['level']}": item["id"]
                    for item in candidates
                }
                selected = st.selectbox(
                    "Selecciona una coincidencia",
                    list(options.keys()),
                    key="campus_candidate_selector",
                )
                selected_id = options[selected]
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button(
                        "Es el mismo plantel",
                        type="primary",
                        width="stretch",
                        key="campus_same",
                    ):
                        st.session_state["merge_campus_id"] = selected_id
                        st.rerun()
                with b2:
                    if st.button(
                        "Es otro plantel",
                        width="stretch",
                        key="campus_different",
                    ):
                        save_pending_campus()
                with b3:
                    if st.button("Cancelar", width="stretch", key="campus_cancel"):
                        clear_pending_campus()
                        st.rerun()
            else:
                st.success("No se encontraron coincidencias.")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Crear plantel", type="primary", width="stretch", key="campus_create"
                    ):
                        save_pending_campus()
                with b2:
                    if st.button("Cancelar", width="stretch", key="campus_create_cancel"):
                        clear_pending_campus()
                        st.rerun()

        merge_id = st.session_state.get("merge_campus_id")
        if pending and merge_id:
            existing = get_campus_detail(merge_id)
            if existing:
                st.divider()
                st.header("Fusionar plantel")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"Campo": "Nombre", "BD actual": existing["campus_name"], "Dato recibido": pending["campus_name"]},
                            {"Campo": "Municipio", "BD actual": existing["municipality"], "Dato recibido": pending["municipality"]},
                            {"Campo": "Estado", "BD actual": existing["state"], "Dato recibido": pending["state"]},
                            {"Campo": "Domicilio", "BD actual": existing["address"], "Dato recibido": pending["address"]},
                            {"Campo": "Teléfono", "BD actual": ", ".join(existing["phones"]), "Dato recibido": pending["phone"]},
                            {"Campo": "Correo", "BD actual": ", ".join(existing["emails"]), "Dato recibido": pending["email"]},
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

                fields = []
                if st.checkbox("Usar municipio recibido", key="campus_merge_municipality"):
                    fields.append("municipality")
                if st.checkbox("Usar estado recibido", key="campus_merge_state"):
                    fields.append("state")
                if st.checkbox("Usar domicilio recibido", key="campus_merge_address"):
                    fields.append("address")
                save_alias = st.checkbox(
                    "Guardar nombre recibido como alias",
                    value=True,
                    key="campus_merge_alias",
                )

                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Confirmar fusión",
                        type="primary",
                        width="stretch",
                        key="campus_merge_confirm",
                    ):
                        merge_campus_data(
                            merge_id, pending, fields, user_id, save_alias
                        )
                        clear_pending_campus()
                        set_message("success", "Plantel fusionado correctamente.")
                        st.rerun()
                with b2:
                    if st.button(
                        "Cancelar fusión", width="stretch", key="campus_merge_cancel"
                    ):
                        st.session_state["merge_campus_id"] = None
                        st.rerun()


# =========================================================
# NUEVO CONTACTO
# =========================================================

with tab_contacto:
    st.subheader("Registrar contacto")
    organizations = get_organizations()

    if not organizations:
        st.warning("Primero registra una organización.")
    else:
        org_options = {
            organization_label(row): int(row["id"])
            for row in organizations
        }
        org_label = st.selectbox(
            "Organización *",
            list(org_options.keys()),
            key="contact_org_selector",
        )
        organization_id = org_options[org_label]

        scope = st.radio(
            "¿Pertenece a un plantel / unidad?",
            [
                "No, es contacto directo de la organización",
                "Sí",
            ],
            horizontal=True,
            key="contact_scope_selector",
        )

        campus_id = None
        campus_available = True

        if scope == "Sí":
            campus_rows = [
                row
                for row in get_campuses(organization_id)
                if row["status"] != "BAJA"
            ]
            if not campus_rows:
                campus_available = False
                st.warning(
                    "La organización no tiene planteles activos. "
                    "Selecciona contacto directo o registra primero un plantel."
                )
            else:
                campus_options = {
                    f"{row['campus_name']} — {row['municipality'] or ''}": int(row["id"])
                    for row in campus_rows
                }
                campus_label = st.selectbox(
                    "Plantel / unidad *",
                    list(campus_options.keys()),
                    key="contact_campus_selector",
                )
                campus_id = campus_options[campus_label]

        with st.form("contact_form"):
            full_name = st.text_input("Nombre del contacto *")
            position = st.text_input("Puesto")
            area = st.text_input("Área")
            contact_phone = st.text_input("Teléfono / celular")
            contact_email = st.text_input("Correo")
            notes = st.text_area("Notas")
            contact_status = st.selectbox(
                "Estatus", ENTRY_STATUSES, key="contact_status_input"
            )
            analyze = st.form_submit_button(
                "Revisar coincidencias",
                width="stretch",
                disabled=not campus_available,
            )

        if analyze:
            if not full_name.strip():
                st.error("El nombre del contacto es obligatorio.")
            else:
                try:
                    candidates = analyze_contact_duplicates(
                        campus_id=campus_id,
                        organization_id=organization_id,
                        full_name=full_name,
                        phone=contact_phone,
                        email=contact_email,
                    )
                    st.session_state["pending_contact"] = {
                        "organization_id": organization_id,
                        "campus_id": campus_id,
                        "full_name": full_name,
                        "position": position,
                        "area": area,
                        "phone": contact_phone,
                        "email": contact_email,
                        "notes": notes,
                        "status": contact_status,
                    }
                    st.session_state["pending_contact_candidates"] = candidates
                    st.session_state["merge_contact_id"] = None
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        pending = st.session_state.get("pending_contact")
        candidates = st.session_state.get("pending_contact_candidates")

        if pending:
            st.divider()
            st.subheader("Revisión del contacto")
            scope_text = (
                "Contacto directo de la organización"
                if pending["campus_id"] is None
                else "Contacto de plantel"
            )
            st.write(f"**Ámbito:** {scope_text}")
            st.write(f"**Contacto propuesto:** {pending['full_name']}")

            if candidates:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "ID": item["id"],
                                "Nombre": item["full_name"],
                                "Puesto": item["position"],
                                "Área": item["area"],
                                "Teléfonos": item["phones"],
                                "Correos": item["emails"],
                                "Similitud": item["name_score"],
                                "Teléfono coincide": item["phone_match"],
                                "Correo coincide": item["email_match"],
                                "Nivel": item["level"],
                            }
                            for item in candidates
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
                options = {
                    f"{item['full_name']} — {item['position'] or 'Sin puesto'} — {item['level']}": item["id"]
                    for item in candidates
                }
                selected = st.selectbox(
                    "Selecciona el contacto con el que deseas comparar",
                    list(options.keys()),
                    key="contact_candidate_selector",
                )
                selected_id = options[selected]
                st.warning(
                    "Se encontró una posible coincidencia. El sistema no fusiona automáticamente."
                )

                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button(
                        "Es la misma persona",
                        type="primary",
                        width="stretch",
                        key="contact_same_person",
                    ):
                        st.session_state["merge_contact_id"] = selected_id
                        st.rerun()
                with b2:
                    if st.button(
                        "Es otra persona",
                        width="stretch",
                        key="contact_different_person",
                    ):
                        save_pending_contact()
                with b3:
                    if st.button(
                        "Cancelar", width="stretch", key="contact_cancel_candidate"
                    ):
                        clear_pending_contact()
                        st.rerun()
            else:
                st.success("No se encontraron contactos similares.")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Crear contacto",
                        type="primary",
                        width="stretch",
                        key="contact_create_new",
                    ):
                        save_pending_contact()
                with b2:
                    if st.button(
                        "Cancelar", width="stretch", key="contact_cancel_new"
                    ):
                        clear_pending_contact()
                        st.rerun()

        merge_id = st.session_state.get("merge_contact_id")
        if pending and merge_id:
            existing = get_contact_detail(merge_id)
            if existing:
                st.divider()
                st.header("Fusionar contacto")
                st.warning(
                    "Confirma qué información debe actualizarse. Nada se modifica hasta confirmar."
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"Campo": "Nombre", "BD actual": existing["full_name"], "Dato recibido": pending["full_name"]},
                            {"Campo": "Puesto", "BD actual": existing["position"], "Dato recibido": pending["position"]},
                            {"Campo": "Área", "BD actual": existing["area"], "Dato recibido": pending["area"]},
                            {"Campo": "Teléfono", "BD actual": ", ".join(existing["phones"]), "Dato recibido": pending["phone"]},
                            {"Campo": "Correo", "BD actual": ", ".join(existing["emails"]), "Dato recibido": pending["email"]},
                            {"Campo": "Notas", "BD actual": existing["notes"], "Dato recibido": pending["notes"]},
                            {"Campo": "Estatus", "BD actual": existing["status"], "Dato recibido": pending["status"]},
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

                fields = []
                if st.checkbox("Usar nombre recibido", key="contact_merge_name"):
                    fields.append("full_name")
                if st.checkbox("Usar puesto recibido", key="contact_merge_position"):
                    fields.append("position")
                if st.checkbox("Usar área recibida", key="contact_merge_area"):
                    fields.append("area")
                if st.checkbox("Usar notas recibidas", key="contact_merge_notes"):
                    fields.append("notes")
                if st.checkbox("Usar estatus recibido", key="contact_merge_status"):
                    fields.append("status")

                st.info(
                    "Teléfono y correo son aditivos: se agregan si son nuevos y no sustituyen automáticamente."
                )

                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Confirmar fusión de contacto",
                        type="primary",
                        width="stretch",
                        key="contact_merge_confirm",
                    ):
                        try:
                            result = merge_contact_data(
                                contact_id=merge_id,
                                incoming_data=pending,
                                selected_fields=fields,
                                user_id=user_id,
                            )
                            details = []
                            if result["fields_updated"]:
                                details.append(
                                    "Campos actualizados: "
                                    + ", ".join(result["fields_updated"])
                                )
                            if result["phone_added"]:
                                details.append("teléfono agregado")
                            if result["email_added"]:
                                details.append("correo agregado")

                            clear_pending_contact()
                            message = (
                                "Contacto fusionado. " + "; ".join(details) + "."
                                if details
                                else "Se confirmó la misma persona; no había información nueva."
                            )
                            set_message("success", message)
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                with b2:
                    if st.button(
                        "Cancelar fusión",
                        width="stretch",
                        key="contact_merge_cancel",
                    ):
                        st.session_state["merge_contact_id"] = None
                        st.rerun()
