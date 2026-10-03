"""Dashboard (Módulo 0): indicadores, detecção de alta performance e "Reciclar este tema"."""

from __future__ import annotations

from statistics import median

import database as db

MIN_POSTS_PARA_MEDIANA = 3   # comparação com a média da persona só vale com histórico mínimo
MULTIPLICADOR_MEDIANA = 2.0  # "alto" = 2x a mediana de views da persona


def limiares() -> tuple[int, int]:
    return (int(db.get_config("metricas_limiar_views", "10000")),
            int(db.get_config("metricas_limiar_saves", "500")))


def calcular_kpis(linhas: list[dict]) -> dict:
    com_metricas = [l for l in linhas if l["views"] is not None]
    views = sum(l["views"] for l in com_metricas)
    saves = sum(l["saves"] for l in com_metricas)
    shares = sum(l["shares"] for l in com_metricas)
    return {
        "posts": len(linhas),
        "posts_com_metricas": len(com_metricas),
        "views_total": views,
        "views_media": round(views / len(com_metricas)) if com_metricas else 0,
        "taxa_salvamento": saves / views if views else None,
        "taxa_compartilhamento": shares / views if views else None,
    }


def identificar_alto_desempenho(linhas: list[dict], limiar_views: int | None = None,
                                limiar_saves: int | None = None) -> list[dict]:
    """Posts com métricas acima dos limiares ou bem acima do normal da própria persona."""
    if limiar_views is None or limiar_saves is None:
        limiar_views, limiar_saves = limiares()
    com_metricas = [l for l in linhas if l["views"] is not None]
    medianas: dict = {}
    for persona_id in {l["persona_id"] for l in com_metricas}:
        views = [l["views"] for l in com_metricas if l["persona_id"] == persona_id]
        if len(views) >= MIN_POSTS_PARA_MEDIANA:
            medianas[persona_id] = median(views)

    destaques = []
    for l in com_metricas:
        motivos = []
        if l["views"] >= limiar_views:
            motivos.append(f"{l['views']:,} views (meta: {limiar_views:,})".replace(",", "."))
        if l["saves"] >= limiar_saves:
            motivos.append(f"{l['saves']:,} salvamentos (meta: {limiar_saves:,})".replace(",", "."))
        mediana = medianas.get(l["persona_id"])
        if mediana and l["views"] >= MULTIPLICADOR_MEDIANA * mediana:
            motivos.append(f"{l['views'] / mediana:.1f}x a mediana de views da persona".replace(".", ","))
        if motivos:
            destaques.append({**l, "motivos": motivos})
    return sorted(destaques, key=lambda l: l["views"], reverse=True)


def enviar_para_reciclagem(conteudo_id: int) -> dict:
    """Cria um Assunto Quente de reciclagem e devolve o pré-preenchimento da Máquina de Conteúdo."""
    c = db.obter_conteudo(conteudo_id)
    if not c:
        raise ValueError("Conteúdo não encontrado.")
    tema = c["extras"].get("tema") or c["titulo"]
    metricas = db.listar_metricas(conteudo_id)
    m = metricas[-1] if metricas else None
    descricao = f"Alta performance no post #{conteudo_id} “{c['titulo']}” ({c['formato'] or 'formato livre'})"
    if m:
        descricao += (f": {m['views']} views, {m['saves']} salvamentos e {m['shares']} compartilhamentos "
                      f"em {m['marco_dias']} dias. Explore o tema com um novo ângulo ou formato.")
    assunto_id = db.criar_assunto_quente(tema, descricao, 90, c["persona_id"], origem="reciclagem",
                                         conteudo_origem_id=conteudo_id, tipo="reciclagem")
    if assunto_id is None:  # o tema já estava ativo na lista
        existente = db.assunto_de_reciclagem(conteudo_id)
        assunto_id = existente["id"] if existente else None
    db.registrar_historico(conteudo_id, "reciclado", "Tema enviado para a Máquina de Conteúdo pelo Dashboard")
    plataforma = c["plataforma"] if c["plataforma"] in ("tiktok", "instagram", "youtube") else "tiktok"
    return {"tema": tema, "plataforma": plataforma, "persona_id": c["persona_id"], "validacao_id": None,
            "assunto_id": assunto_id}
