from django.apps import AppConfig


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # O caminho completo é necessário porque o app fica dentro da pasta apps/.
    name = "apps.contas"
    verbose_name = "Contas"
