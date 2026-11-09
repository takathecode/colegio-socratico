"""Gráficos do sistema, desenhados no servidor com matplotlib.

Cada função recebe dados já calculados, desenha o gráfico e devolve um dicionário:
- "png": a imagem em base64, que o template coloca em <img src="data:image/png;base64,...">;
- "descricao": um texto com os números do gráfico, usado no "alt" da imagem para quem usa
  leitor de tela.
Quando não há dados, a função devolve None e a tela mostra o estado vazio.

Usamos matplotlib.figure.Figure em vez de pyplot: cada gráfico tem a sua própria figura,
e o servidor não guarda nada na memória entre um acesso e outro.
"""

import base64
import textwrap
from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # desenha só em memória, sem abrir janela (o servidor não tem tela)

from matplotlib.figure import Figure  # noqa: E402 (precisa vir depois do use("Agg"))
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from apps.academico.calculos import FREQUENCIA_MINIMA, MEDIA_MINIMA  # noqa: E402

from .dados import ABAIXO_DE_6, ENTRE_6_E_7, SETE_OU_MAIS  # noqa: E402

# --- Cores (as mesmas do Tailwind nas telas) ---
TEXTO = "#0B2545"  # azul-marinho da marca
TEXTO_SECUNDARIO = "#64748B"  # slate-500
GRADE = "#E5E9F0"  # borda dos cards
EIXO = "#CBD5E1"  # slate-300
AZUL = "#1F4E8C"  # botão primário
REFERENCIA = "#64748B"  # linhas de mínimo (média 7, frequência 75%)

# Cores das faixas de média: as mesmas do anel "Situação das disciplinas" do aluno.
# O azul é um pouco mais claro que o da marca para separar bem do vermelho e do âmbar,
# inclusive para daltônicos (paleta testada com um validador de contraste e daltonismo).
COR_DO_GRUPO = {ABAIXO_DE_6: "#C62828", ENTRE_6_E_7: "#D97706", SETE_OU_MAIS: "#2A78D6"}

# Uma cor por turma, sempre na mesma ordem (a 1ª turma é sempre azul, a 2ª laranja...).
# Ordem testada para daltonismo: cores vizinhas nunca se confundem.
CORES_DAS_TURMAS = [
    "#2A78D6",  # azul
    "#EB6834",  # laranja
    "#1BAF7A",  # verde-água
    "#EDA100",  # amarelo
    "#E87BA4",  # rosa
    "#008300",  # verde
    "#6250D6",  # violeta
    "#E34948",  # vermelho
]

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# --- Funções de apoio ---


def numero(valor, casas=1):
    """Número no formato brasileiro: 7.5 vira "7,5"."""
    return f"{valor:.{casas}f}".replace(".", ",")


def nova_figura(largura=7, altura=3):
    """Cria a figura com o visual do sistema: fundo branco, grade clara e sem moldura."""
    figura = Figure(figsize=(largura, altura))
    eixos = figura.add_subplot()
    for lado in ("top", "right", "left"):
        eixos.spines[lado].set_visible(False)
    eixos.spines["bottom"].set_color(EIXO)
    eixos.tick_params(colors=TEXTO_SECUNDARIO, labelsize=9, length=0)
    eixos.tick_params(axis="x", pad=6)
    eixos.yaxis.grid(True, color=GRADE, linewidth=1)  # só linhas horizontais, bem claras
    eixos.set_axisbelow(True)  # a grade fica atrás das barras
    return figura, eixos


def legenda_embaixo(eixos, itens, colunas, distancia=0.2):
    """Legenda sem moldura, centralizada abaixo do gráfico (distancia: quanto abaixo)."""
    eixos.legend(
        handles=itens,
        loc="upper center",
        bbox_to_anchor=(0.5, -distancia),
        ncol=colunas,
        frameon=False,
        fontsize=9,
        labelcolor=TEXTO_SECUNDARIO,
        handlelength=1.6,
    )


def para_base64(figura):
    """Salva a figura como PNG na memória e devolve o texto em base64."""
    buffer = BytesIO()
    # dpi 144 deixa a imagem nítida em telas de alta resolução (celulares e notebooks).
    figura.savefig(buffer, format="png", dpi=144, bbox_inches="tight", facecolor="white")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


# --- Os três gráficos ---


def notas_por_disciplina(linhas):
    """Aluno: média de cada disciplina em barras, com a linha da média mínima (7,0).

    Recebe as linhas do boletim (resumo_por_disciplina). Disciplina ainda sem nota não
    ganha barra, porque "sem nota" não é o mesmo que nota zero.
    """
    com_nota = [linha for linha in linhas if linha["media"] is not None]
    if not com_nota:
        return None

    nomes = [linha["oferta"].disciplina.nome for linha in com_nota]
    medias = [float(linha["media"]) for linha in com_nota]

    figura, eixos = nova_figura()
    posicoes = range(len(medias))
    barras = eixos.bar(posicoes, medias, width=0.4, color=AZUL)
    textos = eixos.bar_label(
        barras, labels=[numero(m) for m in medias], padding=3, fontsize=9, color=TEXTO
    )
    for texto in textos:
        # Fundo branco atrás do número, para a linha tracejada não passar por cima dele.
        texto.set_bbox({"facecolor": "white", "edgecolor": "none", "pad": 1})
    eixos.axhline(float(MEDIA_MINIMA), color=REFERENCIA, linestyle="--", linewidth=1)

    # Nomes longos são encurtados e quebrados em linhas curtas, para não se sobreporem.
    rotulos = [textwrap.fill(textwrap.shorten(nome, 26, placeholder="…"), 13) for nome in nomes]
    eixos.set_xticks(list(posicoes), rotulos, fontsize=8)
    eixos.set_ylim(0, 10.9)  # um pouco acima de 10, para caber o número em cima da barra
    eixos.set_yticks(range(0, 11, 2))

    legenda_embaixo(
        eixos,
        [
            Patch(color=AZUL, label="Sua média na disciplina"),
            Line2D([], [], color=REFERENCIA, linestyle="--", label=f"Média mínima ({numero(MEDIA_MINIMA)})"),
        ],
        colunas=2,
    )

    descricao = "Gráfico de barras com a sua média em cada disciplina: " + "; ".join(
        f"{nome}, {numero(media)}" for nome, media in zip(nomes, medias)
    )
    return {"png": para_base64(figura), "descricao": descricao + "."}


def distribuicao_de_notas(faixas):
    """Professor: quantos alunos da turma têm a média em cada faixa.

    Recebe a lista de contar_por_faixa() (apps/analytics/dados.py). As barras abaixo de 6
    ficam vermelhas, entre 6 e 7 âmbar e de 7 para cima azuis, como os selos de situação.
    """
    if not any(faixa["quantidade"] for faixa in faixas):
        return None

    rotulos = [faixa["rotulo"] for faixa in faixas]
    quantidades = [faixa["quantidade"] for faixa in faixas]

    figura, eixos = nova_figura()
    barras = eixos.bar(
        rotulos,
        quantidades,
        width=0.55,
        color=[COR_DO_GRUPO[faixa["grupo"]] for faixa in faixas],
    )
    # Mostra o número só nas barras que existem (faixa vazia fica sem o "0" em cima).
    eixos.bar_label(
        barras,
        labels=[str(q) if q else "" for q in quantidades],
        padding=3,
        fontsize=9,
        color=TEXTO,
    )
    eixos.yaxis.set_major_locator(MaxNLocator(integer=True))  # não existe meio aluno
    eixos.set_ylim(0, max(quantidades) * 1.15)
    eixos.set_xlabel("Faixa de média", fontsize=9, color=TEXTO_SECUNDARIO, labelpad=8)
    eixos.set_ylabel("Alunos", fontsize=9, color=TEXTO_SECUNDARIO)

    legenda_embaixo(
        eixos,
        [Patch(color=cor, label=f"Média {grupo.lower()}") for grupo, cor in COR_DO_GRUPO.items()],
        colunas=3,
    )

    descricao = "Gráfico de barras com quantos alunos têm a média em cada faixa: " + "; ".join(
        f"{faixa['rotulo']}, {faixa['quantidade']} aluno{'s' if faixa['quantidade'] != 1 else ''}"
        for faixa in faixas
    )
    return {"png": para_base64(figura), "descricao": descricao + "."}


def evolucao_da_frequencia(series):
    """Coordenação: frequência de cada turma, mês a mês, com a linha do mínimo (75%).

    Recebe a lista de frequencia_mensal_por_turma() (apps/analytics/dados.py).
    Cada turma tem a sua cor fixa. Com mais turmas do que cores, o gráfico ficaria
    confuso: nesse caso a tabela de turmas da tela é o lugar para comparar.
    """
    series = [serie for serie in series if serie["meses"]][: len(CORES_DAS_TURMAS)]
    if not series:
        return None

    # Todos os meses que aparecem em alguma turma, em ordem, viram o eixo horizontal.
    meses = sorted({mes for serie in series for mes, _ in serie["meses"]})
    posicao = {mes: indice for indice, mes in enumerate(meses)}

    figura, eixos = nova_figura()
    itens_da_legenda = []
    menor = 100.0
    for serie, cor in zip(series, CORES_DAS_TURMAS):
        x = [posicao[mes] for mes, _ in serie["meses"]]
        y = [float(valor) for _, valor in serie["meses"]]
        menor = min(menor, *y)
        eixos.plot(
            x,
            y,
            color=cor,
            linewidth=2,
            marker="o",
            markersize=7,
            markeredgecolor="white",  # anel branco: o ponto aparece mesmo cruzando outra linha
            markeredgewidth=1.5,
            solid_capstyle="round",
            solid_joinstyle="round",
        )
        itens_da_legenda.append(
            Line2D([], [], color=cor, linewidth=2, marker="o", markersize=6, label=serie["nome"])
        )

    eixos.axhline(float(FREQUENCIA_MINIMA), color=REFERENCIA, linestyle="--", linewidth=1)
    itens_da_legenda.append(
        Line2D(
            [],
            [],
            color=REFERENCIA,
            linestyle="--",
            label=f"Mínimo exigido ({int(FREQUENCIA_MINIMA)}%)",
        )
    )

    eixos.set_xticks(range(len(meses)), [f"{MESES[mes.month - 1]}/{mes:%y}" for mes in meses])
    # O eixo começa um pouco abaixo do menor valor (e nunca acima de 70%, para o 75% aparecer).
    piso = max(0, min(70, int(menor // 10) * 10 - 10))
    eixos.set_ylim(piso, 101)
    eixos.yaxis.set_major_formatter(FuncFormatter(lambda valor, _: f"{valor:.0f}%"))
    if len(meses) == 1:
        eixos.set_xlim(-0.5, 0.5)  # com um mês só, o ponto fica no meio

    legenda_embaixo(
        eixos, itens_da_legenda, colunas=min(len(itens_da_legenda), 5), distancia=0.12
    )

    partes = []
    for serie in series:
        valores = ", ".join(
            f"{MESES[mes.month - 1]} {numero(valor, 0)}%" for mes, valor in serie["meses"]
        )
        partes.append(f"{serie['nome']}: {valores}")
    descricao = "Gráfico de linhas com a frequência de cada turma por mês. " + "; ".join(partes)
    return {"png": para_base64(figura), "descricao": descricao + "."}
