"""Regras da área da Secretaria: quais contas ela administra.

Princípio do menor privilégio: a Secretaria cuida só dos acessos (dados de login, senha,
bloqueio e situação da conta). Ela não vê notas, frequência, riscos nem relatórios.

Ela administra contas de aluno, professor e coordenação. Ficam de fora, e só o Django
Admin altera: contas ADMIN, de superusuário ou de equipe (staff) e outras contas da
Secretaria. Com isso, ninguém da Secretaria consegue tomar uma conta mais poderosa que a
sua (escalada de privilégio), nem trocar a senha de um colega para entrar no lugar dele.
A regra fica na consulta: uma conta fora dela responde 404 em todas as ações.
"""

from django.db.models import Q
from django.utils import timezone

from apps.contas.models import BloqueioDeLogin, Usuario

PERFIS_GERENCIAVEIS = (
    Usuario.Perfil.ALUNO,
    Usuario.Perfil.PROFESSOR,
    Usuario.Perfil.COORDENADOR,
)


def contas_gerenciaveis():
    return Usuario.objects.filter(
        perfil__in=PERFIS_GERENCIAVEIS, is_staff=False, is_superuser=False
    )


def matriculas_bloqueadas():
    """Matrículas com o login bloqueado agora (5 senhas erradas seguidas)."""
    return set(
        BloqueioDeLogin.objects.filter(bloqueado_ate__gt=timezone.now()).values_list(
            "matricula", flat=True
        )
    )


def filtrar_por_busca(contas, busca):
    """Nome, sobrenome ou matrícula que contêm o texto buscado (no banco)."""
    busca = busca.strip()
    if not busca:
        return contas
    filtro = Q(matricula__icontains=busca)
    for palavra in busca.split():
        filtro |= Q(first_name__icontains=palavra) | Q(last_name__icontains=palavra)
    return contas.filter(filtro)


def email_em_uso(email, exceto=None):
    """True se outra conta ATIVA já usa este e-mail (sem diferenciar maiúsculas).

    Contas desativadas não contam: o e-mail de quem saiu da escola pode ser reaproveitado.
    """
    contas = Usuario.objects.filter(email__iexact=email, is_active=True)
    if exceto is not None and exceto.pk:
        contas = contas.exclude(pk=exceto.pk)
    return contas.exists()
