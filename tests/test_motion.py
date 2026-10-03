import numpy as np
import pytest
from PIL import Image

from services import motion, video

FRASE = ("Pare de usar água sanitária no piso! Ela tira o brilho em 3 dias. A dica é usar detergente "
         "neutro e o resultado aparece rápido. Salva esse vídeo")
PALAVRAS = [{"texto": w, "inicio": round(i * 0.34, 2), "fim": round(i * 0.34 + 0.3, 2)}
            for i, w in enumerate(FRASE.split())]


def test_icone_da_palavra():
    assert motion.icone_da_palavra("Erro!") == "x"
    assert motion.icone_da_palavra("NÃO") == "x"
    assert motion.icone_da_palavra("dica") == "ideia"
    assert motion.icone_da_palavra("dinheiro,") == "dinheiro"
    assert motion.icone_da_palavra("resultados") == "grafico"
    assert motion.icone_da_palavra("casa") is None
    assert motion.icone_da_palavra("a") is None


@pytest.mark.parametrize("nome", motion.ICONES)
def test_todos_os_icones_desenham(nome):
    img = motion.desenhar_icone(nome, 120, "#FFD60A")
    assert img.size == (120, 120) and img.mode == "RGBA"
    alfa = np.asarray(img.getchannel("A"))
    assert alfa[60, 60] > 0 and alfa[0, 0] == 0  # forma no centro, cantos transparentes


def test_detectar_eventos():
    eventos = motion.detectar_eventos(PALAVRAS, [0.0, 4.1], 9.0, stickers=True, destaques=True,
                                      transicoes="alternado", abertura=True, cta=False)
    tipos = [(e.tipo, e.dados.get("icone") or e.dados.get("texto") or e.dados.get("estilo")) for e in eventos]
    assert ("sticker", "x") in tipos and ("destaque", "3 DIAS") in tipos
    assert ("transicao", "flash") in tipos and ("abertura", None) in tipos
    stickers = [e for e in eventos if e.tipo == "sticker"]
    assert all(b.t - a.t >= 2.2 for a, b in zip(stickers, stickers[1:]))  # espaçamento mínimo
    assert [e.dados["lado"] for e in stickers] == [i % 2 for i in range(len(stickers))]  # alterna os lados


def test_cta_limpa_a_tela():
    eventos = motion.detectar_eventos(PALAVRAS, [0.0], 9.0, stickers=True, destaques=True, cta=True)
    cta = next(e for e in eventos if e.tipo == "cta")
    assert cta.t == pytest.approx(6.2)
    assert all(e.t + e.duracao <= cta.t for e in eventos if e.tipo in ("sticker", "destaque"))
    assert not any(e.tipo == "cta" for e in motion.detectar_eventos(PALAVRAS, [0.0], 5.0, cta=True))


def test_transicoes_alternadas_e_desligadas():
    eventos = motion.detectar_eventos([], [0, 2, 4, 6], 8, stickers=False, destaques=False, transicoes="alternado")
    assert [e.dados["estilo"] for e in eventos] == ["flash", "zoom", "glitch"]
    assert motion.detectar_eventos([], [0, 2], 8, transicoes="nenhuma", stickers=False, destaques=False) == []


@pytest.mark.parametrize("nome", ["whoosh", "pop", "clique", "ding"])
def test_sfx(nome):
    som = motion.sfx(nome)
    assert som.dtype == np.float32 and 0.02 < len(som) / 44100 < 1.0
    assert np.abs(som).max() == pytest.approx(1.0, abs=1e-4)


def test_mixar_sfx_nos_instantes_certos():
    sr = 44100
    audio = np.zeros((sr * 4, 2), dtype=np.float32)
    eventos = [motion.Evento("sticker", 1.0, 1.0), motion.Evento("transicao", 3.0, 0.2, {"estilo": "flash"})]
    mix = motion.mixar_sfx(audio, sr, eventos, volume=0.5)
    assert mix.shape == audio.shape and np.abs(mix).max() <= 1.0
    assert np.abs(mix[: int(0.9 * sr)]).max() == 0          # silêncio antes do primeiro evento
    assert np.abs(mix[sr: sr + 2000]).max() > 0.1            # pop no sticker
    assert np.abs(mix[int(2.9 * sr): int(3.1 * sr)]).max() > 0.05  # whoosh adiantado antes do corte
    alto = motion.mixar_sfx(np.full((sr, 2), 0.95, np.float32), sr, [motion.Evento("sticker", 0.0, 1)], 1.0)
    assert np.abs(alto).max() <= 1.0  # limitador evita distorção


def test_motion_desenha_e_acabamento():
    eventos = motion.detectar_eventos(PALAVRAS, [0.0, 4.1], 9.0, stickers=True, destaques=True,
                                      transicoes="glitch", abertura=True, cta=True)
    m = motion.Motion(360, 640, eventos, "#FFD60A", None, "@teste", "seguir", acabamento=True)
    base = Image.new("RGB", (360, 640), (40, 80, 120))
    for t in (0.2, 1.0, 4.2, 4.5, 7.4, 8.5):
        quadro = m.finalizar(base.copy(), t)
        if m.transicao_ativa(t):
            quadro = Image.fromarray(m.transicao(np.asarray(quadro), t))
        m.sobrepor(quadro, t)
        assert quadro.size == (360, 640)
    # vinheta escurece as bordas mais que o centro
    f = np.asarray(m.finalizar(Image.new("RGB", (360, 640), (200, 200, 200)), 0.0)).astype(int)
    assert f[5, 5].mean() < f[320, 180].mean() - 20


def test_render_com_motion_e_sons(tmp_path):
    from moviepy import AudioArrayClip, VideoClip, VideoFileClip

    entrada = tmp_path / "v.mp4"
    sr = 44100
    au = (0.2 * np.sin(2 * np.pi * 220 * np.arange(sr * 7) / sr)).astype(np.float32)
    VideoClip(frame_function=lambda t: np.full((240, 320, 3), 90, np.uint8), duration=7).with_audio(
        AudioArrayClip(np.c_[au, au], fps=sr)).write_videofile(str(entrada), fps=12, codec="libx264",
                                                               audio_codec="aac", logger=None)
    cfg = video.ConfigEdicao(estilo_legenda="hormozi", stickers=True, destaques=True, abertura=True,
                             nome_abertura="@x", cta=False, transicoes="flash", sons=True, acabamento=True)
    info = video.renderizar(entrada, tmp_path / "out.mp4", PALAVRAS[:16], [0.0, 3.0], cfg)
    assert info["stickers"] >= 1 and info["destaques"] == 1 and info["transicoes"] == 1
    with VideoFileClip(str(tmp_path / "out.mp4")) as clip:
        assert clip.audio is not None and clip.duration == pytest.approx(7, abs=0.2)


def test_hormozi_usa_paginas_curtas():
    from moviepy import ColorClip

    clip = ColorClip((320, 240), color=(0, 0, 0), duration=5)
    r = video.Renderizador(clip, PALAVRAS, [0.0], video.ConfigEdicao(estilo_legenda="hormozi", max_palavras=4))
    assert all(len(p["palavras"]) <= 2 for p in r.paginas)
    assert r.quadro(1.0).shape == (240, 320, 3)
