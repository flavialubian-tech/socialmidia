"""Cofre de Ideias (Módulo 3): edição dos cards, Dossiê e reciclagem de conteúdos."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

import database as db
from services import maquina

CAMPOS_EDITAVEIS = ("titulo", "gancho", "roteiro", "legenda", "hashtags", "formato", "funil", "plataforma",
                    "persona_id", "url_publicacao", "data_postagem")


def salvar_edicao(conteudo_id: int, **novos) -> list[str]:
    """Salva só o que mudou e registra no Dossiê quais campos foram editados."""
    atual = db.obter_conteudo(conteudo_id)
    if not atual:
        raise ValueError("Conteúdo não encontrado.")
    if "hashtags" in novos and isinstance(novos["hashtags"], str):
        novos["hashtags"] = maquina.normalizar_hashtags(novos["hashtags"])
    mudancas = {k: v for k, v in novos.items() if k in CAMPOS_EDITAVEIS and atual.get(k) != v}
    if not mudancas:
        return []
    db.atualizar_conteudo(conteudo_id, **mudancas)
    db.registrar_historico(conteudo_id, "editado", "Campos alterados: " + ", ".join(sorted(mudancas)))
    return sorted(mudancas)


def _resumo_original(original: dict) -> str:
    linhas = [f"Título: {original['titulo']}", f"Formato original: {original['formato'] or '-'}",
              f"Gancho original: {original['gancho'] or '-'}"]
    linhas += [f"- [{b.get('tempo', '')}] {b.get('audio', '')} (tela: {b.get('tela', '')})"
               for b in original["roteiro"][:15]]
    if original["legenda"]:
        linhas.append(f"Legenda original: {original['legenda'][:600]}")
    metricas = db.listar_metricas(original["id"])
    if metricas:
        m = metricas[-1]
        linhas.append(f"Desempenho ({m['marco_dias']} dias): {m['views']} views, {m['saves']} salvamentos, "
                      f"{m['shares']} compartilhamentos, {m['comments']} comentários.")
    return "\n".join(linhas)


def reciclar_conteudo(conteudo_id: int, novo_formato: str, funil: str | None = None, instrucoes: str = "",
                      llm: BaseChatModel | None = None) -> dict:
    """Gera uma nova versão de um post antigo em outro formato (ainda não salva)."""
    original = db.obter_conteudo(conteudo_id)
    if not original:
        raise ValueError("Conteúdo não encontrado.")
    funil = funil or original["funil"] or "topo"
    tema = original["extras"].get("tema") or original["titulo"]
    validacao = db.obter_validacao(original["validacao_id"]) if original["validacao_id"] else None
    pedido = (
        "RECICLAGEM: este conteúdo já foi publicado. Mantenha a ideia central e o que funcionou, mas crie um "
        f"conteúdo NOVO no formato '{novo_formato}', com gancho diferente e estrutura adaptada ao formato. "
        "Não copie frases do original.\n\nCONTEÚDO ORIGINAL:\n" + _resumo_original(original)
    )
    if instrucoes.strip():
        pedido += f"\n\nPedido da criadora para esta versão: {instrucoes.strip()}"
    novo = maquina.gerar_roteiro(tema, funil, novo_formato, original["plataforma"] or "tiktok",
                                 original["persona_id"], validacao, pedido, llm=llm)
    novo.update({"formato": novo_formato, "funil": funil, "tema": tema})
    return novo


def salvar_reciclagem(conteudo_id: int, novo: dict) -> int:
    """Grava a versão reciclada como um novo card em 'Roteiros Prontos', ligada ao original."""
    original = db.obter_conteudo(conteudo_id)
    extras = {
        "tema": novo["tema"],
        "ganchos_alternativos": novo.get("ganchos_alternativos", []),
        "cta": novo.get("cta", ""),
        "palavras_chave_seo": novo.get("palavras_chave_seo", []),
        "duracao_estimada": novo.get("duracao_estimada", ""),
        "reciclado_de": conteudo_id,
    }
    novo_id = db.criar_conteudo(
        novo["titulo"] or original["titulo"], persona_id=original["persona_id"], assunto_id=original["assunto_id"],
        validacao_id=original["validacao_id"], funil=novo["funil"], formato=novo["formato"],
        plataforma=original["plataforma"], gancho=novo["gancho"], roteiro=novo["roteiro"],
        legenda=novo["legenda"], hashtags=novo["hashtags"], referencias=original["referencias"],
        extras=extras, conteudo_pai_id=conteudo_id,
    )
    db.registrar_historico(novo_id, "reciclado", f"Nova versão do conteúdo #{conteudo_id} ({original['formato']} → {novo['formato']})")
    db.registrar_historico(conteudo_id, "reciclado", f"Gerou a versão #{novo_id} em {novo['formato']}")
    return novo_id
