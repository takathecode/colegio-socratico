"""Permissões da API: quais perfis podem chamar cada endpoint.

A API segue as mesmas regras das telas:
- PerfilDoPortal vale para todos os endpoints (está no REST_FRAMEWORK do settings).
  Aluno, professor e coordenador entram; ADMIN usa só o Django Admin, como nas áreas.
- Alguns endpoints pedem um perfil específico, com so_perfis(...). Ex.: o risco de evasão
  é só da coordenação.

Permissão diz se a pessoa pode usar o endpoint (senão: 403). Quais registros ela enxerga
dentro dele é outra regra, que fica em escopo.py (registro fora do escopo: 404).
"""

from rest_framework.permissions import BasePermission

from apps.contas.models import Usuario

ALUNO = Usuario.Perfil.ALUNO
PROFESSOR = Usuario.Perfil.PROFESSOR
COORDENADOR = Usuario.Perfil.COORDENADOR


def so_perfis(*perfis):
    """Cria uma permissão que só deixa passar os perfis informados.

    Exemplo: permission_classes = [so_perfis(COORDENADOR)]
    """

    class PerfilPermitido(BasePermission):
        message = "O seu perfil não tem acesso a este recurso da API."

        def has_permission(self, request, view):
            return getattr(request.user, "perfil", None) in perfis

    return PerfilPermitido


# Os três perfis que usam o portal. PerfilDoPortal é a permissão padrão de toda a API.
PERFIS_DO_PORTAL = (ALUNO, PROFESSOR, COORDENADOR)
PerfilDoPortal = so_perfis(*PERFIS_DO_PORTAL)
