"""Fábrica de Carrosséis (Módulo 4): texto do roteiro + imagem de fundo -> lâminas PNG em um .zip."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from services import fontes

TAMANHOS = {
    "4:5 (1080×1350) — feed do Instagram": (1080, 1350),
    "1:1 (1080×1080) — quadrado": (1080, 1080),
    "9:16 (1080×1920) — Stories / TikTok": (1080, 1920),
}
_PREFIXO_LAMINA = re.compile(r"^\s*(l[âa]mina|slide|card)\s*\d+\s*[:.\-–]\s*", re.IGNORECASE)


class CarrosselError(RuntimeError):
    """Erro amigável para exibir na interface."""


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def dividir_texto(texto: str) -> list[str]:
    """Uma lâmina por bloco separado por linha em branco ou por '---'."""
    blocos = re.split(r"\n\s*(?:---+)?\s*\n|^\s*---+\s*$", texto.strip(), flags=re.MULTILINE)
    return [_PREFIXO_LAMINA.sub("", b).strip() for b in blocos if b and b.strip()]


def laminas_do_conteudo(conteudo: dict) -> list[str]:
    """Usa o texto de cada lâmina do roteiro salvo no Cofre (coluna Áudio/Texto)."""
    laminas = [_PREFIXO_LAMINA.sub("", (b.get("audio") or "")).strip() for b in conteudo.get("roteiro", [])]
    laminas = [l for l in laminas if l]
    if not laminas and conteudo.get("gancho"):
        laminas = [conteudo["gancho"]]
    return laminas


def _segmentos(texto: str) -> list[tuple[str, bool]]:
    """Separa trechos destacados com *asterisco* ou **duplo** (viram a cor de destaque)."""
    partes = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", texto)
    saida = []
    for parte in partes:
        if not parte:
            continue
        destaque = parte.startswith("*") and parte.endswith("*") and len(parte) > 2
        saida.append((parte.strip("*"), destaque))
    return saida


def _palavras(texto: str) -> list[tuple[str, bool, bool]]:
    """(palavra, destacada, quebra_de_linha_antes)."""
    palavras = []
    for n, linha in enumerate(texto.split("\n")):
        primeira = True
        for trecho, destaque in _segmentos(linha):
            for w in trecho.split():
                palavras.append((w, destaque, n > 0 and primeira))
                primeira = False
    return palavras


def _quebrar(palavras, fonte, largura_max: int, desenho: ImageDraw.ImageDraw):
    espaco = desenho.textlength(" ", font=fonte)
    linhas, atual, largura = [], [], 0.0
    for w, destaque, quebra in palavras:
        lw = desenho.textlength(w, font=fonte)
        if atual and (quebra or largura + espaco + lw > largura_max):
            linhas.append((atual, largura))
            atual, largura = [], 0.0
        atual.append((w, destaque, lw))
        largura += (espaco if len(atual) > 1 else 0) + lw
    if atual:
        linhas.append((atual, largura))
    return linhas, espaco


# ---------------------------------------------------------------------------
# Imagem
# ---------------------------------------------------------------------------
def _fundo(caminho: str | None, tamanho: tuple[int, int]) -> Image.Image:
    if caminho and Path(caminho).is_file():
        imagem = ImageOps.exif_transpose(Image.open(caminho)).convert("RGB")
        return ImageOps.fit(imagem, tamanho, Image.LANCZOS)  # preenche cortando as sobras (cover)
    return Image.new("RGB", tamanho, "#1d1d1f")


def _sombra(base: Image.Image, intensidade: int, posicao: str) -> Image.Image:
    """Escurece a imagem (mais forte onde fica o texto) para garantir leitura."""
    if intensidade <= 0:
        return base
    w, h = base.size
    alfa = Image.new("L", (1, 256))
    for y in range(256):
        rel = y / 255
        foco = {"topo": 1 - rel, "base": rel}.get(posicao, 1 - abs(rel - 0.5) * 2)
        alfa.putpixel((0, y), int(255 * intensidade / 100 * (0.55 + 0.45 * foco)))
    camada = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(camada, base, alfa.resize((w, h)))


def renderizar_lamina(texto: str, template: dict | None, indice: int, total: int,
                      tamanho: tuple[int, int] = (1080, 1350), assinatura: str = "",
                      mostrar_contador: bool = True) -> Image.Image:
    t = {"caminho_imagem": None, "fonte": None, "tamanho_fonte": 72, "cor_texto": "#FFFFFF",
         "cor_destaque": "#FFD60A", "posicao": "centro", "alinhamento": "centro", "margem": 90,
         "escurecer": 35, **(template or {})}
    w, h = tamanho
    imagem = _sombra(_fundo(t["caminho_imagem"], tamanho), int(t["escurecer"]), t["posicao"])
    desenho = ImageDraw.Draw(imagem)
    margem = int(t["margem"])
    largura_max, altura_max = w - 2 * margem, int(h * 0.62)

    # Ajuste automático: diminui a fonte até o texto caber na área
    palavras = _palavras(texto)
    escala_capa = 1.25 if indice == 0 else 1.0
    tamanho_fonte = int(int(t["tamanho_fonte"]) * escala_capa * w / 1080)
    while True:
        f = fontes.carregar(t["fonte"] or None, tamanho_fonte)
        linhas, espaco = _quebrar(palavras, f, largura_max, desenho)
        altura_linha = int(tamanho_fonte * 1.18)
        if len(linhas) * altura_linha <= altura_max or tamanho_fonte <= 28:
            break
        tamanho_fonte = int(tamanho_fonte * 0.92)

    altura_bloco = len(linhas) * altura_linha
    y = {"topo": int(h * 0.14), "base": h - int(h * 0.14) - altura_bloco}.get(t["posicao"], (h - altura_bloco) // 2)
    camada = Image.new("RGBA", tamanho, (0, 0, 0, 0))  # texto numa camada própria para ganhar sombra
    desenho_texto = ImageDraw.Draw(camada)
    for palavras_linha, largura in linhas:
        x = margem if t["alinhamento"] == "esquerda" else (w - largura) / 2
        for palavra, destaque, lw in palavras_linha:
            desenho_texto.text((x, y), palavra, font=f, fill=t["cor_destaque"] if destaque else t["cor_texto"])
            x += lw + espaco
        y += altura_linha
    sombra = camada.getchannel("A").filter(ImageFilter.GaussianBlur(max(2, tamanho_fonte // 14)))
    sombra = sombra.point(lambda a: int(a * 0.7))
    imagem.paste((0, 0, 0), (0, max(2, tamanho_fonte // 30)), sombra)
    imagem.paste(camada, (0, 0), camada)

    pequena = fontes.carregar(str(fontes.FONTE_PADRAO_BOLD), max(18, int(w * 0.028)))
    if mostrar_contador and total > 1:
        rotulo = f"{indice + 1}/{total}"
        desenho.text((w - margem - desenho.textlength(rotulo, font=pequena), int(h * 0.045)), rotulo,
                     font=pequena, fill=t["cor_texto"])
    if assinatura.strip():
        desenho.text(((w - desenho.textlength(assinatura, font=pequena)) / 2, h - int(h * 0.075)), assinatura,
                     font=pequena, fill=t["cor_texto"])
    if indice == 0 and total > 1:
        seta = "arraste →"
        desenho.text((w - margem - desenho.textlength(seta, font=pequena), h - int(h * 0.075)), seta,
                     font=pequena, fill=t["cor_destaque"])
    return imagem


def gerar_carrossel(laminas: list[str], template: dict | None, template_capa: dict | None = None,
                    tamanho: tuple[int, int] = (1080, 1350), assinatura: str = "",
                    mostrar_contador: bool = True) -> list[Image.Image]:
    if not laminas:
        raise CarrosselError("Não há texto para as lâminas.")
    total = len(laminas)
    return [renderizar_lamina(texto, (template_capa if i == 0 and template_capa else template), i, total,
                              tamanho, assinatura, mostrar_contador)
            for i, texto in enumerate(laminas)]


def exportar_zip(imagens: list[Image.Image], caminho: str | Path | None = None, prefixo: str = "lamina") -> bytes:
    """Gera o .zip com as lâminas em PNG (e grava em disco se `caminho` for informado)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, imagem in enumerate(imagens, start=1):
            png = io.BytesIO()
            imagem.save(png, "PNG", optimize=True)
            zf.writestr(f"{prefixo}_{i:02d}.png", png.getvalue())
    dados = buffer.getvalue()
    if caminho:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        Path(caminho).write_bytes(dados)
    return dados
