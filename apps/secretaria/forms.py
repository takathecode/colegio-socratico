"""Formulários da Secretaria: criar contas e editar os dados de acesso.

Nenhum formulário tem os campos perfil, is_staff ou is_superuser: o perfil vem da tela
escolhida (aluno, professor ou coordenação) e nunca do que o navegador envia. Assim a
Secretaria não consegue criar nem transformar uma conta em administrador.
"""

from django import forms

from apps.academico.utilidades import CLASSES_CAMPO
from apps.contas.models import Usuario
from apps.contas.senhas import gerar_senha_provisoria

from . import servicos

TRATAMENTOS = [("Prof.", "Prof."), ("Profa.", "Profa.")]


class EstiloMixin:
    """Aplica a aparência padrão dos campos a todos os campos do formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", CLASSES_CAMPO)


class DadosDeAcessoForm(EstiloMixin, forms.ModelForm):
    """Nome e e-mail da conta. O e-mail é obrigatório: a recuperação de senha depende dele."""

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No modelo esses campos são opcionais (por causa do Admin); aqui são obrigatórios.
        for nome in ("first_name", "last_name", "email"):
            self.fields[nome].required = True
        self.fields["email"].help_text = "Para onde vão os links de nova senha. Confira com a pessoa."
        self.fields["email"].error_messages["invalid"] = "Digite um e-mail válido, como nome@exemplo.com."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # Dois usuários ativos com o mesmo e-mail receberiam os links um do outro.
        if servicos.email_em_uso(email, exceto=self.instance):
            raise forms.ValidationError("Este e-mail já está em uso por outra conta ativa.")
        return email


class EdicaoProfessorForm(DadosDeAcessoForm):
    tratamento = forms.ChoiceField(label="Tratamento", choices=TRATAMENTOS)

    class Meta(DadosDeAcessoForm.Meta):
        fields = ["tratamento", "first_name", "last_name", "email"]


class EdicaoCoordenadorForm(DadosDeAcessoForm):
    tratamento = forms.ChoiceField(
        label="Tratamento", choices=[("", "Nenhum"), *TRATAMENTOS], required=False
    )

    class Meta(DadosDeAcessoForm.Meta):
        fields = ["tratamento", "first_name", "last_name", "email"]


class NovaContaMixin:
    """Criação de conta: matrícula, senha provisória e troca obrigatória no primeiro login.

    A senha provisória (self.senha_provisoria) é mostrada uma única vez, para ser entregue
    pessoalmente. O banco guarda só o hash dela. Não existe tela de cadastro aberto.
    """

    perfil = None  # definido nas subclasses

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.senha_provisoria = None

    def clean_matricula(self):
        return self.cleaned_data["matricula"].strip()

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.perfil = self.perfil
        self.senha_provisoria = gerar_senha_provisoria(usuario)
        usuario.set_password(self.senha_provisoria)
        usuario.precisa_trocar_senha = True
        if commit:
            usuario.save()
        return usuario


def meta_de_criacao(base):
    """Meta da criação: a mesma da edição, com a matrícula na frente."""

    class Meta(base.Meta):
        fields = ["matricula", *base.Meta.fields]
        labels = {**base.Meta.labels, "matricula": "Matrícula (usada no login)"}
        error_messages = {"matricula": {"unique": "Já existe uma conta com esta matrícula."}}

    return Meta


class NovoAlunoForm(NovaContaMixin, DadosDeAcessoForm):
    """Só a conta. A matrícula na turma é feita pela coordenação (cadastro acadêmico)."""

    perfil = Usuario.Perfil.ALUNO
    Meta = meta_de_criacao(DadosDeAcessoForm)


class NovoProfessorForm(NovaContaMixin, EdicaoProfessorForm):
    perfil = Usuario.Perfil.PROFESSOR
    Meta = meta_de_criacao(EdicaoProfessorForm)


class NovoCoordenadorForm(NovaContaMixin, EdicaoCoordenadorForm):
    perfil = Usuario.Perfil.COORDENADOR
    Meta = meta_de_criacao(EdicaoCoordenadorForm)


# Formulário de edição de cada perfil.
EDICAO_DO_PERFIL = {
    Usuario.Perfil.ALUNO: DadosDeAcessoForm,
    Usuario.Perfil.PROFESSOR: EdicaoProfessorForm,
    Usuario.Perfil.COORDENADOR: EdicaoCoordenadorForm,
}
