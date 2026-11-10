from django.contrib import admin

from .models import Alerta


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    """Só leitura: os alertas são gerados pelas regras automáticas, nunca digitados."""

    list_display = ("titulo", "destinatario", "tipo", "gravidade", "criado_em", "lido_em", "email_enviado_em")
    list_filter = ("tipo", "gravidade", "por_email")
    list_select_related = ("destinatario",)
    search_fields = ("titulo", "destinatario__matricula", "destinatario__first_name")
    date_hierarchy = "criado_em"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
