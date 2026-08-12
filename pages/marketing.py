import pandas as pd
import streamlit as st

from database.repositories.marketing import (
    add_multiple_campaign_recipients,
    create_campaign,
    get_campaign,
    get_campaign_recipients,
    get_campaigns,
    archive_invalid_error_recipients,
    correct_campaign_recipient_email,
    get_active_delivery_incidents,
    get_archived_campaign_recipients,
    get_eligible_campuses,
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
    "Realizar un primer contacto en frío con instituciones educativas, "
    "presentar a Grupo Asercom, detectar proyectos tecnológicos en puerta "
    "y obtener al contacto responsable dentro del plantel."
)

DEFAULT_SUBJECT = (
    "Presentación Grupo Asercom | Soluciones tecnológicas para educación"
)

DEFAULT_BODY = """Hola, muy buen día:

Mi nombre es Patricia Aguirre y formo parte de Grupo Asercom.

Me pongo en contacto para presentarnos y compartir brevemente algunas de las soluciones tecnológicas que integramos para instituciones educativas, orientadas a modernizar espacios, fortalecer la experiencia de aprendizaje y apoyar proyectos de transformación tecnológica.

Trabajamos principalmente en:

• Aulas interactivas y pantallas inteligentes, para crear entornos de enseñanza más dinámicos y participativos.

• Soluciones STEM, integrando tecnologías como robótica, fabricación aditiva, realidad virtual, Inteligencia Artificial e Internet de las Cosas (IoT).

• Soluciones audiovisuales y experiencias inmersivas, para auditorios, eventos, espacios comunes y proyectos de comunicación e interacción.

Nos gustaría conocer si actualmente tienen en puerta algún proyecto o están evaluando incorporar nuevas tecnologías en su institución.

En caso de que sea un tema de interés, con gusto podemos coordinar una breve llamada de 10 minutos para presentarnos y conocer un poco más sobre sus necesidades.

Si usted no es la persona responsable de este tipo de proyectos, le agradecería mucho si pudiera orientarme sobre con quién sería conveniente establecer contacto.

Muchas gracias por su tiempo.

Saludos cordiales,"""


# =========================================================
# UTILIDADES
# =========================================================

def rows_to_dataframe(rows):
    return pd.DataFrame(
        [
            {
                "campus_id": row["campus_id"],
                "Organización": row["official_name"],
                "Subsistema": row["subsystem"] or "",
                "Plantel": row["campus_name"],
                "Municipio": row["municipality"] or "",
                "Estado": row["state"] or "",
                "Correo": row["email"],
                "Tipo correo": row["email_type"] or "",
                "Principal": bool(row["is_primary"]),
            }
            for row in rows
        ]
    )


def get_smtp_configuration():
    """Lee SMTP e IMAP desde .streamlit/secrets.toml."""

    try:
        smtp = st.secrets["smtp"]
        imap = st.secrets["imap"]

        config = {
            "host": smtp.get("host", ""),
            "port": int(smtp.get("port", 587)),
            "security": smtp.get("security", "starttls"),
            "user": smtp.get("user", ""),
            "password": smtp.get("password", ""),
            "imap": {
                "host": imap.get("host", ""),
                "port": int(imap.get("port", 993)),
                "user": imap.get("user", ""),
                "password": imap.get("password", ""),
                "sent_folder": imap.get(
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

        return config if all(required) else None

    except Exception:
        return None


def calculate_campaign_counts(recipients):
    total = len(recipients)

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
        if row["status"] == "CONTACTO_REFERIDO"
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
        "total": total,
        "pending": pending,
        "sent": sent,
        "errors": errors,
        "bounces": bounces,
        "responses": responses,
        "referred": referred,
        "waiting": waiting,
    }


def get_campaign_stage(
    campaign_id,
    recipients,
):
    """
    Devuelve un estado de operación amigable.

    No modifica el estado interno de SQLite.
    """

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
        counts["pending"] == counts["total"]
        and not test_ok
    ):
        return "PREPARAR"

    if (
        counts["pending"] == counts["total"]
        and test_ok
    ):
        return "PREPARADA"

    if counts["pending"] > 0:
        return "EN_PROCESO"

    if counts["responses"] > 0:
        return "EN_SEGUIMIENTO"

    return "ENVIADA"


def show_step_header(
    number,
    title,
    status,
):
    if status == "done":
        icon = "✓"
    elif status == "active":
        icon = "→"
    else:
        icon = "○"

    st.markdown(
        f"**{icon} {number}. {title}**"
    )


# =========================================================
# PANTALLA
# =========================================================


def select_campaign(section_key: str):
    """Carga una campaña en una sección sin duplicar lógica."""

    campaigns = get_campaigns()

    if not campaigns:
        st.info("Primero debes crear una campaña.")
        return None

    campaign_options = {
        f"{row['id']} - {row['name']}": row["id"]
        for row in campaigns
    }

    labels = list(campaign_options.keys())
    selected_stored = st.session_state.get(
        "marketing_selected_campaign"
    )
    default_index = 0

    if selected_stored:
        for index, label in enumerate(labels):
            if campaign_options[label] == selected_stored:
                default_index = index
                break

    selected_label = st.selectbox(
        "Campaña",
        options=labels,
        index=default_index,
        key=f"campaign_selector_{section_key}",
    )

    campaign_id = campaign_options[selected_label]
    st.session_state["marketing_selected_campaign"] = campaign_id

    campaign = get_campaign(campaign_id)
    recipients = get_campaign_recipients(campaign_id)

    if campaign is None:
        st.error("No fue posible cargar la campaña.")
        return None

    counts = calculate_campaign_counts(recipients)
    stage = get_campaign_stage(campaign_id, recipients)

    return {
        "campaign_id": campaign_id,
        "campaign": campaign,
        "recipients": recipients,
        "counts": counts,
        "stage": stage,
    }


def show_campaign_identity(context):
    campaign = context["campaign"]
    counts = context["counts"]

    st.subheader(campaign["name"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Destinatarios", counts["total"])
    c2.metric("Pendientes", counts["pending"])
    c3.metric("Rebotes", counts["bounces"])
    c4.metric("Errores", counts["errors"])


def render_create_campaign(user_id: int):

    st.header(
        "Crear nueva campaña"
    )

    st.info(
        "Sigue los pasos en orden. Crear la campaña "
        "no envía ningún correo."
    )

    # =================================================
    # PASO 1
    # =================================================

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
        height=520,
    )

    st.divider()

    # =================================================
    # PASO 2
    # =================================================

    st.subheader(
        "Paso 2 · Seleccionar destinatarios"
    )

    st.caption(
        "Filtra primero el segmento de instituciones "
        "que formará parte de esta campaña."
    )

    eligible_rows = get_eligible_campuses()

    if not eligible_rows:

        st.warning(
            "No existen planteles con correo institucional activo."
        )

    else:

        df = rows_to_dataframe(
            eligible_rows
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Correos disponibles",
            len(df),
        )

        col2.metric(
            "Planteles",
            df["campus_id"].nunique(),
        )

        col3.metric(
            "Subsistemas",
            df["Subsistema"]
            .replace("", pd.NA)
            .dropna()
            .nunique(),
        )

        subsystem_options = sorted(
            [
                value
                for value
                in df["Subsistema"]
                .dropna()
                .unique()
                if value
            ]
        )

        state_options = sorted(
            [
                value
                for value
                in df["Estado"]
                .dropna()
                .unique()
                if value
            ]
        )

        selected_subsystems = st.multiselect(
            "Subsistema",
            options=subsystem_options,
        )

        selected_states = st.multiselect(
            "Estado",
            options=state_options,
        )

        filtered_df = df.copy()

        if selected_subsystems:
            filtered_df = filtered_df[
                filtered_df["Subsistema"].isin(
                    selected_subsystems
                )
            ]

        if selected_states:
            filtered_df = filtered_df[
                filtered_df["Estado"].isin(
                    selected_states
                )
            ]

        municipality_options = sorted(
            [
                value
                for value
                in filtered_df["Municipio"]
                .dropna()
                .unique()
                if value
            ]
        )

        selected_municipalities = st.multiselect(
            "Municipio",
            options=municipality_options,
        )

        if selected_municipalities:
            filtered_df = filtered_df[
                filtered_df["Municipio"].isin(
                    selected_municipalities
                )
            ]

        filtered_df = filtered_df.reset_index(
            drop=True
        )

        filtered_df.insert(
            0,
            "Seleccionar",
            True,
        )

        st.write(
            f"Registros encontrados: "
            f"**{len(filtered_df)}**"
        )

        edited_df = st.data_editor(
            filtered_df[
                [
                    "Seleccionar",
                    "Organización",
                    "Subsistema",
                    "Plantel",
                    "Municipio",
                    "Correo",
                    "Principal",
                    "campus_id",
                ]
            ],
            hide_index=True,
            width="stretch",
            disabled=[
                "Organización",
                "Subsistema",
                "Plantel",
                "Municipio",
                "Correo",
                "Principal",
                "campus_id",
            ],
            column_config={
                "Seleccionar":
                    st.column_config.CheckboxColumn(
                        "Incluir"
                    ),
                "campus_id": None,
            },
            key="marketing_recipients_editor",
        )

        selected_df = edited_df[
            edited_df["Seleccionar"] == True
        ].copy()

        st.success(
            f"Destinatarios seleccionados: "
            f"{len(selected_df)}"
        )

        st.divider()

        # =================================================
        # PASO 3
        # =================================================

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
                f"**Destinatarios:** "
                f"{len(selected_df)}"
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

            elif not subject.strip():

                st.error(
                    "El asunto es obligatorio."
                )

            elif not body_text.strip():

                st.error(
                    "El contenido es obligatorio."
                )

            elif selected_df.empty:

                st.error(
                    "Selecciona al menos un destinatario."
                )

            else:

                campaign_id = create_campaign(
                    name=campaign_name.strip(),
                    campaign_type="CONTACTO_FRIO",
                    objective=objective.strip(),
                    subject=subject.strip(),
                    body_text=body_text.strip(),
                    user_id=user_id,
                )

                recipients_to_add = []

                for _, row in (
                    selected_df.iterrows()
                ):

                    recipients_to_add.append(
                        {
                            "campus_id": int(
                                row["campus_id"]
                            ),
                            "campus_name":
                                row["Plantel"],
                            "email":
                                row["Correo"],
                            "email_type":
                                "INSTITUCIONAL",
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
                    f"Se agregaron "
                    f"{result['added']} destinatarios.\n\n"
                    "Siguiente paso: entra en "
                    "**Operar campaña** y realiza "
                    "el envío de prueba."
                )


def render_operate_campaign(user_id: int):
    st.header("Operar campaña")
    st.caption(
        "Revisa el contenido, realiza la prueba y ejecuta los envíos. "
        "Los errores técnicos se gestionan en Incidencias."
    )

    context = select_campaign("operate")
    if context is None:
        return

    selected_campaign_id = context["campaign_id"]
    campaign = context["campaign"]
    recipients = context["recipients"]
    counts = context["counts"]
    stage = context["stage"]
    # =================================================
    # ESTADO GENERAL
    # =================================================

    st.divider()

    st.subheader(
        campaign["name"]
    )

    status_col1, status_col2 = st.columns(
        [2, 1]
    )

    status_col1.write(
        f"**Estado actual:** {stage}"
    )

    status_col2.write(
        f"**Remitente:** "
        f"soluciones@grupoasercom.com"
    )

    if counts["total"] > 0:

        completed = (
            counts["total"]
            - counts["pending"]
        )

        progress = (
            completed
            / counts["total"]
        )

        st.progress(
            progress
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
        "Errores inmediatos",
        counts["errors"],
    )

    # =================================================
    # SIGUIENTE PASO
    # =================================================

    st.divider()

    st.markdown(
        "### Siguiente paso recomendado"
    )

    test_ok = st.session_state.get(
        f"marketing_test_ok_{selected_campaign_id}",
        False,
    )

    if (
        counts["pending"] == counts["total"]
        and not test_ok
    ):

        st.info(
            "Revisa el contenido y realiza un "
            "**envío de prueba** antes de iniciar "
            "la campaña."
        )

    elif counts["pending"] > 0:

        st.info(
            "La campaña tiene destinatarios pendientes. "
            "Continúa con el siguiente lote."
        )

    elif (
        counts["errors"] > 0
        or counts["bounces"] > 0
    ):

        st.warning(
            "El envío terminó, pero existen incidencias "
            "de entrega. Abre la pestaña **Incidencias** "
            "para revisar el diagnóstico, corregir el "
            "correo y preparar el reenvío."
        )

    else:

        st.success(
            "El envío de la campaña terminó sin "
            "incidencias activas. Continúa con "
            "el seguimiento de respuestas."
        )
    # =================================================
    # PASO 1 - REVISAR
    # =================================================

    st.divider()

    with st.expander(
        "Revisar campaña",
        expanded=not test_ok,
    ):

        st.write(
            f"**Asunto:** "
            f"{campaign['subject']}"
        )

        st.write(
            f"**Destinatarios:** "
            f"{counts['total']}"
        )

        st.text(
            campaign["body_text"]
        )

        recipient_df = pd.DataFrame(
            [
                {
                    "Plantel":
                        row["campus_name_snapshot"],
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


    smtp_config = get_smtp_configuration()

    if smtp_config is None:
        st.error("No existe una configuración SMTP válida.")
        return

    with st.expander(
        "Realizar envío de prueba",
        expanded=(
            not test_ok
        ),
    ):

        st.caption(
            "El correo de prueba usa exactamente "
            "el asunto, cuerpo y cintilla de esta campaña. "
            "No modifica ningún prospecto."
        )

        st.write(
            f"**De:** "
            f"{smtp_config['user']}"
        )

        test_recipient = st.text_input(
            "Enviar prueba a",
            placeholder="correo@dominio.com",
            key=(
                f"marketing_test_email_"
                f"{selected_campaign_id}"
            ),
        )

        if st.button(
            "Enviar correo de prueba",
            width="stretch",
            key=(
                f"marketing_test_button_"
                f"{selected_campaign_id}"
            ),
        ):

            test_recipient = (
                test_recipient or ""
            ).strip()

            if not test_recipient:

                st.error(
                    "Captura un correo de prueba."
                )

            else:

                with st.spinner(
                    "Enviando prueba..."
                ):

                    result = send_campaign_email(
                        smtp_host=smtp_config["host"],
                        smtp_port=smtp_config["port"],
                        smtp_user=smtp_config["user"],
                        smtp_password=smtp_config[
                            "password"
                        ],
                        smtp_security=smtp_config.get(
                            "security",
                            "starttls",
                        ),
                        imap_config=smtp_config["imap"],
                        recipient=test_recipient,
                        subject=campaign["subject"],
                        body_text=campaign[
                            "body_text"
                        ],
                        attachment_paths=[],
                    )

                if result["success"]:

                    st.session_state[
                        f"marketing_test_ok_"
                        f"{selected_campaign_id}"
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
                "Prueba realizada. "
                "La campaña puede continuar al envío."
            )

    # =================================================
    # PASO 3 - ENVÍO
    # =================================================

    with st.expander(
        "Enviar campaña",
        expanded=(
            test_ok
            and counts["pending"] > 0
        ),
    ):

        if not test_ok:

            previous_test = st.checkbox(
                (
                    "Ya realicé y validé una prueba "
                    "de esta campaña anteriormente."
                ),
                key=(
                    f"marketing_previous_test_"
                    f"{selected_campaign_id}"
                ),
            )

            if previous_test:

                st.session_state[
                    f"marketing_test_ok_"
                    f"{selected_campaign_id}"
                ] = True

                st.rerun()

            else:

                st.warning(
                    "Primero realiza un envío de prueba."
                )

        else:

            if counts["pending"] == 0:

                st.success(
                    "No quedan destinatarios "
                    "pendientes de envío."
                )

            else:

                st.write(
                    f"Pendientes de envío: "
                    f"**{counts['pending']}**"
                )

                st.info(
                    "Modo recomendado: 5 correos "
                    "por lote con 45 segundos "
                    "entre mensajes."
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
                            f"{selected_campaign_id}"
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
                                f"{selected_campaign_id}"
                            ),
                        )
                    )

                next_batch_size = min(
                    int(batch_size),
                    counts["pending"],
                )

                st.write(
                    "El siguiente lote enviará "
                    f"**{next_batch_size} correo(s)**."
                )

                st.write(
                    "Los destinatarios que ya estén "
                    "marcados como ENVIADO "
                    "**no se volverán a procesar**."
                )

                batch_confirmation = st.checkbox(
                    (
                        "Confirmo que revisé la campaña "
                        "y deseo iniciar este lote."
                    ),
                    key=(
                        f"batch_confirm_"
                        f"{selected_campaign_id}"
                    ),
                )

                if st.button(
                    (
                        f"Enviar siguiente lote "
                        f"({next_batch_size})"
                    ),
                    type="primary",
                    width="stretch",
                    disabled=(
                        not batch_confirmation
                    ),
                    key=(
                        f"batch_send_"
                        f"{selected_campaign_id}"
                    ),
                ):

                    with st.spinner(
                        "Procesando lote. "
                        "No cierres esta ventana..."
                    ):

                        batch_result = (
                            send_next_campaign_batch(
                                campaign_id=(
                                    selected_campaign_id
                                ),
                                user_id=user_id,
                                smtp_config=smtp_config,
                                batch_size=int(
                                    batch_size
                                ),
                                interval_seconds=int(
                                    interval_seconds
                                ),
                                imap_config=smtp_config["imap"],
                            )
                        )

                    st.session_state[
                        f"last_batch_result_"
                        f"{selected_campaign_id}"
                    ] = batch_result

                    st.rerun()

                last_result = st.session_state.get(
                    f"last_batch_result_"
                    f"{selected_campaign_id}"
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

                    st.write(
                        f"Pendientes: "
                        f"**{last_result['remaining']}**"
                    )

                    if last_result["results"]:

                        st.dataframe(
                            pd.DataFrame(
                                last_result[
                                    "results"
                                ]
                            ),
                            hide_index=True,
                            width="stretch",
                        )

                # =====================================
                # ENVÍO INDIVIDUAL AVANZADO
                # =====================================

                with st.expander(
                    "Envío individual avanzado"
                ):

                    pending_recipients = [
                        row
                        for row in recipients
                        if row["status"]
                        == "PENDIENTE"
                    ]

                    if pending_recipients:

                        recipient_options = {
                            (
                                f"{row['campus_name_snapshot']} "
                                f"— {row['email_address']}"
                            ):
                                row
                            for row
                            in pending_recipients
                        }

                        selected_label = st.selectbox(
                            "Destinatario",
                            options=list(
                                recipient_options.keys()
                            ),
                            key=(
                                f"individual_recipient_"
                                f"{selected_campaign_id}"
                            ),
                        )

                        selected_recipient = (
                            recipient_options[
                                selected_label
                            ]
                        )

                        individual_confirm = (
                            st.checkbox(
                                (
                                    "Confirmo este "
                                    "envío individual."
                                ),
                                key=(
                                    f"individual_confirm_"
                                    f"{selected_campaign_id}"
                                ),
                            )
                        )

                        if st.button(
                            "Enviar correo individual",
                            disabled=(
                                not individual_confirm
                            ),
                            width="stretch",
                            key=(
                                f"individual_send_"
                                f"{selected_campaign_id}"
                            ),
                        ):

                            result = send_single_campaign_recipient(
                                campaign_id=selected_campaign_id,
                                recipient_id=int(
                                    selected_recipient["id"]
                                ),
                                user_id=user_id,
                                smtp_config=smtp_config,
                                imap_config=smtp_config["imap"],
                            )

                            if result["success"]:
                                st.success(result["message"])

                                if result.get(
                                    "sent_folder_saved",
                                    False,
                                ):
                                    st.info(
                                        "Copia guardada en INBOX.Sent."
                                    )
                                else:
                                    st.warning(
                                        "SMTP aceptó el mensaje, pero "
                                        "no se guardó la copia IMAP."
                                    )

                                st.rerun()

                            else:
                                st.error(result["message"])



def render_incidents(user_id: int):
    st.header("Incidencias")
    st.caption(
        "Sincroniza el buzón, revisa errores inmediatos y rebotes, "
        "corrige direcciones y deja los reenvíos como PENDIENTE."
    )

    context = select_campaign("incidents")
    if context is None:
        return

    selected_campaign_id = context["campaign_id"]
    campaign = context["campaign"]
    recipients = context["recipients"]
    counts = context["counts"]
    stage = context["stage"]

    show_campaign_identity(context)
    # =================================================
    # SMTP
    # =================================================

    smtp_config = get_smtp_configuration()

    if smtp_config is None:

        st.error(
            "No existe una configuración SMTP válida."
        )
        return

    # =================================================
    # SINCRONIZACIÓN DEL BUZÓN
    # =================================================

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
            mailbox_state["last_sync_at"]
            if mailbox_state
            and mailbox_state["last_sync_at"]
            else "Sin ejecutar"
        ),
    )

    sync_col2.metric(
        "Rebotes aplicados",
        (
            mailbox_state["last_bounces"]
            if mailbox_state
            else 0
        ),
    )

    sync_col3.metric(
        "Respuestas aplicadas",
        (
            mailbox_state["last_replies"]
            if mailbox_state
            else 0
        ),
    )

    sync_col4.metric(
        "Sin coincidencia",
        (
            mailbox_state["last_unmatched"]
            if mailbox_state
            else 0
        ),
    )

    if (
        mailbox_state
        and mailbox_state["last_error"]
    ):
        st.error(
            mailbox_state["last_error"]
        )

    st.caption(
        "La tarea de Windows revisa INBOX cada 10 minutos. "
        "El botón permite forzar una revisión inmediata."
    )

    if st.button(
        "Sincronizar bandeja ahora",
        type="primary",
        width="stretch",
        key=(
            f"sync_mailbox_now_"
            f"{selected_campaign_id}"
        ),
    ):

        with st.spinner(
            "Revisando mensajes nuevos..."
        ):
            sync_result = scan_mailbox(
                host=smtp_config["imap"]["host"],
                port=smtp_config["imap"]["port"],
                user=smtp_config["imap"]["user"],
                password=smtp_config["imap"]["password"],
                user_id=user_id,
                limit=500,
                apply_changes=True,
                mailbox="INBOX",
                incremental=True,
                source="STREAMLIT",
            )

        if sync_result.get("locked"):
            st.warning(
                sync_result["message"]
            )

        elif sync_result.get("success"):
            st.success(
                (
                    "Sincronización terminada. "
                    f"Mensajes nuevos: "
                    f"{sync_result['scanned']}; "
                    f"rebotes aplicados: "
                    f"{sync_result['applied_bounces']}; "
                    f"respuestas aplicadas: "
                    f"{sync_result['applied_replies']}."
                )
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
                            "Inicio": row["started_at"],
                            "Fin": row["finished_at"],
                            "Origen": row["source"],
                            "Estado": row["status"],
                            "Revisados": row["scanned"],
                            "Rebotes": row["bounces"],
                            "Respuestas": row["replies"],
                            "Sin coincidencia": row["unmatched"],
                            "Errores": row["errors"],
                        }
                        for row in recent_runs
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info(
                "Todavía no existen ejecuciones registradas."
            )


    # =================================================
    # DEPURAR HISTORIAL Y CORREGIR ERRORES
    # =================================================

    # =================================================
    # INCIDENCIAS DE ENTREGA
    # =================================================

    incidents = (
        get_active_delivery_incidents(
            selected_campaign_id
        )
    )

    with st.expander(
        (
            "Incidencias de entrega "
            f"({len(incidents)})"
        ),
        expanded=bool(incidents),
    ):

        st.caption(
            "Aquí aparecen los errores inmediatos y los "
            "rebotes detectados después del envío. "
            "Cada incidencia muestra el diagnóstico y "
            "permite corregir el correo para reenviarlo."
        )

        archived_rows = (
            get_archived_campaign_recipients(
                selected_campaign_id
            )
        )

        incident_col1, incident_col2, incident_col3 = (
            st.columns(3)
        )

        incident_col1.metric(
            "Errores inmediatos",
            sum(
                1
                for row in incidents
                if row["status"] == "ERROR"
            ),
        )

        incident_col2.metric(
            "Rebotes",
            sum(
                1
                for row in incidents
                if row["status"] == "REBOTE"
            ),
        )

        incident_col3.metric(
            "Históricos archivados",
            len(archived_rows),
        )

        if not incidents:

            st.success(
                "No existen incidencias activas "
                "en esta campaña."
            )

        else:

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
                        "Plantel":
                            row["campus_name_snapshot"],
                        "Correo":
                            row["email_address"],
                        "Tipo":
                            row["status"],
                        "Código":
                            row["bounce_code"] or "",
                        "Intentos":
                            row["attempt_count"],
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
                    f"{row['campus_name_snapshot']} "
                    f"— {row['email_address']} "
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
                        f"{selected_campaign_id}"
                    ),
                )
            )

            selected_incident = (
                incident_options[
                    selected_incident_label
                ]
            )

            diagnosis = (
                selected_incident["bounce_reason"]
                or selected_incident["smtp_response"]
                or selected_incident["activity_details"]
                or "Sin diagnóstico técnico disponible."
            )

            st.markdown(
                "#### Diagnóstico"
            )

            detail1, detail2 = st.columns(2)

            detail1.write(
                f"**Plantel:** "
                f"{selected_incident['campus_name_snapshot']}"
            )

            detail1.write(
                f"**Correo actual:** "
                f"{selected_incident['email_address']}"
            )

            detail2.write(
                f"**Estado:** "
                f"{selected_incident['status']}"
            )

            detail2.write(
                f"**Código:** "
                f"{selected_incident['bounce_code'] or 'N/D'}"
            )

            st.error(
                diagnosis
            )

            st.markdown(
                "#### Corregir y preparar reenvío"
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
                    "Corrección del correo institucional "
                    "después de una incidencia de entrega."
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
                (
                    "Confirmo archivar el registro anterior "
                    "y crear el correo corregido como PENDIENTE."
                ),
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
                                selected_incident["id"]
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
                        (
                            "Correo corregido. "
                            f"Anterior: "
                            f"{correction_result['old_email']}. "
                            f"Nuevo: "
                            f"{correction_result['new_email']}. "
                            "El nuevo registro quedó PENDIENTE."
                        )
                    )

                    st.rerun()

                except Exception as exc:

                    st.error(
                        str(exc)
                    )

        st.divider()

        st.markdown(
            "#### Archivar valores que no son correos"
        )

        st.caption(
            "Úsalo para domicilios, teléfonos u otros "
            "valores históricos que quedaron registrados "
            "como ERROR. No elimina intentos ni auditoría."
        )

        archive_reason = st.text_input(
            "Motivo del archivado",
            value=(
                "Valores anteriores sustituidos "
                "después de corregir la base maestra."
            ),
            key=(
                f"archive_reason_"
                f"{selected_campaign_id}"
            ),
        )

        archive_confirm = st.checkbox(
            "Confirmo archivar los valores inválidos.",
            key=(
                f"archive_confirm_"
                f"{selected_campaign_id}"
            ),
        )

        if st.button(
            "Archivar valores inválidos",
            width="stretch",
            disabled=not archive_confirm,
            key=(
                f"archive_invalid_"
                f"{selected_campaign_id}"
            ),
        ):

            try:

                archive_result = (
                    archive_invalid_error_recipients(
                        campaign_id=(
                            selected_campaign_id
                        ),
                        user_id=user_id,
                        reason=(
                            archive_reason
                        ),
                    )
                )

                st.success(
                    (
                        "Registros archivados: "
                        f"{archive_result['archived']}."
                    )
                )

                st.rerun()

            except Exception as exc:

                st.error(
                    str(exc)
                )



def render_followup(user_id: int):
    st.header("Seguimiento")
    st.caption(
        "Clasifica respuestas, contactos referidos, falta de respuesta "
        "y resultados comerciales. Los rebotes se gestionan en Incidencias."
    )

    context = select_campaign("followup")
    if context is None:
        return

    selected_campaign_id = context["campaign_id"]
    campaign = context["campaign"]
    recipients = context["recipients"]
    counts = context["counts"]
    stage = context["stage"]

    show_campaign_identity(context)
    # =================================================
    # PASO 4 - SEGUIMIENTO
    # =================================================

    with st.expander(
        "Registrar seguimiento",
        expanded=(
            counts["pending"] == 0
        ),
    ):

        st.write(
            "Registra aquí lo que ocurrió "
            "cuando un plantel responda."
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
                "Todavía no existen envíos "
                "para dar seguimiento."
            )

        else:

            followup_options = {
                (
                    f"{row['campus_name_snapshot']} "
                    f"— {row['email_address']} "
                    f"[{row['status']}]"
                ):
                    row
                for row
                in followup_recipients
            }

            selected_follow_label = (
                st.selectbox(
                    "Plantel / correo",
                    options=list(
                        followup_options.keys()
                    ),
                    key=(
                        f"follow_recipient_"
                        f"{selected_campaign_id}"
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
                    f"{selected_campaign_id}"
                ),
            )

            recipient_id = int(
                selected_follow["id"]
            )

            # =========================================
            # CONTACTO REFERIDO
            # =========================================

            if (
                response_type
                == "Proporcionó un contacto"
            ):

                st.markdown(
                    "#### Datos del contacto"
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
                            "Captura al menos "
                            "el nombre del contacto."
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

            # =========================================
            # OTROS RESULTADOS
            # =========================================

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

                new_status = status_map[
                    response_type
                ]

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


def render():
    st.title("Marketing")
    st.caption(
        "Creación, operación, incidencias y seguimiento de campañas."
    )

    user = st.session_state.get("user", {})
    user_id = user.get("id")

    if not user_id:
        st.error("No se pudo identificar al usuario activo.")
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
        render_create_campaign(user_id)

    with tabs[1]:
        render_operate_campaign(user_id)

    with tabs[2]:
        render_incidents(user_id)

    with tabs[3]:
        render_followup(user_id)


render()
