"""Tarefas do Celery: rodam no worker, fora do caminho da tela.

- rotina_diaria: agendada pelo beat para as 6h (CELERY_BEAT_SCHEDULE em settings.py).
  Recalcula o risco de evasão e roda as regras de alerta do dia.
- avisar_notas_publicadas e avisar_justificativa_avaliada: colocadas na fila pela tela do
  professor, logo depois que ele salva. O professor não espera o aviso ser gerado.
- enviar_email: manda o e-mail de um alerta. Se o servidor de e-mail falhar, o Celery tenta
  de novo mais tarde, até 3 vezes.

As tarefas recebem só o id (número) dos registros, não o objeto inteiro: o pedido na fila
fica pequeno e o worker lê o dado atualizado do banco na hora de trabalhar.
"""

import logging
from collections import Counter

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.academico.models import Avaliacao, Justificativa
from apps.analytics import evasao

from . import regras
from .fila import enfileirar
from .models import Alerta

logger = logging.getLogger(__name__)


def mandar_emails(alertas):
    """Coloca na fila um e-mail para cada alerta marcado como "por e-mail"."""
    for alerta in alertas:
        if alerta.por_email:
            enfileirar(enviar_email, alerta.pk)


def resumo_por_tipo(alertas):
    """Quantos alertas de cada tipo foram criados, como {"Média abaixo de 6": 3}."""
    return dict(Counter(alerta.get_tipo_display() for alerta in alertas))


@shared_task
def rotina_diaria():
    """Recalcula o risco de evasão e gera os alertas do dia. Devolve o resumo por tipo."""
    try:
        total = evasao.calcular_riscos()
        logger.info("Risco de evasão recalculado para %s aluno(s).", total)
    except evasao.ModeloNaoTreinado as erro:
        # Sem modelo, as outras regras continuam valendo: só o alerta de evasão fica de fora.
        logger.warning("%s", erro)
    novos = regras.alertas_do_dia()
    mandar_emails(novos)
    logger.info("Rotina diária: %s alerta(s) novo(s).", len(novos))
    return resumo_por_tipo(novos)


@shared_task
def avisar_notas_publicadas(avaliacao_id):
    avaliacao = (
        Avaliacao.objects.select_related("oferta__disciplina").filter(pk=avaliacao_id).first()
    )
    if avaliacao is None:  # a avaliação foi apagada antes de a tarefa rodar
        return 0
    novos = regras.avisos_de_notas(avaliacao)
    mandar_emails(novos)
    return len(novos)


@shared_task
def avisar_justificativa_avaliada(justificativa_id):
    justificativa = (
        Justificativa.objects.select_related(
            "frequencia__matricula__aluno", "frequencia__aula__oferta__disciplina"
        )
        .filter(pk=justificativa_id)
        .first()
    )
    if justificativa is None:
        return 0
    novos = regras.aviso_de_justificativa(justificativa)
    mandar_emails(novos)
    return len(novos)


@shared_task(bind=True, max_retries=3)
def enviar_email(self, alerta_id):
    """Envia o alerta por e-mail. bind=True dá acesso a self, usado para tentar de novo."""
    alerta = Alerta.objects.select_related("destinatario").filter(pk=alerta_id).first()
    if alerta is None or alerta.email_enviado_em or not alerta.destinatario.email:
        return False  # alerta apagado, e-mail já enviado ou pessoa sem e-mail cadastrado

    corpo = f"Olá, {alerta.destinatario.first_name or alerta.destinatario.matricula}.\n\n{alerta.texto}\n"
    if alerta.link:
        corpo += f"\nAcesse o portal: {settings.ENDERECO_DO_SITE}{alerta.link}\n"
    corpo += "\nEste é um aviso automático do Instituto Socrático. Não responda este e-mail.\n"

    try:
        send_mail(
            subject=f"[Instituto Socrático] {alerta.titulo}",
            message=corpo,
            from_email=None,  # usa o DEFAULT_FROM_EMAIL
            recipient_list=[alerta.destinatario.email],
        )
    except OSError as erro:  # falhas de rede e do servidor de e-mail (smtplib) são OSError
        if self.request.is_eager:
            # Sem fila (CELERY_SEM_REDIS ou Redis fora do ar) não há como tentar mais tarde.
            logger.warning("E-mail do alerta %s não enviado: %s", alerta_id, erro)
            return False
        raise self.retry(exc=erro, countdown=60) from erro

    alerta.email_enviado_em = timezone.now()
    alerta.save(update_fields=["email_enviado_em"])
    return True
