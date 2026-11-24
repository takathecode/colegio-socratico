from django.urls import path

from . import views

app_name = "videochamadas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("nova/", views.nova, name="nova"),
    # Janela "Fulano está te chamando" (static/js/portal.js)
    path("recebida/", views.recebida, name="recebida"),
    path("<int:pk>/", views.sala, name="sala"),
    path("<int:pk>/encerrar/", views.encerrar, name="encerrar"),
    path("<int:pk>/recusar/", views.recusar_chamada, name="recusar"),
    # Sinalização da sala própria (static/js/chamada.js)
    path("<int:pk>/sinal/", views.sinal, name="sinal"),
    path("<int:pk>/ice/", views.ice, name="ice"),
]
