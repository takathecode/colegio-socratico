"""Serializers: transformam registros e cálculos em JSON.

Há dois tipos aqui:
- ModelSerializer: para os registros do banco (curso, turma, matrícula...);
- Serializer simples: para os resultados calculados (boletim, desempenho), que são
  dicionários montados em views.py com as funções de apps/academico/calculos.py.
Os dois descrevem cada campo, e o drf-spectacular usa essa descrição na documentação.

Todos os campos são só de leitura: a API só consulta (as gravações ficam nas telas, com as
regras de chamada, notas e contas). Os números saem como números no JSON (6.75), sem
arredondar para uma casa como no PDF.
"""

from rest_framework import serializers

from apps.academico.models import Curso, Disciplina, Matricula, Oferta, Turma
from apps.analytics.models import RiscoEvasao
from apps.contas.models import Usuario

SITUACAO_AJUDA = 'Selo calculado: "Regular", "Em atenção" ou "Em risco". Nulo sem notas nem chamadas.'


def nota(**opcoes):
    return serializers.DecimalField(max_digits=4, decimal_places=2, allow_null=True, **opcoes)


def percentual(**opcoes):
    return serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True, **opcoes)


def situacao():
    return serializers.CharField(allow_null=True, help_text=SITUACAO_AJUDA)


# --- Pessoas ---


class PessoaSerializer(serializers.ModelSerializer):
    """Aluno ou professor dentro de outro registro: só RA e nome."""

    ra = serializers.CharField(source="matricula", help_text="Matrícula (RA) usada no login.")
    nome = serializers.CharField(source="get_full_name")

    class Meta:
        model = Usuario
        fields = ["ra", "nome"]


class EuSerializer(serializers.ModelSerializer):
    ra = serializers.CharField(source="matricula")
    nome = serializers.CharField(source="get_full_name")
    nome_com_tratamento = serializers.CharField(help_text='Ex.: "Prof. Ricardo Almeida".')
    perfil_nome = serializers.CharField(source="get_perfil_display")

    class Meta:
        model = Usuario
        fields = ["ra", "nome", "nome_com_tratamento", "email", "perfil", "perfil_nome"]


# --- Cadastro acadêmico ---


class CursoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Curso
        fields = ["id", "nome", "total_creditos"]


class DisciplinaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disciplina
        fields = ["id", "codigo", "nome", "creditos", "carga_horaria", "curso"]


class DisciplinaResumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disciplina
        fields = ["id", "codigo", "nome"]


class TurmaResumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Turma
        fields = ["id", "codigo", "semestre"]


class TurmaSerializer(serializers.ModelSerializer):
    curso = CursoSerializer()

    class Meta:
        model = Turma
        fields = ["id", "codigo", "semestre", "periodo", "curso"]


class OfertaSerializer(serializers.ModelSerializer):
    """Uma disciplina em uma turma, com o professor que a leciona."""

    turma = TurmaResumoSerializer()
    disciplina = DisciplinaResumoSerializer()
    professor = serializers.CharField(source="professor.nome_com_tratamento")

    class Meta:
        model = Oferta
        fields = ["id", "turma", "disciplina", "professor"]


class MatriculaSerializer(serializers.ModelSerializer):
    """Um aluno em uma turma. Média, frequência e selo vêm de resumo_das_matriculas.

    A view coloca o resultado do cálculo em "resumo" antes de serializar (views.py).
    """

    aluno = PessoaSerializer()
    turma = TurmaResumoSerializer()
    situacao_matricula = serializers.CharField(
        source="situacao", help_text="ATIVA, TRANCADA, EVADIDA ou CONCLUIDA."
    )
    media = nota(source="resumo.media", help_text="Média das médias das disciplinas com nota.")
    frequencia = percentual(
        source="resumo.frequencia", help_text="Frequência global (%), somando todas as disciplinas."
    )
    disciplinas_em_risco = serializers.IntegerField(source="resumo.disciplinas_em_risco")
    situacao = serializers.CharField(
        source="resumo.situacao",
        allow_null=True,
        help_text="A pior situação entre as disciplinas. Nulo se a matrícula não está ativa.",
    )

    class Meta:
        model = Matricula
        fields = [
            "id",
            "aluno",
            "turma",
            "situacao_matricula",
            "data_matricula",
            "creditos_concluidos",
            "coeficiente_rendimento",
            "media",
            "frequencia",
            "disciplinas_em_risco",
            "situacao",
        ]


class RiscoSerializer(serializers.ModelSerializer):
    """Resultado do modelo preditivo de evasão para uma matrícula ativa."""

    matricula = serializers.IntegerField(source="matricula_id")
    aluno = PessoaSerializer(source="matricula.aluno")
    turma = TurmaResumoSerializer(source="matricula.turma")
    nivel_nome = serializers.CharField(source="get_nivel_display")
    motivos = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = RiscoEvasao
        fields = [
            "matricula",
            "aluno",
            "turma",
            "probabilidade",
            "nivel",
            "nivel_nome",
            "motivos",
            "frequencia",
            "media",
            "tendencia",
            "justificativas_pendentes",
            "calculado_em",
        ]


# --- Resultados calculados (dicionários montados em views.py) ---


class NotaSerializer(serializers.Serializer):
    avaliacao = serializers.CharField(help_text='Nome da avaliação, como "A1".')
    valor = nota(help_text="Nula se a nota ainda não foi lançada.")


class IndicadoresSerializer(serializers.Serializer):
    alunos = serializers.IntegerField(help_text="Alunos com matrícula ativa.")
    media = nota(help_text="Média da turma.")
    frequencia = percentual(help_text="Média simples das frequências dos alunos (%).")
    regulares = serializers.IntegerField()
    atencao = serializers.IntegerField(help_text='Alunos "Em atenção".')
    risco = serializers.IntegerField(help_text='Alunos "Em risco".')


class DisciplinaDoBoletimSerializer(serializers.Serializer):
    oferta = serializers.IntegerField()
    disciplina = DisciplinaResumoSerializer()
    professor = serializers.CharField()
    notas = NotaSerializer(many=True)
    media = nota()
    horas_dadas = serializers.IntegerField()
    horas_faltas = serializers.IntegerField()
    frequencia = percentual()
    situacao = situacao()


class BoletimSerializer(serializers.Serializer):
    matricula = serializers.IntegerField()
    aluno = PessoaSerializer()
    turma = TurmaSerializer()
    frequencia_global = percentual()
    coeficiente_rendimento = nota()
    creditos_concluidos = serializers.IntegerField()
    disciplinas = DisciplinaDoBoletimSerializer(many=True)


class AvaliacaoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nome = serializers.CharField()
    tipo = serializers.CharField(help_text="PROVA ou ENTREGA.")
    data_hora = serializers.DateTimeField()


class AlunoDaOfertaSerializer(serializers.Serializer):
    matricula = serializers.IntegerField()
    aluno = PessoaSerializer()
    notas = NotaSerializer(many=True, help_text="Na mesma ordem de 'avaliacoes'.")
    media = nota()
    horas_faltas = serializers.IntegerField()
    frequencia = percentual()
    situacao = situacao()


class DesempenhoDaOfertaSerializer(serializers.Serializer):
    oferta = OfertaSerializer()
    avaliacoes = AvaliacaoSerializer(many=True)
    indicadores = IndicadoresSerializer()
    alunos = AlunoDaOfertaSerializer(many=True)


class AlunoDaTurmaSerializer(serializers.Serializer):
    matricula = serializers.IntegerField()
    aluno = PessoaSerializer()
    media = nota(help_text="Média das médias das disciplinas.")
    frequencia = percentual(help_text="Frequência global (%).")
    disciplinas_em_risco = serializers.IntegerField()
    situacao = situacao()


class DesempenhoDaTurmaSerializer(serializers.Serializer):
    turma = TurmaSerializer()
    disciplinas = OfertaSerializer(many=True)
    indicadores = IndicadoresSerializer()
    alunos = AlunoDaTurmaSerializer(many=True)


# --- Token de acesso ---


class PedidoDeTokenSerializer(serializers.Serializer):
    matricula = serializers.CharField(help_text="A mesma matrícula do login.")
    senha = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(help_text='Envie no cabeçalho: "Authorization: Token <token>".')
    perfil = serializers.CharField()
