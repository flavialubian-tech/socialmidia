"""Estúdio (Módulo 4): organiza os trabalhos de vídeo e carrossel (pastas, etapas, histórico)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

import database as db
from services import carrossel, video


def _nome_seguro(nome: str) -> str:
    base = re.sub(r"[^\w.\-]+", "_", Path(nome).name).strip("._")
    return base or "arquivo"


def pasta_estudio(*partes: str) -> Path:
    pasta = db.pasta_dados() / "estudio" / Path(*partes) if partes else db.pasta_dados() / "estudio"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


# ===========================================================================
# Vídeo
# ===========================================================================
def novo_video(nome_arquivo: str, conteudo: bytes, titulo: str = "", conteudo_id: int | None = None) -> int:
    """Cria o trabalho e guarda o vídeo bruto na pasta dele."""
    job_id = db.criar_job("video", titulo or Path(nome_arquivo).stem, conteudo_id)
    destino = pasta_estudio("videos", f"job_{job_id}") / f"bruto_{_nome_seguro(nome_arquivo)}"
    destino.write_bytes(conteudo)
    db.atualizar_job(job_id, arquivo_entrada=str(destino), dados={"etapa": "enviado"})
    return job_id


def etapa_cortar(job_id: int, limiar_db: float = -35.0, min_silencio: float = 0.45, margem: float = 0.12,
                 cortar: bool = True, gerar_legendas: bool = True, usar_gpu: bool = False,
                 transcrever_fn: Callable = video.transcrever,
                 progresso: Callable[[str, float], None] = lambda _m, _p: None) -> dict:
    """Etapa 1: remove os silêncios e transcreve o vídeo já cortado."""
    job = db.obter_job(job_id)
    pasta = Path(job["arquivo_entrada"]).parent
    cortado = pasta / "cortado.mp4"
    db.atualizar_job(job_id, status="processando", erro=None)
    try:
        if cortar:
            progresso("✂️ Cortando os silêncios...", 0.0)
            stats = video.cortar_silencios(job["arquivo_entrada"], cortado, limiar_db, min_silencio, margem, usar_gpu,
                                           progresso_cb=lambda p: progresso("✂️ Cortando os silêncios...", p * 0.5))
        else:
            shutil.copyfile(job["arquivo_entrada"], cortado)
            from moviepy import VideoFileClip

            with VideoFileClip(str(cortado)) as clip:
                stats = {"duracao_original": round(clip.duration, 2), "duracao_final": round(clip.duration, 2),
                         "trechos": [(0.0, clip.duration)], "inicios": [0.0]}
        palavras, aviso = [], None
        if gerar_legendas:
            progresso("📝 Transcrevendo com o Whisper (a primeira vez baixa o modelo)...", 0.55)
            try:
                palavras = transcrever_fn(cortado)
            except video.VideoError as exc:  # sem Whisper: o corte continua valendo, só não há legendas
                aviso = str(exc)
        dados = {**job["dados"], "etapa": "cortado", "palavras": palavras, "aviso_transcricao": aviso,
                 "inicios": stats["inicios"], "duracao_original": float(stats["duracao_original"]),
                 "duracao_final": float(stats["duracao_final"]), "trechos": len(stats["trechos"]),
                 "opcoes_corte": {"limiar_db": limiar_db, "min_silencio": min_silencio, "margem": margem}}
        db.atualizar_job(job_id, status="pendente", dados=dados)
        progresso("Pronto!", 1.0)
        return dados
    except Exception as exc:
        db.atualizar_job(job_id, status="erro", erro=str(exc))
        raise


def etapa_renderizar(job_id: int, config: video.ConfigEdicao, palavras: list[dict] | None = None,
                     progresso: Callable[[float], None] = lambda _p: None) -> str:
    """Etapa 2: legendas, zooms e motions sobre o vídeo cortado."""
    job = db.obter_job(job_id)
    pasta = Path(job["arquivo_entrada"]).parent
    palavras = job["dados"].get("palavras", []) if palavras is None else palavras
    saida = pasta / "final.mp4"
    db.atualizar_job(job_id, status="processando", erro=None)
    try:
        info = video.renderizar(pasta / "cortado.mp4", saida, palavras, job["dados"].get("inicios", [0.0]),
                                config, progresso_cb=progresso)
        db.atualizar_job(job_id, status="concluido", arquivo_saida=str(saida),
                         dados={**job["dados"], "etapa": "renderizado", "palavras": palavras,
                                "config": config.como_dict(), "resultado": info})
        if job["conteudo_id"]:
            db.registrar_historico(job["conteudo_id"], "estudio",
                                   f"Vídeo editado no Estúdio ({info['duracao']}s, {info['largura']}×{info['altura']})")
        return str(saida)
    except Exception as exc:
        db.atualizar_job(job_id, status="erro", erro=str(exc))
        raise


def excluir_trabalho(job_id: int) -> None:
    job = db.obter_job(job_id)
    if job and job["arquivo_entrada"]:
        pasta = Path(job["arquivo_entrada"]).parent
        if pasta.parent.name in ("videos", "carrosseis") and pasta.is_dir():
            shutil.rmtree(pasta, ignore_errors=True)
    elif job and job["arquivo_saida"] and Path(job["arquivo_saida"]).is_file():
        Path(job["arquivo_saida"]).unlink()
    db.excluir_job(job_id)


# ===========================================================================
# Carrossel
# ===========================================================================
def salvar_template(nome: str, nome_arquivo: str, conteudo: bytes, **opcoes) -> int:
    destino = pasta_estudio("templates") / _nome_seguro(nome_arquivo)
    contador = 1
    while destino.exists():
        destino = destino.with_name(f"{destino.stem}_{contador}{destino.suffix}")
        contador += 1
    destino.write_bytes(conteudo)
    return db.criar_template(nome, str(destino), **opcoes)


def excluir_template(template_id: int) -> None:
    t = db.obter_template(template_id)
    if t and Path(t["caminho_imagem"]).is_file() and Path(t["caminho_imagem"]).parent == pasta_estudio("templates"):
        Path(t["caminho_imagem"]).unlink()
    db.excluir_template(template_id)


def salvar_fonte(nome_arquivo: str, conteudo: bytes) -> str:
    from PIL import ImageFont

    from services import fontes

    destino = pasta_estudio("fontes") / _nome_seguro(nome_arquivo)
    destino.write_bytes(conteudo)
    try:
        ImageFont.truetype(str(destino), 40)  # valida de verdade (o carregador normal cai para a padrão)
    except OSError:
        destino.unlink(missing_ok=True)
        raise
    fontes.carregar.cache_clear()
    return str(destino)


def gerar_carrossel(laminas: list[str], template_id: int | None, capa_id: int | None = None,
                    tamanho: tuple[int, int] = (1080, 1350), assinatura: str = "", mostrar_contador: bool = True,
                    conteudo_id: int | None = None, titulo: str = "", mover_para_edicao: bool = False):
    """Gera as lâminas, grava o .zip e registra no histórico. Retorna (imagens, bytes do zip, job_id)."""
    template = db.obter_template(template_id) if template_id else None
    capa = db.obter_template(capa_id) if capa_id else None
    imagens = carrossel.gerar_carrossel(laminas, template, capa, tamanho, assinatura, mostrar_contador)
    job_id = db.criar_job("carrossel", titulo or "Carrossel", conteudo_id,
                          dados={"laminas": laminas, "template_id": template_id, "capa_id": capa_id,
                                 "tamanho": list(tamanho), "assinatura": assinatura})
    caminho_zip = pasta_estudio("carrosseis") / f"carrossel_{job_id}.zip"
    dados_zip = carrossel.exportar_zip(imagens, caminho_zip)
    db.atualizar_job(job_id, status="concluido", arquivo_saida=str(caminho_zip))
    if conteudo_id:
        db.registrar_historico(conteudo_id, "estudio", f"Carrossel gerado no Estúdio ({len(imagens)} lâminas)")
        if mover_para_edicao and (c := db.obter_conteudo(conteudo_id)) and c["status"] in ("ideia", "roteiro_pronto"):
            db.mover_conteudo(conteudo_id, "em_edicao")
    return imagens, dados_zip, job_id
