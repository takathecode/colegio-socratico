"""Consultas da área do professor.

Regra de segurança: tudo parte de ofertas_do_professor(). Uma disciplina de outro professor
responde 404, para ninguém descobrir nem alterar dados de turmas que não leciona.
"""

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.academico.calculos import indicadores_da_turma, resumo_da_oferta
from apps.academico.models import Aula, Avaliacao, Frequencia, Justificativa, Matricula, Nota, Oferta


def ofertas_do_professor(professor):
    """Disciplinas que o professor leciona, do semestre mais recente para o mais antigo."""
    return (
        Oferta.objects.filter(professor=professor)
        .select_related("turma__curso", "disciplina")
        .order_by("-turma__semestre", "disciplina__nome", "turma__codigo")
    )


def oferta_do_professor(professor, pk):
    """Uma disciplina do professor. A de outro professor dá 404, como se não existisse."""
    return get_object_or_404(ofertas_do_professor(professor), pk=pk)


def escolher_oferta(professor, valor):
    """Lê ?oferta= da URL nas telas de notas e chamada.

    Sem valor, abre a primeira disciplina. Retorna (oferta escolhida, todas as do professor),
    ou (None, []) quando o professor ainda não leciona nenhuma.
    """
    ofertas = list(ofertas_do_professor(professor))
    if not ofertas:
        return None, []
    if not valor:
        return ofertas[0], ofertas
    if not str(valor).isdecimal():
        raise Http404("Disciplina inválida.")
    for oferta in ofertas:
        if oferta.pk == int(valor):
            return oferta, ofertas
    raise Http404("Esta disciplina não é sua.")


def resumo_das_ofertas(ofertas):
    """Indicadores de cada disciplina, para os cards de "Minhas turmas" e para o painel.

    São quatro consultas por disciplina: um professor costuma ter poucas, então fica rápido.
    """
    resumos = []
    for oferta in ofertas:
        avaliacoes, linhas = resumo_da_oferta(oferta)
        resumos.append(
            {
                "oferta": oferta,
                "avaliacoes": avaliacoes,
                "linhas": linhas,
                "indicadores": indicadores_da_turma(linhas),
            }
        )
    return resumos


def justificativas_do_professor(professor):
    """Justificativas das faltas nas disciplinas do professor, das mais novas para as mais antigas."""
    return Justificativa.objects.filter(
        frequencia__aula__oferta__professor=professor
    ).select_related(
        "frequencia__matricula__aluno",
        "frequencia__aula__oferta__disciplina",
        "frequencia__aula__oferta__turma",
        "avaliada_por",
    )


def proximas_avaliacoes_do_professor(professor):
    return (
        Avaliacao.objects.filter(oferta__professor=professor, data_hora__gte=timezone.now())
        .select_related("oferta__disciplina", "oferta__turma")
        .order_by("data_hora")
    )


# --- Notas ---


@transaction.atomic
def salvar_notas(avaliacao, valores):
    """Grava as notas de uma avaliação de uma só vez.

    valores: {matricula_id: Decimal ou None}. None (campo vazio) apaga a nota, se existir.
    O @transaction.atomic garante que, se algo falhar no meio, nada fica salvo pela metade.
    São no máximo três consultas de escrita, em vez de uma por aluno.
    """
    existentes = {nota.matricula_id: nota for nota in Nota.objects.filter(avaliacao=avaliacao)}
    criar, atualizar, apagar = [], [], []
    agora = timezone.now()

    for matricula_id, valor in valores.items():
        nota = existentes.get(matricula_id)
        if valor is None:
            if nota:
                apagar.append(nota.pk)
        elif nota is None:
            criar.append(Nota(avaliacao=avaliacao, matricula_id=matricula_id, valor=valor))
        elif nota.valor != valor:
            nota.valor = valor
            nota.atualizada_em = agora  # bulk_update não preenche o auto_now sozinho
            atualizar.append(nota)

    Nota.objects.bulk_create(criar)
    Nota.objects.bulk_update(atualizar, ["valor", "atualizada_em"])
    Nota.objects.filter(pk__in=apagar).delete()
    return len(criar) + len(atualizar) + len(apagar)


# --- Chamada ---


def matriculas_ativas(oferta):
    return list(
        Matricula.objects.filter(turma_id=oferta.turma_id, situacao=Matricula.Situacao.ATIVA)
        .select_related("aluno")
        .order_by("aluno__first_name", "aluno__last_name")
    )


def montar_chamada(oferta, data):
    """Linhas da tela de chamada: cada aluno com a presença já registrada (se houver).

    Uma falta que já tem justificativa fica travada: mudá-la para presença deixaria
    o pedido do aluno ligado a uma aula em que ele estava presente.
    """
    aula = Aula.objects.filter(oferta=oferta, data=data).first()
    registros = {}
    travadas = set()
    if aula:
        registros = {f.matricula_id: f for f in Frequencia.objects.filter(aula=aula)}
        travadas = set(
            Justificativa.objects.filter(frequencia__aula=aula).values_list(
                "frequencia__matricula_id", flat=True
            )
        )

    linhas = []
    for matricula in matriculas_ativas(oferta):
        registro = registros.get(matricula.pk)
        linhas.append(
            {
                "matricula": matricula,
                "presente": registro.presente if registro else None,  # None = ainda não marcado
                "metodo": registro.metodo if registro else Frequencia.Metodo.MANUAL,
                "travada": matricula.pk in travadas,
            }
        )
    return aula, linhas


@transaction.atomic
def salvar_chamada(oferta, data, horas_aula, conteudo, marcacoes):
    """Cria (ou atualiza) a aula do dia e as presenças.

    marcacoes: {matricula_id: (presente, metodo)}. As linhas travadas não entram aqui.
    """
    aula, _criada = Aula.objects.update_or_create(
        oferta=oferta, data=data, defaults={"horas_aula": horas_aula, "conteudo": conteudo}
    )
    existentes = {f.matricula_id: f for f in Frequencia.objects.filter(aula=aula)}
    criar, atualizar = [], []

    for matricula_id, (presente, metodo) in marcacoes.items():
        registro = existentes.get(matricula_id)
        if registro is None:
            criar.append(
                Frequencia(aula=aula, matricula_id=matricula_id, presente=presente, metodo=metodo)
            )
        elif registro.presente != presente or registro.metodo != metodo:
            registro.presente, registro.metodo = presente, metodo
            atualizar.append(registro)

    Frequencia.objects.bulk_create(criar)
    Frequencia.objects.bulk_update(atualizar, ["presente", "metodo"])
    return aula
