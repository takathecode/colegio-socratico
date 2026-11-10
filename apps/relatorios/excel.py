"""Grava um Relatorio (dados.py) como planilha Excel, com pandas e openpyxl.

Cada tabela do relatório vira uma aba: o pandas transforma as linhas em um DataFrame e o
to_excel grava a aba. Depois, o openpyxl (a biblioteca que o pandas usa por baixo para
arquivos .xlsx) acerta a aparência: cabeçalho em negrito, largura das colunas, filtro e
a primeira linha fixa.

Notas e percentuais são gravados como número, não como texto, para quem abrir a planilha
conseguir ordenar, filtrar e fazer contas. Dado que ainda não existe fica em branco.
A última aba, "Sobre o relatório", guarda o título, os filtros e a data de emissão.
"""

import re
from decimal import Decimal
from io import BytesIO

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .dados import NOTA, PERCENTUAL, Coluna, Tabela, formatar

ABA_SOBRE = "Sobre o relatório"
LARGURA_MAXIMA = 60  # colunas de texto longo (como os motivos do risco) não passam disso


def valor_da_celula(valor):
    """Decimal vira float, que o Excel entende como número."""
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def titulo_da_coluna(coluna):
    """Percentual vai como número (88.89), então o título avisa: "Frequência (%)"."""
    return f"{coluna.titulo} (%)" if coluna.tipo == PERCENTUAL else coluna.titulo


def nome_da_aba(titulo, usados):
    """O Excel aceita até 31 caracteres, sem []:*?/\\, e não repete nomes de abas."""
    base = re.sub(r"[\[\]:*?/\\]", "-", titulo)[:31]
    nome, numero = base, 2
    while nome.casefold() in usados:
        sufixo = f" ({numero})"
        nome = base[: 31 - len(sufixo)] + sufixo
        numero += 1
    usados.add(nome.casefold())
    return nome


def ajustar_aba(aba, tabela):
    """Aparência da aba: cabeçalho azul, primeira linha fixa, filtro e largura das colunas."""
    for celula in aba[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="1F4E8C")
    aba.freeze_panes = "A2"  # o cabeçalho continua visível ao rolar a planilha
    if tabela.linhas:
        aba.auto_filter.ref = aba.dimensions

    for indice, coluna in enumerate(tabela.colunas, start=1):
        letra = get_column_letter(indice)
        textos = [titulo_da_coluna(coluna), *(formatar(linha[indice - 1], coluna.tipo) for linha in tabela.linhas)]
        aba.column_dimensions[letra].width = min(max(len(t) for t in textos) + 2, LARGURA_MAXIMA)
        if coluna.tipo in (NOTA, PERCENTUAL):
            for celula in aba[letra][1:]:
                celula.number_format = "0.0#"  # 7 aparece como 7,0 e 6,75 como 6,75


def tabela_sobre(relatorio):
    linhas = [
        ["Relatório", relatorio.titulo],
        ["Descrição", relatorio.subtitulo],
        *([rotulo, valor] for rotulo, valor in relatorio.informacoes),
        ["Emitido em", f"{relatorio.emitido_em:%d/%m/%Y %H:%M}"],
        *(["Observação", observacao] for observacao in relatorio.observacoes),
    ]
    return Tabela(titulo=ABA_SOBRE, colunas=[Coluna("Campo"), Coluna("Valor")], linhas=linhas)


def gerar_excel(relatorio):
    """Devolve os bytes do arquivo .xlsx."""
    buffer = BytesIO()
    usados = {ABA_SOBRE.casefold()}  # reservado para a última aba
    with pd.ExcelWriter(buffer, engine="openpyxl") as planilha:
        for tabela in [*relatorio.tabelas, tabela_sobre(relatorio)]:
            nome = ABA_SOBRE if tabela.titulo == ABA_SOBRE else nome_da_aba(tabela.titulo, usados)
            quadro = pd.DataFrame(
                [[valor_da_celula(valor) for valor in linha] for linha in tabela.linhas],
                columns=[titulo_da_coluna(coluna) for coluna in tabela.colunas],
            )
            quadro.to_excel(planilha, sheet_name=nome, index=False)
            ajustar_aba(planilha.sheets[nome], tabela)
    return buffer.getvalue()
