"""Mensalidades do aluno. É um módulo extra e simulado: o sistema não processa pagamentos."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.academico.models import Matricula


class Mensalidade(models.Model):
    PAGA = "Pago"
    A_VENCER = "A vencer"
    EM_ATRASO = "Em atraso"

    matricula = models.ForeignKey(
        Matricula, on_delete=models.PROTECT, related_name="mensalidades", verbose_name="matrícula"
    )
    competencia = models.DateField("competência", help_text="Primeiro dia do mês de referência.")
    parcela = models.PositiveSmallIntegerField("parcela")
    total_parcelas = models.PositiveSmallIntegerField("total de parcelas")
    valor = models.DecimalField(
        "valor líquido",
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    bolsa_percentual = models.PositiveSmallIntegerField(
        "bolsa (%)", default=0, validators=[MaxValueValidator(100)]
    )
    vencimento = models.DateField("vencimento")
    paga_em = models.DateField("paga em", null=True, blank=True)

    class Meta:
        verbose_name = "mensalidade"
        verbose_name_plural = "mensalidades"
        ordering = ["-competencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["matricula", "competencia"], name="mensalidade_unica_por_mes"
            ),
        ]

    def __str__(self):
        return f"{self.matricula} - {self.competencia:%m/%Y}"

    @property
    def situacao(self):
        """Calculada, e não salva: uma parcela vira "Em atraso" só com a passagem do tempo."""
        if self.paga_em:
            return self.PAGA
        if self.vencimento < timezone.localdate():
            return self.EM_ATRASO
        return self.A_VENCER
