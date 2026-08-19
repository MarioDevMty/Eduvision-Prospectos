import pandas as pd
import streamlit as st

from database.repositories.marketing import (
    add_multiple_campaign_recipients,
    archive_invalid_error_recipients,
    correct_campaign_recipient_email,
    create_campaign,
    get_active_delivery_incidents,
    get_archived_campaign_recipients,
    get_campaign,
    get_campaign_recipients,
    get_campaigns,
    get_eligible_recipients,
    register_referred_contact,
    update_recipient_status,
)

from services.smtp_service import (
    send_campaign_email,
)

from services.campaign_sender import (
    send_next_campaign_batch,
    send_single_campaign_recipient,
)

from database.repositories.mailbox_state import (
    get_mailbox_sync_state,
    get_recent_mailbox_sync_runs,
)

from services.mailbox_sync import (
    scan_mailbox,
)


# =========================================================
# CAMPAÑA BASE
# =========================================================

DEFAULT_CAMPAIGN_NAME = (
    "Presentación institucional Grupo Asercom"
)

DEFAULT_OBJECTIVE = (
    "Realizar un primer contacto con organizaciones y contactos "
    "seleccionados, presentar a Grupo Asercom y detectar oportunidades."
)

DEFAULT_SUBJECT = (
    "Presentación Grupo Asercom | Soluciones tecnológicas"
)

DEFAULT_BODY = """Hola, muy buen día:

Mi nombre es Patricia Aguirre y formo parte de Grupo Asercom.

Me pongo en contacto para presentarnos y compartir brevemente algunas de las soluciones tecnológicas que integramos.

Trabajamos principalmente en:

• Aulas interactivas y pantallas inteligentes.

• Soluciones STEM, incluyendo robótica, fabricación aditiva, realidad virtual, Inteligencia Artificial e Internet de las Cosas (IoT).

• Soluciones audiovisuales y experiencias inmersivas.

Nos gustaría conocer si actualmente tienen algún proyecto en puerta o si están evaluando incorporar nuevas tecnologías.

En caso de que sea un tema de interés, con gusto podemos coordinar una breve llamada para presentarnos y conocer mejor sus necesidades.

Si usted no es la persona responsable de este tipo de proyectos, le agradecería mucho si pudiera orientarme sobre con quién sería conveniente establecer contacto.

Muchas gracias por su tiempo.

Saludos cordiales,"""


# =========================================================
# UTILIDADES
# =========================================================

def get_smtp_configuration():
    try:
        smtp = st.secrets["smtp"]
        imap = st.secrets["imap"]

        config = {
            "host":
                smtp.get("host", ""),
            "port":
                int(
                    smtp.get(
                        "port",
                        587,
                    )
                ),
            "security":
                smtp.get(
                    "security",
                    "starttls",
                ),
            "user":
                smtp.get("user", ""),
            "password":
                smtp.get(
                    "password",
                    "",
                ),
            "imap": {
                "host":
                    imap.get(
                        "host",
                        "",
                    ),
                "port":
                    int(
                        imap.get(
                            "port",
                            993,
                        )
                    ),
                "user":
                    imap.get(
                        "user",
                        "",
                    ),
                "password":
                    imap.get(
                        "password",
                        "",
                    ),
                "sent_folder":
                    imap.get(
                        "sent_folder",
                        "INBOX.Sent",
                    ),
            },
        }

        required = [
            config["host"],
            config["user"],
            config["password"],
            config["imap"]["host"],
            config["imap"]["user"],
            config["imap"]["password"],
        ]

        return (
            config
            if all(required)
            else None
        )

    except Exception:
        return None


def recipient_display_name(
    row,
) -> str:
    return (
        (
            row["recipient_name_snapshot"]
            or ""
        ).strip()
        or
        (
            row["campus_name_snapshot"]
            or ""
        ).strip()
        or
        (
            row["organization_name_snapshot"]
            or ""
        ).strip()
        or
        (
            row["email_address"]
            or ""
        ).strip()
    )


def calculate_campaign_counts(
    recipients,
):
    total = len(
        recipients
    )

    pending = sum(
        1
        for row in recipients
        if row["status"] == "PENDIENTE"
    )

    sent = sum(
        1
        for row in recipients
        if row["status"] == "ENVIADO"
    )

    errors = sum(
        1
        for row in recipients
        if row["status"] == "ERROR"
    )

    bounces = sum(
        1
        for row in recipients
        if row["status"] == "REBOTE"
    )

    responses = sum(
        1
        for row in recipients
        if row["status"] in {
            "RESPONDIO",
            "CONTACTO_REFERIDO",
            "NO_INTERESADO",
        }
    )

    referred = sum(
        1
        for row in recipients
        if row["status"]
        == "CONTACTO_REFERIDO"
    )

    waiting = sum(
        1
        for row in recipients
        if row["status"] in {
            "ENVIADO",
            "SIN_RESPUESTA",
        }
    )

    return {
        "total":
            total,
        "pending":
            pending,
        "sent":
            sent,
        "errors":
            errors,
        "bounces":
            bounces,
        "responses":
            responses,
        "referred":
            referred,
        "waiting":
            waiting,
    }


def get_campaign_stage(
    campaign_id,
    recipients,
):
    counts = calculate_campaign_counts(
        recipients
    )

    test_ok = st.session_state.get(
        f"marketing_test_ok_{campaign_id}",
        False,
    )

    if counts["total"] == 0:
        return "BORRADOR"

    if (
        counts["pending"]
        == counts["total"]
        and not test_ok
    ):
        return "PREPARAR"

    if (
        counts["pending"]
        == counts["total"]
        and test_ok
    ):
        return "PREPARADA"

    if counts["pending"] > 0:
        return "EN_PROCESO"

    if counts["responses"] > 0:
        return "EN_SEGUIMIENTO"

    return "ENVIADA"


def select_campaign(
    section_key: str,
):
    campaigns = get_campaigns()

    if not campaigns:
        st.info(
            "Primero debes crear una campaña."
        )
        return None

    campaign_options = {
        f"{row['id']} - {row['name']}":
            row["id"]
        for row in campaigns
    }

    labels = list(
        campaign_options.keys()
    )

    stored = st.session_state.get(
        "marketing_selected_campaign"
    )

    default_index = 0

    if stored:
        for index, label in enumerate(
            labels
        ):
            if (
                campaign_options[label]
                == stored
            ):
                default_index = index
                break

    selected_label = st.selectbox(
        "Campaña",
        options=labels,
        index=default_index,
        key=(
            f"campaign_selector_"
            f"{section_key}"
        ),
    )

    campaign_id = (
        campaign_options[
            selected_label
        ]
    )

    st.session_state[
        "marketing_selected_campaign"
    ] = campaign_id

    campaign = get_campaign(
        campaign_id
    )

    recipients = (
        get_campaign_recipients(
            campaign_id
        )
    )

    if campaign is None:
        st.error(
            "No fue posible cargar la campaña."
        )
        return None

    counts = (
        calculate_campaign_counts(
            recipients
        )
    )

    stage = get_campaign_stage(
        campaign_id,
        recipients,
    )

    return {
        "campaign_id":
            campaign_id,
        "campaign":
            campaign,
        "recipients":
            recipients,
        "counts":
            counts,
        "stage":
            stage,
    }


def show_campaign_identity(
    context,
):
    campaign = context[
        "campaign"
    ]

    counts = context[
        "counts"
    ]

    st.subheader(
        campaign["name"]
    )

    c1, c2, c3, c4 = (
        st.columns(4)
    )

    c1.metric(
        "Destinatarios",
        counts["total"],
    )

    c2.metric(
        "Pendientes",
        counts["pending"],
    )

    c3.metric(
        "Rebotes",
        counts["bounces"],
    )

    c4.metric(
        "Errores",
        counts["errors"],
    )


def eligible_rows_to_dataframe(
    rows: list[dict],
) -> pd.DataFrame:
    data = []

    for row in rows:
        data.append(
            {
                "recipient_type":
                    row["recipient_type"],
                "organization_id":
                    row["organization_id"],
                "campus_id":
                    row["campus_id"],
                "contact_id":
                    row["contact_id"],

                "Tipo":
                    (
                        "Contacto"
                        if row["recipient_type"]
                        == "CONTACTO"
                        else "Institucional"
                    ),

                "Tipo organización":
                    (
                        row["organization_type"]
                        or "SIN_CLASIFICAR"
                    ),

                "Organización":
                    row["official_name"],

                "Subsistema":
                    row["subsystem"] or "",

                "Plantel / unidad":
                    row["campus_name"] or "",

                "Destinatario":
                    row["recipient_name"] or "",

                "Puesto":
                    row["position"] or "",

                "Área":
                    row["area"] or "",

                "Municipio":
                    row["municipality"] or "",

                "Estado":
                    row["state"] or "",

                "Correo":
                    row["email"],

                "Tipo correo":
                    row["source_email_type"] or "",

                "Principal":
                    bool(
                        row["is_primary"]
                    ),
            }
        )

    return pd.DataFrame(
        data
    )


def apply_text_filter(
    dataframe: pd.DataFrame,
    text: str,
    columns: list[str],
) -> pd.Series:
    terms = [
        item.strip().lower()
        for item in (
            text
            or ""
        ).split(",")
        if item.strip()
    ]

    if not terms:
        return pd.Series(
            True,
            index=dataframe.index,
        )

    combined = (
        dataframe[
            columns
        ]
        .fillna("")
        .astype(str)
        .agg(
            " ".join,
            axis=1,
        )
        .str.lower()
    )

    mask = pd.Series(
        False,
        index=dataframe.index,
    )

    for term in terms:
        mask = (
            mask
            | combined.str.contains(
                term,
                regex=False,
            )
        )

    return mask


# =========================================================
# CREAR CAMPAÑA
# =========================================================

def render_create_campaign(
    user_id: int,
):

    st.header(
        "Crear nueva campaña"
    )

    st.info(
        "La campaña puede combinar correos institucionales "
        "y contactos identificados de cualquier tipo de organización. "
        "Guardar la campaña no envía correos."
    )

    st.subheader(
        "Paso 1 · Definir campaña"
    )

    campaign_name = st.text_input(
        "Nombre de la campaña",
        value=DEFAULT_CAMPAIGN_NAME,
    )

    objective = st.text_area(
        "Objetivo",
        value=DEFAULT_OBJECTIVE,
        height=100,
    )

    subject = st.text_input(
        "Asunto del correo",
        value=DEFAULT_SUBJECT,
    )

    body_text = st.text_area(
        "Contenido del correo",
        value=DEFAULT_BODY,
        height=500,
    )

    st.divider()

    st.subheader(
        "Paso 2 · Seleccionar destinatarios"
    )

    st.caption(
        "Primero define qué canales quieres considerar. "
        "Después filtra el universo resultante. "
        "Puesto y área son filtros opcionales, nunca requisitos."
    )

    source_col1, source_col2 = (
        st.columns(2)
    )

    include_institutional = (
        source_col1.checkbox(
            "Incluir correos institucionales",
            value=True,
            help=(
                "Correos activos de planteles/unidades "
                "y correos ligados directamente a una organización."
            ),
        )
    )

    include_contacts = (
        source_col2.checkbox(
            "Incluir contactos identificados",
            value=True,
            help=(
                "Personas con correo activo. "
                "Pueden pertenecer a un plantel o directamente a una organización."
            ),
        )
    )

    if (
        not include_institutional
        and not include_contacts
    ):
        st.warning(
            "Selecciona al menos un tipo de destinatario."
        )
        return

    eligible_rows = get_eligible_recipients(
        include_institutional=(
            include_institutional
        ),
        include_contacts=(
            include_contacts
        ),
    )

    if not eligible_rows:
        st.warning(
            "No existen destinatarios con correo activo "
            "para los tipos seleccionados."
        )
        return

    df = eligible_rows_to_dataframe(
        eligible_rows
    )

    metric1, metric2, metric3, metric4 = (
        st.columns(4)
    )

    metric1.metric(
        "Correos disponibles",
        df["Correo"].nunique(),
    )

    metric2.metric(
        "Organizaciones",
        df["organization_id"].nunique(),
    )

    metric3.metric(
        "Planteles / unidades",
        df["campus_id"]
        .dropna()
        .nunique(),
    )

    metric4.metric(
        "Contactos",
        df[
            df["recipient_type"]
            == "CONTACTO"
        ]["contact_id"]
        .dropna()
        .nunique(),
    )

    st.markdown(
        "#### Segmentación"
    )

    filter1, filter2 = (
        st.columns(2)
    )

    organization_type_options = sorted(
        [
            value
            for value
            in df[
                "Tipo organización"
            ].dropna().unique()
            if value
        ]
    )

    selected_org_types = (
        filter1.multiselect(
            "Tipo de organización",
            options=(
                organization_type_options
            ),
        )
    )

    working_df = df.copy()

    if selected_org_types:
        working_df = working_df[
            working_df[
                "Tipo organización"
            ].isin(
                selected_org_types
            )
        ]

    organization_options = sorted(
        [
            value
            for value
            in working_df[
                "Organización"
            ].dropna().unique()
            if value
        ]
    )

    selected_organizations = (
        filter2.multiselect(
            "Organización",
            options=(
                organization_options
            ),
        )
    )

    if selected_organizations:
        working_df = working_df[
            working_df[
                "Organización"
            ].isin(
                selected_organizations
            )
        ]

    filter3, filter4 = (
        st.columns(2)
    )

    subsystem_options = sorted(
        [
            value
            for value
            in working_df[
                "Subsistema"
            ].dropna().unique()
            if value
        ]
    )

    selected_subsystems = (
        filter3.multiselect(
            "Subsistema",
            options=(
                subsystem_options
            ),
        )
    )

    if selected_subsystems:
        working_df = working_df[
            working_df[
                "Subsistema"
            ].isin(
                selected_subsystems
            )
        ]

    campus_options = sorted(
        [
            value
            for value
            in working_df[
                "Plantel / unidad"
            ].dropna().unique()
            if value
        ]
    )

    selected_campuses = (
        filter4.multiselect(
            "Plantel / unidad",
            options=(
                campus_options
            ),
        )
    )

    if selected_campuses:
        working_df = working_df[
            working_df[
                "Plantel / unidad"
            ].isin(
                selected_campuses
            )
        ]

    filter5, filter6 = (
        st.columns(2)
    )

    state_options = sorted(
        [
            value
            for value
            in working_df[
                "Estado"
            ].dropna().unique()
            if value
        ]
    )

    selected_states = (
        filter5.multiselect(
            "Estado",
            options=(
                state_options
            ),
        )
    )

    if selected_states:
        working_df = working_df[
            working_df[
                "Estado"
            ].isin(
                selected_states
            )
        ]

    municipality_options = sorted(
        [
            value
            for value
            in working_df[
                "Municipio"
            ].dropna().unique()
            if value
        ]
    )

    selected_municipalities = (
        filter6.multiselect(
            "Municipio",
            options=(
                municipality_options
            ),
        )
    )

    if selected_municipalities:
        working_df = working_df[
            working_df[
                "Municipio"
            ].isin(
                selected_municipalities
            )
        ]

    st.markdown(
        "#### Filtros opcionales de contacto"
    )

    st.caption(
        "Estos filtros solo reducen los CONTACTOS. "
        "Los correos institucionales permanecen si elegiste incluirlos."
    )

    contact_filter_col1, contact_filter_col2 = (
        st.columns(2)
    )

    position_area_query = (
        contact_filter_col1.text_input(
            "Puesto / área",
            placeholder=(
                "Ej.: TIC, sistemas, tecnología"
            ),
            help=(
                "Separa términos alternativos con coma. "
                "Una coincidencia en puesto o área es suficiente."
            ),
        )
    )

    person_query = (
        contact_filter_col2.text_input(
            "Nombre o correo",
            placeholder=(
                "Ej.: María, @empresa.com"
            ),
        )
    )

    if position_area_query.strip():
        is_contact = (
            working_df[
                "recipient_type"
            ]
            == "CONTACTO"
        )

        contact_match = (
            apply_text_filter(
                working_df,
                position_area_query,
                [
                    "Puesto",
                    "Área",
                ],
            )
        )

        working_df = working_df[
            (~is_contact)
            | contact_match
        ]

    if person_query.strip():
        general_match = (
            apply_text_filter(
                working_df,
                person_query,
                [
                    "Destinatario",
                    "Correo",
                ],
            )
        )

        working_df = working_df[
            general_match
        ]

    working_df = working_df.reset_index(
        drop=True
    )

    st.write(
        "Registros encontrados después de filtros: "
        f"**{len(working_df)}**"
    )

    if working_df.empty:
        st.warning(
            "Los filtros no encontraron destinatarios."
        )
        return

    preselect_all = st.checkbox(
        "Preseleccionar todos los resultados filtrados",
        value=False,
        help=(
            "Déjalo desactivado cuando quieras escoger personas "
            "o correos individualmente."
        ),
    )

    editor_df = working_df.copy()

    editor_df.insert(
        0,
        "Seleccionar",
        bool(
            preselect_all
        ),
    )

    technical_columns = [
        "recipient_type",
        "organization_id",
        "campus_id",
        "contact_id",
    ]

    editor_columns = [
        "Seleccionar",
        "Tipo",
        "Tipo organización",
        "Organización",
        "Plantel / unidad",
        "Destinatario",
        "Puesto",
        "Área",
        "Correo",
        "Principal",
        *technical_columns,
    ]

    stable_key_values = tuple(
        (
            str(row["recipient_type"]),
            str(row["organization_id"]),
            str(row["campus_id"]),
            str(row["contact_id"]),
            str(row["Correo"]),
        )
        for _, row
        in editor_df.iterrows()
    )

    editor_key = (
        "marketing_recipients_editor_"
        + str(
            abs(
                hash(
                    stable_key_values
                )
            )
        )
    )

    edited_df = st.data_editor(
        editor_df[
            editor_columns
        ],
        hide_index=True,
        width="stretch",
        disabled=[
            column
            for column in editor_columns
            if column != "Seleccionar"
        ],
        column_config={
            "Seleccionar":
                st.column_config.CheckboxColumn(
                    "Incluir"
                ),
            "recipient_type":
                None,
            "organization_id":
                None,
            "campus_id":
                None,
            "contact_id":
                None,
        },
        key=editor_key,
    )

    selected_df = edited_df[
        edited_df[
            "Seleccionar"
        ] == True
    ].copy()

    st.success(
        "Destinatarios seleccionados: "
        f"{len(selected_df)}"
    )

    st.divider()

    st.subheader(
        "Paso 3 · Revisar y guardar"
    )

    with st.container(
        border=True
    ):
        st.write(
            f"**Campaña:** {campaign_name}"
        )

        st.write(
            "**Destinatarios:** "
            f"{len(selected_df)}"
        )

        if not selected_df.empty:
            selected_contact_count = (
                selected_df[
                    selected_df[
                        "recipient_type"
                    ]
                    == "CONTACTO"
                ].shape[0]
            )

            selected_institutional_count = (
                selected_df[
                    selected_df[
                        "recipient_type"
                    ]
                    == "INSTITUCIONAL"
                ].shape[0]
            )

            st.write(
                "**Composición:** "
                f"{selected_institutional_count} institucionales · "
                f"{selected_contact_count} contactos"
            )

        st.write(
            f"**Asunto:** {subject}"
        )

        with st.expander(
            "Revisar contenido completo"
        ):
            st.text(
                body_text
            )

    st.warning(
        "Al guardar se crea la campaña, "
        "pero todavía no se envían correos."
    )

    create_button = st.button(
        "Guardar campaña",
        type="primary",
        width="stretch",
    )

    if create_button:
        if not campaign_name.strip():
            st.error(
                "El nombre de la campaña es obligatorio."
            )
            return

        if not subject.strip():
            st.error(
                "El asunto es obligatorio."
            )
            return

        if not body_text.strip():
            st.error(
                "El contenido es obligatorio."
            )
            return

        if selected_df.empty:
            st.error(
                "Selecciona al menos un destinatario."
            )
            return

        campaign_id = create_campaign(
            name=campaign_name.strip(),
            campaign_type="CONTACTO_FRIO",
            objective=objective.strip(),
            subject=subject.strip(),
            body_text=body_text.strip(),
            user_id=user_id,
        )

        recipients_to_add = []

        selected_lookup = {
            (
                item["recipient_type"],
                int(
                    item["organization_id"]
                ),
                (
                    int(item["campus_id"])
                    if pd.notna(
                        item["campus_id"]
                    )
                    else None
                ),
                (
                    int(item["contact_id"])
                    if pd.notna(
                        item["contact_id"]
                    )
                    else None
                ),
                item["Correo"],
            ):
                item
            for _, item
            in working_df.iterrows()
        }

        for _, row in selected_df.iterrows():
            key = (
                row["recipient_type"],
                int(
                    row["organization_id"]
                ),
                (
                    int(row["campus_id"])
                    if pd.notna(
                        row["campus_id"]
                    )
                    else None
                ),
                (
                    int(row["contact_id"])
                    if pd.notna(
                        row["contact_id"]
                    )
                    else None
                ),
                row["Correo"],
            )

            original = (
                selected_lookup[
                    key
                ]
            )

            recipients_to_add.append(
                {
                    "recipient_type":
                        original[
                            "recipient_type"
                        ],
                    "organization_id":
                        int(
                            original[
                                "organization_id"
                            ]
                        ),
                    "organization_name":
                        original[
                            "Organización"
                        ],
                    "campus_id":
                        (
                            int(
                                original[
                                    "campus_id"
                                ]
                            )
                            if pd.notna(
                                original[
                                    "campus_id"
                                ]
                            )
                            else None
                        ),
                    "campus_name":
                        original[
                            "Plantel / unidad"
                        ],
                    "contact_id":
                        (
                            int(
                                original[
                                    "contact_id"
                                ]
                            )
                            if pd.notna(
                                original[
                                    "contact_id"
                                ]
                            )
                            else None
                        ),
                    "recipient_name":
                        original[
                            "Destinatario"
                        ],
                    "email":
                        original[
                            "Correo"
                        ],
                    "email_type":
                        (
                            "CONTACTO"
                            if original[
                                "recipient_type"
                            ]
                            == "CONTACTO"
                            else
                            "INSTITUCIONAL"
                        ),
                }
            )

        result = (
            add_multiple_campaign_recipients(
                campaign_id=campaign_id,
                recipients=recipients_to_add,
                user_id=user_id,
            )
        )

        st.session_state[
            "marketing_selected_campaign"
        ] = campaign_id

        st.success(
            "Campaña creada correctamente."
        )

        st.info(
            f"Se agregaron {result['added']} destinatarios. "
            f"Se omitieron {result['skipped']} duplicados. "
            "Siguiente paso: entra en Operar campaña "
            "y realiza el envío de prueba."
        )


# =========================================================
# OPERAR CAMPAÑA
# =========================================================

def render_operate_campaign(
    user_id: int,
):

    st.header(
        "Operar campaña"
    )

    st.caption(
        "Revisa el contenido, realiza la prueba y ejecuta los envíos."
    )

    context = select_campaign(
        "operate"
    )

    if context is None:
        return

    campaign_id = context[
        "campaign_id"
    ]

    campaign = context[
        "campaign"
    ]

    recipients = context[
        "recipients"
    ]

    counts = context[
        "counts"
    ]

    stage = context[
        "stage"
    ]

    st.divider()

    st.subheader(
        campaign["name"]
    )

    status_col1, status_col2 = (
        st.columns(
            [2, 1]
        )
    )

    status_col1.write(
        f"**Estado actual:** {stage}"
    )

    status_col2.write(
        "**Remitente:** "
        "soluciones@grupoasercom.com"
    )

    if counts["total"] > 0:
        completed = (
            counts["total"]
            - counts["pending"]
        )

        st.progress(
            completed
            / counts["total"]
        )

        st.caption(
            f"{completed} de "
            f"{counts['total']} destinatarios procesados"
        )

    metric1, metric2, metric3, metric4, metric5 = (
        st.columns(5)
    )

    metric1.metric(
        "Destinatarios",
        counts["total"],
    )

    metric2.metric(
        "Pendientes",
        counts["pending"],
    )

    metric3.metric(
        "Enviados",
        counts["sent"],
    )

    metric4.metric(
        "Rebotes",
        counts["bounces"],
    )

    metric5.metric(
        "Errores",
        counts["errors"],
    )

    test_ok = st.session_state.get(
        f"marketing_test_ok_{campaign_id}",
        False,
    )

    st.divider()

    with st.expander(
        "Revisar campaña",
        expanded=not test_ok,
    ):
        st.write(
            f"**Asunto:** {campaign['subject']}"
        )

        st.write(
            "**Destinatarios:** "
            f"{counts['total']}"
        )

        st.text(
            campaign["body_text"]
        )

        recipient_df = pd.DataFrame(
            [
                {
                    "Tipo":
                        row["recipient_type"],
                    "Organización":
                        row[
                            "organization_name_snapshot"
                        ],
                    "Plantel / unidad":
                        row[
                            "campus_name_snapshot"
                        ] or "",
                    "Destinatario":
                        recipient_display_name(
                            row
                        ),
                    "Correo":
                        row["email_address"],
                    "Estado":
                        row["status"],
                }
                for row in recipients
            ]
        )

        st.dataframe(
            recipient_df,
            hide_index=True,
            width="stretch",
        )

    smtp_config = (
        get_smtp_configuration()
    )

    if smtp_config is None:
        st.error(
            "No existe una configuración SMTP válida."
        )
        return

    with st.expander(
        "Realizar envío de prueba",
        expanded=not test_ok,
    ):
        test_recipient = st.text_input(
            "Enviar prueba a",
            placeholder="correo@dominio.com",
            key=(
                f"marketing_test_email_"
                f"{campaign_id}"
            ),
        )

        if st.button(
            "Enviar correo de prueba",
            width="stretch",
            key=(
                f"marketing_test_button_"
                f"{campaign_id}"
            ),
        ):
            test_recipient = (
                test_recipient
                or ""
            ).strip()

            if not test_recipient:
                st.error(
                    "Captura un correo de prueba."
                )
            else:
                with st.spinner(
                    "Enviando prueba..."
                ):
                    result = (
                        send_campaign_email(
                            smtp_host=(
                                smtp_config[
                                    "host"
                                ]
                            ),
                            smtp_port=(
                                smtp_config[
                                    "port"
                                ]
                            ),
                            smtp_user=(
                                smtp_config[
                                    "user"
                                ]
                            ),
                            smtp_password=(
                                smtp_config[
                                    "password"
                                ]
                            ),
                            smtp_security=(
                                smtp_config.get(
                                    "security",
                                    "starttls",
                                )
                            ),
                            imap_config=(
                                smtp_config[
                                    "imap"
                                ]
                            ),
                            recipient=(
                                test_recipient
                            ),
                            subject=(
                                campaign[
                                    "subject"
                                ]
                            ),
                            body_text=(
                                campaign[
                                    "body_text"
                                ]
                            ),
                            attachment_paths=[],
                        )
                    )

                if result["success"]:
                    st.session_state[
                        f"marketing_test_ok_"
                        f"{campaign_id}"
                    ] = True

                    st.success(
                        "Prueba enviada correctamente."
                    )
                    st.rerun()
                else:
                    st.error(
                        result["message"]
                    )

        if test_ok:
            st.success(
                "Prueba realizada. La campaña puede continuar al envío."
            )

    with st.expander(
        "Enviar campaña",
        expanded=(
            test_ok
            and counts["pending"] > 0
        ),
    ):
        if not test_ok:
            previous_test = (
                st.checkbox(
                    "Ya realicé y validé una prueba de esta campaña anteriormente.",
                    key=(
                        f"marketing_previous_test_"
                        f"{campaign_id}"
                    ),
                )
            )

            if previous_test:
                st.session_state[
                    f"marketing_test_ok_"
                    f"{campaign_id}"
                ] = True
                st.rerun()
            else:
                st.warning(
                    "Primero realiza un envío de prueba."
                )

        elif counts["pending"] == 0:
            st.success(
                "No quedan destinatarios pendientes de envío."
            )

        else:
            st.write(
                "Pendientes de envío: "
                f"**{counts['pending']}**"
            )

            batch_size = 5
            interval_seconds = 45

            with st.expander(
                "Opciones avanzadas"
            ):
                batch_size = st.number_input(
                    "Tamaño del lote",
                    min_value=1,
                    max_value=20,
                    value=5,
                    step=1,
                    key=(
                        f"batch_size_"
                        f"{campaign_id}"
                    ),
                )

                interval_seconds = (
                    st.number_input(
                        "Segundos entre correos",
                        min_value=15,
                        max_value=180,
                        value=45,
                        step=5,
                        key=(
                            f"batch_interval_"
                            f"{campaign_id}"
                        ),
                    )
                )

            next_batch_size = min(
                int(
                    batch_size
                ),
                counts["pending"],
            )

            batch_confirmation = (
                st.checkbox(
                    "Confirmo que revisé la campaña y deseo iniciar este lote.",
                    key=(
                        f"batch_confirm_"
                        f"{campaign_id}"
                    ),
                )
            )

            if st.button(
                (
                    "Enviar siguiente lote "
                    f"({next_batch_size})"
                ),
                type="primary",
                width="stretch",
                disabled=(
                    not batch_confirmation
                ),
                key=(
                    f"batch_send_"
                    f"{campaign_id}"
                ),
            ):
                with st.spinner(
                    "Procesando lote. No cierres esta ventana..."
                ):
                    batch_result = (
                        send_next_campaign_batch(
                            campaign_id=(
                                campaign_id
                            ),
                            user_id=user_id,
                            smtp_config=(
                                smtp_config
                            ),
                            batch_size=int(
                                batch_size
                            ),
                            interval_seconds=int(
                                interval_seconds
                            ),
                            imap_config=(
                                smtp_config[
                                    "imap"
                                ]
                            ),
                        )
                    )

                st.session_state[
                    f"last_batch_result_"
                    f"{campaign_id}"
                ] = batch_result

                st.rerun()

            last_result = (
                st.session_state.get(
                    f"last_batch_result_"
                    f"{campaign_id}"
                )
            )

            if last_result:
                st.markdown(
                    "#### Último lote procesado"
                )

                result1, result2, result3 = (
                    st.columns(3)
                )

                result1.metric(
                    "Procesados",
                    last_result[
                        "processed"
                    ],
                )

                result2.metric(
                    "Enviados",
                    last_result[
                        "sent"
                    ],
                )

                result3.metric(
                    "Errores",
                    last_result[
                        "errors"
                    ],
                )

                if last_result[
                    "results"
                ]:
                    st.dataframe(
                        pd.DataFrame(
                            last_result[
                                "results"
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )

            with st.expander(
                "Envío individual avanzado"
            ):
                pending_recipients = [
                    row
                    for row in recipients
                    if row["status"]
                    == "PENDIENTE"
                ]

                if not pending_recipients:
                    st.info(
                        "No hay destinatarios pendientes."
                    )
                else:
                    recipient_options = {
                        (
                            f"{row['organization_name_snapshot']} — "
                            f"{recipient_display_name(row)} — "
                            f"{row['email_address']}"
                        ):
                            row
                        for row
                        in pending_recipients
                    }

                    selected_label = (
                        st.selectbox(
                            "Destinatario",
                            options=list(
                                recipient_options.keys()
                            ),
                            key=(
                                f"individual_recipient_"
                                f"{campaign_id}"
                            ),
                        )
                    )

                    selected_recipient = (
                        recipient_options[
                            selected_label
                        ]
                    )

                    confirm = st.checkbox(
                        "Confirmo este envío individual.",
                        key=(
                            f"individual_confirm_"
                            f"{campaign_id}"
                        ),
                    )

                    if st.button(
                        "Enviar correo individual",
                        disabled=not confirm,
                        width="stretch",
                        key=(
                            f"individual_send_"
                            f"{campaign_id}"
                        ),
                    ):
                        result = (
                            send_single_campaign_recipient(
                                campaign_id=(
                                    campaign_id
                                ),
                                recipient_id=int(
                                    selected_recipient[
                                        "id"
                                    ]
                                ),
                                user_id=user_id,
                                smtp_config=(
                                    smtp_config
                                ),
                                imap_config=(
                                    smtp_config[
                                        "imap"
                                    ]
                                ),
                            )
                        )

                        if result[
                            "success"
                        ]:
                            st.success(
                                result["message"]
                            )
                            st.rerun()
                        else:
                            st.error(
                                result["message"]
                            )


# =========================================================
# INCIDENCIAS
# =========================================================

def render_incidents(
    user_id: int,
):

    st.header(
        "Incidencias"
    )

    st.caption(
        "Sincroniza el buzón, revisa errores y rebotes, "
        "corrige direcciones y conserva el historial."
    )

    context = select_campaign(
        "incidents"
    )

    if context is None:
        return

    campaign_id = context[
        "campaign_id"
    ]

    show_campaign_identity(
        context
    )

    smtp_config = (
        get_smtp_configuration()
    )

    if smtp_config is None:
        st.error(
            "No existe una configuración SMTP válida."
        )
        return

    st.divider()

    st.markdown(
        "### Sincronización del buzón"
    )

    mailbox_state = (
        get_mailbox_sync_state(
            "INBOX"
        )
    )

    sync_col1, sync_col2, sync_col3, sync_col4 = (
        st.columns(4)
    )

    sync_col1.metric(
        "Última revisión",
        (
            mailbox_state[
                "last_sync_at"
            ]
            if mailbox_state
            and mailbox_state[
                "last_sync_at"
            ]
            else "Sin ejecutar"
        ),
    )

    sync_col2.metric(
        "Rebotes aplicados",
        (
            mailbox_state[
                "last_bounces"
            ]
            if mailbox_state
            else 0
        ),
    )

    sync_col3.metric(
        "Respuestas aplicadas",
        (
            mailbox_state[
                "last_replies"
            ]
            if mailbox_state
            else 0
        ),
    )

    sync_col4.metric(
        "Sin coincidencia",
        (
            mailbox_state[
                "last_unmatched"
            ]
            if mailbox_state
            else 0
        ),
    )

    st.caption(
        "La bandeja se revisa únicamente cuando presionas este botón. "
        "Se mantiene el control incremental por UID."
    )

    if st.button(
        "Sincronizar bandeja ahora",
        type="primary",
        width="stretch",
        key=(
            f"sync_mailbox_now_"
            f"{campaign_id}"
        ),
    ):
        with st.spinner(
            "Revisando mensajes nuevos..."
        ):
            sync_result = (
                scan_mailbox(
                    host=(
                        smtp_config[
                            "imap"
                        ]["host"]
                    ),
                    port=(
                        smtp_config[
                            "imap"
                        ]["port"]
                    ),
                    user=(
                        smtp_config[
                            "imap"
                        ]["user"]
                    ),
                    password=(
                        smtp_config[
                            "imap"
                        ]["password"]
                    ),
                    user_id=user_id,
                    limit=500,
                    apply_changes=True,
                    mailbox="INBOX",
                    incremental=True,
                    source=(
                        "MANUAL_STREAMLIT"
                    ),
                )
            )

        if sync_result.get(
            "locked"
        ):
            st.warning(
                sync_result["message"]
            )

        elif sync_result.get(
            "success"
        ):
            st.success(
                "Sincronización terminada."
            )
            st.rerun()

        else:
            st.error(
                sync_result.get(
                    "message",
                    "No fue posible sincronizar el buzón.",
                )
            )

    with st.expander(
        "Historial reciente de sincronización"
    ):
        recent_runs = (
            get_recent_mailbox_sync_runs(
                limit=10
            )
        )

        if recent_runs:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Inicio":
                                row[
                                    "started_at"
                                ],
                            "Fin":
                                row[
                                    "finished_at"
                                ],
                            "Origen":
                                row[
                                    "source"
                                ],
                            "Estado":
                                row[
                                    "status"
                                ],
                            "Revisados":
                                row[
                                    "scanned"
                                ],
                            "Rebotes":
                                row[
                                    "bounces"
                                ],
                            "Respuestas":
                                row[
                                    "replies"
                                ],
                            "Sin coincidencia":
                                row[
                                    "unmatched"
                                ],
                            "Errores":
                                row[
                                    "errors"
                                ],
                        }
                        for row
                        in recent_runs
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info(
                "Todavía no existen ejecuciones registradas."
            )

    incidents = (
        get_active_delivery_incidents(
            campaign_id
        )
    )

    archived_rows = (
        get_archived_campaign_recipients(
            campaign_id
        )
    )

    st.divider()

    incident_col1, incident_col2, incident_col3 = (
        st.columns(3)
    )

    incident_col1.metric(
        "Errores inmediatos",
        sum(
            1
            for row in incidents
            if row["status"]
            == "ERROR"
        ),
    )

    incident_col2.metric(
        "Rebotes",
        sum(
            1
            for row in incidents
            if row["status"]
            == "REBOTE"
        ),
    )

    incident_col3.metric(
        "Históricos archivados",
        len(
            archived_rows
        ),
    )

    if not incidents:
        st.success(
            "No existen incidencias activas en esta campaña."
        )
        return

    incident_table = []

    for row in incidents:
        diagnosis = (
            row["bounce_reason"]
            or row["smtp_response"]
            or row["activity_details"]
            or "Sin diagnóstico técnico disponible."
        )

        incident_table.append(
            {
                "Tipo":
                    row[
                        "recipient_type"
                    ],
                "Organización":
                    row[
                        "organization_name_snapshot"
                    ],
                "Destinatario":
                    row[
                        "recipient_name_snapshot"
                    ] or "",
                "Plantel / unidad":
                    row[
                        "campus_name_snapshot"
                    ] or "",
                "Correo":
                    row[
                        "email_address"
                    ],
                "Estado":
                    row[
                        "status"
                    ],
                "Código":
                    row[
                        "bounce_code"
                    ] or "",
                "Intentos":
                    row[
                        "attempt_count"
                    ],
                "Diagnóstico":
                    diagnosis,
            }
        )

    st.dataframe(
        pd.DataFrame(
            incident_table
        ),
        hide_index=True,
        width="stretch",
    )

    incident_options = {
        (
            f"{row['organization_name_snapshot']} — "
            f"{row['recipient_name_snapshot'] or row['campus_name_snapshot'] or ''} — "
            f"{row['email_address']} "
            f"[{row['status']}]"
        ):
            row
        for row in incidents
    }

    selected_incident_label = (
        st.selectbox(
            "Incidencia para revisar",
            options=list(
                incident_options.keys()
            ),
            key=(
                f"delivery_incident_"
                f"{campaign_id}"
            ),
        )
    )

    selected_incident = (
        incident_options[
            selected_incident_label
        ]
    )

    diagnosis = (
        selected_incident[
            "bounce_reason"
        ]
        or selected_incident[
            "smtp_response"
        ]
        or selected_incident[
            "activity_details"
        ]
        or "Sin diagnóstico técnico disponible."
    )

    st.markdown(
        "#### Diagnóstico"
    )

    detail1, detail2 = (
        st.columns(2)
    )

    detail1.write(
        "**Organización:** "
        f"{selected_incident['organization_name_snapshot']}"
    )

    detail1.write(
        "**Destinatario:** "
        f"{selected_incident['recipient_name_snapshot'] or ''}"
    )

    detail2.write(
        "**Correo actual:** "
        f"{selected_incident['email_address']}"
    )

    detail2.write(
        "**Estado / código:** "
        f"{selected_incident['status']} / "
        f"{selected_incident['bounce_code'] or 'N/D'}"
    )

    st.error(
        diagnosis
    )

    corrected_email = st.text_input(
        "Correo corregido y validado",
        placeholder="usuario@dominio.mx",
        key=(
            f"corrected_email_"
            f"{selected_incident['id']}"
        ),
    )

    correction_reason = st.text_area(
        "Motivo de la corrección",
        value=(
            "Corrección después de una incidencia de entrega."
        ),
        key=(
            f"correction_reason_"
            f"{selected_incident['id']}"
        ),
    )

    update_master = st.checkbox(
        "Actualizar también la base maestra",
        value=True,
        key=(
            f"update_master_"
            f"{selected_incident['id']}"
        ),
    )

    correction_confirm = st.checkbox(
        "Confirmo archivar el registro anterior "
        "y crear el correo corregido como PENDIENTE.",
        key=(
            f"correction_confirm_"
            f"{selected_incident['id']}"
        ),
    )

    if st.button(
        "Guardar corrección y preparar reenvío",
        type="primary",
        width="stretch",
        disabled=(
            not correction_confirm
        ),
        key=(
            f"save_correction_"
            f"{selected_incident['id']}"
        ),
    ):
        try:
            correction_result = (
                correct_campaign_recipient_email(
                    recipient_id=int(
                        selected_incident[
                            "id"
                        ]
                    ),
                    new_email=(
                        corrected_email
                    ),
                    user_id=user_id,
                    reason=(
                        correction_reason
                    ),
                    update_master=(
                        update_master
                    ),
                )
            )

            st.success(
                "Correo corregido. "
                f"Anterior: {correction_result['old_email']}. "
                f"Nuevo: {correction_result['new_email']}. "
                "El nuevo registro quedó PENDIENTE."
            )

            st.rerun()

        except Exception as exc:
            st.error(
                str(exc)
            )

    st.divider()

    archive_reason = st.text_input(
        "Motivo para archivar valores inválidos",
        value=(
            "Valores anteriores sustituidos "
            "después de corregir la base maestra."
        ),
        key=(
            f"archive_reason_"
            f"{campaign_id}"
        ),
    )

    archive_confirm = st.checkbox(
        "Confirmo archivar los valores inválidos.",
        key=(
            f"archive_confirm_"
            f"{campaign_id}"
        ),
    )

    if st.button(
        "Archivar valores inválidos",
        width="stretch",
        disabled=(
            not archive_confirm
        ),
        key=(
            f"archive_invalid_"
            f"{campaign_id}"
        ),
    ):
        try:
            archive_result = (
                archive_invalid_error_recipients(
                    campaign_id=(
                        campaign_id
                    ),
                    user_id=user_id,
                    reason=(
                        archive_reason
                    ),
                )
            )

            st.success(
                "Registros archivados: "
                f"{archive_result['archived']}."
            )

            st.rerun()

        except Exception as exc:
            st.error(
                str(exc)
            )


# =========================================================
# SEGUIMIENTO
# =========================================================

def render_followup(
    user_id: int,
):

    st.header(
        "Seguimiento"
    )

    st.caption(
        "Clasifica respuestas, contactos referidos, "
        "falta de respuesta y resultados comerciales."
    )

    context = select_campaign(
        "followup"
    )

    if context is None:
        return

    campaign_id = context[
        "campaign_id"
    ]

    recipients = context[
        "recipients"
    ]

    counts = context[
        "counts"
    ]

    show_campaign_identity(
        context
    )

    follow1, follow2, follow3 = (
        st.columns(3)
    )

    follow1.metric(
        "Respuestas",
        counts["responses"],
    )

    follow2.metric(
        "Contactos obtenidos",
        counts["referred"],
    )

    follow3.metric(
        "Esperando respuesta",
        counts["waiting"],
    )

    followup_recipients = [
        row
        for row in recipients
        if row["status"] in {
            "ENVIADO",
            "RESPONDIO",
            "CONTACTO_REFERIDO",
            "SIN_RESPUESTA",
            "NO_INTERESADO",
        }
    ]

    if not followup_recipients:
        st.info(
            "Todavía no existen envíos para dar seguimiento."
        )
        return

    followup_options = {
        (
            f"{row['organization_name_snapshot']} — "
            f"{recipient_display_name(row)} — "
            f"{row['email_address']} "
            f"[{row['status']}]"
        ):
            row
        for row
        in followup_recipients
    }

    selected_follow_label = (
        st.selectbox(
            "Destinatario / correo",
            options=list(
                followup_options.keys()
            ),
            key=(
                f"follow_recipient_"
                f"{campaign_id}"
            ),
        )
    )

    selected_follow = (
        followup_options[
            selected_follow_label
        ]
    )

    response_type = st.radio(
        "¿Qué ocurrió?",
        options=[
            "Mostró interés / respondió",
            "Proporcionó un contacto",
            "Sin respuesta",
            "No está interesado",
            "Correo rechazado / rebote",
        ],
        key=(
            f"follow_type_"
            f"{campaign_id}"
        ),
    )

    recipient_id = int(
        selected_follow["id"]
    )

    if (
        response_type
        == "Proporcionó un contacto"
    ):
        st.markdown(
            "#### Datos del contacto referido"
        )

        referred_name = st.text_input(
            "Nombre",
            key=(
                f"ref_name_"
                f"{recipient_id}"
            ),
        )

        referred_position = (
            st.text_input(
                "Puesto",
                key=(
                    f"ref_position_"
                    f"{recipient_id}"
                ),
            )
        )

        referred_email = st.text_input(
            "Correo",
            key=(
                f"ref_email_"
                f"{recipient_id}"
            ),
        )

        referred_phone = st.text_input(
            "Teléfono",
            key=(
                f"ref_phone_"
                f"{recipient_id}"
            ),
        )

        referred_notes = st.text_area(
            "Observaciones",
            key=(
                f"ref_notes_"
                f"{recipient_id}"
            ),
        )

        if st.button(
            "Guardar contacto referido",
            type="primary",
            width="stretch",
            key=(
                f"save_ref_"
                f"{recipient_id}"
            ),
        ):
            if not referred_name.strip():
                st.error(
                    "Captura al menos el nombre del contacto."
                )
            else:
                register_referred_contact(
                    recipient_id=(
                        recipient_id
                    ),
                    name=(
                        referred_name.strip()
                    ),
                    position=(
                        referred_position.strip()
                    ),
                    email=(
                        referred_email.strip()
                    ),
                    phone=(
                        referred_phone.strip()
                    ),
                    notes=(
                        referred_notes.strip()
                    ),
                    user_id=user_id,
                )

                st.success(
                    "Contacto referido guardado."
                )

                st.rerun()

    else:
        notes = st.text_area(
            "Observaciones",
            key=(
                f"follow_notes_"
                f"{recipient_id}"
            ),
        )

        status_map = {
            "Mostró interés / respondió":
                "RESPONDIO",
            "Sin respuesta":
                "SIN_RESPUESTA",
            "No está interesado":
                "NO_INTERESADO",
            "Correo rechazado / rebote":
                "REBOTE",
        }

        new_status = (
            status_map[
                response_type
            ]
        )

        if st.button(
            "Registrar seguimiento",
            type="primary",
            width="stretch",
            key=(
                f"save_follow_"
                f"{recipient_id}"
            ),
        ):
            update_recipient_status(
                recipient_id=(
                    recipient_id
                ),
                status=new_status,
                user_id=user_id,
                details=(
                    notes.strip()
                    or response_type
                ),
            )

            st.success(
                "Seguimiento registrado."
            )

            st.rerun()


# =========================================================
# PANTALLA PRINCIPAL
# =========================================================

def render():

    st.title(
        "Marketing"
    )

    st.caption(
        "Creación, segmentación, operación, incidencias "
        "y seguimiento de campañas."
    )

    user = st.session_state.get(
        "user",
        {},
    )

    user_id = user.get(
        "id"
    )

    if not user_id:
        st.error(
            "No se pudo identificar al usuario activo."
        )
        return

    tabs = st.tabs(
        [
            "1. Crear",
            "2. Operar",
            "3. Incidencias",
            "4. Seguimiento",
        ]
    )

    with tabs[0]:
        render_create_campaign(
            user_id
        )

    with tabs[1]:
        render_operate_campaign(
            user_id
        )

    with tabs[2]:
        render_incidents(
            user_id
        )

    with tabs[3]:
        render_followup(
            user_id
        )


render()
