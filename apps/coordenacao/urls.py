from django.urls import path

from . import views

app_name = "coordenacao"

urlpatterns = [
    path("", views.painel, name="painel"),
]
