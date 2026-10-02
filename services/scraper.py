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
ATORES_APIFY = {
    "tiktok": "clockworks/tiktok-comments-scraper",
    "instagram": "apify/instagram-comment-scraper",
    "youtube": "streamers/youtube-comments-scraper",
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


def _input_apify(plataforma: str, url: str, limite: int) -> dict:
    if plataforma == "tiktok":
        return {"postURLs": [url], "commentsPerPost": limite, "maxRepliesPerComment": 0}
    if plataforma == "instagram":
        return {"directUrls": [url], "resultsLimit": limite}
    if plataforma == "youtube":
        return {"startUrls": [{"url": url}], "maxComments": limite}
    raise ColetaError("Plataforma não suportada pela coleta automática.")


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


def coletar_apify(url: str, limite: int = 300) -> list[dict]:
    token = obter_segredo("APIFY_API_TOKEN")
    if not token:
        raise ColetaError("APIFY_API_TOKEN não configurado. Adicione no .env ou em ⚙️ Configurações, "
                          "ou use a opção de colar os comentários.")
    plataforma = detectar_plataforma(url)
    if plataforma not in ATORES_APIFY:
        raise ColetaError("URL não reconhecida. Use um link do TikTok, Instagram ou YouTube.")

    from apify_client import ApifyClient

    cliente = ApifyClient(token)
    try:
        run = cliente.actor(ATORES_APIFY[plataforma]).call(run_input=_input_apify(plataforma, url, limite))
    except Exception as exc:
        raise ColetaError(f"Falha ao executar a coleta na Apify: {exc}") from exc
    if not run:
        raise ColetaError("A Apify não retornou resultado para esta coleta.")

    # apify-client 3.x devolve um objeto; versões 1.x/2.x devolvem dict.
    dataset_id = getattr(run, "default_dataset_id", None) or (run.get("defaultDatasetId") if isinstance(run, dict) else None)
    if not dataset_id:
        raise ColetaError("A Apify não informou o dataset com os comentários.")

    comentarios = []
    for item in cliente.dataset(dataset_id).iterate_items(limit=limite):
        normalizado = normalizar_item_apify(item)
        if normalizado:
            comentarios.append(normalizado)
    if not comentarios:
        raise ColetaError("Nenhum comentário encontrado. O post pode ser privado ou não ter comentários.")
    return comentarios


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
