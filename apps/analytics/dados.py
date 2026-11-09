"""Dados que alimentam os gráficos.

Os números vêm das mesmas regras de apps/academico/calculos.py, então o gráfico sempre
concorda com as tabelas das telas.
"""

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth

from apps.academico.calculos import MEDIA_MINIMA, MEDIA_RISCO, calcular_frequencia
from apps.academico.models import Frequencia, Matricula

# Faixas de média do gráfico do professor: (de, até, rótulo).
# A nota que fica exatamente no limite entra na faixa de cima (6,0 fica em "6 a 7").
FAIXAS_DE_MEDIA = [
    (0, 2, "0 a 2"),
    (2, 4, "2 a 4"),
    (4, 6, "4 a 6"),
    (6, 7, "6 a 7"),
    (7, 8, "7 a 8"),
    (8, 10, "8 a 10"),
]

# Grupos de cor das faixas, usados no gráfico e na legenda da tela.
ABAIXO_DE_6 = "Abaixo de 6"
ENTRE_6_E_7 = "Entre 6 e 7"
SETE_OU_MAIS = "7 ou mais"


def grupo_da_faixa(inicio):
    """Em qual grupo de cor uma faixa fica, pelos mesmos limites do selo de situação."""
    if inicio < MEDIA_RISCO:
        return ABAIXO_DE_6
    if inicio < MEDIA_MINIMA:
        return ENTRE_6_E_7
    return SETE_OU_MAIS


def contar_por_faixa(medias):
    """Quantos alunos têm a média em cada faixa. Média None (sem nota) não entra na conta."""
    # Vira lista porque a contagem percorre as médias uma vez para cada faixa.
    medias = [media for media in medias if media is not None]
    faixas = []
    for inicio, fim, rotulo in FAIXAS_DE_MEDIA:
        ultima = fim == 10
        quantidade = sum(
            1
            for media in medias
            # A última faixa inclui o 10; as outras param antes do limite de cima.
            if inicio <= media and (media <= fim if ultima else media < fim)
        )
        faixas.append({"rotulo": rotulo, "quantidade": quantidade, "grupo": grupo_da_faixa(inicio)})
    return faixas


def frequencia_mensal_por_turma(turmas):
    """Frequência de cada turma, mês a mês, contando só os alunos com matrícula ativa.

    Uma única consulta agrupada por turma e mês. Retorna uma lista, na ordem do código
    da turma, assim: [{"nome": "CC-2026", "meses": [(date(2026, 8, 1), Decimal("91.50")), ...]}].
    Turma ainda sem chamada fica de fora.
    """
    turmas = sorted(turmas, key=lambda turma: turma.codigo)
    linhas = (
        Frequencia.objects.filter(
            aula__oferta__turma__in=turmas,
            matricula__situacao=Matricula.Situacao.ATIVA,
        )
        .annotate(mes=TruncMonth("aula__data"))
        .order_by()
        .values("aula__oferta__turma_id", "mes")
        .annotate(
            dadas=Sum("aula__horas_aula"),
            faltas=Sum("aula__horas_aula", filter=Q(presente=False)),
        )
    )

    meses_por_turma = {}
    for linha in linhas:
        percentual = calcular_frequencia(linha["dadas"], linha["faltas"] or 0)
        if percentual is not None:
            meses_por_turma.setdefault(linha["aula__oferta__turma_id"], []).append(
                (linha["mes"], percentual)
            )

    return [
        {"nome": turma.codigo, "meses": sorted(meses_por_turma[turma.pk])}
        for turma in turmas
        if turma.pk in meses_por_turma
    ]
