import json
from datetime import date

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import database as db
from services import radar, scraper
from services.llm import LLMError, extrair_json, gerar_json

RESPOSTA_IA = {
    "resumo": "Público quer rotina de skincare simples.",
    "dores": [{"dor": "Não tem tempo", "evidencia": "não tenho 10 min", "frequencia": "Alta"}],
    "dicionario": [{"termo": "skin", "significado": "pele", "exemplo": "minha skin tá ótima"}],
    "tendencias": [
        {"tema": "Skincare em 3 passos", "motivo": "muitos pedidos", "intensidade": "85", "angulo_sugerido": "POV"},
        {"tema": "Produto barato que funciona", "motivo": "x", "intensidade": 70, "angulo_sugerido": ""},
        {"tema": "Protetor solar no inverno", "motivo": "dúvidas", "intensidade": 150},
    ],
}
COMENTARIOS = [
    {"autor": "ana", "texto": "não tenho 10 min de manhã", "curtidas": 50},
    {"autor": "bia", "texto": "faz um vídeo de rotina simples!", "curtidas": 10},
    {"autor": "bia", "texto": "faz um vídeo de rotina simples!", "curtidas": 1},
]


def llm_falso(*respostas):
    return FakeListChatModel(responses=list(respostas))


# --- Banco -----------------------------------------------------------------
def test_init_db_idempotente_e_configuracoes():
    db.init_db()
    assert db.get_config("llm_provedor") == "ollama"
    db.set_config("llm_provedor", "anthropic")
    db.init_db()
    assert db.get_config("llm_provedor") == "anthropic"


def test_crud_persona():
    pid = db.criar_persona(" Criadora ", "tiktok", palavras_proibidas=["barato"])
    assert db.obter_persona(pid)["nome"] == "Criadora"
    db.atualizar_persona(pid, tom_de_voz="leve", palavras_proibidas=["a", "b"], campo_invalido=1)
    p = db.obter_persona(pid)
    assert p["tom_de_voz"] == "leve" and p["palavras_proibidas"] == ["a", "b"]
    db.atualizar_persona(pid, ativo=0)
    assert db.listar_personas() == [] and len(db.listar_personas(somente_ativas=False)) == 1
    db.excluir_persona(pid)
    assert db.obter_persona(pid) is None


def test_assunto_quente_nao_duplica():
    pid = db.criar_persona("P")
    assert db.criar_assunto_quente("Tema X", persona_id=pid, intensidade=300)
    assert db.criar_assunto_quente("tema x", persona_id=pid) is None
    assert db.criar_assunto_quente("tema x") is not None  # outra persona (nenhuma)
    assert db.listar_assuntos_quentes(pid)[0]["intensidade"] == 100


def test_alertas_metricas():
    with db.get_connection() as c:
        c.execute("INSERT INTO conteudos (titulo, status, data_postagem) VALUES ('A', 'postado', '2026-09-15')")
        c.execute("INSERT INTO metricas (conteudo_id, marco_dias) VALUES (1, 7)")
    alertas = db.listar_alertas_metricas(date(2026, 10, 2))
    assert [a["marco_dias"] for a in alertas] == [14]


# --- LLM / JSON ------------------------------------------------------------
def test_extrair_json_com_cercas_e_texto():
    assert extrair_json('Claro! ```json\n{"a": 1}\n``` pronto') == {"a": 1}
    with pytest.raises(LLMError):
        extrair_json("sem json aqui")


def test_gerar_json_tenta_de_novo():
    assert gerar_json("x", llm=llm_falso("ops", '{"ok": true}')) == {"ok": True}


# --- Scraper ---------------------------------------------------------------
def test_detectar_plataforma():
    assert scraper.detectar_plataforma("https://www.tiktok.com/@a/video/1") == "tiktok"
    assert scraper.detectar_plataforma("https://youtu.be/abc") == "youtube"
    assert scraper.detectar_plataforma("https://instagram.com/p/x") == "instagram"
    assert scraper.detectar_plataforma("https://site.com") == "desconhecida"


def test_parse_manual_e_csv():
    itens = scraper.parse_texto_manual("@ana: amei demais\n\nquero parte 2\n")
    assert itens[0]["autor"] == "ana" and itens[0]["texto"] == "amei demais"
    assert itens[1]["autor"] is None
    csv_bytes = "usuario;comentario;likes\nana;muito bom;12\nbia;;3\n".encode()
    assert scraper.parse_csv(csv_bytes) == [
        {"autor": "ana", "texto": "muito bom", "curtidas": 12, "publicado_em": None}]


def test_normalizar_itens_apify():
    tiktok = scraper.normalizar_item_apify({"text": "oi", "diggCount": 5, "uniqueId": "ana"})
    youtube = scraper.normalizar_item_apify({"comment": "top", "voteCount": "1.234", "author": "@bia"})
    assert tiktok == {"autor": "ana", "texto": "oi", "curtidas": 5, "publicado_em": None}
    assert youtube["curtidas"] == 1234
    assert scraper.normalizar_item_apify({"text": ""}) is None


def test_coleta_sem_token_da_erro_amigavel():
    with pytest.raises(scraper.ColetaError, match="APIFY_API_TOKEN"):
        scraper.coletar_apify("https://www.tiktok.com/@a/video/1")


# --- Radar -----------------------------------------------------------------
def test_preparar_comentarios_ordena_e_deduplica():
    texto = radar.preparar_comentarios(COMENTARIOS)
    assert texto.splitlines() == ["[50] não tenho 10 min de manhã", "[10] faz um vídeo de rotina simples!"]


def test_normalizar_analise_filtra_proibidas_e_limita():
    analise = radar.normalizar_analise(RESPOSTA_IA, ["barato"])
    assert [t["tema"] for t in analise["tendencias"]] == ["Protetor solar no inverno", "Skincare em 3 passos"]
    assert analise["tendencias"][0]["intensidade"] == 100
    assert analise["dores"][0]["frequencia"] == "alta"


def test_executar_radar_manual_completo():
    pid = db.criar_persona("Skin", "tiktok", palavras_proibidas=["barato"])
    resultado = radar.executar_radar("", comentarios=COMENTARIOS, persona_id=pid,
                                     llm=llm_falso(json.dumps(RESPOSTA_IA)))
    assert resultado.total_comentarios == 3
    assert len(resultado.assuntos_criados) == 3  # 2 tendências + 1 dor de frequência alta
    assert {a["tipo"] for a in db.listar_assuntos_quentes(pid)} == {"tendencia", "dor"}
    busca = db.listar_buscas()[0]
    assert busca["status"] == "concluido" and busca["metodo_coleta"] == "manual"
    assert busca["analise_id"] == resultado.analise_id
    assert db.obter_analise(resultado.analise_id)["dicionario"][0]["termo"] == "skin"
    # Rodar de novo não duplica assuntos ainda ativos
    again = radar.executar_radar("", comentarios=COMENTARIOS, persona_id=pid,
                                 llm=llm_falso(json.dumps(RESPOSTA_IA)))
    assert again.assuntos_criados == []


def test_executar_radar_registra_erro():
    with pytest.raises(LLMError):
        radar.executar_radar("", comentarios=COMENTARIOS, llm=llm_falso("nada", "nada"))
    busca = db.listar_buscas()[0]
    assert busca["status"] == "erro" and "JSON" in busca["erro"]
