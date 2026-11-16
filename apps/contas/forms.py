from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from . import bloqueio
from .foto import VALIDADORES_FOTO


class FormularioFoto(forms.Form):
    """Envio da foto de perfil. Só passa com a confirmação de que a pessoa leu as regras."""

    aceite = forms.BooleanField(
        error_messages={
            "required": "Confirme que leu as regras de uso da foto antes de enviar."
        }
    )
    foto = forms.FileField(
        validators=VALIDADORES_FOTO,
        error_messages={"required": "Escolha uma imagem para enviar."},
    )


class FormularioLogin(AuthenticationForm):
    """Login padrão do Django (matrícula e senha) com a opção "Manter conectado"."""

    manter_conectado = forms.BooleanField(required=False)

    # Minutos de bloqueio que faltam, mostrados na tela (0 = login não está bloqueado).
    minutos_de_bloqueio = 0

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            # O backend (backends.py) recusa a matrícula bloqueada mesmo com a senha certa.
            # Aqui a tela troca o "senha incorreta" pelo aviso do bloqueio.
            self.minutos_de_bloqueio = bloqueio.minutos_restantes(
                self.cleaned_data.get("username", "")
            )
            raise
