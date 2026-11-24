"""Diz se o sistema entrega e-mails de verdade, e avisa quando não entrega.

Sem as variáveis do SMTP no .env (ou na Vercel), o Django usa o backend de "console": a
mensagem só aparece no terminal do runserver (ou no log da Vercel) e não chega a ninguém.
No computador isso é o esperado; no servidor publicado, o "Esqueci minha senha" e o botão
"Enviar link" da Secretaria parecem funcionar, mas o e-mail nunca chega. Por isso:

- a Secretaria vê um aviso e a sugestão de usar a senha provisória (apps/secretaria);
- o "python manage.py check" avisa no servidor publicado (DEBUG=False);
- cada envio sem SMTP deixa um aviso no log (apps/contas/tasks.py).
"""

from django.conf import settings
from django.core.checks import Warning, register

# Backends que não entregam a mensagem a ninguém. (O "locmem" dos testes guarda em
# mail.outbox e conta como entregue, para os testes enxergarem os e-mails.)
BACKENDS_SEM_ENTREGA = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
)


def entrega_de_verdade():
    """True quando os e-mails saem para a caixa das pessoas (SMTP configurado)."""
    return settings.EMAIL_BACKEND not in BACKENDS_SEM_ENTREGA


@register()
def conferir_envio_de_email(app_configs, **kwargs):
    """No servidor publicado, sem SMTP, os links de nova senha não chegam a ninguém."""
    if settings.DEBUG or entrega_de_verdade():
        return []
    return [
        Warning(
            "Os e-mails não são entregues: o EMAIL_BACKEND não é o SMTP.",
            hint=(
                "Preencha EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend e as "
                "variáveis EMAIL_* (veja o .env.example e o docs/VERCEL.md). Sem isso, o link "
                "de \"Esqueci minha senha\" só aparece no log."
            ),
            id="contas.W001",
        )
    ]
