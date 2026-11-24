from django.apps import AppConfig


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # O caminho completo é necessário porque o app fica dentro da pasta apps/.
    name = "apps.contas"
    verbose_name = "Contas"

    def ready(self):
        # Registra a conferência "os e-mails são entregues?" no python manage.py check.
        from . import envio_de_email  # noqa: F401
