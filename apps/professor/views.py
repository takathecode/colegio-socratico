"""Telas da área do professor.

Toda tela começa pelas disciplinas do professor logado (ver servicos.py). Assim ele só vê
e altera as turmas que leciona. Os outros perfis recebem 403 pelo @perfil_requerido.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academico.calculos import EM_RISCO, FREQUENCIA_MINIMA, MEDIA_MINIMA
from apps.academico.models import Frequencia, Justificativa
from apps.academico.utilidades import baixar_anexo, data_valida, saudacao, texto_dias_ate
from apps.analytics.dados import contar_por_faixa
from apps.analytics.graficos import distribuicao_de_notas
from apps.contas.decorators import perfil_requerido

from . import servicos
from .forms import AvaliarJustificativaForm, ChamadaForm, NotasForm, NovaAvaliacaoForm

# Quantos itens o painel mostra em cada lista.
LIMITE_DO_PAINEL = 5


def url_com_parametros(rota, **parametros):
    """Monta, por exemplo, /professor/notas/?oferta=3&avaliacao=8."""
    return f"{reverse(rota)}?{urlencode(parametros)}"


@login_required
@perfil_requerido("PROFESSOR")
def painel(request):
    resumos = servicos.resumo_das_ofertas(servicos.ofertas_do_professor(request.user))
    pendentes = servicos.justificativas_do_professor(request.user).filter(
        status=Justificativa.Status.PENDENTE
    )
    proximas = list(servicos.proximas_avaliacoes_do_professor(request.user)[:LIMITE_DO_PAINEL])

    # Alunos em risco em qualquer disciplina do professor, para ele agir cedo.
    em_risco = [
        {"oferta": resumo["oferta"], **linha}
        for resumo in resumos
        for linha in resumo["linhas"]
        if linha["situacao"] == EM_RISCO
    ]
    em_risco.sort(key=lambda linha: (linha["frequencia"] or 0, linha["media"] or 0))

    total_turmas = len({resumo["oferta"].turma_id for resumo in resumos})
    detalhe_proxima = ""
    if proximas:
        primeira = proximas[0]
        detalhe_proxima = (
            f"{primeira.nome} · {primeira.oferta.disciplina.nome} · {primeira.oferta.turma.codigo}"
        )

    return render(
        request,
        "professor/painel.html",
        {
            "saudacao": saudacao(),
            "hoje": timezone.localdate(),
            "resumos": resumos,
            "detalhe_turmas": f"Em {total_turmas} turma{'s' if total_turmas != 1 else ''}",
            "detalhe_proxima": detalhe_proxima,
            # Um aluno pode estar em mais de uma disciplina do professor: conta uma vez só.
            "total_alunos": len(
                {linha["matricula"].pk for resumo in resumos for linha in resumo["linhas"]}
            ),
            "total_pendentes": pendentes.count(),
            "pendentes": pendentes[:LIMITE_DO_PAINEL],
            "proximas": proximas,
            "dias_ate_a_proxima": texto_dias_ate(proximas[0].data_hora) if proximas else None,
            "em_risco": em_risco[:8],
            "total_em_risco": len(em_risco),
        },
    )


@login_required
@perfil_requerido("PROFESSOR")
def turmas(request):
    return render(
        request,
        "professor/turmas.html",
        {"resumos": servicos.resumo_das_ofertas(servicos.ofertas_do_professor(request.user))},
    )


@login_required
@perfil_requerido("PROFESSOR")
def turma(request, pk):
    oferta = servicos.oferta_do_professor(request.user, pk)
    resumo = servicos.resumo_das_ofertas([oferta])[0]
    linhas = resumo["linhas"]
    for linha in linhas:
        # Pares (avaliação, nota), usados na lista do celular.
        linha["notas_nomeadas"] = list(zip(resumo["avaliacoes"], linha["notas"]))

    # Busca por nome ou matrícula. Os indicadores continuam sendo da turma inteira.
    busca = request.GET.get("busca", "").strip()
    if busca:
        termo = busca.casefold()
        linhas = [
            linha
            for linha in linhas
            if termo in linha["matricula"].aluno.get_full_name().casefold()
            or termo in linha["matricula"].aluno.matricula.casefold()
        ]

    return render(
        request,
        "professor/turma.html",
        {
            "oferta": oferta,
            "avaliacoes": resumo["avaliacoes"],
            "indicadores": resumo["indicadores"],
            "linhas": linhas,
            "busca": busca,
            "media_minima": MEDIA_MINIMA,
            "frequencia_minima": int(FREQUENCIA_MINIMA),
        },
    )


@login_required
@perfil_requerido("PROFESSOR")
def notas(request):
    """Lançar notas. A mesma tela cria avaliações (campo "acao" do formulário enviado)."""
    oferta, ofertas = servicos.escolher_oferta(request.user, request.GET.get("oferta"))
    if oferta is None:
        return render(request, "professor/sem_disciplinas.html", {"titulo_da_tela": "Lançar notas"})

    avaliacoes = list(oferta.avaliacoes.order_by("data_hora", "nome"))
    avaliacao = None
    pedida = request.GET.get("avaliacao", "")
    if pedida:
        avaliacao = next((a for a in avaliacoes if str(a.pk) == pedida), None)
        if avaliacao is None:
            raise Http404("Esta avaliação não é desta disciplina.")
    elif avaliacoes:
        # Sem escolha, abre a avaliação mais recente que já aconteceu (ou a primeira).
        passadas = [a for a in avaliacoes if a.data_hora <= timezone.now()]
        avaliacao = passadas[-1] if passadas else avaliacoes[0]

    matriculas = servicos.matriculas_ativas(oferta)
    notas_atuais = (
        dict(avaliacao.notas.values_list("matricula_id", "valor")) if avaliacao else {}
    )
    form = None
    form_avaliacao = NovaAvaliacaoForm(oferta=oferta)

    if request.method == "POST" and request.POST.get("acao") == "nova_avaliacao":
        form_avaliacao = NovaAvaliacaoForm(request.POST, oferta=oferta)
        if form_avaliacao.is_valid():
            nova = form_avaliacao.save()
            messages.success(request, f"Avaliação {nova.nome} criada. Já pode lançar as notas.")
            return redirect(url_com_parametros("professor:notas", oferta=oferta.pk, avaliacao=nova.pk))
        messages.error(request, "A avaliação não foi criada. Confira os campos destacados.")

    elif request.method == "POST":
        if avaliacao is None:
            raise Http404("Escolha uma avaliação.")
        form = NotasForm(request.POST, matriculas=matriculas, notas_atuais=notas_atuais)
        if form.is_valid():
            alteradas = servicos.salvar_notas(avaliacao, form.valores())
            if alteradas:
                plural = "ões" if alteradas > 1 else "ão"
                messages.success(
                    request, f"Notas da {avaliacao.nome} salvas: {alteradas} alteraç{plural}."
                )
            else:
                messages.info(request, "Nenhuma nota foi alterada.")
            return redirect(
                url_com_parametros("professor:notas", oferta=oferta.pk, avaliacao=avaliacao.pk)
            )
        messages.error(request, "As notas não foram salvas. Corrija os campos destacados.")

    if form is None and avaliacao:
        form = NotasForm(matriculas=matriculas, notas_atuais=notas_atuais)

    return render(
        request,
        "professor/notas.html",
        {
            "oferta": oferta,
            "ofertas": ofertas,
            "avaliacoes": avaliacoes,
            "avaliacao": avaliacao,
            "form": form,
            "linhas": [{"matricula": m, "campo": form.campo_de(m)} for m in matriculas]
            if form
            else [],
            "form_avaliacao": form_avaliacao,
            "abrir_modal": form_avaliacao.is_bound or "nova" in request.GET,
        },
    )


@login_required
@perfil_requerido("PROFESSOR")
def chamada(request):
    oferta, ofertas = servicos.escolher_oferta(
        request.user, request.POST.get("oferta") or request.GET.get("oferta")
    )
    if oferta is None:
        return render(request, "professor/sem_disciplinas.html", {"titulo_da_tela": "Chamada"})

    hoje = timezone.localdate()
    data = data_valida(request.GET.get("data", "")) or hoje
    if data > hoje:
        messages.warning(request, "Não é possível fazer a chamada de uma aula futura. Mostrando hoje.")
        data = hoje

    if request.method == "POST":
        form = ChamadaForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data["data_aula"]
            _aula, linhas = servicos.montar_chamada(oferta, data)
            marcacoes, sem_marcacao = ler_marcacoes(request.POST, linhas)
            if not sem_marcacao:
                servicos.salvar_chamada(
                    oferta,
                    data,
                    form.cleaned_data["horas_aula"],
                    form.cleaned_data["conteudo"],
                    marcacoes,
                )
                presentes = sum(1 for presente, _metodo in marcacoes.values() if presente)
                messages.success(
                    request,
                    f"Chamada de {data:%d/%m/%Y} salva: {presentes} presente(s) e "
                    f"{len(marcacoes) - presentes} falta(s).",
                )
                return redirect(
                    url_com_parametros("professor:chamada", oferta=oferta.pk, data=data.isoformat())
                )
            nomes = ", ".join(sem_marcacao[:3])
            if len(sem_marcacao) > 3:
                nomes += f" e mais {len(sem_marcacao) - 3}"
            messages.error(
                request, f"Marque presença ou falta para todos os alunos. Faltam: {nomes}."
            )
        else:
            messages.error(request, "A chamada não foi salva. Confira os campos destacados.")
        aula, linhas = servicos.montar_chamada(oferta, data)
        # Mantém na tela o que o professor já tinha marcado, para ele não perder o trabalho.
        for linha in linhas:
            escolha = request.POST.get(f"presenca_{linha['matricula'].pk}")
            if not linha["travada"] and escolha in ("presente", "falta"):
                linha["presente"] = escolha == "presente"
                linha["metodo"] = request.POST.get(f"metodo_{linha['matricula'].pk}", "MANUAL")
    else:
        aula, linhas = servicos.montar_chamada(oferta, data)
        form = ChamadaForm(
            initial={
                "data_aula": data,
                "horas_aula": aula.horas_aula if aula else 2,
                "conteudo": aula.conteudo if aula else "",
            }
        )

    return render(
        request,
        "professor/chamada.html",
        {
            "oferta": oferta,
            "ofertas": ofertas,
            "data": data,
            "hoje": hoje,
            "aula": aula,
            "form": form,
            "linhas": linhas,
            "total_presentes": sum(1 for linha in linhas if linha["presente"] is True),
            "total_faltas": sum(1 for linha in linhas if linha["presente"] is False),
        },
    )


@login_required
@perfil_requerido("PROFESSOR")
def desempenho(request):
    """Gráfico com a distribuição das médias da turma em uma disciplina do professor."""
    oferta, ofertas = servicos.escolher_oferta(request.user, request.GET.get("oferta"))
    if oferta is None:
        return render(request, "professor/sem_disciplinas.html", {"titulo_da_tela": "Desempenho"})

    resumo = servicos.resumo_das_ofertas([oferta])[0]
    faixas = contar_por_faixa(linha["media"] for linha in resumo["linhas"])
    return render(
        request,
        "professor/desempenho.html",
        {
            "oferta": oferta,
            "ofertas": ofertas,
            "indicadores": resumo["indicadores"],
            "faixas": faixas,
            "sem_nota": sum(1 for linha in resumo["linhas"] if linha["media"] is None),
            "grafico": distribuicao_de_notas(faixas),
        },
    )


def ler_marcacoes(dados, linhas):
    """Lê do formulário a presença de cada aluno.

    Cada aluno envia "presenca_<id>" (presente/falta) e "metodo_<id>" (BIOMETRIA/MANUAL).
    Só são lidos os alunos da própria turma, e as linhas travadas são ignoradas.
    Retorna ({matricula_id: (presente, metodo)}, [nomes de quem ficou sem marcação]).
    """
    metodos_validos = {valor for valor, _rotulo in Frequencia.Metodo.choices}
    marcacoes, sem_marcacao = {}, []
    for linha in linhas:
        if linha["travada"]:
            continue
        matricula = linha["matricula"]
        escolha = dados.get(f"presenca_{matricula.pk}")
        if escolha not in ("presente", "falta"):
            sem_marcacao.append(matricula.aluno.get_full_name() or matricula.aluno.matricula)
            continue
        presente = escolha == "presente"
        metodo = dados.get(f"metodo_{matricula.pk}")
        # A biometria é simulada no navegador; uma falta é sempre registrada como manual.
        if not presente or metodo not in metodos_validos:
            metodo = Frequencia.Metodo.MANUAL
        marcacoes[matricula.pk] = (presente, metodo)
    return marcacoes, sem_marcacao


def pagina_de_justificativas(request, aba, com_erro=None):
    """Monta a tela de justificativas.

    com_erro: formulário enviado com erro. Ele aparece de novo no card da justificativa
    certa, com o que o professor digitou e as mensagens de erro.
    """
    todas = servicos.justificativas_do_professor(request.user)
    pendentes = todas.filter(status=Justificativa.Status.PENDENTE)
    avaliadas = todas.exclude(status=Justificativa.Status.PENDENTE).order_by("-avaliada_em")

    lista = list(pendentes if aba == "pendentes" else avaliadas[:50])
    if aba == "pendentes":
        # Cada justificativa pendente ganha o próprio formulário. O prefixo deixa os nomes
        # dos campos diferentes em cada card (ex.: "j12-decisao").
        for justificativa in lista:
            if com_erro and com_erro.prefix == f"j{justificativa.pk}":
                justificativa.form = com_erro
            else:
                justificativa.form = AvaliarJustificativaForm(prefix=f"j{justificativa.pk}")

    return render(
        request,
        "professor/justificativas.html",
        {
            "aba": aba,
            "lista": lista,
            "total_pendentes": pendentes.count(),
            "total_avaliadas": avaliadas.count(),
        },
    )


@login_required
@perfil_requerido("PROFESSOR")
def justificativas(request):
    aba = "avaliadas" if request.GET.get("aba") == "avaliadas" else "pendentes"
    return pagina_de_justificativas(request, aba)


@login_required
@perfil_requerido("PROFESSOR")
@require_POST
def avaliar_justificativa(request, pk):
    """Aprova ou rejeita. A frequência do aluno não muda, como informa a tela do aluno."""
    justificativa = get_object_or_404(servicos.justificativas_do_professor(request.user), pk=pk)

    if justificativa.status != Justificativa.Status.PENDENTE:
        messages.warning(request, "Esta justificativa já tinha sido avaliada.")
        return redirect("professor:justificativas")

    form = AvaliarJustificativaForm(request.POST, prefix=f"j{pk}")
    if not form.is_valid():
        messages.error(request, "A justificativa não foi avaliada. Confira os campos destacados.")
        return pagina_de_justificativas(request, "pendentes", com_erro=form)

    justificativa.status = form.cleaned_data["decisao"]
    justificativa.resposta = form.cleaned_data["resposta"].strip()
    justificativa.avaliada_por = request.user
    justificativa.avaliada_em = timezone.now()
    justificativa.save(update_fields=["status", "resposta", "avaliada_por", "avaliada_em"])

    aluno = justificativa.frequencia.matricula.aluno
    nome = aluno.get_full_name() or aluno.matricula
    messages.success(
        request, f"Justificativa de {nome} {justificativa.get_status_display().lower()}."
    )
    return redirect("professor:justificativas")


@login_required
@perfil_requerido("PROFESSOR")
def anexo_justificativa(request, pk):
    """Só o professor da disciplina baixa o atestado. Para os outros, ele "não existe"."""
    justificativa = get_object_or_404(servicos.justificativas_do_professor(request.user), pk=pk)
    if not justificativa.anexo:
        raise Http404("Esta justificativa não tem anexo.")
    return baixar_anexo(justificativa.anexo)
