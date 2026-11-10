"""Filtros dos relatórios, feitos com o django-filter.

Um FilterSet lê os parâmetros da URL (?turma=3&nivel=ALTO&busca=bia), valida cada um e
aplica os filtros na consulta. Valor inválido (como ?turma=abc) é simplesmente ignorado.

O RiscoFiltro também é usado na tela "Alunos em risco": assim, o botão "Baixar PDF" da tela
gera um relatório com exatamente os alunos que estão na lista.
"""

import django_filters
from django.db.models import Q, Value
from django.db.models.functions import Concat

from apps.academico.models import Matricula, Turma
from apps.analytics.models import RiscoEvasao


def buscar_aluno(consulta, caminho, termo):
    """Filtra pelo nome completo ou pela matrícula (RA) do aluno.

    "caminho" é o trecho até o aluno na consulta, como "matricula__aluno__".
    O nome completo é montado no banco (nome + espaço + sobrenome) para "Bia Reis" funcionar.
    """
    termo = termo.strip()
    if not termo:
        return consulta
    return consulta.annotate(
        nome_completo_do_aluno=Concat(f"{caminho}first_name", Value(" "), f"{caminho}last_name")
    ).filter(Q(nome_completo_do_aluno__icontains=termo) | Q(**{f"{caminho}matricula__icontains": termo}))


class RiscoFiltro(django_filters.FilterSet):
    busca = django_filters.CharFilter(method="filtrar_busca", label="Nome ou RA")
    turma = django_filters.NumberFilter(field_name="matricula__turma_id", label="Turma")
    nivel = django_filters.ChoiceFilter(choices=RiscoEvasao.Nivel.choices, label="Nível")

    class Meta:
        model = RiscoEvasao
        fields = []  # os filtros já estão declarados acima

    def filtrar_busca(self, consulta, nome, valor):
        return buscar_aluno(consulta, "matricula__aluno__", valor)


class MatriculaFiltro(django_filters.FilterSet):
    busca = django_filters.CharFilter(method="filtrar_busca", label="Nome ou RA")
    turma = django_filters.NumberFilter(field_name="turma_id", label="Turma")
    situacao_matricula = django_filters.ChoiceFilter(
        field_name="situacao", choices=Matricula.Situacao.choices, label="Matrícula"
    )

    class Meta:
        model = Matricula
        fields = []

    def filtrar_busca(self, consulta, nome, valor):
        return buscar_aluno(consulta, "aluno__", valor)


def descrever(filtro):
    """Texto com os filtros usados, impresso no relatório. Ex.: 'Turma T1 · Risco alto'."""
    filtro.qs  # garante que os valores já foram validados
    dados = filtro.form.cleaned_data
    partes = []
    if dados.get("turma"):
        turma = Turma.objects.filter(pk=dados["turma"]).first()
        if turma:
            partes.append(f"Turma {turma.codigo} ({turma.semestre})")
    if dados.get("nivel"):
        partes.append(RiscoEvasao.Nivel(dados["nivel"]).label)
    if dados.get("situacao_matricula"):
        partes.append(f"Matrícula {Matricula.Situacao(dados['situacao_matricula']).label.lower()}")
    if dados.get("busca"):
        partes.append(f'Busca "{dados["busca"].strip()}"')
    return " · ".join(partes)
