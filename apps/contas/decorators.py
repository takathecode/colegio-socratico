"""Controle de acesso às áreas do sistema."""

from functools import wraps

from django.core.exceptions import PermissionDenied


def perfil_requerido(*perfis):
    """Só deixa entrar quem tem um dos perfis informados. Os demais recebem a página 403.

    Exemplo:
        @login_required
        @perfil_requerido("ALUNO")
        def painel(request): ...

    O @login_required vem antes para mandar ao login quem ainda não entrou. Se ele for
    esquecido, o acesso continua bloqueado, pois o visitante anônimo não tem perfil.
    """

    def decorador(view):
        @wraps(view)
        def view_protegida(request, *args, **kwargs):
            if getattr(request.user, "perfil", None) not in perfis:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return view_protegida

    return decorador
