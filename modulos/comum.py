"""Recursos compartilhados entre as páginas do Streamlit."""

import streamlit as st


@st.cache_resource
def obter_agendador():
    """Liga o piloto automático (Rastreador) em segundo plano, uma única vez por processo."""
    from services.rastreador import iniciar_agendador

    return iniciar_agendador()
