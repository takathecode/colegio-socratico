"""Formulários da coordenação: matrícula do aluno, turmas, disciplinas e ofertas.

As contas (criar, editar nome e e-mail, senha, desativar) são da Secretaria (apps/secretaria).
"""

from django import forms

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


# --- Matrícula do aluno ---


class MatriculaDoAlunoForm(EstiloMixin, forms.Form):
    """Turma e situação da matrícula do aluno (cadastro acadêmico).

    A conta do aluno (nome, e-mail, senha) é da Secretaria; aqui só a parte acadêmica.
    Aluno sem matrícula (conta recém-criada pela Secretaria) é matriculado na turma escolhida.
    A turma só pode mudar enquanto a matrícula não tem notas nem presenças; depois disso,
    trocar a turma deixaria notas ligadas a disciplinas que o aluno não cursa mais.
    """

    turma = forms.ModelChoiceField(
        label="Turma",
        queryset=Turma.objects.select_related("curso").order_by("-semestre", "codigo"),
        empty_label="Escolha a turma",
    )
    situacao = forms.ChoiceField(label="Situação da matrícula", choices=Matricula.Situacao.choices)

    def __init__(self, *args, aluno, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno
        self.fields["turma"].label_from_instance = (
            lambda turma: f"{turma.codigo} · {turma.semestre} · {turma.curso.nome}"
        )
        self.matricula_atual = servicos.ultima_matricula(aluno)
        if self.matricula_atual is None:
            # Aluno sem matrícula: a matrícula começa ativa.
            del self.fields["situacao"]
            return
        self.fields["turma"].initial = self.matricula_atual.turma
        self.fields["situacao"].initial = self.matricula_atual.situacao
        if servicos.tem_historico(self.matricula_atual):
            self.fields["turma"].disabled = True
            self.fields["turma"].help_text = (
                "O aluno já tem notas ou presenças nesta turma, então ela não pode mudar."
            )

    def save(self):
        turma = self.cleaned_data["turma"]
        if self.matricula_atual is None:
            return Matricula.objects.create(aluno=self.aluno, turma=turma)
        self.matricula_atual.turma = turma
        self.matricula_atual.situacao = self.cleaned_data["situacao"]
        self.matricula_atual.save(update_fields=["turma", "situacao"])
        return self.matricula_atual


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
