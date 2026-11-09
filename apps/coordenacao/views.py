"""Telas da área da coordenação.

Todas usam @perfil_requerido("COORDENADOR"): os outros perfis recebem 403.
Contas nunca são apagadas por aqui, só desativadas, para não perder o histórico acadêmico.
Turmas, disciplinas e ofertas só podem ser excluídas enquanto não têm registros ligados.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.academico.calculos import (
    EM_RISCO,
    GRAVIDADE,
    indicadores_da_turma,
    resumo_das_matriculas,
)
from apps.academico.models import Disciplina, Justificativa, Matricula, Oferta, Turma
from apps.academico.utilidades import saudacao
from apps.contas.decorators import perfil_requerido
from apps.contas.models import Usuario

from . import servicos
from .forms import (
    FORM_DO_PERFIL,
    AlunoForm,
    CoordenadorForm,
    DisciplinaForm,
    OfertaForm,
    ProfessorForm,
    TurmaForm,
)

ITENS_POR_PAGINA = 25

# Para onde cada perfil volta depois de editar, e qual rota edita a conta.
LISTA_DO_PERFIL = {
    Usuario.Perfil.ALUNO: "coordenacao:alunos",
    Usuario.Perfil.PROFESSOR: "coordenacao:professores",
    Usuario.Perfil.COORDENADOR: "coordenacao:contas",
}
EDICAO_DO_PERFIL = {
    Usuario.Perfil.ALUNO: "coordenacao:aluno_editar",
    Usuario.Perfil.PROFESSOR: "coordenacao:professor_editar",
    Usuario.Perfil.COORDENADOR: "coordenacao:coordenador_editar",
}


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


def guardar_senha_e_mostrar(request, usuario, senha, acao):
    """Guarda a senha provisória na sessão (no servidor) e abre a tela que a mostra uma vez."""
    request.session["senha_provisoria"] = {
        "nome": nome_de(usuario),
        "matricula": usuario.matricula,
        "perfil": usuario.get_perfil_display(),
        "senha": senha,
        "acao": acao,
        "voltar": reverse(LISTA_DO_PERFIL[usuario.perfil]),
    }
    return redirect("coordenacao:senha_provisoria")


def nova_conta(request, form_classe, *, titulo, subtitulo):
    form = form_classe(request.POST or None)

    def ao_salvar(usuario):
        return guardar_senha_e_mostrar(request, usuario, form.senha_provisoria, "criada")

    return tela_de_formulario(
        request,
        form,
        titulo=titulo,
        subtitulo=subtitulo,
        voltar=reverse(LISTA_DO_PERFIL[form_classe.perfil]),
        botao="Criar conta",
        ao_salvar=ao_salvar,
    )


def editar_conta(request, pk, perfil):
    usuario = get_object_or_404(Usuario, pk=pk, perfil=perfil)
    form = FORM_DO_PERFIL[perfil](request.POST or None, instance=usuario)
    lista = reverse(LISTA_DO_PERFIL[perfil])

    def ao_salvar(usuario):
        messages.success(request, f"Dados de {nome_de(usuario)} atualizados.")
        return redirect(lista)

    return tela_de_formulario(
        request,
        form,
        titulo=f"Editar {usuario.get_perfil_display().lower()}",
        subtitulo=f"{nome_de(usuario)} · matrícula {usuario.matricula}",
        voltar=lista,
        botao="Salvar alterações",
        ao_salvar=ao_salvar,
    )


# --- Visão geral ---


@login_required
@perfil_requerido("COORDENADOR")
def painel(request):
    matriculas = servicos.matriculas_ativas()
    resumo = resumo_das_matriculas(matriculas)

    # Linhas por turma, no formato que indicadores_da_turma() espera.
    linhas_por_turma = {}
    em_risco = []
    for matricula in matriculas:
        linha = {"matricula": matricula, **resumo[matricula.pk]}
        linhas_por_turma.setdefault(matricula.turma_id, []).append(linha)
        if linha["situacao"] == EM_RISCO:
            em_risco.append(linha)
    em_risco.sort(key=lambda linha: (-linha["disciplinas_em_risco"], linha["frequencia"] or 0))

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
            "em_risco": em_risco[:8],
        },
    )


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
        },
    )


@login_required
@perfil_requerido("COORDENADOR")
def aluno_novo(request):
    if not Turma.objects.exists():
        messages.warning(request, "Cadastre uma turma antes de matricular alunos.")
        return redirect("coordenacao:turma_nova")
    return nova_conta(
        request,
        AlunoForm,
        titulo="Novo aluno",
        subtitulo="Cria a conta do aluno e a matrícula dele na turma.",
    )


@login_required
@perfil_requerido("COORDENADOR")
def aluno_editar(request, pk):
    return editar_conta(request, pk, Usuario.Perfil.ALUNO)


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


@login_required
@perfil_requerido("COORDENADOR")
def professor_novo(request):
    return nova_conta(
        request,
        ProfessorForm,
        titulo="Novo professor",
        subtitulo="Depois de criar a conta, ligue o professor às disciplinas na tela da turma.",
    )


@login_required
@perfil_requerido("COORDENADOR")
def professor_editar(request, pk):
    return editar_conta(request, pk, Usuario.Perfil.PROFESSOR)


# --- Contas ---


@login_required
@perfil_requerido("COORDENADOR")
def contas(request):
    lista = servicos.contas_gerenciadas().order_by("first_name", "last_name")
    busca = request.GET.get("busca", "").strip()
    perfil = request.GET.get("perfil", "")
    estado = request.GET.get("estado", "")
    if perfil in servicos.PERFIS_GERENCIADOS:
        lista = lista.filter(perfil=perfil)
    if estado in ("ativas", "inativas"):
        lista = lista.filter(is_active=estado == "ativas")
    lista = servicos.filtrar_por_busca(list(lista), busca)
    for conta in lista:
        conta.url_editar = reverse(EDICAO_DO_PERFIL[conta.perfil], args=[conta.pk])

    return render(
        request,
        "coordenacao/contas.html",
        {
            "pagina": paginar(request, lista),
            "total": len(lista),
            "perfis": [(p.value, p.label) for p in servicos.PERFIS_GERENCIADOS],
            "busca": busca,
            "perfil": perfil,
            "estado": estado,
            "filtrando": bool(busca or perfil or estado),
        },
    )


@login_required
@perfil_requerido("COORDENADOR")
def coordenador_novo(request):
    return nova_conta(
        request,
        CoordenadorForm,
        titulo="Nova conta de coordenação",
        subtitulo="A conta terá acesso a toda a área da coordenação.",
    )


@login_required
@perfil_requerido("COORDENADOR")
def coordenador_editar(request, pk):
    return editar_conta(request, pk, Usuario.Perfil.COORDENADOR)


def conta_de_outra_pessoa(request, pk):
    """Conta gerenciada pela coordenação. A própria conta fica de fora dessas ações."""
    conta = get_object_or_404(servicos.contas_gerenciadas(), pk=pk)
    if conta == request.user:
        messages.error(
            request, "Você não pode fazer isso com a sua própria conta. Peça a outro coordenador."
        )
        return None
    return conta


def voltar_para(request, padrao="coordenacao:contas"):
    """Volta para a página que enviou o formulário (campo "proxima"), se ela for do próprio site."""
    proxima = request.POST.get("proxima", "")
    if url_has_allowed_host_and_scheme(proxima, allowed_hosts={request.get_host()}):
        return redirect(proxima)
    return redirect(padrao)


@login_required
@perfil_requerido("COORDENADOR")
@require_POST
def conta_nova_senha(request, pk):
    conta = conta_de_outra_pessoa(request, pk)
    if conta is None:
        return voltar_para(request)
    senha = servicos.gerar_senha_provisoria()
    # Trocar a senha também encerra as sessões abertas daquela conta.
    conta.set_password(senha)
    conta.save(update_fields=["password"])
    return guardar_senha_e_mostrar(request, conta, senha, "redefinida")


@login_required
@perfil_requerido("COORDENADOR")
@require_POST
def conta_alternar_ativa(request, pk):
    """Desativa (a pessoa não entra mais) ou reativa uma conta. Nada é apagado."""
    conta = conta_de_outra_pessoa(request, pk)
    if conta is None:
        return voltar_para(request)
    conta.is_active = not conta.is_active
    conta.save(update_fields=["is_active"])
    estado = "reativada" if conta.is_active else "desativada"
    messages.success(request, f"Conta de {nome_de(conta)} {estado}.")
    return voltar_para(request)


@login_required
@perfil_requerido("COORDENADOR")
def senha_provisoria(request):
    """Mostra a senha uma única vez: ela é retirada da sessão ao abrir a página."""
    dados = request.session.pop("senha_provisoria", None)
    if dados is None:
        return redirect("coordenacao:contas")
    return render(request, "coordenacao/senha_provisoria.html", {"dados": dados})


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
