"""Regras de média, frequência e selo de situação.

Ficam em um só lugar para que todas as telas, relatórios e a API mostrem os mesmos valores.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum

from .models import Avaliacao, Frequencia, Matricula, Nota, Oferta

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


def frequencia_das_linhas(linhas):
    """Frequência global a partir das linhas do boletim, sem uma nova consulta ao banco."""
    return calcular_frequencia(
        sum(linha["horas_dadas"] for linha in linhas),
        sum(linha["horas_faltas"] for linha in linhas),
    )


def somar_meses(data, meses):
    """Primeiro dia do mês que fica "meses" à frente (ou atrás, se for negativo) da data."""
    indice = data.year * 12 + (data.month - 1) + meses
    return date(indice // 12, indice % 12 + 1, 1)


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
    nomeadas_por_oferta = {}  # as mesmas notas, com o nome da avaliação: [("A1", 6.8), ...]
    notas = (
        Nota.objects.filter(matricula=matricula)
        .order_by("avaliacao__data_hora", "avaliacao_id")
        .values_list("avaliacao__oferta_id", "valor", "avaliacao__nome")
    )
    for oferta_id, valor, nome in notas:
        notas_por_oferta.setdefault(oferta_id, []).append(valor)
        nomeadas_por_oferta.setdefault(oferta_id, []).append((nome, valor))

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
                "notas_nomeadas": nomeadas_por_oferta.get(oferta.id, []),
                "media": media,
                "horas_dadas": horas_dadas,
                "horas_faltas": horas_faltas,
                "frequencia": frequencia,
                "situacao": calcular_situacao(media, frequencia),
            }
        )
    return linhas


def resumo_da_oferta(oferta):
    """Monta a visão do professor: uma linha por aluno ativo da turma, nesta disciplina.

    Usa as mesmas regras do boletim do aluno, então os dois veem os mesmos números.
    São quatro consultas ao todo, qualquer que seja o tamanho da turma.
    Retorna (avaliacoes, linhas). Em cada linha, "notas" segue a ordem de "avaliacoes"
    e tem None onde a nota ainda não foi lançada.
    """
    avaliacoes = list(Avaliacao.objects.filter(oferta=oferta).order_by("data_hora", "nome"))
    matriculas = list(
        Matricula.objects.filter(turma_id=oferta.turma_id, situacao=Matricula.Situacao.ATIVA)
        .select_related("aluno")
        .order_by("aluno__first_name", "aluno__last_name")
    )

    notas = {
        (matricula_id, avaliacao_id): valor
        for matricula_id, avaliacao_id, valor in Nota.objects.filter(
            avaliacao__oferta=oferta
        ).values_list("matricula_id", "avaliacao_id", "valor")
    }
    horas = {
        linha["matricula_id"]: linha
        for linha in Frequencia.objects.filter(aula__oferta=oferta)
        .order_by()
        .values("matricula_id")
        .annotate(
            dadas=Sum("aula__horas_aula"),
            faltas=Sum("aula__horas_aula", filter=Q(presente=False)),
        )
    }

    linhas = []
    for matricula in matriculas:
        notas_do_aluno = [notas.get((matricula.pk, avaliacao.pk)) for avaliacao in avaliacoes]
        media = calcular_media(valor for valor in notas_do_aluno if valor is not None)
        horas_do_aluno = horas.get(matricula.pk, {})
        horas_dadas = horas_do_aluno.get("dadas") or 0
        horas_faltas = horas_do_aluno.get("faltas") or 0
        frequencia = calcular_frequencia(horas_dadas, horas_faltas)
        linhas.append(
            {
                "matricula": matricula,
                "notas": notas_do_aluno,
                "media": media,
                "horas_dadas": horas_dadas,
                "horas_faltas": horas_faltas,
                "frequencia": frequencia,
                "situacao": calcular_situacao(media, frequencia),
            }
        )
    return avaliacoes, linhas


def indicadores_da_turma(linhas):
    """Médias da turma e quantos alunos há em cada situação, a partir das linhas acima."""
    medias = [linha["media"] for linha in linhas if linha["media"] is not None]
    frequencias = [linha["frequencia"] for linha in linhas if linha["frequencia"] is not None]
    return {
        "alunos": len(linhas),
        "media": calcular_media(medias),
        "frequencia": calcular_media(frequencias),  # média simples dos percentuais
        "regulares": sum(1 for linha in linhas if linha["situacao"] == REGULAR),
        "atencao": sum(1 for linha in linhas if linha["situacao"] == EM_ATENCAO),
        "risco": sum(1 for linha in linhas if linha["situacao"] == EM_RISCO),
    }


# Ordem de gravidade dos selos, usada para achar a "pior" situação de um aluno.
GRAVIDADE = {None: 0, REGULAR: 1, EM_ATENCAO: 2, EM_RISCO: 3}


def resumo_das_matriculas(matriculas):
    """Situação geral de vários alunos de uma vez, para as telas da coordenação.

    Para cada matrícula calcula:
    - media: média das médias das disciplinas que já têm nota;
    - frequencia: frequência global, somando as horas de todas as disciplinas;
    - situacao: a pior situação entre as disciplinas. Assim, quem está "Em risco" para
      algum professor também aparece "Em risco" para a coordenação;
    - disciplinas_em_risco: em quantas disciplinas o aluno está "Em risco".

    São só duas consultas agrupadas, qualquer que seja o número de alunos.
    Retorna {matricula_id: dados}.
    """
    ids = [matricula.pk for matricula in matriculas]

    # (matrícula, oferta) -> notas lançadas
    notas = {}
    for matricula_id, oferta_id, valor in Nota.objects.filter(matricula_id__in=ids).values_list(
        "matricula_id", "avaliacao__oferta_id", "valor"
    ):
        notas.setdefault((matricula_id, oferta_id), []).append(valor)

    # (matrícula, oferta) -> (horas dadas, horas de falta)
    horas = {
        (linha["matricula_id"], linha["aula__oferta_id"]): (
            linha["dadas"] or 0,
            linha["faltas"] or 0,
        )
        for linha in Frequencia.objects.filter(matricula_id__in=ids)
        .order_by()
        .values("matricula_id", "aula__oferta_id")
        .annotate(
            dadas=Sum("aula__horas_aula"),
            faltas=Sum("aula__horas_aula", filter=Q(presente=False)),
        )
    }

    # matrícula -> disciplinas em que ela já tem nota ou chamada registrada
    ofertas_por_matricula = {}
    for matricula_id, oferta_id in (*notas, *horas):
        ofertas_por_matricula.setdefault(matricula_id, set()).add(oferta_id)

    resumo = {}
    for matricula_id in ids:
        medias, situacoes = [], []
        total_dadas = total_faltas = 0
        for oferta_id in ofertas_por_matricula.get(matricula_id, ()):
            media = calcular_media(notas.get((matricula_id, oferta_id), []))
            dadas, faltas = horas.get((matricula_id, oferta_id), (0, 0))
            total_dadas += dadas
            total_faltas += faltas
            if media is not None:
                medias.append(media)
            situacoes.append(calcular_situacao(media, calcular_frequencia(dadas, faltas)))
        resumo[matricula_id] = {
            "media": calcular_media(medias),
            "frequencia": calcular_frequencia(total_dadas, total_faltas),
            "situacao": max(situacoes, key=GRAVIDADE.get, default=None),
            "disciplinas_em_risco": situacoes.count(EM_RISCO),
        }
    return resumo


def resumo_da_turma(turma):
    """Uma linha por aluno ativo da turma, com o resumo acima e a matrícula em "matricula".

    Usada no relatório de desempenho da turma e na API. As linhas servem também para
    indicadores_da_turma, que lê "media", "frequencia" e "situacao".
    """
    matriculas = list(
        Matricula.objects.filter(turma=turma, situacao=Matricula.Situacao.ATIVA)
        .select_related("aluno")
        .order_by("aluno__first_name", "aluno__last_name")
    )
    resumo = resumo_das_matriculas(matriculas)
    return [{"matricula": matricula, **resumo[matricula.pk]} for matricula in matriculas]
