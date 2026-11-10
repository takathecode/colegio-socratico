"""Bloqueio do login depois de muitas senhas erradas seguidas.

Regra: 5 erros seguidos na mesma matrícula bloqueiam o login dela por 15 minutos, mesmo
com a senha certa. Isso impede alguém de testar milhares de senhas. Os erros ficam no
banco (model BloqueioDeLogin), e não na memória, porque na Vercel cada pedido pode cair
em uma cópia diferente do sistema.

O bloqueio acaba sozinho depois dos 15 minutos, ou antes, se a senha for trocada
("Esqueci minha senha" ou senha provisória da coordenação) ou se o administrador apagar
o registro no Django Admin.
"""

import math
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import BloqueioDeLogin

ERROS_PARA_BLOQUEAR = 5
TEMPO_DE_BLOQUEIO = timedelta(minutes=15)
# Erros mais antigos que isto não contam: quem erra uma vez por semana nunca é bloqueado.
JANELA_DOS_ERROS = timedelta(minutes=15)

TAMANHO_MAXIMO = BloqueioDeLogin._meta.get_field("matricula").max_length


def normalizar(matricula):
    return str(matricula).strip()[:TAMANHO_MAXIMO]


def minutos_restantes(matricula):
    """Quantos minutos faltam para o login da matrícula voltar a funcionar (0 = livre)."""
    registro = BloqueioDeLogin.objects.filter(matricula=normalizar(matricula)).first()
    if registro is None or registro.bloqueado_ate is None:
        return 0
    faltam = (registro.bloqueado_ate - timezone.now()).total_seconds()
    return math.ceil(faltam / 60) if faltam > 0 else 0


@transaction.atomic
def registrar_erro(matricula):
    """Conta mais um erro. No quinto erro seguido, bloqueia e zera a contagem."""
    agora = timezone.now()
    # select_for_update trava a linha até o fim da transação: dois erros ao mesmo tempo
    # não se perdem na contagem.
    registro, _ = BloqueioDeLogin.objects.select_for_update().get_or_create(
        matricula=normalizar(matricula)
    )
    if registro.ultimo_erro_em and agora - registro.ultimo_erro_em > JANELA_DOS_ERROS:
        registro.erros = 0
    registro.erros += 1
    registro.ultimo_erro_em = agora
    if registro.erros >= ERROS_PARA_BLOQUEAR:
        registro.bloqueado_ate = agora + TEMPO_DE_BLOQUEIO
        registro.erros = 0
    registro.save()


def limpar(matricula):
    """Login certo: os erros anteriores deixam de contar."""
    BloqueioDeLogin.objects.filter(matricula=normalizar(matricula)).delete()
