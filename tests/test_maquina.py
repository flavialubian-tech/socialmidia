import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import database as db
from services import maquina, scraper

VIDEOS = [
    {"url": "https://t.com/1", "titulo": "Como tirar mancha", "views": 100_000, "curtidas": 5_000,
     "comentarios": 300, "compartilhamentos": 200},
    {"url": "https://t.com/2", "titulo": "Produto X", "views": 10_000, "curtidas": 300,
     "comentarios": 0, "compartilhamentos": 10},
]
RESPOSTA_VALIDACAO = {
    "score_ia": 70, "veredito": "Vale a pena", "saturacao": "Média",
    "o_que_funciona": ["antes e depois"], "lacuna": "Ninguém explica qual produto não usar.",
    "oportunidades": ["mostrar erro comum"],
    "concorrentes": [{"indice": 0, "resumo": "tutorial", "ponto_fraco": "não mostra o resultado"}],
}
RESPOSTA_ROTEIRO = {
    "titulo": "Mancha no porcelanato",
    "gancho": "Pare de usar isso no seu porcelanato!",
    "ganchos_alternativos": ["Seu porcelanato manchou?"],
    "roteiro": [{"tempo": "0-3s", "audio": "Pare!", "tela": "close na mancha"},
                {"tempo": "3-8s", "audio": "O erro é...", "tela": "B-roll"}, {"tempo": "x"}],
    "legenda": "Salva esse vídeo!", "cta": "Salve", "hashtags": ["#porcelanato", "limpeza pesada", "#Porcelanato"],
    "palavras_chave_seo": ["mancha porcelanato"], "duracao_estimada": "30s",
}


def llm(*respostas):
    return FakeListChatModel(responses=[json.dumps(r) if isinstance(r, dict) else r for r in respostas])


def test_calcular_metricas_e_score():
    metricas = maquina.calcular_metricas(VIDEOS)
    assert metricas["views_mediana"] == 55_000 and metricas["total_videos"] == 2
    score = maquina.score_por_dados(metricas)
    assert 40 <= score <= 70
    assert maquina.score_por_dados({"total_videos": 0}) is None
    assert maquina.score_por_dados(maquina.calcular_metricas(
        [{"url": "u", "titulo": "", "views": 0, "curtidas": 1000, "comentarios": 5, "compartilhamentos": 0}])) > 0


def test_validar_tema_completo():
    pid = db.criar_persona("Limpeza", "tiktok")
    aid = db.criar_assunto_quente("Mancha no porcelanato", persona_id=pid)
    coletas = []

    def coletar(urls, plataforma, limite):
        coletas.append(urls)
        return [{"texto": "qual produto não usar?", "curtidas": 9}]

    validacao = maquina.validar_tema("Mancha no porcelanato", "tiktok", pid, aid, llm=llm(RESPOSTA_VALIDACAO),
                                     buscar=lambda *a: VIDEOS, coletar=coletar)
    assert coletas == [["https://t.com/1"]]  # só vídeos com comentários
    assert validacao["score_ia"] == 70
    assert validacao["score_viralizacao"] == round(0.5 * validacao["score_dados"] + 35)
    assert validacao["lacuna"].startswith("Ninguém")
    assert validacao["analise"]["saturacao"] == "media"
    assert validacao["concorrentes"][0]["ponto_fraco"] == "não mostra o resultado"
    assert validacao["concorrentes"][1]["ponto_fraco"] == ""
    assert db.validacao_recente("mancha no porcelanato", "tiktok")["id"] == validacao["id"]
    assert db.validacao_recente("mancha no porcelanato", "youtube") is None


def test_validar_tema_sem_videos_usa_so_ia():
    validacao = maquina.validar_tema("tema raro", "youtube", llm=llm(RESPOSTA_VALIDACAO),
                                     buscar=lambda *a: [], coletar=lambda *a: pytest.fail("não deveria coletar"))
    assert validacao["score_dados"] is None and validacao["score_viralizacao"] == 70


def test_validar_tema_segue_se_coleta_de_comentarios_falhar():
    def falha(*_):
        raise scraper.ColetaError("erro")

    validacao = maquina.validar_tema("x", "tiktok", llm=llm(RESPOSTA_VALIDACAO), buscar=lambda *a: VIDEOS,
                                     coletar=falha)
    assert validacao["analise"]["comentarios_lidos"] == 0


def test_sugerir_formatos():
    resposta = {"formatos": [{"formato": "Antes e depois", "por_que": "visual", "exemplo_gancho": "Olha isso"},
                             {"formato": ""}, {"formato": "Vídeo POV"}, {"formato": "A"}, {"formato": "B"}]}
    sugestoes = maquina.sugerir_formatos("tema", "topo", "tiktok", llm=llm(resposta))
    assert [s["formato"] for s in sugestoes] == ["Antes e depois", "Vídeo POV", "A"]


def test_gerar_roteiro_normaliza():
    conteudo = maquina.gerar_roteiro("Mancha", "meio", "Tutorial passo a passo", "tiktok", llm=llm(RESPOSTA_ROTEIRO))
    assert len(conteudo["roteiro"]) == 2
    assert conteudo["hashtags"] == ["#porcelanato", "#limpeza", "#pesada"]
    assert conteudo["palavras_proibidas_usadas"] == []


def test_gerar_roteiro_refaz_com_palavra_proibida():
    pid = db.criar_persona("P", palavras_proibidas=["barato"])
    ruim = {**RESPOSTA_ROTEIRO, "legenda": "Produto barato que resolve"}
    conteudo = maquina.gerar_roteiro("x", "fundo", "Vídeo POV", "tiktok", pid, llm=llm(ruim, RESPOSTA_ROTEIRO))
    assert conteudo["palavras_proibidas_usadas"] == []
    assert conteudo["legenda"] == "Salva esse vídeo!"
    # Se insistir, avisa em vez de esconder
    conteudo = maquina.gerar_roteiro("x", "fundo", "Vídeo POV", "tiktok", pid, llm=llm(ruim, ruim))
    assert conteudo["palavras_proibidas_usadas"] == ["barato"]


def test_proibida_respeita_palavra_inteira():
    assert maquina.palavras_proibidas_encontradas("baratinho e barata", ["barato"]) == []
    assert maquina.palavras_proibidas_encontradas("muito Barato!", ["barato"]) == ["barato"]


def test_carrossel_e_salvar_no_cofre():
    assert maquina.eh_carrossel("Carrossel Checklist") and not maquina.eh_carrossel("Vídeo POV")
    pid = db.criar_persona("P")
    aid = db.criar_assunto_quente("Tema", persona_id=pid)
    validacao = maquina.validar_tema("Tema", "tiktok", pid, aid, llm=llm(RESPOSTA_VALIDACAO),
                                     buscar=lambda *a: VIDEOS, coletar=lambda *a: [])
    conteudo = maquina.gerar_roteiro("Tema", "meio", "Carrossel Checklist", "tiktok", pid, validacao,
                                     llm=llm(RESPOSTA_ROTEIRO))
    cid = maquina.salvar_no_cofre(conteudo, "Tema", "meio", "Carrossel Checklist", "tiktok", pid, aid, validacao)

    salvo = db.obter_conteudo(cid)
    assert salvo["status"] == "roteiro_pronto" and salvo["validacao_id"] == validacao["id"]
    assert salvo["roteiro"][0]["audio"] == "Pare!"
    assert salvo["extras"]["lacuna"].startswith("Ninguém")
    assert salvo["referencias"] == ["https://t.com/1", "https://t.com/2"]
    assert db.obter_assunto(aid)["status"] == "em_uso"
    with db.get_connection() as c:
        assert c.execute("SELECT evento FROM historico_conteudo WHERE conteudo_id = ?", (cid,)).fetchone()[0] == "criado"
