"""Videochamadas: a mesma tela atende a coordenação e os professores.

A segurança vem de Chamada.objects.do_usuario: quem não participa da chamada recebe 404, e
nem descobre se ela existe. O aluno e o ADMIN recebem 403 pelo @perfil_requerido.

Sala própria (VIDEO_MODO=proprio): o vídeo vai direto entre os dois navegadores (WebRTC). As
rotas sinal/ e ice/ só ajudam os dois a se encontrar (sinalização). Detalhes em
docs/VIDEOCHAMADA.md.
"""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.alertas.models import Alerta
from apps.alertas.regras import aviso_de_chamada, chave_da_chamada
from apps.contas.decorators import perfil_requerido

from .forms import NovaChamadaForm
from .models import VALIDADE_DO_SINAL, Chamada, SinalChamada, nome_na_chamada

PERFIS = ("PROFESSOR", "COORDENADOR")
ITENS_POR_PAGINA = 20

# Sinalização da sala própria
LIMITE_DO_SINAL = 16 * 1024  # 16 KB: uma oferta de vídeo e áudio tem cerca de 6 KB
SINAIS_POR_CONSULTA = 100
# STUN: servidor público e gratuito que só diz a cada navegador qual é o seu endereço na
# internet. Não recebe o vídeo e não precisa de senha.
STUN_PADRAO = "stun:stun.cloudflare.com:3478"


def video_proprio():
    return settings.VIDEO_MODO == "proprio"


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
            "video_proprio": video_proprio(),
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

    # Na sala própria, o navegador começa a ler os sinais depois do último que já existe:
    # recados antigos (de uma aba fechada ou de uma tentativa anterior) não atrapalham.
    ultimo_sinal = 0
    if video_proprio() and chamada.em_andamento:
        ultimo_sinal = (
            SinalChamada.objects.filter(chamada=chamada, para=request.user)
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
        ) or 0

    return render(
        request,
        "videochamadas/sala.html",
        {
            "chamada": chamada,
            "outro": outro,
            "nome_do_outro": nome_na_chamada(outro),
            "fui_eu_que_chamei": chamada.criada_por_id == request.user.pk,
            "link_do_jitsi": chamada.link_do_jitsi(request.user),
            "video_proprio": video_proprio(),
            "ultimo_sinal": ultimo_sinal,
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
    # Os sinais só servem enquanto a chamada está em andamento.
    chamada.sinais.all().delete()
    return redirect("videochamadas:inicio")


# --- Sinalização da sala própria (respostas em JSON, lidas por static/js/chamada.js) ---


def recusar(texto, **extra):
    """Resposta 400 com o motivo, para o pedido que o portal não aceita."""
    return JsonResponse({"erro": texto, **extra}, status=400)


def chamada_da_sinalizacao(request, pk):
    """A chamada, se a sala própria estiver ligada e a pessoa participar dela (senão, 404)."""
    if not video_proprio():
        raise Http404("A sala própria está desligada (VIDEO_MODO=jitsi).")
    # Uma consulta só, sem select_related: aqui bastam os números das duas contas.
    return get_object_or_404(Chamada.objects.do_usuario(request.user), pk=pk)


@login_required
@perfil_requerido(*PERFIS)
@require_http_methods(["GET", "POST"])
@never_cache
def sinal(request, pk):
    """GET: os sinais novos para quem pergunta. POST: grava um sinal para o outro participante."""
    chamada = chamada_da_sinalizacao(request, pk)
    if request.method == "POST":
        return gravar_sinal(request, chamada)
    return ler_sinais(request, chamada)


def ler_sinais(request, chamada):
    """Sinais para esta pessoa nesta chamada com número maior que ?depois=, e a situação.

    Cada pessoa só lê o que foi mandado PARA ela (filtro para=request.user). É a consulta que
    o navegador repete a cada segundo, então ela usa o índice (chamada, para, id) e devolve só
    três campos.
    """
    try:
        depois = int(request.GET.get("depois", "0"))
    except ValueError:
        return recusar("O parâmetro depois precisa ser um número.")
    if depois < 0:
        return recusar("O parâmetro depois precisa ser um número.")

    encerrada = not chamada.em_andamento
    sinais = []
    if not encerrada:
        sinais = list(
            SinalChamada.objects.filter(chamada=chamada, para=request.user, id__gt=depois)
            .order_by("id")
            .values("id", "tipo", "conteudo")[:SINAIS_POR_CONSULTA]
        )
    return JsonResponse({"sinais": sinais, "encerrada": encerrada})


def gravar_sinal(request, chamada):
    """Confere o pedido e grava o sinal para o outro participante (nunca para outra pessoa)."""
    if not chamada.em_andamento:
        return recusar("A chamada não está mais em andamento.", encerrada=True)
    if len(request.body) > LIMITE_DO_SINAL:
        return recusar("O sinal é grande demais.")
    try:
        dados = json.loads(request.body)
    except (ValueError, RecursionError):  # JSON inválido ou aninhado demais
        return recusar("O sinal precisa estar em JSON.")
    if not isinstance(dados, dict):
        return recusar("O sinal precisa estar em JSON.")

    tipo = dados.get("tipo")
    conteudo = dados.get("conteudo")
    if tipo not in SinalChamada.Tipo.values:
        return recusar("Tipo de sinal desconhecido.")
    if conteudo is not None and not isinstance(conteudo, dict):
        return recusar("O conteúdo do sinal precisa ser um objeto JSON.")

    agora = timezone.now()
    if tipo == SinalChamada.Tipo.ENTREI:
        # Faxina, sem Celery: cada vez que alguém entra numa sala, os sinais com mais de
        # 2 horas (de qualquer chamada) são apagados.
        SinalChamada.objects.filter(criado_em__lt=agora - VALIDADE_DO_SINAL).delete()

    novo = SinalChamada.objects.create(
        chamada=chamada,
        de=request.user,
        para_id=chamada.id_do_outro(request.user),
        tipo=tipo,
        conteudo=conteudo,
        criado_em=agora,
    )
    return JsonResponse({"id": novo.id}, status=201)


def servidores_ice():
    """Lista de servidores que ajudam os navegadores a se acharem (formato do WebRTC)."""
    servidores = [{"urls": [STUN_PADRAO]}]
    # O TURN só entra com as três variáveis do .env preenchidas.
    if settings.TURN_URLS and settings.TURN_USUARIO and settings.TURN_SENHA:
        servidores.append(
            {
                "urls": list(settings.TURN_URLS),
                "username": settings.TURN_USUARIO,
                "credential": settings.TURN_SENHA,
            }
        )
    return servidores


@login_required
@perfil_requerido(*PERFIS)
@require_GET
@never_cache
def ice(request, pk):
    """Servidores STUN/TURN. As credenciais do TURN só vão para quem participa da chamada."""
    chamada = chamada_da_sinalizacao(request, pk)
    if not chamada.em_andamento:
        return recusar("A chamada não está mais em andamento.", encerrada=True)
    return JsonResponse({"iceServers": servidores_ice()})
