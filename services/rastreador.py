"""Rastreador Automático (piloto automático do Módulo 1).

Para cada palavra-chave cadastrada:
    busca os vídeos mais quentes (Apify) -> coleta os comentários -> IA analisa
    -> dores e tendências vão direto para "Assuntos Quentes".

O agendamento usa o APScheduler em segundo plano. A cada 15 minutos ele verifica
se algum rastreador está "pendente" (passou do dia/hora configurados desde a última
execução). Isso também cobre o caso de o computador estar desligado na sexta-feira:
a busca roda assim que o app for aberto de novo.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable

import database as db
from services import scraper
from services.radar import executar_radar
from services.scraper import ColetaError

log = logging.getLogger("rastreador")

INTERVALO_VERIFICACAO_MIN = 15
ESPERA_APOS_ERRO = timedelta(hours=6)  # evita gastar créditos repetindo uma falha a cada 15 min
_DIAS_INDICE = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_lock_ciclo = threading.Lock()  # um ciclo por vez neste processo (controla custo da Apify)


# ---------------------------------------------------------------------------
# Regras de agenda
# ---------------------------------------------------------------------------
def config_agenda() -> tuple[bool, str, str]:
    return (
        db.get_config("rastreador_agendamento_ativo", "1") == "1",
        db.get_config("rastreador_dia_semana", "fri"),
        db.get_config("rastreador_hora", "08:00"),
    )


def _hora_minuto(hora: str) -> tuple[int, int]:
    try:
        h, m = (int(x) for x in hora.split(":"))
        return max(0, min(23, h)), max(0, min(59, m))
    except ValueError:
        return 8, 0


def ultimo_horario_agendado(agora: datetime, dia: str, hora: str) -> datetime:
    """O horário agendado mais recente que já passou (ex.: a última sexta às 08:00)."""
    h, m = _hora_minuto(hora)
    alvo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
    alvo -= timedelta(days=(agora.weekday() - _DIAS_INDICE.get(dia, 4)) % 7)
    if alvo > agora:
        alvo -= timedelta(days=7)
    return alvo


def proximo_horario_agendado(agora: datetime, dia: str, hora: str) -> datetime:
    return ultimo_horario_agendado(agora, dia, hora) + timedelta(days=7)


def _data(texto: str | None) -> datetime | None:
    return datetime.fromisoformat(texto) if texto else None


def esta_pendente(rastreador: dict, agora: datetime, dia: str, hora: str,
                  ultima_tentativa: datetime | None = None) -> bool:
    if not rastreador["ativo"]:
        return False
    slot = ultimo_horario_agendado(agora, dia, hora)
    referencia = _data(rastreador["ultima_execucao"]) or _data(rastreador["criado_em"])
    if referencia and referencia >= slot:
        return False  # já rodou (ou foi criado) depois do último horário agendado
    if ultima_tentativa and agora - ultima_tentativa < ESPERA_APOS_ERRO:
        return False
    return True


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def executar_rastreador(
    rastreador_id: int,
    gatilho: str = "agendado",
    llm=None,
    buscar: Callable = scraper.buscar_videos,
    coletar: Callable = scraper.coletar_comentarios_apify,
) -> dict | None:
    """Roda um rastreador de ponta a ponta. Retorna None se ele já estava em execução."""
    r = db.obter_rastreador(rastreador_id)
    if not r:
        return None
    execucao_id = db.iniciar_execucao(rastreador_id, gatilho)
    if execucao_id is None:
        log.info("Rastreador %s já está em execução; ignorado.", rastreador_id)
        return None

    log.info("Rastreador '%s' (%s) iniciado.", r["palavra_chave"], r["plataforma"])
    try:
        videos = buscar(r["palavra_chave"], r["plataforma"], r["max_videos"])
        if not videos:
            db.finalizar_execucao(execucao_id, "sem_resultados", erro="Nenhum vídeo encontrado na busca.")
            return {"status": "sem_resultados", "videos": []}

        com_comentarios = [v for v in videos if v.get("comentarios", 1) > 0] or videos
        comentarios = coletar([v["url"] for v in com_comentarios], r["plataforma"], r["max_comentarios"])
        if not comentarios:
            db.finalizar_execucao(execucao_id, "sem_resultados", videos=videos,
                                  erro="Os vídeos encontrados não tinham comentários acessíveis.")
            return {"status": "sem_resultados", "videos": videos}

        try:
            resultado = executar_radar(
                f"busca: {r['palavra_chave']}",
                comentarios=comentarios,
                persona_id=r["persona_id"],
                llm=llm,
                metodo="rastreador",
                plataforma=r["plataforma"],
                palavra_chave=r["palavra_chave"],
                rastreador_id=rastreador_id,
            )
        except ColetaError as exc:  # todos os comentários eram "boa dica", emojis etc.
            db.finalizar_execucao(execucao_id, "sem_resultados", videos=videos, erro=str(exc))
            return {"status": "sem_resultados", "videos": videos}
        db.finalizar_execucao(execucao_id, "concluido", busca_id=resultado.busca_id, videos=videos,
                              total_comentarios=resultado.total_comentarios,
                              assuntos_criados=len(resultado.assuntos_criados))
        log.info("Rastreador '%s' concluído: %s assuntos novos.", r["palavra_chave"], len(resultado.assuntos_criados))
        return {"status": "concluido", "videos": videos, "assuntos": resultado.assuntos_criados,
                "analise_id": resultado.analise_id}
    except Exception as exc:
        log.exception("Rastreador '%s' falhou.", r["palavra_chave"])
        db.finalizar_execucao(execucao_id, "erro", erro=str(exc))
        return {"status": "erro", "erro": str(exc)}


def _ultimas_tentativas() -> dict[int, datetime]:
    tentativas: dict[int, datetime] = {}
    for e in db.listar_execucoes(limite=500):
        if e["rastreador_id"] not in tentativas:
            tentativas[e["rastreador_id"]] = datetime.fromisoformat(e["iniciado_em"])
    return tentativas


def rastreadores_pendentes(agora: datetime | None = None) -> list[dict]:
    ativo, dia, hora = config_agenda()
    if not ativo:
        return []
    agora = agora or datetime.now()
    tentativas = _ultimas_tentativas()
    return [r for r in db.listar_rastreadores(somente_ativos=True)
            if esta_pendente(r, agora, dia, hora, tentativas.get(r["id"]))]


def executar_pendentes(agora: datetime | None = None, **kwargs) -> list[dict]:
    """Chamado pelo agendador: roda, em sequência, todos os rastreadores pendentes."""
    if not _lock_ciclo.acquire(blocking=False):
        return []  # ciclo anterior ainda rodando
    try:
        return [res for r in rastreadores_pendentes(agora)
                if (res := executar_rastreador(r["id"], "agendado", **kwargs)) is not None]
    finally:
        _lock_ciclo.release()


def executar_todos_agora(**kwargs) -> list[dict]:
    with _lock_ciclo:
        return [res for r in db.listar_rastreadores(somente_ativos=True)
                if (res := executar_rastreador(r["id"], "manual", **kwargs)) is not None]


# ---------------------------------------------------------------------------
# Agendador em segundo plano
# ---------------------------------------------------------------------------
def criar_agendador(bloqueante: bool = False):
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.schedulers.blocking import BlockingScheduler

    agendador = (BlockingScheduler if bloqueante else BackgroundScheduler)(
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
    )
    agendador.add_job(executar_pendentes, "interval", minutes=INTERVALO_VERIFICACAO_MIN, id="verificar_pendentes",
                      next_run_time=datetime.now() + timedelta(minutes=1))
    return agendador


def iniciar_agendador():
    agendador = criar_agendador()
    agendador.start()
    log.info("Agendador do Rastreador iniciado (verificação a cada %s min).", INTERVALO_VERIFICACAO_MIN)
    return agendador


def executar_em_segundo_plano(agendador, rastreador_id: int | None = None) -> None:
    """Dispara uma execução manual sem travar a interface."""
    # Sem id fixo: a proteção contra execução dupla fica no banco (iniciar_execucao).
    if rastreador_id is None:
        agendador.add_job(executar_todos_agora)
    else:
        agendador.add_job(executar_rastreador, args=[rastreador_id, "manual"])
