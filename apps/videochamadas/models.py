"""Videochamadas entre a coordenação e os professores (o aluno não participa).

O vídeo não passa pelo portal. Com VIDEO_MODO=proprio (o padrão), ele vai direto de um
navegador ao outro (WebRTC, static/js/chamada.js), e o portal só leva os "sinais" que os dois
navegadores trocam para se encontrar (model SinalChamada). Com VIDEO_MODO=jitsi, a chamada
acontece no Jitsi Meet, em outra aba, como antes. Nos dois modos o portal:
1. cria a chamada e avisa a outra pessoa pelo sino (apps/alertas/regras.py, aviso_de_chamada);
2. guarda o histórico de quem chamou quem, e quando.

Explicação em docs/VIDEOCHAMADA.md.
"""

import json
import secrets
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.contas.models import Usuario

# Uma chamada que ninguém encerrou deixa de aparecer como "em andamento" depois deste tempo.
DURACAO_MAXIMA = timedelta(hours=3)

PERFIS_DA_CHAMADA = (Usuario.Perfil.COORDENADOR, Usuario.Perfil.PROFESSOR)


def nome_de_sala():
    """Nome da sala no Jitsi: um prefixo fixo e 24 letras e números sorteados.

    No Jitsi, quem conhece o nome da sala entra nela. Por isso o nome é sorteado pelo módulo
    secrets (o mesmo das senhas provisórias), e não montado com o número da chamada.
    """
    return f"InstitutoSocratico-{secrets.token_hex(12)}"


def nome_na_chamada(usuario):
    """Nome mostrado nas telas e no Jitsi, como "Prof. Ricardo Almeida".

    Diferente de Mensagens, o coordenador aparece com o próprio nome, e não como
    "Secretaria acadêmica": o professor precisa saber com quem vai falar.
    """
    return usuario.nome_com_tratamento or usuario.matricula


class ChamadaQuerySet(models.QuerySet):
    def do_usuario(self, usuario):
        """Somente as chamadas de que a pessoa participa. É a base da permissão."""
        return self.filter(Q(criada_por=usuario) | Q(convidado=usuario))


class Chamada(models.Model):
    # PROTECT: as contas nunca são apagadas pela coordenação, só desativadas.
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chamadas_criadas",
        limit_choices_to={"perfil__in": PERFIS_DA_CHAMADA},
        verbose_name="quem chamou",
    )
    convidado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chamadas_recebidas",
        limit_choices_to={"perfil__in": PERFIS_DA_CHAMADA},
        verbose_name="convidado",
    )
    assunto = models.CharField("assunto", max_length=120, blank=True)
    sala = models.CharField(
        "sala no Jitsi", max_length=60, unique=True, default=nome_de_sala, editable=False
    )
    criada_em = models.DateTimeField("criada em", default=timezone.now, editable=False)
    encerrada_em = models.DateTimeField("encerrada em", null=True, blank=True)

    objects = ChamadaQuerySet.as_manager()

    class Meta:
        verbose_name = "videochamada"
        verbose_name_plural = "videochamadas"
        ordering = ["-criada_em", "-id"]

    def __str__(self):
        return f"{self.criada_por} → {self.convidado} ({self.criada_em:%d/%m/%Y %H:%M})"

    def clean(self):
        """A chamada é sempre entre um coordenador e um professor, nos dois sentidos."""
        if not (self.criada_por_id and self.convidado_id):
            return
        perfis = {self.criada_por.perfil, self.convidado.perfil}
        if perfis != set(PERFIS_DA_CHAMADA):
            raise ValidationError(
                {"convidado": "A chamada precisa ser entre um coordenador e um professor."}
            )

    def outro_participante(self, usuario):
        return self.convidado if usuario.pk == self.criada_por_id else self.criada_por

    def id_do_outro(self, usuario):
        """Como outro_participante, mas só o número da conta (não busca a pessoa no banco)."""
        return self.convidado_id if usuario.pk == self.criada_por_id else self.criada_por_id

    @property
    def em_andamento(self):
        return self.encerrada_em is None and timezone.now() - self.criada_em < DURACAO_MAXIMA

    @property
    def situacao(self):
        return "Em andamento" if self.em_andamento else "Encerrada"

    def link_do_jitsi(self, usuario):
        """Endereço da sala no Jitsi, já com o nome da pessoa e o assunto preenchidos.

        A parte depois do "#" não é enviada ao servidor do Jitsi: quem a lê é a página do
        Jitsi, no navegador. Os valores vão em JSON (com aspas) e codificados para URL.
        """
        def valor(texto):
            return quote(json.dumps(texto, ensure_ascii=False), safe="")

        opcoes = [f"userInfo.displayName={valor(nome_na_chamada(usuario))}"]
        if self.assunto:
            opcoes.append(f"config.subject={valor(self.assunto)}")
        return f"{settings.JITSI_SERVIDOR}/{self.sala}#{'&'.join(opcoes)}"


# Sinais com mais deste tempo são apagados (a chamada já acabou ou a negociação já terminou).
VALIDADE_DO_SINAL = timedelta(hours=2)


class SinalChamada(models.Model):
    """Um recado curto de um navegador para o outro, na sala de vídeo própria.

    Para dois navegadores conversarem direto (WebRTC), eles precisam antes trocar alguns
    recados: "entrei", a oferta, a resposta e os candidatos de rede (endereços onde cada um
    pode ser encontrado). O portal guarda esses recados aqui, e cada navegador pergunta a cada
    1 segundo se chegou algo novo para ele (polling). O vídeo em si nunca passa por aqui.

    Os sinais são descartáveis: apagados quando a chamada é encerrada e depois de 2 horas.
    """

    class Tipo(models.TextChoices):
        ENTREI = "entrei", "Entrei na sala"
        OFERTA = "oferta", "Oferta"
        RESPOSTA = "resposta", "Resposta"
        CANDIDATO = "candidato", "Candidato de rede"
        SAIU = "saiu", "Saí da sala"

    chamada = models.ForeignKey(Chamada, on_delete=models.CASCADE, related_name="sinais")
    de = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+", verbose_name="de"
    )
    para = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+", verbose_name="para"
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    conteudo = models.JSONField("conteúdo", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", default=timezone.now)

    class Meta:
        verbose_name = "sinal de videochamada"
        verbose_name_plural = "sinais de videochamada"
        ordering = ["id"]
        # A consulta de cada segundo é "sinais desta chamada, para mim, depois do número X".
        indexes = [models.Index(fields=["chamada", "para", "id"], name="sinal_chamada_para_id")]

    def __str__(self):
        return f"{self.get_tipo_display()} (chamada {self.chamada_id})"
