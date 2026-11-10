"""O que cada perfil enxerga na API. São as mesmas regras das telas:

- aluno: só as próprias matrículas, as suas turmas e as disciplinas dessas turmas;
- professor: só as disciplinas que leciona (ofertas) e as turmas delas; os alunos, ele vê
  no desempenho de cada disciplina;
- coordenação: a instituição inteira.

Os viewsets partem sempre destas funções. Um registro fora do escopo responde 404, como se
não existisse, para ninguém descobrir dados de outra pessoa trocando o número na URL
(o mesmo comportamento da área do professor).
"""

from apps.academico.models import Matricula, Oferta, Turma
from apps.professor.servicos import ofertas_do_professor

from .permissoes import ALUNO, COORDENADOR, PROFESSOR


def perfil_de(usuario):
    """Perfil do usuário, ou None para o visitante anônimo (ele não tem esse campo).

    O visitante nunca chega a ver dados, pois a permissão pede login antes. Mas o
    drf-spectacular chama estas funções sem usuário para montar a documentação.
    """
    return getattr(usuario, "perfil", None)


def matriculas_visiveis(usuario):
    """Matrículas com a média e o selo gerais (todas as disciplinas juntas).

    O professor não entra aqui: a média geral mistura as notas de outros professores.
    Ele vê os seus alunos em /api/ofertas/{id}/desempenho/, só na disciplina dele.
    """
    consulta = Matricula.objects.select_related("aluno", "turma__curso")
    if perfil_de(usuario) == COORDENADOR:
        return consulta
    if perfil_de(usuario) == ALUNO:
        return consulta.filter(aluno=usuario)
    return consulta.none()


def ofertas_visiveis(usuario):
    if perfil_de(usuario) == PROFESSOR:
        return ofertas_do_professor(usuario)
    consulta = Oferta.objects.select_related("turma__curso", "disciplina", "professor")
    if perfil_de(usuario) == COORDENADOR:
        return consulta
    if perfil_de(usuario) == ALUNO:
        return consulta.filter(turma__matriculas__aluno=usuario).distinct()
    return consulta.none()


def turmas_visiveis(usuario):
    consulta = Turma.objects.select_related("curso")
    if perfil_de(usuario) == COORDENADOR:
        return consulta
    if perfil_de(usuario) == PROFESSOR:
        return consulta.filter(ofertas__professor=usuario).distinct()
    if perfil_de(usuario) == ALUNO:
        return consulta.filter(matriculas__aluno=usuario).distinct()
    return consulta.none()
