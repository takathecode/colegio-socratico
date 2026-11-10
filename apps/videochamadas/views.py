"""Videochamadas: a mesma tela atende a coordenação e os professores.

A segurança vem de Chamada.objects.do_usuario: quem não participa da chamada recebe 404, e
nem descobre se ela existe. O aluno e o ADMIN recebem 403 pelo @perfil_requerido.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.alertas.models import Alerta
from apps.alertas.regras import aviso_de_chamada, chave_da_chamada
from apps.contas.decorators import perfil_requerido

from .forms import NovaChamadaForm
from .models import Chamada, nome_na_chamada

PERFIS = ("PROFESSOR", "COORDENADOR")
ITENS_POR_PAGINA = 20


def chamadas_do_usuario(usuario):
    return Chamada.objects.do_usuario(usuario).select_related("criada_por", "convidado")


def renderizar_inicio(request, form):
    pagina = Paginator(chamadas_do_usuario(request.user), ITENS_POR_PAGINA).get_page(
        request.GET.get("pagina")
    )
    for chamada in pagina:
        outro = chamada.outro_participante(request.user)
        chamada.outro = outro
        chamada.nome_do_outro = nome_na_chamada(outro)
        chamada.fui_eu_que_chamei = chamada.criada_por_id == request.user.pk
    return render(
        request,
        "videochamadas/inicio.html",
        {
            "form": form,
            "pagina": pagina,
            # Sem ninguém ativo para chamar, a tela mostra um aviso no lugar do formulário.
            "tem_quem_chamar": form.fields["convidado"].queryset.exists(),
        },
    )


@login_required
@perfil_requerido(*PERFIS)
def inicio(request):
    # ?para= vem do botão "Chamar" da lista de professores e já escolhe a pessoa.
    form = NovaChamadaForm(usuario=request.user, initial={"convidado": request.GET.get("para")})
    return renderizar_inicio(request, form)


@login_required
@perfil_requerido(*PERFIS)
@require_POST
def nova(request):
    form = NovaChamadaForm(request.POST, usuario=request.user)
    if not form.is_valid():
        messages.error(request, "A chamada não foi criada. Confira os campos destacados.")
        return renderizar_inicio(request, form)

    # A chamada e o convite no sino são gravados juntos: ou os dois, ou nenhum.
    # O convite é gravado aqui mesmo, sem a fila do Celery, porque a chamada é para agora.
    with transaction.atomic():
        chamada = form.save()
        aviso_de_chamada(chamada)
    messages.success(
        request, f"Chamada criada. O convite foi enviado a {nome_na_chamada(chamada.convidado)}."
    )
    return redirect("videochamadas:sala", pk=chamada.pk)


@login_required
@perfil_requerido(*PERFIS)
def sala(request, pk):
    chamada = get_object_or_404(chamadas_do_usuario(request.user), pk=pk)
    # Quem abriu a sala já viu o convite: ele deixa de contar como não lido no sino.
    Alerta.objects.filter(
        destinatario=request.user, chave=chave_da_chamada(chamada.pk), lido_em__isnull=True
    ).update(lido_em=timezone.now())
    outro = chamada.outro_participante(request.user)
    return render(
        request,
        "videochamadas/sala.html",
        {
            "chamada": chamada,
            "outro": outro,
            "nome_do_outro": nome_na_chamada(outro),
            "fui_eu_que_chamei": chamada.criada_por_id == request.user.pk,
            "link_do_jitsi": chamada.link_do_jitsi(request.user),
        },
    )


@login_required
@perfil_requerido(*PERFIS)
@require_POST
def encerrar(request, pk):
    chamada = get_object_or_404(chamadas_do_usuario(request.user), pk=pk)
    if chamada.encerrada_em is None:
        chamada.encerrada_em = timezone.now()
        chamada.save(update_fields=["encerrada_em"])
        messages.success(request, "Chamada encerrada. Ela continua no histórico.")
    return redirect("videochamadas:inicio")
