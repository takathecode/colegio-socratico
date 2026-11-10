"""Roda agora a mesma rotina que o Celery agenda para as 6h.

Uso: python manage.py gerar_alertas
Recalcula o risco de evasão (se o modelo estiver treinado) e gera os alertas do dia.
Os e-mails seguem pela fila do Celery, ou saem na hora se o Redis não estiver no ar.
"""

from django.core.management.base import BaseCommand

from apps.alertas.tasks import rotina_diaria


class Command(BaseCommand):
    help = "Recalcula o risco de evasão e gera os alertas automáticos do dia."

    def handle(self, *args, **opcoes):
        # Chamar a tarefa como função comum roda aqui mesmo, sem passar pela fila.
        resumo = rotina_diaria()
        if not resumo:
            self.stdout.write("Nenhum alerta novo: ninguém precisa ser avisado agora.")
            return
        for tipo, total in resumo.items():
            self.stdout.write(f"  {tipo}: {total}")
        self.stdout.write(self.style.SUCCESS(f"{sum(resumo.values())} alerta(s) novo(s)."))
