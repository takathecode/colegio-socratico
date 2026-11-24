"""Registro de auditoria das ações sensíveis sobre as contas (model RegistroDeAuditoria).

Uso nas views:
    auditoria.registrar(request, conta, RegistroDeAuditoria.Acao.DESBLOQUEIO)

Quem fez é o usuário logado (ou ninguém, nas telas públicas). Nunca passe senhas nem
códigos de link em "detalhe".
"""

import ipaddress

from django.conf import settings

from .models import RegistroDeAuditoria


def ip_de(request):
    """IP de quem fez o pedido.

    No computador, é o REMOTE_ADDR. Na Vercel (USAR_HTTPS=True) o pedido chega pelo proxy,
    e o IP da pessoa vem no cabeçalho X-Forwarded-For, que a própria Vercel preenche.
    Valor que não é um IP válido vira None.
    """
    if request is None:
        return None
    ip = request.META.get("REMOTE_ADDR", "")
    if settings.USAR_HTTPS:
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if encaminhado:
            ip = encaminhado.split(",")[0]
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def registrar(request, conta, acao, detalhe="", autor=None):
    """Grava o registro. autor: quem fez; sem ele, é o usuário logado (ou ninguém)."""
    if autor is None:
        autor = getattr(request, "user", None)
    return RegistroDeAuditoria.objects.create(
        autor=autor if autor is not None and autor.is_authenticated else None,
        conta=conta,
        acao=acao,
        detalhe=detalhe[:200],
        ip=ip_de(request),
    )
