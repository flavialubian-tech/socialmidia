"""Radar de Audiência: comentários -> IA -> Dores, Dicionário e Assuntos Quentes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

import database as db
from services import scraper
from services.llm import config_atual, criar_llm, gerar_json

# Limite de texto enviado à IA (evita estourar o contexto de modelos locais).
MAX_CARACTERES_PROMPT = 24_000
MAX_COMENTARIOS_PROMPT = 400

SISTEMA = (
    "Você é uma estrategista sênior de conteúdo para Instagram e TikTok no Brasil, "
    "especialista em pesquisa de audiência. Você lê comentários reais e extrai insights "
    "acionáveis, sempre com base em evidências do texto. Responda sempre em português do Brasil "
    "e apenas com JSON válido."
)

PROMPT_ANALISE = """Analise os comentários abaixo, coletados de um post ({plataforma}).

{contexto_persona}
COMENTÁRIOS (formato: [curtidas] texto), ordenados dos mais curtidos para os menos:
{comentarios}

Gere um JSON exatamente com esta estrutura:
{{
  "resumo": "2 a 3 frases sobre o que esse público sente e procura",
  "dores": [
    {{"dor": "problema/desejo frustrado em uma frase", "evidencia": "trecho curto de um comentário real", "frequencia": "alta|media|baixa"}}
  ],
  "dicionario": [
    {{"termo": "gíria, expressão ou jeito de falar do público", "significado": "o que querem dizer", "exemplo": "frase de exemplo como o público usaria"}}
  ],
  "tendencias": [
    {{"tema": "assunto quente com potencial de virar conteúdo (máx. 10 palavras)", "motivo": "por que está quente, com base nos comentários", "intensidade": 0-100, "angulo_sugerido": "ideia de abordagem para um vídeo/carrossel"}}
  ]
}}

Regras:
- De 3 a 7 dores, de 5 a 15 termos no dicionário e de 3 a 6 tendências.
- Ordene dores por frequência e tendências por intensidade (maior primeiro).
- Não invente: se algo não aparece nos comentários, não inclua.
- Os temas e ângulos NUNCA podem conter as palavras proibidas da persona."""


@dataclass
class ResultadoRadar:
    busca_id: int
    analise_id: int
    total_comentarios: int
    analise: dict
    assuntos_criados: list[int] = field(default_factory=list)


def _contexto_persona(persona: dict | None) -> str:
    if not persona:
        return "PERSONA: não definida (análise genérica)."
    proibidas = ", ".join(persona.get("palavras_proibidas") or []) or "nenhuma"
    return (
        "PERSONA DA CRIADORA (use para priorizar o que é relevante para ela):\n"
        f"- Nome: {persona['nome']} ({persona['plataforma']})\n"
        f"- Público-alvo: {persona.get('publico_alvo') or '-'}\n"
        f"- Tom de voz: {persona.get('tom_de_voz') or '-'}\n"
        f"- Palavras proibidas: {proibidas}\n"
    )


def preparar_comentarios(comentarios: list[dict]) -> str:
    """Prioriza os mais curtidos, remove duplicados e respeita o limite de caracteres."""
    vistos: set[str] = set()
    linhas: list[str] = []
    total = 0
    for c in sorted(comentarios, key=lambda c: c.get("curtidas") or 0, reverse=True):
        texto = " ".join((c.get("texto") or "").split())
        chave = texto.lower()
        if len(texto) < 3 or chave in vistos:
            continue
        vistos.add(chave)
        linha = f"[{c.get('curtidas') or 0}] {texto[:500]}"
        if total + len(linha) > MAX_CARACTERES_PROMPT or len(linhas) >= MAX_COMENTARIOS_PROMPT:
            break
        linhas.append(linha)
        total += len(linha) + 1
    return "\n".join(linhas)


def _lista_de_dicts(valor, chave_obrigatoria: str) -> list[dict]:
    if not isinstance(valor, list):
        return []
    return [v for v in valor if isinstance(v, dict) and str(v.get(chave_obrigatoria, "")).strip()]


def _contem_proibida(texto: str, proibidas: list[str]) -> bool:
    texto = texto.lower()
    return any(p.strip() and p.strip().lower() in texto for p in proibidas)


def normalizar_analise(bruta: dict, palavras_proibidas: list[str] | None = None) -> dict:
    """Garante a estrutura esperada mesmo se a IA variar o formato."""
    proibidas = palavras_proibidas or []
    tendencias = []
    for t in _lista_de_dicts(bruta.get("tendencias"), "tema"):
        if _contem_proibida(f"{t.get('tema', '')} {t.get('angulo_sugerido', '')}", proibidas):
            continue
        try:
            intensidade = int(float(t.get("intensidade", 50)))
        except (TypeError, ValueError):
            intensidade = 50
        tendencias.append({
            "tema": str(t["tema"]).strip(),
            "motivo": str(t.get("motivo", "")).strip(),
            "intensidade": max(0, min(100, intensidade)),
            "angulo_sugerido": str(t.get("angulo_sugerido", "")).strip(),
        })
    tendencias.sort(key=lambda t: t["intensidade"], reverse=True)

    dores = [{"dor": str(d["dor"]).strip(),
              "evidencia": str(d.get("evidencia", "")).strip(),
              "frequencia": str(d.get("frequencia", "media")).lower().replace("é", "e")}
             for d in _lista_de_dicts(bruta.get("dores"), "dor")]
    dicionario = [{"termo": str(d["termo"]).strip(),
                   "significado": str(d.get("significado", "")).strip(),
                   "exemplo": str(d.get("exemplo", "")).strip()}
                  for d in _lista_de_dicts(bruta.get("dicionario"), "termo")]
    return {"resumo": str(bruta.get("resumo", "")).strip(), "dores": dores,
            "dicionario": dicionario, "tendencias": tendencias}


def analisar_comentarios(
    comentarios: list[dict],
    persona: dict | None = None,
    plataforma: str = "rede social",
    llm: BaseChatModel | None = None,
) -> dict:
    texto = preparar_comentarios(comentarios)
    if not texto:
        raise scraper.ColetaError("Não há comentários com texto suficiente para analisar.")
    prompt = PROMPT_ANALISE.format(
        plataforma=plataforma, contexto_persona=_contexto_persona(persona), comentarios=texto
    )
    bruta = gerar_json(prompt, SISTEMA, llm=llm)
    return normalizar_analise(bruta, (persona or {}).get("palavras_proibidas"))


def executar_radar(
    url: str,
    comentarios: list[dict] | None = None,
    persona_id: int | None = None,
    limite: int = 300,
    llm: BaseChatModel | None = None,
    progresso: Callable[[str], None] = lambda _msg: None,
) -> ResultadoRadar:
    """Pipeline completo. Se `comentarios` vier preenchido, pula a coleta automática (modo manual)."""
    url = url.strip() or "manual"
    plataforma = scraper.detectar_plataforma(url) if url != "manual" else "desconhecida"
    metodo = "manual" if comentarios is not None else "apify"
    busca_id = db.criar_busca(url, plataforma, metodo, persona_id)
    persona = db.obter_persona(persona_id) if persona_id else None

    try:
        if comentarios is None:
            db.atualizar_busca(busca_id, status="coletando")
            progresso(f"Coletando comentários do {plataforma} via Apify (pode levar 1-3 min)...")
            comentarios = scraper.coletar_apify(url, limite)
        total = db.salvar_comentarios(busca_id, comentarios)
        if total == 0:
            raise scraper.ColetaError("Nenhum comentário válido para analisar.")

        db.atualizar_busca(busca_id, status="analisando")
        progresso(f"{total} comentários salvos. A IA está analisando...")
        if llm is None:
            llm = criar_llm(json_mode=True)
        analise = analisar_comentarios(comentarios, persona, plataforma, llm=llm)

        analise_id = db.salvar_analise(busca_id, persona_id, analise, config_atual().rotulo)
        progresso("Registrando Assuntos Quentes...")
        criados = []
        for t in analise["tendencias"]:
            descricao = t["motivo"] + (f"\n\nÂngulo sugerido: {t['angulo_sugerido']}" if t["angulo_sugerido"] else "")
            novo = db.criar_assunto_quente(t["tema"], descricao, t["intensidade"], persona_id, analise_id)
            if novo:
                criados.append(novo)
        db.atualizar_busca(busca_id, status="concluido", erro=None)
        return ResultadoRadar(busca_id, analise_id, total, analise, criados)
    except Exception as exc:
        db.atualizar_busca(busca_id, status="erro", erro=str(exc))
        raise
