"""Regras dos alertas: quem recebe qual aviso, e quando.

Rotina diária (tarefa rotina_diaria, agendada para as 6h):
- Frequência global abaixo de 75%       -> aluno         (Em risco, também por e-mail)
- Média abaixo de 6                     -> aluno         (Em risco, também por e-mail)
- Risco de evasão alto (modelo de ML)   -> coordenadores (Em risco, também por e-mail)
- Justificativas sem resposta há 3 dias -> professor     (Em atenção, só no sistema)

Avisos na hora, disparados por uma ação de alguém:
- Nota publicada                        -> aluno         (Informativo)
- Justificativa aprovada ou rejeitada   -> aluno         (Informativo ou Em atenção)
- Mensagem nova na caixa de mensagens   -> quem recebe   (Informativo, um aviso por conversa)
- Convite para videochamada            -> convidado     (Informativo, um aviso por chamada)

Os limites são os mesmos do selo de situação (apps/academico/calculos.py), então o alerta
concorda com o que as outras telas mostram. Só os alertas "Em risco" vão por e-mail.

Este arquivo só decide e grava. Quem chama estas funções e manda os e-mails é tasks.py.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from apps.academico.calculos import FREQUENCIA_MINIMA, MEDIA_RISCO, resumo_das_matriculas
from apps.academico.models import Justificativa, Matricula, Nota
from apps.analytics.evasao import numero_br
from apps.analytics.models import RiscoEvasao
from apps.contas.models import Usuario
from apps.mensagens.models import nome_de_exibicao
from apps.videochamadas.models import nome_na_chamada

from .models import Alerta

# O mesmo assunto (mesma pessoa e mesma chave) não gera outro alerta antes de 7 dias.
# Sem isso, quem está com frequência baixa receberia um alerta igual todo dia.
JANELA_SEM_REPETIR = timedelta(days=7)

# Justificativa pendente há mais do que isto vira lembrete para o professor.
DIAS_PARA_LEMBRAR_O_PROFESSOR = 3


def nome_de(usuario):
    return usuario.get_full_name() or usuario.matricula


def salvar_alertas(candidatos):
    """Grava os alertas novos e devolve a lista do que foi gravado.

    Pula quem já recebeu um alerta com a mesma chave dentro da janela de 7 dias.
    Uma consulta para conferir as repetições e uma para gravar, qualquer que seja o total.
    """
    if not candidatos:
        return []
    ja_avisados = set(
        Alerta.objects.filter(
            criado_em__gte=timezone.now() - JANELA_SEM_REPETIR,
            chave__in={alerta.chave for alerta in candidatos},
        ).values_list("destinatario_id", "chave")
    )
    novos = []
    for alerta in candidatos:
        assunto = (alerta.destinatario_id, alerta.chave)
        if assunto not in ja_avisados:
            ja_avisados.add(assunto)  # evita duplicar dentro da própria lista
            novos.append(alerta)
    return Alerta.objects.bulk_create(novos)


# --- Rotina diária ---


def alertas_do_dia():
    """Roda as quatro regras da rotina diária e devolve os alertas gravados."""
    return salvar_alertas(
        [
            *alertas_de_frequencia_e_media(),
            *alertas_de_risco_de_evasao(),
            *lembretes_de_justificativas(),
        ]
    )


def alertas_de_frequencia_e_media():
    """Avisa o aluno com frequência abaixo de 75% ou média abaixo de 6.

    Usa os mesmos números da coordenação (resumo_das_matriculas): duas consultas para todos.
    Aluno sem chamada ou sem nota ainda não tem o que avisar.
    """
    matriculas = list(
        Matricula.objects.filter(
            situacao=Matricula.Situacao.ATIVA, aluno__is_active=True
        ).select_related("aluno")
    )
    resumo = resumo_das_matriculas(matriculas)

    alertas = []
    for matricula in matriculas:
        frequencia = resumo[matricula.pk]["frequencia"]
        media = resumo[matricula.pk]["media"]
        if frequencia is not None and frequencia < FREQUENCIA_MINIMA:
            alertas.append(
                Alerta(
                    destinatario=matricula.aluno,
                    tipo=Alerta.Tipo.FREQUENCIA_BAIXA,
                    gravidade=Alerta.Gravidade.RISCO,
                    titulo="Sua frequência está abaixo do mínimo",
                    texto=(
                        f"Sua frequência global é de {numero_br(frequencia)}%, abaixo do mínimo "
                        f"de {FREQUENCIA_MINIMA}%. Converse com seus professores ou com a "
                        "secretaria para não perder as disciplinas por falta."
                    ),
                    link=reverse("aluno:frequencia"),
                    chave=f"frequencia-{matricula.pk}",
                    por_email=True,
                )
            )
        if media is not None and media < MEDIA_RISCO:
            alertas.append(
                Alerta(
                    destinatario=matricula.aluno,
                    tipo=Alerta.Tipo.MEDIA_BAIXA,
                    gravidade=Alerta.Gravidade.RISCO,
                    titulo="Sua média está abaixo de 6",
                    texto=(
                        f"Sua média geral é {numero_br(media)}, abaixo de {MEDIA_RISCO}. "
                        "Veja no boletim quais disciplinas precisam de mais atenção e procure "
                        "os professores para tirar dúvidas."
                    ),
                    link=reverse("aluno:notas"),
                    chave=f"media-{matricula.pk}",
                    por_email=True,
                )
            )
    return alertas


def alertas_de_risco_de_evasao():
    """Avisa todos os coordenadores ativos sobre cada aluno com risco de evasão alto."""
    coordenadores = list(
        Usuario.objects.filter(perfil=Usuario.Perfil.COORDENADOR, is_active=True)
    )
    if not coordenadores:
        return []

    alertas = []
    riscos = RiscoEvasao.objects.filter(
        nivel=RiscoEvasao.Nivel.ALTO, matricula__situacao=Matricula.Situacao.ATIVA
    ).select_related("matricula__aluno", "matricula__turma")
    for risco in riscos:
        aluno = risco.matricula.aluno
        texto = (
            f"{nome_de(aluno)} (RA {aluno.matricula}, turma {risco.matricula.turma.codigo}) "
            f"tem {numero_br(risco.probabilidade)}% de chance de evasão, segundo o modelo "
            "preditivo."
        )
        if risco.motivos:
            texto += " Motivos: " + "; ".join(risco.motivos) + "."
        for coordenador in coordenadores:
            alertas.append(
                Alerta(
                    destinatario=coordenador,
                    tipo=Alerta.Tipo.RISCO_EVASAO,
                    gravidade=Alerta.Gravidade.RISCO,
                    titulo=f"Risco alto de evasão: {nome_de(aluno)}"[:120],
                    texto=texto,
                    link=reverse("coordenacao:risco") + "?" + urlencode({"busca": aluno.matricula}),
                    chave=f"evasao-{risco.matricula_id}",
                    por_email=True,
                )
            )
    return alertas


def lembretes_de_justificativas():
    """Lembra o professor das justificativas que esperam resposta há mais de 3 dias.

    Um único lembrete por professor, com o total, em vez de um por justificativa.
    """
    limite = timezone.now() - timedelta(days=DIAS_PARA_LEMBRAR_O_PROFESSOR)
    por_professor = dict(
        Justificativa.objects.filter(status=Justificativa.Status.PENDENTE, criada_em__lte=limite)
        .order_by()
        .values("frequencia__aula__oferta__professor")
        .annotate(total=Count("id"))
        .values_list("frequencia__aula__oferta__professor", "total")
    )
    professores = Usuario.objects.filter(pk__in=por_professor, is_active=True)

    alertas = []
    for professor in professores:
        total = por_professor[professor.pk]
        quantas = f"{total} justificativas aguardam" if total > 1 else "1 justificativa aguarda"
        alertas.append(
            Alerta(
                destinatario=professor,
                tipo=Alerta.Tipo.JUSTIFICATIVA_ATRASADA,
                gravidade=Alerta.Gravidade.ATENCAO,
                titulo="Justificativas esperando a sua avaliação",
                texto=(
                    f"{quantas} resposta há mais de {DIAS_PARA_LEMBRAR_O_PROFESSOR} dias. Enquanto isso, "
                    "o aluno não sabe se a falta foi aceita."
                ),
                link=reverse("professor:justificativas"),
                chave="justificativas-pendentes",
            )
        )
    return alertas


# --- Avisos na hora ---


def avisos_de_notas(avaliacao):
    """Avisa cada aluno que tem nota nesta avaliação. A nota em si não vai no aviso:
    ela pode ser corrigida depois, e o boletim sempre mostra o valor atual."""
    disciplina = avaliacao.oferta.disciplina.nome
    notas = Nota.objects.filter(
        avaliacao=avaliacao,
        matricula__situacao=Matricula.Situacao.ATIVA,
        matricula__aluno__is_active=True,
    ).select_related("matricula__aluno")
    return salvar_alertas(
        [
            Alerta(
                destinatario=nota.matricula.aluno,
                tipo=Alerta.Tipo.NOTA_LANCADA,
                gravidade=Alerta.Gravidade.INFORMATIVO,
                titulo=f"Nota publicada: {avaliacao.nome}"[:120],
                texto=f"Sua nota na avaliação {avaliacao.nome} de {disciplina} já está no boletim.",
                link=reverse("aluno:notas"),
                chave=f"nota-{avaliacao.pk}",
            )
            for nota in notas
        ]
    )


def aviso_de_justificativa(justificativa):
    """Conta ao aluno a decisão do professor sobre a justificativa de falta."""
    if justificativa.status == Justificativa.Status.PENDENTE:
        return []
    aula = justificativa.frequencia.aula
    aprovada = justificativa.status == Justificativa.Status.APROVADA
    decisao = justificativa.get_status_display().lower()
    texto = (
        f"Sua justificativa da falta de {aula.data:%d/%m/%Y} em {aula.oferta.disciplina.nome} "
        f"foi {decisao}."
    )
    if justificativa.resposta:
        texto += f" Resposta do professor: {justificativa.resposta}"
    return salvar_alertas(
        [
            Alerta(
                destinatario=justificativa.frequencia.matricula.aluno,
                tipo=Alerta.Tipo.JUSTIFICATIVA_AVALIADA,
                gravidade=Alerta.Gravidade.INFORMATIVO if aprovada else Alerta.Gravidade.ATENCAO,
                titulo=f"Justificativa {decisao}",
                texto=texto,
                link=reverse("aluno:frequencia"),
                chave=f"justificativa-{justificativa.pk}",
            )
        ]
    )


def chave_da_conversa(conversa_id):
    """Identifica os avisos de mensagem de uma conversa (usada também ao abrir a conversa)."""
    return f"mensagem-{conversa_id}"


def aviso_de_mensagem(mensagem):
    """Avisa quem recebeu a mensagem. Devolve a lista com o alerta criado (ou vazia).

    Só existe um aviso não lido por conversa: se a pessoa ainda não leu o anterior, a mensagem
    nova entra na mesma conversa e o sino não enche. Depois que ela abre a conversa, o aviso é
    marcado como lido (apps/mensagens/views.py) e a próxima mensagem avisa de novo. Por isso
    esta regra não usa salvar_alertas, que bloquearia novos avisos por 7 dias.
    """
    conversa = mensagem.conversa
    destinatario = conversa.outro_participante(mensagem.remetente)
    if not destinatario.is_active:
        return []
    chave = chave_da_conversa(conversa.pk)
    if Alerta.objects.filter(destinatario=destinatario, chave=chave, lido_em__isnull=True).exists():
        return []
    return [
        Alerta.objects.create(
            destinatario=destinatario,
            tipo=Alerta.Tipo.MENSAGEM_NOVA,
            gravidade=Alerta.Gravidade.INFORMATIVO,
            titulo=f"Nova mensagem de {nome_de_exibicao(mensagem.remetente)}"[:120],
            texto=f"Assunto: {conversa.assunto}",
            link=f"{reverse('mensagens:caixa')}?{urlencode({'conversa': conversa.pk})}",
            chave=chave,
        )
    ]


def chave_da_chamada(chamada_id):
    """Identifica o convite de uma videochamada (usada também ao abrir a sala)."""
    return f"chamada-{chamada_id}"


def aviso_de_chamada(chamada):
    """Avisa o convidado de que alguém está chamando. Devolve o alerta criado.

    Cada chamada é um assunto novo, então não há janela de 7 dias (salvar_alertas): duas
    chamadas no mesmo dia geram dois convites. Quem abre a sala marca o convite como lido
    (apps/videochamadas/views.py).
    """
    if chamada.assunto:
        texto = f"Assunto: {chamada.assunto}"
    else:
        texto = "Abra o convite para entrar na sala."
    titulo = f"{nome_na_chamada(chamada.criada_por)} chamou você para uma videochamada"
    return Alerta.objects.create(
        destinatario=chamada.convidado,
        tipo=Alerta.Tipo.VIDEOCHAMADA,
        gravidade=Alerta.Gravidade.INFORMATIVO,
        titulo=titulo[:120],
        texto=texto,
        link=reverse("videochamadas:sala", args=[chamada.pk]),
        chave=chave_da_chamada(chamada.pk),
    )
