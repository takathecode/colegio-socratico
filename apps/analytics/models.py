"""Risco de evasão calculado pelo modelo preditivo (apps/analytics/evasao.py).

É um dado calculado, não digitado: o comando calcular_riscos (e a rotina diária do
Celery, em apps/alertas/tasks.py) apaga os registros e grava tudo de novo. Por isso o vínculo com a
matrícula usa CASCADE: perder um risco não perde histórico, ele é refeito no próximo cálculo.
"""

from django.db import models

from apps.academico.models import Matricula


class RiscoEvasao(models.Model):
    class Nivel(models.TextChoices):
        BAIXO = "BAIXO", "Risco baixo"
        MEDIO = "MEDIO", "Risco médio"
        ALTO = "ALTO", "Risco alto"

    matricula = models.OneToOneField(
        Matricula, on_delete=models.CASCADE, related_name="risco", verbose_name="matrícula"
    )
    probabilidade = models.DecimalField(
        "probabilidade de evasão (%)", max_digits=5, decimal_places=2
    )
    nivel = models.CharField("nível", max_length=5, choices=Nivel.choices)
    # Frases curtas que explicam o resultado, como "Frequência de 68%, abaixo do mínimo de 75%".
    motivos = models.JSONField("principais motivos", default=list, blank=True)

    # Os valores que o modelo recebeu, guardados para a tela mostrar de onde veio o resultado.
    frequencia = models.DecimalField("frequência (%)", max_digits=5, decimal_places=2)
    media = models.DecimalField("média", max_digits=4, decimal_places=2)
    tendencia = models.DecimalField("tendência das notas", max_digits=4, decimal_places=2)
    justificativas_pendentes = models.PositiveSmallIntegerField("justificativas pendentes")

    calculado_em = models.DateTimeField("calculado em", auto_now=True)

    class Meta:
        verbose_name = "risco de evasão"
        verbose_name_plural = "riscos de evasão"
        ordering = ["-probabilidade"]

    def __str__(self):
        return f"{self.matricula}: {self.probabilidade}% ({self.get_nivel_display()})"
