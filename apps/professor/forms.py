from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from apps.academico.models import VALIDADORES_NOTA, Avaliacao, Justificativa
from apps.academico.utilidades import CLASSES_CAMPO

# Campo de nota pequeno, para caber na tabela.
CLASSES_NOTA = (
    "h-10 w-24 rounded-lg border border-[#E5E9F0] bg-white px-3 text-center text-sm outline-none "
    "focus:border-[#1F4E8C] focus:ring-2 focus:ring-[#1F4E8C]/30 "
    "aria-[invalid=true]:border-[#C62828] aria-[invalid=true]:bg-red-50"
)


class NotasForm(forms.Form):
    """Um campo de nota para cada aluno ativo da turma.

    Os campos são criados no __init__, porque a quantidade depende da turma.
    O nome de cada campo é "nota_<id da matrícula>". Campo vazio significa "sem nota".
    """

    def __init__(self, *args, matriculas, notas_atuais, **kwargs):
        super().__init__(*args, **kwargs)
        self.matriculas = matriculas
        for matricula in matriculas:
            self.fields[f"nota_{matricula.pk}"] = forms.DecimalField(
                label=matricula.aluno.get_full_name() or matricula.aluno.matricula,
                required=False,
                max_digits=4,
                decimal_places=2,
                validators=VALIDADORES_NOTA,
                localize=True,  # aceita "7,5", com vírgula, como se escreve no Brasil
                initial=notas_atuais.get(matricula.pk),
                widget=forms.TextInput(attrs={"class": CLASSES_NOTA, "inputmode": "decimal"}),
                error_messages={
                    "invalid": "Digite um número, como 7,5.",
                    "max_value": "A nota vai de 0 a 10.",
                    "min_value": "A nota vai de 0 a 10.",
                },
            )

    def campo_de(self, matricula):
        return self[f"nota_{matricula.pk}"]

    def valores(self):
        """{matricula_id: nota ou None}, depois de validado."""
        return {m.pk: self.cleaned_data[f"nota_{m.pk}"] for m in self.matriculas}


class NovaAvaliacaoForm(forms.ModelForm):
    """Cria uma prova ou entrega na disciplina. Ela aparece no calendário do aluno."""

    class Meta:
        model = Avaliacao
        fields = ["nome", "tipo", "data_hora", "local"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": CLASSES_CAMPO, "placeholder": "Ex.: A3"}),
            "tipo": forms.Select(attrs={"class": CLASSES_CAMPO}),
            "data_hora": forms.DateTimeInput(
                attrs={"class": CLASSES_CAMPO, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "local": forms.TextInput(
                attrs={"class": CLASSES_CAMPO, "placeholder": "Ex.: Sala B204 (opcional)"}
            ),
        }

    def __init__(self, *args, oferta, **kwargs):
        super().__init__(*args, **kwargs)
        self.oferta = oferta

    def clean_nome(self):
        # A regra "nome único na disciplina" usa a oferta, que não é um campo do formulário,
        # então o Django não a confere sozinho. Conferimos aqui para mostrar um erro amigável.
        nome = self.cleaned_data["nome"].strip()
        if Avaliacao.objects.filter(oferta=self.oferta, nome__iexact=nome).exists():
            raise forms.ValidationError("Já existe uma avaliação com este nome nesta disciplina.")
        return nome

    def save(self, commit=True):
        self.instance.oferta = self.oferta
        return super().save(commit)


class ChamadaForm(forms.Form):
    """Dados da aula. As presenças de cada aluno são lidas à parte, na view."""

    # O nome não pode ser só "data": form.data já é usado pelo Django para os dados enviados.
    data_aula = forms.DateField(label="Data da aula", widget=forms.HiddenInput)
    horas_aula = forms.IntegerField(
        label="Horas-aula",
        initial=2,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        widget=forms.NumberInput(attrs={"class": CLASSES_CAMPO, "min": 1, "max": 6}),
    )
    conteudo = forms.CharField(
        label="Conteúdo da aula",
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": CLASSES_CAMPO, "placeholder": "Ex.: Revisão para a A3 (opcional)"}
        ),
    )

    def clean_data_aula(self):
        data = self.cleaned_data["data_aula"]
        if data > timezone.localdate():
            raise forms.ValidationError("Não é possível fazer a chamada de uma aula futura.")
        return data


class AvaliarJustificativaForm(forms.Form):
    decisao = forms.ChoiceField(
        label="Decisão",
        choices=[
            (Justificativa.Status.APROVADA, "Aprovar"),
            (Justificativa.Status.REJEITADA, "Rejeitar"),
        ],
        # "peer sr-only" esconde a bolinha do rádio; o template desenha um botão no lugar.
        widget=forms.RadioSelect(attrs={"class": "peer sr-only"}),
        error_messages={"required": "Escolha aprovar ou rejeitar."},
    )
    resposta = forms.CharField(
        label="Resposta ao aluno",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "class": CLASSES_CAMPO}),
    )

    def clean(self):
        dados = super().clean()
        if dados.get("decisao") == Justificativa.Status.REJEITADA and not dados.get(
            "resposta", ""
        ).strip():
            self.add_error("resposta", "Explique ao aluno o motivo da rejeição.")
        return dados
