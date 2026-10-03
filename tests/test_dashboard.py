from datetime import date, timedelta

import pytest

import database as db
from services import dashboard, graficos


def post(titulo, pid=None, dias_atras=20, formato="Vídeo POV", **metricas):
    cid = db.criar_conteudo(titulo, persona_id=pid, formato=formato, plataforma="tiktok", extras={"tema": titulo})
    db.mover_conteudo(cid, "postado", (date.today() - timedelta(days=dias_atras)).isoformat())
    if metricas:
        db.salvar_metricas(cid, metricas.pop("marco", 7), **metricas)
    return cid


def test_salvar_metricas_upsert_e_historico():
    cid = post("A")
    db.salvar_metricas(cid, 7, views=100, saves=5)
    db.salvar_metricas(cid, 7, views=150, saves=-3)
    m = db.listar_metricas(cid)
    assert len(m) == 1 and m[0]["views"] == 150 and m[0]["saves"] == 0
    assert db.listar_historico(cid)[-1]["evento"] == "metricas"
    with pytest.raises(ValueError):
        db.salvar_metricas(cid, 30, views=1)


def test_alertas_somem_apos_registrar():
    cid = post("B", dias_atras=15)
    assert {a["marco_dias"] for a in db.listar_alertas_metricas() if a["conteudo_id"] == cid} == {7, 14}
    db.salvar_metricas(cid, 7, views=10)
    db.salvar_metricas(cid, 14, views=20)
    assert not [a for a in db.listar_alertas_metricas() if a["conteudo_id"] == cid]


def test_dados_performance_usa_metrica_mais_recente_e_filtros():
    pid = db.criar_persona("P")
    cid = post("C", pid, dias_atras=20, views=100)
    db.salvar_metricas(cid, 14, views=300, saves=30)
    post("Antigo", pid, dias_atras=400, views=999)
    post("Sem métrica", dias_atras=2)
    linhas = db.dados_performance(desde=(date.today() - timedelta(days=90)).isoformat())
    por_titulo = {l["titulo"]: l for l in linhas}
    assert set(por_titulo) == {"C", "Sem métrica"}
    assert por_titulo["C"]["views"] == 300 and por_titulo["C"]["marco_dias"] == 14
    assert por_titulo["Sem métrica"]["views"] is None
    assert [l["titulo"] for l in db.dados_performance(persona_id=pid)] == ["Antigo", "C"]


def test_kpis():
    post("A", views=1000, saves=50, shares=10)
    post("B", views=3000, saves=150, shares=30)
    post("C")
    k = dashboard.calcular_kpis(db.dados_performance())
    assert k["posts"] == 3 and k["posts_com_metricas"] == 2
    assert k["views_total"] == 4000 and k["views_media"] == 2000
    assert k["taxa_salvamento"] == pytest.approx(0.05) and k["taxa_compartilhamento"] == pytest.approx(0.01)
    assert dashboard.calcular_kpis([])["taxa_salvamento"] is None


def test_alto_desempenho_por_meta_e_por_mediana():
    pid = db.criar_persona("P")
    for i, v in enumerate([1000, 1100, 900, 5000]):
        post(f"Post {i}", pid, views=v, saves=10)
    post("Muitos saves", views=100, saves=800)
    destaques = dashboard.identificar_alto_desempenho(db.dados_performance(), limiar_views=10_000, limiar_saves=500)
    titulos = [d["titulo"] for d in destaques]
    assert titulos == ["Post 3", "Muitos saves"]
    assert "mediana" in destaques[0]["motivos"][0]
    assert "salvamentos" in destaques[1]["motivos"][0]


def test_enviar_para_reciclagem_cria_assunto_e_prefill():
    pid = db.criar_persona("P", "instagram")
    cid = post("Tema campeão", pid, views=50_000, saves=900, shares=300)
    pendente = dashboard.enviar_para_reciclagem(cid)
    assunto = db.obter_assunto(pendente["assunto_id"])
    assert assunto["origem"] == "reciclagem" and assunto["tipo"] == "reciclagem"
    assert assunto["conteudo_origem_id"] == cid and "50000 views" in assunto["descricao"]
    assert pendente["tema"] == "Tema campeão" and pendente["persona_id"] == pid
    assert db.assunto_de_reciclagem(cid)["id"] == assunto["id"]
    # Clicar de novo não duplica o assunto
    assert dashboard.enviar_para_reciclagem(cid)["assunto_id"] == assunto["id"]
    assert len(db.listar_assuntos_quentes(pid)) == 1


@pytest.mark.parametrize("tema", ["light", "dark"])
def test_graficos_geram_figuras(tema):
    post("A", views=1000, saves=50, formato="Vídeo POV")
    post("B", views=500, saves=100, formato="Carrossel Checklist")
    linhas = db.dados_performance()
    top = graficos.barras_top_views(linhas, tema)
    assert list(top.data[0].x) == [500, 1000]  # menor para maior: o maior fica no topo
    assert top.data[0].marker.color == graficos.TEMAS[tema]["serie"]
    formato = graficos.barras_salvamento_por_formato(linhas, tema)
    assert list(formato.data[0].x) == pytest.approx([5.0, 20.0])
    linha = graficos.linha_views_no_tempo(linhas, tema)
    assert len(linha.data[0].x) == 2 and not linha.layout.showlegend
