# Carrega o Celery junto com o Django, para que as tarefas usem esta configuração.
from .celery import app as celery_app

__all__ = ("celery_app",)
