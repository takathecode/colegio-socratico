"""Telas da Secretaria: administração dos acessos de alunos, professores e coordenadores.

Todas usam @perfil_requerido("SECRETARIA"): os outros perfis recebem 403.
Toda ação sobre uma conta busca a conta em servicos.contas_gerenciaveis(): conta de
administrador, de equipe (staff) ou de outra Secretaria responde 404, mesmo que alguém
monte o pedido à mão. Esconder o botão não basta; quem protege é a consulta.
Cada ação sensível fica no registro de auditoria (apps/contas/auditoria.py).
Contas nunca são apagadas, só desativadas, para não perder o histórico acadêmico.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.alertas.fila import enfileirar
from apps.contas import auditoria, redefinicao
from apps.contas.decorators import perfil_requerido
from apps.contas.envio_de_email import entrega_de_verdade
from apps.contas.mascara import mascarar_email
from apps.contas.models import BloqueioDeLogin, RegistroDeAuditoria, Usuario
from apps.contas.senhas import gerar_senha_provisoria
from apps.contas.tasks import avisar_troca_de_email

from . import servicos
from .forms import EDICAO_DO_PERFIL, NovoAlunoForm, NovoCoordenadorForm, NovoProfessorForm

Acao = RegistroDeAuditoria.Acao
ITENS_POR_PAGINA = 25

# Tipo de conta na URL (contas/nova/<tipo>/) → formulário e textos da tela.
FORM_DO_TIPO = {
    "aluno": (NovoAlunoForm, "Nova conta de aluno", "A matrícula na turma é feita depois pela coordenação."),
    "professor": (NovoProfessorForm, "Nova conta de professor", "A coordenação liga o professor às disciplinas."),
    "coordenacao": (NovoCoordenadorForm, "Nova conta de coordenação", "A conta terá acesso à área da coordenação."),
}

AVISO_DE_IDENTIDADE = "Confirme a identidade da pessoa com documento com foto antes de redefinir."


def nome_de(usuario):
    return usuario.get_full_name() or usuario.matricula


def conta_gerenciavel(pk):
    """A conta que a Secretaria pode alterar, ou 404 (admin, staff, Secretaria ou inexistente)."""
    return get_object_or_404(servicos.contas_gerenciaveis(), pk=pk)


# --- Visão geral ---


@login_required
@perfil_requerido("SECRETARIA")
def painel(request):
    contas = servicos.contas_gerenciaveis()
    por_perfil = dict(
        contas.filter(is_active=True).order_by().values_list("perfil").annotate(total=Count("id"))
    )
    bloqueadas = servicos.matriculas_bloqueadas()
    return render(
        request,
        "secretaria/painel.html",
        {
            "alunos": por_perfil.get(Usuario.Perfil.ALUNO, 0),
            "professores": por_perfil.get(Usuario.Perfil.PROFESSOR, 0),
            "coordenadores": por_perfil.get(Usuario.Perfil.COORDENADOR, 0),
            "desativadas": contas.filter(is_active=False).count(),
            "bloqueadas": list(contas.filter(matricula__in=bloqueadas).order_by("first_name")),
            "troca_pendente": list(
                contas.filter(is_active=True, precisa_trocar_senha=True).order_by("first_name")[:10]
            ),
            "sem_email": contas.filter(is_active=True, email="").count(),
            "ultimas_acoes": RegistroDeAuditoria.objects.filter(conta__in=contas)
            .select_related("autor", "conta")[:10],
        },
    )


# --- Contas ---


@login_required
@perfil_requerido("SECRETARIA")
def contas(request):
    lista = servicos.contas_gerenciaveis().order_by("first_name", "last_name", "matricula")
    busca = request.GET.get("busca", "").strip()
    perfil = request.GET.get("perfil", "")
    estado = request.GET.get("estado", "")
    if perfil in servicos.PERFIS_GERENCIAVEIS:
        lista = lista.filter(perfil=perfil)
    bloqueadas = servicos.matriculas_bloqueadas()
    if estado in ("ativas", "inativas"):
        lista = lista.filter(is_active=estado == "ativas")
    elif estado == "bloqueadas":
        lista = lista.filter(matricula__in=bloqueadas)
    elif estado == "troca":
        lista = lista.filter(precisa_trocar_senha=True)
    lista = servicos.filtrar_por_busca(lista, busca)

    pagina = Paginator(lista, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    for conta in pagina:
        conta.bloqueada = conta.matricula in bloqueadas
    return render(
        request,
        "secretaria/contas.html",
        {
            "pagina": pagina,
            "total": pagina.paginator.count,
            "perfis": [(p.value, p.label) for p in servicos.PERFIS_GERENCIAVEIS],
            "busca": busca,
            "perfil": perfil,
            "estado": estado,
            "filtrando": bool(busca or perfil or estado),
        },
    )


def guardar_senha_e_mostrar(request, conta, senha, acao):
    """Guarda a senha provisória na sessão (no servidor) e abre a tela que a mostra uma vez."""
    request.session["senha_provisoria"] = {
        "pk": conta.pk,
        "nome": nome_de(conta),
        "matricula": conta.matricula,
        "perfil": conta.get_perfil_display(),
        "senha": senha,
        "acao": acao,
    }
    return redirect("secretaria:senha_provisoria")


@login_required
@perfil_requerido("SECRETARIA")
def conta_nova(request, tipo):
    if tipo not in FORM_DO_TIPO:
        raise Http404("Tipo de conta desconhecido.")
    form_classe, titulo, subtitulo = FORM_DO_TIPO[tipo]
    form = form_classe(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            with transaction.atomic():
                conta = form.save()
                auditoria.registrar(request, conta, Acao.CONTA_CRIADA, conta.get_perfil_display())
                auditoria.registrar(request, conta, Acao.SENHA_PROVISORIA)
            return guardar_senha_e_mostrar(request, conta, form.senha_provisoria, "criada")
        messages.error(request, "Não foi possível criar a conta. Confira os campos destacados.")
    return render(
        request,
        "secretaria/formulario.html",
        {
            "form": form,
            "titulo": titulo,
            "subtitulo": subtitulo,
            "voltar": reverse("secretaria:contas"),
            "botao": "Criar conta",
            "criando": True,
        },
    )


@login_required
@perfil_requerido("SECRETARIA")
def conta(request, pk):
    """Detalhe da conta: dados de acesso, ações de senha e o histórico de auditoria."""
    conta = conta_gerenciavel(pk)
    bloqueio = BloqueioDeLogin.objects.filter(
        matricula=conta.matricula, bloqueado_ate__gt=timezone.now()
    ).first()
    historico = conta.historico_de_acesso.select_related("autor")
    return render(
        request,
        "secretaria/conta.html",
        {
            "conta": conta,
            "bloqueio": bloqueio,
            "historico": Paginator(historico, ITENS_POR_PAGINA).get_page(request.GET.get("pagina")),
            "aviso_de_identidade": AVISO_DE_IDENTIDADE,
            # Sem SMTP no servidor publicado, o link não chega: a tela avisa antes do clique.
            "email_sem_entrega": not entrega_de_verdade() and not settings.DEBUG,
        },
    )


@login_required
@perfil_requerido("SECRETARIA")
def conta_editar(request, pk):
    conta = conta_gerenciavel(pk)
    email_antigo = conta.email
    form = EDICAO_DO_PERFIL[conta.perfil](request.POST or None, instance=conta)
    voltar = reverse("secretaria:conta", args=[conta.pk])
    if request.method == "POST":
        if form.is_valid():
            with transaction.atomic():
                conta = form.save()
                mudou = [form.fields[nome].label for nome in form.changed_data if nome != "email"]
                if mudou:
                    auditoria.registrar(request, conta, Acao.DADOS_ALTERADOS, ", ".join(mudou))
                if conta.email != email_antigo:
                    # Mascarados: o histórico mostra que houve troca sem expor os endereços.
                    detalhe = f"De {mascarar_email(email_antigo) or 'sem e-mail'} para {mascarar_email(conta.email)}"
                    auditoria.registrar(request, conta, Acao.EMAIL_ALTERADO, detalhe)
                    if email_antigo:
                        # O endereço antigo fica sabendo da troca: se não foi pedida, a pessoa reage.
                        quando = timezone.now().isoformat()
                        transaction.on_commit(
                            lambda: enfileirar(avisar_troca_de_email, conta.pk, email_antigo, quando)
                        )
            messages.success(request, f"Dados de {nome_de(conta)} atualizados.")
            return redirect(voltar)
        messages.error(request, "Não foi possível salvar. Confira os campos destacados.")
    return render(
        request,
        "secretaria/formulario.html",
        {
            "form": form,
            "titulo": f"Editar conta de {conta.get_perfil_display().lower()}",
            "subtitulo": f"{nome_de(conta)} · matrícula {conta.matricula}",
            "voltar": voltar,
            "botao": "Salvar alterações",
        },
    )


@login_required
@perfil_requerido("SECRETARIA")
@require_POST
def conta_redefinir(request, pk):
    """Redefine a senha de outra pessoa: link por e-mail (recomendado) ou senha provisória.

    As duas opções exigem marcar que a identidade foi conferida com documento com foto.
    """
    conta = conta_gerenciavel(pk)
    voltar = redirect("secretaria:conta", conta.pk)
    acao = request.POST.get("acao")
    if acao not in ("link", "provisoria"):
        messages.error(request, "Escolha como redefinir a senha.")
        return voltar
    if request.POST.get("identidade") != "conferida":
        messages.error(request, AVISO_DE_IDENTIDADE)
        return voltar
    if not conta.is_active:
        messages.error(request, "Reative a conta antes de redefinir a senha.")
        return voltar

    if acao == "link":
        if not conta.email:
            messages.error(request, "A conta não tem e-mail. Edite a conta ou gere uma senha provisória.")
            return voltar
        valido_ate = redefinicao.enviar_link(request, conta)
        texto = (
            f"Link enviado para {mascarar_email(conta.email)}. "
            f"Ele vale até {timezone.localtime(valido_ate):%H:%M}."
        )
        if entrega_de_verdade():
            messages.success(request, texto)
        elif settings.DEBUG:
            messages.info(request, f"{texto} Em desenvolvimento, o e-mail aparece no terminal do runserver.")
        else:
            # Sem SMTP o e-mail não chega: melhor avisar do que dizer que deu certo.
            messages.warning(
                request,
                "O envio de e-mails ainda não está configurado neste servidor, então o link não "
                "chega à pessoa. Use \"Gerar senha provisória\" e entregue a senha pessoalmente.",
            )
        return voltar

    senha = gerar_senha_provisoria(conta)
    with transaction.atomic():
        # set_password guarda só o hash. Trocar a senha encerra as sessões abertas da conta,
        # apaga o token da API e desbloqueia o login (Usuario.save).
        conta.set_password(senha)
        conta.precisa_trocar_senha = True
        conta.save(update_fields=["password", "precisa_trocar_senha"])
        auditoria.registrar(request, conta, Acao.SENHA_PROVISORIA)
    return guardar_senha_e_mostrar(request, conta, senha, "redefinida")


@login_required
@perfil_requerido("SECRETARIA")
@require_POST
def conta_desbloquear(request, pk):
    """Libera na hora o login bloqueado por 5 senhas erradas."""
    conta = conta_gerenciavel(pk)
    apagados, _ = BloqueioDeLogin.objects.filter(matricula=conta.matricula).delete()
    if apagados:
        auditoria.registrar(request, conta, Acao.DESBLOQUEIO)
        messages.success(request, f"Login de {nome_de(conta)} desbloqueado.")
    else:
        messages.info(request, "Esta matrícula não estava bloqueada.")
    return redirect("secretaria:conta", conta.pk)


@login_required
@perfil_requerido("SECRETARIA")
@require_POST
def conta_alternar_ativa(request, pk):
    """Desativa (a pessoa não entra mais) ou reativa uma conta. Nada é apagado."""
    conta = conta_gerenciavel(pk)
    if not conta.is_active and conta.email and servicos.email_em_uso(conta.email, exceto=conta):
        messages.error(
            request,
            "Outra conta ativa já usa o e-mail desta conta. Troque o e-mail antes de reativá-la.",
        )
        return redirect("secretaria:conta", conta.pk)
    with transaction.atomic():
        conta.is_active = not conta.is_active
        conta.save(update_fields=["is_active"])
        auditoria.registrar(request, conta, Acao.REATIVACAO if conta.is_active else Acao.DESATIVACAO)
    estado = "reativada" if conta.is_active else "desativada"
    messages.success(request, f"Conta de {nome_de(conta)} {estado}.")
    return redirect("secretaria:conta", conta.pk)


@login_required
@perfil_requerido("SECRETARIA")
def senha_provisoria(request):
    """Mostra a senha uma única vez: ela é retirada da sessão ao abrir a página."""
    dados = request.session.pop("senha_provisoria", None)
    if dados is None:
        return redirect("secretaria:contas")
    return render(request, "secretaria/senha_provisoria.html", {"dados": dados})
