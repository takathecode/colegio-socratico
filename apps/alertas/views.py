"""Notificações: os alertas da própria pessoa. A mesma tela atende os três perfis.

A segurança vem do filtro destinatario=request.user: o alerta de outra pessoa responde 404.
A central da coordenação, com os alertas de todos, fica em apps/coordenacao/views.py.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.contas.decorators import perfil_requerido

from .models import Alerta

PERFIS = ("ALUNO", "PROFESSOR", "COORDENADOR")
ITENS_POR_PAGINA = 20


def endereco_seguro(request, endereco, padrao="alertas:lista"):
    """Só redireciona para endereços deste site; qualquer outro volta para a lista."""
    if endereco and url_has_allowed_host_and_scheme(
        endereco, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(endereco)
    return redirect(padrao)


@login_required
@perfil_requerido(*PERFIS)
def lista(request):
    alertas = Alerta.objects.filter(destinatario=request.user)
    total_nao_lidos = alertas.filter(lido_em__isnull=True).count()
    filtro = "nao_lidos" if request.GET.get("filtro") == "nao_lidos" else "todos"
    if filtro == "nao_lidos":
        alertas = alertas.filter(lido_em__isnull=True)
    return render(
        request,
        "alertas/lista.html",
        {
            "pagina": Paginator(alertas, ITENS_POR_PAGINA).get_page(request.GET.get("pagina")),
            "filtro": filtro,
            "total_nao_lidos": total_nao_lidos,
        },
    )


@login_required
@perfil_requerido(*PERFIS)
@require_POST
def abrir(request, pk):
    """Marca o alerta como lido e leva para a tela onde o assunto se resolve."""
    alerta = get_object_or_404(Alerta, pk=pk, destinatario=request.user)
    if alerta.lido_em is None:
        alerta.lido_em = timezone.now()
        alerta.save(update_fields=["lido_em"])
    return endereco_seguro(request, alerta.link)


@login_required
@perfil_requerido(*PERFIS)
@require_POST
def marcar_todos(request):
    total = Alerta.objects.filter(destinatario=request.user, lido_em__isnull=True).update(
        lido_em=timezone.now()
    )
    if total:
        messages.success(request, "Todas as notificações foram marcadas como lidas.")
    return endereco_seguro(request, request.POST.get("proxima"))
