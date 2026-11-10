"""Coloca uma tarefa na fila do Celery sem nunca derrubar a tela.

Quando tudo está no ar, .delay() grava o pedido no Redis e volta na hora; o worker faz o
trabalho depois. Se o Redis estiver fora do ar, o Celery desiste em cerca de 2 segundos
(CELERY_BROKER_TRANSPORT_OPTIONS em settings.py) e a tarefa roda aqui mesmo, sem fila. Assim o professor
nunca vê um erro só porque o serviço de filas caiu: o aviso só demora um pouco mais.
"""

import logging

from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)


def enfileirar(tarefa, *argumentos):
    try:
        tarefa.delay(*argumentos)
    except OperationalError as erro:
        logger.warning(
            "Redis indisponível (%s). A tarefa %s rodou na hora, sem a fila.", erro, tarefa.name
        )
        tarefa.apply(args=argumentos)
