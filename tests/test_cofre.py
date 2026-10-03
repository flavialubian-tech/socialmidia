import json
from datetime import date

from langchain_core.language_models.fake_chat_models import FakeListChatModel

import database as db
from services import cofre, maquina
from tests.test_maquina import RESPOSTA_ROTEIRO


def llm(*respostas):
    return FakeListChatModel(responses=[json.dumps(r) for r in respostas])


def criar_post(pid=None, **extras):
    cid = db.criar_conteudo("Post original", persona_id=pid, funil="topo", formato="Vídeo POV", plataforma="tiktok",
                            gancho="Gancho velho", roteiro=[{"tempo": "0-3s", "audio": "Oi", "tela": "close"}],
                            legenda="Legenda", hashtags=["#a"], extras={"tema": "Mancha"}, **extras)
    return cid


def test_listar_conteudos_com_filtros():
    pid = db.criar_persona("A")
    criar_post(pid)
    db.criar_ideia("Ideia solta", plataforma="instagram", notas="vi no radar")
    assert len(db.listar_conteudos()) == 2
    assert [c["titulo"] for c in db.listar_conteudos(persona_id=pid)] == ["Post original"]
    assert [c["titulo"] for c in db.listar_conteudos(plataforma="instagram")] == ["Ideia solta"]
    assert [c["titulo"] for c in db.listar_conteudos(busca="velho")] == ["Post original"]
    ideia = db.listar_conteudos(status="ideia")[0]
    assert ideia["extras"]["notas"] == "vi no radar" and ideia["total_metricas"] == 0


def test_mover_para_postado_grava_data_e_historico():
    cid = criar_post()
    db.mover_conteudo(cid, "em_edicao")
    db.mover_conteudo(cid, "postado", "2026-09-20", " https://tiktok.com/x ")
    c = db.obter_conteudo(cid)
    assert c["data_postagem"] == "2026-09-20" and c["url_publicacao"] == "https://tiktok.com/x"
    eventos = [e["detalhes"] for e in db.listar_historico(cid) if e["evento"] == "status_alterado"]
    assert eventos == ["roteiro_pronto -> em_edicao", "em_edicao -> postado"]
    assert db.listar_alertas_metricas(date(2026, 10, 3))[0]["conteudo_id"] == cid
    db.mover_conteudo(cid, "postado")  # sem mudança de coluna: nada novo no histórico
    assert len([e for e in db.listar_historico(cid) if e["evento"] == "status_alterado"]) == 2


def test_mover_status_invalido():
    import pytest

    with pytest.raises(ValueError):
        db.mover_conteudo(criar_post(), "arquivado")


def test_salvar_edicao_registra_so_o_que_mudou():
    cid = criar_post()
    assert cofre.salvar_edicao(cid, titulo="Post original", gancho="Gancho novo", hashtags="#limpeza, faxina") == ["gancho", "hashtags"]
    c = db.obter_conteudo(cid)
    assert c["gancho"] == "Gancho novo" and c["hashtags"] == ["#limpeza", "#faxina"]
    assert cofre.salvar_edicao(cid, gancho="Gancho novo") == []
    assert db.listar_historico(cid)[-1]["detalhes"] == "Campos alterados: gancho, hashtags"


def test_reciclar_e_salvar():
    pid = db.criar_persona("P")
    cid = criar_post(pid)
    db.mover_conteudo(cid, "postado", "2026-09-01")
    with db.get_connection() as conn:
        conn.execute("INSERT INTO metricas (conteudo_id, marco_dias, views, saves) VALUES (?, 7, 50000, 900)", (cid,))
    modelo = llm(RESPOSTA_ROTEIRO)
    novo = cofre.reciclar_conteudo(cid, "Carrossel Checklist", instrucoes="mais curto", llm=modelo)
    assert novo["formato"] == "Carrossel Checklist" and novo["funil"] == "topo" and novo["tema"] == "Mancha"

    novo_id = cofre.salvar_reciclagem(cid, novo)
    reciclado = db.obter_conteudo(novo_id)
    assert reciclado["conteudo_pai_id"] == cid and reciclado["status"] == "roteiro_pronto"
    assert reciclado["persona_id"] == pid and reciclado["extras"]["reciclado_de"] == cid
    assert db.listar_reciclagens(cid)[0]["id"] == novo_id
    assert db.listar_conteudos(status="postado")[0]["total_reciclagens"] == 1
    assert db.listar_historico(cid)[-1]["evento"] == "reciclado"


def test_reciclagem_envia_original_e_metricas_para_ia(monkeypatch):
    cid = criar_post()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO metricas (conteudo_id, marco_dias, views) VALUES (?, 14, 12345)", (cid,))
    capturado = {}

    def gerar_falso(tema, funil, formato, plataforma, persona_id, validacao, instrucoes, llm=None):
        capturado.update(tema=tema, instrucoes=instrucoes)
        return maquina.normalizar_roteiro(RESPOSTA_ROTEIRO, formato) | {"palavras_proibidas_usadas": []}

    monkeypatch.setattr(maquina, "gerar_roteiro", gerar_falso)
    cofre.reciclar_conteudo(cid, "Antes e depois")
    assert "Gancho velho" in capturado["instrucoes"] and "12345 views" in capturado["instrucoes"]
    assert capturado["tema"] == "Mancha"


def test_ideia_roteirizada_atualiza_o_mesmo_card():
    ideia = db.criar_ideia("Ideia X", notas="nota")
    conteudo = maquina.normalizar_roteiro(RESPOSTA_ROTEIRO, "Vídeo POV")
    retorno = maquina.salvar_no_cofre(conteudo, "Ideia X", "meio", "Vídeo POV", "tiktok", conteudo_id=ideia)
    assert retorno == ideia
    c = db.obter_conteudo(ideia)
    assert c["status"] == "roteiro_pronto" and c["gancho"] == RESPOSTA_ROTEIRO["gancho"]
    assert c["extras"]["notas"] == "nota"  # mantém as notas da ideia
    assert len(db.listar_conteudos()) == 1
    assert {e["evento"] for e in db.listar_historico(ideia)} >= {"criado", "roteirizado", "status_alterado"}


def test_excluir_conteudo_apaga_historico():
    cid = criar_post()
    db.excluir_conteudo(cid)
    assert db.obter_conteudo(cid) is None and db.listar_historico(cid) == []
