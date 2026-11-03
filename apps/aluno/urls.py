from django.urls import path

from . import views

app_name = "aluno"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("notas/", views.notas, name="notas"),
    path("frequencia/", views.frequencia, name="frequencia"),
    path("justificativas/<int:pk>/anexo/", views.anexo_justificativa, name="anexo_justificativa"),
    path("calendario/", views.calendario, name="calendario"),
    path("financeiro/", views.financeiro, name="financeiro"),
]
