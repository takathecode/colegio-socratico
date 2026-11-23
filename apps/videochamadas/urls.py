from django.urls import path

from . import views

app_name = "videochamadas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("nova/", views.nova, name="nova"),
    path("<int:pk>/", views.sala, name="sala"),
    path("<int:pk>/encerrar/", views.encerrar, name="encerrar"),
    # Sinalização da sala própria (static/js/chamada.js)
    path("<int:pk>/sinal/", views.sinal, name="sinal"),
    path("<int:pk>/ice/", views.ice, name="ice"),
]
