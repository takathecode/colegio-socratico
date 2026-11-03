"""Telas da área do aluno. Toda consulta parte da matrícula do próprio usuário logado."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.academico.calculos import (
    EM_ATENCAO,
    EM_RISCO,
    FREQUENCIA_MINIMA,
    MEDIA_MINIMA,
    frequencia_das_linhas,
    resumo_por_disciplina,
    somar_meses,
)
from apps.academico.models import Avaliacao, Justificativa, Matricula, Nota
from apps.academico.utilidades import baixar_anexo
from apps.contas.decorators import perfil_requerido
from apps.financeiro.models import Mensalidade
from apps.mensagens.forms import secretaria

from . import servicos
from .forms import JustificativaForm


def sem_matricula(request, titulo):
    """Tela mostrada a quem ainda não tem matrícula ativa, no lugar de uma página de erro."""
    return render(request, "aluno/sem_matricula.html", {"titulo_da_tela": titulo})


def dados_de_frequencia(linhas):
    """Valores do card "Frequência global": percentual, barra e comparação com o mínimo."""
    percentual = frequencia_das_linhas(linhas)
    return {
        "percentual": percentual,
        # Número inteiro, porque "88,9" com vírgula não é um valor válido no CSS.
        "largura": round(percentual) if percentual is not None else 0,
        "minimo": int(FREQUENCIA_MINIMA),
        "acima_do_minimo": percentual is not None and percentual >= FREQUENCIA_MINIMA,
    }


def dados_de_creditos(matricula):
    total = matricula.turma.curso.total_creditos
    return {
        "concluidos": matricula.creditos_concluidos,
        "total": total,
        "percentual": round(matricula.creditos_concluidos * 100 / total) if total else 0,
    }


@login_required
@perfil_requerido("ALUNO")
def painel(request):
    matricula = Matricula.atual_de(request.user)
    if matricula is None:
        return sem_matricula(request, "Painel")

    linhas = resumo_por_disciplina(matricula)
    proximas = list(servicos.proximas_avaliacoes(matricula.turma)[:10])
    proxima_prova = next((a for a in proximas if a.tipo == Avaliacao.Tipo.PROVA), None)
    mes = servicos.mes_do_ultimo_registro(matricula)

    return render(
        request,
        "aluno/painel.html",
        {
            "saudacao": servicos.saudacao(),
            "hoje": timezone.localdate(),
            "matricula": matricula,
            "creditos": dados_de_creditos(matricula),
            "linhas": linhas,
            "frequencia": dados_de_frequencia(linhas),
            "situacoes": servicos.resumo_de_situacoes(linhas),
            "proxima_prova": proxima_prova,
            "dias_ate_a_prova": (
                servicos.texto_dias_ate(proxima_prova.data_hora) if proxima_prova else None
            ),
            "proxima_atividade": proximas[0] if proximas else None,
            "pendencias": servicos.montar_pendencias(matricula),
            "mes": mes,
            "semanas": servicos.semanas_de_frequencia(matricula, mes),
        },
    )


@login_required
@perfil_requerido("ALUNO")
def notas(request):
    matricula = Matricula.atual_de(request.user)
    if matricula is None:
        return sem_matricula(request, "Notas e Boletim")

    linhas = resumo_por_disciplina(matricula)
    atencao = [linha for linha in linhas if linha["situacao"] in (EM_ATENCAO, EM_RISCO)]
    atualizacao = Nota.objects.filter(matricula=matricula).aggregate(ultima=Max("atualizada_em"))

    return render(
        request,
        "aluno/notas.html",
        {
            "matricula": matricula,
            "creditos": dados_de_creditos(matricula),
            "linhas": linhas,
            "em_atencao": atencao,
            "nomes_em_atencao": ", ".join(l["oferta"].disciplina.nome for l in atencao),
            "atualizada_em": atualizacao["ultima"],
            "media_minima": MEDIA_MINIMA,
            "frequencia_minima": int(FREQUENCIA_MINIMA),
        },
    )


@login_required
@perfil_requerido("ALUNO")
def frequencia(request):
    matricula = Matricula.atual_de(request.user)
    if matricula is None:
        return sem_matricula(request, "Frequência")

    faltas = list(servicos.faltas_sem_justificativa(matricula))

    if request.method == "POST":
        form = JustificativaForm(request.POST, request.FILES, matricula=matricula)
        if form.is_valid():
            form.save()
            messages.success(
                request, "Justificativa enviada. Acompanhe a resposta em Minhas justificativas."
            )
            return redirect("aluno:frequencia")
        messages.error(request, "A justificativa não foi enviada. Confira os campos destacados.")
    else:
        # A falta mais recente já vem selecionada, como no protótipo.
        form = JustificativaForm(
            matricula=matricula, initial={"frequencia": faltas[0].pk if faltas else None}
        )

    linhas = resumo_por_disciplina(matricula)

    # Filtro de disciplina do calendário. Um valor que não é da turma do aluno é ignorado.
    ofertas_da_turma = {str(linha["oferta"].pk) for linha in linhas}
    disciplina = request.GET.get("disciplina", "")
    oferta_id = int(disciplina) if disciplina in ofertas_da_turma else None

    mes = servicos.ler_mes(
        request.GET.get("mes", ""), servicos.mes_do_ultimo_registro(matricula)
    )

    # Disciplinas que aparecem no modal: só as que têm falta para justificar.
    ids_com_falta = {falta.aula.oferta_id for falta in faltas}

    return render(
        request,
        "aluno/frequencia.html",
        {
            "hoje": timezone.localdate(),
            "matricula": matricula,
            "linhas": linhas,
            "frequencia": dados_de_frequencia(linhas),
            "falta_recente": faltas[0] if faltas else None,
            "outras_faltas": max(len(faltas) - 1, 0),
            "disciplinas_com_falta": [l for l in linhas if l["oferta"].pk in ids_com_falta],
            "form": form,
            "abrir_modal": bool(faltas) and (form.is_bound or "justificar" in request.GET),
            "justificativas": Justificativa.objects.filter(
                frequencia__matricula=matricula
            ).select_related("frequencia__aula__oferta__disciplina"),
            "oferta_id": oferta_id,
            "mes": mes,
            "mes_anterior": somar_meses(mes, -1),
            "mes_seguinte": somar_meses(mes, 1),
            "semanas": servicos.semanas_de_frequencia(matricula, mes, oferta_id),
        },
    )


@login_required
@perfil_requerido("ALUNO")
def anexo_justificativa(request, pk):
    """Só o dono baixa o atestado: para qualquer outra pessoa, a justificativa "não existe"."""
    justificativa = get_object_or_404(
        Justificativa, pk=pk, frequencia__matricula__aluno=request.user
    )
    if not justificativa.anexo:
        raise Http404("Esta justificativa não tem anexo.")
    return baixar_anexo(justificativa.anexo)


@login_required
@perfil_requerido("ALUNO")
def calendario(request):
    matricula = Matricula.atual_de(request.user)
    if matricula is None:
        return sem_matricula(request, "Calendário Acadêmico")

    visao = request.GET.get("visao")
    if visao not in ("mes", "semana", "lista"):
        visao = "mes"
    referencia = servicos.ler_data(request.GET.get("data"))

    return render(
        request,
        "aluno/calendario.html",
        {
            "visao": visao,
            "visoes": (("mes", "Mês"), ("semana", "Semana"), ("lista", "Lista")),
            "dias_da_semana": ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"),
            "hoje": timezone.localdate(),
            "data_atual": referencia.isoformat(),
            "calendario": servicos.montar_calendario(matricula.turma, visao, referencia),
            "a_seguir": servicos.proximos_itens(matricula.turma),
        },
    )


@login_required
@perfil_requerido("ALUNO")
def financeiro(request):
    matricula = Matricula.atual_de(request.user)
    if matricula is None:
        return sem_matricula(request, "Financeiro")

    mensalidades = list(Mensalidade.objects.filter(matricula=matricula))
    # Parcela em aberto com o vencimento mais antigo: é a primeira a ser paga.
    em_aberto = sorted(
        (parcela for parcela in mensalidades if not parcela.paga_em),
        key=lambda parcela: parcela.vencimento,
    )
    atrasadas = [p for p in em_aberto if p.situacao == Mensalidade.EM_ATRASO]

    return render(
        request,
        "aluno/financeiro.html",
        {
            "matricula": matricula,
            "mensalidades": mensalidades,
            "proxima": em_aberto[0] if em_aberto else None,
            "atrasadas": len(atrasadas),
            "bolsa": mensalidades[0].bolsa_percentual if mensalidades else 0,
            "secretaria": secretaria(),
        },
    )
