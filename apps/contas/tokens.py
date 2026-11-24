"""Código (token) do link de "Esqueci minha senha".

Usa o gerador do próprio Django (PasswordResetTokenGenerator): o código é uma assinatura
feita com a SECRET_KEY sobre dados da conta, e nada é guardado no banco. O link deixa de
valer quando qualquer um desses dados muda:

- a senha (hash): o link funciona uma vez só, porque usá-lo troca a senha;
- o último login: entrar com a senha antiga também invalida o link;
- o e-mail: trocar o e-mail da conta invalida os links mandados para o endereço antigo;
- o último pedido de link (ultimo_pedido_reset): pedir um link novo invalida o anterior.
  Este é o único dado que acrescentamos ao padrão do Django.

O prazo é o PASSWORD_RESET_TIMEOUT do settings (10 minutos), contado a partir do pedido.
"""

from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils import timezone


class GeradorDeLinkDeSenha(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        pedido = user.ultimo_pedido_reset
        # Em UTC e com os microssegundos: dois pedidos no mesmo segundo geram links diferentes.
        pedido = "" if pedido is None else pedido.astimezone(dt_timezone.utc).isoformat()
        return super()._make_hash_value(user, timestamp) + pedido

    def check_token(self, user, token):
        """Além das regras do Django, o prazo conta do momento do pedido.

        O e-mail pode sair pela fila do Celery alguns segundos depois do pedido. Contando
        do pedido, o horário "válido até" mostrado na tela é exatamente o que vale.
        """
        if not super().check_token(user, token):
            return False
        return user.ultimo_pedido_reset is not None and timezone.now() <= validade_do_link(user)


def validade_do_link(usuario):
    """Até quando o último link pedido vale (None se a conta nunca pediu um link)."""
    if usuario.ultimo_pedido_reset is None:
        return None
    return usuario.ultimo_pedido_reset + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)


gerador_de_link = GeradorDeLinkDeSenha()
