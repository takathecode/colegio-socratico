from django.contrib import admin

from .models import Chamada


@admin.register(Chamada)
class ChamadaAdmin(admin.ModelAdmin):
    list_display = ("criada_por", "convidado", "assunto", "criada_em", "encerrada_em")
    list_select_related = ("criada_por", "convidado")
    search_fields = ("assunto", "criada_por__matricula", "convidado__matricula")
    autocomplete_fields = ("criada_por", "convidado")
    readonly_fields = ("sala", "criada_em")
