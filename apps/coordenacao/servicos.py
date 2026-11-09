"""Consultas e regras da área da coordenação.

A coordenação enxerga a instituição inteira, então aqui não há filtro por usuário logado:
a proteção é o @perfil_requerido("COORDENADOR") de cada view.
"""

import secrets

from django.db.models import Count, Q

from apps.academico.calculos import EM_ATENCAO, EM_RISCO, REGULAR, resumo_das_matriculas
from apps.academico.models import Matricula, Turma
from apps.contas.models import Usuario

# Perfis que a coordenação pode gerenciar. Contas ADMIN ficam só no Django Admin.
PERFIS_GERENCIADOS = (
    Usuario.Perfil.ALUNO,
    Usuario.Perfil.PROFESSOR,
    Usuario.Perfil.COORDENADOR,
)

SITUACOES = (REGULAR, EM_ATENCAO, EM_RISCO)

# Sem letras e números parecidos (0/O, 1/l/I), para a senha ser ditada sem confusão.
CARACTERES_SENHA = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gerar_senha_provisoria(tamanho=10):
    """Senha aleatória para uma conta nova. O módulo secrets é o indicado para senhas."""
    return "".join(secrets.choice(CARACTERES_SENHA) for _ in range(tamanho))


def contas_gerenciadas():
    return Usuario.objects.filter(perfil__in=PERFIS_GERENCIADOS)


def ultima_matricula(aluno):
    """Matrícula mais recente do aluno, em qualquer situação (ativa, trancada...)."""
    return (
        Matricula.objects.filter(aluno=aluno)
        .select_related("turma__curso")
        .order_by("-turma__semestre", "-pk")
        .first()
    )


def tem_historico(matricula):
    """True se a matrícula já tem notas ou presenças. Aí ela não pode trocar de turma."""
    return matricula.notas.exists() or matricula.frequencias.exists()


def linhas_de_alunos():
    """Uma linha por aluno, com a matrícula mais recente e a situação calculada.

    Usada na lista de alunos. São poucas consultas, qualquer que seja o número de alunos.
    """
    alunos = list(Usuario.objects.filter(perfil=Usuario.Perfil.ALUNO))
    ultimas = {}
    for matricula in (
        Matricula.objects.select_related("turma")
        .filter(aluno__perfil=Usuario.Perfil.ALUNO)
        .order_by("aluno_id", "-turma__semestre", "-pk")
    ):
        ultimas.setdefault(matricula.aluno_id, matricula)  # fica só a primeira (mais recente)

    resumo = resumo_das_matriculas(list(ultimas.values()))
    linhas = []
    for aluno in alunos:
        matricula = ultimas.get(aluno.pk)
        dados = resumo.get(matricula.pk, {}) if matricula else {}
        ativa = matricula is not None and matricula.situacao == Matricula.Situacao.ATIVA
        linhas.append(
            {
                "aluno": aluno,
                "matricula": matricula,
                "media": dados.get("media"),
                "frequencia": dados.get("frequencia"),
                # O selo só vale para quem está cursando; os demais mostram a matrícula.
                "situacao": dados.get("situacao") if ativa else None,
                "ativa": ativa,
            }
        )
    linhas.sort(key=lambda linha: linha["aluno"].get_full_name().casefold())
    return linhas


def filtrar_por_busca(linhas, busca, usuario_de=lambda linha: linha):
    """Mantém as linhas cujo nome ou matrícula contêm o texto buscado."""
    termo = busca.strip().casefold()
    if not termo:
        return linhas
    return [
        linha
        for linha in linhas
        if termo in usuario_de(linha).get_full_name().casefold()
        or termo in usuario_de(linha).matricula.casefold()
    ]


def matriculas_ativas():
    return list(
        Matricula.objects.filter(situacao=Matricula.Situacao.ATIVA).select_related(
            "aluno", "turma"
        )
    )


def turmas_com_contagens():
    """Turmas com o número de alunos ativos e de disciplinas, do semestre mais novo ao mais antigo."""
    return Turma.objects.select_related("curso").annotate(
        total_alunos=Count(
            "matriculas",
            filter=Q(matriculas__situacao=Matricula.Situacao.ATIVA),
            distinct=True,
        ),
        total_disciplinas=Count("ofertas", distinct=True),
    )


def semestre_atual():
    """O semestre mais recente cadastrado, como "2026.2". None se não há turmas."""
    return Turma.objects.order_by("-semestre").values_list("semestre", flat=True).first()
