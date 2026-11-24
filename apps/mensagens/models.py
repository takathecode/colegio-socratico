"""Caixa de mensagens interna: conversas entre um aluno e um professor, a coordenação ou a Secretaria."""

import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.academico.models import VALIDADORES_ANEXO, Oferta
from apps.contas.models import Usuario


# Quem pode estar do outro lado da conversa com o aluno.
PERFIS_DE_CONTATO = (
    Usuario.Perfil.PROFESSOR,
    Usuario.Perfil.COORDENADOR,
    Usuario.Perfil.SECRETARIA,
)


def nome_de_exibicao(usuario):
    """Nome mostrado na conversa. As contas da Secretaria atendem como "Secretaria acadêmica"."""
    if usuario.perfil == Usuario.Perfil.SECRETARIA:
        return "Secretaria acadêmica"
    return usuario.nome_com_tratamento or usuario.matricula


class ConversaQuerySet(models.QuerySet):
    def do_usuario(self, usuario):
        """Somente as conversas de que a pessoa participa. É a base da permissão."""
        return self.filter(Q(aluno=usuario) | Q(contato=usuario))


class Conversa(models.Model):
    aluno = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conversas_como_aluno",
        limit_choices_to={"perfil": Usuario.Perfil.ALUNO},
        verbose_name="aluno",
    )
    # Quem fala com o aluno: um professor, um coordenador ou a Secretaria.
    contato = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conversas_como_contato",
        limit_choices_to={"perfil__in": list(PERFIS_DE_CONTATO)},
        verbose_name="contato",
    )
    assunto = models.CharField("assunto", max_length=120)
    # Disciplina do assunto, quando a conversa é com um professor.
    oferta = models.ForeignKey(
        Oferta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conversas",
        verbose_name="disciplina",
    )
    criada_em = models.DateTimeField("criada em", default=timezone.now, editable=False)

    objects = ConversaQuerySet.as_manager()

    class Meta:
        verbose_name = "conversa"
        verbose_name_plural = "conversas"
        ordering = ["-criada_em"]

    def __str__(self):
        return self.assunto

    def clean(self):
        if self.aluno_id and self.aluno.perfil != Usuario.Perfil.ALUNO:
            raise ValidationError({"aluno": "O usuário escolhido não é aluno."})
        if self.contato_id and self.contato.perfil not in PERFIS_DE_CONTATO:
            raise ValidationError(
                {"contato": "O contato precisa ser professor, coordenador ou da Secretaria."}
            )

    def outro_participante(self, usuario):
        return self.contato if usuario.pk == self.aluno_id else self.aluno


class Mensagem(models.Model):
    # CASCADE: uma mensagem não existe sem a sua conversa.
    conversa = models.ForeignKey(
        Conversa, on_delete=models.CASCADE, related_name="mensagens", verbose_name="conversa"
    )
    remetente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mensagens_enviadas",
        verbose_name="remetente",
    )
    texto = models.TextField("mensagem")
    anexo = models.FileField(
        "anexo", upload_to="mensagens/%Y/%m/", blank=True, validators=VALIDADORES_ANEXO
    )
    enviada_em = models.DateTimeField("enviada em", default=timezone.now, editable=False)
    # Vazio enquanto o destinatário não abriu a conversa.
    lida_em = models.DateTimeField("lida em", null=True, blank=True)

    class Meta:
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"
        ordering = ["enviada_em"]

    def __str__(self):
        return f"{self.remetente}: {self.texto[:40]}"

    @property
    def nome_do_anexo(self):
        return os.path.basename(self.anexo.name)
