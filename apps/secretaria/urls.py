from django.urls import path

from . import views

app_name = "secretaria"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("contas/", views.contas, name="contas"),
    # tipo: aluno, professor ou coordenacao (FORM_DO_TIPO em views.py)
    path("contas/nova/<slug:tipo>/", views.conta_nova, name="conta_nova"),
    path("contas/<int:pk>/", views.conta, name="conta"),
    path("contas/<int:pk>/editar/", views.conta_editar, name="conta_editar"),
    path("contas/<int:pk>/redefinir/", views.conta_redefinir, name="conta_redefinir"),
    path("contas/<int:pk>/desbloquear/", views.conta_desbloquear, name="conta_desbloquear"),
    path("contas/<int:pk>/ativar/", views.conta_alternar_ativa, name="conta_alternar_ativa"),
    path("senha-provisoria/", views.senha_provisoria, name="senha_provisoria"),
]
