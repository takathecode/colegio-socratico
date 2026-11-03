"""Regras de média, frequência e selo de situação.

Ficam em um só lugar para que todas as telas, relatórios e a API mostrem os mesmos valores.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum

from .models import Frequencia, Nota, Oferta

# Limites do selo de situação.
FREQUENCIA_MINIMA = Decimal("75")  # abaixo disso: Em risco
FREQUENCIA_ATENCAO = Decimal("80")  # abaixo disso: Em atenção
MEDIA_RISCO = Decimal("6")  # abaixo disso: Em risco
MEDIA_MINIMA = Decimal("7")  # abaixo disso: Em atenção

REGULAR = "Regular"
EM_ATENCAO = "Em atenção"
EM_RISCO = "Em risco"

DUAS_CASAS = Decimal("0.01")


def calcular_media(valores):
    """Média simples das notas lançadas. Retorna None se ainda não há nota."""
    valores = list(valores)
    if not valores:
        return None
    return (sum(valores) / len(valores)).quantize(DUAS_CASAS, ROUND_HALF_UP)


def calcular_frequencia(horas_dadas, horas_faltas):
    """Percentual de presença. Retorna None se ainda não houve aula."""
    if not horas_dadas:
        return None
    presentes = Decimal(horas_dadas - horas_faltas)
    return (presentes * 100 / horas_dadas).quantize(DUAS_CASAS, ROUND_HALF_UP)


def calcular_situacao(media, frequencia):
    """Define o selo. Um dado ainda inexistente (None) não conta contra o aluno."""
    if media is None and frequencia is None:
        return None
    if (frequencia is not None and frequencia < FREQUENCIA_MINIMA) or (
        media is not None and media < MEDIA_RISCO
    ):
        return EM_RISCO
    if (frequencia is not None and frequencia < FREQUENCIA_ATENCAO) or (
        media is not None and media < MEDIA_MINIMA
    ):
        return EM_ATENCAO
    return REGULAR


def frequencia_global(matricula):
    """Frequência do aluno somando todas as disciplinas da turma."""
    totais = Frequencia.objects.filter(matricula=matricula).aggregate(
        dadas=Sum("aula__horas_aula"),
        faltas=Sum("aula__horas_aula", filter=Q(presente=False)),
    )
    return calcular_frequencia(totais["dadas"], totais["faltas"] or 0)


def resumo_por_disciplina(matricula):
    """Monta as linhas do boletim: uma por disciplina da turma do aluno.

    Busca tudo em poucas consultas agrupadas, em vez de uma consulta por disciplina,
    porque cada ida ao banco no Supabase leva tempo.
    """
    notas_por_oferta = {}
    notas = (
        Nota.objects.filter(matricula=matricula)
        .order_by("avaliacao__data_hora")
        .values_list("avaliacao__oferta_id", "valor")
    )
    for oferta_id, valor in notas:
        notas_por_oferta.setdefault(oferta_id, []).append(valor)

    horas_por_oferta = {
        linha["aula__oferta_id"]: linha
        for linha in Frequencia.objects.filter(matricula=matricula)
        .order_by()
        .values("aula__oferta_id")
        .annotate(
            dadas=Sum("aula__horas_aula"),
            faltas=Sum("aula__horas_aula", filter=Q(presente=False)),
        )
    }

    linhas = []
    ofertas = (
        Oferta.objects.filter(turma_id=matricula.turma_id)
        .select_related("disciplina", "professor")
        .order_by("id")
    )
    for oferta in ofertas:
        notas_da_oferta = notas_por_oferta.get(oferta.id, [])
        horas = horas_por_oferta.get(oferta.id, {})
        horas_dadas = horas.get("dadas") or 0
        horas_faltas = horas.get("faltas") or 0
        media = calcular_media(notas_da_oferta)
        frequencia = calcular_frequencia(horas_dadas, horas_faltas)
        linhas.append(
            {
                "oferta": oferta,
                "notas": notas_da_oferta,
                "media": media,
                "horas_dadas": horas_dadas,
                "horas_faltas": horas_faltas,
                "frequencia": frequencia,
                "situacao": calcular_situacao(media, frequencia),
            }
        )
    return linhas
