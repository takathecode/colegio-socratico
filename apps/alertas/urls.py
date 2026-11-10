from django.urls import path

from . import views

app_name = "alertas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/abrir/", views.abrir, name="abrir"),
    path("marcar-todos/", views.marcar_todos, name="marcar_todos"),
]
