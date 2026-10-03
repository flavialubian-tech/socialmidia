import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from streamlit.testing.v1 import AppTest

import database as db
from services import radar
from tests.test_cerebro import RESPOSTA_IA

RAIZ = Path(__file__).resolve().parents[1]
PAGINA = str(RAIZ / "modulos" / "m1_cerebro.py")


def test_app_principal_carrega():
    at = AppTest.from_file(str(RAIZ / "app.py")).run(timeout=30)
    assert not at.exception


def test_configuracoes_carrega():
    at = AppTest.from_file(str(RAIZ / "modulos" / "configuracoes.py")).run(timeout=30)
    assert not at.exception


def test_criar_persona_pela_tela():
    at = AppTest.from_file(PAGINA).run(timeout=30)
    assert not at.exception
    at.text_input[0].input("Criadora TikTok")
    at.text_area[0].input("Mulheres 25-35")
    at.text_input[1].input("barato, milagre, barato")
    at.button[0].click().run(timeout=30)  # "Salvar persona" (primeiro botão de form)
    assert not at.exception
    persona = db.listar_personas()[0]
    assert persona["nome"] == "Criadora TikTok"
    assert persona["palavras_proibidas"] == ["barato", "milagre"]


def test_radar_manual_pela_tela(monkeypatch):
    db.criar_persona("Skin", "tiktok")
    monkeypatch.setattr(radar, "criar_llm",
                        lambda **_: FakeListChatModel(responses=[json.dumps(RESPOSTA_IA)]))
    at = AppTest.from_file(PAGINA).run(timeout=30)
    at.radio(key="radar_metodo").set_value("✍️ Colar / enviar arquivo").run(timeout=30)
    at.text_area(key="radar_texto").input("ana: não tenho tempo\nbia: quero rotina simples").run(timeout=30)
    botao = next(b for b in at.button if "Analisar" in b.label)
    assert not botao.disabled
    botao.click().run(timeout=30)
    assert not at.exception, at.exception
    assert len(db.listar_assuntos_quentes()) == 4  # 3 tendências + 1 dor
    assert any("Resumo da audiência" in m.value for m in at.info)


# --- Rastreador Automático ---------------------------------------------------
def test_rastreador_pela_tela(monkeypatch):
    from services import rastreador

    disparos = []
    monkeypatch.setattr(rastreador, "executar_em_segundo_plano", lambda ag, rid=None: disparos.append(rid))
    at = AppTest.from_file(PAGINA).run(timeout=30)
    campo = next(t for t in at.text_area if "Palavras-chave" in t.label)
    campo.input("limpeza porcelanato manchado\ndicas para afiliados\n")
    next(b for b in at.button if b.label == "Adicionar ao rastreador").click().run(timeout=30)
    assert not at.exception, at.exception
    assert sorted(r["palavra_chave"] for r in db.listar_rastreadores()) == [
        "dicas para afiliados", "limpeza porcelanato manchado"]
    assert any("Piloto automático ligado" in s.value for s in at.success)

    next(b for b in at.button if "Executar todas agora" in b.label).click().run(timeout=30)
    assert disparos == [None]


# --- Módulo 2: fluxo completo ----------------------------------------------
PAGINA_M2 = str(RAIZ / "modulos" / "m2_maquina_conteudo.py")


def test_maquina_fluxo_completo(monkeypatch):
    from services import llm as llm_mod
    from services import maquina
    from tests.test_maquina import RESPOSTA_ROTEIRO, RESPOSTA_VALIDACAO, VIDEOS

    monkeypatch.setenv("APIFY_API_TOKEN", "teste")
    respostas = FakeListChatModel(responses=[
        json.dumps(RESPOSTA_VALIDACAO),
        json.dumps({"formatos": [{"formato": "Antes e depois", "por_que": "visual", "exemplo_gancho": "Olha"}]}),
        json.dumps(RESPOSTA_ROTEIRO),
    ])
    monkeypatch.setattr(llm_mod, "criar_llm", lambda *a, **k: respostas)
    original = maquina.validar_tema
    monkeypatch.setattr(maquina, "validar_tema", lambda *a, **k: original(
        *a, **k, buscar=lambda *_: VIDEOS, coletar=lambda *_: []))

    pid = db.criar_persona("Limpeza", "tiktok")
    aid = db.criar_assunto_quente("Mancha no porcelanato", persona_id=pid, intensidade=90)

    at = AppTest.from_file(PAGINA_M2).run(timeout=30)
    assert not at.exception, at.exception
    at.selectbox(key="m2_persona").set_value(pid).run(timeout=30)
    next(b for b in at.button if "Medir viralização" in b.label).click().run(timeout=30)
    assert not at.exception, at.exception
    assert any("A Lacuna" in s.value for s in at.success)

    next(b for b in at.button if "Sugerir formatos" in b.label).click().run(timeout=30)
    assert any("Antes e depois" in m.value for m in at.markdown)

    next(b for b in at.button if "Gerar roteiro" in b.label).click().run(timeout=30)
    assert not at.exception, at.exception
    assert at.text_area(key="m2_gancho_1").value == RESPOSTA_ROTEIRO["gancho"]

    at.text_input(key="m2_titulo_1").input("Meu título").run(timeout=30)
    next(b for b in at.button if "Salvar no Cofre" in b.label).click().run(timeout=30)
    assert not at.exception, at.exception
    with db.get_connection() as c:
        cid = c.execute("SELECT id FROM conteudos").fetchone()[0]
    salvo = db.obter_conteudo(cid)
    assert salvo["titulo"] == "Meu título" and salvo["formato"] == "Antes e depois"
    assert salvo["assunto_id"] == aid and salvo["status"] == "roteiro_pronto"
    assert len(salvo["roteiro"]) == 2
    assert db.obter_assunto(aid)["status"] == "em_uso"


def test_maquina_pular_validacao_e_aba_historico():
    db.criar_persona("P", "instagram")
    at = AppTest.from_file(PAGINA_M2).run(timeout=30)
    at.radio(key="m2_fonte").set_value("✍️ Tema livre").run(timeout=30)
    at.text_input(key="m2_tema_livre").input("Tema livre qualquer").run(timeout=30)
    next(b for b in at.button if "Pular validação" in b.label).click().run(timeout=30)
    assert not at.exception, at.exception
    assert any(b.label.startswith("✨ Gerar roteiro") for b in at.button)
    assert any("Nenhuma validação ainda" in i.value for i in at.info)


# --- Módulo 3: Kanban --------------------------------------------------------
PAGINA_M3 = str(RAIZ / "modulos" / "m3_cofre_ideias.py")


def test_kanban_mostra_colunas_e_move_cards():
    pid = db.criar_persona("Limpeza", "tiktok")
    ideia = db.criar_ideia("Minha ideia", pid, "tiktok")
    pronto = db.criar_conteudo("Roteiro A", persona_id=pid, plataforma="tiktok", formato="Vídeo POV")
    postado = db.criar_conteudo("Post antigo", persona_id=pid, plataforma="tiktok")
    db.mover_conteudo(postado, "postado", "2026-09-01")

    at = AppTest.from_file(PAGINA_M3).run(timeout=30)
    assert not at.exception, at.exception
    titulos = [m.value for m in at.markdown]
    assert any("Ideias no Radar" in t and "`1`" in t for t in titulos)
    assert any("Postado" in t and "`1`" in t for t in titulos)
    assert any("métricas pendentes" in c.value for c in at.caption)

    at.button(key=f"avancar_{pronto}").click().run(timeout=30)
    assert db.obter_conteudo(pronto)["status"] == "em_edicao"
    at.button(key=f"voltar_{pronto}").click().run(timeout=30)
    assert db.obter_conteudo(pronto)["status"] == "roteiro_pronto"

    at.selectbox(key="m3_plataforma").set_value("instagram").run(timeout=30)
    assert any("Nada por aqui" in c.value for c in at.caption)
    assert ideia


def test_kanban_ideia_vai_para_maquina():
    ideia = db.criar_ideia("Ideia para roteirizar", plataforma="youtube")
    at = AppTest.from_file(PAGINA_M3).run(timeout=30)
    at.button(key=f"maquina_{ideia}").click().run(timeout=30)
    assert not at.exception, at.exception
    pendente = at.session_state["m2_pendente"]
    assert pendente["conteudo_id"] == ideia and pendente["plataforma"] == "youtube"
    assert pendente["tema"] == "Ideia para roteirizar"


def test_kanban_abre_dossie():
    cid = db.criar_conteudo("Com dossiê", gancho="Gancho X", roteiro=[{"tempo": "0-3s", "audio": "a", "tela": "b"}])
    at = AppTest.from_file(PAGINA_M3).run(timeout=30)
    at.button(key=f"abrir_{cid}").click().run(timeout=30)
    assert not at.exception, at.exception
    assert any(t.value == "Gancho X" for t in at.text_area)
