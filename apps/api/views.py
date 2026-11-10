"""Endpoints da API REST (Django REST Framework). Documentação navegável em /api/docs/.

A API só consulta (GET). As gravações (notas, chamada, contas) continuam nas telas, que já
aplicam as regras de cada uma. Toda requisição precisa de login: pela sessão do navegador
ou pelo token (cabeçalho "Authorization: Token <token>", obtido em POST /api/token/).

Cada endpoint tem duas camadas de proteção:
- permissão (permissoes.py): o perfil pode usar o endpoint? Se não: 403;
- escopo (escopo.py): quais registros o usuário enxerga. Fora do escopo: 404.

Os números vêm das mesmas funções das telas e dos relatórios (apps/academico/calculos.py),
então a API nunca mostra uma média diferente da que aparece no boletim.
"""

from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.academico.calculos import (
    frequencia_das_linhas,
    indicadores_da_turma,
    resumo_da_oferta,
    resumo_da_turma,
    resumo_das_matriculas,
    resumo_por_disciplina,
)
from apps.academico.models import Curso, Disciplina, Matricula
from apps.analytics.models import RiscoEvasao
from apps.relatorios import dados
from apps.relatorios.filtros import MatriculaFiltro, RiscoFiltro, descrever
from apps.relatorios.views import EXCEL, PDF, SELOS, baixar, ler_formato, riscos_com_aluno

from . import escopo
from .permissoes import ALUNO, COORDENADOR, PERFIS_DO_PORTAL, PROFESSOR, so_perfis
from .serializers import (
    BoletimSerializer,
    CursoSerializer,
    DesempenhoDaOfertaSerializer,
    DesempenhoDaTurmaSerializer,
    DisciplinaSerializer,
    EuSerializer,
    MatriculaSerializer,
    OfertaSerializer,
    PedidoDeTokenSerializer,
    RiscoSerializer,
    TokenSerializer,
    TurmaSerializer,
)

# --- Quem está usando a API e o token de acesso ---


class EuView(APIView):
    @extend_schema(
        tags=["Acesso"],
        summary="Dados de quem está usando a API",
        responses=EuSerializer,
    )
    def get(self, request):
        return Response(EuSerializer(request.user).data)


class TokenView(APIView):
    """POST: troca matrícula e senha por um token. DELETE: apaga o token (sair).

    O token não expira sozinho: vale até ser apagado aqui, no Django Admin, ou até a conta
    ser desativada pela coordenação (o DRF recusa token de conta inativa).
    """

    # Só o token: o POST vem de quem ainda não tem login, e assim não há checagem de CSRF.
    authentication_classes = [TokenAuthentication]
    # No máximo 10 tentativas por minuto, para dificultar quem tenta adivinhar senhas.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token"

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated()]
        return [AllowAny()]

    @extend_schema(
        tags=["Acesso"],
        summary="Obter o token de acesso",
        description=(
            "Envie a matrícula e a senha do login. A resposta traz o token, que vai em todas "
            'as requisições seguintes no cabeçalho "Authorization: Token <token>". '
            "Pedir de novo devolve o mesmo token."
        ),
        request=PedidoDeTokenSerializer,
        responses={
            200: TokenSerializer,
            400: OpenApiResponse(description="Matrícula ou senha incorretas, ou conta desativada."),
            403: OpenApiResponse(description="Conta de administrador (usa só o Django Admin)."),
        },
        auth=[],
    )
    def post(self, request):
        pedido = PedidoDeTokenSerializer(data=request.data)
        pedido.is_valid(raise_exception=True)
        usuario = authenticate(
            request,
            matricula=pedido.validated_data["matricula"],
            password=pedido.validated_data["senha"],
        )
        # authenticate devolve None para senha errada e também para conta desativada.
        if usuario is None:
            return Response(
                {"detail": "Matrícula ou senha incorretas."}, status=status.HTTP_400_BAD_REQUEST
            )
        if usuario.perfil not in PERFIS_DO_PORTAL:
            return Response(
                {"detail": "Contas de administrador usam o Django Admin, não a API."},
                status=status.HTTP_403_FORBIDDEN,
            )
        token, _ = Token.objects.get_or_create(user=usuario)
        return Response({"token": token.key, "perfil": usuario.perfil})

    @extend_schema(
        tags=["Acesso"],
        summary="Apagar o token (sair)",
        description="Depois disso, o token antigo deixa de funcionar. Um POST gera outro.",
        request=None,
        responses={204: None},
    )
    def delete(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Cadastro acadêmico ---


@extend_schema_view(
    list=extend_schema(summary="Listar cursos"),
    retrieve=extend_schema(summary="Um curso"),
)
@extend_schema(tags=["Cadastro acadêmico"])
class CursoViewSet(viewsets.ReadOnlyModelViewSet):
    """Cursos da instituição. Todos os perfis veem."""

    queryset = Curso.objects.order_by("nome")
    serializer_class = CursoSerializer


@extend_schema_view(
    list=extend_schema(summary="Listar disciplinas", description="Filtro: ?curso=<id>."),
    retrieve=extend_schema(summary="Uma disciplina"),
)
@extend_schema(tags=["Cadastro acadêmico"])
class DisciplinaViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo de disciplinas. Todos os perfis veem."""

    queryset = Disciplina.objects.order_by("nome")
    serializer_class = DisciplinaSerializer
    filterset_fields = ["curso"]


@extend_schema_view(
    list=extend_schema(
        summary="Listar turmas",
        description=(
            "Aluno: as turmas em que está matriculado. Professor: as turmas em que dá aula. "
            "Coordenação: todas. Filtros: ?curso=<id>&semestre=2026.2."
        ),
    ),
    retrieve=extend_schema(summary="Uma turma"),
)
@extend_schema(tags=["Turmas"])
class TurmaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TurmaSerializer
    filterset_fields = ["curso", "semestre"]

    def get_queryset(self):
        return escopo.turmas_visiveis(self.request.user)

    @extend_schema(
        summary="Desempenho da turma (coordenação)",
        description=(
            "Um resumo por aluno ativo (média geral, frequência global, disciplinas em risco e "
            "a pior situação entre elas) e os indicadores da turma. "
            "São os mesmos números do relatório de desempenho da turma."
        ),
        responses=DesempenhoDaTurmaSerializer,
    )
    @action(detail=True, permission_classes=[so_perfis(COORDENADOR)])
    def desempenho(self, request, pk=None):
        turma = self.get_object()
        linhas = resumo_da_turma(turma)
        resposta = {
            "turma": turma,
            "disciplinas": turma.ofertas.select_related("turma", "disciplina", "professor"),
            "indicadores": indicadores_da_turma(linhas),
            "alunos": [
                {**linha, "matricula": linha["matricula"].pk, "aluno": linha["matricula"].aluno}
                for linha in linhas
            ],
        }
        return Response(DesempenhoDaTurmaSerializer(resposta).data)


@extend_schema_view(
    list=extend_schema(
        summary="Listar disciplinas das turmas (ofertas)",
        description=(
            "Uma oferta é uma disciplina em uma turma, com o professor que a leciona. "
            "Aluno: as da sua turma. Professor: só as que leciona. Coordenação: todas. "
            "Filtros: ?turma=<id>&disciplina=<id>."
        ),
    ),
    retrieve=extend_schema(summary="Uma oferta"),
)
@extend_schema(tags=["Turmas"])
class OfertaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OfertaSerializer
    filterset_fields = ["turma", "disciplina"]

    def get_queryset(self):
        return escopo.ofertas_visiveis(self.request.user)

    @extend_schema(
        summary="Desempenho da disciplina (professor e coordenação)",
        description=(
            "Uma linha por aluno ativo, com a nota de cada avaliação, a média, a frequência "
            "e o selo, e os indicadores da turma nesta disciplina. O professor só consulta as "
            "disciplinas que leciona (as outras respondem 404)."
        ),
        responses=DesempenhoDaOfertaSerializer,
    )
    @action(detail=True, permission_classes=[so_perfis(PROFESSOR, COORDENADOR)])
    def desempenho(self, request, pk=None):
        oferta = self.get_object()
        avaliacoes, linhas = resumo_da_oferta(oferta)
        resposta = {
            "oferta": oferta,
            "avaliacoes": avaliacoes,
            "indicadores": indicadores_da_turma(linhas),
            "alunos": [
                {
                    **linha,
                    "matricula": linha["matricula"].pk,
                    "aluno": linha["matricula"].aluno,
                    # resumo_da_oferta devolve as notas na ordem das avaliações.
                    "notas": [
                        {"avaliacao": avaliacao.nome, "valor": valor}
                        for avaliacao, valor in zip(avaliacoes, linha["notas"])
                    ],
                }
                for linha in linhas
            ],
        }
        return Response(DesempenhoDaOfertaSerializer(resposta).data)


# --- Alunos (matrículas) ---


def anexar_resumo(matriculas):
    """Calcula média, frequência e selo de várias matrículas de uma vez (duas consultas) e
    guarda o resultado em matricula.resumo, que o MatriculaSerializer lê."""
    resumo = resumo_das_matriculas(matriculas)
    for matricula in matriculas:
        matricula.resumo = dict(resumo[matricula.pk])
        if matricula.situacao != Matricula.Situacao.ATIVA:
            matricula.resumo["situacao"] = None  # o selo só vale para quem está cursando


@extend_schema_view(
    list=extend_schema(
        summary="Listar alunos (uma linha por matrícula)",
        description=(
            "Cada item é um aluno em uma turma, com a média geral, a frequência global e a "
            "pior situação entre as disciplinas. Aluno: só as próprias matrículas. "
            "Coordenação: todas. Professor: 403 (ele vê os seus alunos no desempenho de cada "
            "disciplina, sem as notas dos outros professores). "
            "Filtros: ?busca=<nome ou RA>&turma=<id>&situacao_matricula=ATIVA."
        ),
    ),
    retrieve=extend_schema(summary="Um aluno (matrícula)"),
)
@extend_schema(tags=["Alunos"])
class MatriculaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MatriculaSerializer
    filterset_class = MatriculaFiltro
    permission_classes = [so_perfis(ALUNO, COORDENADOR)]

    def get_queryset(self):
        return escopo.matriculas_visiveis(self.request.user).order_by(
            "aluno__first_name", "aluno__last_name", "-turma__semestre", "pk"
        )

    def get_serializer(self, instancia=None, *args, **kwargs):
        # Antes de virar JSON, as matrículas desta página recebem os números calculados.
        if instancia is not None:
            anexar_resumo(instancia if kwargs.get("many") else [instancia])
        return super().get_serializer(instancia, *args, **kwargs)

    @extend_schema(
        summary="Boletim do aluno",
        description=(
            "Uma linha por disciplina da turma, com as notas de cada avaliação, a média, a "
            "frequência e o selo. Os mesmos números da tela Notas e do boletim em PDF."
        ),
        responses=BoletimSerializer,
    )
    @action(detail=True)
    def boletim(self, request, pk=None):
        matricula = self.get_object()
        linhas = resumo_por_disciplina(matricula)
        resposta = {
            "matricula": matricula.pk,
            "aluno": matricula.aluno,
            "turma": matricula.turma,
            "frequencia_global": frequencia_das_linhas(linhas),
            "coeficiente_rendimento": matricula.coeficiente_rendimento,
            "creditos_concluidos": matricula.creditos_concluidos,
            "disciplinas": [
                {
                    **linha,
                    "oferta": linha["oferta"].pk,
                    "disciplina": linha["oferta"].disciplina,
                    "professor": dados.professor_da(linha["oferta"]),
                    "notas": [
                        {"avaliacao": nome, "valor": valor}
                        for nome, valor in linha["notas_nomeadas"]
                    ],
                }
                for linha in linhas
            ],
        }
        return Response(BoletimSerializer(resposta).data)


# --- Risco de evasão (módulo preditivo) ---


@extend_schema_view(
    list=extend_schema(
        summary="Listar alunos com risco de evasão calculado",
        description=(
            "Resultado do modelo preditivo (RandomForest), do maior para o menor risco. "
            "Níveis: BAIXO (abaixo de 30%), MEDIO (30% a 60%) e ALTO (a partir de 60%). "
            "Filtros: ?nivel=ALTO&turma=<id>&busca=<nome ou RA>."
        ),
    ),
    retrieve=extend_schema(summary="Risco de uma matrícula"),
)
@extend_schema(tags=["Risco de evasão"])
class RiscoViewSet(viewsets.ReadOnlyModelViewSet):
    """Só a coordenação. O endereço usa o número da matrícula: /api/riscos/<matrícula>/,
    porque o registro do risco é apagado e gravado de novo a cada cálculo."""

    serializer_class = RiscoSerializer
    filterset_class = RiscoFiltro
    permission_classes = [so_perfis(COORDENADOR)]
    lookup_field = "matricula"
    lookup_url_kwarg = "matricula"
    queryset = RiscoEvasao.objects.none()  # só para a documentação; a consulta real vem abaixo

    def get_queryset(self):
        return riscos_com_aluno()


# --- Relatórios em PDF e Excel (os mesmos da etapa 10) ---


class SemNegociacao(BaseContentNegotiation):
    """Os relatórios devolvem sempre um arquivo, então não há formato para negociar.

    Sem isto, o Swagger manda "Accept: application/pdf" e o DRF responderia 406, pois os
    seus renderizadores só sabem escrever JSON. Os erros (403, 404) continuam em JSON.
    """

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ARQUIVO_PDF = {(200, "application/pdf"): OpenApiTypes.BINARY}
ARQUIVO_EXCEL = {(200, TIPO_EXCEL): OpenApiTypes.BINARY}
FORMATO = OpenApiParameter(
    "formato", str, enum=[PDF, EXCEL], default=PDF, description="pdf (padrão) ou xlsx."
)
BUSCA = OpenApiParameter("busca", str, description="Parte do nome ou do RA do aluno.")
TURMA = OpenApiParameter("turma", int, description="Número (id) da turma.")


class RelatorioView(APIView):
    """Base dos downloads: lê ?formato=, monta o relatório com apps/relatorios/dados.py e
    devolve o arquivo. Cada relatório só diz quem pode baixar e como montar o conteúdo."""

    content_negotiation_class = SemNegociacao
    formatos = (PDF, EXCEL)

    def get(self, request, pk=None):
        formato = ler_formato(request, self.formatos)  # formato desconhecido: 404
        return baixar(self.montar(request, pk), formato)

    def montar(self, request, pk):
        raise NotImplementedError


@extend_schema_view(
    get=extend_schema(
        tags=["Relatórios"],
        summary="Boletim em PDF",
        description="Aluno: só o próprio. Coordenação: de qualquer matrícula. O número é o da matrícula.",
        responses=ARQUIVO_PDF,
    )
)
class BoletimArquivoView(RelatorioView):
    permission_classes = [so_perfis(ALUNO, COORDENADOR)]
    formatos = (PDF,)

    def montar(self, request, pk):
        return dados.boletim(get_object_or_404(escopo.matriculas_visiveis(request.user), pk=pk))


@extend_schema_view(
    get=extend_schema(
        tags=["Relatórios"],
        summary="Desempenho da disciplina em PDF ou Excel",
        description="Professor: só as disciplinas que leciona. Coordenação: qualquer uma. O número é o da oferta.",
        parameters=[FORMATO],
        responses={**ARQUIVO_PDF, **ARQUIVO_EXCEL},
    )
)
class DisciplinaArquivoView(RelatorioView):
    permission_classes = [so_perfis(PROFESSOR, COORDENADOR)]

    def montar(self, request, pk):
        return dados.desempenho_da_disciplina(
            get_object_or_404(escopo.ofertas_visiveis(request.user), pk=pk)
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Relatórios"],
        summary="Desempenho da turma em PDF ou Excel (coordenação)",
        parameters=[FORMATO],
        responses={**ARQUIVO_PDF, **ARQUIVO_EXCEL},
    )
)
class TurmaArquivoView(RelatorioView):
    permission_classes = [so_perfis(COORDENADOR)]

    def montar(self, request, pk):
        return dados.desempenho_da_turma(get_object_or_404(escopo.turmas_visiveis(request.user), pk=pk))


@extend_schema_view(
    get=extend_schema(
        tags=["Relatórios"],
        summary="Alunos em risco de evasão em PDF ou Excel (coordenação)",
        parameters=[
            FORMATO,
            OpenApiParameter("nivel", str, enum=RiscoEvasao.Nivel.values, description="Nível de risco."),
            TURMA,
            BUSCA,
        ],
        responses={**ARQUIVO_PDF, **ARQUIVO_EXCEL},
    )
)
class RiscoArquivoView(RelatorioView):
    permission_classes = [so_perfis(COORDENADOR)]

    def montar(self, request, pk):
        filtro = RiscoFiltro(request.GET, queryset=riscos_com_aluno())
        return dados.alunos_em_risco(filtro.qs, descrever(filtro))


@extend_schema_view(
    get=extend_schema(
        tags=["Relatórios"],
        summary="Lista de alunos em Excel (coordenação)",
        parameters=[
            OpenApiParameter("formato", str, enum=[EXCEL], default=EXCEL, description="Só xlsx."),
            TURMA,
            BUSCA,
            OpenApiParameter(
                "situacao_matricula", str, enum=Matricula.Situacao.values, description="Situação da matrícula."
            ),
            OpenApiParameter("situacao", str, enum=list(SELOS), description="Selo calculado."),
        ],
        responses=ARQUIVO_EXCEL,
    )
)
class AlunosArquivoView(RelatorioView):
    permission_classes = [so_perfis(COORDENADOR)]
    formatos = (EXCEL,)

    def montar(self, request, pk):
        filtro = MatriculaFiltro(request.GET, queryset=Matricula.objects.all())
        selo = request.GET.get("situacao", "")
        return dados.lista_de_alunos(filtro.qs, selo if selo in SELOS else "", descrever(filtro))
