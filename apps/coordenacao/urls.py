from django.urls import path

from . import views

app_name = "coordenacao"

urlpatterns = [
    path("", views.painel, name="painel"),
    # Alunos
    path("alunos/", views.alunos, name="alunos"),
    path("alunos/novo/", views.aluno_novo, name="aluno_novo"),
    path("alunos/<int:pk>/editar/", views.aluno_editar, name="aluno_editar"),
    # Professores
    path("professores/", views.professores, name="professores"),
    path("professores/novo/", views.professor_novo, name="professor_novo"),
    path("professores/<int:pk>/editar/", views.professor_editar, name="professor_editar"),
    # Contas (todos os perfis) e contas de coordenação
    path("contas/", views.contas, name="contas"),
    path("contas/coordenacao/nova/", views.coordenador_novo, name="coordenador_novo"),
    path(
        "contas/coordenacao/<int:pk>/editar/",
        views.coordenador_editar,
        name="coordenador_editar",
    ),
    path("contas/<int:pk>/nova-senha/", views.conta_nova_senha, name="conta_nova_senha"),
    path("contas/<int:pk>/ativar/", views.conta_alternar_ativa, name="conta_alternar_ativa"),
    path("contas/senha-provisoria/", views.senha_provisoria, name="senha_provisoria"),
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
