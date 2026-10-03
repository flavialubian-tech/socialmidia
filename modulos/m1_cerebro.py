"""MÓDULO 1 — Cérebro: Multi-Personas, Radar de Audiência e Assuntos Quentes."""

from datetime import datetime, time

import pandas as pd
import streamlit as st

import database as db
from modulos.comum import obter_agendador
from services import rastreador as rastreador_srv
from services import scraper
from services.llm import LLMError, PROVEDORES, config_atual, obter_segredo
from services.radar import executar_radar

ROTULOS_PLATAFORMA = {
    "instagram": "📸 Instagram",
    "tiktok": "🎵 TikTok",
    "youtube": "▶️ YouTube",
    "multiplataforma": "🌐 Multiplataforma",
}
ROTULOS_STATUS_ASSUNTO = {"novo": "🔥 Novo", "em_uso": "✍️ Em uso", "usado": "✅ Usado", "descartado": "🗑️ Descartado"}
ROTULOS_STATUS_BUSCA = {"pendente": "⏳", "coletando": "📥", "analisando": "🧠", "concluido": "✅", "erro": "❌"}
ROTULOS_TIPO_ASSUNTO = {"tendencia": "📈 Tendência", "dor": "😣 Dor", "manual": "✍️ Manual",
                        "reciclagem": "♻️ Reciclar (alta performance)"}
ROTULOS_STATUS_EXECUCAO = {"executando": "⏳ Rodando", "concluido": "✅ Concluído",
                           "sem_resultados": "🤷 Sem resultados", "erro": "❌ Erro"}
ICONE_FREQUENCIA = {"alta": "🔴", "media": "🟠", "baixa": "🟡"}


def avisar(mensagem: str, icone: str = "✅") -> None:
    """Mostra um toast que sobrevive ao st.rerun()."""
    st.session_state["_aviso_cerebro"] = (mensagem, icone)


def lista_de_texto(texto: str) -> list[str]:
    itens = [p.strip() for p in texto.replace("\n", ",").split(",")]
    return list(dict.fromkeys(i for i in itens if i))  # remove vazios e duplicados


def seletor_persona(chave: str, rotulo: str = "Persona", permitir_vazio: bool = True) -> int | None:
    personas = db.listar_personas()
    opcoes = ([None] if permitir_vazio else []) + [p["id"] for p in personas]
    nomes = {p["id"]: f"{p['nome']} · {ROTULOS_PLATAFORMA[p['plataforma']]}" for p in personas}
    return st.selectbox(rotulo, opcoes, key=chave,
                        format_func=lambda i: "— Todas / nenhuma —" if i is None else nomes[i])


if aviso := st.session_state.pop("_aviso_cerebro", None):
    st.toast(aviso[0], icon=aviso[1])

st.title("🧠 Cérebro")
st.caption("Quem você é para cada público, o que esse público sente e sobre o que ele quer ouvir agora.")

aba_personas, aba_radar, aba_rastreador, aba_assuntos, aba_historico = st.tabs(
    ["👤 Personas", "📡 Radar de Audiência", "🤖 Rastreador Automático", "🔥 Assuntos Quentes",
     "🕘 Histórico do Radar"]
)

# ===========================================================================
# PERSONAS
# ===========================================================================
with aba_personas:
    with st.expander("➕ Nova persona", expanded=not db.listar_personas(somente_ativas=False)):
        with st.form("form_nova_persona", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            nome = c1.text_input("Nome do perfil *", placeholder="Ex.: Criadora TikTok, Empresa B2B Instagram")
            plataforma = c2.selectbox("Plataforma", db.PLATAFORMAS, format_func=ROTULOS_PLATAFORMA.get)
            publico = st.text_area("Público-alvo", placeholder="Ex.: Mulheres de 25 a 40 anos, empreendedoras iniciantes...")
            tom = st.text_area("Tom de voz", placeholder="Ex.: Próxima, divertida, direta, sem termos técnicos...")
            proibidas = st.text_input("Palavras proibidas (separadas por vírgula)", placeholder="Ex.: barato, promoção, milagre")
            descricao = st.text_area("Notas adicionais (opcional)")
            if st.form_submit_button("Salvar persona", type="primary"):
                if not nome.strip():
                    st.error("Informe o nome da persona.")
                else:
                    try:
                        db.criar_persona(nome, plataforma, publico, tom, lista_de_texto(proibidas), descricao)
                        avisar(f"Persona '{nome.strip()}' criada!")
                        st.rerun()
                    except db.sqlite3.IntegrityError:
                        st.error("Já existe uma persona com esse nome.")

    mostrar_inativas = st.toggle("Mostrar personas arquivadas", value=False)
    personas = db.listar_personas(somente_ativas=not mostrar_inativas)
    if not personas:
        st.info("Nenhuma persona cadastrada ainda. Crie a primeira acima. 👆")

    for p in personas:
        titulo = f"{ROTULOS_PLATAFORMA[p['plataforma']]} **{p['nome']}**" + ("" if p["ativo"] else " · _arquivada_")
        with st.expander(titulo):
            with st.form(f"form_persona_{p['id']}"):
                c1, c2 = st.columns([2, 1])
                nome = c1.text_input("Nome", p["nome"])
                plataforma = c2.selectbox("Plataforma", db.PLATAFORMAS, index=db.PLATAFORMAS.index(p["plataforma"]),
                                          format_func=ROTULOS_PLATAFORMA.get)
                publico = st.text_area("Público-alvo", p["publico_alvo"])
                tom = st.text_area("Tom de voz", p["tom_de_voz"])
                proibidas = st.text_input("Palavras proibidas", ", ".join(p["palavras_proibidas"]))
                descricao = st.text_area("Notas adicionais", p["descricao"])
                if st.form_submit_button("💾 Salvar alterações"):
                    try:
                        db.atualizar_persona(p["id"], nome=nome.strip(), plataforma=plataforma, publico_alvo=publico,
                                             tom_de_voz=tom, palavras_proibidas=lista_de_texto(proibidas),
                                             descricao=descricao)
                        avisar("Persona atualizada!")
                        st.rerun()
                    except db.sqlite3.IntegrityError:
                        st.error("Já existe uma persona com esse nome.")

            c1, c2, _ = st.columns([1, 1, 2])
            if p["ativo"]:
                if c1.button("📦 Arquivar", key=f"arq_{p['id']}", help="Some das listas, mas mantém o histórico."):
                    db.atualizar_persona(p["id"], ativo=0)
                    avisar("Persona arquivada.", "📦")
                    st.rerun()
            elif c1.button("♻️ Reativar", key=f"reat_{p['id']}"):
                db.atualizar_persona(p["id"], ativo=1)
                avisar("Persona reativada.")
                st.rerun()
            with c2.popover("🗑️ Excluir"):
                st.write("Excluir de vez? Conteúdos e análises ficam sem persona.")
                if st.button("Confirmar exclusão", key=f"del_{p['id']}", type="primary"):
                    db.excluir_persona(p["id"])
                    avisar("Persona excluída.", "🗑️")
                    st.rerun()


# ===========================================================================
# RADAR DE AUDIÊNCIA
# ===========================================================================
def mostrar_analise(analise: dict) -> None:
    if analise.get("resumo"):
        st.info(f"**Resumo da audiência:** {analise['resumo']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Dores encontradas", len(analise["dores"]))
    c2.metric("Termos no dicionário", len(analise["dicionario"]))
    c3.metric("Assuntos quentes", len(analise["tendencias"]))

    st.markdown("#### 😣 Dores principais")
    for d in analise["dores"]:
        st.markdown(f"{ICONE_FREQUENCIA.get(d.get('frequencia'), '⚪')} **{d['dor']}**")
        if d.get("evidencia"):
            st.caption(f"💬 “{d['evidencia']}”")

    st.markdown("#### 📖 Dicionário do público")
    if analise["dicionario"]:
        st.dataframe(pd.DataFrame(analise["dicionario"]).rename(
            columns={"termo": "Termo", "significado": "Significado", "exemplo": "Exemplo"}),
            hide_index=True, width="stretch")

    st.markdown("#### 🔥 Alertas de tendência")
    for t in analise["tendencias"]:
        with st.container(border=True):
            st.markdown(f"**{t['tema']}**")
            st.progress(t["intensidade"] / 100, text=f"Intensidade {t['intensidade']}%")
            st.write(t.get("motivo", ""))
            if t.get("angulo_sugerido"):
                st.caption(f"💡 Ângulo sugerido: {t['angulo_sugerido']}")


with aba_radar:
    cfg = config_atual()
    st.caption(f"IA em uso: **{PROVEDORES.get(cfg.provedor, cfg.provedor)}** · `{cfg.modelo}` — altere em ⚙️ Configurações.")

    persona_radar = seletor_persona("radar_persona", "Analisar para qual persona?")
    metodo = st.radio("Como obter os comentários?", ["🤖 Coleta automática (Apify)", "✍️ Colar / enviar arquivo"],
                      horizontal=True, key="radar_metodo")
    automatico = metodo.startswith("🤖")

    comentarios_manuais: list[dict] | None = None
    if automatico:
        url = st.text_input("URL do post (TikTok, Instagram ou YouTube)",
                            placeholder="https://www.tiktok.com/@perfil/video/123...", key="radar_url")
        limite = st.slider("Máximo de comentários", 50, 1000,
                           int(db.get_config("radar_limite_comentarios", "300")), step=50)
        if url and not scraper.url_valida(url):
            st.warning("Essa URL não parece válida.")
        elif url and scraper.detectar_plataforma(url) == "desconhecida":
            st.warning("Rede não reconhecida. Use um link do TikTok, Instagram ou YouTube.")
        if not obter_segredo("APIFY_API_TOKEN"):
            st.warning("Token da Apify não configurado. Cadastre em ⚙️ Configurações ou use a opção de colar comentários.")
    else:
        url = st.text_input("URL de referência (opcional)", key="radar_url_manual")
        limite = 0
        texto = st.text_area("Cole os comentários (um por linha; 'usuario: comentário' também funciona)",
                             height=200, key="radar_texto")
        arquivo = st.file_uploader("...ou envie um arquivo .txt / .csv", type=["txt", "csv"], key="radar_arquivo")
        try:
            comentarios_manuais = scraper.parse_texto_manual(texto) if texto else []
            if arquivo is not None:
                comentarios_manuais += scraper.parse_arquivo(arquivo.name, arquivo.getvalue())
            if comentarios_manuais:
                st.caption(f"📝 {len(comentarios_manuais)} comentários prontos para análise.")
        except scraper.ColetaError as exc:
            st.error(str(exc))
            comentarios_manuais = []

    pode_rodar = (automatico and scraper.url_valida(url or "")) or (not automatico and bool(comentarios_manuais))
    if st.button("🔍 Analisar audiência", type="primary", disabled=not pode_rodar):
        with st.status("Iniciando o Radar...", expanded=True) as status:
            try:
                resultado = executar_radar(
                    url or "manual",
                    comentarios=None if automatico else comentarios_manuais,
                    persona_id=persona_radar,
                    limite=limite or 300,
                    progresso=lambda msg: status.update(label=msg) or st.write(msg),
                )
                status.update(label="Análise concluída!", state="complete", expanded=False)
                st.session_state["radar_ultima_analise"] = resultado.analise_id
                st.toast(f"{len(resultado.assuntos_criados)} novos Assuntos Quentes adicionados!", icon="🔥")
            except (scraper.ColetaError, LLMError) as exc:
                status.update(label="Não foi possível concluir", state="error")
                st.error(str(exc))
            except Exception as exc:  # erro inesperado: mostra detalhes para depuração
                status.update(label="Erro inesperado", state="error")
                st.exception(exc)

    if analise_id := st.session_state.get("radar_ultima_analise"):
        analise = db.obter_analise(analise_id)
        if analise:
            st.divider()
            st.subheader(f"Resultado · {analise['total_comentarios']} comentários analisados")
            mostrar_analise(analise)


# ===========================================================================
# ASSUNTOS QUENTES
# ===========================================================================
with aba_assuntos:
    st.caption("Temas que a Máquina de Conteúdo (Módulo 2) vai usar como ponto de partida.")
    c1, c2 = st.columns(2)
    with c1:
        persona_filtro = seletor_persona("assuntos_persona", "Filtrar por persona")
    status_filtro = c2.multiselect("Status", list(ROTULOS_STATUS_ASSUNTO), default=["novo", "em_uso"],
                                   format_func=ROTULOS_STATUS_ASSUNTO.get)

    with st.expander("➕ Adicionar assunto manualmente"):
        with st.form("form_assunto_manual", clear_on_submit=True):
            tema = st.text_input("Tema *")
            descricao = st.text_area("Por que esse tema importa?")
            intensidade = st.slider("Intensidade (seu feeling)", 0, 100, 60)
            persona_manual = seletor_persona("assunto_manual_persona")
            if st.form_submit_button("Adicionar", type="primary"):
                if not tema.strip():
                    st.error("Informe o tema.")
                elif db.criar_assunto_quente(tema, descricao, intensidade, persona_manual, origem="manual",
                                             tipo="manual"):
                    avisar("Assunto adicionado!", "🔥")
                    st.rerun()
                else:
                    st.warning("Esse assunto já está na lista.")

    assuntos = db.listar_assuntos_quentes(persona_filtro, tuple(status_filtro) or None)
    if not assuntos:
        st.info("Nenhum assunto aqui ainda. Rode o 📡 Radar de Audiência para descobrir temas.")
    for a in assuntos:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{a['tema']}**")
            c1.caption(f"{ROTULOS_STATUS_ASSUNTO[a['status']]} · {a['persona'] or 'Sem persona'} · "
                       f"{ROTULOS_TIPO_ASSUNTO.get(a['tipo'], a['tipo'])} · "
                       f"{'🤖 rastreador: ' + a['rastreador'] if a['rastreador'] else 'origem: ' + a['origem']}"
                       f" · {a['criado_em'][:10]}")
            c2.progress(a["intensidade"] / 100, text=f"{a['intensidade']}%")
            if a["descricao"]:
                st.write(a["descricao"])
            b1, b2, _ = st.columns([1, 1, 3])
            if a["status"] in ("novo", "em_uso"):
                if b1.button("✅ Marcar usado", key=f"usado_{a['id']}"):
                    db.atualizar_status_assunto(a["id"], "usado")
                    st.rerun()
                if b2.button("🗑️ Descartar", key=f"desc_{a['id']}"):
                    db.atualizar_status_assunto(a["id"], "descartado")
                    st.rerun()
            elif b1.button("♻️ Reativar", key=f"reat_assunto_{a['id']}"):
                db.atualizar_status_assunto(a["id"], "novo")
                st.rerun()


# ===========================================================================
# HISTÓRICO DO RADAR
# ===========================================================================
with aba_historico:
    buscas = db.listar_buscas()
    if not buscas:
        st.info("Nenhuma busca realizada ainda.")
    else:
        tabela = pd.DataFrame([{
            "": ROTULOS_STATUS_BUSCA.get(b["status"], ""),
            "Data": b["criado_em"][:16],
            "Persona": b["persona"] or "—",
            "Rede": b["plataforma"],
            "Comentários": b["total_comentarios"],
            "Método": b["metodo_coleta"],
            "URL": b["url"],
        } for b in buscas])
        st.dataframe(tabela, hide_index=True, width="stretch")

        busca_sel = st.selectbox(
            "Abrir busca", [b["id"] for b in buscas],
            format_func=lambda i: next(f"#{b['id']} · {b['criado_em'][:16]} · {b['url'][:60]}" for b in buscas if b["id"] == i),
        )
        busca = next(b for b in buscas if b["id"] == busca_sel)
        if busca["status"] == "erro":
            st.error(f"Erro: {busca['erro']}")
        if busca["analise_id"]:
            mostrar_analise(db.obter_analise(busca["analise_id"]))
        with st.expander(f"💬 Ver comentários coletados ({busca['total_comentarios']})"):
            comentarios = db.listar_comentarios(busca_sel)
            if comentarios:
                st.dataframe(pd.DataFrame(comentarios), hide_index=True, width="stretch")
        with st.popover("🗑️ Excluir esta busca"):
            st.write("Remove a busca, os comentários e a análise. Os Assuntos Quentes gerados continuam.")
            if st.button("Confirmar", key=f"del_busca_{busca_sel}", type="primary"):
                db.excluir_busca(busca_sel)
                if st.session_state.get("radar_ultima_analise") == busca["analise_id"]:
                    st.session_state.pop("radar_ultima_analise")
                avisar("Busca excluída.", "🗑️")
                st.rerun()


# ===========================================================================
# RASTREADOR AUTOMÁTICO (piloto automático)
# ===========================================================================
def formatar_data(texto: str | None) -> str:
    return datetime.fromisoformat(texto).strftime("%d/%m %H:%M") if texto else "nunca"


@st.fragment(run_every="10s" if db.ha_execucao_em_andamento() else None)
def painel_execucoes() -> None:
    execucoes = db.listar_execucoes(limite=15)
    if not execucoes:
        st.caption("Nenhuma rodada ainda. Elas aparecem aqui assim que o piloto automático trabalhar.")
        return
    if any(e["status"] == "executando" for e in execucoes):
        st.info("⏳ Há rastreadores rodando agora (busca + comentários + IA levam alguns minutos). "
                "Esta lista se atualiza sozinha.")
    for e in execucoes:
        rotulo = (f"{ROTULOS_STATUS_EXECUCAO[e['status']]} · 🔎 {e['palavra_chave']} "
                  f"({ROTULOS_PLATAFORMA[e['plataforma']]}) · {formatar_data(e['iniciado_em'])} · "
                  f"{'🔁 agendado' if e['gatilho'] == 'agendado' else '👆 manual'}")
        with st.expander(rotulo):
            if e["erro"]:
                (st.error if e["status"] == "erro" else st.warning)(e["erro"])
            c1, c2, c3 = st.columns(3)
            c1.metric("Vídeos analisados", len(e["videos"]))
            c2.metric("Comentários lidos", e["total_comentarios"])
            c3.metric("Assuntos novos", e["assuntos_criados"])
            if e["videos"]:
                st.dataframe(
                    pd.DataFrame(e["videos"])[["url", "titulo", "views", "curtidas", "comentarios"]],
                    hide_index=True, width="stretch",
                    column_config={"url": st.column_config.LinkColumn("Vídeo", display_text="abrir ↗"),
                                   "titulo": "Legenda", "views": "Views", "curtidas": "Curtidas",
                                   "comentarios": "Comentários"},
                )
            if e["busca_id"] and st.toggle("Ver análise completa", key=f"ver_exec_{e['id']}"):
                if analise := db.analise_da_busca(e["busca_id"]):
                    mostrar_analise(analise)


with aba_rastreador:
    agendador = obter_agendador()
    ativo, dia, hora = rastreador_srv.config_agenda()
    proxima = rastreador_srv.proximo_horario_agendado(datetime.now(), dia, hora)
    rastreadores = db.listar_rastreadores()
    ativos = [r for r in rastreadores if r["ativo"]]

    st.caption("Cadastre palavras-chave e o app, sozinho, encontra os vídeos mais quentes, lê os comentários "
               "e envia as dores e tendências para 🔥 Assuntos Quentes.")
    if not obter_segredo("APIFY_API_TOKEN"):
        st.warning("O Rastreador usa a Apify. Cadastre o token em ⚙️ Configurações para ele funcionar.")

    if ativo and ativos:
        st.success(f"🟢 **Piloto automático ligado** · {len(ativos)} palavra(s)-chave ativa(s) · "
                   f"próxima rodada: **{db.DIAS_SEMANA[dia]}, {proxima:%d/%m às %H:%M}**")
    elif ativo:
        st.info("🟡 Piloto automático ligado, mas sem palavras-chave ativas. Cadastre abaixo.")
    else:
        st.warning("🔴 Piloto automático desligado. As buscas só rodam quando você clicar em ▶️ Executar.")
    st.caption("ℹ️ As buscas rodam enquanto o app estiver aberto. Se o computador estiver desligado no horário, "
               "a rodada acontece assim que você abrir o app. Para rodar com o app fechado, veja o `worker.py` no README.")

    with st.expander("⏰ Agenda do piloto automático"):
        with st.form("form_agenda"):
            novo_ativo = st.toggle("Ligado", value=ativo)
            c1, c2 = st.columns(2)
            novo_dia = c1.selectbox("Dia da semana", list(db.DIAS_SEMANA), index=list(db.DIAS_SEMANA).index(dia),
                                    format_func=db.DIAS_SEMANA.get)
            h, m = rastreador_srv._hora_minuto(hora)
            nova_hora = c2.time_input("Horário", value=time(h, m), step=1800)
            if st.form_submit_button("💾 Salvar agenda", type="primary"):
                db.set_config("rastreador_agendamento_ativo", "1" if novo_ativo else "0")
                db.set_config("rastreador_dia_semana", novo_dia)
                db.set_config("rastreador_hora", nova_hora.strftime("%H:%M"))
                avisar("Agenda atualizada!", "⏰")
                st.rerun()

    with st.expander("➕ Novas palavras-chave", expanded=not rastreadores):
        with st.form("form_rastreador", clear_on_submit=True):
            palavras = st.text_area("Palavras-chave (uma por linha)",
                                    placeholder="limpeza porcelanato manchado\ndicas para afiliados")
            c1, c2 = st.columns(2)
            plataforma_r = c1.selectbox("Onde buscar", db.PLATAFORMAS_BUSCA, format_func=ROTULOS_PLATAFORMA.get,
                                        help="No Instagram a busca é feita pela hashtag equivalente "
                                             "(ex.: #limpezaporcelanatomanchado).")
            with c2:
                persona_r = seletor_persona("rastreador_persona", "Para qual persona?")
            c3, c4 = st.columns(2)
            max_videos = c3.slider("Vídeos mais quentes por palavra", 1, 10, 5)
            max_coment = c4.slider("Comentários lidos por vídeo", 20, 300, 100, step=10)
            st.caption(f"💰 Cada rodada lê até **{max_videos * max_coment} comentários** por palavra-chave "
                       "(isso consome créditos da Apify).")
            if st.form_submit_button("Adicionar ao rastreador", type="primary"):
                lista = [p.strip() for p in palavras.splitlines() if p.strip()]
                criados = [p for p in lista
                           if db.criar_rastreador(p, plataforma_r, persona_r, max_videos, max_coment)]
                if not lista:
                    st.error("Escreva pelo menos uma palavra-chave.")
                else:
                    repetidas = len(lista) - len(criados)
                    avisar(f"{len(criados)} palavra(s)-chave adicionada(s)"
                           + (f" · {repetidas} já existia(m)" if repetidas else "") + "!", "🤖")
                    st.rerun()

    if rastreadores:
        c1, _ = st.columns([1, 3])
        if c1.button("▶️ Executar todas agora", disabled=not ativos,
                     help="Roda todas as palavras-chave ativas agora, em segundo plano."):
            rastreador_srv.executar_em_segundo_plano(agendador)
            avisar("Rodada iniciada em segundo plano! Acompanhe em 'Rodadas recentes'.", "🚀")
            st.rerun()

    for r in rastreadores:
        with st.container(border=True):
            c1, c2 = st.columns([3, 2])
            c1.markdown(f"{'🟢' if r['ativo'] else '⏸️'} **🔎 {r['palavra_chave']}** · "
                        f"{ROTULOS_PLATAFORMA[r['plataforma']]} · {r['persona'] or 'Sem persona'}")
            c1.caption(f"{r['max_videos']} vídeos × {r['max_comentarios']} comentários · "
                       f"última rodada: {formatar_data(r['ultima_execucao'])}"
                       + (f" ({ROTULOS_STATUS_EXECUCAO[r['ultimo_status']]})" if r["ultimo_status"] else "")
                       + f" · {r['total_assuntos']} assuntos gerados")
            b1, b2, b3 = c2.columns(3)
            if b1.button("▶️", key=f"exec_r_{r['id']}", help="Executar agora"):
                rastreador_srv.executar_em_segundo_plano(agendador, r["id"])
                avisar(f"'{r['palavra_chave']}' rodando em segundo plano!", "🚀")
                st.rerun()
            if b2.button("⏸️" if r["ativo"] else "▶ Ativar", key=f"pausa_r_{r['id']}",
                         help="Pausar" if r["ativo"] else "Reativar"):
                db.atualizar_rastreador(r["id"], ativo=0 if r["ativo"] else 1)
                st.rerun()
            with b3.popover("🗑️", help="Excluir"):
                st.write("Excluir este rastreador? Os assuntos já gerados continuam.")
                if st.button("Confirmar", key=f"del_r_{r['id']}", type="primary"):
                    db.excluir_rastreador(r["id"])
                    avisar("Rastreador excluído.", "🗑️")
                    st.rerun()

    st.markdown("#### 🕘 Rodadas recentes")
    painel_execucoes()
