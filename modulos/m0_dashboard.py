"""MÓDULO 0 — Dashboard (Centro de Comando). Versão inicial: contadores e alertas."""

import streamlit as st

from database import STATUS_KANBAN_LABELS, contar_conteudos_por_status, listar_alertas_metricas, listar_personas

st.title("📊 Centro de Comando")

contagem = contar_conteudos_por_status()
colunas = st.columns(len(STATUS_KANBAN_LABELS) + 1)
colunas[0].metric("Personas ativas", len(listar_personas()))
for col, (status, label) in zip(colunas[1:], STATUS_KANBAN_LABELS.items()):
    col.metric(label, contagem[status])

st.subheader("🔔 Métricas pendentes")
alertas = listar_alertas_metricas()
if not alertas:
    st.success("Nenhuma métrica pendente. Tudo em dia!")
for alerta in alertas:
    st.warning(
        f"**{alerta['titulo']}** ({alerta['persona'] or 'sem persona'}) — "
        f"postado em {alerta['data_postagem']}, marco de **{alerta['marco_dias']} dias** sem métricas."
    )

st.info("🚧 Em breve: formulário de métricas, gráficos de performance e sugestão \"Reciclar este tema\".")
