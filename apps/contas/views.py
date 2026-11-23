from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .decorators import perfil_requerido
from .foto import pode_ver_foto, tipo_da_imagem
from .forms import FormularioFoto, FormularioLogin
from .models import Usuario

# Perfis que usam o portal (e têm avatar no topo). O ADMIN usa só o Django Admin.
PERFIS_DO_PORTAL = (
    Usuario.Perfil.ALUNO,
    Usuario.Perfil.PROFESSOR,
    Usuario.Perfil.COORDENADOR,
)

# Para onde cada perfil vai depois de entrar no sistema.
ROTA_POR_PERFIL = {
    Usuario.Perfil.ALUNO: "aluno:painel",
    Usuario.Perfil.PROFESSOR: "professor:painel",
    Usuario.Perfil.COORDENADOR: "coordenacao:painel",
    Usuario.Perfil.ADMIN: "admin:index",
}


def inicio(request):
    """Endereço "/": manda cada pessoa para a área do seu perfil."""
    if not request.user.is_authenticated:
        return redirect("contas:entrar")
    rota = ROTA_POR_PERFIL.get(request.user.perfil)
    if rota is None:
        raise PermissionDenied
    return redirect(rota)


class EntrarView(LoginView):
    """Tela de login. Não existe tela de cadastro: as contas são criadas pela coordenação."""

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
