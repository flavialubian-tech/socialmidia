"""Radar de Audiência: comentários -> IA -> Dores, Dicionário e Assuntos Quentes."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

import database as db
from services import scraper
from services.llm import config_atual, criar_llm, gerar_json

# A IA lê TODOS os comentários relevantes, em lotes. Modelos locais (Ollama) recebem lotes menores
# para não faltar memória; Claude/OpenAI aguentam lotes grandes.
LOTE_CARACTERES = {"ollama": 7_000, "padrao": 40_000}
MAX_LOTES = 25

SISTEMA = (
    "Você é uma estrategista sênior de conteúdo para Instagram e TikTok no Brasil, "
    "especialista em pesquisa de audiência. Você lê comentários reais e extrai insights "
    "acionáveis, sempre com base em evidências do texto. Responda sempre em português do Brasil "
    "e apenas com JSON válido."
)

PROMPT_ANALISE = """Analise os comentários abaixo, coletados de {origem} ({plataforma}).{parte}

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
  ],
  "comentarios_quentes": [
    {{"comentario": "o comentário EXATO, copiado da lista", "por_que": "por que ele pode virar um conteúdo", "ideia": "título do conteúdo para gravar respondendo a ele (máx. 12 palavras)", "potencial": 0-100}}
  ]
}}

Regras:
- De 3 a 7 dores, de 5 a 15 termos no dicionário, de 3 a 6 tendências e de 3 a 8 comentários quentes.
- Comentários quentes são os que viram vídeo sozinhos: perguntas que muita gente tem, dúvidas detalhadas,
  pedidos de conteúdo, relatos de problema, polêmicas ou opiniões fortes. Copie o texto exatamente como está.
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
    filtro: dict = field(default_factory=dict)


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


PROMPT_SINTESE = """Você recebeu análises PARCIAIS de {n} lotes de comentários de {origem} ({plataforma}),
totalizando {total} comentários. Junte tudo em UMA análise final.

{contexto_persona}
ANÁLISES PARCIAIS (JSON):
{parciais}

Regras para juntar:
- Una itens parecidos (mesma dor, mesmo tema) e aumente a frequência/intensidade do que aparece em vários lotes.
- Mantenha os comentários quentes com maior potencial (copie o texto exatamente como veio).
- De 3 a 7 dores, 5 a 15 termos, 3 a 6 tendências e 3 a 8 comentários quentes.
- Os temas, ângulos e ideias NUNCA podem conter as palavras proibidas da persona.

Responda com um JSON exatamente na mesma estrutura das análises parciais
(chaves: resumo, dores, dicionario, tendencias, comentarios_quentes)."""


# ---------------------------------------------------------------------------
# Filtro de relevância
# ---------------------------------------------------------------------------
# Palavras de comentários "de passagem": se quase tudo for isso, o comentário não traz informação.
_GENERICAS = set("""
a o e de da do das dos em no na um uma que q isso esse essa muito mt mto mais demais super tao
boa bom boas bons otima otimo otimas otimos dica dicas conteudo video videos post perfil
amei amo adorei gostei ameii amoo top show legal massa incrivel lindo linda lindos maravilhoso maravilhosa
perfeito perfeita sensacional arrasou arrasa parabens obrigada obrigado obg brigada valeu
seguindo sigo segui seguir seguidora seguidor ja to tô estou te voce vc tbm tambem sim verdade
dia tarde noite oi ola gente amiga amigo mana mulher menina vdd kkk kkkk kkkkk haha hahaha rs rsrs
salvando salvei salvo compartilhando compartilhei like curtido mesmo bem tudo nossa ne
""".split())


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", sem_acento))


def contar_palavras(texto: str) -> int:
    """Palavras de verdade: ignora @menções, links, emojis e pontuação."""
    limpo = re.sub(r"@\w+|https?://\S+", " ", texto)
    return len(re.findall(r"[^\W\d_]+|\d+", limpo))


def filtrar_comentarios(comentarios: list[dict], min_palavras: int = 8) -> tuple[list[dict], dict]:
    """Mantém só os comentários com conteúdo. Devolve (relevantes, estatísticas do que saiu)."""
    stats = {"coletados": len(comentarios), "relevantes": 0, "curtos": 0, "so_emoji": 0, "genericos": 0,
             "repetidos": 0, "min_palavras": min_palavras}
    vistos: set[str] = set()
    relevantes = []
    for c in comentarios:
        texto = " ".join(str(c.get("texto") or "").split())
        sem_mencoes = re.sub(r"@\w+", " ", texto)
        if not re.search(r"[^\W\d_]", sem_mencoes):
            stats["so_emoji"] += 1
            continue
        chave = _normalizar(sem_mencoes)
        if chave in vistos:
            stats["repetidos"] += 1
            continue
        vistos.add(chave)
        palavras = chave.split()
        if palavras and sum(p in _GENERICAS for p in palavras) / len(palavras) >= 0.8 and len(palavras) <= 15:
            stats["genericos"] += 1
            continue
        if contar_palavras(texto) < min_palavras:
            stats["curtos"] += 1
            continue
        relevantes.append({**c, "texto": texto})
    stats["relevantes"] = len(relevantes)
    return relevantes, stats


def resumo_filtro(stats: dict) -> str:
    descartados = stats["coletados"] - stats["relevantes"]
    partes = [f"{stats[k]} {rotulo}" for k, rotulo in (("curtos", f"com menos de {stats['min_palavras']} palavras"),
                                                         ("so_emoji", "só emoji"), ("genericos", "genéricos"),
                                                         ("repetidos", "repetidos")) if stats.get(k)]
    return (f"{stats['coletados']} comentários → {stats['relevantes']} relevantes"
            + (f" · descartados {descartados}: " + ", ".join(partes) if descartados else ""))


def dividir_em_lotes(comentarios: list[dict], max_caracteres: int) -> list[str]:
    """Todos os comentários, dos mais curtidos para os menos, em blocos de até `max_caracteres`."""
    lotes, atual, tamanho = [], [], 0
    for c in sorted(comentarios, key=lambda c: c.get("curtidas") or 0, reverse=True):
        texto = " ".join((c.get("texto") or "").split())
        if not texto:
            continue
        linha = f"[{c.get('curtidas') or 0}] {texto[:600]}"
        if atual and tamanho + len(linha) > max_caracteres:
            lotes.append("\n".join(atual))
            atual, tamanho = [], 0
        atual.append(linha)
        tamanho += len(linha) + 1
    if atual:
        lotes.append("\n".join(atual))
    return lotes


def preparar_comentarios(comentarios: list[dict], max_caracteres: int = 24_000, max_comentarios: int = 400) -> str:
    """Bloco único (usado pelo Termômetro): mais curtidos primeiro, sem duplicados, dentro do limite."""
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
        if total + len(linha) > max_caracteres or len(linhas) >= max_comentarios:
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
    quentes = []
    for q in _lista_de_dicts(bruta.get("comentarios_quentes"), "comentario"):
        ideia = str(q.get("ideia", "")).strip()
        if _contem_proibida(ideia, proibidas):
            continue
        try:
            potencial = int(float(q.get("potencial", 60)))
        except (TypeError, ValueError):
            potencial = 60
        quentes.append({"comentario": str(q["comentario"]).strip(), "por_que": str(q.get("por_que", "")).strip(),
                        "ideia": ideia, "potencial": max(0, min(100, potencial))})
    quentes.sort(key=lambda q: q["potencial"], reverse=True)
    return {"resumo": str(bruta.get("resumo", "")).strip(), "dores": dores,
            "dicionario": dicionario, "tendencias": tendencias, "comentarios_quentes": quentes[:8]}


def tamanho_do_lote() -> int:
    return LOTE_CARACTERES["ollama"] if config_atual().provedor == "ollama" else LOTE_CARACTERES["padrao"]


def analisar_comentarios(
    comentarios: list[dict],
    persona: dict | None = None,
    plataforma: str = "rede social",
    llm: BaseChatModel | None = None,
    palavra_chave: str | None = None,
    max_caracteres: int | None = None,
    progresso: Callable[[str], None] = lambda _msg: None,
) -> dict:
    """Analisa TODOS os comentários: em um envio só, ou em lotes + uma síntese final."""
    lotes = dividir_em_lotes(comentarios, max_caracteres or tamanho_do_lote())
    if not lotes:
        raise scraper.ColetaError("Não há comentários com texto suficiente para analisar.")
    if len(lotes) > MAX_LOTES:
        progresso(f"Muitos comentários: analisando os {MAX_LOTES} lotes mais curtidos.")
        lotes = lotes[:MAX_LOTES]
    origem = (f'vários vídeos em alta da busca "{palavra_chave}"' if palavra_chave else "um post")
    contexto = _contexto_persona(persona)
    proibidas = (persona or {}).get("palavras_proibidas")

    if len(lotes) == 1:
        bruta = gerar_json(PROMPT_ANALISE.format(origem=origem, plataforma=plataforma, parte="",
                                                 contexto_persona=contexto, comentarios=lotes[0]), SISTEMA, llm=llm)
        return normalizar_analise(bruta, proibidas)

    parciais = []
    for i, lote in enumerate(lotes, start=1):
        progresso(f"A IA está lendo o lote {i} de {len(lotes)}...")
        bruta = gerar_json(PROMPT_ANALISE.format(origem=origem, plataforma=plataforma,
                                                 parte=f" (parte {i} de {len(lotes)})", contexto_persona=contexto,
                                                 comentarios=lote), SISTEMA, llm=llm)
        parciais.append(normalizar_analise(bruta, proibidas))
    progresso("Juntando as análises dos lotes em um resultado final...")
    compactas = [{"resumo": p["resumo"], "dores": p["dores"][:6], "dicionario": p["dicionario"][:10],
                  "tendencias": p["tendencias"][:5], "comentarios_quentes": p["comentarios_quentes"][:5]}
                 for p in parciais]
    bruta = gerar_json(PROMPT_SINTESE.format(n=len(lotes), origem=origem, plataforma=plataforma,
                                             total=len(comentarios), contexto_persona=contexto,
                                             parciais=json.dumps(compactas, ensure_ascii=False)), SISTEMA, llm=llm)
    final = normalizar_analise(bruta, proibidas)
    if not final["comentarios_quentes"]:  # se a síntese esquecer, aproveita os dos lotes
        todos = [q for p in parciais for q in p["comentarios_quentes"]]
        final["comentarios_quentes"] = sorted(todos, key=lambda q: q["potencial"], reverse=True)[:8]
    return final


INTENSIDADE_DOR = {"alta": 80, "media": 60}  # dores de frequência baixa não viram assunto


def registrar_assuntos(analise: dict, persona_id: int | None, analise_id: int,
                       rastreador_id: int | None = None) -> list[int]:
    """Envia tendências e dores (frequência alta/média) para a aba Assuntos Quentes."""
    criados = []
    for t in analise["tendencias"]:
        descricao = t["motivo"] + (f"\n\nÂngulo sugerido: {t['angulo_sugerido']}" if t["angulo_sugerido"] else "")
        novo = db.criar_assunto_quente(t["tema"], descricao, t["intensidade"], persona_id, analise_id,
                                       tipo="tendencia", rastreador_id=rastreador_id)
        if novo:
            criados.append(novo)
    for d in analise["dores"]:
        if d["frequencia"] not in INTENSIDADE_DOR:
            continue
        descricao = "Dor do público" + (f" — “{d['evidencia']}”" if d["evidencia"] else "")
        novo = db.criar_assunto_quente(d["dor"], descricao, INTENSIDADE_DOR[d["frequencia"]], persona_id,
                                       analise_id, tipo="dor", rastreador_id=rastreador_id)
        if novo:
            criados.append(novo)
    for q in analise.get("comentarios_quentes", [])[:5]:
        if q["potencial"] < 60 or not q["ideia"]:
            continue
        descricao = f"💬 “{q['comentario']}”" + (f"\n\n{q['por_que']}" if q["por_que"] else "")
        novo = db.criar_assunto_quente(q["ideia"], descricao, q["potencial"], persona_id, analise_id,
                                       tipo="comentario", rastreador_id=rastreador_id)
        if novo:
            criados.append(novo)
    return criados


def executar_radar(
    url: str,
    comentarios: list[dict] | None = None,
    persona_id: int | None = None,
    limite: int = 300,
    llm: BaseChatModel | None = None,
    progresso: Callable[[str], None] = lambda _msg: None,
    metodo: str | None = None,
    plataforma: str | None = None,
    palavra_chave: str | None = None,
    rastreador_id: int | None = None,
    min_palavras: int | None = None,
) -> ResultadoRadar:
    """Pipeline completo. Se `comentarios` vier preenchido, pula a coleta automática (modo manual)."""
    url = url.strip() or "manual"
    if plataforma is None:
        plataforma = scraper.detectar_plataforma(url) if url.startswith("http") else "desconhecida"
    metodo = metodo or ("manual" if comentarios is not None else "apify")
    busca_id = db.criar_busca(url, plataforma, metodo, persona_id, rastreador_id)
    persona = db.obter_persona(persona_id) if persona_id else None

    try:
        if comentarios is None:
            db.atualizar_busca(busca_id, status="coletando")
            progresso(f"Coletando comentários do {plataforma} via Apify (pode levar 1-3 min)...")
            comentarios = scraper.coletar_apify(url, limite)
        if min_palavras is None:
            min_palavras = int(db.get_config("radar_min_palavras", "8"))
        relevantes, filtro = filtrar_comentarios(comentarios, min_palavras)
        db.atualizar_busca(busca_id, total_coletados=len(comentarios), filtro=filtro)
        progresso(resumo_filtro(filtro))
        total = db.salvar_comentarios(busca_id, relevantes)
        if total == 0:
            raise scraper.ColetaError(
                f"Nenhum comentário relevante para analisar ({resumo_filtro(filtro)}). "
                f"Diminua o mínimo de palavras (hoje {min_palavras}) ou use um post com mais comentários.")

        db.atualizar_busca(busca_id, status="analisando")
        if llm is None:
            llm = criar_llm(json_mode=True)
        analise = analisar_comentarios(relevantes, persona, plataforma, llm=llm, palavra_chave=palavra_chave,
                                       progresso=progresso)

        analise_id = db.salvar_analise(busca_id, persona_id, analise, config_atual().rotulo)
        progresso("Registrando Assuntos Quentes...")
        criados = registrar_assuntos(analise, persona_id, analise_id, rastreador_id)
        db.atualizar_busca(busca_id, status="concluido", erro=None)
        return ResultadoRadar(busca_id, analise_id, total, analise, criados, filtro)
    except Exception as exc:
        db.atualizar_busca(busca_id, status="erro", erro=str(exc))
        raise
