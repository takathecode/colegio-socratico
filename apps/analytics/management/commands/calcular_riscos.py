"""Recalcula o risco de evasão dos alunos ativos com o modelo já treinado.

Uso: python manage.py calcular_riscos
A rotina diária do Celery (apps/alertas/tasks.py, às 6h) chama a mesma função,
evasao.calcular_riscos().
"""

from django.core.management.base import BaseCommand, CommandError

from apps.analytics import evasao


class Command(BaseCommand):
    help = "Recalcula o risco de evasão de todos os alunos com matrícula ativa."

    def handle(self, *args, **opcoes):
        try:
            total = evasao.calcular_riscos()
        except evasao.ModeloNaoTreinado as erro:
            raise CommandError(str(erro)) from erro
        self.stdout.write(self.style.SUCCESS(f"Risco recalculado para {total} aluno(s)."))
