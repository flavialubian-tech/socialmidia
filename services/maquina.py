"""Máquina de Conteúdo (Módulo 2): Termômetro de Validação, Funil/Formato e geração do roteiro."""

from __future__ import annotations

import math
import re
from statistics import median
from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

import database as db
from services import scraper
from services.llm import gerar_json

FUNIS = {
    "topo": "🧲 Topo · Atração",
    "meio": "📚 Meio · Educação",
    "fundo": "💰 Fundo · Conversão",
}
OBJETIVO_FUNIL = {
    "topo": "atrair pessoas novas: alcance, identificação e compartilhamento. CTA leve (seguir, compartilhar, comentar).",
    "meio": "educar e gerar autoridade: conteúdo salvável, prático e com prova. CTA: salvar, comentar dúvida, seguir para mais.",
    "fundo": "converter: quebrar objeções, mostrar resultado/oferta, gerar desejo. CTA direto: link na bio, chamar no direct, comentar palavra-chave.",
}
FORMATOS = [
    "Vídeo POV",
    "Voiceover com B-roll",
    "Talking head (falando para a câmera)",
    "Tutorial passo a passo",
    "Antes e depois",
    "Storytelling (história pessoal)",
    "Trend com áudio em alta",
    "Mitos x Verdades (vídeo)",
    "Lista / Top N (vídeo)",
    "Carrossel Checklist",
    "Carrossel Passo a passo",
    "Carrossel Mitos x Verdades",
    "Carrossel Erros comuns",
]

SISTEMA = (
    "Você é uma estrategista sênior de conteúdo e roteirista de vídeos curtos virais para Instagram, "
    "TikTok e YouTube Shorts no Brasil. Você domina ganchos, retenção, funil de conteúdo e SEO social. "
    "Responda sempre em português do Brasil e apenas com JSON válido."
)


def eh_carrossel(formato: str | None) -> bool:
    return "carrossel" in (formato or "").lower()


def _contexto_persona(persona: dict | None) -> str:
    if not persona:
        return "PERSONA: não definida — use um tom próximo e didático."
    proibidas = ", ".join(persona.get("palavras_proibidas") or []) or "nenhuma"
    return (
        f"PERSONA: {persona['nome']} ({persona['plataforma']})\n"
        f"- Público-alvo: {persona.get('publico_alvo') or '-'}\n"
        f"- Tom de voz: {persona.get('tom_de_voz') or '-'}\n"
        f"- Palavras PROIBIDAS (nunca use): {proibidas}\n"
        f"- Notas: {persona.get('descricao') or '-'}"
    )


def _int(valor, padrao: int = 0, minimo: int = 0, maximo: int = 100) -> int:
    try:
        return max(minimo, min(maximo, int(float(valor))))
    except (TypeError, ValueError):
        return padrao


def _lista_textos(valor) -> list[str]:
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list):
        return []
    return [str(v).strip() for v in valor if str(v).strip()]


def palavras_proibidas_encontradas(texto: str, proibidas: list[str]) -> list[str]:
    texto = texto.lower()
    return [p for p in proibidas if p.strip() and re.search(rf"\b{re.escape(p.strip().lower())}\b", texto)]


# ---------------------------------------------------------------------------
# Termômetro de Validação
# ---------------------------------------------------------------------------
def calcular_metricas(videos: list[dict]) -> dict:
    if not videos:
        return {"total_videos": 0}
    views = [v["views"] for v in videos if v.get("views")]
    engajamentos = [
        (v["curtidas"] + v["comentarios"] + v["compartilhamentos"]) / v["views"]
        for v in videos if v.get("views")
    ]
    return {
        "total_videos": len(videos),
        "views_mediana": int(median(views)) if views else 0,
        "views_max": max(views) if views else 0,
        "curtidas_mediana": int(median([v["curtidas"] for v in videos])),
        "comentarios_mediana": int(median([v["comentarios"] for v in videos])),
        "engajamento_mediano": round(median(engajamentos), 4) if engajamentos else None,
    }


def score_por_dados(metricas: dict) -> int | None:
    """Nota 0-100 baseada só em números reais dos concorrentes.

    Demanda (60%): mediana de views em escala logarítmica (1 mil = 20, 10 mil = 40, 100 mil = 60, 1 mi = 80).
    Engajamento (40%): (curtidas + comentários + compartilhamentos) / views; 10% ou mais = nota máxima.
    Sem views (ex.: posts de foto do Instagram), usa curtidas como sinal de demanda.
    """
    if not metricas.get("total_videos"):
        return None
    if metricas.get("views_mediana"):
        demanda = 20 * math.log10(metricas["views_mediana"] + 1) - 40
    else:
        demanda = 20 * math.log10(metricas.get("curtidas_mediana", 0) * 30 + 1) - 40
    demanda = max(0.0, min(100.0, demanda))
    engajamento = metricas.get("engajamento_mediano")
    if engajamento is None:
        return round(demanda)
    nota_engajamento = max(0.0, min(100.0, engajamento * 1000))
    return round(0.6 * demanda + 0.4 * nota_engajamento)


PROMPT_VALIDACAO = """Avalie o potencial de viralização do tema abaixo para {plataforma}.

TEMA: {tema}
{contexto_persona}

MÉTRICAS DOS CONCORRENTES (busca real na {plataforma}): {metricas}

VÍDEOS CONCORRENTES MAIS QUENTES (índice | views | curtidas | comentários | legenda):
{concorrentes}

COMENTÁRIOS DO PÚBLICO NOS MAIORES CONCORRENTES (o que as pessoas ainda perguntam/reclamam):
{comentarios}

Gere um JSON exatamente com esta estrutura:
{{
  "score_ia": 0-100,
  "veredito": "frase curta: vale a pena ou não, e por quê",
  "saturacao": "baixa|media|alta",
  "o_que_funciona": ["padrões dos vídeos que performaram bem"],
  "lacuna": "o que FALTOU nos vídeos concorrentes e que o público pede — a oportunidade principal, em 2-3 frases",
  "oportunidades": ["ângulos específicos para se diferenciar"],
  "concorrentes": [{{"indice": 0, "resumo": "o que o vídeo faz", "ponto_fraco": "o que deixou a desejar"}}]
}}

Critérios para o score_ia: demanda real do público, espaço para diferenciação (lacuna clara = nota maior),
saturação (muito batido sem ângulo novo = nota menor) e aderência à persona."""


def _formatar_concorrentes(videos: list[dict]) -> str:
    if not videos:
        return "(nenhum vídeo encontrado)"
    return "\n".join(
        f"{i} | {v['views']} | {v['curtidas']} | {v['comentarios']} | {' '.join(v['titulo'].split())[:200]}"
        for i, v in enumerate(videos)
    )


def validar_tema(
    tema: str,
    plataforma: str,
    persona_id: int | None = None,
    assunto_id: int | None = None,
    max_videos: int | None = None,
    ler_comentarios: bool = True,
    llm: BaseChatModel | None = None,
    buscar: Callable = scraper.buscar_videos,
    coletar: Callable = scraper.coletar_comentarios_apify,
    progresso: Callable[[str], None] = lambda _m: None,
) -> dict:
    """Busca concorrentes, calcula o Score de Viralização e aponta a Lacuna. Salva e retorna a validação."""
    max_videos = max_videos or int(db.get_config("termometro_max_videos", "10"))
    persona = db.obter_persona(persona_id) if persona_id else None

    progresso(f"Buscando os vídeos mais quentes sobre '{tema}' no {plataforma}...")
    videos = buscar(tema, plataforma, max_videos)
    metricas = calcular_metricas(videos)

    comentarios: list[dict] = []
    if ler_comentarios and videos:
        top = [v["url"] for v in videos if v["comentarios"] > 0][:3]
        if top:
            progresso("Lendo o que o público comentou nos 3 maiores concorrentes...")
            try:
                comentarios = coletar(top, plataforma, int(db.get_config("termometro_comentarios_concorrentes", "40")))
            except scraper.ColetaError:
                comentarios = []  # a validação segue só com as métricas

    progresso("A IA está avaliando o potencial e procurando a lacuna...")
    from services.radar import preparar_comentarios

    bruta = gerar_json(
        PROMPT_VALIDACAO.format(
            plataforma=plataforma, tema=tema, contexto_persona=_contexto_persona(persona),
            metricas=metricas, concorrentes=_formatar_concorrentes(videos),
            comentarios=preparar_comentarios(comentarios)[:8000] or "(não coletados)",
        ),
        SISTEMA, llm=llm,
    )

    score_ia = _int(bruta.get("score_ia"), 50)
    score_dados = score_por_dados(metricas)
    score = score_ia if score_dados is None else round(0.5 * score_dados + 0.5 * score_ia)

    analises_por_indice = {}
    for c in bruta.get("concorrentes") or []:
        if isinstance(c, dict):
            analises_por_indice[_int(c.get("indice"), -1, -1, 10_000)] = c
    concorrentes = [
        {**v, "resumo": str(analises_por_indice.get(i, {}).get("resumo", "")),
         "ponto_fraco": str(analises_por_indice.get(i, {}).get("ponto_fraco", ""))}
        for i, v in enumerate(videos)
    ]
    saturacao = str(bruta.get("saturacao", "media")).lower().replace("é", "e")
    analise = {
        "veredito": str(bruta.get("veredito", "")).strip(),
        "saturacao": saturacao if saturacao in ("baixa", "media", "alta") else "media",
        "o_que_funciona": _lista_textos(bruta.get("o_que_funciona")),
        "oportunidades": _lista_textos(bruta.get("oportunidades")),
        "comentarios_lidos": len(comentarios),
    }
    validacao_id = db.salvar_validacao(
        tema.strip(), score, score_dados, score_ia, concorrentes, str(bruta.get("lacuna", "")).strip(),
        metricas, analise, plataforma, persona_id, assunto_id,
    )
    return db.obter_validacao(validacao_id)


# ---------------------------------------------------------------------------
# Funil e formato
# ---------------------------------------------------------------------------
PROMPT_FORMATOS = """Sugira os 3 melhores formatos de conteúdo para este tema.

TEMA: {tema}
PLATAFORMA: {plataforma}
NÍVEL DO FUNIL: {funil} — objetivo: {objetivo}
{contexto_persona}
{contexto_validacao}

Escolha preferencialmente desta lista (pode adaptar o nome): {formatos}

JSON exatamente assim:
{{"formatos": [{{"formato": "nome", "por_que": "por que encaixa neste tema e funil", "exemplo_gancho": "um gancho de 3 segundos neste formato"}}]}}
Ordene do mais recomendado para o menos."""


def _contexto_validacao(validacao: dict | None) -> str:
    if not validacao:
        return "VALIDAÇÃO: não realizada."
    oportunidades = "; ".join(validacao["analise"].get("oportunidades", [])[:4])
    funciona = "; ".join(validacao["analise"].get("o_que_funciona", [])[:4])
    return (f"VALIDAÇÃO DO TEMA: score {validacao['score_viralizacao']}%\n"
            f"- LACUNA dos concorrentes (explore isso!): {validacao['lacuna'] or '-'}\n"
            f"- O que já funciona: {funciona or '-'}\n"
            f"- Oportunidades: {oportunidades or '-'}")


def sugerir_formatos(tema: str, funil: str, plataforma: str, persona_id: int | None = None,
                     validacao: dict | None = None, llm: BaseChatModel | None = None) -> list[dict]:
    persona = db.obter_persona(persona_id) if persona_id else None
    bruta = gerar_json(
        PROMPT_FORMATOS.format(tema=tema, plataforma=plataforma, funil=funil, objetivo=OBJETIVO_FUNIL[funil],
                               contexto_persona=_contexto_persona(persona),
                               contexto_validacao=_contexto_validacao(validacao), formatos=", ".join(FORMATOS)),
        SISTEMA, llm=llm,
    )
    sugestoes = []
    for f in bruta.get("formatos") or []:
        if isinstance(f, dict) and str(f.get("formato", "")).strip():
            sugestoes.append({"formato": str(f["formato"]).strip(), "por_que": str(f.get("por_que", "")).strip(),
                              "exemplo_gancho": str(f.get("exemplo_gancho", "")).strip()})
    return sugestoes[:3]


# ---------------------------------------------------------------------------
# Geração do roteiro
# ---------------------------------------------------------------------------
PROMPT_ROTEIRO = """Crie um conteúdo completo, pronto para gravar e postar.

TEMA: {tema}
PLATAFORMA: {plataforma}
FORMATO: {formato}
NÍVEL DO FUNIL: {funil} — objetivo: {objetivo}
{contexto_persona}
{contexto_validacao}
{contexto_audiencia}
INSTRUÇÕES EXTRAS DA CRIADORA: {instrucoes}

{regras_formato}

JSON exatamente assim:
{{
  "titulo": "título interno curto do conteúdo",
  "gancho": "o gancho dos 3 primeiros segundos (máx. 15 palavras), que para a rolagem",
  "ganchos_alternativos": ["outra opção de gancho", "mais uma opção"],
  "roteiro": [{{"tempo": "{exemplo_tempo}", "audio": "{exemplo_audio}", "tela": "{exemplo_tela}"}}],
  "legenda": "legenda pronta para colar, com quebras de linha, emojis com moderação e CTA no final",
  "cta": "a chamada para ação principal",
  "hashtags": ["#exemplo"],
  "palavras_chave_seo": ["termos que as pessoas digitam na busca"],
  "duracao_estimada": "{exemplo_duracao}"
}}

Regras gerais:
- Escreva no tom de voz da persona e use o vocabulário do público quando natural.
- Explore a LACUNA dos concorrentes: entregue o que eles não entregaram.
- NUNCA use as palavras proibidas da persona.
- SEO social: inclua as palavras-chave de busca naturalmente no gancho falado, no texto da tela e na 1ª linha da legenda.
- Hashtags: de 3 a 5, específicas do nicho (evite genéricas como #fyp ou #viral)."""

REGRAS_VIDEO = """REGRAS DO ROTEIRO (vídeo):
- Roteiro técnico em blocos com tempo (ex.: "0-3s"), "audio" (fala/narração exata) e "tela" (o que aparece: enquadramento, B-roll, texto na tela, transições).
- O primeiro bloco é o gancho (0-3s). Mantenha ritmo: troque de cena a cada 2-4 segundos.
- Duração ideal entre 20 e 60 segundos, salvo instrução contrária."""

REGRAS_CARROSSEL = """REGRAS DO ROTEIRO (carrossel):
- Cada item do "roteiro" é uma lâmina: "tempo" = "Lâmina 1", "Lâmina 2"...; "audio" = o TEXTO exato escrito na lâmina (curto, máx. 30 palavras); "tela" = orientação visual (fundo, destaque, ícone).
- Lâmina 1 = gancho forte; penúltima = resumo/virada; última = CTA.
- Entre 6 e 10 lâminas."""


def _contexto_audiencia(persona_id: int | None) -> str:
    ctx = db.contexto_audiencia(persona_id)
    if not ctx["dores"] and not ctx["dicionario"]:
        return ""
    termos = ", ".join(f"{t['termo']} ({t.get('significado', '')})" for t in ctx["dicionario"])
    return (f"O QUE O RADAR DE AUDIÊNCIA DESCOBRIU SOBRE ESSE PÚBLICO:\n"
            f"- Dores: {'; '.join(ctx['dores']) or '-'}\n"
            f"- Dicionário do público: {termos or '-'}")


def normalizar_hashtags(valor) -> list[str]:
    tags = []
    for item in _lista_textos(valor):
        for parte in re.split(r"[\s,]+", item):
            tag = "#" + re.sub(r"[^\w]", "", parte.lstrip("#"))
            if len(tag) > 2 and tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag)
    return tags[:10]


def normalizar_roteiro(bruto: dict, formato: str) -> dict:
    blocos = []
    for i, b in enumerate(bruto.get("roteiro") or []):
        if isinstance(b, dict) and (b.get("audio") or b.get("tela")):
            blocos.append({
                "tempo": str(b.get("tempo") or (f"Lâmina {i + 1}" if eh_carrossel(formato) else "")).strip(),
                "audio": str(b.get("audio", "")).strip(),
                "tela": str(b.get("tela", "")).strip(),
            })
    return {
        "titulo": str(bruto.get("titulo", "")).strip(),
        "gancho": str(bruto.get("gancho", "")).strip(),
        "ganchos_alternativos": _lista_textos(bruto.get("ganchos_alternativos"))[:3],
        "roteiro": blocos,
        "legenda": str(bruto.get("legenda", "")).strip(),
        "cta": str(bruto.get("cta", "")).strip(),
        "hashtags": normalizar_hashtags(bruto.get("hashtags")),
        "palavras_chave_seo": _lista_textos(bruto.get("palavras_chave_seo"))[:8],
        "duracao_estimada": str(bruto.get("duracao_estimada", "")).strip(),
    }


def texto_completo(conteudo: dict) -> str:
    partes = [conteudo.get("titulo", ""), conteudo.get("gancho", ""), conteudo.get("legenda", ""),
              conteudo.get("cta", ""), " ".join(conteudo.get("hashtags", []))]
    partes += [f"{b['audio']} {b['tela']}" for b in conteudo.get("roteiro", [])]
    return "\n".join(partes)


def gerar_roteiro(tema: str, funil: str, formato: str, plataforma: str, persona_id: int | None = None,
                  validacao: dict | None = None, instrucoes: str = "",
                  llm: BaseChatModel | None = None) -> dict:
    """Gera gancho, roteiro técnico, legenda e hashtags. Refaz uma vez se usar palavra proibida."""
    persona = db.obter_persona(persona_id) if persona_id else None
    proibidas = (persona or {}).get("palavras_proibidas") or []
    carrossel = eh_carrossel(formato)
    prompt = PROMPT_ROTEIRO.format(
        tema=tema, plataforma=plataforma, formato=formato, funil=funil, objetivo=OBJETIVO_FUNIL[funil],
        contexto_persona=_contexto_persona(persona), contexto_validacao=_contexto_validacao(validacao),
        contexto_audiencia=_contexto_audiencia(persona_id), instrucoes=instrucoes.strip() or "nenhuma",
        regras_formato=REGRAS_CARROSSEL if carrossel else REGRAS_VIDEO,
        exemplo_tempo="Lâmina 1" if carrossel else "0-3s",
        exemplo_audio="texto escrito na lâmina" if carrossel else "fala exata",
        exemplo_tela="orientação visual da lâmina" if carrossel else "o que aparece na tela / B-roll / texto na tela",
        exemplo_duracao="8 lâminas" if carrossel else "35s",
    )
    conteudo = normalizar_roteiro(gerar_json(prompt, SISTEMA, llm=llm), formato)
    encontradas = palavras_proibidas_encontradas(texto_completo(conteudo), proibidas)
    if encontradas:
        aviso = (f"\n\nATENÇÃO: a versão anterior usou palavras proibidas ({', '.join(encontradas)}). "
                 "Reescreva sem elas.")
        conteudo = normalizar_roteiro(gerar_json(prompt + aviso, SISTEMA, llm=llm), formato)
        encontradas = palavras_proibidas_encontradas(texto_completo(conteudo), proibidas)
    conteudo["palavras_proibidas_usadas"] = encontradas
    if not conteudo["titulo"]:
        conteudo["titulo"] = tema[:80]
    return conteudo


def salvar_no_cofre(conteudo: dict, tema: str, funil: str, formato: str, plataforma: str,
                    persona_id: int | None = None, assunto_id: int | None = None,
                    validacao: dict | None = None, conteudo_id: int | None = None) -> int:
    """Grava o conteúdo no Cofre de Ideias (coluna 'Roteiros Prontos').

    Com `conteudo_id` (ideia vinda do Cofre), atualiza o card existente em vez de criar outro.
    """
    referencias = [c["url"] for c in (validacao or {}).get("concorrentes", [])[:5]]
    extras = {
        "tema": tema,
        "ganchos_alternativos": conteudo.get("ganchos_alternativos", []),
        "cta": conteudo.get("cta", ""),
        "palavras_chave_seo": conteudo.get("palavras_chave_seo", []),
        "duracao_estimada": conteudo.get("duracao_estimada", ""),
        "lacuna": (validacao or {}).get("lacuna", ""),
        "score_viralizacao": (validacao or {}).get("score_viralizacao"),
    }
    if conteudo_id and (existente := db.obter_conteudo(conteudo_id)):
        db.atualizar_conteudo(
            conteudo_id, titulo=conteudo["titulo"] or tema, persona_id=persona_id,
            assunto_id=assunto_id or existente["assunto_id"],
            validacao_id=(validacao or {}).get("id") or existente["validacao_id"], funil=funil, formato=formato,
            plataforma=plataforma, gancho=conteudo["gancho"], roteiro=conteudo["roteiro"],
            legenda=conteudo["legenda"], hashtags=conteudo["hashtags"],
            referencias=referencias or existente["referencias"], extras={**existente["extras"], **extras},
        )
        db.registrar_historico(conteudo_id, "roteirizado", f"Roteiro gerado na Máquina de Conteúdo ({formato})")
        if existente["status"] == "ideia":
            db.mover_conteudo(conteudo_id, "roteiro_pronto")
        return conteudo_id
    return db.criar_conteudo(
        conteudo["titulo"] or tema, persona_id=persona_id, assunto_id=assunto_id,
        validacao_id=(validacao or {}).get("id"), funil=funil, formato=formato, plataforma=plataforma,
        gancho=conteudo["gancho"], roteiro=conteudo["roteiro"], legenda=conteudo["legenda"],
        hashtags=conteudo["hashtags"], referencias=referencias, extras=extras,
    )
