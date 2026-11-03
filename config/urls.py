"""Rotas principais do projeto."""

from django.contrib import admin
from django.urls import path

# Textos exibidos no cabeçalho do Django Admin.
admin.site.site_header = "Colégio Socrático"
admin.site.site_title = "Colégio Socrático"
admin.site.index_title = "Administração do sistema"

urlpatterns = [
    path("admin/", admin.site.urls),
]
