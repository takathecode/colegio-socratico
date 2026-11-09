"""Formulários da coordenação: contas (aluno, professor, coordenador), turmas, disciplinas e ofertas."""

from django import forms
from django.db import transaction

from apps.academico.models import Disciplina, Matricula, Oferta, Turma
from apps.academico.utilidades import CLASSES_CAMPO
from apps.contas.models import Usuario

from . import servicos


class EstiloMixin:
    """Aplica a aparência padrão dos campos a todos os campos do formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", CLASSES_CAMPO)


# --- Contas ---


class ContaForm(EstiloMixin, forms.ModelForm):
    """Base dos formulários de conta. Cada subclasse define o perfil da conta.

    Ao criar uma conta, o sistema gera uma senha provisória (self.senha_provisoria),
    que a coordenação entrega ao usuário. Não existe tela de cadastro aberto.
    """

    perfil = None  # definido nas subclasses

    class Meta:
        model = Usuario
        fields = ["matricula", "first_name", "last_name", "email"]
        labels = {"first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail"}
        error_messages = {"matricula": {"unique": "Já existe uma conta com esta matrícula."}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No modelo esses campos são opcionais (por causa do Admin); aqui são obrigatórios.
        for nome in ("first_name", "last_name", "email"):
            self.fields[nome].required = True
        self.fields["email"].help_text = "Usado para redefinir a senha."
        self.senha_provisoria = None

    def clean_matricula(self):
        return self.cleaned_data["matricula"].strip()

    def clean_email(self):
        # Dois usuários com o mesmo e-mail receberiam o link de redefinição um do outro.
        email = self.cleaned_data["email"].strip().lower()
        repetido = Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Este e-mail já está em uso por outra conta.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.perfil = self.perfil
        if usuario.pk is None:
            self.senha_provisoria = servicos.gerar_senha_provisoria()
            usuario.set_password(self.senha_provisoria)  # no banco fica só o hash
        if commit:
            usuario.save()
        return usuario


TRATAMENTOS = [("Prof.", "Prof."), ("Profa.", "Profa.")]


class ProfessorForm(ContaForm):
    perfil = Usuario.Perfil.PROFESSOR
    tratamento = forms.ChoiceField(label="Tratamento", choices=TRATAMENTOS)

    class Meta(ContaForm.Meta):
        fields = ["matricula", "tratamento", "first_name", "last_name", "email"]


class CoordenadorForm(ContaForm):
    perfil = Usuario.Perfil.COORDENADOR
    tratamento = forms.ChoiceField(
        label="Tratamento", choices=[("", "Nenhum"), *TRATAMENTOS], required=False
    )

    class Meta(ContaForm.Meta):
        fields = ["matricula", "tratamento", "first_name", "last_name", "email"]


class AlunoForm(ContaForm):
    """Conta do aluno e a sua matrícula na turma, salvas juntas.

    A turma só pode mudar enquanto a matrícula não tem notas nem presenças; depois disso,
    trocar a turma deixaria notas ligadas a disciplinas que o aluno não cursa mais.
    """

    perfil = Usuario.Perfil.ALUNO
    turma = forms.ModelChoiceField(
        label="Turma",
        queryset=Turma.objects.select_related("curso").order_by("-semestre", "codigo"),
        empty_label="Escolha a turma",
    )
    situacao = forms.ChoiceField(label="Situação da matrícula", choices=Matricula.Situacao.choices)

    class Meta(ContaForm.Meta):
        labels = {**ContaForm.Meta.labels, "matricula": "RA (matrícula)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["turma"].label_from_instance = (
            lambda turma: f"{turma.codigo} · {turma.semestre} · {turma.curso.nome}"
        )
        self.matricula_atual = (
            servicos.ultima_matricula(self.instance) if self.instance.pk else None
        )
        if self.matricula_atual is None:
            # Aluno novo (ou sem matrícula): a matrícula começa ativa.
            del self.fields["situacao"]
            return
        self.fields["turma"].initial = self.matricula_atual.turma
        self.fields["situacao"].initial = self.matricula_atual.situacao
        if servicos.tem_historico(self.matricula_atual):
            self.fields["turma"].disabled = True
            self.fields["turma"].help_text = (
                "O aluno já tem notas ou presenças nesta turma, então ela não pode mudar."
            )

    def save(self, commit=True):
        # transaction.atomic: a conta e a matrícula são salvas juntas, ou nenhuma das duas.
        with transaction.atomic():
            usuario = super().save(commit=True)
            turma = self.cleaned_data["turma"]
            if self.matricula_atual is None:
                Matricula.objects.create(aluno=usuario, turma=turma)
            else:
                self.matricula_atual.turma = turma
                self.matricula_atual.situacao = self.cleaned_data["situacao"]
                self.matricula_atual.save(update_fields=["turma", "situacao"])
        return usuario


# Formulário usado na edição de cada perfil.
FORM_DO_PERFIL = {
    Usuario.Perfil.ALUNO: AlunoForm,
    Usuario.Perfil.PROFESSOR: ProfessorForm,
    Usuario.Perfil.COORDENADOR: CoordenadorForm,
}


# --- Turmas, disciplinas e ofertas ---


class MudancaDeCursoMixin:
    """Impede trocar o curso de algo que já está em uso.

    Uma oferta precisa ligar turma e disciplina do mesmo curso. Trocar o curso de uma
    turma (ou disciplina) que já tem ofertas quebraria essa regra.
    """

    def clean_curso(self):
        curso = self.cleaned_data["curso"]
        if self.instance.pk and curso.pk != self.instance.curso_id:
            if self.instance.ofertas.exists():
                raise forms.ValidationError(
                    "Não é possível trocar o curso: já existem disciplinas oferecidas aqui."
                )
        return curso


class TurmaForm(MudancaDeCursoMixin, EstiloMixin, forms.ModelForm):
    class Meta:
        model = Turma
        fields = ["curso", "codigo", "semestre", "periodo"]
        widgets = {
            "codigo": forms.TextInput(attrs={"placeholder": "Ex.: CC-6A"}),
            "semestre": forms.TextInput(attrs={"placeholder": "Ex.: 2026.2"}),
        }

    def clean_curso(self):
        curso = super().clean_curso()
        if self.instance.pk and curso.pk != self.instance.curso_id:
            if self.instance.matriculas.exists():
                raise forms.ValidationError(
                    "Não é possível trocar o curso: a turma já tem alunos matriculados."
                )
        return curso

    def clean(self):
        dados = super().clean()
        codigo, semestre = dados.get("codigo"), dados.get("semestre")
        # Confere aqui a regra "código único no semestre", para dar uma mensagem clara.
        if codigo and semestre:
            repetida = Turma.objects.filter(codigo__iexact=codigo, semestre=semestre)
            if repetida.exclude(pk=self.instance.pk).exists():
                self.add_error("codigo", f"Já existe a turma {codigo} no semestre {semestre}.")
        return dados


class DisciplinaForm(MudancaDeCursoMixin, EstiloMixin, forms.ModelForm):
    class Meta:
        model = Disciplina
        fields = ["curso", "codigo", "nome", "creditos", "carga_horaria"]
        widgets = {"codigo": forms.TextInput(attrs={"placeholder": "Ex.: MAT204"})}
        error_messages = {"codigo": {"unique": "Já existe uma disciplina com este código."}}


class OfertaForm(EstiloMixin, forms.ModelForm):
    """Liga uma disciplina a uma turma, com o professor que vai lecioná-la.

    Na edição, só o professor muda; para trocar a disciplina, remova a oferta e crie outra.
    """

    class Meta:
        model = Oferta
        fields = ["disciplina", "professor"]

    def __init__(self, *args, turma, **kwargs):
        kwargs.setdefault("instance", Oferta(turma=turma))
        super().__init__(*args, **kwargs)
        self.fields["professor"].queryset = Usuario.objects.filter(
            perfil=Usuario.Perfil.PROFESSOR, is_active=True
        ).order_by("first_name", "last_name")
        self.fields["professor"].label_from_instance = lambda professor: (
            professor.nome_com_tratamento or professor.matricula
        )
        self.fields["professor"].empty_label = "Escolha o professor"

        if self.instance.pk:
            del self.fields["disciplina"]
            return
        # Só as disciplinas do curso da turma que ainda não são oferecidas nela.
        self.fields["disciplina"].queryset = Disciplina.objects.filter(
            curso_id=turma.curso_id
        ).exclude(ofertas__turma=turma)
        self.fields["disciplina"].empty_label = "Escolha a disciplina"
