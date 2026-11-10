from django.urls import path

from . import views

app_name = "videochamadas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("nova/", views.nova, name="nova"),
    path("<int:pk>/", views.sala, name="sala"),
    path("<int:pk>/encerrar/", views.encerrar, name="encerrar"),
]
