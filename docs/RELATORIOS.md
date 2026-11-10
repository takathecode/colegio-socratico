# Relatórios em PDF e Excel

## A ideia em uma frase

Cada perfil baixa os dados que pode ver: o aluno, o próprio boletim; o professor, as
disciplinas que leciona; a coordenação, a instituição inteira. O PDF serve para imprimir e
apresentar, e o Excel serve para analisar.

## Os relatórios

| Relatório | Quem baixa | Onde fica o botão | PDF | Excel |
|---|---|---|---|---|
| Boletim do semestre | aluno (o próprio) | Notas e Boletim → "Baixar boletim (PDF)" | sim | não |
| Boletim de qualquer aluno | coordenação | Alunos → "Boletim" em cada linha | sim | não |
| Desempenho da disciplina | professor (só as dele) | Desempenho → "PDF" / "Excel" | sim | sim |
| Desempenho da turma | coordenação | Relatórios, ou a tela da turma | sim | sim |
| Alunos em risco de evasão | coordenação | Relatórios, ou Alunos em risco (com os filtros da tela) | sim | sim |
| Lista de alunos | coordenação | Relatórios, ou Alunos (com os filtros da tela) | não | sim |

O enunciado pede "relatórios gerados para coordenadores" no módulo preditivo: é o relatório
"Alunos em risco de evasão", com a probabilidade, o nível e os motivos de cada aluno.

## Como funciona

```
tela (botão)  →  views.py  →  dados.py  →  pdf.py   (reportlab)  →  arquivo .pdf
                 permissão     números  ↘  excel.py (pandas)     →  arquivo .xlsx
```

| Arquivo | Papel |
|---|---|
| `apps/relatorios/dados.py` | Monta o conteúdo de cada relatório (título, quadro de informações, tabelas, gráficos). Os números vêm de `apps/academico/calculos.py`, as mesmas funções das telas. |
| `apps/relatorios/pdf.py` | Desenha o relatório em PDF com o reportlab. |
| `apps/relatorios/excel.py` | Grava o relatório em Excel com o pandas (uma aba por tabela). |
| `apps/relatorios/filtros.py` | Filtros com o django-filter (turma, nível de risco, situação da matrícula, busca). |
| `apps/relatorios/views.py` | Confere a permissão e devolve o arquivo para download. |

**Por que separar `dados.py` de `pdf.py` e `excel.py`?** O conteúdo é montado uma vez só.
Assim, o PDF e o Excel de um mesmo relatório nunca mostram números diferentes, e um formato
novo (CSV, por exemplo) seria só mais um arquivo que desenha o mesmo conteúdo.

### PDF (reportlab)

- Usamos o **platypus**, a parte do reportlab que trabalha com blocos: título, quadro,
  tabela e imagem. O reportlab distribui os blocos pelas páginas sozinho. Uma tabela longa
  continua na página seguinte, com o cabeçalho repetido.
- Toda página tem o cabeçalho com a logo "S" e o nome Instituto Socrático, e o rodapé com a
  data de emissão e o número da página (`desenhar_moldura`).
- Os selos têm as mesmas cores das telas: verde "Regular", âmbar "Em atenção" e vermelho
  "Em risco".
- O boletim e o relatório do professor trazem o gráfico do matplotlib (etapa 7), que vira uma
  imagem dentro do PDF.
- Tabelas largas (turma, disciplina e risco) usam a folha deitada (paisagem).
- Os números aparecem com uma casa, **cortando** a segunda em vez de arredondar: 74,96% sai
  como 74,9%. Arredondado, sairia 75%, que pareceria estar no limite mínimo, e não abaixo dele.
  A regra é a mesma dos motivos do risco de evasão (etapa 8).

### Excel (pandas + openpyxl)

- Cada tabela vira uma **aba**. O relatório da turma tem a aba "Resumo por aluno" e uma aba
  por disciplina. A última aba, "Sobre o relatório", guarda o título, os filtros e a data.
- Notas e percentuais são gravados como **número**, e não como texto: quem abre a planilha
  pode ordenar, filtrar e fazer contas. As colunas de percentual levam "(%)" no título.
  O Excel recebe o valor exato, com duas casas.
- Nota ainda não lançada fica **em branco**, porque "sem nota" não é nota zero.
- O cabeçalho fica fixo ao rolar a planilha e já vem com filtro.
- O nome da aba respeita o limite do Excel: no máximo 31 caracteres, sem `[]:*?/\` e sem
  nomes repetidos.

### Filtros (django-filter)

O `RiscoFiltro` lê `?turma=3&nivel=ALTO&busca=bia` da URL, valida cada valor e filtra a
consulta. Um valor inválido (como `?turma=abc`) é ignorado, e a página não quebra.
A tela **Alunos em risco** usa o mesmo filtro, então o botão "PDF" da tela gera um
relatório com exatamente os alunos da lista.

O selo (Regular, Em atenção, Em risco) é calculado e não fica salvo no banco. Por isso, na
lista de alunos, o filtro por selo é feito depois do cálculo, como na tela de alunos.

## Permissões

| Pedido | Resultado |
|---|---|
| Aluno baixa o próprio boletim | arquivo. A URL não tem número de matrícula, então não há como pedir o boletim de outra pessoa. |
| Professor baixa uma disciplina dele | arquivo |
| Professor pede uma disciplina de outro professor | 404, como no resto da área do professor |
| Aluno ou professor abre um relatório da coordenação | 403 (página amigável) |
| Visitante sem login | vai para a tela de login |
| `?formato=` diferente de `pdf` ou `xlsx` | 404 |

## Por que não usamos o Celery aqui

Com o volume de uma escola, cada arquivo fica pronto em menos de um segundo (o relatório de
risco, com 40 alunos, leva cerca de 0,6 s com o banco no Supabase). Gerar na hora é mais simples
de explicar e de usar. Com milhares de alunos, o caminho seria gerar o arquivo em uma tarefa do
Celery e avisar pelo sino quando ficasse pronto.

## Para testar

```powershell
python manage.py test apps.relatorios
```

Os testes conferem as permissões dos três perfis, se o PDF é um PDF de verdade (começa com
`%PDF`) e se o Excel abre com o `pandas.read_excel` com as abas, as colunas e os números certos.
