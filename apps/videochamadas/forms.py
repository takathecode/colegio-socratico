from django import forms

from apps.academico.utilidades import CLASSES_CAMPO
from apps.contas.models import Usuario

from .models import Chamada, nome_na_chamada


def pessoas_para_chamar(usuario):
    """A coordenação chama professores ativos; o professor chama coordenadores ativos."""
    if usuario.perfil == Usuario.Perfil.COORDENADOR:
        perfil = Usuario.Perfil.PROFESSOR
    else:
        perfil = Usuario.Perfil.COORDENADOR
    return Usuario.objects.filter(perfil=perfil, is_active=True).order_by(
        "first_name", "last_name"
    )


class CampoPessoa(forms.ModelChoiceField):
    def label_from_instance(self, usuario):
        return nome_na_chamada(usuario)


class NovaChamadaForm(forms.ModelForm):
    convidado = CampoPessoa(
        label="Quem você quer chamar",
        queryset=Usuario.objects.none(),
        empty_label="Selecione",
        widget=forms.Select(attrs={"class": CLASSES_CAMPO}),
    )

    class Meta:
        model = Chamada
        fields = ["convidado", "assunto"]
        labels = {"assunto": "Assunto (opcional)"}
        widgets = {
            "assunto": forms.TextInput(
                attrs={"class": CLASSES_CAMPO, "placeholder": "Ex.: planejamento das avaliações"}
            )
        }

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        # Quem chama é sempre quem está logado: o campo não vem do formulário.
        self.instance.criada_por = usuario
        self.fields["convidado"].queryset = pessoas_para_chamar(usuario)
        if usuario.perfil == Usuario.Perfil.COORDENADOR:
            self.fields["convidado"].label = "Professor"
        else:
            self.fields["convidado"].label = "Coordenador"
