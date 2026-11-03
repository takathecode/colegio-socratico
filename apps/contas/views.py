from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from .forms import FormularioLogin
from .models import Usuario

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
