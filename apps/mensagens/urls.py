from django.urls import path

from . import views

app_name = "mensagens"

urlpatterns = [
    path("", views.caixa, name="caixa"),
    path("nova/", views.nova, name="nova"),
    path("<int:pk>/responder/", views.responder, name="responder"),
    path("anexo/<int:pk>/", views.anexo, name="anexo"),
]
