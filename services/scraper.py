"""Coleta de comentários para o Radar de Audiência.

- Automática: via Apify (TikTok, Instagram e YouTube), exige APIFY_API_TOKEN.
- Manual: texto colado ou arquivo .txt/.csv — funciona sempre, sem custo.

Todas as funções devolvem a mesma estrutura normalizada:
    {"autor": str | None, "texto": str, "curtidas": int, "publicado_em": str | None}
"""

from __future__ import annotations

import csv
import io
import re
from urllib.parse import urlparse

from services.llm import obter_segredo

# Atores públicos da Apify Store para cada rede.
# Se algum ator mudar de nome ou de formato, ajuste apenas aqui e em _input_* abaixo.
ATORES_APIFY = {
    "tiktok": "clockworks/tiktok-comments-scraper",
    "instagram": "apify/instagram-comment-scraper",
    "youtube": "streamers/youtube-comments-scraper",
}
ATORES_BUSCA_APIFY = {
    "tiktok": "clockworks/tiktok-scraper",
    "instagram": "apify/instagram-hashtag-scraper",  # Instagram não tem busca por frase: usa hashtag
    "youtube": "streamers/youtube-scraper",
}


class ColetaError(RuntimeError):
    """Erro amigável para exibir na interface."""


def detectar_plataforma(url: str) -> str:
    host = urlparse(url.strip()).netloc.lower()
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return "desconhecida"


def url_valida(url: str) -> bool:
    partes = urlparse(url.strip())
    return partes.scheme in ("http", "https") and bool(partes.netloc)


def _input_apify(plataforma: str, urls: list[str], limite: int) -> dict:
    """Entrada dos atores de comentários. `limite` = comentários por post."""
    if plataforma == "tiktok":
        return {"postURLs": urls, "commentsPerPost": limite, "maxRepliesPerComment": 0}
    if plataforma == "instagram":
        return {"directUrls": urls, "resultsLimit": limite}
    if plataforma == "youtube":
        return {"startUrls": [{"url": u} for u in urls], "maxComments": limite}
    raise ColetaError("Plataforma não suportada pela coleta automática.")


def hashtag_de(palavra_chave: str) -> str:
    """'Limpeza porcelanato manchado' -> 'limpezaporcelanatomanchado'."""
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", palavra_chave).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _input_busca(plataforma: str, palavra_chave: str, limite: int) -> dict:
    """Entrada dos atores de busca de vídeos por palavra-chave."""
    if plataforma == "tiktok":
        return {"searchQueries": [palavra_chave], "resultsPerPage": limite, "searchSection": "/video",
                "shouldDownloadVideos": False, "shouldDownloadCovers": False}
    if plataforma == "instagram":
        return {"hashtags": [hashtag_de(palavra_chave)], "resultsLimit": limite, "resultsType": "posts"}
    if plataforma == "youtube":
        return {"searchQueries": [palavra_chave], "maxResults": limite, "maxResultsShorts": limite,
                "maxResultStreams": 0}
    raise ColetaError("Plataforma não suportada pela busca automática.")


def _primeiro(item: dict, *chaves: str):
    for chave in chaves:
        valor = item.get(chave)
        if valor not in (None, ""):
            return valor
    return None


def normalizar_item_apify(item: dict) -> dict | None:
    """Converte um item de qualquer um dos atores para o formato padrão."""
    texto = _primeiro(item, "text", "comment", "commentText", "content")
    if not texto:
        return None
    autor = _primeiro(item, "uniqueId", "ownerUsername", "author", "username", "authorName")
    if isinstance(autor, dict):
        autor = autor.get("username") or autor.get("name")
    curtidas = _primeiro(item, "diggCount", "likesCount", "voteCount", "likes") or 0
    try:
        curtidas = int(str(curtidas).replace(".", "").replace(",", ""))
    except ValueError:
        curtidas = 0
    publicado = _primeiro(item, "createTimeISO", "timestamp", "publishedTimeText", "date")
    return {"autor": autor, "texto": str(texto).strip(), "curtidas": curtidas, "publicado_em": publicado}


def executar_ator(ator: str, run_input: dict, limite_itens: int) -> list[dict]:
    """Roda um ator da Apify e devolve os itens brutos do dataset."""
    token = obter_segredo("APIFY_API_TOKEN")
    if not token:
        raise ColetaError("APIFY_API_TOKEN não configurado. Adicione no .env ou em ⚙️ Configurações.")

    from apify_client import ApifyClient

    cliente = ApifyClient(token)
    try:
        run = cliente.actor(ator).call(run_input=run_input)
    except Exception as exc:
        raise ColetaError(f"Falha ao executar '{ator}' na Apify: {exc}") from exc
    if not run:
        raise ColetaError("A Apify não retornou resultado.")

    # apify-client 3.x devolve um objeto; versões 1.x/2.x devolvem dict.
    dataset_id = getattr(run, "default_dataset_id", None) or (run.get("defaultDatasetId") if isinstance(run, dict) else None)
    if not dataset_id:
        raise ColetaError("A Apify não informou o dataset com os resultados.")
    return list(cliente.dataset(dataset_id).iterate_items(limit=limite_itens))


def coletar_comentarios_apify(urls: list[str], plataforma: str, limite_por_post: int = 100) -> list[dict]:
    if plataforma not in ATORES_APIFY:
        raise ColetaError("URL não reconhecida. Use um link do TikTok, Instagram ou YouTube.")
    itens = executar_ator(ATORES_APIFY[plataforma], _input_apify(plataforma, urls, limite_por_post),
                          limite_por_post * len(urls))
    return [c for c in (normalizar_item_apify(i) for i in itens) if c]


def coletar_apify(url: str, limite: int = 300) -> list[dict]:
    """Coleta os comentários de um único post (modo URL do Radar)."""
    if not obter_segredo("APIFY_API_TOKEN"):
        raise ColetaError("APIFY_API_TOKEN não configurado. Adicione no .env ou em ⚙️ Configurações, "
                          "ou use a opção de colar os comentários.")
    comentarios = coletar_comentarios_apify([url], detectar_plataforma(url), limite)
    if not comentarios:
        raise ColetaError("Nenhum comentário encontrado. O post pode ser privado ou não ter comentários.")
    return comentarios


# ---------------------------------------------------------------------------
# Busca de vídeos por palavra-chave (Rastreador e Termômetro)
# ---------------------------------------------------------------------------
def _numero(valor) -> int:
    if valor in (None, ""):
        return 0
    if isinstance(valor, (int, float)):
        return int(valor)
    texto = str(valor).strip().upper().replace(" ", "")
    multiplicador = 1
    if texto.endswith(("K", "M", "B")):
        multiplicador = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[texto[-1]]
        texto = texto[:-1].replace(",", ".")
        try:
            return int(float(texto) * multiplicador)
        except ValueError:
            return 0
    digitos = re.sub(r"[^0-9]", "", texto)
    return int(digitos) if digitos else 0


def normalizar_video(item: dict) -> dict | None:
    """Converte um resultado de busca (qualquer rede) para o formato padrão."""
    url = _primeiro(item, "webVideoUrl", "url", "postUrl", "videoUrl")
    if not url or not str(url).startswith("http"):
        return None
    autor = _primeiro(item, "ownerUsername", "channelName", "author")
    if not autor and isinstance(item.get("authorMeta"), dict):
        autor = item["authorMeta"].get("name")
    if isinstance(autor, dict):
        autor = autor.get("name") or autor.get("username")
    return {
        "url": str(url),
        "titulo": str(_primeiro(item, "title", "text", "caption", "description") or "")[:300],
        "autor": autor,
        "views": _numero(_primeiro(item, "playCount", "viewCount", "videoViewCount", "videoPlayCount", "views")),
        "curtidas": _numero(_primeiro(item, "diggCount", "likesCount", "likes")),
        "comentarios": _numero(_primeiro(item, "commentCount", "commentsCount")),
        "compartilhamentos": _numero(_primeiro(item, "shareCount", "sharesCount")),
        "publicado_em": _primeiro(item, "createTimeISO", "timestamp", "date", "uploadDate"),
    }


def pontuar_video(video: dict) -> float:
    """Engajamento ponderado: comentários e compartilhamentos valem mais que views."""
    return (video["views"] * 0.01 + video["curtidas"] + video["comentarios"] * 5
            + video["compartilhamentos"] * 3)


def buscar_videos(palavra_chave: str, plataforma: str, quantidade: int = 5, multiplicador: int = 3) -> list[dict]:
    """Busca vídeos da palavra-chave e devolve os `quantidade` mais quentes (por engajamento)."""
    if plataforma not in ATORES_BUSCA_APIFY:
        raise ColetaError(f"Busca por palavra-chave não disponível para '{plataforma}'.")
    pedidos = max(quantidade * multiplicador, 10)
    itens = executar_ator(ATORES_BUSCA_APIFY[plataforma], _input_busca(plataforma, palavra_chave, pedidos), pedidos)
    vistos, videos = set(), []
    for item in itens:
        video = normalizar_video(item)
        if video and video["url"] not in vistos:
            vistos.add(video["url"])
            videos.append(video)
    videos.sort(key=pontuar_video, reverse=True)
    return videos[:quantidade]


_PREFIXO_AUTOR = re.compile(r"^@?([\w.]{2,30})\s*[:\-–]\s+(.+)$")


def parse_texto_manual(texto: str) -> list[dict]:
    """Cada linha não vazia vira um comentário. Aceita o formato opcional 'usuario: comentário'."""
    comentarios = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if len(linha) < 2:
            continue
        autor = None
        casamento = _PREFIXO_AUTOR.match(linha)
        if casamento:
            autor, linha = casamento.group(1), casamento.group(2).strip()
        comentarios.append({"autor": autor, "texto": linha, "curtidas": 0, "publicado_em": None})
    return comentarios


_COLUNAS_TEXTO = ("texto", "comentario", "comentário", "comment", "text", "content")
_COLUNAS_AUTOR = ("autor", "author", "usuario", "usuário", "username", "user")
_COLUNAS_CURTIDAS = ("curtidas", "likes", "likescount", "diggcount", "votecount")


def parse_csv(conteudo: bytes) -> list[dict]:
    texto = conteudo.decode("utf-8-sig", errors="replace")
    try:
        dialeto = csv.Sniffer().sniff(texto[:2048], delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    leitor = csv.DictReader(io.StringIO(texto), dialect=dialeto)
    campos = {c.lower().strip(): c for c in (leitor.fieldnames or [])}

    def coluna(opcoes):
        return next((campos[o] for o in opcoes if o in campos), None)

    col_texto, col_autor, col_curtidas = coluna(_COLUNAS_TEXTO), coluna(_COLUNAS_AUTOR), coluna(_COLUNAS_CURTIDAS)
    if not col_texto:
        raise ColetaError("CSV sem coluna de texto. Use uma coluna chamada 'texto' ou 'comment'.")
    comentarios = []
    for linha in leitor:
        valor = (linha.get(col_texto) or "").strip()
        if not valor:
            continue
        try:
            curtidas = int(linha.get(col_curtidas) or 0) if col_curtidas else 0
        except ValueError:
            curtidas = 0
        comentarios.append({"autor": linha.get(col_autor) if col_autor else None,
                            "texto": valor, "curtidas": curtidas, "publicado_em": None})
    return comentarios


def parse_arquivo(nome: str, conteudo: bytes) -> list[dict]:
    if nome.lower().endswith(".csv"):
        return parse_csv(conteudo)
    return parse_texto_manual(conteudo.decode("utf-8-sig", errors="replace"))
