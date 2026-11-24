"""Regras de senha forte e a senha provisória gerada pela Secretaria.

Os validadores abaixo entram no AUTH_PASSWORD_VALIDATORS do settings, junto com os do
Django. Assim valem em todo lugar que troca senha: "Esqueci minha senha", "Alterar minha
senha", a troca obrigatória depois da senha provisória e o Django Admin.
O JavaScript da tela (checklist ao vivo) só ajuda a pessoa; quem decide é o servidor.
"""

import re
import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

TAMANHO_MAXIMO = 128
CARACTERES_ESPECIAIS = "!@#$%&*?-_+=."


class ComplexidadeValidator:
    """Exige letra maiúscula, minúscula, número e caractere especial, e no máximo 128 caracteres."""

    REGRAS = (
        (r"[A-Z]", "pelo menos uma letra maiúscula"),
        (r"[a-z]", "pelo menos uma letra minúscula"),
        (r"[0-9]", "pelo menos um número"),
        (r"[^A-Za-z0-9]", "pelo menos um caractere especial (como ! @ # $ %)"),
    )

    def validate(self, password, user=None):
        erros = []
        if len(password) > TAMANHO_MAXIMO:
            erros.append(
                ValidationError(
                    f"A senha pode ter no máximo {TAMANHO_MAXIMO} caracteres.",
                    code="senha_longa",
                )
            )
        for padrao, texto in self.REGRAS:
            if not re.search(padrao, password):
                erros.append(ValidationError(f"A senha precisa ter {texto}.", code="senha_simples"))
        if erros:
            raise ValidationError(erros)

    def get_help_text(self):
        return "Use letras maiúsculas e minúsculas, números e um caractere especial."


class DadosPessoaisValidator:
    """Recusa a senha que contém a matrícula, o nome, o sobrenome ou o usuário do e-mail.

    O UserAttributeSimilarityValidator do Django recusa senhas *parecidas* com esses dados;
    este recusa a senha que os *contém* (ex.: "Aluno01!xyz" para a matrícula aluno01).
    Pedaços com menos de 3 letras não contam, para não recusar senhas por acaso.
    """

    def validate(self, password, user=None):
        if user is None:
            return
        senha = password.casefold()
        pedacos = [user.matricula, *user.first_name.split(), *user.last_name.split()]
        if user.email:
            # O usuário do e-mail, inteiro e dividido em pontos ("maria.souza" -> maria, souza).
            usuario_do_email = user.email.split("@")[0]
            pedacos += [usuario_do_email, *re.split(r"[._+-]", usuario_do_email)]
        for pedaco in pedacos:
            if pedaco and len(pedaco) >= 3 and pedaco.casefold() in senha:
                raise ValidationError(
                    "A senha não pode conter a sua matrícula, o seu nome nem parte do seu e-mail.",
                    code="senha_com_dados_pessoais",
                )

    def get_help_text(self):
        return "Não use a matrícula, o nome nem o e-mail na senha."


class DiferenteDaAtualValidator:
    """A senha nova não pode ser igual à atual.

    Os formulários de troca chamam a validação antes de gravar, então a senha "atual" do
    usuário ainda é a antiga neste momento.
    """

    def validate(self, password, user=None):
        if user is not None and user.pk and user.has_usable_password():
            if user.check_password(password):
                raise ValidationError(
                    "A senha nova precisa ser diferente da senha atual.", code="senha_repetida"
                )

    def get_help_text(self):
        return "A senha nova precisa ser diferente da atual."


# Sem letras e números parecidos (0/O, 1/l/I), para a senha ser ditada sem confusão.
MINUSCULAS = "abcdefghjkmnpqrstuvwxyz"
MAIUSCULAS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
NUMEROS = "23456789"
ESPECIAIS = "!@#$%&*?"


def gerar_senha_provisoria(usuario=None, tamanho=12):
    """Senha aleatória que já cumpre as regras de senha forte. Usa o módulo secrets.

    Garante um caractere de cada grupo e embaralha. Na rara chance de a senha sorteada não
    passar nos validadores (ex.: conter o nome da pessoa), sorteia de novo.
    """
    todos = MINUSCULAS + MAIUSCULAS + NUMEROS + ESPECIAIS
    gerador = secrets.SystemRandom()
    while True:
        caracteres = [secrets.choice(grupo) for grupo in (MINUSCULAS, MAIUSCULAS, NUMEROS, ESPECIAIS)]
        caracteres += [secrets.choice(todos) for _ in range(tamanho - len(caracteres))]
        gerador.shuffle(caracteres)
        senha = "".join(caracteres)
        try:
            validate_password(senha, usuario)
        except ValidationError:
            continue
        return senha
