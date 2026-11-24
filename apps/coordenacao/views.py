"""Telas da área da coordenação.

Todas usam @perfil_requerido("COORDENADOR"): os outros perfis recebem 403.
A coordenação cuida do cadastro acadêmico (matrículas, turmas, disciplinas, professores das
disciplinas). As contas de acesso (criar, nome, e-mail, senha, desativar) são da Secretaria.
Turmas, disciplinas e ofertas só podem ser excluídas enquanto não têm registros ligados.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academico.calculos import GRAVIDADE, indicadores_da_turma, resumo_das_matriculas
from apps.academico.models import Disciplina, Justificativa, Matricula, Oferta, Turma
from apps.academico.utilidades import saudacao
from apps.alertas import tasks as alertas_tasks
from apps.alertas.fila import enfileirar
from apps.alertas.models import Alerta
from apps.analytics import evasao
from apps.analytics.dados import frequencia_mensal_por_turma
from apps.analytics.graficos import evolucao_da_frequencia
from apps.analytics.models import RiscoEvasao
from apps.contas.decorators import perfil_requerido
from apps.contas.models import Usuario
from apps.relatorios.filtros import RiscoFiltro
from apps.videochamadas.models import Chamada, nome_na_chamada

from . import servicos
from .forms import DisciplinaForm, MatriculaDoAlunoForm, OfertaForm, TurmaForm

ITENS_POR_PAGINA = 25

def paginar(request, itens):
    return Paginator(itens, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))


def nome_de(usuario):
    return usuario.get_full_name() or usuario.matricula


# --- Funções auxiliares usadas por vários CRUDs ---


def tela_de_formulario(request, form, *, titulo, subtitulo, voltar, botao, ao_salvar):
    """Mostra um formulário e, quando ele é enviado sem erros, chama ao_salvar.

    ao_salvar(objeto) devolve a resposta (normalmente um redirect) depois de salvar.
    """
    if request.method == "POST":
        if form.is_valid():
            return ao_salvar(form.save())
        messages.error(request, "Não foi possível salvar. Confira os campos destacados.")
    return render(
        request,
        "coordenacao/formulario.html",
        {
            "form": form,
            "titulo": titulo,
            "subtitulo": subtitulo,
            "voltar": voltar,
            "botao": botao,
        },
    )


def tela_de_exclusao(request, objeto, *, descricao, voltar, depois):
    """Pede confirmação (GET) e exclui (POST).

    Os modelos usam PROTECT: se algo depende do objeto (ex.: uma turma com alunos),
    o Django recusa a exclusão com ProtectedError, e a tela explica o motivo.
    """
    if request.method == "POST":
        try:
            objeto.delete()
        except ProtectedError as erro:
            # Nomes dos tipos de registro que impedem a exclusão, como "matrículas".
            ligados = sorted({str(item._meta.verbose_name_plural) for item in erro.protected_objects})
            messages.error(
                request,
                f"Não foi possível excluir {descricao}, pois ela já tem registros ligados "
                f"({', '.join(ligados)}). Remova esses registros antes.",
            )
            return redirect(voltar)
        messages.success(request, f"{descricao[0].upper()}{descricao[1:]} excluída.")
        return redirect(depois)
    return render(
        request,
        "coordenacao/confirmar_exclusao.html",
        {"descricao": descricao, "voltar": voltar},
    )


# --- Visão geral ---


@login_required
@perfil_requerido("COORDENADOR")
def painel(request):
    matriculas = servicos.matriculas_ativas()
    resumo = resumo_das_matriculas(matriculas)

    # Linhas por turma, no formato que indicadores_da_turma() espera.
    linhas_por_turma = {}
    for matricula in matriculas:
        linha = {"matricula": matricula, **resumo[matricula.pk]}
        linhas_por_turma.setdefault(matricula.turma_id, []).append(linha)

    turmas = list(servicos.turmas_com_contagens().filter(semestre=servicos.semestre_atual()))
    for turma in turmas:
        turma.indicadores = indicadores_da_turma(linhas_por_turma.get(turma.pk, []))

    todas = [linha for linhas in linhas_por_turma.values() for linha in linhas]
    return render(
        request,
        "coordenacao/painel.html",
        {
            "saudacao": saudacao(),
            "semestre": servicos.semestre_atual(),
            "indicadores": indicadores_da_turma(todas),
            "total_professores": Usuario.objects.filter(
                perfil=Usuario.Perfil.PROFESSOR, is_active=True
            ).count(),
            "total_pendentes": Justificativa.objects.filter(
                status=Justificativa.Status.PENDENTE
            ).count(),
            "turmas": turmas,
            "grafico_frequencia": evolucao_da_frequencia(frequencia_mensal_por_turma(turmas)),
            # Os alunos com maior probabilidade de evasão, calculada pelo modelo preditivo.
            "maiores_riscos": list(
                riscos_com_aluno().exclude(nivel=RiscoEvasao.Nivel.BAIXO)[:8]
            ),
            "risco_calculado": RiscoEvasao.objects.exists(),
        },
    )


# --- Alunos em risco (módulo preditivo, apps/analytics/evasao.py) ---


def riscos_com_aluno():
    return RiscoEvasao.objects.select_related(
        "matricula__aluno", "matricula__turma"
    ).order_by("-probabilidade")


def marcar_professores_para_chamar(riscos):
    """Botão "Chamar professor sobre este aluno": os professores ativos da turma de cada aluno.

    Uma consulta para a página inteira. Cada risco ganha a lista chamar_professores, com o
    link para Videochamadas já com o professor e o assunto escolhidos (?para= e ?assunto=). Um
    professor com duas disciplinas na turma aparece uma vez só, com as duas.
    """
    turmas = {risco.matricula.turma_id for risco in riscos}
    professores_por_turma = {}
    ofertas = (
        Oferta.objects.filter(turma_id__in=turmas, professor__is_active=True)
        .select_related("professor", "disciplina")
        .order_by("professor__first_name", "professor__last_name", "disciplina__nome")
    )
    for oferta in ofertas:
        da_turma = professores_por_turma.setdefault(oferta.turma_id, {})
        item = da_turma.setdefault(
            oferta.professor_id, {"professor": oferta.professor, "disciplinas": []}
        )
        item["disciplinas"].append(oferta.disciplina.nome)

    endereco = reverse("videochamadas:inicio")
    limite = Chamada._meta.get_field("assunto").max_length
    for risco in riscos:
        aluno = risco.matricula.aluno
        assunto = f"Aluno em risco: {aluno.get_full_name() or aluno.matricula} (RA {aluno.matricula})"
        risco.chamar_professores = [
            {
                "nome": nome_na_chamada(item["professor"]),
                "disciplinas": ", ".join(item["disciplinas"]),
                "url": f"{endereco}?{urlencode({'para': item['professor'].pk, 'assunto': assunto[:limite]})}",
            }
            for item in professores_por_turma.get(risco.matricula.turma_id, {}).values()
        ]


@login_required
@perfil_requerido("COORDENADOR")
def risco(request):
    riscos = riscos_com_aluno()
    # Quantos alunos há em cada nível, antes dos filtros, para os cards do topo.
    por_nivel = dict(
        RiscoEvasao.objects.order_by().values_list("nivel").annotate(total=Count("id"))
    )
    total_calculado = sum(por_nivel.values())

    busca = request.GET.get("busca", "").strip()
    turma = request.GET.get("turma", "")
    nivel = request.GET.get("nivel", "")
    # O mesmo filtro do relatório (apps/relatorios/filtros.py): o PDF traz a lista da tela.
    riscos = list(RiscoFiltro(request.GET, queryset=riscos).qs)
    filtros_usados = {"busca": busca, "turma": turma, "nivel": nivel}
    pagina = paginar(request, riscos)
    marcar_professores_para_chamar(pagina.object_list)

    return render(
        request,
        "coordenacao/risco.html",
        {
            "pagina": pagina,
            "total": len(riscos),
            "modelo_treinado": evasao.modelo_treinado(),
            "alto": por_nivel.get(RiscoEvasao.Nivel.ALTO, 0),
            "medio": por_nivel.get(RiscoEvasao.Nivel.MEDIO, 0),
            "baixo": por_nivel.get(RiscoEvasao.Nivel.BAIXO, 0),
            "total_calculado": total_calculado,
            "calculado_em": RiscoEvasao.objects.aggregate(ultimo=Max("calculado_em"))["ultimo"],
            # Alunos ativos sem nota ou sem chamada ficam fora do cálculo.
            "sem_dados": Matricula.objects.filter(situacao=Matricula.Situacao.ATIVA).count()
            - total_calculado,
            "turmas": Turma.objects.filter(matriculas__risco__isnull=False)
            .distinct()
            .order_by("-semestre", "codigo"),
            "niveis": RiscoEvasao.Nivel.choices,
            "limite_medio": evasao.LIMITE_MEDIO,
            "limite_alto": evasao.LIMITE_ALTO,
            "busca": busca,
            "turma": turma,
            "nivel": nivel,
            "filtrando": bool(busca or turma or nivel),
            # Parâmetros dos botões PDF e Excel, como "turma=3&nivel=ALTO".
            "consulta": urlencode({chave: valor for chave, valor in filtros_usados.items() if valor}),
        },
    )


@login_required
@perfil_requerido("COORDENADOR")
@require_POST
def risco_recalcular(request):
    """Roda o modelo de novo para todos os alunos ativos (o mesmo que calcular_riscos)."""
    try:
        total = evasao.calcular_riscos()
    except evasao.ModeloNaoTreinado:
        messages.error(
            request,
            "O modelo de evasão ainda não foi treinado. "
            "Rode python manage.py treinar_modelo no servidor.",
        )
    else:
        messages.success(request, f"Risco de evasão recalculado para {total} aluno(s).")
    return redirect("coordenacao:risco")


# --- Central de alertas (apps/alertas) ---


@login_required
@perfil_requerido("COORDENADOR")
def alertas(request):
    """Todos os alertas enviados pelo sistema, para a coordenação acompanhar quem foi avisado."""
    todos = Alerta.objects.select_related("destinatario")
    semana = todos.filter(criado_em__gte=timezone.now() - timedelta(days=7))
    indicadores = semana.aggregate(
        total=Count("id"),
        em_risco=Count("id", filter=Q(gravidade=Alerta.Gravidade.RISCO)),
        emails=Count("id", filter=Q(email_enviado_em__isnull=False)),
        nao_lidos=Count("id", filter=Q(lido_em__isnull=True)),
    )

    busca = request.GET.get("busca", "").strip()
    tipo = request.GET.get("tipo", "")
    leitura = request.GET.get("leitura", "")
    lista = todos
    if tipo in Alerta.Tipo.values:
        lista = lista.filter(tipo=tipo)
    if leitura == "nao_lidos":
        lista = lista.filter(lido_em__isnull=True)
    elif leitura == "lidos":
        lista = lista.filter(lido_em__isnull=False)
    if busca:
        lista = lista.filter(
            Q(destinatario__first_name__icontains=busca)
            | Q(destinatario__last_name__icontains=busca)
            | Q(destinatario__matricula__icontains=busca)
            | Q(titulo__icontains=busca)
        )

    return render(
        request,
        "coordenacao/alertas.html",
        {
            "pagina": paginar(request, lista),
            "indicadores": indicadores,
            "tipos": Alerta.Tipo.choices,
            "busca": busca,
            "tipo": tipo,
            "leitura": leitura,
            "filtrando": bool(busca or tipo or leitura),
            "sem_redis": settings.CELERY_TASK_ALWAYS_EAGER,
        },
    )


@login_required
@perfil_requerido("COORDENADOR")
@require_POST
def alertas_rotina(request):
    """Coloca na fila a mesma rotina que o Celery agenda para as 6h."""
    enfileirar(alertas_tasks.rotina_diaria)
    messages.success(
        request,
        "Rotina de alertas iniciada: o risco de evasão é recalculado e os alertas novos "
        "aparecem nesta lista em instantes. Atualize a página para ver.",
    )
    return redirect("coordenacao:alertas")


# --- Alunos ---


@login_required
@perfil_requerido("COORDENADOR")
def alunos(request):
    linhas = servicos.linhas_de_alunos()
    turmas = list(Turma.objects.order_by("-semestre", "codigo"))

    busca = request.GET.get("busca", "").strip()
    turma = request.GET.get("turma", "")
    situacao = request.GET.get("situacao", "")
    linhas = servicos.filtrar_por_busca(linhas, busca, lambda linha: linha["aluno"])
    if turma.isdecimal():
        linhas = [
            linha
            for linha in linhas
            if linha["matricula"] and linha["matricula"].turma_id == int(turma)
        ]
    if situacao in servicos.SITUACOES:
        linhas = [linha for linha in linhas if linha["situacao"] == situacao]

    return render(
        request,
        "coordenacao/alunos.html",
        {
            "pagina": paginar(request, linhas),
            "total": len(linhas),
            "turmas": turmas,
            "situacoes": servicos.SITUACOES,
            "busca": busca,
            "turma": turma,
            "situacao": situacao,
            "filtrando": bool(busca or turma or situacao),
            # Parâmetros do botão Excel (o relatório entende os mesmos nomes).
            "consulta": urlencode(
                {
                    chave: valor
                    for chave, valor in {"busca": busca, "turma": turma, "situacao": situacao}.items()
                    if valor
                }
            ),
        },
    )


@login_required
@perfil_requerido("COORDENADOR")
def aluno_editar(request, pk):
    """Matrícula do aluno: turma e situação. A conta (nome, e-mail, senha) é da Secretaria."""
    aluno = get_object_or_404(Usuario, pk=pk, perfil=Usuario.Perfil.ALUNO)
    if not Turma.objects.exists():
        messages.warning(request, "Cadastre uma turma antes de matricular alunos.")
        return redirect("coordenacao:turma_nova")
    form = MatriculaDoAlunoForm(request.POST or None, aluno=aluno)
    nome = aluno.get_full_name() or aluno.matricula

    def ao_salvar(matricula):
        messages.success(request, f"Matrícula de {nome} atualizada.")
        return redirect("coordenacao:alunos")

    return tela_de_formulario(
        request,
        form,
        titulo="Matrícula do aluno" if form.matricula_atual else "Matricular aluno",
        subtitulo=f"{nome} · RA {aluno.matricula}",
        voltar=reverse("coordenacao:alunos"),
        botao="Salvar matrícula",
        ao_salvar=ao_salvar,
    )


# --- Professores ---


@login_required
@perfil_requerido("COORDENADOR")
def professores(request):
    lista = Usuario.objects.filter(perfil=Usuario.Perfil.PROFESSOR).annotate(
        total_ofertas=Count("ofertas")
    )
    busca = request.GET.get("busca", "").strip()
    lista = servicos.filtrar_por_busca(
        sorted(lista, key=lambda professor: professor.get_full_name().casefold()), busca
    )
    return render(
        request,
        "coordenacao/professores.html",
        {"pagina": paginar(request, lista), "total": len(lista), "busca": busca},
    )


# --- Turmas e ofertas ---


@login_required
@perfil_requerido("COORDENADOR")
def turmas(request):
    return render(
        request,
        "coordenacao/turmas.html",
        {"turmas": servicos.turmas_com_contagens().order_by("-semestre", "codigo")},
    )


@login_required
@perfil_requerido("COORDENADOR")
def turma_nova(request):
    def ao_salvar(turma):
        messages.success(request, f"Turma {turma.codigo} criada. Agora adicione as disciplinas.")
        return redirect("coordenacao:turma", turma.pk)

    return tela_de_formulario(
        request,
        TurmaForm(request.POST or None),
        titulo="Nova turma",
        subtitulo="Depois de criar, adicione as disciplinas e os professores na tela da turma.",
        voltar=reverse("coordenacao:turmas"),
        botao="Criar turma",
        ao_salvar=ao_salvar,
    )


@login_required
@perfil_requerido("COORDENADOR")
def turma(request, pk):
    """Detalhe da turma: disciplinas oferecidas (com professor) e alunos matriculados."""
    turma = get_object_or_404(Turma.objects.select_related("curso"), pk=pk)
    form = OfertaForm(request.POST or None, turma=turma)
    if request.method == "POST":
        if form.is_valid():
            oferta = form.save()
            messages.success(request, f"{oferta.disciplina.nome} adicionada à turma.")
            return redirect("coordenacao:turma", turma.pk)
        messages.error(request, "A disciplina não foi adicionada. Confira os campos destacados.")

    ofertas = (
        turma.ofertas.select_related("disciplina", "professor")
        .annotate(total_avaliacoes=Count("avaliacoes", distinct=True))
        .order_by("disciplina__nome")
    )
    matriculas = list(
        Matricula.objects.filter(turma=turma)
        .select_related("aluno")
        .order_by("aluno__first_name", "aluno__last_name")
    )
    resumo = resumo_das_matriculas(matriculas)
    linhas = [{"matricula": m, **resumo[m.pk]} for m in matriculas]
    ativas = [linha for linha in linhas if linha["matricula"].situacao == Matricula.Situacao.ATIVA]
    linhas.sort(key=lambda linha: -GRAVIDADE[linha["situacao"]])  # quem precisa de ajuda primeiro

    return render(
        request,
        "coordenacao/turma.html",
        {
            "turma": turma,
            "ofertas": ofertas,
            "linhas": linhas,
            "indicadores": indicadores_da_turma(ativas),
            "form": form,
            "abrir_modal": form.is_bound,
            "pode_adicionar": form.fields["disciplina"].queryset.exists(),
        },
    )


@login_required
@perfil_requerido("COORDENADOR")
def turma_editar(request, pk):
    turma = get_object_or_404(Turma, pk=pk)
    voltar = reverse("coordenacao:turma", args=[pk])

    def ao_salvar(turma):
        messages.success(request, f"Turma {turma.codigo} atualizada.")
        return redirect(voltar)

    return tela_de_formulario(
        request,
        TurmaForm(request.POST or None, instance=turma),
        titulo="Editar turma",
        subtitulo=str(turma),
        voltar=voltar,
        botao="Salvar alterações",
        ao_salvar=ao_salvar,
    )


@login_required
@perfil_requerido("COORDENADOR")
def turma_excluir(request, pk):
    turma = get_object_or_404(Turma, pk=pk)
    return tela_de_exclusao(
        request,
        turma,
        descricao=f"a turma {turma}",
        voltar=reverse("coordenacao:turma", args=[pk]),
        depois="coordenacao:turmas",
    )


@login_required
@perfil_requerido("COORDENADOR")
def oferta_editar(request, pk):
    """Troca o professor de uma disciplina da turma."""
    oferta = get_object_or_404(Oferta.objects.select_related("turma", "disciplina"), pk=pk)
    voltar = reverse("coordenacao:turma", args=[oferta.turma_id])

    def ao_salvar(oferta):
        messages.success(request, f"Professor de {oferta.disciplina.nome} atualizado.")
        return redirect(voltar)

    return tela_de_formulario(
        request,
        OfertaForm(request.POST or None, turma=oferta.turma, instance=oferta),
        titulo="Trocar professor",
        subtitulo=f"{oferta.disciplina.nome} · Turma {oferta.turma.codigo}",
        voltar=voltar,
        botao="Salvar alterações",
        ao_salvar=ao_salvar,
    )


@login_required
@perfil_requerido("COORDENADOR")
def oferta_excluir(request, pk):
    oferta = get_object_or_404(Oferta.objects.select_related("turma", "disciplina"), pk=pk)
    voltar = reverse("coordenacao:turma", args=[oferta.turma_id])
    return tela_de_exclusao(
        request,
        oferta,
        descricao=f"a oferta de {oferta.disciplina.nome} na turma {oferta.turma.codigo}",
        voltar=voltar,
        depois=voltar,
    )


# --- Disciplinas ---


@login_required
@perfil_requerido("COORDENADOR")
def disciplinas(request):
    lista = Disciplina.objects.select_related("curso").annotate(total_turmas=Count("ofertas"))
    busca = request.GET.get("busca", "").strip()
    if busca:
        lista = lista.filter(Q(nome__icontains=busca) | Q(codigo__icontains=busca))
    return render(
        request,
        "coordenacao/disciplinas.html",
        {"disciplinas": lista.order_by("curso__nome", "nome"), "busca": busca},
    )


@login_required
@perfil_requerido("COORDENADOR")
def disciplina_nova(request):
    def ao_salvar(disciplina):
        messages.success(request, f"Disciplina {disciplina.nome} criada.")
        return redirect("coordenacao:disciplinas")

    return tela_de_formulario(
        request,
        DisciplinaForm(request.POST or None),
        titulo="Nova disciplina",
        subtitulo="A disciplina pode ser oferecida nas turmas do mesmo curso.",
        voltar=reverse("coordenacao:disciplinas"),
        botao="Criar disciplina",
        ao_salvar=ao_salvar,
    )


@login_required
@perfil_requerido("COORDENADOR")
def disciplina_editar(request, pk):
    disciplina = get_object_or_404(Disciplina, pk=pk)

    def ao_salvar(disciplina):
        messages.success(request, f"Disciplina {disciplina.nome} atualizada.")
        return redirect("coordenacao:disciplinas")

    return tela_de_formulario(
        request,
        DisciplinaForm(request.POST or None, instance=disciplina),
        titulo="Editar disciplina",
        subtitulo=str(disciplina),
        voltar=reverse("coordenacao:disciplinas"),
        botao="Salvar alterações",
        ao_salvar=ao_salvar,
    )


@login_required
@perfil_requerido("COORDENADOR")
def disciplina_excluir(request, pk):
    disciplina = get_object_or_404(Disciplina, pk=pk)
    return tela_de_exclusao(
        request,
        disciplina,
        descricao=f"a disciplina {disciplina.nome}",
        voltar=reverse("coordenacao:disciplinas"),
        depois="coordenacao:disciplinas",
    )
