"""Modelos acadêmicos. O diagrama de entidades está em docs/DER.md.

Média, frequência e selo de situação não ficam salvos no banco: são calculados em
calculos.py a partir das notas e presenças, para nunca existirem valores divergentes.

As chaves estrangeiras usam PROTECT: apagar uma turma ou um aluno que já tem notas e
presenças gera erro, em vez de apagar o histórico acadêmico sem ninguém perceber.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.contas.models import Usuario

TAMANHO_MAXIMO_ANEXO = 5 * 1024 * 1024  # 5 MB, limite indicado no protótipo

VALIDADORES_NOTA = [MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))]


def validar_tamanho_anexo(arquivo):
    if arquivo.size > TAMANHO_MAXIMO_ANEXO:
        raise ValidationError("O anexo deve ter no máximo 5 MB.")


class Curso(models.Model):
    nome = models.CharField("nome", max_length=100, unique=True)
    total_creditos = models.PositiveSmallIntegerField("total de créditos")

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Disciplina(models.Model):
    curso = models.ForeignKey(
        Curso, on_delete=models.PROTECT, related_name="disciplinas", verbose_name="curso"
    )
    codigo = models.CharField("código", max_length=10, unique=True)
    nome = models.CharField("nome", max_length=100)
    creditos = models.PositiveSmallIntegerField("créditos")
    carga_horaria = models.PositiveSmallIntegerField("carga horária (horas-aula)")

    class Meta:
        verbose_name = "disciplina"
        verbose_name_plural = "disciplinas"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class Turma(models.Model):
    curso = models.ForeignKey(
        Curso, on_delete=models.PROTECT, related_name="turmas", verbose_name="curso"
    )
    codigo = models.CharField("código", max_length=20)
    semestre = models.CharField(
        "semestre",
        max_length=6,
        validators=[RegexValidator(r"^\d{4}\.[12]$", "Use o formato 2026.2.")],
    )
    periodo = models.PositiveSmallIntegerField("período")

    class Meta:
        verbose_name = "turma"
        verbose_name_plural = "turmas"
        ordering = ["-semestre", "codigo"]
        constraints = [
            models.UniqueConstraint(fields=["codigo", "semestre"], name="turma_unica_no_semestre"),
        ]

    def __str__(self):
        return f"{self.codigo} ({self.semestre})"


class Oferta(models.Model):
    """Uma disciplina em uma turma, com o professor que a leciona.

    É a base da permissão do professor: ele só acessa as ofertas ligadas a ele.
    """

    turma = models.ForeignKey(
        Turma, on_delete=models.PROTECT, related_name="ofertas", verbose_name="turma"
    )
    disciplina = models.ForeignKey(
        Disciplina, on_delete=models.PROTECT, related_name="ofertas", verbose_name="disciplina"
    )
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ofertas",
        limit_choices_to={"perfil": Usuario.Perfil.PROFESSOR},
        verbose_name="professor",
    )

    class Meta:
        verbose_name = "oferta de disciplina"
        verbose_name_plural = "ofertas de disciplinas"
        ordering = ["turma__codigo", "disciplina__nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["turma", "disciplina"], name="disciplina_unica_na_turma"
            ),
        ]

    def __str__(self):
        return f"{self.disciplina.nome} - {self.turma.codigo}"

    def clean(self):
        if self.turma_id and self.disciplina_id:
            if self.turma.curso_id != self.disciplina.curso_id:
                raise ValidationError("A disciplina precisa ser do mesmo curso da turma.")
        if self.professor_id and self.professor.perfil != Usuario.Perfil.PROFESSOR:
            raise ValidationError({"professor": "O usuário escolhido não é professor."})


class Matricula(models.Model):
    class Situacao(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        TRANCADA = "TRANCADA", "Trancada"
        EVADIDA = "EVADIDA", "Evadida"
        CONCLUIDA = "CONCLUIDA", "Concluída"

    aluno = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="matriculas",
        limit_choices_to={"perfil": Usuario.Perfil.ALUNO},
        verbose_name="aluno",
    )
    turma = models.ForeignKey(
        Turma, on_delete=models.PROTECT, related_name="matriculas", verbose_name="turma"
    )
    situacao = models.CharField(
        "situação", max_length=9, choices=Situacao.choices, default=Situacao.ATIVA
    )
    data_matricula = models.DateField("data da matrícula", default=timezone.localdate)
    # Histórico simplificado: resume os semestres anteriores, que não são cadastrados.
    creditos_concluidos = models.PositiveSmallIntegerField("créditos concluídos", default=0)
    coeficiente_rendimento = models.DecimalField(
        "coeficiente de rendimento",
        max_digits=4,
        decimal_places=2,
        default=Decimal("0"),
        validators=VALIDADORES_NOTA,
    )

    class Meta:
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        ordering = ["turma__codigo", "aluno__first_name", "aluno__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["aluno", "turma"], name="aluno_unico_na_turma"),
        ]

    def __str__(self):
        return f"{self.aluno.get_full_name() or self.aluno.matricula} - {self.turma.codigo}"

    def clean(self):
        if self.aluno_id and self.aluno.perfil != Usuario.Perfil.ALUNO:
            raise ValidationError({"aluno": "O usuário escolhido não é aluno."})


class Avaliacao(models.Model):
    class Tipo(models.TextChoices):
        PROVA = "PROVA", "Prova"
        ENTREGA = "ENTREGA", "Entrega"

    oferta = models.ForeignKey(
        Oferta, on_delete=models.PROTECT, related_name="avaliacoes", verbose_name="oferta"
    )
    nome = models.CharField("nome", max_length=60)
    tipo = models.CharField("tipo", max_length=7, choices=Tipo.choices, default=Tipo.PROVA)
    data_hora = models.DateTimeField("data e hora")
    local = models.CharField("local", max_length=60, blank=True)

    class Meta:
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"
        ordering = ["data_hora"]
        constraints = [
            models.UniqueConstraint(fields=["oferta", "nome"], name="avaliacao_unica_na_oferta"),
        ]

    def __str__(self):
        return f"{self.nome} - {self.oferta}"


class Nota(models.Model):
    avaliacao = models.ForeignKey(
        Avaliacao, on_delete=models.PROTECT, related_name="notas", verbose_name="avaliação"
    )
    matricula = models.ForeignKey(
        Matricula, on_delete=models.PROTECT, related_name="notas", verbose_name="matrícula"
    )
    valor = models.DecimalField(
        "nota", max_digits=4, decimal_places=2, validators=VALIDADORES_NOTA
    )
    atualizada_em = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "nota"
        verbose_name_plural = "notas"
        ordering = ["avaliacao__data_hora"]
        constraints = [
            models.UniqueConstraint(
                fields=["avaliacao", "matricula"], name="nota_unica_por_avaliacao"
            ),
            # Os validadores protegem os formulários; esta regra protege o próprio banco.
            models.CheckConstraint(
                condition=Q(valor__gte=0) & Q(valor__lte=10), name="nota_entre_0_e_10"
            ),
        ]

    def __str__(self):
        return f"{self.matricula} - {self.avaliacao.nome}: {self.valor}"

    def clean(self):
        if self.avaliacao_id and self.matricula_id:
            if self.avaliacao.oferta.turma_id != self.matricula.turma_id:
                raise ValidationError("O aluno não pertence à turma desta avaliação.")


class Aula(models.Model):
    """Uma aula dada, que corresponde a uma chamada."""

    oferta = models.ForeignKey(
        Oferta, on_delete=models.PROTECT, related_name="aulas", verbose_name="oferta"
    )
    data = models.DateField("data")
    horas_aula = models.PositiveSmallIntegerField(
        "horas-aula", default=2, validators=[MinValueValidator(1)]
    )
    conteudo = models.CharField("conteúdo", max_length=200, blank=True)

    class Meta:
        verbose_name = "aula"
        verbose_name_plural = "aulas"
        ordering = ["-data"]
        constraints = [
            models.UniqueConstraint(fields=["oferta", "data"], name="aula_unica_por_dia"),
        ]

    def __str__(self):
        return f"{self.oferta} em {self.data:%d/%m/%Y}"


class Frequencia(models.Model):
    """Log de presença de um aluno em uma aula."""

    class Metodo(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        BIOMETRIA = "BIOMETRIA", "Biometria simulada"

    aula = models.ForeignKey(
        Aula, on_delete=models.PROTECT, related_name="frequencias", verbose_name="aula"
    )
    matricula = models.ForeignKey(
        Matricula, on_delete=models.PROTECT, related_name="frequencias", verbose_name="matrícula"
    )
    presente = models.BooleanField("presente", default=True)
    metodo = models.CharField(
        "método", max_length=9, choices=Metodo.choices, default=Metodo.MANUAL
    )
    registrada_em = models.DateTimeField("registrada em", auto_now_add=True)

    class Meta:
        verbose_name = "frequência"
        verbose_name_plural = "frequências"
        ordering = ["-aula__data"]
        constraints = [
            models.UniqueConstraint(
                fields=["aula", "matricula"], name="frequencia_unica_por_aula"
            ),
        ]

    def __str__(self):
        situacao = "presente" if self.presente else "falta"
        return f"{self.matricula} - {self.aula.data:%d/%m/%Y}: {situacao}"

    def clean(self):
        if self.aula_id and self.matricula_id:
            if self.aula.oferta.turma_id != self.matricula.turma_id:
                raise ValidationError("O aluno não pertence à turma desta aula.")


class Justificativa(models.Model):
    """Pedido do aluno para justificar uma falta.

    Mesmo aprovada, a justificativa não altera a frequência, como informa o protótipo.
    Uma falta pode ter mais de uma justificativa, caso o aluno reenvie após uma rejeição.
    """

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        APROVADA = "APROVADA", "Aprovada"
        REJEITADA = "REJEITADA", "Rejeitada"

    frequencia = models.ForeignKey(
        Frequencia,
        on_delete=models.PROTECT,
        related_name="justificativas",
        verbose_name="falta",
    )
    motivo = models.TextField("motivo")
    anexo = models.FileField(
        "anexo",
        upload_to="justificativas/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]),
            validar_tamanho_anexo,
        ],
    )
    status = models.CharField(
        "situação", max_length=9, choices=Status.choices, default=Status.PENDENTE
    )
    avaliada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="justificativas_avaliadas",
        verbose_name="avaliada por",
    )
    resposta = models.TextField("resposta", blank=True)
    criada_em = models.DateTimeField("enviada em", auto_now_add=True)
    avaliada_em = models.DateTimeField("avaliada em", null=True, blank=True)

    class Meta:
        verbose_name = "justificativa"
        verbose_name_plural = "justificativas"
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.frequencia} ({self.get_status_display()})"

    def clean(self):
        if self.frequencia_id and self.frequencia.presente:
            raise ValidationError({"frequencia": "Só é possível justificar uma falta."})


class Evento(models.Model):
    """Data do calendário. Provas e entregas vêm de Avaliacao, não daqui."""

    class Tipo(models.TextChoices):
        INSTITUCIONAL = "INSTITUCIONAL", "Institucional"
        FERIADO = "FERIADO", "Feriado"
        ATIVIDADE = "ATIVIDADE", "Atividade da disciplina"

    titulo = models.CharField("título", max_length=100)
    tipo = models.CharField(
        "tipo", max_length=13, choices=Tipo.choices, default=Tipo.INSTITUCIONAL
    )
    inicio = models.DateTimeField("início")
    fim = models.DateTimeField("fim", null=True, blank=True)
    local = models.CharField("local", max_length=60, blank=True)
    descricao = models.TextField("descrição", blank=True)
    # Sem oferta, o evento é institucional e aparece para todos.
    oferta = models.ForeignKey(
        Oferta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos",
        verbose_name="oferta",
    )

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"
        ordering = ["inicio"]

    def __str__(self):
        return f"{self.titulo} ({self.inicio:%d/%m/%Y})"

    def clean(self):
        if self.inicio and self.fim and self.fim < self.inicio:
            raise ValidationError({"fim": "O fim não pode ser antes do início."})
