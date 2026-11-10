"""Rotas da API, todas debaixo de /api/.

O DefaultRouter cria sozinho, para cada viewset, a lista (/api/turmas/) e o detalhe
(/api/turmas/3/), além das ações extras como /api/turmas/3/desempenho/. Ele também cria a
página /api/, com links para todas as listas.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import views

app_name = "api"

roteador = DefaultRouter()
roteador.register("cursos", views.CursoViewSet, basename="curso")
roteador.register("disciplinas", views.DisciplinaViewSet, basename="disciplina")
roteador.register("turmas", views.TurmaViewSet, basename="turma")
roteador.register("ofertas", views.OfertaViewSet, basename="oferta")
roteador.register("matriculas", views.MatriculaViewSet, basename="matricula")
roteador.register("riscos", views.RiscoViewSet, basename="risco")

urlpatterns = [
    path("", include(roteador.urls)),
    # Acesso
    path("eu/", views.EuView.as_view(), name="eu"),
    path("token/", views.TokenView.as_view(), name="token"),
    # Relatórios em arquivo (?formato=pdf ou xlsx)
    path("relatorios/boletim/<int:pk>/", views.BoletimArquivoView.as_view(), name="relatorio_boletim"),
    path(
        "relatorios/disciplina/<int:pk>/",
        views.DisciplinaArquivoView.as_view(),
        name="relatorio_disciplina",
    ),
    path("relatorios/turma/<int:pk>/", views.TurmaArquivoView.as_view(), name="relatorio_turma"),
    path("relatorios/risco/", views.RiscoArquivoView.as_view(), name="relatorio_risco"),
    path("relatorios/alunos/", views.AlunosArquivoView.as_view(), name="relatorio_alunos"),
    # Documentação: o esquema OpenAPI (gerado pelo drf-spectacular) e a tela do Swagger
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
]
