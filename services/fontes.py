"""Fontes usadas no Estúdio (legendas e carrosséis).

Por padrão usa a Source Sans Pro (licença SIL OFL) incluída em assets/fontes, para o resultado
ser igual em qualquer computador. A criadora pode enviar a própria fonte (.ttf/.otf).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

PASTA_FONTES = Path(__file__).resolve().parents[1] / "assets" / "fontes"
FONTE_PADRAO = PASTA_FONTES / "SourceSansPro-Black.ttf"
FONTE_PADRAO_BOLD = PASTA_FONTES / "SourceSansPro-Bold.ttf"


@lru_cache(maxsize=64)
def carregar(caminho: str | None, tamanho: int) -> ImageFont.FreeTypeFont:
    """Carrega a fonte pedida; se faltar, cai para a fonte incluída e, por último, a do Pillow."""
    for candidato in (caminho, str(FONTE_PADRAO)):
        if candidato and Path(candidato).is_file():
            try:
                return ImageFont.truetype(candidato, tamanho)
            except OSError:
                continue
    return ImageFont.load_default(size=tamanho)


def fonte_configurada() -> str | None:
    """Fonte escolhida em ⚙️ Configurações (ou None para a padrão)."""
    import database as db

    caminho = db.get_config("estudio_fonte", "")
    return caminho if caminho and Path(caminho).is_file() else None
