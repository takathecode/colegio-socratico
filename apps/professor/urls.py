from django.urls import path

from . import views

app_name = "professor"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("turmas/", views.turmas, name="turmas"),
    path("turmas/<int:pk>/", views.turma, name="turma"),
    path("notas/", views.notas, name="notas"),
    path("chamada/", views.chamada, name="chamada"),
    path("desempenho/", views.desempenho, name="desempenho"),
    path("justificativas/", views.justificativas, name="justificativas"),
    path(
        "justificativas/<int:pk>/avaliar/",
        views.avaliar_justificativa,
        name="avaliar_justificativa",
    ),
    path(
        "justificativas/<int:pk>/anexo/",
        views.anexo_justificativa,
        name="anexo_justificativa",
    ),
]
