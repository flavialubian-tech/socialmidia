"""Social Mídia Autônoma — ponto de entrada do app.

Executar:  streamlit run app.py
"""

import logging

import streamlit as st
from dotenv import load_dotenv

from database import init_db
from modulos.comum import obter_agendador

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(
    page_title="Social Mídia Autônoma",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _inicializar_banco() -> bool:
    """Roda uma única vez por processo do Streamlit."""
    init_db()
    return True


_inicializar_banco()


obter_agendador()  # piloto automático do Rastreador em segundo plano

paginas = {
    "Visão Geral": [
        st.Page("modulos/m0_dashboard.py", title="Dashboard", icon="📊", default=True),
    ],
    "Estratégia": [
        st.Page("modulos/m1_cerebro.py", title="Cérebro", icon="🧠"),
        st.Page("modulos/m2_maquina_conteudo.py", title="Máquina de Conteúdo", icon="⚙️"),
    ],
    "Produção": [
        st.Page("modulos/m3_cofre_ideias.py", title="Cofre de Ideias", icon="🗄️"),
        st.Page("modulos/m4_estudio.py", title="Estúdio de Produção", icon="🎬"),
    ],
    "Sistema": [
        st.Page("modulos/configuracoes.py", title="Configurações", icon="⚙️"),
    ],
}

navegacao = st.navigation(paginas)

with st.sidebar:
    st.divider()
    st.caption("🚀 Social Mídia Autônoma · v0.1")

navegacao.run()
