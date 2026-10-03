"""MÓDULO 0 — Dashboard (Centro de Comando): métricas pendentes, performance e "Reciclar este tema"."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import database as db
from services import dashboard, graficos

ICONES_COLUNA = {"ideia": "💡", "roteiro_pronto": "📝", "em_edicao": "🎬", "postado": "✅"}
PERIODOS = {"30 dias": 30, "90 dias": 90, "12 meses": 365, "Tudo": None}


def br(n: int | float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor * 100:.1f}%".replace(".", ",")


def data_br(texto: str | None) -> str:
    return "—" if not texto else f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}"


def tema_visual() -> str:
    try:
        return st.context.theme.type or "light"
    except AttributeError:
        return "light"


def form_metricas(conteudo_id: int, marco: int, chave: str, valores: dict | None = None) -> None:
    valores = valores or {}
    with st.form(chave, border=False):
        cols = st.columns(5)
        campos = {}
        for col, (campo, rotulo) in zip(cols, [("views", "👁️ Views"), ("saves", "🔖 Salvamentos"),
                                               ("shares", "🔁 Compart."), ("comments", "💬 Coment."),
                                               ("likes", "❤️ Curtidas")]):
            campos[campo] = col.number_input(rotulo, min_value=0, step=1, value=int(valores.get(campo) or 0),
                                             key=f"{chave}_{campo}")
        if st.form_submit_button("💾 Salvar métricas", type="primary"):
            db.salvar_metricas(conteudo_id, marco, **campos)
            st.session_state["_aviso_dash"] = ("Métricas salvas!", "📊")
            st.rerun()


def ir_para_maquina(pendente: dict) -> None:
    st.session_state["m2_pendente"] = pendente
    try:
        st.switch_page("modulos/m2_maquina_conteudo.py")
    except Exception:  # página aberta fora do menu principal
        st.session_state["_aviso_dash"] = ("Tema enviado! Abra a ⚙️ Máquina de Conteúdo para continuar.", "♻️")
        st.rerun()


if aviso := st.session_state.pop("_aviso_dash", None):
    st.toast(aviso[0], icon=aviso[1])

st.title("📊 Centro de Comando")

# ---------------------------------------------------------------------------
# Filtros (uma linha, acima de tudo)
# ---------------------------------------------------------------------------
personas = {p["id"]: p["nome"] for p in db.listar_personas()}
f1, f2, _ = st.columns([1.2, 1, 2])
persona_id = f1.selectbox("Persona", [None] + list(personas), key="dash_persona",
                          format_func=lambda i: "Todas" if i is None else personas[i])
periodo = f2.selectbox("Período (data da postagem)", list(PERIODOS), index=1, key="dash_periodo")
dias = PERIODOS[periodo]
desde = (date.today() - timedelta(days=dias)).isoformat() if dias else None

linhas = db.dados_performance(persona_id, desde)
kpis = dashboard.calcular_kpis(linhas)

# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Posts publicados", kpis["posts"],
          help=f"{kpis['posts_com_metricas']} com métricas registradas")
k2.metric("Views", br(kpis["views_total"]))
k3.metric("Média de views/post", br(kpis["views_media"]))
k4.metric("Taxa de salvamento", pct(kpis["taxa_salvamento"]), help="Salvamentos ÷ views")
k5.metric("Taxa de compartilhamento", pct(kpis["taxa_compartilhamento"]), help="Compartilhamentos ÷ views")

contagem = db.contar_conteudos_por_status()
st.caption("Produção agora: " + " · ".join(f"{ICONES_COLUNA[s]} {db.STATUS_KANBAN_LABELS[s]}: **{n}**"
                                          for s, n in contagem.items()))

# ---------------------------------------------------------------------------
# Alertas de métricas (7 e 14 dias)
# ---------------------------------------------------------------------------
alertas = db.listar_alertas_metricas()
if persona_id:
    alertas = [a for a in alertas if a["persona_id"] == persona_id]
st.subheader(f"🔔 Métricas pendentes ({len(alertas)})")
if not alertas:
    st.success("Nenhuma métrica pendente. Tudo em dia! ✨")
for a in alertas:
    titulo = (f"**{a['titulo']}** · {a['persona'] or 'Sem persona'} · postado em {data_br(a['data_postagem'])} · "
              f"marco de **{a['marco_dias']} dias** (hoje: {a['dias_desde_postagem']} dias)")
    with st.expander(titulo, expanded=len(alertas) <= 3):
        st.caption("Copie os números do app da rede social (Insights / Estatísticas do post).")
        form_metricas(a["conteudo_id"], a["marco_dias"], f"alerta_{a['conteudo_id']}_{a['marco_dias']}")

# ---------------------------------------------------------------------------
# Alta performance -> Reciclar este tema
# ---------------------------------------------------------------------------
limiar_views, limiar_saves = dashboard.limiares()
destaques = dashboard.identificar_alto_desempenho(linhas, limiar_views, limiar_saves)
st.subheader(f"🔥 Alta performance ({len(destaques)})")
st.caption(f"Posts com {br(limiar_views)}+ views, {br(limiar_saves)}+ salvamentos ou 2x acima do normal da persona. "
           "Ajuste as metas em ⚙️ Configurações.")
if not destaques:
    st.info("Nenhum post acima das metas ainda. Assim que as métricas chegarem, os campeões aparecem aqui.")
for d in destaques:
    with st.container(border=True):
        c1, c2 = st.columns([3, 1.2])
        c1.markdown(f"**{d['titulo']}** · {d['persona'] or 'Sem persona'} · {d['formato'] or 'formato livre'}")
        c1.caption("🏆 " + " · ".join(d["motivos"]) + f" · métricas de {d['marco_dias']} dias")
        ja_enviado = db.assunto_de_reciclagem(d["id"])
        if c2.button("♻️ Reciclar este tema" if not ja_enviado else "♻️ Reciclar de novo",
                     key=f"reciclar_tema_{d['id']}", type="primary" if not ja_enviado else "secondary",
                     help="Cria um Assunto Quente e abre a Máquina de Conteúdo com este tema."):
            ir_para_maquina(dashboard.enviar_para_reciclagem(d["id"]))
        if ja_enviado:
            c2.caption(f"Já enviado em {data_br(ja_enviado['criado_em'])}")

# ---------------------------------------------------------------------------
# Gráficos de performance
# ---------------------------------------------------------------------------
st.subheader("📈 Performance")
com_metricas = [l for l in linhas if l["views"] is not None]
if not com_metricas:
    st.info("Os gráficos aparecem quando houver posts com métricas registradas neste período.")
else:
    tema = tema_visual()
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Top posts por views**")
        st.plotly_chart(graficos.barras_top_views(com_metricas, tema), theme=None,
                        config=graficos.CONFIG_PLOTLY, key="graf_top")
    with g2:
        st.markdown("**Taxa de salvamento por formato**")
        st.plotly_chart(graficos.barras_salvamento_por_formato(com_metricas, tema), theme=None,
                        config=graficos.CONFIG_PLOTLY, key="graf_formato")
    st.markdown("**Views por data de postagem**")
    st.plotly_chart(graficos.linha_views_no_tempo(com_metricas, tema), theme=None,
                    config=graficos.CONFIG_PLOTLY, key="graf_tempo")

    with st.expander("📋 Ver dados em tabela"):
        st.dataframe(
            pd.DataFrame(com_metricas)[["titulo", "persona", "formato", "data_postagem", "marco_dias", "views",
                                        "saves", "shares", "comments", "likes"]],
            hide_index=True, width="stretch",
            column_config={"titulo": "Post", "persona": "Persona", "formato": "Formato",
                           "data_postagem": "Postado em", "marco_dias": "Dias", "views": "Views",
                           "saves": "Salvamentos", "shares": "Compart.", "comments": "Coment.", "likes": "Curtidas"},
        )

# ---------------------------------------------------------------------------
# Lançamento manual / correção
# ---------------------------------------------------------------------------
postados = db.listar_conteudos(status="postado")
if postados:
    with st.expander("✏️ Lançar ou corrigir métricas de qualquer post"):
        por_id = {c["id"]: c for c in postados}
        c1, c2 = st.columns([3, 1])
        escolhido = c1.selectbox("Post", list(por_id), key="dash_manual_post",
                                 format_func=lambda i: f"#{i} · {por_id[i]['titulo']} ({data_br(por_id[i]['data_postagem'])})")
        marco = c2.selectbox("Marco", db.MARCOS_METRICAS, format_func=lambda m: f"{m} dias", key="dash_manual_marco")
        atuais = next((m for m in db.listar_metricas(escolhido) if m["marco_dias"] == marco), None)
        form_metricas(escolhido, marco, f"manual_{escolhido}_{marco}", atuais)
