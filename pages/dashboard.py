import streamlit as st


st.title("Panel principal")

st.write(
    f"Sesión iniciada como **{st.session_state.get('full_name', '')}**"
)

st.caption(
    f"Rol: {st.session_state.get('role', '')}"
)

st.divider()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Instituciones",
        value="0",
    )

with col2:
    st.metric(
        label="Planteles",
        value="0",
    )

with col3:
    st.metric(
        label="Contactos",
        value="0",
    )

with col4:
    st.metric(
        label="Requieren revisión",
        value="0",
    )

st.info(
    "La estructura comercial de la base de datos "
    "se incorporará en la siguiente etapa."
)