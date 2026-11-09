from django.contrib import admin

from .models import RiscoEvasao


@admin.register(RiscoEvasao)
class RiscoEvasaoAdmin(admin.ModelAdmin):
    """Só leitura: o risco é calculado pelo modelo, nunca digitado à mão."""

    list_display = ("matricula", "probabilidade", "nivel", "frequencia", "media", "calculado_em")
    list_filter = ("nivel", "matricula__turma")
    list_select_related = ("matricula__aluno", "matricula__turma")
    search_fields = ("matricula__aluno__matricula", "matricula__aluno__first_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
