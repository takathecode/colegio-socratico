from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetConfirmView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.alertas.fila import enfileirar

from . import auditoria, redefinicao
from .decorators import perfil_requerido
from .foto import pode_ver_foto, tipo_da_imagem
from .forms import (
    FormularioFoto,
    FormularioLogin,
    FormularioMatricula,
    FormularioNovaSenha,
    FormularioTrocaDeSenha,
)
from .mascara import mascarar_email
from .models import RegistroDeAuditoria, Usuario
from .tasks import avisar_senha_alterada
from .tokens import gerador_de_link

# Perfis que usam o portal (e têm avatar no topo). O ADMIN usa só o Django Admin.
PERFIS_DO_PORTAL = (
    Usuario.Perfil.ALUNO,
    Usuario.Perfil.PROFESSOR,
    Usuario.Perfil.COORDENADOR,
    Usuario.Perfil.SECRETARIA,
)

# Para onde cada perfil vai depois de entrar no sistema.
ROTA_POR_PERFIL = {
    Usuario.Perfil.ALUNO: "aluno:painel",
    Usuario.Perfil.PROFESSOR: "professor:painel",
    Usuario.Perfil.COORDENADOR: "coordenacao:painel",
    Usuario.Perfil.SECRETARIA: "secretaria:painel",
    Usuario.Perfil.ADMIN: "admin:index",
}

# Chaves da sessão entre as etapas do "Esqueci minha senha". A matrícula fica na sessão (no
# servidor), e não na URL, para não aparecer no histórico do navegador nem nos logs.
SESSAO_MATRICULA = "senha_matricula"
SESSAO_VALIDO_ATE = "senha_valido_ate"

MENSAGEM_NEUTRA = (
    "Não foi possível enviar o link para esta matrícula. Procure a Secretaria da escola."
)
MENSAGEM_LIMITE = (
    "Foram feitos muitos pedidos na última hora. Espere um pouco e tente de novo, "
    "ou procure a Secretaria da escola."
)


def inicio(request):
    """Endereço "/": manda cada pessoa para a área do seu perfil."""
    if not request.user.is_authenticated:
        return redirect("contas:entrar")
    rota = ROTA_POR_PERFIL.get(request.user.perfil)
    if rota is None:
        raise PermissionDenied
    return redirect(rota)


class EntrarView(LoginView):
    """Tela de login. Não existe tela de cadastro: as contas são criadas pela Secretaria."""

    template_name = "contas/login.html"
    authentication_form = FormularioLogin
    # Quem já está logado e abre o login vai direto para a sua área.
    redirect_authenticated_user = True

    def form_valid(self, form):
        resposta = super().form_valid(form)
        if form.cleaned_data["manter_conectado"]:
            # None usa o prazo padrão do Django (SESSION_COOKIE_AGE, 2 semanas).
            self.request.session.set_expiry(None)
        else:
            # 0 encerra a sessão quando o navegador é fechado.
            self.request.session.set_expiry(0)
        return resposta


def atendimento(request):
    """Orientações para quem não consegue entrar. A página é pública."""
    return render(request, "contas/atendimento.html")


# --- Esqueci minha senha (pela matrícula; regras em redefinicao.py) ---


def sem_referer(resposta):
    """Estas telas não contam a outros sites de onde a pessoa veio (cabeçalho Referer).

    "same-origin": o endereço da página só vai para o próprio portal; para outros sites
    (fontes do Google, ícones do CDN), nada. Assim o endereço com o código do link nunca vaza.

    Não use "no-referrer": com ele, o navegador envia "Origin: null" nos formulários (POST),
    e a proteção CSRF do Django recusa o envio com 403, porque não consegue confirmar que o
    formulário veio do próprio site. O teste test_formularios_passam_pelo_csrf_do_navegador
    (test_senha.py) protege contra essa volta.
    """
    resposta["Referrer-Policy"] = "same-origin"
    return resposta


@never_cache
@require_http_methods(["GET", "POST"])
def senha_esqueci(request):
    """Etapa 1: a pessoa digita a matrícula, que é guardada na sessão."""
    form = FormularioMatricula(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not redefinicao.pode_consultar(request):
            messages.error(request, MENSAGEM_LIMITE)
        else:
            matricula = form.cleaned_data["matricula"]
            redefinicao.registrar_consulta(request, matricula)
            request.session[SESSAO_MATRICULA] = matricula
            return redirect("contas:senha_confirmar")
    return sem_referer(render(request, "contas/senha_esqueci.html", {"form": form}))


@never_cache
@require_http_methods(["GET", "POST"])
def senha_confirmar(request):
    """Etapa 2: mostra o e-mail cadastrado, mascarado, e envia o link (POST).

    Matrícula inexistente, conta desativada e conta sem e-mail mostram a mesma mensagem.
    """
    matricula = request.session.get(SESSAO_MATRICULA)
    if not matricula:
        return redirect("contas:senha_esqueci")
    conta = redefinicao.conta_para_redefinir(matricula)

    if request.method == "POST" and conta is not None:
        if not redefinicao.pode_enviar(request, matricula):
            messages.error(request, MENSAGEM_LIMITE)
            return redirect("contas:senha_confirmar")
        valido_ate = redefinicao.enviar_link(request, conta)
        request.session[SESSAO_VALIDO_ATE] = valido_ate.isoformat()
        return redirect("contas:senha_enviada")

    contexto = {
        "matricula": matricula,
        "email_mascarado": mascarar_email(conta.email) if conta else "",
        "mensagem_neutra": MENSAGEM_NEUTRA,
    }
    return sem_referer(render(request, "contas/senha_confirmar.html", contexto))


@never_cache
@require_GET
def senha_enviada(request):
    """Etapa 3: "Verifique seu e-mail", com o horário em que o link deixa de valer."""
    valido_ate = request.session.get(SESSAO_VALIDO_ATE)
    matricula = request.session.get(SESSAO_MATRICULA)
    if not valido_ate or not matricula:
        return redirect("contas:senha_esqueci")
    conta = redefinicao.conta_para_redefinir(matricula)
    contexto = {
        "valido_ate": timezone.localtime(datetime.fromisoformat(valido_ate)),
        "minutos": settings.PASSWORD_RESET_TIMEOUT // 60,
        "email_mascarado": mascarar_email(conta.email) if conta else "",
    }
    return sem_referer(render(request, "contas/senha_enviada.html", contexto))


def avisar_troca_de_senha(usuario):
    """E-mail "Sua senha foi alterada em ...", pela fila, depois que a troca for gravada."""
    quando = timezone.now().isoformat()
    transaction.on_commit(lambda: enfileirar(avisar_senha_alterada, usuario.pk, quando))


class RedefinirSenhaView(PasswordResetConfirmView):
    """Etapa 4: o link do e-mail. A tela tem o visual do login e a matrícula travada.

    O PasswordResetConfirmView do Django confere o código, guarda-o na sessão e redireciona
    para um endereço sem ele (".../set-password/"): assim o código não fica no histórico do
    navegador nem vaza pelo cabeçalho Referer. Depois da troca, não entra sozinho no portal.
    """

    template_name = "contas/senha_redefinir.html"
    form_class = FormularioNovaSenha
    token_generator = gerador_de_link
    post_reset_login = False
    success_url = reverse_lazy("contas:entrar")

    def dispatch(self, *args, **kwargs):
        return sem_referer(super().dispatch(*args, **kwargs))

    def form_valid(self, form):
        resposta = super().form_valid(form)  # grava a senha (só o hash) e apaga o código da sessão
        usuario = form.user
        auditoria.registrar(
            self.request, usuario, RegistroDeAuditoria.Acao.SENHA_REDEFINIDA, autor=usuario
        )
        avisar_troca_de_senha(usuario)
        # Limpa as etapas anteriores: o próximo pedido começa do zero.
        for chave in (SESSAO_MATRICULA, SESSAO_VALIDO_ATE):
            self.request.session.pop(chave, None)
        messages.success(self.request, "Senha alterada. Entre no portal com a nova senha.")
        return resposta


class AlterarSenhaView(PasswordChangeView):
    """ "Alterar minha senha" (menu do avatar) e a troca obrigatória da senha provisória.

    Pede a senha atual e aplica as mesmas regras de senha forte. O update_session_auth_hash
    do Django mantém esta sessão aberta; as outras sessões da pessoa são encerradas.
    """

    template_name = "contas/senha_alterar.html"
    form_class = FormularioTrocaDeSenha
    success_url = reverse_lazy("contas:inicio")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["obrigatoria"] = self.request.user.precisa_trocar_senha
        return contexto

    def form_valid(self, form):
        resposta = super().form_valid(form)
        usuario = self.request.user
        auditoria.registrar(self.request, usuario, RegistroDeAuditoria.Acao.SENHA_ALTERADA)
        avisar_troca_de_senha(usuario)
        messages.success(self.request, "Senha alterada. A nova senha já está valendo.")
        return resposta


# --- Foto de perfil (janela aberta ao clicar no avatar do topo, em templates/base.html) ---


def _voltar(request):
    """Volta para a tela de onde o formulário veio, só se o endereço for deste site."""
    proxima = request.POST.get("proxima", "")
    seguro = url_has_allowed_host_and_scheme(
        proxima, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return redirect(proxima if seguro else "contas:inicio")


@login_required
@perfil_requerido(*PERFIS_DO_PORTAL)
@require_GET
def foto(request):
    """Entrega a foto da própria pessoa (avatar do topo)."""
    return entregar_foto(request.user)


@login_required
@perfil_requerido(*PERFIS_DO_PORTAL)
@require_GET
def foto_de(request, pk):
    """Entrega a foto de outra pessoa, como na sala da videochamada e nas mensagens.

    Qualquer pessoa logada no portal vê a foto de qualquer conta (regra em foto.pode_ver_foto).
    A conta ADMIN responde 404, o mesmo de uma conta sem foto.
    """
    dono = get_object_or_404(Usuario, pk=pk)
    if not pode_ver_foto(request.user, dono):
        raise Http404("Sem foto de perfil.")
    return entregar_foto(dono)


def entregar_foto(usuario):
    """Resposta com a imagem da foto de perfil, ou 404 se a pessoa não tiver foto."""
    if not usuario.foto:
        raise Http404("Sem foto de perfil.")
    try:
        with usuario.foto.open("rb") as arquivo:
            dados = arquivo.read()
    except FileNotFoundError as erro:
        raise Http404("A foto não está disponível.") from erro

    # O tipo vem do conteúdo, nunca do nome do arquivo.
    tipo = tipo_da_imagem(dados[:12])
    if tipo is None:
        raise Http404("A foto não é uma imagem válida.")

    resposta = HttpResponse(dados, content_type=tipo)
    # O endereço da foto muda a cada envio (?v=... no template), então o navegador pode
    # guardá-la por muito tempo. "private": só o navegador da pessoa guarda, nunca um proxy.
    resposta["Cache-Control"] = "private, max-age=31536000, immutable"
    # Mesmo se alguém abrir a foto direto na barra de endereços, nada nela pode rodar.
    resposta["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resposta


@login_required
@perfil_requerido(*PERFIS_DO_PORTAL)
@require_POST
def enviar_foto(request):
    """Troca a foto de perfil. A foto antiga é apagada do banco."""
    formulario = FormularioFoto(request.POST, request.FILES)
    if not formulario.is_valid():
        for erros in formulario.errors.values():
            messages.error(request, erros[0])
        return _voltar(request)

    usuario = request.user
    antiga = usuario.foto.name
    with transaction.atomic():
        usuario.foto = formulario.cleaned_data["foto"]
        usuario.save(update_fields=["foto"])
        if antiga:
            usuario.foto.storage.delete(antiga)
    messages.success(request, "Foto de perfil atualizada.")
    return _voltar(request)


@login_required
@perfil_requerido(*PERFIS_DO_PORTAL)
@require_POST
def remover_foto(request):
    """Volta para as iniciais no lugar da foto."""
    usuario = request.user
    if usuario.foto:
        antiga = usuario.foto.name
        with transaction.atomic():
            # "" e não None: a coluna não aceita vazio (NULL), como os outros FileField.
            usuario.foto = ""
            usuario.save(update_fields=["foto"])
            usuario.foto.storage.delete(antiga)
        messages.success(request, "Foto de perfil removida.")
    return _voltar(request)
