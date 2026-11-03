from django import forms

from apps.academico.models import Frequencia, Justificativa
from apps.academico.utilidades import CLASSES_CAMPO, FORMATOS_ANEXO

from .servicos import faltas_sem_justificativa


class SelectDeFalta(forms.Select):
    """Lista de faltas. Cada opção guarda a disciplina, para o JavaScript filtrar as datas."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcao = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            opcao["attrs"]["data-oferta"] = value.instance.aula.oferta_id
        return opcao


class CampoDeFalta(forms.ModelChoiceField):
    def label_from_instance(self, falta):
        return f"{falta.aula.data:%d/%m/%Y}"


class JustificativaForm(forms.ModelForm):
    """Envio de justificativa.

    O aluno escolhe uma falta entre as dele: como a lista só tem as faltas da própria matrícula
    ainda sem justificativa, não dá para enviar o id da falta de outra pessoa nem repetir o pedido.
    """

    frequencia = CampoDeFalta(
        label="Data da ausência",
        queryset=Frequencia.objects.none(),  # definido no __init__, conforme o aluno
        empty_label=None,
        widget=SelectDeFalta(attrs={"class": CLASSES_CAMPO}),
    )
    motivo = forms.CharField(
        label="Motivo",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "class": CLASSES_CAMPO}),
    )

    class Meta:
        model = Justificativa
        fields = ["frequencia", "motivo", "anexo"]
        widgets = {"anexo": forms.FileInput(attrs={"class": "sr-only", "accept": FORMATOS_ANEXO})}

    def __init__(self, *args, matricula, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["frequencia"].queryset = faltas_sem_justificativa(matricula)
        self.fields["frequencia"].error_messages["invalid_choice"] = (
            "Escolha uma das suas faltas ainda sem justificativa."
        )
