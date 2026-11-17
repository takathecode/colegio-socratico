"""Rotina diária chamada pelo Cron da Vercel (vercel.json).

Na Vercel não existe worker nem beat do Celery rodando o tempo todo: cada pedido acorda o
Django, responde e o processo pode ser desligado. Por isso a rotina das 6h é disparada pelo
Cron da Vercel, que faz um GET neste endereço uma vez por dia.

Segurança: a Vercel manda o cabeçalho "Authorization: Bearer <CRON_SECRET>", com o valor da
variável CRON_SECRET cadastrada no painel. Sem esse segredo, o endereço responde 404, como se
não existisse. Assim ninguém de fora consegue rodar a rotina à vontade.
"""

import secrets

from django.conf import settings
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET

from . import tasks


def pedido_veio_do_cron(request):
    segredo = settings.CRON_SECRET
    if not segredo:
        return False  # sem CRON_SECRET configurado, a rota fica desligada
    recebido = request.headers.get("Authorization", "")
    # compare_digest leva o mesmo tempo para qualquer valor, e não dá pistas do segredo.
    return secrets.compare_digest(recebido, f"Bearer {segredo}")


@require_GET
def rotina_diaria(request):
    if not pedido_veio_do_cron(request):
        raise Http404
    # Roda aqui mesmo, sem fila: na Vercel o CELERY_SEM_REDIS fica True.
    resumo = tasks.rotina_diaria()
    return JsonResponse({"ok": True, "alertas_novos": resumo})
