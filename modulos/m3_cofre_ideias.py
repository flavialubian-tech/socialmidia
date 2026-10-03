"""MÓDULO 3 — Cofre de Ideias: Kanban de produção, Dossiê e Reciclagem."""

from datetime import date

import pandas as pd
import streamlit as st

import database as db
from services import cofre, maquina
from services.llm import LLMError

ICONES_COLUNA = {"ideia": "💡", "roteiro_pronto": "📝", "em_edicao": "🎬", "postado": "✅"}
ROTULOS_PLATAFORMA = {"tiktok": "🎵 TikTok", "instagram": "📸 Instagram", "youtube": "▶️ YouTube",
                      "multiplataforma": "🌐 Multi"}
ROTULOS_FUNIL = {"topo": "🧲 Topo", "meio": "📚 Meio", "fundo": "💰 Fundo"}
ROTULOS_EVENTO = {"criado": "🆕 Criado", "status_alterado": "➡️ Mudou de coluna", "editado": "✏️ Editado",
                  "roteirizado": "⚙️ Roteirizado", "reciclado": "♻️ Reciclagem"}
STATUS = list(db.STATUS_KANBAN)


def avisar(mensagem: str, icone: str = "✅") -> None:
    st.session_state["_aviso_cofre"] = (mensagem, icone)


def rotulo_status(status: str) -> str:
    return f"{ICONES_COLUNA[status]} {db.STATUS_KANBAN_LABELS[status]}"


def data_br(texto: str | None) -> str:
    if not texto:
        return "—"
    partes = texto[:10].split("-")
    return f"{partes[2]}/{partes[1]}/{partes[0]}" + (f" {texto[11:16]}" if len(texto) > 10 else "")


def detalhes_evento(evento: dict) -> str:
    if evento["evento"] == "status_alterado" and " -> " in evento["detalhes"]:
        de, para = evento["detalhes"].split(" -> ", 1)
        return f"{db.STATUS_KANBAN_LABELS.get(de, de)} → {db.STATUS_KANBAN_LABELS.get(para, para)}"
    return evento["detalhes"]


def tabela_roteiro(roteiro: list[dict], formato: str | None, chave: str, editavel: bool = False):
    carrossel = maquina.eh_carrossel(formato)
    config = {
        "tempo": st.column_config.TextColumn("Lâmina" if carrossel else "Tempo", width="small"),
        "audio": st.column_config.TextColumn("Texto da lâmina" if carrossel else "🎙️ Áudio", width="large"),
        "tela": st.column_config.TextColumn("Visual" if carrossel else "🎥 Tela / B-roll", width="large"),
    }
    df = pd.DataFrame(roteiro or [{"tempo": "", "audio": "", "tela": ""}], columns=["tempo", "audio", "tela"])
    if editavel:
        return st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=chave,
                              column_config=config)
    st.dataframe(df, hide_index=True, width="stretch", key=chave, column_config=config)
    return df


def roteiro_de(df: pd.DataFrame) -> list[dict]:
    return [{k: str(linha.get(k) or "").strip() for k in ("tempo", "audio", "tela")}
            for linha in df.fillna("").to_dict("records")
            if str(linha.get("audio") or "").strip() or str(linha.get("tela") or "").strip()]


def abrir_na_maquina(c: dict) -> None:
    """Envia uma ideia para a Máquina de Conteúdo; ao salvar lá, o mesmo card é atualizado."""
    plataforma = c["plataforma"] if c["plataforma"] in ("tiktok", "instagram", "youtube") else "tiktok"
    st.session_state["m2_pendente"] = {"tema": c["extras"].get("tema") or c["titulo"], "plataforma": plataforma,
                                       "persona_id": c["persona_id"], "validacao_id": c["validacao_id"],
                                       "conteudo_id": c["id"]}
    try:
        st.switch_page("modulos/m2_maquina_conteudo.py")
    except Exception:  # página aberta fora do menu principal
        avisar("Abra a ⚙️ Máquina de Conteúdo para continuar.", "➡️")
        st.rerun()


# ===========================================================================
# Diálogos
# ===========================================================================
@st.dialog("💡 Nova ideia")
def dialog_nova_ideia() -> None:
    personas = {p["id"]: p["nome"] for p in db.listar_personas()}
    titulo = st.text_input("Ideia / tema *", placeholder="Ex.: 3 erros que mancham o porcelanato")
    persona_id = st.selectbox("Persona", [None] + list(personas),
                              format_func=lambda i: "— Sem persona —" if i is None else personas[i])
    plataforma = st.selectbox("Plataforma", ["tiktok", "instagram", "youtube"], format_func=ROTULOS_PLATAFORMA.get)
    notas = st.text_area("Notas (opcional)", placeholder="Referências, insight, onde surgiu a ideia...")
    if st.button("Adicionar ao Cofre", type="primary", disabled=not titulo.strip()):
        db.criar_ideia(titulo, persona_id, plataforma, notas)
        avisar("Ideia adicionada em 'Ideias no Radar'!", "💡")
        st.rerun()


@st.dialog("✅ Marcar como postado")
def dialog_postar(conteudo_id: int) -> None:
    c = db.obter_conteudo(conteudo_id)
    st.write(f"**{c['titulo']}**")
    data_post = st.date_input("Data da postagem", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
    url = st.text_input("Link do post (opcional)", value=c["url_publicacao"] or "")
    st.caption("🔔 O Dashboard vai pedir as métricas 7 e 14 dias depois desta data.")
    if st.button("Confirmar postagem", type="primary"):
        db.mover_conteudo(conteudo_id, "postado", data_post.isoformat(), url)
        avisar("Conteúdo movido para 'Postado'!", "✅")
        st.rerun()


@st.dialog("📂 Dossiê do conteúdo", width="large")
def dialog_dossie(conteudo_id: int) -> None:
    c = db.obter_conteudo(conteudo_id)
    if not c:
        st.error("Conteúdo não encontrado.")
        return
    persona = db.obter_persona(c["persona_id"]) if c["persona_id"] else None
    st.markdown(f"### {c['titulo']}")
    st.caption(f"#{c['id']} · {rotulo_status(c['status'])} · {persona['nome'] if persona else 'Sem persona'} · "
               f"{ROTULOS_PLATAFORMA.get(c['plataforma'], c['plataforma'] or '—')} · {c['formato'] or 'sem formato'} · "
               f"{ROTULOS_FUNIL.get(c['funil'], 'funil —')}")

    aba_roteiro, aba_refs, aba_hist, aba_metricas = st.tabs(["📝 Roteiro", "🔗 Referências", "🕘 Histórico",
                                                             "📊 Métricas"])
    with aba_roteiro:
        with st.form(f"form_dossie_{conteudo_id}"):
            titulo = st.text_input("Título", c["titulo"])
            c1, c2, c3 = st.columns(3)
            status = c1.selectbox("Coluna", STATUS, index=STATUS.index(c["status"]), format_func=rotulo_status)
            formatos = list(dict.fromkeys(([c["formato"]] if c["formato"] else []) + maquina.FORMATOS))
            formato = c2.selectbox("Formato", formatos, index=0)
            funis = [None] + list(maquina.FUNIS)
            funil = c3.selectbox("Funil", funis, index=funis.index(c["funil"]),
                                 format_func=lambda f: "—" if f is None else maquina.FUNIS[f])
            c4, c5 = st.columns(2)
            data_post = c4.date_input("Data da postagem (se postado)",
                                      value=date.fromisoformat(c["data_postagem"]) if c["data_postagem"] else date.today(),
                                      format="DD/MM/YYYY")
            url = c5.text_input("Link do post (se postado)", c["url_publicacao"] or "")
            gancho = st.text_area("🪝 Gancho", c["gancho"], height=70)
            roteiro_df = tabela_roteiro(c["roteiro"], formato, f"dossie_roteiro_{conteudo_id}", editavel=True)
            legenda = st.text_area("📝 Legenda", c["legenda"], height=160)
            hashtags = st.text_input("#️⃣ Hashtags", " ".join(c["hashtags"]))
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                cofre.salvar_edicao(conteudo_id, titulo=titulo.strip() or c["titulo"], formato=formato, funil=funil,
                                    gancho=gancho.strip(), roteiro=roteiro_de(roteiro_df), legenda=legenda.strip(),
                                    hashtags=hashtags)
                if status != c["status"]:
                    db.mover_conteudo(conteudo_id, status, data_post.isoformat(), url)
                elif status == "postado":
                    cofre.salvar_edicao(conteudo_id, data_postagem=data_post.isoformat(), url_publicacao=url.strip() or None)
                avisar("Dossiê atualizado!", "💾")
                st.rerun()

        extras = c["extras"]
        if extras.get("notas"):
            st.info(f"🗒️ **Notas:** {extras['notas']}")
        if extras.get("ganchos_alternativos"):
            st.caption("Outros ganchos: " + " · ".join(f"“{g}”" for g in extras["ganchos_alternativos"]))
        if extras.get("cta"):
            st.caption(f"📣 CTA: {extras['cta']}")
        if extras.get("palavras_chave_seo"):
            st.caption("🔎 Palavras-chave de busca: " + ", ".join(extras["palavras_chave_seo"]))
        if extras.get("duracao_estimada"):
            st.caption(f"⏱️ Duração estimada: {extras['duracao_estimada']}")

        b1, b2, _ = st.columns([1.3, 1, 2])
        if c["status"] == "ideia" and b1.button("⚙️ Roteirizar na Máquina", key=f"dossie_maquina_{conteudo_id}"):
            abrir_na_maquina(c)
        with b2.popover("🗑️ Excluir"):
            st.write("Excluir este conteúdo e todo o histórico dele?")
            if st.button("Confirmar exclusão", key=f"dossie_del_{conteudo_id}", type="primary"):
                db.excluir_conteudo(conteudo_id)
                avisar("Conteúdo excluído.", "🗑️")
                st.rerun()

    with aba_refs:
        if c["assunto_id"] and (assunto := db.obter_assunto(c["assunto_id"])):
            st.markdown(f"**🔥 Assunto Quente de origem:** {assunto['tema']} ({assunto['intensidade']}%)")
        if c["conteudo_pai_id"]:
            pai = db.obter_conteudo(c["conteudo_pai_id"])
            st.markdown(f"**♻️ Reciclado de:** #{c['conteudo_pai_id']} · {pai['titulo'] if pai else '(excluído)'}")
        if reciclagens := db.listar_reciclagens(conteudo_id):
            st.markdown("**♻️ Versões recicladas a partir deste:**")
            for r in reciclagens:
                st.markdown(f"- #{r['id']} · {r['titulo']} · {r['formato']} · {rotulo_status(r['status'])}")
        validacao = db.obter_validacao(c["validacao_id"]) if c["validacao_id"] else None
        if validacao:
            st.markdown(f"**🌡️ Score de Viralização:** {validacao['score_viralizacao']}% "
                        f"(validado em {data_br(validacao['criado_em'])})")
            if validacao["lacuna"]:
                st.success(f"🎯 **Lacuna:** {validacao['lacuna']}")
        if c["referencias"]:
            st.markdown("**🔗 Referências:**")
            for ref in c["referencias"]:
                st.markdown(f"- {ref}")
        if not (c["assunto_id"] or c["conteudo_pai_id"] or validacao or c["referencias"]):
            st.caption("Sem referências registradas.")

    with aba_hist:
        c1, c2, c3 = st.columns(3)
        c1.metric("Criado em", data_br(c["criado_em"])[:10])
        c2.metric("Última alteração", data_br(c["atualizado_em"])[:10])
        c3.metric("Postado em", data_br(c["data_postagem"]))
        for e in reversed(db.listar_historico(conteudo_id)):
            st.markdown(f"**{data_br(e['criado_em'])}** · {ROTULOS_EVENTO.get(e['evento'], e['evento'])} — "
                        f"{detalhes_evento(e)}")

    with aba_metricas:
        metricas = db.listar_metricas(conteudo_id)
        if metricas:
            st.dataframe(pd.DataFrame(metricas)[["marco_dias", "views", "saves", "shares", "comments", "likes"]]
                         .rename(columns={"marco_dias": "Dias", "views": "Views", "saves": "Salvamentos",
                                          "shares": "Compartilhamentos", "comments": "Comentários",
                                          "likes": "Curtidas"}),
                         hide_index=True, width="stretch")
        elif c["status"] == "postado":
            st.info("As métricas de 7 e 14 dias são registradas pelo 📊 Dashboard, que avisa quando chegar a hora.")
        else:
            st.caption("As métricas aparecem aqui depois que o conteúdo for postado.")


@st.dialog("♻️ Reciclar conteúdo", width="large")
def dialog_reciclar(conteudo_id: int) -> None:
    c = db.obter_conteudo(conteudo_id)
    st.markdown(f"**Original:** {c['titulo']} · {c['formato'] or 'sem formato'}")
    if c["gancho"]:
        st.caption(f"🪝 Gancho original: “{c['gancho']}”")
    opcoes = [f for f in maquina.FORMATOS if f != c["formato"]]
    c1, c2 = st.columns(2)
    formato = c1.selectbox("Novo formato", opcoes, key=f"rec_formato_{conteudo_id}")
    formato_livre = c2.text_input("...ou outro formato", key=f"rec_formato_livre_{conteudo_id}").strip()
    formato = formato_livre or formato
    funil = st.radio("Funil", list(maquina.FUNIS), format_func=maquina.FUNIS.get, horizontal=True,
                     index=list(maquina.FUNIS).index(c["funil"]) if c["funil"] else 0, key=f"rec_funil_{conteudo_id}")
    instrucoes = st.text_area("Instruções (opcional)", key=f"rec_instr_{conteudo_id}",
                              placeholder="Ex.: focar no erro mais comentado, versão mais curta...")
    chave = f"m3_reciclagem_{conteudo_id}"
    if st.button("✨ Gerar versão reciclada", type="primary"):
        with st.spinner("Reescrevendo para o novo formato..."):
            try:
                st.session_state[chave] = cofre.reciclar_conteudo(conteudo_id, formato, funil, instrucoes)
            except LLMError as exc:
                st.error(str(exc))

    if novo := st.session_state.get(chave):
        st.divider()
        if novo["palavras_proibidas_usadas"]:
            st.warning("⚠️ Palavras proibidas na versão gerada: " + ", ".join(novo["palavras_proibidas_usadas"]))
        st.markdown(f"**{novo['titulo']}** · {novo['formato']}")
        st.markdown(f"🪝 **Gancho:** {novo['gancho']}")
        tabela_roteiro(novo["roteiro"], novo["formato"], f"rec_preview_{conteudo_id}")
        st.text_area("Legenda", novo["legenda"], disabled=True, key=f"rec_leg_{conteudo_id}")
        st.caption(" ".join(novo["hashtags"]))
        if st.button("💾 Salvar como novo card em 'Roteiros Prontos'", key=f"rec_salvar_{conteudo_id}"):
            novo_id = cofre.salvar_reciclagem(conteudo_id, novo)
            st.session_state.pop(chave, None)
            avisar(f"Versão reciclada #{novo_id} criada em 'Roteiros Prontos'!", "♻️")
            st.rerun()


# ===========================================================================
# Página
# ===========================================================================
if aviso := st.session_state.pop("_aviso_cofre", None):
    st.toast(aviso[0], icon=aviso[1])

st.title("🗄️ Cofre de Ideias")
st.caption("Do radar ao post: acompanhe cada conteúdo, abra o Dossiê completo e recicle o que já foi publicado.")

personas = {p["id"]: p["nome"] for p in db.listar_personas()}
f1, f2, f3, f4, f5 = st.columns([1.3, 1, 1, 1.6, 0.9])
filtro_persona = f1.selectbox("Persona", [None] + list(personas), key="m3_persona",
                              format_func=lambda i: "Todas" if i is None else personas[i])
filtro_plataforma = f2.selectbox("Plataforma", [None, "tiktok", "instagram", "youtube"], key="m3_plataforma",
                                 format_func=lambda p: "Todas" if p is None else ROTULOS_PLATAFORMA[p])
filtro_funil = f3.selectbox("Funil", [None] + list(maquina.FUNIS), key="m3_funil",
                            format_func=lambda f: "Todos" if f is None else ROTULOS_FUNIL[f])
busca = f4.text_input("Buscar", key="m3_busca", placeholder="título, gancho ou legenda")
f5.write("")
f5.write("")
if f5.button("💡 Nova ideia", type="primary", width="stretch"):
    dialog_nova_ideia()

conteudos = db.listar_conteudos(filtro_persona, filtro_plataforma, filtro_funil, busca)
pendentes = {a["conteudo_id"] for a in db.listar_alertas_metricas()}
if not conteudos and not any((filtro_persona, filtro_plataforma, filtro_funil, busca)):
    st.info("O Cofre está vazio. Crie roteiros na ⚙️ Máquina de Conteúdo ou adicione uma 💡 Nova ideia.")

colunas = st.columns(len(STATUS))
for indice, (coluna, status) in enumerate(zip(colunas, STATUS)):
    cards = [c for c in conteudos if c["status"] == status]
    with coluna:
        st.markdown(f"#### {ICONES_COLUNA[status]} {db.STATUS_KANBAN_LABELS[status]} `{len(cards)}`")
        if not cards:
            st.caption("Nada por aqui.")
        for c in cards:
            with st.container(border=True):
                st.markdown(f"**{c['titulo']}**")
                info = [ROTULOS_PLATAFORMA.get(c["plataforma"], ""), c["persona"] or "Sem persona"]
                if c["formato"]:
                    info.append(c["formato"])
                if c["funil"]:
                    info.append(ROTULOS_FUNIL[c["funil"]])
                st.caption(" · ".join(i for i in info if i))
                selos = []
                if c["score_viralizacao"] is not None:
                    selos.append(f"🌡️ {c['score_viralizacao']}%")
                if status == "postado":
                    selos.append(f"📅 {data_br(c['data_postagem'])}")
                    if c["id"] in pendentes:
                        selos.append("🔔 métricas pendentes")
                    elif c["total_metricas"]:
                        selos.append(f"📊 {c['total_metricas']} métrica(s)")
                if c["conteudo_pai_id"]:
                    selos.append("♻️ reciclado")
                if c["total_reciclagens"]:
                    selos.append(f"♻️ {c['total_reciclagens']} versão(ões)")
                if selos:
                    st.caption(" · ".join(selos))

                b1, b2, b3, b4 = st.columns(4)
                if indice > 0 and b1.button("◀", key=f"voltar_{c['id']}",
                                            help=f"Voltar para {db.STATUS_KANBAN_LABELS[STATUS[indice - 1]]}"):
                    db.mover_conteudo(c["id"], STATUS[indice - 1])
                    st.rerun()
                if b2.button("📂", key=f"abrir_{c['id']}", help="Abrir Dossiê"):
                    dialog_dossie(c["id"])
                if status == "ideia" and b3.button("⚙️", key=f"maquina_{c['id']}", help="Roteirizar na Máquina"):
                    abrir_na_maquina(c)
                if status == "postado" and b3.button("♻️", key=f"reciclar_{c['id']}", help="Reciclar em novo formato"):
                    dialog_reciclar(c["id"])
                if indice < len(STATUS) - 1 and b4.button(
                        "▶", key=f"avancar_{c['id']}", help=f"Mover para {db.STATUS_KANBAN_LABELS[STATUS[indice + 1]]}"):
                    if STATUS[indice + 1] == "postado":
                        dialog_postar(c["id"])
                    else:
                        db.mover_conteudo(c["id"], STATUS[indice + 1])
                        st.rerun()
