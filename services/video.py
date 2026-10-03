"""Vídeo Automático (Módulo 4).

Etapa 1 — cortar_silencios(): detecta as falas pelo volume do áudio e remove os silêncios.
           transcrever(): Whisper com tempo de cada palavra (usa a GPU NVIDIA quando houver).
Etapa 2 — renderizar(): legendas sincronizadas (palavra ativa em destaque), zooms dinâmicos e motions:
           • zoom alternado nos cortes (disfarça o "jump cut" dos silêncios removidos)
           • punch-in nas palavras de ênfase
           • Ken Burns sutil (a imagem "respira" dentro de cada trecho)
           • legenda com entrada em pop (escala + opacidade + subida) e saída rápida
           • título do gancho animado nos primeiros segundos
           • barra de progresso
Todos os movimentos usam curvas suaves (services/movimento.py), nunca lineares.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw

from services import fontes
from services.movimento import (ease_in_out_cubic, ease_out_back, ease_out_cubic, misturar, progresso)

SR_ANALISE = 16_000
JANELA_S = 0.02


class VideoError(RuntimeError):
    """Erro amigável para exibir na interface."""


# ===========================================================================
# 1. Silêncios
# ===========================================================================
def detectar_falas(amostras: np.ndarray, sr: int, limiar_db: float = -35.0, min_silencio: float = 0.45,
                   margem: float = 0.12, min_fala: float = 0.12) -> list[tuple[float, float]]:
    """Trechos com fala (início, fim) em segundos.

    O volume é medido em janelas de 20 ms, em dB relativos ao trecho mais alto do vídeo
    (percentil 99, para um estalo não distorcer a referência). Pausas menores que
    `min_silencio` são mantidas (respiração natural); cada trecho ganha `margem` nas pontas.
    """
    mono = amostras.mean(axis=1) if amostras.ndim > 1 else amostras
    duracao = len(mono) / sr
    janela = max(1, int(sr * JANELA_S))
    n = len(mono) // janela
    if n == 0:
        return []
    blocos = mono[: n * janela].astype(np.float64).reshape(n, janela)
    rms = np.sqrt((blocos ** 2).mean(axis=1)) + 1e-10
    referencia = np.percentile(rms, 99)
    if referencia <= 1e-8:
        return []  # vídeo mudo
    com_fala = 20 * np.log10(rms / referencia) > limiar_db

    trechos: list[list[float]] = []
    inicio = None
    for i, ativo in enumerate(np.append(com_fala, False)):
        if ativo and inicio is None:
            inicio = i
        elif not ativo and inicio is not None:
            trechos.append([inicio * JANELA_S, i * JANELA_S])
            inicio = None

    unidos: list[list[float]] = []
    for t in trechos:
        if unidos and t[0] - unidos[-1][1] < min_silencio:
            unidos[-1][1] = t[1]
        else:
            unidos.append(t)
    unidos = [t for t in unidos if t[1] - t[0] >= min_fala]

    final: list[list[float]] = []
    for a, b in unidos:
        a, b = max(0.0, a - margem), min(duracao, b + margem)
        if final and a <= final[-1][1]:
            final[-1][1] = b
        else:
            final.append([a, b])
    return [(round(a, 3), round(b, 3)) for a, b in final]


def inicios_dos_trechos(trechos: list[tuple[float, float]]) -> list[float]:
    """Onde cada trecho começa na linha do tempo do vídeo já cortado."""
    inicios, acumulado = [], 0.0
    for a, b in trechos:
        inicios.append(round(acumulado, 3))
        acumulado += b - a
    return inicios


# ===========================================================================
# 2. Exportação (com barra de progresso e GPU opcional)
# ===========================================================================
def _logger(progresso_cb: Callable[[float], None] | None):
    if progresso_cb is None:
        return None
    from proglog import ProgressBarLogger

    class LoggerProgresso(ProgressBarLogger):
        def bars_callback(self, bar, attr, value, old_value=None):
            if bar == "frame_index" and attr == "index":
                total = self.bars[bar].get("total") or 1
                progresso_cb(min(1.0, value / total))

    return LoggerProgresso()


def exportar(clip, saida: str | Path, fps: float | None = None, usar_gpu: bool = False, preset: str = "medium",
             progresso_cb: Callable[[float], None] | None = None) -> str:
    """Grava MP4 (H.264 + AAC). Com usar_gpu tenta NVENC (placa NVIDIA) e cai para CPU se falhar."""
    codecs = (["h264_nvenc"] if usar_gpu else []) + ["libx264"]
    ultimo_erro = None
    for codec in codecs:
        try:
            clip.write_videofile(str(saida), fps=fps or clip.fps or 30, codec=codec, audio_codec="aac",
                                 preset=preset, threads=4, ffmpeg_params=["-pix_fmt", "yuv420p"],
                                 logger=_logger(progresso_cb))
            return codec
        except Exception as exc:  # NVENC indisponível, driver antigo etc.
            ultimo_erro = exc
    raise VideoError(f"Falha ao exportar o vídeo: {ultimo_erro}")


def audio_mono(caminho: str | Path, sr: int = SR_ANALISE) -> np.ndarray:
    """Áudio mono em float32, extraído com o FFmpeg que acompanha o moviepy (imageio-ffmpeg).

    Lemos direto pelo FFmpeg porque a leitura do áudio inteiro pelo moviepy 2.1 em outra taxa de
    amostragem devolve dados errados; assim também não é preciso ter FFmpeg instalado no Windows.
    """
    import subprocess

    import imageio_ffmpeg

    comando = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(caminho), "-vn", "-ac", "1",
               "-ar", str(sr), "-f", "f32le", "-"]
    resultado = subprocess.run(comando, capture_output=True)
    amostras = np.frombuffer(resultado.stdout, dtype=np.float32)
    if resultado.returncode != 0 or amostras.size == 0:
        raise VideoError("O vídeo não tem áudio (ou o arquivo não pôde ser lido) — não dá para detectar "
                         "silêncios nem gerar legendas.")
    return amostras


def cortar_silencios(entrada: str | Path, saida: str | Path, limiar_db: float = -35.0, min_silencio: float = 0.45,
                     margem: float = 0.12, usar_gpu: bool = False,
                     progresso_cb: Callable[[float], None] | None = None) -> dict:
    from moviepy import VideoFileClip, concatenate_videoclips

    clip = VideoFileClip(str(entrada))
    try:
        trechos = detectar_falas(audio_mono(entrada), SR_ANALISE, limiar_db, min_silencio, margem)
        # o áudio pode durar alguns milissegundos a mais que o vídeo
        trechos = [(a, min(b, clip.duration)) for a, b in trechos if a < clip.duration - 0.05]
        if not trechos:
            raise VideoError("Não encontrei fala no vídeo. Tente baixar a sensibilidade (limiar de silêncio).")
        cortado = concatenate_videoclips([clip.subclipped(a, b) for a, b in trechos])
        exportar(cortado, saida, fps=clip.fps, usar_gpu=usar_gpu, preset="veryfast", progresso_cb=progresso_cb)
        return {"duracao_original": round(clip.duration, 2), "duracao_final": round(cortado.duration, 2),
                "trechos": trechos, "inicios": inicios_dos_trechos(trechos)}
    finally:
        clip.close()


# ===========================================================================
# 3. Transcrição (Whisper)
# ===========================================================================
def tem_gpu() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def modelo_padrao() -> str:
    import database as db

    escolhido = db.get_config("estudio_whisper_modelo", "auto")
    if escolhido and escolhido != "auto":
        return escolhido
    return "medium" if tem_gpu() else "small"


@lru_cache(maxsize=1)
def _carregar_whisper(nome: str, dispositivo: str):
    import whisper

    return whisper.load_model(nome, device=dispositivo)


def transcrever(caminho: str | Path, modelo: str | None = None, idioma: str = "pt") -> list[dict]:
    """Palavras com início/fim em segundos (o áudio vai direto para o Whisper, sem exigir FFmpeg no PATH)."""
    try:
        import whisper  # noqa: F401
    except ImportError as exc:
        raise VideoError("O Whisper não está instalado. Veja no README como instalar o openai-whisper "
                         "e o PyTorch com suporte à sua placa NVIDIA.") from exc
    audio = audio_mono(caminho)
    gpu = tem_gpu()
    modelo_whisper = _carregar_whisper(modelo or modelo_padrao(), "cuda" if gpu else "cpu")
    resultado = modelo_whisper.transcribe(audio, language=idioma, word_timestamps=True, fp16=gpu, verbose=None)
    palavras = []
    for segmento in resultado.get("segments", []):
        for p in segmento.get("words", []):
            texto = p["word"].strip()
            if texto:
                palavras.append({"texto": texto, "inicio": round(float(p["start"]), 3),
                                 "fim": round(float(p["end"]), 3)})
    return palavras


# ===========================================================================
# 4. Legendas
# ===========================================================================
def agrupar_legendas(palavras: list[dict], max_palavras: int = 3, max_caracteres: int = 22,
                     pausa_quebra: float = 0.45) -> list[dict]:
    """Agrupa palavras em 'páginas' curtas (estilo TikTok/Reels)."""
    paginas: list[dict] = []
    atual: list[dict] = []
    for p in sorted(palavras, key=lambda p: p["inicio"]):
        if atual:
            caracteres = sum(len(x["texto"]) + 1 for x in atual) + len(p["texto"])
            quebra = (len(atual) >= max_palavras or caracteres > max_caracteres
                      or p["inicio"] - atual[-1]["fim"] > pausa_quebra
                      or re.search(r"[.!?…]$", atual[-1]["texto"]))
            if quebra:
                paginas.append({"inicio": atual[0]["inicio"], "fim": atual[-1]["fim"], "palavras": atual})
                atual = []
        atual.append(p)
    if atual:
        paginas.append({"inicio": atual[0]["inicio"], "fim": atual[-1]["fim"], "palavras": atual})
    for anterior, seguinte in zip(paginas, paginas[1:]):  # evita a legenda "piscar" entre páginas
        if seguinte["inicio"] - anterior["fim"] < 0.3:
            anterior["fim"] = seguinte["inicio"]
    return paginas


def _limpar(texto: str) -> str:
    return texto.strip().upper()


def desenhar_legenda(palavras: list[str], ativa: int, largura_max: int, tamanho: int, cor_texto: str,
                     cor_destaque: str, estilo: str = "cor", fonte: str | None = None) -> Image.Image:
    """Imagem RGBA da página de legenda, com a palavra ativa destacada (cor ou pílula)."""
    f = fontes.carregar(fonte, tamanho)
    contorno = max(2, int(tamanho * 0.09))
    espaco = int(tamanho * 0.28)
    medidor = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    medidas = []
    for w in palavras:
        caixa = medidor.textbbox((0, 0), _limpar(w), font=f, stroke_width=contorno)
        medidas.append((caixa[2] - caixa[0], caixa[3] - caixa[1], caixa[0], caixa[1]))

    linhas: list[list[int]] = [[]]
    largura_linha = 0
    for i, (w, *_resto) in enumerate(medidas):
        extra = w + (espaco if linhas[-1] else 0)
        if linhas[-1] and largura_linha + extra > largura_max:
            linhas.append([])
            largura_linha = 0
            extra = w
        linhas[-1].append(i)
        largura_linha += extra

    altura_linha = int(tamanho * 1.15)
    pad = int(tamanho * 0.25)
    larguras = [sum(medidas[i][0] for i in ln) + espaco * (len(ln) - 1) for ln in linhas]
    img = Image.new("RGBA", (max(larguras) + 2 * pad, altura_linha * len(linhas) + 2 * pad), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(img)
    for n, ln in enumerate(linhas):
        x = pad + (img.width - 2 * pad - larguras[n]) // 2
        y = pad + n * altura_linha
        for i in ln:
            w, h, ox, oy = medidas[i]
            texto = _limpar(palavras[i])
            cor = cor_texto
            if i == ativa and estilo == "pilula":
                folga = int(tamanho * 0.14)
                desenho.rounded_rectangle((x - folga, y - folga // 2, x + w + folga, y + altura_linha - folga // 2),
                                          radius=int(tamanho * 0.22), fill=cor_destaque)
                cor = "#111111"
            elif i == ativa:
                cor = cor_destaque
            desenho.text((x - ox, y - oy + (altura_linha - h) // 2), texto, font=f, fill=cor,
                         stroke_width=0 if (i == ativa and estilo == "pilula") else contorno, stroke_fill="#000000")
            x += w + espaco
    return img


def desenhar_titulo(texto: str, largura_max: int, tamanho: int, fonte: str | None = None) -> Image.Image:
    """Caixa do gancho (texto branco sobre fundo escuro arredondado)."""
    f = fontes.carregar(fonte, tamanho)
    medidor = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if medidor.textlength(teste, font=f) > largura_max and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = teste
    if atual:
        linhas.append(atual)
    linhas = linhas[:3]
    altura_linha = int(tamanho * 1.18)
    pad_x, pad_y = int(tamanho * 0.6), int(tamanho * 0.4)
    largura = int(max(medidor.textlength(ln, font=f) for ln in linhas)) + 2 * pad_x
    img = Image.new("RGBA", (largura, altura_linha * len(linhas) + 2 * pad_y), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(img)
    desenho.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=int(tamanho * 0.45),
                              fill=(10, 10, 10, 200))
    for n, ln in enumerate(linhas):
        x = (img.width - medidor.textlength(ln, font=f)) / 2
        desenho.text((x, pad_y + n * altura_linha), ln, font=f, fill="#FFFFFF")
    return img


# ===========================================================================
# 5. Zooms e motions
# ===========================================================================
def momentos_de_enfase(palavras: list[dict], intervalo_min: float = 2.5) -> list[float]:
    """Palavras que pedem um punch-in: números, exclamações/perguntas, palavras longas ou em CAIXA ALTA."""
    momentos: list[float] = []
    for p in palavras:
        texto = p["texto"].strip()
        limpo = re.sub(r"[^\wÀ-ú]", "", texto)
        enfatica = (re.search(r"\d", texto) or texto.endswith(("!", "?")) or len(limpo) >= 10
                    or (len(limpo) >= 3 and limpo.isupper()))
        if enfatica and (not momentos or p["inicio"] - momentos[-1] >= intervalo_min):
            momentos.append(p["inicio"])
    return momentos


def fator_zoom(t: float, inicios: list[float], enfases: list[float], duracao: float, intensidade: float = 1.0,
               zoom_cortes: bool = True, ken_burns: bool = True, punch: bool = True) -> float:
    """Zoom total no instante t (1.0 = sem zoom)."""
    z = 1.0
    if inicios:
        i = max(0, bisect.bisect_right(inicios, t) - 1)
        if zoom_cortes and i % 2 == 1:
            z += 0.10 * intensidade  # alterna o enquadramento a cada corte
        if ken_burns:
            fim = inicios[i + 1] if i + 1 < len(inicios) else duracao
            z += 0.035 * ease_in_out_cubic(progresso(t, inicios[i], max(fim - inicios[i], 0.01)))
    if punch and enfases:
        j = bisect.bisect_right(enfases, t) - 1
        if j >= 0:
            dt = t - enfases[j]
            subida, segura, descida = 0.14, 0.45, 0.35
            if dt < subida:
                z += 0.08 * intensidade * ease_out_cubic(dt / subida)
            elif dt < subida + segura:
                z += 0.08 * intensidade
            elif dt < subida + segura + descida:
                z += 0.08 * intensidade * (1 - ease_in_out_cubic((dt - subida - segura) / descida))
    return z


# ===========================================================================
# 6. Renderização
# ===========================================================================
@dataclass
class ConfigEdicao:
    formato: str = "original"          # original | 9:16
    legendas: bool = True
    estilo_legenda: str = "cor"        # cor | pilula
    cor_texto: str = "#FFFFFF"
    cor_destaque: str = "#FFD60A"
    tamanho_legenda: float = 0.095     # proporção da largura do vídeo
    posicao_legenda: float = 0.66      # proporção da altura (dentro da área segura do 9:16)
    max_palavras: int = 3
    zooms: bool = True
    intensidade_zoom: float = 1.0
    zoom_cortes: bool = True
    punch_enfase: bool = True
    ken_burns: bool = True
    titulo: str = ""
    duracao_titulo: float = 3.0
    barra_progresso: bool = True
    usar_gpu: bool = False
    fonte: str | None = None
    foco_vertical: float = 0.42        # onde costuma estar o rosto (0 = topo, 1 = base)
    extras: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return asdict(self)


def _par(n: float) -> int:
    n = int(round(n))
    return n - (n % 2)


class Renderizador:
    """Monta cada quadro: enquadramento + zoom, legenda animada, título e barra de progresso."""

    def __init__(self, clip, palavras: list[dict], inicios: list[float], config: ConfigEdicao):
        self.clip, self.config = clip, config
        self.duracao = clip.duration
        fw, fh = clip.size
        if config.formato == "9:16":
            self.W, self.H = 1080, 1920
        else:
            escala = min(1.0, 1920 / max(fw, fh))
            self.W, self.H = _par(fw * escala), _par(fh * escala)
        alvo = self.W / self.H
        self.src_w, self.src_h = (fh * alvo, fh) if fw / fh > alvo else (fw, fw / alvo)
        self.inicios = inicios if (config.zooms or config.ken_burns) else []
        self.enfases = momentos_de_enfase(palavras) if config.zooms and config.punch_enfase else []
        self.paginas = agrupar_legendas(palavras, config.max_palavras) if config.legendas else []
        self.inicios_paginas = [p["inicio"] for p in self.paginas]
        tamanho = max(24, int(self.W * config.tamanho_legenda))
        self._cache_legendas: dict[tuple[int, int], Image.Image] = {}
        self._tamanho_legenda = tamanho
        self.titulo_img = (desenhar_titulo(config.titulo, int(self.W * 0.80), max(22, int(self.W * 0.06)),
                                           config.fonte) if config.titulo.strip() else None)

    # --- peças ---------------------------------------------------------------
    def _legenda(self, i_pagina: int, ativa: int) -> Image.Image:
        chave = (i_pagina, ativa)
        if chave not in self._cache_legendas:
            c = self.config
            self._cache_legendas[chave] = desenhar_legenda(
                [p["texto"] for p in self.paginas[i_pagina]["palavras"]], ativa, int(self.W * 0.84),
                self._tamanho_legenda, c.cor_texto, c.cor_destaque, c.estilo_legenda, c.fonte)
        return self._cache_legendas[chave]

    @staticmethod
    def _colar(base: Image.Image, img: Image.Image, cx: float, cy: float, escala: float, opacidade: float):
        if opacidade <= 0.01 or escala <= 0.01:
            return
        if abs(escala - 1) > 0.01:
            img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.BILINEAR)
        if opacidade < 0.99:
            alfa = img.getchannel("A").point(lambda a: int(a * opacidade))
            img = img.copy()
            img.putalpha(alfa)
        base.paste(img, (int(cx - img.width / 2), int(cy - img.height / 2)), img)

    def _desenhar_legenda(self, base: Image.Image, t: float) -> None:
        i = bisect.bisect_right(self.inicios_paginas, t) - 1
        if i < 0:
            return
        pagina = self.paginas[i]
        if t > pagina["fim"]:
            return
        ativa = max(0, bisect.bisect_right([p["inicio"] for p in pagina["palavras"]], t) - 1)
        p = progresso(t, pagina["inicio"], 0.22)
        escala = misturar(0.72, 1.0, ease_out_back(p))
        opacidade = ease_out_cubic(p)
        subida = misturar(self.H * 0.025, 0, ease_out_cubic(p))
        proxima = self.paginas[i + 1]["inicio"] if i + 1 < len(self.paginas) else None
        if proxima is None or proxima - pagina["fim"] > 0.05:  # saída só quando há pausa depois
            q = progresso(t, pagina["fim"] - 0.1, 0.1)
            opacidade *= 1 - ease_out_cubic(q)
            escala *= misturar(1.0, 0.92, q)
        self._colar(base, self._legenda(i, ativa), self.W / 2, self.H * self.config.posicao_legenda + subida,
                    escala, opacidade)

    def _desenhar_titulo(self, base: Image.Image, t: float) -> None:
        dur = self.config.duracao_titulo
        if self.titulo_img is None or t > dur:
            return
        p = progresso(t, 0.05, 0.4)
        q = progresso(t, dur - 0.2, 0.2)
        escala = misturar(0.85, 1.0, ease_out_back(p)) * misturar(1.0, 0.94, q)
        opacidade = ease_out_cubic(p) * (1 - ease_out_cubic(q))
        cy = self.H * 0.15 + misturar(-self.H * 0.02, 0, ease_out_cubic(p))
        self._colar(base, self.titulo_img, self.W / 2, cy, escala, opacidade)

    def _desenhar_barra(self, base: Image.Image, t: float) -> None:
        altura = max(6, int(self.H * 0.006))
        desenho = ImageDraw.Draw(base)
        desenho.rectangle((0, 0, self.W, altura), fill=(255, 255, 255))
        desenho.rectangle((0, 0, int(self.W * min(1.0, t / max(self.duracao, 0.01))), altura),
                          fill=self.config.cor_destaque)

    # --- quadro --------------------------------------------------------------
    def quadro(self, t: float) -> np.ndarray:
        imagem = Image.fromarray(self.clip.get_frame(t))
        z = fator_zoom(t, self.inicios, self.enfases, self.duracao, self.config.intensidade_zoom,
                       self.config.zooms and self.config.zoom_cortes, self.config.ken_burns,
                       self.config.zooms and self.config.punch_enfase)
        cw, ch = self.src_w / z, self.src_h / z
        fw, fh = imagem.size
        cx = fw / 2
        # sem folga vertical fica no centro; quanto mais zoom, mais se aproxima do ponto do rosto
        foco = fh * self.config.foco_vertical
        cy = min(max(foco + (fh / 2 - foco) * (ch / fh), ch / 2), fh - ch / 2)
        cx = min(max(cx, cw / 2), fw - cw / 2)
        imagem = imagem.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2)))
        imagem = imagem.resize((self.W, self.H), Image.BILINEAR)
        if self.paginas:
            self._desenhar_legenda(imagem, t)
        self._desenhar_titulo(imagem, t)
        if self.config.barra_progresso:
            self._desenhar_barra(imagem, t)
        return np.asarray(imagem)


def renderizar(entrada: str | Path, saida: str | Path, palavras: list[dict], inicios: list[float],
               config: ConfigEdicao, progresso_cb: Callable[[float], None] | None = None) -> dict:
    from moviepy import VideoClip, VideoFileClip

    clip = VideoFileClip(str(entrada))
    try:
        r = Renderizador(clip, palavras, inicios, config)
        final = VideoClip(frame_function=r.quadro, duration=clip.duration)
        if clip.audio is not None:
            final = final.with_audio(clip.audio)
        codec = exportar(final, saida, fps=clip.fps, usar_gpu=config.usar_gpu, progresso_cb=progresso_cb)
        return {"largura": r.W, "altura": r.H, "duracao": round(clip.duration, 2), "codec": codec,
                "paginas_legenda": len(r.paginas), "zooms_enfase": len(r.enfases)}
    finally:
        clip.close()


def previa_quadro(entrada: str | Path, palavras: list[dict], inicios: list[float], config: ConfigEdicao,
                  t: float) -> Image.Image:
    """Um quadro do resultado final, para conferir o estilo antes de renderizar o vídeo todo."""
    from moviepy import VideoFileClip

    clip = VideoFileClip(str(entrada))
    try:
        r = Renderizador(clip, palavras, inicios, config)
        return Image.fromarray(r.quadro(min(max(0.0, t), max(0.0, clip.duration - 0.05))))
    finally:
        clip.close()
