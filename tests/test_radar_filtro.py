import json
import sqlite3

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import database as db
from services import llm as llm_mod
from services import radar

LONGO = "como faço pra tirar mancha de ferrugem do porcelanato sem estragar o brilho"
COMENTARIOS = [
    {"texto": LONGO, "curtidas": 30},
    {"texto": "boa dica 😍", "curtidas": 50},
    {"texto": "Bom dia, seguindo todas! amei demais", "curtidas": 5},
    {"texto": "😂😂😂🔥🔥", "curtidas": 9},
    {"texto": "@maria @joana 👀", "curtidas": 2},
    {"texto": LONGO.upper() + "!!", "curtidas": 1},  # repetido (mesmo texto)
    {"texto": "verdade", "curtidas": 0},
    {"texto": "eu uso vinagre e bicarbonato e ficou manchado, o que eu fiz de errado?", "curtidas": 12},
]
QUENTES = {"resumo": "r", "dores": [{"dor": "mancha", "evidencia": "x", "frequencia": "alta"}],
           "dicionario": [{"termo": "porce", "significado": "porcelanato"}],
           "tendencias": [{"tema": "Ferrugem no piso", "motivo": "m", "intensidade": 70}],
           "comentarios_quentes": [
               {"comentario": LONGO, "por_que": "dúvida comum", "ideia": "Tire ferrugem sem perder o brilho",
                "potencial": 90},
               {"comentario": "outro", "por_que": "p", "ideia": "Ideia fraca", "potencial": 40},
               {"comentario": "barato", "por_que": "p", "ideia": "Produto barato milagroso", "potencial": 95}]}


def test_contar_palavras():
    assert radar.contar_palavras("@ana olha isso 😍 https://x.com/a muito bom") == 4
    assert radar.contar_palavras("😂😂🔥") == 0
    assert radar.contar_palavras("Tenho 3 filhos e 2 cachorros") == 6


def test_filtrar_comentarios():
    relevantes, stats = radar.filtrar_comentarios(COMENTARIOS, min_palavras=8)
    assert [c["texto"] for c in relevantes] == [LONGO, COMENTARIOS[7]["texto"]]
    assert stats == {"coletados": 8, "relevantes": 2, "curtos": 0, "so_emoji": 2, "genericos": 3, "repetidos": 1,
                     "min_palavras": 8}
    assert "8 comentários → 2 relevantes" in radar.resumo_filtro(stats)
    # mínimo menor deixa passar frases curtas que não são genéricas
    relevantes, _ = radar.filtrar_comentarios([{"texto": "qual produto você usa?"}], min_palavras=3)
    assert len(relevantes) == 1


def test_dividir_em_lotes_mantem_todos():
    comentarios = [{"texto": f"comentário número {i} " + "palavra " * 20, "curtidas": i} for i in range(50)]
    lotes = radar.dividir_em_lotes(comentarios, 1000)
    linhas = [ln for lote in lotes for ln in lote.splitlines()]
    assert len(linhas) == 50 and len(lotes) > 1
    assert all(len(lote) <= 1000 + 200 for lote in lotes)
    assert linhas[0].startswith("[49]")  # mais curtido primeiro


def test_analise_em_lotes_com_sintese():
    comentarios = [{"texto": f"dúvida {i}: " + "como limpar o rejunte encardido do banheiro " * 3, "curtidas": i}
                   for i in range(30)]
    n_lotes = len(radar.dividir_em_lotes(comentarios, 2000))
    respostas = [json.dumps(QUENTES)] * (n_lotes + 1)
    modelo = FakeListChatModel(responses=respostas)
    etapas = []
    analise = radar.analisar_comentarios(comentarios, {"nome": "P", "plataforma": "tiktok",
                                                       "palavras_proibidas": ["barato"]},
                                         llm=modelo, max_caracteres=2000, progresso=etapas.append)
    assert n_lotes > 1
    assert sum("lendo o lote" in e for e in etapas) == n_lotes and any("Juntando" in e for e in etapas)
    assert [q["ideia"] for q in analise["comentarios_quentes"]] == ["Tire ferrugem sem perder o brilho",
                                                                    "Ideia fraca"]  # proibida removida


def test_executar_radar_filtra_e_cria_assunto_de_comentario():
    pid = db.criar_persona("Limpeza", palavras_proibidas=["barato"])
    resultado = radar.executar_radar("", comentarios=COMENTARIOS, persona_id=pid,
                                     llm=FakeListChatModel(responses=[json.dumps(QUENTES)]))
    assert resultado.total_comentarios == 2 and resultado.filtro["coletados"] == 8
    busca = db.listar_buscas()[0]
    assert busca["total_coletados"] == 8 and json.loads(busca["filtro"])["so_emoji"] == 2
    assert len(db.listar_comentarios(busca["id"])) == 2
    analise = db.obter_analise(resultado.analise_id)
    assert [q["potencial"] for q in analise["comentarios_quentes"]] == [90, 40]
    assert analise["filtro"]["relevantes"] == 2 and analise["total_coletados"] == 8
    assuntos = db.listar_assuntos_quentes(pid)
    comentario = next(a for a in assuntos if a["tipo"] == "comentario")
    assert comentario["tema"] == "Tire ferrugem sem perder o brilho" and LONGO in comentario["descricao"]
    assert not any(a["tema"] == "Ideia fraca" for a in assuntos)  # potencial < 60 não vira assunto


def test_tudo_filtrado_da_erro_explicativo():
    from services import scraper

    with pytest.raises(scraper.ColetaError, match="Diminua o mínimo de palavras"):
        radar.executar_radar("", comentarios=COMENTARIOS[1:5], llm=FakeListChatModel(responses=["{}"]))


def test_min_palavras_vem_da_configuracao():
    db.set_config("radar_min_palavras", "3")
    resultado = radar.executar_radar("", comentarios=[{"texto": "qual produto você usa nisso?"}],
                                     llm=FakeListChatModel(responses=[json.dumps(QUENTES)]))
    assert resultado.total_comentarios == 1


def test_erro_do_ollama_vira_mensagem_clara():
    class Quebrado:
        def invoke(self, _):
            raise RuntimeError("error reading llama-server response: read tcp 127.0.0.1: wsarecv (status code: 500)")

    with pytest.raises(llm_mod.LLMError, match="falta de memória") as exc:
        llm_mod.gerar_texto("oi", llm=Quebrado())
    assert "llama3.2:3b" in str(exc.value)
    assert "chave de API foi recusada" in llm_mod.traduzir_erro(Exception("Error code: 401 invalid x-api-key"))


def test_migracao_v3_para_v4(tmp_path, monkeypatch):
    antigo = tmp_path / "v3.db"
    conn = sqlite3.connect(antigo)
    for versao in (1, 2, 3):
        conn.executescript(db.MIGRATIONS[versao])
    conn.execute("PRAGMA user_version = 3")
    conn.execute("INSERT INTO radar_buscas (url) VALUES ('x')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", antigo)
    db.init_db()
    busca = db.listar_buscas()[0]
    assert busca["total_coletados"] == 0 and busca["filtro"] == "{}"
    assert db.get_config("radar_min_palavras") == "8"
