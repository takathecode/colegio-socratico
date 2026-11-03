from django import forms
from django.db.models import Q

from apps.academico.models import Matricula, Oferta
from apps.academico.utilidades import CLASSES_CAMPO, FORMATOS_ANEXO
from apps.contas.models import Usuario

from .models import Conversa, Mensagem, nome_de_exibicao


def secretaria():
    """A conta que recebe as mensagens da secretaria: o primeiro coordenador ativo."""
    return (
        Usuario.objects.filter(perfil=Usuario.Perfil.COORDENADOR, is_active=True)
        .order_by("pk")
        .first()
    )


def contatos_do_aluno(aluno):
    """O aluno só pode escrever aos professores da própria turma e à secretaria."""
    filtro = Q(pk__in=[])
    matricula = Matricula.atual_de(aluno)
    if matricula:
        filtro |= Q(ofertas__turma=matricula.turma)
    conta_da_secretaria = secretaria()
    if conta_da_secretaria:
        filtro |= Q(pk=conta_da_secretaria.pk)
    return Usuario.objects.filter(filtro, is_active=True).distinct().order_by("first_name")


class CampoContato(forms.ModelChoiceField):
    def label_from_instance(self, usuario):
        return nome_de_exibicao(usuario)


def campo_de_texto():
    return forms.CharField(
        label="Mensagem",
        max_length=4000,
        widget=forms.Textarea(
            attrs={"rows": 2, "class": CLASSES_CAMPO, "placeholder": "Escreva sua mensagem..."}
        ),
    )


def widget_de_anexo():
    return forms.FileInput(attrs={"class": "sr-only", "accept": FORMATOS_ANEXO})


class RespostaForm(forms.ModelForm):
    texto = campo_de_texto()

    class Meta:
        model = Mensagem
        fields = ["texto", "anexo"]
        widgets = {"anexo": widget_de_anexo()}


class NovaConversaForm(forms.ModelForm):
    """Cria a conversa e a primeira mensagem de uma só vez."""

    contato = CampoContato(
        label="Para",
        queryset=Usuario.objects.none(),
        empty_label="Selecione",
        widget=forms.Select(attrs={"class": CLASSES_CAMPO}),
    )
    assunto = forms.CharField(
        label="Assunto",
        max_length=120,
        widget=forms.TextInput(attrs={"class": CLASSES_CAMPO}),
    )
    texto = campo_de_texto()

    class Meta:
        model = Mensagem
        fields = ["texto", "anexo"]
        widgets = {"anexo": widget_de_anexo()}

    def __init__(self, *args, aluno, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno
        self.fields["contato"].queryset = contatos_do_aluno(aluno)

    def save(self):
        contato = self.cleaned_data["contato"]
        matricula = Matricula.atual_de(self.aluno)
        # Se o contato é professor da turma, a conversa já fica ligada à disciplina dele.
        oferta = None
        if matricula:
            oferta = Oferta.objects.filter(turma=matricula.turma, professor=contato).first()
        conversa = Conversa.objects.create(
            aluno=self.aluno,
            contato=contato,
            assunto=self.cleaned_data["assunto"],
            oferta=oferta,
        )
        self.instance.conversa = conversa
        self.instance.remetente = self.aluno
        self.instance.save()
        return conversa
