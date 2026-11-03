from django import forms
from django.contrib.auth.forms import AuthenticationForm


class FormularioLogin(AuthenticationForm):
    """Login padrão do Django (matrícula e senha) com a opção "Manter conectado"."""

    manter_conectado = forms.BooleanField(required=False)
