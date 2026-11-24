"""E-mails de acesso, enviados pela fila do Celery (ou na hora, sem Redis: apps/alertas/fila.py).

- enviar_link_de_senha: link de "Esqueci minha senha" (ou o enviado pela Secretaria).
- avisar_senha_alterada: aviso de que a senha mudou, para a pessoa notar uma troca que não fez.
- avisar_troca_de_email: aviso ao e-mail ANTIGO de que o e-mail da conta foi trocado.

As tarefas recebem só números e textos simples. O código do link é criado aqui, no
worker, e por isso nunca fica guardado no Redis.
"""

import logging
from datetime import datetime

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .envio_de_email import entrega_de_verdade
from .tokens import gerador_de_link, validade_do_link

logger = logging.getLogger(__name__)


def enviar(tarefa, assunto, modelo, contexto, para):
    """Monta o e-mail em texto e em HTML (templates contas/email/<modelo>.txt e .html)."""
    contexto = {"site": settings.SITE_URL, **contexto}
    mensagem = EmailMultiAlternatives(
        subject=f"[Instituto Socrático] {assunto}",
        body=render_to_string(f"contas/email/{modelo}.txt", contexto),
        to=[para],
    )
    mensagem.attach_alternative(render_to_string(f"contas/email/{modelo}.html", contexto), "text/html")
    if not entrega_de_verdade() and not settings.DEBUG:
        # No servidor publicado sem SMTP, deixa claro no log que ninguém vai receber.
        logger.warning("E-mail '%s' não será entregue: falta configurar o SMTP.", assunto)
    try:
        mensagem.send()
    except OSError as erro:  # falhas de rede e do servidor de e-mail (smtplib) são OSError
        if tarefa.request.is_eager:
            # Sem fila não há como tentar mais tarde: fica registrado no log.
            logger.warning("E-mail '%s' não enviado: %s", assunto, erro)
            return False
        raise tarefa.retry(exc=erro, countdown=30) from erro
    return True


def nome_de(usuario):
    return usuario.first_name or usuario.matricula


@shared_task(bind=True, max_retries=2)
def enviar_link_de_senha(self, usuario_id):
    usuario = get_user_model().objects.filter(pk=usuario_id, is_active=True).first()
    if usuario is None or not usuario.email or usuario.ultimo_pedido_reset is None:
        return False
    validade = validade_do_link(usuario)
    if timezone.now() > validade:
        return False  # a fila atrasou mais que o prazo: o link já chegaria vencido

    # O endereço vem do SITE_URL (settings), nunca do cabeçalho Host do pedido: assim ninguém
    # consegue fazer o e-mail apontar para outro site (host header poisoning).
    caminho = reverse(
        "contas:senha_redefinir",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(usuario.pk)),
            "token": gerador_de_link.make_token(usuario),
        },
    )
    contexto = {
        "nome": nome_de(usuario),
        "matricula": usuario.matricula,
        "link": f"{settings.SITE_URL}{caminho}",
        "valido_ate": timezone.localtime(validade),
        "minutos": settings.PASSWORD_RESET_TIMEOUT // 60,
    }
    return enviar(self, "Criar nova senha", "link_de_senha", contexto, usuario.email)


@shared_task(bind=True, max_retries=3)
def avisar_senha_alterada(self, usuario_id, quando):
    """quando: data e hora da troca, em texto ISO (as tarefas só recebem dados simples)."""
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    if usuario is None or not usuario.email:
        return False
    contexto = {"nome": nome_de(usuario), "quando": timezone.localtime(datetime.fromisoformat(quando))}
    return enviar(self, "Sua senha foi alterada", "senha_alterada", contexto, usuario.email)


@shared_task(bind=True, max_retries=3)
def avisar_troca_de_email(self, usuario_id, email_antigo, quando):
    usuario = get_user_model().objects.filter(pk=usuario_id).first()
    if usuario is None or not email_antigo:
        return False
    contexto = {
        "nome": nome_de(usuario),
        "matricula": usuario.matricula,
        "quando": timezone.localtime(datetime.fromisoformat(quando)),
    }
    return enviar(self, "O e-mail da sua conta foi trocado", "email_trocado", contexto, email_antigo)
