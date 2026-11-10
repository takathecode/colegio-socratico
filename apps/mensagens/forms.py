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


def alunos_do_professor(professor):
    """O professor só pode escrever aos alunos ativos das turmas em que leciona.

    As duas condições ficam no mesmo filter(): assim valem para a mesma matrícula, e um aluno
    com matrícula trancada em uma turma do professor não entra na lista.
    """
    return (
        Usuario.objects.filter(
            perfil=Usuario.Perfil.ALUNO,
            is_active=True,
            matriculas__situacao=Matricula.Situacao.ATIVA,
            matriculas__turma__ofertas__professor=professor,
        )
        .distinct()
        .order_by("first_name", "last_name")
    )


def alunos_da_secretaria():
    """A secretaria pode escrever a qualquer aluno ativo com matrícula ativa."""
    return (
        Usuario.objects.filter(
            perfil=Usuario.Perfil.ALUNO,
            is_active=True,
            matriculas__situacao=Matricula.Situacao.ATIVA,
        )
        .distinct()
        .order_by("first_name", "last_name")
    )


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
    """Cria a conversa e a primeira mensagem de uma só vez.

    Quem escreve é o aluno (escolhe um professor da turma ou a secretaria), o professor
    (escolhe um aluno das suas turmas) ou a secretaria (escolhe qualquer aluno ativo).
    O campo "contato" é sempre "a outra pessoa".
    """

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

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario.perfil == Usuario.Perfil.PROFESSOR:
            self.fields["contato"].label = "Aluno"
            self.fields["contato"].queryset = alunos_do_professor(usuario)
        elif usuario.perfil == Usuario.Perfil.COORDENADOR:
            self.fields["contato"].label = "Aluno"
            self.fields["contato"].queryset = alunos_da_secretaria()
        else:
            self.fields["contato"].queryset = contatos_do_aluno(usuario)

    def save(self):
        outro = self.cleaned_data["contato"]
        if self.usuario.perfil != Usuario.Perfil.ALUNO:
            aluno, contato = outro, self.usuario
        else:
            aluno, contato = self.usuario, outro

        # Se o contato é professor da turma do aluno, a conversa já fica ligada à disciplina
        # dele. A turma mais recente vem primeiro, caso o aluno tenha matrículas antigas.
        oferta = (
            Oferta.objects.filter(
                professor=contato,
                turma__matriculas__aluno=aluno,
                turma__matriculas__situacao=Matricula.Situacao.ATIVA,
            )
            .order_by("-turma__semestre")
            .first()
        )
        conversa = Conversa.objects.create(
            aluno=aluno, contato=contato, assunto=self.cleaned_data["assunto"], oferta=oferta
        )
        self.instance.conversa = conversa
        self.instance.remetente = self.usuario
        self.instance.save()
        return conversa
