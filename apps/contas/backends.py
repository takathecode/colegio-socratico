"""Backend de autenticação: o login padrão do Django com o bloqueio por senhas erradas.

Todo login passa por aqui: a tela do portal, o pedido de token da API e o Django Admin.
Por isso o bloqueio vale para os três sem repetir código.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from . import bloqueio


class LoginComBloqueio(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # A tela de login envia "username"; a API envia "matricula" (o USERNAME_FIELD).
        matricula = username if username is not None else kwargs.get(
            get_user_model().USERNAME_FIELD
        )
        if matricula is None or password is None:
            return None
        if bloqueio.minutos_restantes(matricula):
            return None  # bloqueada: nem confere a senha

        usuario = super().authenticate(request, username=matricula, password=password)
        if usuario is None:
            bloqueio.registrar_erro(matricula)  # senha errada, matrícula inexistente ou conta inativa
        else:
            bloqueio.limpar(matricula)
        return usuario
