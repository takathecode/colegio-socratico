from django.contrib import admin

from .models import Mensalidade


@admin.register(Mensalidade)
class MensalidadeAdmin(admin.ModelAdmin):
    list_display = ("matricula", "competencia", "parcela", "valor", "vencimento", "paga_em")
    list_filter = ("competencia",)
    list_select_related = ("matricula__aluno", "matricula__turma")
    search_fields = ("matricula__aluno__matricula", "matricula__aluno__first_name")
    autocomplete_fields = ("matricula",)
