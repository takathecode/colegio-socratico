from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "contas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.EntrarView.as_view(), name="entrar"),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),
    path("atendimento/", views.atendimento, name="atendimento"),
    # Fluxo de "Esqueci minha senha" do próprio Django, só com as telas do projeto.
    path(
        "senha/esqueci/",
        auth_views.PasswordResetView.as_view(
            template_name="contas/senha_esqueci.html",
            email_template_name="contas/email_senha.txt",
            subject_template_name="contas/email_senha_assunto.txt",
            success_url=reverse_lazy("contas:senha_enviada"),
        ),
        name="senha_esqueci",
    ),
    path(
        "senha/enviada/",
        auth_views.PasswordResetDoneView.as_view(template_name="contas/senha_enviada.html"),
        name="senha_enviada",
    ),
    path(
        "senha/nova/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="contas/senha_nova.html",
            success_url=reverse_lazy("contas:senha_concluida"),
        ),
        name="senha_nova",
    ),
    path(
        "senha/concluida/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="contas/senha_concluida.html"
        ),
        name="senha_concluida",
    ),
]
