from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
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


class FormularioMatricula(forms.Form):
    """Primeira etapa do "Esqueci minha senha": só a matrícula."""

    matricula = forms.CharField(
        label="Matrícula",
        max_length=150,
        error_messages={"required": "Digite a sua matrícula."},
    )

    def clean_matricula(self):
        return self.cleaned_data["matricula"].strip()


class SenhaNovaMixin:
    """Rótulos em português e a limpeza da troca obrigatória ao salvar a senha nova."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Nova senha"
        self.fields["new_password2"].label = "Confirmar nova senha"
        self.fields["new_password1"].help_text = ""

    def save(self, commit=True):
        # A senha nova (sempre só o hash, pelo set_password) encerra a troca obrigatória.
        self.user.precisa_trocar_senha = False
        return super().save(commit=commit)


class FormularioNovaSenha(SenhaNovaMixin, SetPasswordForm):
    """Senha nova pelo link do e-mail.

    Não existe campo de matrícula: a tela só mostra a matrícula da conta do link. Mesmo que
    alguém envie uma "matricula" no POST, ela é ignorada; a conta é sempre a do link.
    """


class FormularioTrocaDeSenha(SenhaNovaMixin, PasswordChangeForm):
    """"Alterar minha senha" (logado) e a troca obrigatória depois da senha provisória."""

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_incorrect": "A senha atual está incorreta. Digite-a novamente.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        provisoria = self.user.precisa_trocar_senha
        self.fields["old_password"].label = "Senha provisória" if provisoria else "Senha atual"
