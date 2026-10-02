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
    assert len(db.listar_assuntos_quentes()) == 3
    assert any("Resumo da audiência" in m.value for m in at.info)
