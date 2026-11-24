from django.urls import path

from . import views

app_name = "coordenacao"

urlpatterns = [
    path("", views.painel, name="painel"),
    # Alunos em risco de evasão (módulo preditivo)
    path("risco/", views.risco, name="risco"),
    path("risco/recalcular/", views.risco_recalcular, name="risco_recalcular"),
    # Central de alertas automáticos
    path("alertas/", views.alertas, name="alertas"),
    path("alertas/rotina/", views.alertas_rotina, name="alertas_rotina"),
    # Alunos
    path("alunos/", views.alunos, name="alunos"),
    # Matrícula do aluno (turma e situação); a conta é da Secretaria.
    path("alunos/<int:pk>/matricula/", views.aluno_editar, name="aluno_editar"),
    # Professores
    path("professores/", views.professores, name="professores"),
    # Turmas e as disciplinas oferecidas nelas
    path("turmas/", views.turmas, name="turmas"),
    path("turmas/nova/", views.turma_nova, name="turma_nova"),
    path("turmas/<int:pk>/", views.turma, name="turma"),
    path("turmas/<int:pk>/editar/", views.turma_editar, name="turma_editar"),
    path("turmas/<int:pk>/excluir/", views.turma_excluir, name="turma_excluir"),
    path("ofertas/<int:pk>/editar/", views.oferta_editar, name="oferta_editar"),
    path("ofertas/<int:pk>/excluir/", views.oferta_excluir, name="oferta_excluir"),
    # Disciplinas
    path("disciplinas/", views.disciplinas, name="disciplinas"),
    path("disciplinas/nova/", views.disciplina_nova, name="disciplina_nova"),
    path("disciplinas/<int:pk>/editar/", views.disciplina_editar, name="disciplina_editar"),
    path("disciplinas/<int:pk>/excluir/", views.disciplina_excluir, name="disciplina_excluir"),
]
