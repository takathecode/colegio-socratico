"""Regras do "Esqueci minha senha" pela matrícula.

1. A pessoa digita a matrícula. Se a conta existe, está ativa e tem e-mail, a tela mostra o
   e-mail mascarado; senão, uma mensagem neutra (a mesma para os três casos).
2. Ao confirmar, o sistema grava o momento do pedido (o que invalida o link anterior) e
   manda o link para o e-mail cadastrado na conta, pela fila do Celery.

Limites por hora, contra quem tenta descobrir matrículas ou lotar a caixa de alguém:
- 5 links por matrícula e 10 links por IP;
- 30 consultas de matrícula por IP.
Os pedidos ficam no banco (model PedidoDeSenha), pelo mesmo motivo do bloqueio de login.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.alertas.fila import enfileirar

from . import auditoria
from .models import PedidoDeSenha, RegistroDeAuditoria

JANELA = timedelta(hours=1)
LINKS_POR_MATRICULA = 5
LINKS_POR_IP = 10
CONSULTAS_POR_IP = 30
# Pedidos mais antigos que isto são apagados, para a tabela não crescer para sempre.
GUARDAR_POR = timedelta(days=1)


def conta_para_redefinir(matricula):
    """A conta que pode receber o link, ou None (inexistente, desativada ou sem e-mail)."""
    matricula = (matricula or "").strip()
    if not matricula:
        return None
    conta = get_user_model().objects.filter(matricula=matricula, is_active=True).first()
    if conta is None or not conta.email:
        return None
    return conta


def _pedidos_recentes(tipo, **filtro):
    return PedidoDeSenha.objects.filter(
        tipo=tipo, criado_em__gte=timezone.now() - JANELA, **filtro
    ).count()


def pode_consultar(request):
    """False se este IP já consultou matrículas demais na última hora."""
    ip = auditoria.ip_de(request)
    return ip is None or _pedidos_recentes(PedidoDeSenha.Tipo.CONSULTA, ip=ip) < CONSULTAS_POR_IP


def registrar_consulta(request, matricula):
    PedidoDeSenha.objects.create(
        tipo=PedidoDeSenha.Tipo.CONSULTA,
        matricula=matricula[:150],
        ip=auditoria.ip_de(request),
    )


def pode_enviar(request, matricula):
    """False se a matrícula ou o IP já pediram links demais na última hora."""
    ip = auditoria.ip_de(request)
    if _pedidos_recentes(PedidoDeSenha.Tipo.ENVIO, matricula=matricula) >= LINKS_POR_MATRICULA:
        return False
    return ip is None or _pedidos_recentes(PedidoDeSenha.Tipo.ENVIO, ip=ip) < LINKS_POR_IP


def enviar_link(request, conta):
    """Grava o pedido e coloca o e-mail na fila. Devolve até quando o link vale.

    Usado pela tela pública e pelo botão "Enviar link de redefinição" da Secretaria.
    """
    # Importado aqui: tasks.py importa este módulo indiretamente pelo Celery.
    from .tasks import enviar_link_de_senha
    from .tokens import validade_do_link

    agora = timezone.now()
    PedidoDeSenha.objects.filter(criado_em__lt=agora - GUARDAR_POR).delete()
    PedidoDeSenha.objects.create(
        tipo=PedidoDeSenha.Tipo.ENVIO, matricula=conta.matricula, ip=auditoria.ip_de(request)
    )
    conta.ultimo_pedido_reset = agora
    conta.save(update_fields=["ultimo_pedido_reset"])
    auditoria.registrar(request, conta, RegistroDeAuditoria.Acao.LINK_ENVIADO)
    # O worker só recebe o número da conta: o código do link é criado lá e nunca passa
    # pelo Redis nem pelo log.
    enfileirar(enviar_link_de_senha, conta.pk)
    return validade_do_link(conta)
