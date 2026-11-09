"""Consultas e contas das telas do aluno. As views só juntam estes resultados e mostram na tela."""

import calendar
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.academico.calculos import EM_ATENCAO, EM_RISCO, REGULAR, somar_meses
from apps.academico.models import Avaliacao, Evento, Frequencia, Justificativa
# saudacao e texto_dias_ate ficam em utilidades porque o painel do professor também usa.
from apps.academico.utilidades import data_valida, saudacao, texto_dias_ate  # noqa: F401
from apps.financeiro.models import Mensalidade

# Entregas aparecem como pendência quando faltam até 14 dias.
DIAS_ENTREGA_PENDENTE = 14

ROTULOS_DE_EVENTO = {
    Evento.Tipo.INSTITUCIONAL: "Institucional",
    Evento.Tipo.FERIADO: "Feriado",
    Evento.Tipo.ATIVIDADE: "Atividade",
}


# --- Painel ---


def proximas_avaliacoes(turma):
    return (
        Avaliacao.objects.filter(oferta__turma=turma, data_hora__gte=timezone.now())
        .select_related("oferta__disciplina")
        .order_by("data_hora")
    )


def faltas_sem_justificativa(matricula):
    """Faltas que ainda podem ser justificadas: sem pedido, ou com o pedido rejeitado."""
    return (
        Frequencia.objects.filter(matricula=matricula, presente=False)
        .exclude(
            justificativas__status__in=[
                Justificativa.Status.PENDENTE,
                Justificativa.Status.APROVADA,
            ]
        )
        .select_related("aula__oferta__disciplina")
        .order_by("-aula__data")
    )


def montar_pendencias(matricula):
    """Lista o que o aluno precisa resolver. Várias faltas contam como uma só pendência."""
    pendencias = []

    faltas = faltas_sem_justificativa(matricula).count()
    if faltas:
        pendencias.append(
            {
                "titulo": "Justificativa de ausência",
                "detalhe": f"Faltas sem justificativa: {faltas}",
                "url": f"{reverse('aluno:frequencia')}?justificar=1",
            }
        )

    limite = timezone.now() + timedelta(days=DIAS_ENTREGA_PENDENTE)
    entregas = proximas_avaliacoes(matricula.turma).filter(
        tipo=Avaliacao.Tipo.ENTREGA, data_hora__lte=limite
    )
    for entrega in entregas:
        pendencias.append(
            {
                "titulo": f"{entrega.nome}: {entrega.oferta.disciplina.nome}",
                "detalhe": f"Até {timezone.localtime(entrega.data_hora):%d/%m/%Y}",
                "url": reverse("aluno:calendario"),
            }
        )

    atrasadas = Mensalidade.objects.filter(
        matricula=matricula, paga_em__isnull=True, vencimento__lt=timezone.localdate()
    ).count()
    if atrasadas:
        pendencias.append(
            {
                "titulo": "Mensalidade em atraso",
                "detalhe": f"Parcelas em aberto: {atrasadas}",
                "url": reverse("aluno:financeiro"),
            }
        )
    return pendencias


def resumo_de_situacoes(linhas):
    """Conta as disciplinas por selo e calcula onde começa cada trecho da rosca do painel.

    No SVG, o contorno do círculo é dividido em "total" partes: cada disciplina vale 1 parte.
    """
    contagem = {REGULAR: 0, EM_ATENCAO: 0, EM_RISCO: 0}
    for linha in linhas:
        if linha["situacao"] in contagem:
            contagem[linha["situacao"]] += 1
    regulares, atencao, risco = contagem[REGULAR], contagem[EM_ATENCAO], contagem[EM_RISCO]
    return {
        "total": len(linhas),
        "regulares": regulares,
        "atencao": atencao,
        "risco": risco,
        # Inícios dos trechos, como deslocamento negativo do traço no SVG.
        "inicio_atencao": -regulares,
        "inicio_risco": -(regulares + atencao),
    }


# --- Calendário de frequência ---


def ler_mes(texto, padrao):
    """Lê ?mes=2026-10 da URL. Valor ausente ou inválido volta ao mês padrão."""
    return data_valida(f"{texto}-01") or padrao


def mes_do_ultimo_registro(matricula):
    """Mês padrão do calendário: o da aula mais recente, para não abrir um mês ainda vazio."""
    ultima = (
        Frequencia.objects.filter(matricula=matricula)
        .order_by("-aula__data")
        .values_list("aula__data", flat=True)
        .first()
    )
    return (ultima or timezone.localdate()).replace(day=1)


def semanas_de_frequencia(matricula, mes, oferta_id=None):
    """Monta as semanas do mês, marcando em cada dia se houve presença ou falta.

    Se o aluno faltou a qualquer aula do dia, o dia inteiro aparece como ausência.
    """
    registros = Frequencia.objects.filter(
        matricula=matricula, aula__data__year=mes.year, aula__data__month=mes.month
    )
    if oferta_id:
        registros = registros.filter(aula__oferta_id=oferta_id)

    status = {}
    for dia, presente in registros.order_by().values_list("aula__data", "presente"):
        if not presente:
            status[dia] = "falta"
        else:
            status.setdefault(dia, "presenca")

    hoje = timezone.localdate()
    return [
        [
            {
                "numero": dia.day,
                "fora_do_mes": dia.month != mes.month,
                "status": status.get(dia),
                "hoje": dia == hoje,
                "data": dia,
            }
            for dia in semana
        ]
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(mes.year, mes.month)
    ]


# --- Calendário acadêmico ---


def _hora(momento):
    """Horário no formato 19h10. Meia-noite significa "dia inteiro" e não mostra hora."""
    return "" if momento.time() == time(0, 0) else f"{momento:%Hh%M}"


def _item_de_avaliacao(avaliacao):
    momento = timezone.localtime(avaliacao.data_hora)
    disciplina = avaliacao.oferta.disciplina.nome
    if avaliacao.tipo == Avaliacao.Tipo.ENTREGA:
        titulo = f"Entrega de {disciplina}"
        detalhes = [avaliacao.nome, f"até {_hora(momento)}" if _hora(momento) else ""]
        rotulo = "Entrega"
    else:
        titulo = f"Prova de {disciplina}"
        detalhes = [avaliacao.nome, _hora(momento), avaliacao.local]
        rotulo = "Avaliação"
    return {
        "inicio": momento,
        "fim": momento,
        "titulo": titulo,
        "detalhe": " · ".join(parte for parte in detalhes if parte),
        "rotulo": rotulo,
        "destaque": True,
    }


def _item_de_evento(evento):
    momento = timezone.localtime(evento.inicio)
    detalhes = [_hora(momento), evento.local, evento.descricao]
    if evento.oferta:
        detalhes.insert(0, evento.oferta.disciplina.nome)
    return {
        "inicio": momento,
        "fim": timezone.localtime(evento.fim) if evento.fim else momento,
        "titulo": evento.titulo,
        "detalhe": " · ".join(parte for parte in detalhes if parte),
        "rotulo": ROTULOS_DE_EVENTO[evento.tipo],
        "destaque": evento.tipo == Evento.Tipo.ATIVIDADE,
    }


def _eventos_da_turma(turma):
    """Eventos institucionais (sem oferta) e os das disciplinas da turma do aluno."""
    return Evento.objects.filter(Q(oferta__isnull=True) | Q(oferta__turma=turma)).select_related(
        "oferta__disciplina"
    )


def _inicio_do_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min))


def itens_do_periodo(turma, primeiro_dia, ultimo_dia):
    """Junta avaliações e eventos entre duas datas, em ordem cronológica."""
    inicio = _inicio_do_dia(primeiro_dia)
    fim = _inicio_do_dia(ultimo_dia + timedelta(days=1))
    avaliacoes = Avaliacao.objects.filter(
        oferta__turma=turma, data_hora__gte=inicio, data_hora__lt=fim
    ).select_related("oferta__disciplina")
    # Um evento de vários dias entra se qualquer parte dele cair dentro do período.
    eventos = _eventos_da_turma(turma).filter(
        Q(inicio__gte=inicio) | Q(fim__gte=inicio), inicio__lt=fim
    )
    itens = [_item_de_avaliacao(a) for a in avaliacoes] + [_item_de_evento(e) for e in eventos]
    return sorted(itens, key=lambda item: item["inicio"])


def proximos_itens(turma, quantidade=3):
    """Bloco "A seguir": o que vem a partir de hoje, sem depender do mês que está na tela."""
    inicio = _inicio_do_dia(timezone.localdate())
    avaliacoes = Avaliacao.objects.filter(
        oferta__turma=turma, data_hora__gte=inicio
    ).select_related("oferta__disciplina")[:quantidade]
    eventos = _eventos_da_turma(turma).filter(inicio__gte=inicio)[:quantidade]
    itens = [_item_de_avaliacao(a) for a in avaliacoes] + [_item_de_evento(e) for e in eventos]
    return sorted(itens, key=lambda item: item["inicio"])[:quantidade]


def ler_data(texto):
    """Lê ?data= da URL. Valor ausente ou inválido volta para hoje."""
    return data_valida(texto or "") or timezone.localdate()


def _semana_com_itens(dias, itens, mes=None):
    hoje = timezone.localdate()
    return [
        {
            "data": dia,
            "fora_do_mes": mes is not None and dia.month != mes,
            "hoje": dia == hoje,
            "fim_de_semana": dia.weekday() >= 5,
            "itens": [
                item for item in itens if item["inicio"].date() <= dia <= item["fim"].date()
            ],
        }
        for dia in dias
    ]


def montar_calendario(turma, visao, referencia):
    """Prepara a tela do calendário conforme a visão escolhida: mês, semana ou lista."""
    if visao == "semana":
        inicio = referencia - timedelta(days=referencia.weekday())
        fim = inicio + timedelta(days=6)
        anterior, seguinte = inicio - timedelta(days=7), inicio + timedelta(days=7)
        if inicio.month == fim.month:
            titulo = f"{inicio.day} a {fim.day} de {_nome_do_mes(fim)} de {fim.year}"
        else:
            titulo = (
                f"{inicio.day} de {_nome_do_mes(inicio)} a "
                f"{fim.day} de {_nome_do_mes(fim)} de {fim.year}"
            )
        dias_das_semanas = [[inicio + timedelta(days=n) for n in range(7)]]
        mes = None
    else:
        inicio = referencia.replace(day=1)
        fim = date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1])
        anterior, seguinte = somar_meses(inicio, -1), somar_meses(inicio, 1)
        titulo = f"{_nome_do_mes(inicio).capitalize()} de {inicio.year}"
        dias_das_semanas = calendar.Calendar(firstweekday=0).monthdatescalendar(
            inicio.year, inicio.month
        )
        mes = inicio.month

    # A grade do mês também mostra os dias vizinhos que completam a primeira e a última semana.
    primeiro_visivel = dias_das_semanas[0][0]
    ultimo_visivel = dias_das_semanas[-1][-1]
    todos = itens_do_periodo(turma, primeiro_visivel, ultimo_visivel)

    return {
        "titulo": titulo,
        "anterior": anterior.isoformat(),
        "seguinte": seguinte.isoformat(),
        "semanas": [_semana_com_itens(dias, todos, mes) for dias in dias_das_semanas],
        # A lista mostra apenas o que cai dentro do período do título.
        "lista": [
            item for item in todos if item["fim"].date() >= inicio and item["inicio"].date() <= fim
        ],
    }


NOMES_DOS_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def _nome_do_mes(data):
    return NOMES_DOS_MESES[data.month - 1]
