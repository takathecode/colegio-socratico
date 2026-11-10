"""Caixa de mensagens. A mesma tela atende aluno, professor e coordenador.

A segurança vem de Conversa.objects.do_usuario: quem não participa recebe 404, e nem
descobre se a conversa existe.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academico.utilidades import baixar_anexo
from apps.alertas import tasks as alertas_tasks
from apps.alertas.fila import enfileirar
from apps.alertas.models import Alerta
from apps.alertas.regras import chave_da_conversa
from apps.contas.decorators import perfil_requerido

from .forms import NovaConversaForm, RespostaForm
from .models import Conversa, Mensagem, nome_de_exibicao

PERFIS = ("ALUNO", "PROFESSOR", "COORDENADOR")
PERFIS_QUE_INICIAM = ("ALUNO", "PROFESSOR", "COORDENADOR")


def rotulo_de_tempo(momento):
    """Hora para mensagens de hoje, "Ontem" ou a data, como na lista do protótipo."""
    momento = timezone.localtime(momento)
    hoje = timezone.localdate()
    if momento.date() == hoje:
        return momento.strftime("%Hh%M")
    if momento.date() == hoje - timedelta(days=1):
        return "Ontem"
    return momento.strftime("%d/%m")


def listar_conversas(usuario):
    """Todas as conversas da pessoa, da mais recente para a mais antiga, em uma só consulta."""
    ultima = Mensagem.objects.filter(conversa=OuterRef("pk")).order_by("-enviada_em")
    conversas = list(
        Conversa.objects.do_usuario(usuario)
        .select_related("aluno", "contato", "oferta__disciplina")
        .annotate(
            ultima_em=Subquery(ultima.values("enviada_em")[:1]),
            previa=Subquery(ultima.values("texto")[:1]),
            nao_lidas=Count(
                "mensagens",
                filter=Q(mensagens__lida_em__isnull=True) & ~Q(mensagens__remetente=usuario),
            ),
        )
        .order_by("-ultima_em")
    )
    for conversa in conversas:
        outro = conversa.outro_participante(usuario)
        conversa.nome_do_outro = nome_de_exibicao(outro)
        conversa.iniciais_do_outro = "".join(
            parte[0] for parte in conversa.nome_do_outro.replace(".", "").split()[-2:]
        ).upper()
        conversa.rotulo_tempo = rotulo_de_tempo(conversa.ultima_em or conversa.criada_em)
    return conversas


def combina_com_busca(conversa, busca):
    alvo = f"{conversa.assunto} {conversa.nome_do_outro}"
    if conversa.oferta:
        alvo += f" {conversa.oferta.disciplina.nome}"
    return busca.casefold() in alvo.casefold()


def abrir_conversa_pedida(request, conversas_do_usuario):
    """Lê ?conversa= e marca as mensagens recebidas como lidas."""
    pedida = request.GET.get("conversa", "")
    if not pedida.isdecimal():
        return None
    conversa = get_object_or_404(conversas_do_usuario, pk=pedida)
    agora = timezone.now()
    conversa.mensagens.filter(lida_em__isnull=True).exclude(remetente=request.user).update(
        lida_em=agora
    )
    # Quem abriu a conversa já viu a novidade: o aviso do sino deixa de contar como não lido.
    Alerta.objects.filter(
        destinatario=request.user, chave=chave_da_conversa(conversa.pk), lido_em__isnull=True
    ).update(lido_em=agora)
    return conversa


def renderizar_caixa(request, conversa_aberta=None, form_resposta=None, form_nova=None):
    usuario = request.user
    filtro = "nao_lidas" if request.GET.get("filtro") == "nao_lidas" else "todas"
    busca = request.GET.get("q", "").strip()

    # Abre a conversa antes de montar a lista, para ela já aparecer como lida.
    aberta_pelo_link = conversa_aberta
    if conversa_aberta is None:
        aberta_pelo_link = abrir_conversa_pedida(request, Conversa.objects.do_usuario(usuario))

    todas = listar_conversas(usuario)
    total_nao_lidas = sum(1 for conversa in todas if conversa.nao_lidas)
    conversas = todas
    if filtro == "nao_lidas":
        conversas = [conversa for conversa in conversas if conversa.nao_lidas]
    if busca:
        conversas = [conversa for conversa in conversas if combina_com_busca(conversa, busca)]

    # No computador, a primeira conversa já aparece aberta, como no protótipo. Ela só conta como
    # lida quando é clicada: no celular essa conversa fica escondida até o clique.
    atual = None
    id_atual = aberta_pelo_link.pk if aberta_pelo_link else (conversas[0].pk if conversas else None)
    if id_atual:
        atual = next((conversa for conversa in todas if conversa.pk == id_atual), None)

    mensagens_da_conversa = []
    if atual:
        mensagens_da_conversa = atual.mensagens.select_related("remetente")

    # Aluno, professor e secretaria (coordenação) iniciam conversas.
    pode_iniciar = usuario.perfil in PERFIS_QUE_INICIAM
    abrir_modal = False
    if pode_iniciar and form_nova is None:
        inicial = {"contato": request.GET.get("para"), "assunto": request.GET.get("assunto", "")}
        form_nova = NovaConversaForm(usuario=usuario, initial=inicial)
        abrir_modal = "para" in request.GET
    elif form_nova is not None:
        abrir_modal = True

    return render(
        request,
        "mensagens/caixa.html",
        {
            "conversas": conversas,
            "conversa": atual,
            "conversa_foi_pedida": aberta_pelo_link is not None,
            "mensagens_da_conversa": mensagens_da_conversa,
            "total_nao_lidas": total_nao_lidas,
            "filtro": filtro,
            "busca": busca,
            # Mantém o filtro e a busca ao clicar em uma conversa da lista.
            "parametros": urlencode({"filtro": filtro, "q": busca}),
            "form_resposta": form_resposta or RespostaForm(),
            "form_nova": form_nova,
            "pode_iniciar": pode_iniciar,
            "subtitulo_do_modal": {
                "PROFESSOR": "Escreva para um aluno das suas turmas.",
                "COORDENADOR": "Escreva para um aluno, como Secretaria acadêmica.",
            }.get(usuario.perfil, "Escreva para um professor da sua turma ou para a secretaria."),
            "abrir_modal": abrir_modal,
        },
    )


def avisar_destinatario(mensagem):
    """Coloca na fila o aviso do sino para quem recebeu a mensagem (depois de gravada)."""
    transaction.on_commit(lambda: enfileirar(alertas_tasks.avisar_mensagem_nova, mensagem.pk))


@login_required
@perfil_requerido(*PERFIS)
def caixa(request):
    return renderizar_caixa(request)


@login_required
@perfil_requerido(*PERFIS)
@require_POST
def responder(request, pk):
    conversa = get_object_or_404(Conversa.objects.do_usuario(request.user), pk=pk)
    form = RespostaForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "A mensagem não foi enviada. Confira os campos destacados.")
        return renderizar_caixa(request, conversa_aberta=conversa, form_resposta=form)

    mensagem = form.save(commit=False)
    mensagem.conversa = conversa
    mensagem.remetente = request.user
    mensagem.save()
    avisar_destinatario(mensagem)
    messages.success(request, "Mensagem enviada.")
    return redirect(f"{reverse('mensagens:caixa')}?conversa={conversa.pk}")


@login_required
@perfil_requerido(*PERFIS_QUE_INICIAM)
@require_POST
def nova(request):
    form = NovaConversaForm(request.POST, request.FILES, usuario=request.user)
    if not form.is_valid():
        messages.error(request, "A conversa não foi criada. Confira os campos destacados.")
        return renderizar_caixa(request, form_nova=form)

    conversa = form.save()
    avisar_destinatario(form.instance)
    messages.success(request, "Mensagem enviada.")
    return redirect(f"{reverse('mensagens:caixa')}?conversa={conversa.pk}")


@login_required
@perfil_requerido(*PERFIS)
def anexo(request, pk):
    conversas = Conversa.objects.do_usuario(request.user)
    mensagem = get_object_or_404(Mensagem, pk=pk, conversa__in=conversas)
    if not mensagem.anexo:
        raise Http404("Esta mensagem não tem anexo.")
    return baixar_anexo(mensagem.anexo)
