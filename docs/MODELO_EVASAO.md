# Módulo preditivo de evasão — explicação para a apresentação

Código: `apps/analytics/evasao.py`. Tela: Coordenação → **Alunos em risco**.

## A ideia em uma frase

O sistema olha quatro números de cada aluno e estima a **chance de ele desistir do curso**,
para a coordenação conversar com ele **antes** que isso aconteça.

## O que o modelo olha (as 4 variáveis)

| Variável | De onde vem | Por que importa |
|---|---|---|
| Frequência | presenças e faltas de todas as disciplinas | quem para de ir às aulas costuma estar perto de desistir |
| Média | média das médias das disciplinas | notas baixas desanimam e levam à reprovação |
| Tendência das notas | última nota menos a primeira, em cada disciplina | notas caindo mostram que algo mudou na vida do aluno |
| Justificativas pendentes | faltas justificadas que o professor ainda não avaliou | sinal de problemas fora da escola (saúde, trabalho) |

Média e frequência são as mesmas da lista de alunos (`apps/academico/calculos.py`),
então todas as telas mostram os mesmos números.

## Como o modelo aprendeu

1. **Dados simulados.** A escola não tem um histórico real de quem desistiu, então o comando
   `treinar_modelo` cria **2.000 alunos fictícios**. Uma regra escrita por nós, com um pouco de
   sorteio, decide quem "evadiu": quanto menor a frequência e a média, maior a chance. O sorteio
   cria exceções, como na vida real.
2. **Random Forest ("floresta aleatória").** São **200 árvores de decisão**. Cada árvore é uma
   sequência de perguntas do tipo "a frequência é menor que 72%?" e "a média é menor que 5,5?".
   Cada árvore aprende com uma parte diferente dos dados e dá o seu voto. A probabilidade final é
   a média dos votos: se 180 de 200 árvores dizem "evade", a chance é de 90%.
3. **Prova.** Antes do treino, separamos **20%** dos alunos fictícios. O modelo nunca vê esses
   alunos durante o treino; depois, tenta adivinhar quem deles evadiu.

O modelo **não conhece a regra** que usamos para criar os dados: ele descobre o padrão sozinho
olhando os exemplos. Com dados reais da escola seria igual, só trocando a origem dos dados.

## Os números do treino (saída do `treinar_modelo`)

- Acurácia na prova: **81%**. Chutando "ninguém evade", acertaríamos só **66%**.
- Peso de cada variável na decisão: frequência **50%**, média **35%**, tendência **13,5%**,
  justificativas pendentes **1,6%**.

Os números saem sempre iguais porque o sorteio usa uma semente fixa (`SEMENTE = 42`).

## O que a tela mostra

- **Probabilidade** de evasão, de 0% a 100%.
- **Nível:** baixo (abaixo de 30%), médio (de 30% a 60%) e alto (60% ou mais).
- **Principais motivos**, em frases como "Frequência de 61,4%, abaixo do mínimo de 75%". As frases
  usam os mesmos limites do selo de situação (75% de frequência, médias 6 e 7).
- Alunos sem nenhuma nota ou chamada ficam de fora ("Sem dados suficientes"): sem dados, o modelo
  estaria só chutando.

## Quando o risco é recalculado

- `python manage.py treinar_modelo`: treina de novo e recalcula todos os alunos.
- `python manage.py calcular_riscos`: recalcula com o modelo que já existe.
- Botão **Recalcular agora**, na tela da coordenação.
- A rotina diária do Celery roda o mesmo cálculo todo dia às 6h e, em seguida, gera os alertas
  (veja `docs/ALERTAS.md`).

O resultado fica salvo na tabela `RiscoEvasao` (um registro por matrícula ativa), com os números
usados no cálculo. O arquivo do modelo fica em `ml/modelo_evasao.joblib`. Ele fica fora do Git,
porque qualquer computador pode gerá-lo de novo com o comando.

## Perguntas que o professor pode fazer

- **"Por que dados simulados?"** Não temos um histórico real de evasão. O enunciado permite dados
  simulados, e o código já está pronto para dados reais.
- **"Por que Random Forest e não uma regra com `if`?"** A regra precisaria de limites escolhidos
  à mão. O modelo aprende os limites e as combinações (frequência um pouco baixa **e** notas
  caindo) a partir dos exemplos, e devolve uma probabilidade, não só "sim" ou "não".
- **"O modelo pode errar?"** Pode: acerta cerca de 8 em cada 10. Por isso a tela trata o resultado
  como um sinal para conversar com o aluno, não como uma sentença.
- **"Por que os motivos não vêm do modelo?"** A Random Forest não explica cada decisão de um
  jeito simples. As frases são montadas a partir dos números do aluno, com os mesmos limites que
  o aluno e o professor já conhecem.
