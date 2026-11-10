"""Downloads dos relatórios e a tela "Relatórios" da coordenação.

Cada view faz três coisas: confere a permissão, monta o relatório (dados.py) e devolve o
arquivo no formato pedido (pdf.py ou excel.py). Os arquivos são gerados na hora, sem fila
do Celery: com o volume de uma escola, ficam prontos em menos de um segundo.

Permissões:
- aluno: só o próprio boletim (a URL não recebe número de matrícula, então não há como
  pedir o de outra pessoa);
- professor: só as disciplinas que leciona (a de outro professor responde 404);
- coordenação: todos os relatórios. Os outros perfis recebem 403 pelo @perfil_requerido.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header

from apps.academico.calculos import EM_ATENCAO, EM_RISCO, REGULAR
from apps.academico.models import Matricula, Turma
from apps.analytics.models import RiscoEvasao
from apps.contas.decorators import perfil_requerido
from apps.professor.servicos import oferta_do_professor

from . import dados
from .excel import gerar_excel
from .filtros import MatriculaFiltro, RiscoFiltro, descrever
from .pdf import gerar_pdf

PDF = "pdf"
EXCEL = "xlsx"
FORMATOS = {
    PDF: ("application/pdf", gerar_pdf),
    EXCEL: ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", gerar_excel),
}
SELOS = (REGULAR, EM_ATENCAO, EM_RISCO)


def ler_formato(request, aceitos=(PDF, EXCEL)):
    """Lê ?formato= da URL. Sem o parâmetro, o relatório sai em PDF."""
    formato = request.GET.get("formato", aceitos[0])
    if formato not in aceitos:
        raise Http404("Formato de relatório inválido.")
    return formato


def baixar(relatorio, formato):
    """Gera o arquivo e responde com ele como download (ex.: boletim-2026001-2026-2.pdf)."""
    tipo, gerar = FORMATOS[formato]
    resposta = HttpResponse(gerar(relatorio), content_type=tipo)
    resposta["Content-Disposition"] = content_disposition_header(
        True, f"{relatorio.nome_arquivo}.{formato}"
    )
    return resposta


def riscos_com_aluno():
    return RiscoEvasao.objects.select_related("matricula__aluno", "matricula__turma").order_by(
        "-probabilidade"
    )


class EscolhaDeTurmaForm(forms.Form):
    turma = forms.ModelChoiceField(queryset=Turma.objects.select_related("curso"))


# --- Tela da coordenação ---


@login_required
@perfil_requerido("COORDENADOR")
def inicio(request):
    return render(
        request,
        "relatorios/inicio.html",
        {
            "turmas": Turma.objects.select_related("curso").order_by("-semestre", "codigo"),
            "niveis": RiscoEvasao.Nivel.choices,
            "situacoes_matricula": Matricula.Situacao.choices,
            "selos": SELOS,
            "risco_calculado": RiscoEvasao.objects.exists(),
        },
    )


# --- Downloads ---


@login_required
@perfil_requerido("ALUNO")
def meu_boletim(request):
    matricula = Matricula.atual_de(request.user)
    if matricula is None:
        return redirect("aluno:notas")  # a tela explica que ainda não há matrícula ativa
    return baixar(dados.boletim(matricula), PDF)


@login_required
@perfil_requerido("COORDENADOR")
def boletim(request, pk):
    matricula = get_object_or_404(Matricula.objects.select_related("aluno", "turma__curso"), pk=pk)
    return baixar(dados.boletim(matricula), PDF)


@login_required
@perfil_requerido("PROFESSOR")
def disciplina(request, pk):
    oferta = oferta_do_professor(request.user, pk)
    return baixar(dados.desempenho_da_disciplina(oferta), ler_formato(request))


@login_required
@perfil_requerido("COORDENADOR")
def turma(request):
    formato = ler_formato(request)
    form = EscolhaDeTurmaForm(request.GET)
    if not form.is_valid():
        messages.error(request, "Escolha uma turma para gerar o relatório de desempenho.")
        return redirect("relatorios:inicio")
    return baixar(dados.desempenho_da_turma(form.cleaned_data["turma"]), formato)


@login_required
@perfil_requerido("COORDENADOR")
def risco(request):
    formato = ler_formato(request)
    filtro = RiscoFiltro(request.GET, queryset=riscos_com_aluno())
    return baixar(dados.alunos_em_risco(filtro.qs, descrever(filtro)), formato)


@login_required
@perfil_requerido("COORDENADOR")
def alunos(request):
    formato = ler_formato(request, aceitos=(EXCEL,))
    filtro = MatriculaFiltro(request.GET, queryset=Matricula.objects.all())
    # O selo é calculado, então é filtrado depois do cálculo (o mesmo ?situacao= da tela Alunos).
    selo = request.GET.get("situacao", "")
    if selo not in SELOS:
        selo = ""
    return baixar(dados.lista_de_alunos(filtro.qs, selo, descrever(filtro)), formato)
