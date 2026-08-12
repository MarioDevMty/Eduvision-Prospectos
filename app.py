import streamlit as st

from database.schema import create_schema
from database.marketing_schema import create_marketing_schema
from database.seed import create_initial_superadmin
from services.auth_service import authenticate_user


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

st.set_page_config(
    page_title="Eduvision Prospectos",
    page_icon="🎓",
    layout="wide",
)


# =========================================================
# INICIALIZACIÓN DE BASE DE DATOS
# =========================================================

create_schema()
create_marketing_schema()

initial_user_created = create_initial_superadmin()


# =========================================================
# INICIALIZACIÓN DE SESIÓN
# =========================================================

SESSION_DEFAULTS = {
    "authenticated": False,
    "user_id": None,
    "username": None,
    "full_name": None,
    "role": None,
    "user": {},
}


for key, value in SESSION_DEFAULTS.items():

    if key not in st.session_state:

        if isinstance(value, dict):
            st.session_state[key] = value.copy()
        else:
            st.session_state[key] = value


# =========================================================
# FUNCIONES DE AUTENTICACIÓN
# =========================================================

def logout() -> None:
    """
    Limpia los datos de autenticación
    y reinicia la aplicación.
    """

    for key, value in SESSION_DEFAULTS.items():

        if isinstance(value, dict):
            st.session_state[key] = value.copy()
        else:
            st.session_state[key] = value

    st.rerun()


def show_login() -> None:
    """
    Muestra el formulario de inicio de sesión.
    """

    st.title("EDUVISION")

    st.subheader(
        "Sistema de Prospección Educativa"
    )

    st.write(
        "Ingresa con tus credenciales para acceder "
        "a la base de datos."
    )

    if initial_user_created:

        st.warning(
            "Se creó el usuario inicial SUPERADMIN. "
            "La contraseña deberá cambiarse posteriormente."
        )

    with st.form("login_form"):

        username = st.text_input(
            "Usuario"
        )

        password = st.text_input(
            "Contraseña",
            type="password",
        )

        submitted = st.form_submit_button(
            "Ingresar",
            width="stretch",
        )

    if submitted:

        user = authenticate_user(
            username=username,
            password=password,
        )

        if user is None:

            st.error(
                "Usuario o contraseña incorrectos."
            )

            return

        user_data = {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
        }

        st.session_state["authenticated"] = True
        st.session_state["user_id"] = user_data["id"]
        st.session_state["username"] = user_data["username"]
        st.session_state["full_name"] = user_data["full_name"]
        st.session_state["role"] = user_data["role"]

        # El módulo de marketing utiliza este diccionario.
        st.session_state["user"] = user_data

        st.rerun()


# =========================================================
# CONTROL DE ACCESO
# =========================================================

if not st.session_state.get(
    "authenticated",
    False,
):

    show_login()
    st.stop()


# Una sesión autenticada debe tener
# un identificador de usuario asociado.

if st.session_state.get("user_id") is None:

    st.error(
        "La sesión no contiene un identificador de usuario válido. "
        "Cierra la aplicación e inicia sesión nuevamente."
    )

    if st.button(
        "Cerrar sesión",
        width="stretch",
    ):
        logout()

    st.stop()


# Compatibilidad con sesiones iniciadas antes
# de incorporar el módulo de marketing.

if not st.session_state.get("user"):

    st.session_state["user"] = {
        "id": st.session_state.get("user_id"),
        "username": st.session_state.get("username"),
        "full_name": st.session_state.get("full_name"),
        "role": st.session_state.get("role"),
    }


# =========================================================
# BARRA LATERAL
# =========================================================

with st.sidebar:

    st.write(
        f"**{st.session_state.get('full_name', '')}**"
    )

    st.caption(
        st.session_state.get("role", "")
    )

    st.divider()

    if st.button(
        "Cerrar sesión",
        width="stretch",
    ):
        logout()


# =========================================================
# DEFINICIÓN DE PÁGINAS
# =========================================================

dashboard_page = st.Page(
    "pages/dashboard.py",
    title="Inicio",
    icon=":material/home:",
    default=True,
)

import_page = st.Page(
    "pages/importar.py",
    title="Importar",
    icon=":material/upload_file:",
)

validation_page = st.Page(
    "pages/validar.py",
    title="Validar",
    icon=":material/fact_check:",
)

database_page = st.Page(
    "pages/base_datos.py",
    title="Base de datos",
    icon=":material/database:",
)

marketing_page = st.Page(
    "pages/marketing.py",
    title="Marketing",
    icon=":material/campaign:",
)

export_page = st.Page(
    "pages/exportar.py",
    title="Exportar",
    icon=":material/download:",
)


navigation = {
    "Prospección": [
        dashboard_page,
        import_page,
        validation_page,
        database_page,
        export_page,
    ],
    "Comunicación": [
        marketing_page,
    ],
}


# =========================================================
# PÁGINAS SEGÚN ROL
# =========================================================

if st.session_state.get("role") in {
    "ADMIN",
    "SUPERADMIN",
}:

    administration_page = st.Page(
        "pages/administracion.py",
        title="Administración",
        icon=":material/admin_panel_settings:",
    )

    navigation["Sistema"] = [
        administration_page
    ]


# =========================================================
# NAVEGACIÓN
# =========================================================

page = st.navigation(
    navigation,
    position="sidebar",
)

page.run()