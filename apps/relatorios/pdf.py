"""Desenha um Relatorio (dados.py) em PDF com o reportlab.

Usamos a parte "platypus" do reportlab: em vez de calcular a posição de cada linha na
folha, montamos uma lista de blocos (título, quadro, tabela, imagem...) e o reportlab
distribui os blocos pelas páginas sozinho. Tabela longa continua na página seguinte,
com o cabeçalho repetido.

O cabeçalho com a logo e o rodapé com a data e o número da página são desenhados em
cada página pela função desenhar_moldura.

A fonte é a Helvetica, que já vem no reportlab e aceita os acentos do português.
"""

import base64
from functools import partial
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .dados import SITUACAO, TEXTO, formatar

# --- Cores (as mesmas das telas) ---
AZUL_MARINHO = colors.HexColor("#0B2545")  # marca
AZUL = colors.HexColor("#1F4E8C")  # botão primário
BORDA = colors.HexColor("#E5E9F0")  # borda dos cards
FUNDO = colors.HexColor("#F5F7FA")  # fundo da página
CINZA = colors.HexColor("#64748B")  # texto secundário (slate-500)

# Texto e fundo de cada selo, iguais aos de templates/componentes/selo.html.
VERDE = ("#166534", "#F0FDF4")
AMBAR = ("#78350F", "#FFFBEB")
VERMELHO = ("#991B1B", "#FEF2F2")
CORES_DO_SELO = {
    "Regular": VERDE,
    "Risco baixo": VERDE,
    "Em atenção": AMBAR,
    "Risco médio": AMBAR,
    "Em risco": VERMELHO,
    "Risco alto": VERMELHO,
}

# --- Estilos de texto ---
ESTILOS = {
    "titulo": ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=AZUL_MARINHO),
    "subtitulo": ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=10, leading=14, textColor=CINZA),
    # keepWithNext: o título da seção nunca fica sozinho no pé da página.
    "secao": ParagraphStyle(
        "secao", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=AZUL_MARINHO, keepWithNext=1
    ),
    "secao_detalhe": ParagraphStyle(
        "secao_detalhe", fontName="Helvetica", fontSize=8.5, leading=11, textColor=CINZA, keepWithNext=1
    ),
    "rotulo": ParagraphStyle("rotulo", fontName="Helvetica", fontSize=7.5, leading=9, textColor=CINZA),
    "valor": ParagraphStyle("valor", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=AZUL_MARINHO),
    "cabecalho": ParagraphStyle("cabecalho", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=CINZA),
    "celula": ParagraphStyle("celula", fontName="Helvetica", fontSize=8.5, leading=10.5),
    "observacao": ParagraphStyle("observacao", fontName="Helvetica", fontSize=8, leading=11, textColor=CINZA),
    "vazio": ParagraphStyle("vazio", fontName="Helvetica", fontSize=9, leading=12, textColor=CINZA),
}
# Números e selos ficam centralizados na coluna; textos, à esquerda.
ESTILOS["cabecalho_centro"] = ParagraphStyle("cabecalho_centro", ESTILOS["cabecalho"], alignment=TA_CENTER)
ESTILOS["celula_centro"] = ParagraphStyle("celula_centro", ESTILOS["celula"], alignment=TA_CENTER)
# Um estilo por selo, como "selo_Em risco": negrito, na cor do texto do selo.
for _selo, (_cor_do_texto, _cor_do_fundo) in CORES_DO_SELO.items():
    ESTILOS[f"selo_{_selo}"] = ParagraphStyle(
        f"selo_{_selo}", ESTILOS["celula_centro"], fontName="Helvetica-Bold", textColor=colors.HexColor(_cor_do_texto)
    )

MARGEM = 1.6 * cm


def texto(valor, estilo):
    """Parágrafo com o texto protegido: um "&" ou "<" no nome não quebra o PDF."""
    return Paragraph(escape(str(valor)), ESTILOS[estilo])


# --- Partes do documento ---


def desenhar_moldura(canvas, documento, relatorio):
    """Cabeçalho (logo "S" e nome) e rodapé (data de emissão e página), em toda página."""
    largura, altura = documento.pagesize
    esquerda, direita = documento.leftMargin, largura - documento.rightMargin
    topo = altura - 1.1 * cm
    lado = 0.8 * cm  # tamanho do quadrado da logo

    canvas.saveState()
    canvas.setFillColor(AZUL_MARINHO)
    canvas.roundRect(esquerda, topo - lado, lado, lado, 3, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawCentredString(esquerda + lado / 2, topo - lado + 0.24 * cm, "S")

    canvas.setFillColor(AZUL_MARINHO)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(esquerda + lado + 0.25 * cm, topo - 0.36 * cm, "Instituto Socrático")
    canvas.setFillColor(CINZA)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(esquerda + lado + 0.25 * cm, topo - 0.72 * cm, "Sistema de Gestão Acadêmica")
    canvas.drawRightString(direita, topo - 0.36 * cm, relatorio.titulo)

    canvas.setStrokeColor(BORDA)
    canvas.setLineWidth(1)
    canvas.line(esquerda, topo - lado - 0.25 * cm, direita, topo - lado - 0.25 * cm)

    canvas.drawString(esquerda, 1 * cm, f"Emitido em {relatorio.emitido_em:%d/%m/%Y às %H:%M}")
    canvas.drawRightString(direita, 1 * cm, f"Página {documento.page}")
    canvas.restoreState()


def quadro_de_informacoes(informacoes, largura, colunas=4):
    """Quadro cinza do topo: cada informação tem um rótulo pequeno e o valor em negrito."""
    celulas = [[texto(rotulo, "rotulo"), texto(valor, "valor")] for rotulo, valor in informacoes]
    celulas += [""] * (-len(celulas) % colunas)  # completa a última linha
    linhas = [celulas[i : i + colunas] for i in range(0, len(celulas), colunas)]
    quadro = Table(linhas, colWidths=[largura / colunas] * colunas)
    quadro.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), FUNDO),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return quadro


def imagem_do_grafico(grafico, largura_disponivel):
    """O gráfico do matplotlib (PNG em base64) vira uma imagem no PDF, sem distorcer."""
    png = base64.b64decode(grafico["png"])
    largura_original, altura_original = ImageReader(BytesIO(png)).getSize()
    largura = min(largura_disponivel, 15 * cm)
    return Image(BytesIO(png), width=largura, height=largura * altura_original / largura_original)


def tabela_do_pdf(tabela, largura):
    """Tabela com o cabeçalho repetido em cada página e os selos coloridos."""
    soma = sum(coluna.largura for coluna in tabela.colunas)
    larguras = [largura * coluna.largura / soma for coluna in tabela.colunas]

    cabecalho = [
        texto(coluna.titulo, "cabecalho" if coluna.tipo == TEXTO else "cabecalho_centro")
        for coluna in tabela.colunas
    ]
    linhas = [cabecalho]
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), FUNDO),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for numero_da_linha, valores in enumerate(tabela.linhas, start=1):
        celulas = []
        for numero_da_coluna, (coluna, valor) in enumerate(zip(tabela.colunas, valores)):
            conteudo = formatar(valor, coluna.tipo)
            if coluna.tipo == SITUACAO and valor in CORES_DO_SELO:
                # Selo: texto em negrito na cor do selo e a célula com o fundo claro da mesma cor.
                celulas.append(Paragraph(escape(conteudo), ESTILOS[f"selo_{valor}"]))
                posicao = (numero_da_coluna, numero_da_linha)
                estilo.append(("BACKGROUND", posicao, posicao, colors.HexColor(CORES_DO_SELO[valor][1])))
            else:
                celulas.append(texto(conteudo, "celula" if coluna.tipo == TEXTO else "celula_centro"))
        linhas.append(celulas)

    resultado = Table(linhas, colWidths=larguras, repeatRows=1)
    resultado.setStyle(TableStyle(estilo))
    return resultado


def secao(tabela, largura):
    blocos = [texto(tabela.titulo, "secao")]
    if tabela.subtitulo:
        blocos.append(texto(tabela.subtitulo, "secao_detalhe"))
    blocos.append(Spacer(1, 6))
    if tabela.linhas:
        blocos.append(tabela_do_pdf(tabela, largura))
    else:
        blocos.append(texto(tabela.vazio, "vazio"))
    blocos.append(Spacer(1, 16))
    return blocos


# --- Função principal ---


def gerar_pdf(relatorio):
    """Devolve os bytes do arquivo PDF."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4) if relatorio.paisagem else A4,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=2.6 * cm,  # espaço para o cabeçalho com a logo
        bottomMargin=1.8 * cm,  # espaço para o rodapé
        title=relatorio.titulo,
        subject=relatorio.subtitulo,
        author="Instituto Socrático",
        creator="Instituto Socrático · Sistema de Gestão Acadêmica",
    )
    largura = documento.width  # largura útil da folha, já sem as margens

    blocos = [texto(relatorio.titulo, "titulo"), texto(relatorio.subtitulo, "subtitulo"), Spacer(1, 12)]
    if relatorio.informacoes:
        blocos += [quadro_de_informacoes(relatorio.informacoes, largura), Spacer(1, 16)]
    for tabela in relatorio.tabelas:
        blocos += secao(tabela, largura)
    for grafico in relatorio.graficos:
        blocos += [imagem_do_grafico(grafico, largura), Spacer(1, 12)]
    for observacao in relatorio.observacoes:
        blocos.append(texto(f"• {observacao}", "observacao"))

    moldura = partial(desenhar_moldura, relatorio=relatorio)
    documento.build(blocos, onFirstPage=moldura, onLaterPages=moldura)
    return buffer.getvalue()
