"""MÓDULO 4 — Estúdio de Produção: Vídeo Automático e Fábrica de Carrosséis."""

from pathlib import Path

import pandas as pd
import streamlit as st

import database as db
from services import carrossel, estudio, maquina, video

FORMATOS_VIDEO = ["mp4", "mov", "m4v", "webm", "mkv"]
ROTULOS_STATUS = {"pendente": "⏳ Aguardando etapa 2", "processando": "⚙️ Processando", "concluido": "✅ Concluído",
                  "erro": "❌ Erro"}
POSICOES = {"topo": "Topo", "centro": "Centro", "base": "Base"}


def avisar(mensagem: str, icone: str = "✅") -> None:
    st.session_state["_aviso_estudio"] = (mensagem, icone)


def seg(valor: float) -> str:
    minutos, segundos = divmod(int(round(valor)), 60)
    return f"{minutos}min {segundos:02d}s" if minutos else f"{segundos}s"


def conteudos_para(formato_carrossel: bool | None = None) -> list[dict]:
    lista = [c for c in db.listar_conteudos() if c["status"] in ("roteiro_pronto", "em_edicao", "ideia")]
    if formato_carrossel is not None:
        lista.sort(key=lambda c: maquina.eh_carrossel(c["formato"]) != formato_carrossel)
    return lista


def seletor_conteudo(chave: str, rotulo: str, formato_carrossel: bool | None = None) -> dict | None:
    lista = conteudos_para(formato_carrossel)
    por_id = {c["id"]: c for c in lista}
    escolhido = st.selectbox(rotulo, [None] + list(por_id), key=chave,
                             format_func=lambda i: "— Nenhum —" if i is None else
                             f"#{i} · {por_id[i]['titulo']} ({por_id[i]['formato'] or 'sem formato'})")
    return por_id.get(escolhido)


if aviso := st.session_state.pop("_aviso_estudio", None):
    st.toast(aviso[0], icon=aviso[1])

st.title("🎬 Estúdio de Produção")
gpu = video.tem_gpu()
st.caption(f"Whisper: modelo **{video.modelo_padrao()}** · {video.texto_diagnostico_gpu()} · "
           "ajuste em ⚙️ Configurações")

aba_video, aba_carrossel, aba_templates, aba_gerados = st.tabs(
    ["🎬 Vídeo Automático", "🖼️ Fábrica de Carrosséis", "🎨 Templates de carrossel", "📁 Arquivos gerados"])

# ===========================================================================
# VÍDEO AUTOMÁTICO
# ===========================================================================
with aba_video:
    job_id = st.session_state.get("m4_job")
    job = db.obter_job(job_id) if job_id else None
    if job and (not job["arquivo_entrada"] or not Path(job["arquivo_entrada"]).exists()):
        job = None

    if not job or job["dados"].get("etapa") == "enviado":
        st.subheader("1️⃣ Enviar o vídeo bruto")
        arquivo = st.file_uploader("Vídeo gravado (MP4, MOV...)", type=FORMATOS_VIDEO, key="m4_upload")
        conteudo = seletor_conteudo("m4_video_conteudo", "Vincular a um conteúdo do Cofre (opcional)", False)
        c1, c2, c3 = st.columns(3)
        cortar = c1.toggle("✂️ Cortar pausas", value=True)
        muletas = c2.toggle("🗣️ Cortar \"ééé\", \"hum\", \"ahn\"", value=True, disabled=not cortar,
                            help="Usa o Whisper para achar os vícios de linguagem e remove cada um inteiro.")
        legendas = c3.toggle("📝 Gerar legendas (Whisper)", value=True)
        with st.expander("⚙️ Ajustes finos do corte"):
            extras = st.text_input("Outras palavras para cortar (separadas por vírgula)", placeholder="tipo, né",
                                   help="Cuidado: palavras como \"né\" e \"tipo\" saem SEMPRE que aparecerem.")
            limiar = st.slider("Sensibilidade do silêncio (dB)", -55, -20, -35,
                               help="Mais perto de -20 corta mais (inclusive falas baixas). "
                                    "Mais perto de -55 corta só silêncio absoluto. Com ruído de fundo "
                                    "(ventilador, ar-condicionado), o app sobe esse valor sozinho.")
            min_silencio = st.slider("Pausa mínima para cortar (s)", 0.2, 1.5, 0.45, 0.05,
                                     help="Pausas menores que isso ficam (respiração natural).")
            margem = st.slider("Respiro antes/depois de cada fala (s)", 0.0, 0.4, 0.12, 0.02)
        if st.button("✂️ Etapa 1: cortar e transcrever", type="primary", disabled=arquivo is None):
            barra = st.progress(0.0, text="Preparando...")
            try:
                novo = estudio.novo_video(arquivo.name, arquivo.getvalue(),
                                          conteudo["titulo"] if conteudo else "", conteudo["id"] if conteudo else None)
                st.session_state["m4_job"] = novo
                estudio.etapa_cortar(novo, limiar, min_silencio, margem, cortar, legendas, usar_gpu=gpu,
                                     remover_muletas=cortar and muletas,
                                     muletas_extras=[e.strip() for e in extras.split(",") if e.strip()],
                                     progresso=lambda msg, p: barra.progress(min(1.0, p), text=msg))
                st.rerun()
            except video.VideoError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.exception(exc)
    else:
        dados = job["dados"]
        pasta = Path(job["arquivo_entrada"]).parent
        topo1, topo2 = st.columns([3, 1])
        topo1.subheader(f"🎞️ {job['titulo'] or 'Vídeo'}")
        if topo2.button("🆕 Novo vídeo", width="stretch"):
            st.session_state.pop("m4_job", None)
            st.rerun()

        # ---- 2. Revisão ----------------------------------------------------
        st.markdown("#### 2️⃣ Revisar corte e legendas")
        original, final = dados.get("duracao_original", 0), dados.get("duracao_final", 0)
        muletas_removidas = dados.get("muletas", [])
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Duração original", seg(original))
        m2.metric("Depois do corte", seg(final),
                  f"-{(1 - final / original) * 100:.0f}%" if original else None, delta_color="off")
        m3.metric("Cortes", max(0, dados.get("trechos", 1) - 1))
        m4.metric("Vícios removidos", len(muletas_removidas))
        m5.metric("Palavras transcritas", len(dados.get("palavras", [])))
        if muletas_removidas:
            st.caption("🗣️ Removidos: " + ", ".join(f"“{m['texto']}” ({seg(m['inicio'])})"
                                                    for m in muletas_removidas[:30]))
        if dados.get("aviso_transcricao"):
            st.warning(f"Legendas indisponíveis: {dados['aviso_transcricao']}")
        if (pasta / "cortado.mp4").exists():
            with st.expander("▶️ Ver vídeo cortado (sem efeitos)"):
                st.video(str(pasta / "cortado.mp4"))
        palavras = dados.get("palavras", [])
        if palavras:
            with st.expander("✏️ Corrigir a transcrição"):
                st.caption("Ajuste palavras escritas errado antes de renderizar. Os tempos estão em segundos.")
                editadas = st.data_editor(pd.DataFrame(palavras, columns=["texto", "inicio", "fim"]),
                                          num_rows="dynamic", hide_index=True, width="stretch",
                                          key=f"m4_palavras_{job['id']}",
                                          column_config={"texto": "Palavra", "inicio": st.column_config.NumberColumn(
                                              "Início", format="%.2f"), "fim": st.column_config.NumberColumn(
                                              "Fim", format="%.2f")})
                palavras = [{"texto": str(r["texto"]).strip(), "inicio": float(r["inicio"]), "fim": float(r["fim"])}
                            for r in editadas.dropna().to_dict("records") if str(r["texto"]).strip()]

        # ---- 3. Estilo -----------------------------------------------------
        st.markdown("#### 3️⃣ Legendas, zooms e motions")
        conteudo = db.obter_conteudo(job["conteudo_id"]) if job["conteudo_id"] else None
        cfg_salva = dados.get("config", {})
        col_leg, col_zoom, col_motion = st.columns(3)
        with col_leg:
            st.markdown("**📝 Legendas**")
            usar_legendas = st.toggle("Mostrar legendas", value=cfg_salva.get("legendas", bool(palavras)),
                                      disabled=not palavras)
            estilos = ["hormozi", "cor", "pilula"]
            estilo = st.radio("Estilo da legenda", estilos, horizontal=True,
                              index=estilos.index(cfg_salva.get("estilo_legenda", "hormozi"))
                              if cfg_salva.get("estilo_legenda", "hormozi") in estilos else 0,
                              format_func={"hormozi": "🔥 Hormozi", "cor": "Cor", "pilula": "Pílula"}.get,
                              help="Hormozi: 1–2 palavras gigantes por vez, pop a cada palavra e cores alternando.")
            cor = st.color_picker("Cor de destaque",
                                  cfg_salva.get("cor_destaque", db.get_config("estudio_cor_destaque", "#FFD60A")))
            tamanho = st.slider("Tamanho", 5, 14, int(cfg_salva.get("tamanho_legenda", 0.095) * 100),
                                help="% da largura do vídeo")
            posicao = st.slider("Altura na tela (%)", 50, 80, int(cfg_salva.get("posicao_legenda", 0.66) * 100),
                                help="66% fica abaixo do rosto e dentro da área segura do Reels/TikTok")
            max_palavras = st.slider("Palavras por vez", 1, 5, cfg_salva.get("max_palavras", 3))
        with col_zoom:
            st.markdown("**🔍 Zooms dinâmicos**")
            zooms = st.toggle("Ativar zooms", value=cfg_salva.get("zooms", True))
            intensidade = st.slider("Intensidade", 0.3, 1.5, float(cfg_salva.get("intensidade_zoom", 1.0)), 0.1,
                                    disabled=not zooms)
            zoom_cortes = st.checkbox("Alternar zoom a cada corte (disfarça os cortes)",
                                      value=cfg_salva.get("zoom_cortes", True), disabled=not zooms)
            punch = st.checkbox("Punch-in nas palavras de ênfase", value=cfg_salva.get("punch_enfase", True),
                                disabled=not zooms, help="Números, exclamações, palavras longas ou em CAIXA ALTA.")
            formato = st.radio("Formato final", ["original", "9:16"], horizontal=True,
                               index=0 if cfg_salva.get("formato", "9:16") == "original" else 1,
                               format_func={"original": "Original", "9:16": "Vertical 9:16"}.get)
        with col_motion:
            st.markdown("**✨ Motions**")
            ken_burns = st.checkbox("Movimento suave de câmera (Ken Burns)", value=cfg_salva.get("ken_burns", True))
            titulo = st.text_area("Título animado do gancho (primeiros segundos)",
                                  cfg_salva.get("titulo", (conteudo or {}).get("gancho", "")), height=80)
            duracao_titulo = st.slider("Duração do título (s)", 1.5, 6.0, float(cfg_salva.get("duracao_titulo", 3.0)),
                                       0.5, disabled=not titulo.strip())
            barra_prog = st.checkbox("Barra de progresso no topo", value=cfg_salva.get("barra_progresso", True))
            usar_gpu = st.checkbox("Exportar com a GPU (NVENC)", value=cfg_salva.get("usar_gpu", gpu),
                                   help="Mais rápido em placas NVIDIA. Se não funcionar, o app usa a CPU sozinho.")

        # ---- Motion graphics ------------------------------------------------
        st.markdown("**🎨 Motion graphics**")
        mg1, mg2, mg3 = st.columns(3)
        with mg1:
            stickers = st.checkbox("Stickers flat 2D (✔ ✖ 💡 💰 ⏰ 📈 …)", value=cfg_salva.get("stickers", True),
                                   help="Aparecem quando você fala palavras como erro, dica, dinheiro, tempo, resultado.")
            destaques = st.checkbox("Tipografia cinética nos números", value=cfg_salva.get("destaques", True),
                                    help="\"3 ERROS\", \"72 HORAS\", \"50%\" entram palavra por palavra.")
            transicoes = st.selectbox("Transição nos cortes", ["alternado", "flash", "zoom", "glitch", "nenhuma"],
                                      index=["alternado", "flash", "zoom", "glitch", "nenhuma"].index(
                                          cfg_salva.get("transicoes", "alternado")),
                                      format_func={"alternado": "Alternar (flash/zoom/glitch)", "flash": "Flash",
                                                   "zoom": "Zoom com desfoque", "glitch": "Glitch",
                                                   "nenhuma": "Nenhuma"}.get)
        with mg2:
            abertura = st.checkbox("Selo de abertura com seu @", value=cfg_salva.get("abertura", True))
            nome_abertura = st.text_input("Seu @", cfg_salva.get("nome_abertura", db.get_config("estudio_arroba", "")),
                                          placeholder="@seuperfil", disabled=not abertura)
            cta = st.checkbox("CTA final animado (com toque no botão)", value=cfg_salva.get("cta", True))
            ctas = ["salvar", "seguir", "comentar", "link"]
            cta_tipo = st.selectbox("Chamada", ctas, index=ctas.index(cfg_salva.get("cta_tipo", "salvar")),
                                    format_func={"salvar": "Salva esse vídeo", "seguir": "Segue pra mais dicas",
                                                 "comentar": "Comenta aqui embaixo", "link": "Link na bio"}.get,
                                    disabled=not cta)
        with mg3:
            sons = st.checkbox("Efeitos sonoros (whoosh, pop, clique, ding)", value=cfg_salva.get("sons", True))
            volume_sons = st.slider("Volume dos efeitos", 0.1, 1.0, float(cfg_salva.get("volume_sons", 0.5)), 0.1,
                                    disabled=not sons)
            acabamento = st.checkbox("Acabamento de cinema (cor + vinheta)", value=cfg_salva.get("acabamento", True))
            granulado = st.checkbox("Granulado de filme", value=cfg_salva.get("granulado", True),
                                    disabled=not acabamento)
        if nome_abertura.strip() and nome_abertura.strip() != db.get_config("estudio_arroba", ""):
            db.set_config("estudio_arroba", nome_abertura.strip())

        config = video.ConfigEdicao(
            formato=formato, legendas=usar_legendas and bool(palavras), estilo_legenda=estilo, cor_destaque=cor,
            tamanho_legenda=tamanho / 100, posicao_legenda=posicao / 100, max_palavras=max_palavras, zooms=zooms,
            intensidade_zoom=intensidade, zoom_cortes=zoom_cortes, punch_enfase=punch, ken_burns=ken_burns,
            titulo=titulo.strip(), duracao_titulo=duracao_titulo, barra_progresso=barra_prog, usar_gpu=usar_gpu,
            fonte=None, stickers=stickers, destaques=destaques, abertura=abertura,
            nome_abertura=nome_abertura.strip(), cta=cta, cta_tipo=cta_tipo, transicoes=transicoes, sons=sons,
            volume_sons=volume_sons, acabamento=acabamento, granulado=granulado,
        )
        from services import fontes as fontes_srv

        config.fonte = fontes_srv.fonte_configurada()

        with st.expander("👁️ Prévia de um quadro", expanded=True):
            c1, c2 = st.columns([1, 2])
            instante = c1.slider("Instante (s)", 0.0, max(0.1, float(final)), min(1.0, float(final) / 2), 0.1)
            c1.caption("Mostra exatamente como o quadro vai ficar no vídeo final.")
            try:
                c2.image(video.previa_quadro(pasta / "cortado.mp4", palavras, dados.get("inicios", [0.0]), config,
                                             instante), width=300 if formato == "9:16" else 520)
            except Exception as exc:
                c2.warning(f"Não foi possível gerar a prévia: {exc}")

        if st.button("🎬 Etapa 2: renderizar vídeo final", type="primary"):
            barra = st.progress(0.0, text="Renderizando quadro a quadro...")
            try:
                estudio.etapa_renderizar(job["id"], config, palavras,
                                         progresso=lambda p: barra.progress(p, text=f"Renderizando... {p * 100:.0f}%"))
                avisar("Vídeo pronto!", "🎬")
                st.rerun()
            except video.VideoError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.exception(exc)

        if job["status"] == "concluido" and job["arquivo_saida"] and Path(job["arquivo_saida"]).exists():
            st.markdown("#### ✅ Vídeo final")
            c1, c2 = st.columns([1, 1])
            c1.video(job["arquivo_saida"])
            c2.download_button("⬇️ Baixar vídeo", Path(job["arquivo_saida"]).read_bytes(),
                               file_name=f"{job['titulo'] or 'video'}_final.mp4".replace(" ", "_"),
                               mime="video/mp4", type="primary")
            info = dados.get("resultado", {})
            if info:
                c2.caption(f"{info.get('largura')}×{info.get('altura')} · {seg(info.get('duracao', 0))} · "
                           f"{info.get('paginas_legenda', 0)} legendas · {info.get('zooms_enfase', 0)} punch-ins · "
                           f"{info.get('stickers', 0)} stickers · {info.get('destaques', 0)} destaques · "
                           f"codec {info.get('codec')}")
        elif job["status"] == "erro":
            st.error(f"Último erro: {job['erro']}")

# ===========================================================================
# FÁBRICA DE CARROSSÉIS
# ===========================================================================
with aba_carrossel:
    templates = db.listar_templates()
    nomes_t = {t["id"]: t["nome"] for t in templates}
    if not templates:
        st.info("Cadastre suas imagens de fundo na aba 🎨 Templates. Enquanto isso, as lâminas usam um fundo escuro liso.")

    origem = st.radio("Texto das lâminas", ["🗄️ Conteúdo do Cofre", "✍️ Texto livre"], horizontal=True,
                      key="m4_car_origem")
    conteudo_car = None
    if origem.startswith("🗄️"):
        conteudo_car = seletor_conteudo("m4_car_conteudo", "Conteúdo (carrosséis aparecem primeiro)", True)
        texto_inicial = "\n\n".join(carrossel.laminas_do_conteudo(conteudo_car)) if conteudo_car else ""
        texto = st.text_area("Lâminas (uma por bloco; linha em branco separa). Use *asteriscos* para destacar.",
                             texto_inicial, height=260, key=f"m4_car_texto_{conteudo_car['id'] if conteudo_car else 0}")
    else:
        texto = st.text_area("Lâminas (uma por bloco; linha em branco separa). Use *asteriscos* para destacar.",
                             height=260, key="m4_car_texto_livre",
                             placeholder="3 erros que *mancham* o porcelanato\n\nErro 1: usar água sanitária pura...")
    laminas = carrossel.dividir_texto(texto) if texto.strip() else []

    c1, c2, c3 = st.columns(3)
    opcoes_t = [None] + list(nomes_t)
    template_id = c1.selectbox("Template das lâminas", opcoes_t, key="m4_car_template", index=1 if templates else 0,
                               format_func=lambda i: "Fundo escuro liso" if i is None else nomes_t[i])
    capa_id = c2.selectbox("Template da capa (opcional)", opcoes_t, key="m4_car_capa",
                           format_func=lambda i: "Igual às lâminas" if i is None else nomes_t[i])
    tamanho_nome = c3.selectbox("Tamanho", list(carrossel.TAMANHOS), key="m4_car_tamanho")
    c4, c5, c6 = st.columns(3)
    assinatura = c4.text_input("Assinatura no rodapé", key="m4_car_assinatura", placeholder="@seuperfil")
    contador = c5.checkbox("Mostrar contador (1/8)", value=True, key="m4_car_contador")
    mover = c6.checkbox("Mover card para 'Em Edição'", value=True, key="m4_car_mover", disabled=conteudo_car is None)
    st.caption(f"🧾 {len(laminas)} lâmina(s)")

    b1, b2, _ = st.columns([1, 1, 2])
    previa = b1.button("👁️ Pré-visualizar", disabled=not laminas)
    gerar = b2.button("📦 Gerar carrossel (.zip)", type="primary", disabled=not laminas)
    if previa or gerar:
        tamanho_px = carrossel.TAMANHOS[tamanho_nome]
        try:
            if gerar:
                imagens, zip_bytes, novo_job = estudio.gerar_carrossel(
                    laminas, template_id, capa_id, tamanho_px, assinatura, contador,
                    conteudo_car["id"] if conteudo_car else None,
                    conteudo_car["titulo"] if conteudo_car else "Carrossel", mover and conteudo_car is not None)
                st.session_state["m4_car_zip"] = (novo_job, zip_bytes)
                st.success(f"Carrossel com {len(imagens)} lâminas pronto!")
            else:
                imagens = carrossel.gerar_carrossel(laminas, db.obter_template(template_id) if template_id else None,
                                                    db.obter_template(capa_id) if capa_id else None, tamanho_px,
                                                    assinatura, contador)
            colunas = st.columns(4)
            for i, imagem in enumerate(imagens):
                colunas[i % 4].image(imagem, caption=f"Lâmina {i + 1}", width="stretch")
        except carrossel.CarrosselError as exc:
            st.error(str(exc))
    if zip_salvo := st.session_state.get("m4_car_zip"):
        st.download_button("⬇️ Baixar .zip", zip_salvo[1], file_name=f"carrossel_{zip_salvo[0]}.zip",
                           mime="application/zip", type="primary", key="m4_car_download")

# ===========================================================================
# TEMPLATES
# ===========================================================================
with aba_templates:
    personas = {p["id"]: p["nome"] for p in db.listar_personas()}
    with st.expander("➕ Novo template", expanded=not db.listar_templates()):
        with st.form("form_template", clear_on_submit=True):
            imagem = st.file_uploader("Imagem de fundo (JPG/PNG)", type=["jpg", "jpeg", "png", "webp"])
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome *", placeholder="Ex.: Porcelanato claro")
            persona_t = c2.selectbox("Persona", [None] + list(personas),
                                     format_func=lambda i: "Todas" if i is None else personas[i])
            c3, c4, c5 = st.columns(3)
            cor_texto = c3.color_picker("Cor do texto", "#FFFFFF")
            cor_dest = c4.color_picker("Cor de destaque", db.get_config("estudio_cor_destaque", "#FFD60A"))
            escurecer = c5.slider("Escurecer a imagem (%)", 0, 80, 35, help="Garante a leitura do texto.")
            c6, c7, c8 = st.columns(3)
            posicao_t = c6.selectbox("Posição do texto", list(POSICOES), index=1, format_func=POSICOES.get)
            alinhamento = c7.selectbox("Alinhamento", ["centro", "esquerda"], format_func=str.capitalize)
            tamanho_fonte = c8.slider("Tamanho do texto", 40, 120, 72)
            margem_t = st.slider("Margem lateral (px)", 40, 200, 90)
            if st.form_submit_button("Salvar template", type="primary"):
                if not imagem or not nome.strip():
                    st.error("Envie a imagem e dê um nome ao template.")
                else:
                    estudio.salvar_template(nome, imagem.name, imagem.getvalue(), persona_id=persona_t,
                                            cor_texto=cor_texto, cor_destaque=cor_dest, escurecer=escurecer,
                                            posicao=posicao_t, alinhamento=alinhamento, tamanho_fonte=tamanho_fonte,
                                            margem=margem_t, fonte=None)
                    avisar("Template salvo!", "🎨")
                    st.rerun()

    lista_t = db.listar_templates()
    colunas = st.columns(3)
    for i, t in enumerate(lista_t):
        with colunas[i % 3].container(border=True):
            amostra = carrossel.renderizar_lamina("Seu texto com *destaque* aqui", t, 1, 3, (540, 675))
            st.image(amostra, width="stretch")
            st.markdown(f"**{t['nome']}** · {t['persona'] or 'Todas as personas'}")
            st.caption(f"Texto {POSICOES.get(t['posicao'], t['posicao']).lower()} · escurecer {t['escurecer']}%")
            with st.popover("🗑️ Excluir"):
                if st.button("Confirmar exclusão", key=f"del_tpl_{t['id']}", type="primary"):
                    estudio.excluir_template(t["id"])
                    avisar("Template excluído.", "🗑️")
                    st.rerun()

# ===========================================================================
# ARQUIVOS GERADOS
# ===========================================================================
with aba_gerados:
    jobs = db.listar_jobs()
    if not jobs:
        st.info("Os vídeos e carrosséis gerados aparecem aqui.")
    for j in jobs:
        icone = "🎬" if j["tipo"] == "video" else "🖼️"
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"{icone} **{j['titulo'] or j['tipo']}** · {ROTULOS_STATUS.get(j['status'], j['status'])}")
            c1.caption(f"#{j['id']} · {j['criado_em'][:16]}" + (f" · conteúdo: {j['conteudo']}" if j["conteudo"] else ""))
            saida = Path(j["arquivo_saida"]) if j["arquivo_saida"] else None
            if saida and saida.exists():
                c2.download_button("⬇️ Baixar", saida.read_bytes(), file_name=saida.name, key=f"down_job_{j['id']}",
                                   mime="video/mp4" if j["tipo"] == "video" else "application/zip")
            elif j["tipo"] == "video" and j["status"] in ("pendente", "erro") and c2.button("Continuar",
                                                                                             key=f"cont_job_{j['id']}"):
                st.session_state["m4_job"] = j["id"]
                avisar("Trabalho reaberto na aba 🎬 Vídeo Automático.", "🎬")
                st.rerun()
            with c3.popover("🗑️"):
                st.write("Excluir o trabalho e os arquivos dele?")
                if st.button("Confirmar", key=f"del_job_{j['id']}", type="primary"):
                    estudio.excluir_trabalho(j["id"])
                    if st.session_state.get("m4_job") == j["id"]:
                        st.session_state.pop("m4_job")
                    st.rerun()
