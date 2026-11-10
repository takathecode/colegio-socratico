"""Rotas principais do projeto."""

from django.contrib import admin
from django.urls import include, path

# Textos exibidos no cabeçalho do Django Admin.
admin.site.site_header = "Instituto Socrático"
admin.site.site_title = "Instituto Socrático"
admin.site.index_title = "Administração do sistema"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("aluno/", include("apps.aluno.urls")),
    path("professor/", include("apps.professor.urls")),
    path("coordenacao/", include("apps.coordenacao.urls")),
    path("mensagens/", include("apps.mensagens.urls")),
    path("alertas/", include("apps.alertas.urls")),
    path("relatorios/", include("apps.relatorios.urls")),
    path("api/", include("apps.api.urls")),  # API REST; documentação em /api/docs/
    # Login, saída, redefinição de senha e o redirecionamento de "/" por perfil.
    path("", include("apps.contas.urls")),
]
