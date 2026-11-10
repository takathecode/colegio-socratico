"""Aplicação Celery do projeto: tarefas assíncronas e agendadas.

O Celery tira trabalho demorado (enviar e-mail, recalcular riscos) do caminho da tela.
A view só coloca um pedido na fila do Redis e responde na hora; o worker, um processo
separado, pega o pedido e faz o trabalho. O beat é o "despertador" que coloca a rotina
diária na fila no horário marcado (CELERY_BEAT_SCHEDULE, em settings.py).

Para rodar, cada um em um terminal (no Windows o worker precisa de --pool=solo):
    celery -A config worker --pool=solo -l info
    celery -A config beat -l info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

# Lê do settings.py todas as configurações que começam com CELERY_.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Procura um arquivo tasks.py em cada app instalado (ex.: apps/alertas/tasks.py).
app.autodiscover_tasks()
