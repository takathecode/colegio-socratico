from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "contas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.EntrarView.as_view(), name="entrar"),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),
    path("atendimento/", views.atendimento, name="atendimento"),
    # Foto de perfil da própria pessoa (aluno, professor, coordenação e Secretaria).
    path("conta/foto/", views.foto, name="foto"),
    path("conta/foto/enviar/", views.enviar_foto, name="foto_enviar"),
    path("conta/foto/remover/", views.remover_foto, name="foto_remover"),
    # Foto de outra pessoa: qualquer conta do portal vê a de qualquer outra (foto.pode_ver_foto).
    path("conta/<int:pk>/foto/", views.foto_de, name="foto_de"),
    # Troca da senha por quem está logado (e a troca obrigatória depois da senha provisória).
    path("conta/senha/", views.AlterarSenhaView.as_view(), name="senha_alterar"),
    # "Esqueci minha senha" pela matrícula (regras em apps/contas/redefinicao.py).
    path("senha/esqueci/", views.senha_esqueci, name="senha_esqueci"),
    path("senha/esqueci/confirmar/", views.senha_confirmar, name="senha_confirmar"),
    path("senha/enviada/", views.senha_enviada, name="senha_enviada"),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        views.RedefinirSenhaView.as_view(),
        name="senha_redefinir",
    ),
]
