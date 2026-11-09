"""Módulo preditivo de evasão.

Como funciona, em três passos:

1. Treino (comando treinar_modelo): como a escola não tem um histórico real de alunos que
   desistiram, geramos alunos fictícios. Uma regra escrita por nós, com um pouco de sorteio,
   decide quais deles "evadiram". O RandomForest não conhece essa regra: ele aprende a
   reconhecer o padrão olhando os exemplos, como aconteceria com dados reais.
2. Previsão (comando calcular_riscos e botão "Recalcular agora"): para cada aluno ativo,
   medimos as quatro variáveis abaixo e o modelo devolve a probabilidade de evasão.
3. Explicação: a probabilidade vira um nível (baixo, médio, alto), e os motivos são frases
   montadas a partir dos números do aluno, usando os mesmos limites do selo de situação.

As quatro variáveis (features):
- frequencia: frequência global do aluno, em %;
- media: média das médias das disciplinas;
- tendencia: quanto as notas subiram ou caíram da primeira para a última avaliação
  (média entre as disciplinas; negativo = notas em queda);
- justificativas_pendentes: justificativas de falta que ainda esperam o professor.
"""

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from apps.academico.calculos import (
    DUAS_CASAS,
    FREQUENCIA_ATENCAO,
    FREQUENCIA_MINIMA,
    MEDIA_MINIMA,
    MEDIA_RISCO,
    calcular_media,
    resumo_das_matriculas,
)
from apps.academico.models import Justificativa, Matricula, Nota

from .models import RiscoEvasao

VARIAVEIS = ["frequencia", "media", "tendencia", "justificativas_pendentes"]

# Faixas de probabilidade (%) de cada nível: abaixo de 30 é baixo, de 30 a 60 é médio.
LIMITE_MEDIO = 30
LIMITE_ALTO = 60

# Notas que caem pelo menos isto (em pontos) contam como motivo "notas em queda".
QUEDA_RELEVANTE = Decimal("-0.5")

SEMENTE = 42  # semente fixa: o treino dá sempre o mesmo resultado


class ModeloNaoTreinado(Exception):
    """O arquivo do modelo ainda não existe: é preciso rodar python manage.py treinar_modelo."""


# --- 1. Treino ---


def gerar_dados_simulados(quantidade=2000, semente=SEMENTE):
    """Cria alunos fictícios e decide quem evadiu.

    A regra escondida: cada ponto de frequência abaixo de 80%, cada ponto de média abaixo
    de 6,5, notas em queda e justificativas pendentes aumentam a chance de evadir. A chance
    passa pela função logística (que transforma qualquer número em um valor entre 0 e 1) e
    um sorteio decide o resultado. Assim existem exceções, como na vida real: alguns alunos
    com frequência baixa continuam, e alguns com boas notas desistem.
    """
    sorteio = np.random.default_rng(semente)
    dados = pd.DataFrame(
        {
            "frequencia": np.clip(sorteio.normal(82, 12, quantidade), 30, 100),
            "media": np.clip(sorteio.normal(6.8, 1.6, quantidade), 0, 10),
            "tendencia": np.clip(sorteio.normal(0, 1.2, quantidade), -5, 5),
            "justificativas_pendentes": np.clip(sorteio.poisson(0.6, quantidade), 0, 6),
        }
    )
    pontos = (
        -1.0
        + 0.15 * (80 - dados["frequencia"])
        + 0.9 * (6.5 - dados["media"])
        - 0.6 * dados["tendencia"]
        + 0.4 * dados["justificativas_pendentes"]
    )
    chance = 1 / (1 + np.exp(-pontos))
    dados["evadiu"] = (sorteio.random(quantidade) < chance).astype(int)
    return dados


def treinar(quantidade=2000, arvores=200):
    """Treina o RandomForest com os dados simulados e salva o arquivo do modelo.

    Separa 20% dos alunos fictícios para a prova: o modelo é treinado com os outros 80% e
    depois tenta acertar quem evadiu entre alunos que ele nunca viu.
    Retorna um dicionário com os números do treino, que o comando mostra no terminal.
    """
    dados = gerar_dados_simulados(quantidade)
    x_treino, x_teste, y_treino, y_teste = train_test_split(
        dados[VARIAVEIS],
        dados["evadiu"],
        test_size=0.2,
        random_state=SEMENTE,
        stratify=dados["evadiu"],  # mantém a mesma proporção de evadidos nas duas partes
    )
    modelo = RandomForestClassifier(
        n_estimators=arvores,  # quantas árvores de decisão "votam"
        max_depth=6,  # árvores rasas generalizam melhor e não decoram os exemplos
        min_samples_leaf=10,  # cada resposta final se apoia em pelo menos 10 alunos
        random_state=SEMENTE,
    )
    modelo.fit(x_treino, y_treino)

    resultado = {
        "alunos_simulados": quantidade,
        "taxa_evasao": float(dados["evadiu"].mean()),
        "acuracia": float(modelo.score(x_teste, y_teste)),
        # Acurácia de quem "chuta" sempre que ninguém evade: o modelo precisa ser melhor que isso.
        "acuracia_chute": float(1 - y_teste.mean()),
        "importancias": dict(
            zip(VARIAVEIS, (float(valor) for valor in modelo.feature_importances_))
        ),
        "treinado_em": datetime.now().isoformat(timespec="seconds"),
    }

    caminho = settings.MODELO_EVASAO
    caminho.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": modelo, "variaveis": VARIAVEIS, **resultado}, caminho)
    return resultado


def carregar_modelo():
    """Lê o modelo salvo pelo treino. O arquivo é gerado por nós, nunca enviado por usuários."""
    caminho = settings.MODELO_EVASAO
    if not caminho.exists():
        raise ModeloNaoTreinado(
            "O modelo de evasão ainda não foi treinado. Rode: python manage.py treinar_modelo"
        )
    return joblib.load(caminho)["modelo"]


def modelo_treinado():
    return settings.MODELO_EVASAO.exists()


# --- 2. Variáveis dos alunos reais ---


def calcular_tendencias(ids):
    """Tendência das notas de cada matrícula: última nota menos a primeira, por disciplina.

    Disciplinas com uma nota só não têm tendência. Quem não tem nenhuma disciplina com duas
    notas fica com tendência 0 (estável). Uma única consulta para todos os alunos.
    """
    notas = {}  # (matrícula, oferta) -> notas na ordem das datas
    for matricula_id, oferta_id, valor in (
        Nota.objects.filter(matricula_id__in=ids)
        .order_by("avaliacao__data_hora", "avaliacao_id")
        .values_list("matricula_id", "avaliacao__oferta_id", "valor")
    ):
        notas.setdefault((matricula_id, oferta_id), []).append(valor)

    diferencas = {}  # matrícula -> diferença de cada disciplina
    for (matricula_id, _oferta_id), valores in notas.items():
        if len(valores) >= 2:
            diferencas.setdefault(matricula_id, []).append(valores[-1] - valores[0])
    return {
        matricula_id: calcular_media(diferencas.get(matricula_id, [])) or Decimal("0")
        for matricula_id in ids
    }


def contar_justificativas_pendentes(ids):
    """Quantas justificativas de cada matrícula ainda esperam a avaliação do professor."""
    return dict(
        Justificativa.objects.filter(
            frequencia__matricula_id__in=ids, status=Justificativa.Status.PENDENTE
        )
        .order_by()
        .values("frequencia__matricula_id")
        .annotate(total=Count("id"))
        .values_list("frequencia__matricula_id", "total")
    )


def variaveis_dos_alunos(matriculas):
    """As quatro variáveis de cada matrícula. Retorna {matrícula_id: {variável: valor}}.

    Média e frequência vêm de resumo_das_matriculas, as mesmas da lista de alunos.
    Quem ainda não tem nota ou chamada fica de fora: sem dados, o modelo só chutaria.
    São quatro consultas ao todo, qualquer que seja o número de alunos.
    """
    ids = [matricula.pk for matricula in matriculas]
    resumo = resumo_das_matriculas(matriculas)
    tendencias = calcular_tendencias(ids)
    pendentes = contar_justificativas_pendentes(ids)

    variaveis = {}
    for matricula_id in ids:
        dados = resumo[matricula_id]
        if dados["media"] is None or dados["frequencia"] is None:
            continue
        variaveis[matricula_id] = {
            "frequencia": dados["frequencia"],
            "media": dados["media"],
            "tendencia": tendencias[matricula_id],
            "justificativas_pendentes": pendentes.get(matricula_id, 0),
        }
    return variaveis


# --- 3. Resultado e explicação ---


def nivel_da_probabilidade(probabilidade):
    if probabilidade >= LIMITE_ALTO:
        return RiscoEvasao.Nivel.ALTO
    if probabilidade >= LIMITE_MEDIO:
        return RiscoEvasao.Nivel.MEDIO
    return RiscoEvasao.Nivel.BAIXO


def numero_br(valor):
    """Escreve o número com uma casa e vírgula, como 6,5.

    Corta a segunda casa em vez de arredondar: 74,96% vira "74,9%", e não "75,0%", que
    pareceria estar no limite mínimo e não abaixo dele.
    """
    return str(Decimal(valor).quantize(Decimal("0.1"), ROUND_DOWN)).replace(".", ",")


def explicar(variaveis):
    """Monta os principais motivos, do mais grave para o mais leve (no máximo três).

    Usa os mesmos limites do selo de situação (calculos.py), então a explicação concorda
    com o que o aluno e o professor veem nas outras telas.
    """
    frequencia = variaveis["frequencia"]
    media = variaveis["media"]
    tendencia = variaveis["tendencia"]
    pendentes = variaveis["justificativas_pendentes"]

    motivos = []
    if frequencia < FREQUENCIA_MINIMA:
        motivos.append(f"Frequência de {numero_br(frequencia)}%, abaixo do mínimo de 75%")
    if media < MEDIA_RISCO:
        motivos.append(f"Média {numero_br(media)}, abaixo de 6")
    if tendencia <= QUEDA_RELEVANTE:
        motivos.append(
            f"Notas em queda: {numero_br(abs(tendencia))} ponto(s) a menos da primeira "
            "para a última avaliação"
        )
    if FREQUENCIA_MINIMA <= frequencia < FREQUENCIA_ATENCAO:
        motivos.append(f"Frequência de {numero_br(frequencia)}%, perto do mínimo de 75%")
    if MEDIA_RISCO <= media < MEDIA_MINIMA:
        motivos.append(f"Média {numero_br(media)}, abaixo de 7")
    if pendentes:
        plural = "s" if pendentes > 1 else ""
        motivos.append(
            f"{pendentes} justificativa{plural} de falta aguardando o professor"
        )
    return motivos[:3]


def calcular_riscos():
    """Calcula e grava o risco de evasão de todos os alunos com matrícula ativa.

    Apaga os resultados anteriores e grava os novos em uma transação: se algo falhar no
    meio, o banco continua com o cálculo anterior inteiro. Retorna quantos foram gravados.
    """
    modelo = carregar_modelo()
    matriculas = list(Matricula.objects.filter(situacao=Matricula.Situacao.ATIVA))
    variaveis = variaveis_dos_alunos(matriculas)

    riscos = []
    if variaveis:
        ids = list(variaveis)
        tabela = pd.DataFrame(
            [[float(variaveis[pk][nome]) for nome in VARIAVEIS] for pk in ids],
            columns=VARIAVEIS,
        )
        # predict_proba devolve [chance de ficar, chance de evadir] para cada aluno.
        chances = modelo.predict_proba(tabela)[:, 1]
        for matricula_id, chance in zip(ids, chances):
            probabilidade = (Decimal(str(chance)) * 100).quantize(DUAS_CASAS, ROUND_HALF_UP)
            dados = variaveis[matricula_id]
            riscos.append(
                RiscoEvasao(
                    matricula_id=matricula_id,
                    probabilidade=probabilidade,
                    nivel=nivel_da_probabilidade(probabilidade),
                    motivos=explicar(dados),
                    **dados,
                )
            )

    with transaction.atomic():
        RiscoEvasao.objects.all().delete()
        RiscoEvasao.objects.bulk_create(riscos)
    return len(riscos)
