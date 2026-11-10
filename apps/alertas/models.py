"""Alertas automáticos: avisos que o sistema manda sozinho para alunos, professores e coordenação.

Os alertas são criados pelas regras de apps/alertas/regras.py, chamadas pelas tarefas do
Celery (apps/alertas/tasks.py). Ninguém digita um alerta: por isso não há tela de cadastro.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Alerta(models.Model):
    class Tipo(models.TextChoices):
        # Regras da rotina diária
        RISCO_EVASAO = "RISCO_EVASAO", "Risco de evasão alto"
        FREQUENCIA_BAIXA = "FREQUENCIA_BAIXA", "Frequência abaixo do mínimo"
        MEDIA_BAIXA = "MEDIA_BAIXA", "Média abaixo de 6"
        JUSTIFICATIVA_ATRASADA = "JUSTIFICATIVA_ATRASADA", "Justificativas sem resposta"
        # Avisos disparados na hora por uma ação (professor salvou, mensagem enviada)
        NOTA_LANCADA = "NOTA_LANCADA", "Nota publicada"
        JUSTIFICATIVA_AVALIADA = "JUSTIFICATIVA_AVALIADA", "Justificativa avaliada"
        MENSAGEM_NOVA = "MENSAGEM_NOVA", "Mensagem nova"

    class Gravidade(models.TextChoices):
        # Os rótulos são os mesmos do selo (componentes/selo.html), que escolhe a cor.
        INFORMATIVO = "INFORMATIVO", "Informativo"
        ATENCAO = "ATENCAO", "Em atenção"
        RISCO = "RISCO", "Em risco"

    # CASCADE: um alerta não faz sentido sem a pessoa que o recebe.
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alertas",
        verbose_name="destinatário",
    )
    tipo = models.CharField("tipo", max_length=22, choices=Tipo.choices)
    gravidade = models.CharField("gravidade", max_length=11, choices=Gravidade.choices)
    titulo = models.CharField("título", max_length=120)
    texto = models.TextField("texto")
    # Caminho da tela onde a pessoa resolve o assunto, como "/aluno/frequencia/".
    link = models.CharField("link", max_length=200, blank=True)
    # Identifica "o mesmo assunto" para não repetir o alerta (ver regras.JANELA_SEM_REPETIR).
    # Exemplos: "frequencia-12" (matrícula 12) ou "nota-30" (avaliação 30).
    chave = models.CharField("chave do assunto", max_length=60)

    por_email = models.BooleanField("enviar também por e-mail", default=False)
    email_enviado_em = models.DateTimeField("e-mail enviado em", null=True, blank=True)

    criado_em = models.DateTimeField("criado em", default=timezone.now, editable=False)
    lido_em = models.DateTimeField("lido em", null=True, blank=True)

    class Meta:
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ["-criado_em", "-id"]
        indexes = [
            # O sino consulta os alertas não lidos da pessoa em toda página.
            models.Index(fields=["destinatario", "lido_em"], name="alerta_destinatario_lido"),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.destinatario})"

    @property
    def lido(self):
        return self.lido_em is not None
