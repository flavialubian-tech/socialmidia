"""MÓDULO 2 — Máquina de Conteúdo: Termômetro de Validação, Funil/Formato e geração do roteiro."""

import pandas as pd
import streamlit as st

import database as db
from services import maquina, scraper
from services.llm import LLMError, PROVEDORES, config_atual, obter_segredo

ROTULOS_PLATAFORMA = {"tiktok": "🎵 TikTok", "instagram": "📸 Instagram", "youtube": "▶️ YouTube"}
ROTULOS_TIPO = {"tendencia": "📈", "dor": "😣", "manual": "✍️"}
FONTE_ASSUNTO, FONTE_LIVRE = "🔥 Assunto Quente", "✍️ Tema livre"
ESTADO_FLUXO = ("m2_validacao", "m2_validacao_pulada", "m2_formatos", "m2_conteudo")


def limpar_fluxo() -> None:
    for chave in ESTADO_FLUXO:
        st.session_state.pop(chave, None)


def rotulo_score(score: int) -> str:
    if score >= 70:
        return "🔥 Alto potencial"
    if score >= 45:
        return "🌤️ Potencial moderado"
    return "🧊 Baixo potencial"


def mostrar_validacao(v: dict, chave: str) -> None:
    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    c1.metric("Score de Viralização", f"{v['score_viralizacao']}%")
    c1.caption(rotulo_score(v["score_viralizacao"]))
    c2.metric("Pelos números", f"{v['score_dados']}%" if v["score_dados"] is not None else "—",
              help="Mediana de views e engajamento dos vídeos concorrentes.")
    c3.metric("Pela IA", f"{v['score_ia']}%", help="Demanda, saturação e espaço para diferenciação.")
    c4.metric("Saturação", {"baixa": "🟢 Baixa", "media": "🟡 Média", "alta": "🔴 Alta"}[v["analise"]["saturacao"]])
    st.progress(v["score_viralizacao"] / 100)
    if v["analise"].get("veredito"):
        st.info(f"**Veredito:** {v['analise']['veredito']}")
    if v["lacuna"]:
        st.success(f"🎯 **A Lacuna (o que faltou nos concorrentes):** {v['lacuna']}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**✅ O que já funciona**")
        for item in v["analise"].get("o_que_funciona", []):
            st.markdown(f"- {item}")
    with c2:
        st.markdown("**💡 Oportunidades para se diferenciar**")
        for item in v["analise"].get("oportunidades", []):
            st.markdown(f"- {item}")

    m = v["metricas"]
    if m.get("total_videos"):
        engajamento = f"{m['engajamento_mediano'] * 100:.1f}%" if m.get("engajamento_mediano") is not None else "—"
        st.caption(f"📊 {m['total_videos']} concorrentes analisados · mediana de {m.get('views_mediana', 0):,} views · "
                   f"engajamento mediano {engajamento} · {v['analise'].get('comentarios_lidos', 0)} comentários lidos"
                   .replace(",", "."))
        with st.expander(f"👀 Ver concorrentes ({len(v['concorrentes'])})"):
            st.dataframe(
                pd.DataFrame(v["concorrentes"])[["url", "titulo", "views", "curtidas", "comentarios", "ponto_fraco"]],
                hide_index=True, width="stretch", key=f"concorrentes_{chave}",
                column_config={"url": st.column_config.LinkColumn("Vídeo", display_text="abrir ↗"),
                               "titulo": "Legenda", "views": "Views", "curtidas": "Curtidas",
                               "comentarios": "Comentários", "ponto_fraco": "Ponto fraco"},
            )
    st.caption(f"Validado em {v['criado_em'][:16]}")


# ---------------------------------------------------------------------------
# Pré-preenchimento vindo da aba "Validações recentes" (antes de criar widgets)
# ---------------------------------------------------------------------------
if pendente := st.session_state.pop("m2_pendente", None):
    st.session_state["m2_fonte"] = FONTE_LIVRE
    st.session_state["m2_tema_livre"] = pendente["tema"]
    st.session_state["m2_plataforma"] = pendente["plataforma"]
    persona_pendente = pendente["persona_id"] if db.obter_persona(pendente["persona_id"] or 0) else None
    st.session_state["m2_persona"] = persona_pendente
    st.session_state["m2_assinatura"] = (pendente["tema"], pendente["plataforma"], persona_pendente)
    limpar_fluxo()
    if pendente.get("validacao_id"):
        st.session_state["m2_validacao"] = db.obter_validacao(pendente["validacao_id"])
    st.session_state["m2_conteudo_id"] = pendente.get("conteudo_id")  # ideia vinda do Cofre
    st.session_state["m2_aba"] = "🏭 Criar conteúdo"

if aviso := st.session_state.pop("m2_aviso", None):
    st.toast(aviso[0], icon=aviso[1])

st.title("⚙️ Máquina de Conteúdo")
cfg = config_atual()
st.caption(f"Do Assunto Quente ao roteiro pronto para gravar · IA: {PROVEDORES.get(cfg.provedor)} · `{cfg.modelo}`")

ABA_CRIAR, ABA_VALIDACOES = "🏭 Criar conteúdo", "🌡️ Validações recentes"
try:  # Streamlit recente: permite voltar para a aba de criação após escolher uma validação
    aba_criar, aba_validacoes = st.tabs([ABA_CRIAR, ABA_VALIDACOES], key="m2_aba", on_change="rerun")
except TypeError:
    aba_criar, aba_validacoes = st.tabs([ABA_CRIAR, ABA_VALIDACOES])

# A aba de validações é desenhada primeiro porque a de criação usa st.stop() entre as etapas.
with aba_validacoes:
    validacoes = db.listar_validacoes()
    if not validacoes:
        st.info("Nenhuma validação ainda. Elas aparecem aqui depois de usar o Termômetro.")
    for v in validacoes:
        with st.expander(f"{rotulo_score(v['score_viralizacao'])[:2]} **{v['score_viralizacao']}%** · {v['tema']} · "
                         f"{ROTULOS_PLATAFORMA.get(v['plataforma'], v['plataforma'] or '')} · {v['criado_em'][:10]}"):
            mostrar_validacao(v, f"hist_{v['id']}")
            if st.button("✍️ Criar conteúdo com este tema", key=f"usar_val_{v['id']}"):
                st.session_state["m2_pendente"] = {"tema": v["tema"], "plataforma": v["plataforma"] or "tiktok",
                                                   "persona_id": v["persona_id"], "validacao_id": v["id"]}
                st.rerun()


with aba_criar:
    # =======================================================================
    # 1. TEMA
    # =======================================================================
    st.subheader("1️⃣ Tema")
    personas = db.listar_personas()
    nomes = {p["id"]: p["nome"] for p in personas}
    c1, c2 = st.columns(2)
    persona_id = c1.selectbox("Persona", [None] + list(nomes), key="m2_persona",
                              format_func=lambda i: "— Sem persona —" if i is None else nomes[i])
    persona = next((p for p in personas if p["id"] == persona_id), None)
    if "m2_plataforma" not in st.session_state:
        padrao = persona["plataforma"] if persona and persona["plataforma"] in ROTULOS_PLATAFORMA else "tiktok"
        st.session_state["m2_plataforma"] = padrao
    plataforma = c2.selectbox("Plataforma", list(ROTULOS_PLATAFORMA), key="m2_plataforma",
                              format_func=ROTULOS_PLATAFORMA.get)
    if not personas:
        st.caption("💡 Cadastre uma persona no 🧠 Cérebro para roteiros no seu tom de voz.")

    fonte = st.radio("De onde vem o tema?", [FONTE_ASSUNTO, FONTE_LIVRE], horizontal=True, key="m2_fonte")
    assunto_id, tema = None, ""
    if fonte == FONTE_ASSUNTO:
        assuntos = db.listar_assuntos_quentes(persona_id, ("novo", "em_uso"))
        if not assuntos:
            st.info("Nenhum Assunto Quente para esta persona. Rode o 📡 Radar ou o 🤖 Rastreador no 🧠 Cérebro, "
                    "ou use um tema livre.")
        else:
            por_id = {a["id"]: a for a in assuntos}
            assunto_id = st.selectbox(
                "Escolha um Assunto Quente", list(por_id), key="m2_assunto",
                format_func=lambda i: f"{ROTULOS_TIPO.get(por_id[i]['tipo'], '')} {por_id[i]['intensidade']}% · "
                                      f"{por_id[i]['tema']}" + (" (em uso)" if por_id[i]["status"] == "em_uso" else ""),
            )
            tema = por_id[assunto_id]["tema"]
            if por_id[assunto_id]["descricao"]:
                st.caption(por_id[assunto_id]["descricao"])
    else:
        tema = st.text_input("Tema", key="m2_tema_livre",
                             placeholder="Ex.: Como tirar mancha de porcelanato sem estragar o piso").strip()

    assinatura = (tema, plataforma, persona_id)
    if st.session_state.get("m2_assinatura") != assinatura:
        st.session_state["m2_assinatura"] = assinatura
        st.session_state.pop("m2_conteudo_id", None)
        limpar_fluxo()

    conteudo_cofre_id = st.session_state.get("m2_conteudo_id")
    if conteudo_cofre_id:
        st.info(f"🗄️ Roteirizando a ideia #{conteudo_cofre_id} do Cofre. Ao salvar, o próprio card vai para "
                "'Roteiros Prontos'.")

    if not tema:
        st.stop()

    # =======================================================================
    # 2. TERMÔMETRO DE VALIDAÇÃO
    # =======================================================================
    st.divider()
    st.subheader("2️⃣ Termômetro de Validação")
    validacao = st.session_state.get("m2_validacao")
    pulada = st.session_state.get("m2_validacao_pulada", False)

    if validacao:
        mostrar_validacao(validacao, "fluxo")
        if st.button("🔄 Validar de novo"):
            limpar_fluxo()
            st.rerun()
    elif pulada:
        st.caption("⏭️ Validação pulada. O roteiro será gerado sem dados de concorrentes.")
        if st.button("🌡️ Validar agora"):
            st.session_state.pop("m2_validacao_pulada")
            st.rerun()
    else:
        st.caption("Busca na rede os vídeos mais quentes sobre o tema, calcula o Score de Viralização e aponta "
                   "a Lacuna — o que os concorrentes não entregaram.")
        recente = db.validacao_recente(tema, plataforma)
        if recente:
            st.info(f"Este tema já foi validado em {recente['criado_em'][:10]} (score {recente['score_viralizacao']}%). "
                    "Reaproveitar economiza créditos da Apify.")
            if st.button("♻️ Usar a validação existente", type="primary"):
                st.session_state["m2_validacao"] = recente
                st.rerun()
        sem_token = not obter_segredo("APIFY_API_TOKEN")
        if sem_token:
            st.warning("O Termômetro usa a Apify. Cadastre o token em ⚙️ Configurações ou pule esta etapa.")
        ler_comentarios = st.checkbox("Ler comentários dos 3 maiores concorrentes (lacuna mais precisa, usa mais créditos)",
                                      value=True)
        c1, c2, _ = st.columns([1.2, 1, 2])
        if c1.button("🌡️ Medir viralização", type="secondary" if recente else "primary", disabled=sem_token):
            with st.status("Medindo a temperatura do tema...", expanded=True) as status:
                try:
                    st.session_state["m2_validacao"] = maquina.validar_tema(
                        tema, plataforma, persona_id, assunto_id, ler_comentarios=ler_comentarios,
                        progresso=lambda msg: status.update(label=msg) or st.write(msg),
                    )
                    status.update(label="Validação concluída!", state="complete")
                    st.rerun()
                except (scraper.ColetaError, LLMError) as exc:
                    status.update(label="Não foi possível validar", state="error")
                    st.error(str(exc))
        if c2.button("⏭️ Pular validação"):
            st.session_state["m2_validacao_pulada"] = True
            st.rerun()
        st.stop()

    # =======================================================================
    # 3. FUNIL E FORMATO
    # =======================================================================
    st.divider()
    st.subheader("3️⃣ Funil e Formato")
    funil = st.radio("Objetivo deste conteúdo", list(maquina.FUNIS), format_func=maquina.FUNIS.get,
                     horizontal=True, key="m2_funil")
    st.caption(f"🎯 {maquina.OBJETIVO_FUNIL[funil]}")
    if st.session_state.get("m2_formatos_funil") != funil:
        st.session_state["m2_formatos_funil"] = funil
        st.session_state.pop("m2_formatos", None)

    if st.button("💡 Sugerir formatos com IA"):
        with st.spinner("Pensando nos melhores formatos..."):
            try:
                st.session_state["m2_formatos"] = maquina.sugerir_formatos(tema, funil, plataforma, persona_id,
                                                                           validacao)
            except LLMError as exc:
                st.error(str(exc))

    sugestoes = st.session_state.get("m2_formatos") or []
    for i, s in enumerate(sugestoes):
        with st.container(border=True):
            st.markdown(f"**{'⭐ ' if i == 0 else ''}{s['formato']}** — {s['por_que']}")
            if s["exemplo_gancho"]:
                st.caption(f"🪝 Exemplo de gancho: “{s['exemplo_gancho']}”")

    opcoes_formato = list(dict.fromkeys([s["formato"] for s in sugestoes] + maquina.FORMATOS))
    c1, c2 = st.columns(2)
    formato = c1.selectbox("Formato", opcoes_formato, key=f"m2_formato_{len(sugestoes)}_{funil}")
    formato_livre = c2.text_input("...ou escreva outro formato", key="m2_formato_livre").strip()
    formato = formato_livre or formato
    instrucoes = st.text_area("Instruções extras (opcional)", key="m2_instrucoes",
                              placeholder="Ex.: mencionar meu serviço de limpeza pós-obra, vídeo de até 30s, gravar no carro...")

    # =======================================================================
    # 4. GERAÇÃO
    # =======================================================================
    st.divider()
    st.subheader("4️⃣ Roteiro")
    conteudo = st.session_state.get("m2_conteudo")
    if st.button("✨ Gerar roteiro" if not conteudo else "🔄 Gerar outra versão", type="primary"):
        with st.spinner("Escrevendo gancho, roteiro, legenda e hashtags..."):
            try:
                novo = maquina.gerar_roteiro(tema, funil, formato, plataforma, persona_id, validacao, instrucoes)
                novo["versao"] = (conteudo or {}).get("versao", 0) + 1
                novo["formato"] = formato
                st.session_state["m2_conteudo"] = conteudo = novo
            except LLMError as exc:
                st.error(str(exc))

    if conteudo:
        v = conteudo["versao"]
        carrossel = maquina.eh_carrossel(conteudo["formato"])
        if conteudo["palavras_proibidas_usadas"]:
            st.warning(f"⚠️ A IA insistiu em palavras proibidas: {', '.join(conteudo['palavras_proibidas_usadas'])}. "
                       "Edite antes de salvar ou gere outra versão.")

        titulo = st.text_input("Título interno", conteudo["titulo"], key=f"m2_titulo_{v}")
        gancho = st.text_area("🪝 Gancho (3 primeiros segundos)", conteudo["gancho"], key=f"m2_gancho_{v}", height=70)
        if conteudo["ganchos_alternativos"]:
            st.caption("Outras opções de gancho: " + " · ".join(f"“{g}”" for g in conteudo["ganchos_alternativos"]))

        st.markdown(f"**{'🖼️ Lâminas do carrossel' if carrossel else '🎬 Roteiro técnico (Áudio x Tela)'}**"
                    + (f" · ⏱️ {conteudo['duracao_estimada']}" if conteudo["duracao_estimada"] else ""))
        roteiro_editado = st.data_editor(
            pd.DataFrame(conteudo["roteiro"] or [{"tempo": "", "audio": "", "tela": ""}]),
            num_rows="dynamic", hide_index=True, width="stretch", key=f"m2_roteiro_{v}",
            column_config={
                "tempo": st.column_config.TextColumn("Lâmina" if carrossel else "Tempo", width="small"),
                "audio": st.column_config.TextColumn("Texto da lâmina" if carrossel else "🎙️ Áudio (fala)",
                                                     width="large"),
                "tela": st.column_config.TextColumn("Visual" if carrossel else "🎥 Tela / B-roll", width="large"),
            },
        )
        legenda = st.text_area("📝 Legenda", conteudo["legenda"], key=f"m2_legenda_{v}", height=200)
        hashtags = st.text_input("#️⃣ Hashtags", " ".join(conteudo["hashtags"]), key=f"m2_hashtags_{v}")
        if conteudo["palavras_chave_seo"]:
            st.caption("🔎 Palavras-chave de busca (use no texto da tela e na 1ª linha da legenda): "
                       + ", ".join(conteudo["palavras_chave_seo"]))

        c1, c2, _ = st.columns([1.4, 1, 2])
        if c1.button("💾 Salvar no Cofre de Ideias", type="primary"):
            final = {
                **conteudo,
                "titulo": titulo.strip() or tema,
                "gancho": gancho.strip(),
                "roteiro": [{k: str(linha.get(k) or "").strip() for k in ("tempo", "audio", "tela")}
                            for linha in roteiro_editado.fillna("").to_dict("records")
                            if str(linha.get("audio") or "").strip() or str(linha.get("tela") or "").strip()],
                "legenda": legenda.strip(),
                "hashtags": maquina.normalizar_hashtags(hashtags),
            }
            cid = maquina.salvar_no_cofre(final, tema, funil, conteudo["formato"], plataforma, persona_id,
                                          assunto_id, validacao, conteudo_id=conteudo_cofre_id)
            limpar_fluxo()
            st.session_state.pop("m2_conteudo_id", None)
            st.session_state["m2_aviso"] = (f"Conteúdo #{cid} salvo em 'Roteiros Prontos' no Cofre de Ideias!", "💾")
            st.rerun()
        if c2.button("🧹 Começar do zero"):
            limpar_fluxo()
            st.session_state.pop("m2_conteudo_id", None)
            st.rerun()
