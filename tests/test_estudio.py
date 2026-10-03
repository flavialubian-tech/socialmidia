import io
import zipfile

import numpy as np
import pytest
from PIL import Image

import database as db
from services import carrossel, estudio, movimento, video

PALAVRAS = [{"texto": w, "inicio": round(i * 0.4, 2), "fim": round(i * 0.4 + 0.35, 2)}
            for i, w in enumerate("Pare de usar ÁGUA SANITÁRIA no piso! Tira o brilho em 3 dias".split())]


@pytest.fixture(scope="module")
def video_bruto(tmp_path_factory):
    """Vídeo 320x240 de 6 s: fala 0-2 s, silêncio 2-3.5 s, fala 3.5-6 s."""
    from moviepy import AudioArrayClip, VideoClip

    caminho = tmp_path_factory.mktemp("video") / "bruto.mp4"
    sr, dur = 44100, 6.0
    t = np.arange(int(dur * sr)) / sr
    audio = 0.4 * np.sin(2 * np.pi * 220 * t) * ((t < 2) | (t > 3.5)) + 0.001 * np.random.default_rng(1).standard_normal(len(t))
    clip = VideoClip(frame_function=lambda tt: np.full((240, 320, 3), int(40 + tt * 20), dtype=np.uint8), duration=dur)
    clip.with_audio(AudioArrayClip(np.c_[audio, audio], fps=sr)).write_videofile(
        str(caminho), fps=24, codec="libx264", audio_codec="aac", logger=None)
    return caminho


# --- Curvas -------------------------------------------------------------------
def test_easing_nos_extremos_e_sem_linearidade():
    for f in (movimento.ease_out_cubic, movimento.ease_in_out_cubic, movimento.ease_out_back):
        assert f(0) == pytest.approx(0) and f(1) == pytest.approx(1)
    assert movimento.ease_out_cubic(0.5) > 0.5 > movimento.ease_in_out_cubic(0.25)
    assert movimento.ease_out_back(0.7) > 1  # o "pop" passa do ponto
    assert movimento.progresso(5, 0, 2) == 1 and movimento.progresso(-1, 0, 2) == 0


# --- Silêncios ----------------------------------------------------------------
def test_detectar_falas_sintetico():
    sr = 16000
    t = np.arange(sr * 6) / sr
    fala = (t < 2) | ((t > 2.3) & (t < 3)) | (t > 4.5)  # pausa curta (0.3 s) fica; pausa longa (1.5 s) sai
    amostras = (0.5 * np.sin(2 * np.pi * 200 * t) * fala + 0.0005).astype(np.float32)
    trechos = video.detectar_falas(amostras, sr, min_silencio=0.45, margem=0.1)
    assert len(trechos) == 2
    assert trechos[0][0] == 0 and 3.0 < trechos[0][1] < 3.2
    assert 4.3 < trechos[1][0] < 4.5 and trechos[1][1] == pytest.approx(6.0, abs=0.03)
    assert video.inicios_dos_trechos(trechos) == [0.0, round(trechos[0][1], 3)]
    assert video.detectar_falas(np.zeros(sr, dtype=np.float32), sr) == []


# --- Legendas, ênfase e zoom -----------------------------------------------------
def test_agrupar_legendas():
    paginas = video.agrupar_legendas(PALAVRAS, max_palavras=3)
    assert all(1 <= len(p["palavras"]) <= 3 for p in paginas)
    textos = [" ".join(w["texto"] for w in p["palavras"]) for p in paginas]
    assert textos[:2] == ["Pare de usar", "ÁGUA SANITÁRIA no"]
    assert "piso!" in textos  # pontuação fecha a página
    assert all(len(t) <= 22 for t in textos)
    longas = video.agrupar_legendas([{"texto": "extraordinariamente", "inicio": 0, "fim": 0.5},
                                     {"texto": "complicado", "inicio": 0.5, "fim": 1}])
    assert len(longas) == 2  # passaria de 22 caracteres juntas
    for a, b in zip(paginas, paginas[1:]):
        assert a["fim"] <= b["inicio"] + 1e-9


def test_momentos_de_enfase_e_zoom():
    enfases = video.momentos_de_enfase(PALAVRAS, intervalo_min=1.0)
    assert PALAVRAS[3]["inicio"] in enfases  # ÁGUA (caixa alta)
    inicios = [0.0, 2.0, 4.0]
    base = video.fator_zoom(1.0, inicios, [], 6.0, ken_burns=False)
    depois_corte = video.fator_zoom(2.1, inicios, [], 6.0, ken_burns=False)
    assert base == 1.0 and depois_corte == pytest.approx(1.10)  # zoom alterna no corte
    pico = video.fator_zoom(0.3, [0.0], [0.0], 6.0, ken_burns=False, zoom_cortes=False)
    assert pico == pytest.approx(1.08)
    assert video.fator_zoom(5.0, [0.0], [0.0], 6.0, ken_burns=False) == 1.0  # punch volta ao normal
    valores = [video.fator_zoom(t / 10, inicios, enfases, 6.0) for t in range(60)]
    assert min(valores) >= 1.0 and max(valores) <= 1.25


def test_desenhar_legenda_destaca_palavra_ativa():
    img = video.desenhar_legenda(["PARE", "DE", "USAR"], 2, 900, 80, "#FFFFFF", "#FFD60A")
    pixels = np.asarray(img)
    amarelos = (pixels[..., 0] > 240) & (pixels[..., 1] > 200) & (pixels[..., 2] < 40) & (pixels[..., 3] > 200)
    assert amarelos.sum() > 200
    assert amarelos[:, : img.width // 2].sum() < amarelos[:, img.width // 2:].sum()  # "USAR" fica à direita
    pilula = video.desenhar_legenda(["PARE", "DE", "USAR"], 0, 900, 80, "#FFFFFF", "#FFD60A", "pilula")
    assert pilula.width > 100


# --- Vídeo de ponta a ponta ----------------------------------------------------------
def test_pipeline_video_completo(video_bruto):
    cid = db.criar_conteudo("Post", gancho="Pare de errar no piso")
    job = estudio.novo_video("meu vídeo.mp4", video_bruto.read_bytes(), "Teste", cid)
    progresso = []
    dados = estudio.etapa_cortar(job, transcrever_fn=lambda caminho: PALAVRAS,
                                 progresso=lambda m, p: progresso.append(p))
    assert dados["duracao_final"] < dados["duracao_original"] - 1.0  # silêncio de 1.5 s removido
    assert dados["trechos"] == 2 and len(dados["inicios"]) == 2 and progresso[-1] == 1.0
    assert db.obter_job(job)["status"] == "pendente"

    cfg = video.ConfigEdicao(formato="original", titulo="Pare de errar no piso")
    cortado = estudio.pasta_estudio("videos", f"job_{job}") / "cortado.mp4"
    quadro = video.previa_quadro(cortado, PALAVRAS, dados["inicios"], cfg, 0.5)
    assert quadro.size == (320, 240)
    saida = estudio.etapa_renderizar(job, cfg, progresso=lambda p: None)
    final = db.obter_job(job)
    assert final["status"] == "concluido" and final["arquivo_saida"] == saida
    assert final["dados"]["resultado"]["paginas_legenda"] >= 3
    from moviepy import VideoFileClip

    with VideoFileClip(saida) as clip:
        assert clip.size == [320, 240] and clip.audio is not None
        assert clip.duration == pytest.approx(dados["duracao_final"], abs=0.15)
    assert db.listar_historico(cid)[-1]["evento"] == "estudio"

    estudio.excluir_trabalho(job)
    assert db.obter_job(job) is None and not (estudio.pasta_estudio("videos") / f"job_{job}").joinpath("final.mp4").exists()


def test_sem_whisper_mantem_o_corte(video_bruto):
    def sem_whisper(_):
        raise video.VideoError("O Whisper não está instalado.")

    job = estudio.novo_video("v.mp4", video_bruto.read_bytes())
    dados = estudio.etapa_cortar(job, transcrever_fn=sem_whisper)
    assert dados["palavras"] == [] and "Whisper" in dados["aviso_transcricao"]
    assert db.obter_job(job)["status"] == "pendente"


def test_video_sem_fala_da_erro_amigavel(tmp_path):
    from moviepy import AudioArrayClip, VideoClip

    caminho = tmp_path / "mudo.mp4"
    clip = VideoClip(frame_function=lambda t: np.zeros((64, 64, 3), dtype=np.uint8), duration=1.0)
    clip.with_audio(AudioArrayClip(np.zeros((44100, 2)), fps=44100)).write_videofile(
        str(caminho), fps=10, codec="libx264", audio_codec="aac", logger=None)
    job = estudio.novo_video("mudo.mp4", caminho.read_bytes())
    with pytest.raises(video.VideoError, match="Não encontrei fala"):
        estudio.etapa_cortar(job, gerar_legendas=False)
    assert db.obter_job(job)["status"] == "erro"


# --- Carrossel -------------------------------------------------------------------
def test_dividir_texto_e_laminas_do_conteudo():
    assert carrossel.dividir_texto("Lâmina 1: Capa\n\nSegunda\nlinha\n---\nTerceira") == ["Capa", "Segunda\nlinha", "Terceira"]
    c = {"roteiro": [{"audio": "Slide 1 - Olá"}, {"audio": ""}, {"audio": "Fim"}], "gancho": "G"}
    assert carrossel.laminas_do_conteudo(c) == ["Olá", "Fim"]
    assert carrossel.laminas_do_conteudo({"roteiro": [], "gancho": "Só o gancho"}) == ["Só o gancho"]


def test_renderizar_lamina_destaque_e_texto_longo():
    lamina = carrossel.renderizar_lamina("Texto com *destaque* amarelo", None, 1, 5, (1080, 1350))
    pixels = np.asarray(lamina)
    assert lamina.size == (1080, 1350)
    assert ((pixels[..., 0] > 240) & (pixels[..., 1] > 200) & (pixels[..., 2] < 40)).sum() > 500
    longo = carrossel.renderizar_lamina(" ".join(["palavra"] * 150), {"tamanho_fonte": 110}, 2, 5)
    assert longo.size == (1080, 1350)  # encolhe a fonte em vez de estourar


def test_gerar_carrossel_com_template_e_zip(tmp_path):
    fundo = io.BytesIO()
    Image.new("RGB", (800, 600), (230, 230, 230)).save(fundo, "JPEG")
    tid = estudio.salvar_template("Claro", "fundo claro.jpg", fundo.getvalue(), escurecer=50, posicao="base")
    assert db.obter_template(tid)["posicao"] == "base"
    cid = db.criar_conteudo("Carrossel X", formato="Carrossel Checklist",
                            roteiro=[{"tempo": "Lâmina 1", "audio": "Capa", "tela": ""}])
    imagens, dados_zip, job = estudio.gerar_carrossel(["Capa", "Meio", "CTA"], tid, None, (1080, 1080), "@perfil",
                                                      conteudo_id=cid, titulo="X", mover_para_edicao=True)
    assert [i.size for i in imagens] == [(1080, 1080)] * 3
    nomes = zipfile.ZipFile(io.BytesIO(dados_zip)).namelist()
    assert nomes == ["lamina_01.png", "lamina_02.png", "lamina_03.png"]
    assert db.obter_job(job)["status"] == "concluido"
    assert db.obter_conteudo(cid)["status"] == "em_edicao"
    estudio.excluir_template(tid)
    assert db.obter_template(tid) is None


def test_salvar_fonte_invalida(tmp_path):
    with pytest.raises(OSError):
        estudio.salvar_fonte("falsa.ttf", b"isto nao e uma fonte")


# --- GPU incompatível: cai para a CPU sem quebrar ------------------------------
def test_gpu_incompativel_vira_cpu(monkeypatch):
    import sys
    import types

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def get_device_name(_):
            return "NVIDIA GeForce GTX 1060"

        @staticmethod
        def get_device_capability(_):
            return (6, 1)

    def ones(*_a, **_k):
        raise RuntimeError("CUDA error: no kernel image is available for execution on the device")

    fake_torch = types.SimpleNamespace(__version__="2.11.0+cu128", version=types.SimpleNamespace(cuda="12.8"),
                                       cuda=FakeCuda, ones=ones)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    video.diagnostico_gpu.cache_clear()
    try:
        d = video.diagnostico_gpu()
        assert d["status"] == "incompativel" and d["capacidade"] == "sm_61"
        assert video.tem_gpu() is False
        assert "GTX 1060" in video.texto_diagnostico_gpu() and "CPU" in video.texto_diagnostico_gpu()
        assert video.modelo_padrao() == "small"
    finally:
        video.diagnostico_gpu.cache_clear()


def test_transcricao_cai_para_cpu_se_a_gpu_falhar(monkeypatch, video_bruto):
    import sys
    import types

    dispositivos = []

    class Modelo:
        def __init__(self, dispositivo):
            self.dispositivo = dispositivo

        def transcribe(self, audio, **kw):
            if self.dispositivo == "cuda":
                raise RuntimeError("CUDA error: no kernel image is available for execution on the device")
            return {"segments": [{"words": [{"word": " Olá", "start": 0.1, "end": 0.4}]}]}

    def load_model(nome, device):
        dispositivos.append((nome, device))
        return Modelo(device)

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=load_model))
    monkeypatch.setattr(video, "tem_gpu", lambda: True)
    video._carregar_whisper.cache_clear()
    try:
        palavras = video.transcrever(video_bruto, modelo="medium")
    finally:
        video._carregar_whisper.cache_clear()
    assert palavras == [{"texto": "Olá", "inicio": 0.1, "fim": 0.4}]
    assert dispositivos == [("medium", "cuda"), ("medium", "cpu")]
