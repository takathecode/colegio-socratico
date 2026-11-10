"""Conteúdo de cada relatório, montado uma única vez e entregue a pdf.py e a excel.py.

A ideia é separar "o que mostrar" de "como desenhar":
- aqui ficam as consultas e as contas (sempre pelas funções de apps/academico/calculos.py,
  para o relatório mostrar os mesmos números das telas);
- pdf.py e excel.py só recebem um Relatorio pronto e o desenham, cada um do seu jeito.
Assim, o PDF e o Excel de um mesmo relatório nunca mostram números diferentes.
"""

from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.text import slugify

from apps.academico.calculos import (
    FREQUENCIA_MINIMA,
    MEDIA_MINIMA,
    frequencia_das_linhas,
    indicadores_da_turma,
    resumo_da_oferta,
    resumo_das_matriculas,
    resumo_por_disciplina,
)
from apps.academico.models import Matricula
from apps.analytics.dados import contar_por_faixa
from apps.analytics.evasao import LIMITE_ALTO, LIMITE_MEDIO, numero_br
from apps.analytics.graficos import distribuicao_de_notas, notas_por_disciplina
from apps.analytics.models import RiscoEvasao

# Tipos de coluna: dizem ao PDF como escrever o valor (o Excel guarda o número puro).
TEXTO = "texto"
NOTA = "nota"  # 6.75 vira "6,7" no PDF
PERCENTUAL = "percentual"  # 88.89 vira "88,8%" no PDF
INTEIRO = "inteiro"
SITUACAO = "situacao"  # selo colorido no PDF: Regular, Em atenção, Em risco...

OBSERVACAO_LIMITES = (
    f"Nota parcial = média das avaliações lançadas. Média mínima: {numero_br(MEDIA_MINIMA)} · "
    f"frequência mínima: {int(FREQUENCIA_MINIMA)}%. Em risco: média abaixo de 6 ou "
    f"frequência abaixo de {int(FREQUENCIA_MINIMA)}%."
)
OBSERVACAO_NUMEROS = (
    "No PDF os números aparecem com uma casa, cortando a segunda em vez de arredondar "
    "(74,96% aparece como 74,9%, e não como 75%, que pareceria estar no limite)."
)


@dataclass
class Coluna:
    titulo: str
    tipo: str = TEXTO
    largura: float = 1  # largura relativa no PDF: 2 ocupa o dobro de 1


@dataclass
class Tabela:
    titulo: str  # no PDF vira o título da seção; no Excel, o nome da aba
    colunas: list
    linhas: list  # cada linha é uma lista de valores, na mesma ordem das colunas
    subtitulo: str = ""
    vazio: str = "Nenhum registro para mostrar."


@dataclass
class Relatorio:
    titulo: str
    subtitulo: str
    nome_arquivo: str  # sem extensão; a view acrescenta .pdf ou .xlsx
    informacoes: list = field(default_factory=list)  # pares (rótulo, texto) do quadro do topo
    tabelas: list = field(default_factory=list)
    graficos: list = field(default_factory=list)  # dicionários de apps/analytics/graficos.py
    observacoes: list = field(default_factory=list)
    paisagem: bool = False  # folha deitada, para tabelas com muitas colunas
    emitido_em: object = field(default_factory=timezone.localtime)


def formatar(valor, tipo=TEXTO):
    """Valor como texto para o PDF. Dado que ainda não existe aparece como travessão."""
    if valor is None or valor == "":
        return "—"
    if tipo in (NOTA, PERCENTUAL):
        numero = numero_br(valor)
        if numero == "-0,0":  # tendência de -0,04 cortada em uma casa: é zero
            numero = "0,0"
        return f"{numero}%" if tipo == PERCENTUAL else numero
    return str(valor)


def nome_de(usuario):
    return usuario.get_full_name() or usuario.matricula


def nome_de_arquivo(*partes):
    """Ex.: ("boletim", "2026001", "2026.2") vira "boletim-2026001-2026-2"."""
    # O ponto vira hífen antes do slugify, que o apagaria ("2026.2" viraria "20262").
    return "-".join(slugify(str(parte).replace(".", "-")) for parte in partes if parte)


def professor_da(oferta):
    return oferta.professor.nome_com_tratamento or nome_de(oferta.professor)


# --- Boletim do aluno ---


def boletim(matricula):
    """Boletim do semestre: uma linha por disciplina, com as notas de cada avaliação."""
    aluno, turma = matricula.aluno, matricula.turma
    linhas = resumo_por_disciplina(matricula)
    total_creditos = turma.curso.total_creditos

    tabela = Tabela(
        titulo="Disciplinas do semestre",
        colunas=[
            Coluna("Disciplina", largura=2.6),
            Coluna("Professor", largura=2),
            Coluna("Avaliações", largura=2.4),
            Coluna("Média", NOTA, 0.8),
            Coluna("Frequência", PERCENTUAL, 1.2),
            Coluna("Faltas (h)", INTEIRO, 0.8),
            Coluna("Situação", SITUACAO, 1.3),
        ],
        linhas=[
            [
                linha["oferta"].disciplina.nome,
                professor_da(linha["oferta"]),
                # "A1 6,8 · A2 6,5", na ordem em que as avaliações aconteceram.
                " · ".join(f"{nome} {numero_br(valor)}" for nome, valor in linha["notas_nomeadas"]),
                linha["media"],
                linha["frequencia"],
                linha["horas_faltas"],
                linha["situacao"],
            ]
            for linha in linhas
        ],
        vazio="A turma ainda não tem disciplinas cadastradas.",
    )

    grafico = notas_por_disciplina(linhas)
    return Relatorio(
        titulo=f"Boletim do semestre {turma.semestre}",
        subtitulo=f"{nome_de(aluno)} · RA {aluno.matricula}",
        nome_arquivo=nome_de_arquivo("boletim", aluno.matricula, turma.semestre),
        informacoes=[
            ("Aluno", nome_de(aluno)),
            ("RA", aluno.matricula),
            ("Curso", turma.curso.nome),
            ("Turma", f"{turma.codigo} · {turma.periodo}º período"),
            ("Matrícula", matricula.get_situacao_display()),
            ("Frequência global", formatar(frequencia_das_linhas(linhas), PERCENTUAL)),
            ("Coeficiente de rendimento", formatar(matricula.coeficiente_rendimento, NOTA)),
            ("Créditos concluídos", f"{matricula.creditos_concluidos} de {total_creditos}"),
        ],
        tabelas=[tabela],
        graficos=[grafico] if grafico else [],
        observacoes=[
            OBSERVACAO_LIMITES,
            OBSERVACAO_NUMEROS,
            "Documento emitido pelo sistema para consulta. Não substitui o histórico escolar oficial.",
        ],
    )


# --- Desempenho de uma disciplina (professor) e da turma inteira (coordenação) ---


def tabela_da_oferta(oferta):
    """Uma linha por aluno ativo, com uma coluna para cada avaliação da disciplina.

    Retorna (tabela, linhas de resumo_da_oferta), para quem quiser calcular os indicadores.
    """
    avaliacoes, linhas = resumo_da_oferta(oferta)
    tabela = Tabela(
        titulo=oferta.disciplina.nome,
        subtitulo=f"{professor_da(oferta)} · {len(avaliacoes)} avaliação(ões) · {len(linhas)} aluno(s)",
        colunas=[
            Coluna("Aluno", largura=2.6),
            Coluna("RA", largura=1.2),
            *(Coluna(avaliacao.nome, NOTA, 0.7) for avaliacao in avaliacoes),
            Coluna("Média", NOTA, 0.8),
            Coluna("Frequência", PERCENTUAL, 1.2),
            Coluna("Faltas (h)", INTEIRO, 0.8),
            Coluna("Situação", SITUACAO, 1.3),
        ],
        linhas=[
            [
                nome_de(linha["matricula"].aluno),
                linha["matricula"].aluno.matricula,
                *linha["notas"],
                linha["media"],
                linha["frequencia"],
                linha["horas_faltas"],
                linha["situacao"],
            ]
            for linha in linhas
        ],
        vazio="Nenhum aluno ativo nesta turma.",
    )
    return tabela, linhas


def informacoes_dos_indicadores(indicadores):
    return [
        ("Alunos ativos", str(indicadores["alunos"])),
        ("Média da turma", formatar(indicadores["media"], NOTA)),
        ("Frequência média", formatar(indicadores["frequencia"], PERCENTUAL)),
        (
            "Regular · Em atenção · Em risco",
            f"{indicadores['regulares']} · {indicadores['atencao']} · {indicadores['risco']}",
        ),
    ]


def desempenho_da_disciplina(oferta):
    """Relatório do professor: os alunos de uma disciplina que ele leciona."""
    turma = oferta.turma
    tabela, linhas = tabela_da_oferta(oferta)
    grafico = distribuicao_de_notas(contar_por_faixa(linha["media"] for linha in linhas))
    return Relatorio(
        titulo=f"Desempenho em {oferta.disciplina.nome}",
        subtitulo=f"Turma {turma.codigo} · {turma.curso.nome} · semestre {turma.semestre}",
        nome_arquivo=nome_de_arquivo("desempenho", oferta.disciplina.codigo, turma.codigo, turma.semestre),
        informacoes=[
            ("Professor", professor_da(oferta)),
            ("Turma", f"{turma.codigo} · {turma.periodo}º período"),
            *informacoes_dos_indicadores(indicadores_da_turma(linhas)),
        ],
        tabelas=[tabela],
        graficos=[grafico] if grafico else [],
        observacoes=[OBSERVACAO_LIMITES, OBSERVACAO_NUMEROS],
        paisagem=True,
    )


def desempenho_da_turma(turma):
    """Relatório da coordenação: um resumo por aluno e uma tabela por disciplina da turma."""
    matriculas = list(
        Matricula.objects.filter(turma=turma, situacao=Matricula.Situacao.ATIVA)
        .select_related("aluno")
        .order_by("aluno__first_name", "aluno__last_name")
    )
    resumo = resumo_das_matriculas(matriculas)
    linhas = [{"matricula": matricula, **resumo[matricula.pk]} for matricula in matriculas]

    tabela_resumo = Tabela(
        titulo="Resumo por aluno",
        subtitulo="Média das disciplinas, frequência somando todas elas e a pior situação entre elas.",
        colunas=[
            Coluna("Aluno", largura=2.6),
            Coluna("RA", largura=1.2),
            Coluna("Média geral", NOTA, 1),
            Coluna("Frequência global", PERCENTUAL, 1.2),
            Coluna("Disciplinas em risco", INTEIRO, 1.2),
            Coluna("Situação", SITUACAO, 1.3),
        ],
        linhas=[
            [
                nome_de(linha["matricula"].aluno),
                linha["matricula"].aluno.matricula,
                linha["media"],
                linha["frequencia"],
                linha["disciplinas_em_risco"],
                linha["situacao"],
            ]
            for linha in linhas
        ],
        vazio="Nenhum aluno ativo nesta turma.",
    )

    ofertas = turma.ofertas.select_related("disciplina", "professor", "turma").order_by(
        "disciplina__nome"
    )
    return Relatorio(
        titulo=f"Desempenho da turma {turma.codigo}",
        subtitulo=f"{turma.curso.nome} · {turma.periodo}º período · semestre {turma.semestre}",
        nome_arquivo=nome_de_arquivo("turma", turma.codigo, turma.semestre),
        informacoes=[
            ("Disciplinas", str(len(ofertas))),
            *informacoes_dos_indicadores(indicadores_da_turma(linhas)),
        ],
        tabelas=[tabela_resumo, *(tabela_da_oferta(oferta)[0] for oferta in ofertas)],
        observacoes=[
            "Só entram os alunos com matrícula ativa.",
            OBSERVACAO_LIMITES,
            OBSERVACAO_NUMEROS,
        ],
        paisagem=True,
    )


# --- Alunos em risco de evasão (módulo preditivo) ---


def alunos_em_risco(riscos, filtros=""):
    """Lista do modelo preditivo. "riscos" já vem filtrado pelo RiscoFiltro (filtros.py)."""
    riscos = list(riscos)
    contagem = {nivel: 0 for nivel in RiscoEvasao.Nivel.values}
    for risco in riscos:
        contagem[risco.nivel] += 1
    calculado_em = max((risco.calculado_em for risco in riscos), default=None)

    tabela = Tabela(
        titulo="Alunos em risco",
        subtitulo="Do maior para o menor risco.",
        colunas=[
            Coluna("Aluno", largura=2.2),
            Coluna("RA", largura=1.1),
            Coluna("Turma", largura=0.9),
            Coluna("Probabilidade", PERCENTUAL, 1.1),
            Coluna("Nível", SITUACAO, 1.2),
            Coluna("Frequência", PERCENTUAL, 1.2),
            Coluna("Média", NOTA, 0.7),
            Coluna("Tendência", NOTA, 0.9),
            Coluna("Justif. pendentes", INTEIRO, 1),
            Coluna("Principais motivos", largura=4),
        ],
        linhas=[
            [
                nome_de(risco.matricula.aluno),
                risco.matricula.aluno.matricula,
                risco.matricula.turma.codigo,
                risco.probabilidade,
                risco.get_nivel_display(),
                risco.frequencia,
                risco.media,
                risco.tendencia,
                risco.justificativas_pendentes,
                "; ".join(risco.motivos),
            ]
            for risco in riscos
        ],
        vazio="Nenhum aluno encontrado. Confira os filtros ou recalcule o risco na tela Alunos em risco.",
    )
    return Relatorio(
        titulo="Alunos em risco de evasão",
        subtitulo="Probabilidade estimada pelo modelo preditivo (RandomForest, scikit-learn).",
        nome_arquivo=nome_de_arquivo("alunos-em-risco", timezone.localdate().isoformat()),
        informacoes=[
            ("Alunos no relatório", str(len(riscos))),
            ("Risco alto", str(contagem[RiscoEvasao.Nivel.ALTO])),
            ("Risco médio", str(contagem[RiscoEvasao.Nivel.MEDIO])),
            ("Risco baixo", str(contagem[RiscoEvasao.Nivel.BAIXO])),
            (
                "Calculado em",
                timezone.localtime(calculado_em).strftime("%d/%m/%Y %H:%M") if calculado_em else "—",
            ),
            ("Filtros", filtros or "Nenhum (todos os alunos calculados)"),
        ],
        tabelas=[tabela],
        observacoes=[
            f"Níveis: baixo abaixo de {LIMITE_MEDIO}%, médio de {LIMITE_MEDIO}% a {LIMITE_ALTO}% "
            f"e alto a partir de {LIMITE_ALTO}%.",
            "Tendência = última nota menos a primeira, na média das disciplinas (negativa: notas em queda).",
            "O modelo foi treinado com dados simulados. O resultado ajuda a decidir quem procurar "
            "primeiro, mas não é um diagnóstico.",
            OBSERVACAO_NUMEROS,
        ],
        paisagem=True,
    )


# --- Lista de alunos (só Excel) ---


def lista_de_alunos(matriculas, selo="", filtros=""):
    """Uma linha por matrícula. "matriculas" já vem filtrado pelo MatriculaFiltro (filtros.py).

    O selo (Regular, Em atenção, Em risco) é calculado, não fica no banco, então o filtro
    por selo é feito aqui, depois do cálculo, como na tela de alunos.
    """
    matriculas = list(
        matriculas.select_related("aluno", "turma__curso").order_by(
            "aluno__first_name", "aluno__last_name", "-turma__semestre"
        )
    )
    resumo = resumo_das_matriculas(matriculas)

    linhas = []
    for matricula in matriculas:
        dados = resumo[matricula.pk]
        ativa = matricula.situacao == Matricula.Situacao.ATIVA
        situacao = dados["situacao"] if ativa else None  # o selo só vale para quem está cursando
        if selo and situacao != selo:
            continue
        aluno = matricula.aluno
        linhas.append(
            [
                nome_de(aluno),
                aluno.matricula,
                aluno.email,
                "Sim" if aluno.is_active else "Não",
                matricula.turma.curso.nome,
                matricula.turma.codigo,
                matricula.turma.semestre,
                matricula.get_situacao_display(),
                dados["media"],
                dados["frequencia"],
                dados["disciplinas_em_risco"],
                situacao,
                matricula.coeficiente_rendimento,
                matricula.creditos_concluidos,
            ]
        )

    tabela = Tabela(
        titulo="Alunos",
        colunas=[
            Coluna("Aluno"),
            Coluna("RA"),
            Coluna("E-mail"),
            Coluna("Conta ativa"),
            Coluna("Curso"),
            Coluna("Turma"),
            Coluna("Semestre"),
            Coluna("Matrícula"),
            Coluna("Média", NOTA),
            Coluna("Frequência", PERCENTUAL),
            Coluna("Disciplinas em risco", INTEIRO),
            Coluna("Situação", SITUACAO),
            Coluna("Coeficiente", NOTA),
            Coluna("Créditos concluídos", INTEIRO),
        ],
        linhas=linhas,
        vazio="Nenhum aluno encontrado com esses filtros.",
    )
    return Relatorio(
        titulo="Lista de alunos",
        subtitulo="Uma linha por matrícula, com a situação acadêmica calculada.",
        nome_arquivo=nome_de_arquivo("alunos", timezone.localdate().isoformat()),
        informacoes=[
            ("Matrículas no relatório", str(len(linhas))),
            ("Filtros", " · ".join(parte for parte in (filtros, selo) if parte) or "Nenhum"),
        ],
        tabelas=[tabela],
        observacoes=[OBSERVACAO_LIMITES],
    )
