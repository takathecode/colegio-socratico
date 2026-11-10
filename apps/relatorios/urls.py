from django.urls import path

from . import views

app_name = "relatorios"

urlpatterns = [
    # Tela da coordenação com todos os relatórios
    path("", views.inicio, name="inicio"),
    # Aluno: o próprio boletim
    path("meu-boletim/", views.meu_boletim, name="meu_boletim"),
    # Professor: uma disciplina que ele leciona (?formato=pdf ou xlsx)
    path("disciplina/<int:pk>/", views.disciplina, name="disciplina"),
    # Coordenação
    path("boletim/<int:pk>/", views.boletim, name="boletim"),  # pk da matrícula
    path("turma/", views.turma, name="turma"),  # ?turma=3&formato=pdf
    path("risco/", views.risco, name="risco"),  # ?turma=&nivel=&busca=&formato=
    path("alunos/", views.alunos, name="alunos"),  # ?turma=&situacao_matricula=&situacao=
]
