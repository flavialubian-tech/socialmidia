"""Piloto automático sem a interface aberta.

    python worker.py            # fica rodando e executa os rastreadores no dia/hora configurados
    python worker.py --agora    # roda só os rastreadores pendentes e encerra (para o Agendador
                                # de Tarefas do Windows ou o cron do Mac/Linux)
    python worker.py --todos    # roda todos os rastreadores ativos agora e encerra

Não há problema em deixar o worker e o app abertos ao mesmo tempo: um rastreador
nunca roda duas vezes em paralelo.
"""

import argparse
import logging

from dotenv import load_dotenv

from database import BASE_DIR, init_db
from services import rastreador


def main() -> None:
    parser = argparse.ArgumentParser(description="Rastreador Automático — Social Mídia Autônoma")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--agora", action="store_true", help="roda os pendentes e encerra")
    grupo.add_argument("--todos", action="store_true", help="roda todos os ativos e encerra")
    args = parser.parse_args()

    load_dotenv()
    (BASE_DIR / "data").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(BASE_DIR / "data" / "rastreador.log", encoding="utf-8")],
    )
    init_db()

    if args.agora or args.todos:
        resultados = rastreador.executar_todos_agora() if args.todos else rastreador.executar_pendentes()
        logging.info("%s rastreador(es) executado(s).", len(resultados))
        return

    logging.info("Worker do Rastreador rodando. Ctrl+C para sair.")
    try:
        rastreador.criar_agendador(bloqueante=True).start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Worker encerrado.")


if __name__ == "__main__":
    main()
