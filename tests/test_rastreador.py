import json
import sqlite3
from datetime import datetime

from langchain_core.language_models.fake_chat_models import FakeListChatModel

import database as db
from services import rastreador, scraper
from tests.test_cerebro import COMENTARIOS, RESPOSTA_IA

VIDEOS = [
    {"url": "https://www.tiktok.com/@a/video/1", "titulo": "dica", "views": 1000, "curtidas": 10,
     "comentarios": 5, "compartilhamentos": 1},
    {"url": "https://www.tiktok.com/@b/video/2", "titulo": "sem comentários", "views": 9, "curtidas": 0,
     "comentarios": 0, "compartilhamentos": 0},
]


def llm():
    return FakeListChatModel(responses=[json.dumps(RESPOSTA_IA)])


def rastreador_fake(chamadas):
    def buscar(palavra, plataforma, quantidade):
        chamadas.append(("buscar", palavra, plataforma, quantidade))
        return VIDEOS

    def coletar(urls, plataforma, limite):
        chamadas.append(("coletar", urls, plataforma, limite))
        return COMENTARIOS

    return buscar, coletar


# --- Agenda ----------------------------------------------------------------
def test_ultimo_e_proximo_horario():
    sexta_manha = datetime(2026, 10, 2, 7, 0)  # 02/10/2026 é uma sexta-feira
    assert rastreador.ultimo_horario_agendado(sexta_manha, "fri", "08:00") == datetime(2026, 9, 25, 8, 0)
    assert rastreador.ultimo_horario_agendado(datetime(2026, 10, 2, 9, 0), "fri", "08:00") == datetime(2026, 10, 2, 8)
    assert rastreador.proximo_horario_agendado(sexta_manha, "fri", "08:00") == datetime(2026, 10, 2, 8, 0)
    assert rastreador.ultimo_horario_agendado(datetime(2026, 10, 5, 12), "fri", "08:00") == datetime(2026, 10, 2, 8)


def test_esta_pendente():
    base = {"ativo": 1, "criado_em": "2026-09-01 10:00:00", "ultima_execucao": None}
    agora = datetime(2026, 10, 2, 9, 0)
    assert rastreador.esta_pendente(base, agora, "fri", "08:00")
    # Já rodou depois das 08:00 de hoje
    assert not rastreador.esta_pendente({**base, "ultima_execucao": "2026-10-02 08:05:00"}, agora, "fri", "08:00")
    # Rodou na semana passada -> pendente (cobre computador desligado na sexta)
    assert rastreador.esta_pendente({**base, "ultima_execucao": "2026-09-25 08:05:00"},
                                    datetime(2026, 10, 4, 15), "fri", "08:00")
    # Criado depois do último horário: espera a próxima sexta
    assert not rastreador.esta_pendente({**base, "criado_em": "2026-10-02 08:30:00"}, agora, "fri", "08:00")
    # Pausado
    assert not rastreador.esta_pendente({**base, "ativo": 0}, agora, "fri", "08:00")
    # Falhou há pouco: aguarda antes de tentar de novo
    assert not rastreador.esta_pendente(base, agora, "fri", "08:00", ultima_tentativa=datetime(2026, 10, 2, 8, 0))


# --- Execução --------------------------------------------------------------
def test_executar_rastreador_completo():
    pid = db.criar_persona("Limpeza", "tiktok", palavras_proibidas=["barato"])
    rid = db.criar_rastreador("limpeza porcelanato manchado", "tiktok", pid, max_videos=2, max_comentarios=50)
    chamadas = []
    buscar, coletar = rastreador_fake(chamadas)
    res = rastreador.executar_rastreador(rid, "manual", llm=llm(), buscar=buscar, coletar=coletar)

    assert res["status"] == "concluido" and len(res["assuntos"]) == 3
    assert chamadas[0] == ("buscar", "limpeza porcelanato manchado", "tiktok", 2)
    assert chamadas[1][1] == [VIDEOS[0]["url"]]  # vídeo sem comentários é ignorado
    execucao = db.listar_execucoes()[0]
    assert execucao["status"] == "concluido" and execucao["assuntos_criados"] == 3
    assert execucao["videos"][0]["url"] == VIDEOS[0]["url"]
    assuntos = db.listar_assuntos_quentes(pid)
    assert all(a["rastreador"] == "limpeza porcelanato manchado" for a in assuntos)
    assert db.obter_rastreador(rid)["ultima_execucao"] is not None
    assert db.listar_buscas()[0]["metodo_coleta"] == "rastreador"


def test_executar_rastreador_sem_videos_e_erro():
    rid = db.criar_rastreador("nada", "youtube")
    res = rastreador.executar_rastreador(rid, buscar=lambda *a: [], coletar=lambda *a: [])
    assert res["status"] == "sem_resultados"

    def falha(*_):
        raise scraper.ColetaError("token inválido")

    rid2 = db.criar_rastreador("outra", "tiktok")
    res = rastreador.executar_rastreador(rid2, buscar=falha)
    assert res["status"] == "erro"
    assert db.listar_execucoes(rid2)[0]["erro"] == "token inválido"
    assert db.obter_rastreador(rid2)["ultima_execucao"] is None  # erro não conta como rodada feita


def test_nao_executa_duas_vezes_em_paralelo():
    rid = db.criar_rastreador("x", "tiktok")
    assert db.iniciar_execucao(rid) is not None
    assert db.iniciar_execucao(rid) is None
    assert db.ha_execucao_em_andamento()
    assert rastreador.executar_rastreador(rid, buscar=lambda *a: 1 / 0) is None


def test_executar_pendentes_respeita_agenda(monkeypatch):
    rid = db.criar_rastreador("pendente", "tiktok")
    with db.get_connection() as c:
        c.execute("UPDATE rastreadores SET criado_em = '2026-09-01 10:00:00' WHERE id = ?", (rid,))
    db.criar_rastreador("pausado", "tiktok")
    with db.get_connection() as c:
        c.execute("UPDATE rastreadores SET criado_em = '2026-09-01 10:00:00', ativo = 0 WHERE palavra_chave = 'pausado'")
    chamadas = []
    buscar, coletar = rastreador_fake(chamadas)
    agora = datetime(2026, 10, 2, 9, 0)

    db.set_config("rastreador_agendamento_ativo", "0")
    assert rastreador.executar_pendentes(agora, llm=llm(), buscar=buscar, coletar=coletar) == []

    db.set_config("rastreador_agendamento_ativo", "1")
    resultados = rastreador.executar_pendentes(agora, llm=llm(), buscar=buscar, coletar=coletar)
    assert [r["status"] for r in resultados] == ["concluido"]
    assert [c[1] for c in chamadas if c[0] == "buscar"] == ["pendente"]


def test_rastreador_nao_duplica():
    assert db.criar_rastreador("Dicas  para afiliados", "tiktok")
    assert db.criar_rastreador("dicas para afiliados", "tiktok") is None
    assert db.criar_rastreador("dicas para afiliados", "youtube")


# --- Scraper de busca ------------------------------------------------------
def test_normalizar_e_ordenar_videos(monkeypatch):
    itens = [
        {"webVideoUrl": "https://t.com/1", "text": "a", "playCount": 100, "diggCount": 1, "commentCount": 0},
        {"url": "https://y.com/2", "title": "b", "viewCount": "1.2K", "likes": 50, "commentsCount": 30},
        {"webVideoUrl": "https://t.com/1", "text": "duplicado"},
        {"text": "sem url"},
    ]
    monkeypatch.setattr(scraper, "executar_ator", lambda ator, entrada, limite: itens)
    videos = scraper.buscar_videos("teste", "youtube", quantidade=5)
    assert [v["url"] for v in videos] == ["https://y.com/2", "https://t.com/1"]
    assert videos[0]["views"] == 1200


def test_hashtag_do_instagram():
    assert scraper.hashtag_de("Limpeza porcelanato manchado!") == "limpezaporcelanatomanchado"
    assert scraper._input_busca("instagram", "Ação rápida", 10)["hashtags"] == ["acaorapida"]


# --- Migração de banco antigo ------------------------------------------------
def test_migra_banco_v1_para_v2(tmp_path, monkeypatch):
    antigo = tmp_path / "antigo.db"
    conn = sqlite3.connect(antigo)
    conn.executescript(db.SCHEMA_V1)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO assuntos_quentes (tema) VALUES ('tema antigo')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_PATH", antigo)
    db.init_db()
    assunto = db.listar_assuntos_quentes()[0]
    assert assunto["tema"] == "tema antigo" and assunto["tipo"] == "tendencia"
    with db.get_connection() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


# --- Agendador real (APScheduler) ------------------------------------------
def test_agendador_executa_em_segundo_plano(monkeypatch):
    import threading

    feito = threading.Event()
    recebidos = []

    def executar_falso(rastreador_id, gatilho="agendado", **_):
        recebidos.append((rastreador_id, gatilho))
        feito.set()

    monkeypatch.setattr(rastreador, "executar_rastreador", executar_falso)
    agendador = rastreador.iniciar_agendador()
    try:
        assert agendador.get_job("verificar_pendentes") is not None
        rastreador.executar_em_segundo_plano(agendador, 42)
        assert feito.wait(timeout=10)
        assert recebidos == [(42, "manual")]
    finally:
        agendador.shutdown(wait=True)
