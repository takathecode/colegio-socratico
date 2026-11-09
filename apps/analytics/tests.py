"""Testes dos gráficos e do módulo preditivo de evasão."""

import base64
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import (
    Avaliacao,
    Frequencia,
    Justificativa,
    Matricula,
    Nota,
    Turma,
)
from apps.coordenacao.tests import BaseCoordenacaoMixin
from apps.professor.tests import HASH_RAPIDO, BaseProfessorMixin

from . import evasao, graficos
from .dados import contar_por_faixa, frequencia_mensal_por_turma
from .models import RiscoEvasao

Usuario = get_user_model()

ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"  # os primeiros bytes de todo arquivo PNG


def linha_do_boletim(nome, media):
    """Uma linha no formato de resumo_por_disciplina(), só com o que o gráfico usa."""
    return {
        "oferta": SimpleNamespace(disciplina=SimpleNamespace(nome=nome)),
        "media": None if media is None else Decimal(media),
    }


class GraficosTests(SimpleTestCase):
    """Os gráficos não consultam o banco: recebem os dados prontos."""

    def assertPngValido(self, grafico):
        self.assertIsNotNone(grafico)
        self.assertTrue(base64.b64decode(grafico["png"]).startswith(ASSINATURA_PNG))

    def test_notas_por_disciplina(self):
        grafico = graficos.notas_por_disciplina(
            [linha_do_boletim("Cálculo", "8.5"), linha_do_boletim("Física", None)]
        )
        self.assertPngValido(grafico)
        # Disciplina sem nota fica fora: "sem nota" não é nota zero.
        self.assertIn("Cálculo, 8,5", grafico["descricao"])
        self.assertNotIn("Física", grafico["descricao"])

    def test_notas_por_disciplina_sem_nota(self):
        self.assertIsNone(graficos.notas_por_disciplina([]))
        self.assertIsNone(graficos.notas_por_disciplina([linha_do_boletim("Física", None)]))

    def test_distribuicao_de_notas(self):
        grafico = graficos.distribuicao_de_notas(contar_por_faixa([Decimal("4"), Decimal("8")]))
        self.assertPngValido(grafico)
        self.assertIn("4 a 6, 1 aluno;", grafico["descricao"])

    def test_distribuicao_sem_notas(self):
        self.assertIsNone(graficos.distribuicao_de_notas(contar_por_faixa([None, None])))

    def test_evolucao_da_frequencia(self):
        series = [
            {"nome": "T1", "meses": [(date(2026, 8, 1), Decimal("90")), (date(2026, 9, 1), Decimal("72.5"))]},
            {"nome": "T2", "meses": [(date(2026, 9, 1), Decimal("85"))]},
        ]
        grafico = graficos.evolucao_da_frequencia(series)
        self.assertPngValido(grafico)
        self.assertIn("T1: ago 90%, set 72%", grafico["descricao"])

    def test_evolucao_sem_chamadas(self):
        self.assertIsNone(graficos.evolucao_da_frequencia([]))
        self.assertIsNone(graficos.evolucao_da_frequencia([{"nome": "T1", "meses": []}]))


class ContarPorFaixaTests(SimpleTestCase):
    def quantidades(self, medias):
        return {f["rotulo"]: f["quantidade"] for f in contar_por_faixa(map(Decimal, medias))}

    def test_limite_entra_na_faixa_de_cima(self):
        contagem = self.quantidades(["6", "7", "5.99"])
        self.assertEqual(contagem["6 a 7"], 1)
        self.assertEqual(contagem["7 a 8"], 1)
        self.assertEqual(contagem["4 a 6"], 1)

    def test_zero_e_dez_entram_nas_pontas(self):
        contagem = self.quantidades(["0", "10"])
        self.assertEqual(contagem["0 a 2"], 1)
        self.assertEqual(contagem["8 a 10"], 1)

    def test_grupos_seguem_os_limites_do_selo(self):
        grupos = [faixa["grupo"] for faixa in contar_por_faixa([])]
        self.assertEqual(
            grupos,
            ["Abaixo de 6", "Abaixo de 6", "Abaixo de 6", "Entre 6 e 7", "7 ou mais", "7 ou mais"],
        )


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class TelasComGraficoTests(BaseProfessorMixin, TestCase):
    """Usa os dados do teste do professor: notas 8 e 4 em Matemática e uma chamada ontem."""

    def test_painel_do_aluno_mostra_o_grafico_de_notas(self):
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertIsNotNone(resposta.context["grafico_notas"])
        self.assertContains(resposta, "data:image/png;base64,")

    def test_desempenho_do_professor(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("professor:desempenho"), {"oferta": self.oferta.pk})
        self.assertEqual(resposta.status_code, 200)
        contagem = {f["rotulo"]: f["quantidade"] for f in resposta.context["faixas"]}
        self.assertEqual(contagem["4 a 6"], 1)
        self.assertEqual(contagem["8 a 10"], 1)
        self.assertContains(resposta, "data:image/png;base64,")

    def test_desempenho_de_disciplina_de_outro_professor_da_404(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(
            reverse("professor:desempenho"), {"oferta": self.oferta_do_outro.pk}
        )
        self.assertEqual(resposta.status_code, 404)

    def test_painel_da_coordenacao_mostra_a_frequencia(self):
        coordenador = Usuario.objects.create_user("coord", "senha", perfil="COORDENADOR")
        self.client.force_login(coordenador)
        resposta = self.client.get(reverse("coordenacao:painel"))
        self.assertIsNotNone(resposta.context["grafico_frequencia"])
        self.assertContains(resposta, "data:image/png;base64,")

    def test_frequencia_mensal_por_turma(self):
        # Ontem: Matemática com 1 presença e 1 falta (2 h cada) e Física com 1 falta (2 h).
        # Na turma: 6 h dadas e 4 h de falta = 33,33%.
        series = frequencia_mensal_por_turma([self.turma])
        self.assertEqual(len(series), 1)
        mes, percentual = series[0]["meses"][-1]
        self.assertEqual(mes, self.aula.data.replace(day=1))
        self.assertEqual(percentual, Decimal("33.33"))

    def test_aluno_inativo_nao_entra_na_frequencia(self):
        self.matricula2.situacao = self.matricula2.Situacao.TRANCADA
        self.matricula2.save()
        mes, percentual = frequencia_mensal_por_turma([self.turma])[0]["meses"][-1]
        # Sobram só as aulas da matrícula 1: 2 h presente e 2 h de falta = 50%.
        self.assertEqual(percentual, Decimal("50.00"))

    def test_turma_sem_chamada_fica_de_fora(self):
        nova = Turma.objects.create(
            curso=self.turma.curso, codigo="T2", semestre="2026.2", periodo=2
        )
        series = frequencia_mensal_por_turma([nova, self.turma])
        self.assertEqual([serie["nome"] for serie in series], ["T1"])


# --- Módulo preditivo de evasão (evasao.py) ---


class ModeloTreinadoMixin:
    """Treina um modelo pequeno (rápido) em uma pasta temporária, uma vez por classe.

    Assim os testes nunca usam nem apagam o modelo de verdade, que fica em ml/.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pasta = tempfile.TemporaryDirectory()
        cls.addClassCleanup(pasta.cleanup)
        configuracao = override_settings(MODELO_EVASAO=Path(pasta.name) / "modelo.joblib")
        configuracao.enable()
        cls.addClassCleanup(configuracao.disable)
        cls.resultado = evasao.treinar(quantidade=400, arvores=25)


SEM_MODELO = override_settings(MODELO_EVASAO=Path(tempfile.gettempdir()) / "nao-existe.joblib")


def variaveis(frequencia, media, tendencia="0", pendentes=0):
    return {
        "frequencia": Decimal(frequencia),
        "media": Decimal(media),
        "tendencia": Decimal(tendencia),
        "justificativas_pendentes": pendentes,
    }


class SimulacaoEExplicacaoTests(SimpleTestCase):
    def test_dados_simulados_sao_sempre_iguais(self):
        dados = evasao.gerar_dados_simulados(300)
        self.assertTrue(dados.equals(evasao.gerar_dados_simulados(300)))
        self.assertEqual(list(dados.columns), [*evasao.VARIAVEIS, "evadiu"])
        self.assertEqual(set(dados["evadiu"]), {0, 1})  # há quem evade e quem continua

    def test_quem_falta_mais_evade_mais(self):
        dados = evasao.gerar_dados_simulados()
        faltosos = dados[dados["frequencia"] < 70]["evadiu"].mean()
        assiduos = dados[dados["frequencia"] > 90]["evadiu"].mean()
        self.assertGreater(faltosos, assiduos)

    def test_nivel_da_probabilidade(self):
        Nivel = RiscoEvasao.Nivel
        for probabilidade, nivel in (
            (Decimal("29.99"), Nivel.BAIXO),
            (Decimal("30"), Nivel.MEDIO),
            (Decimal("59.99"), Nivel.MEDIO),
            (Decimal("60"), Nivel.ALTO),
        ):
            with self.subTest(probabilidade=probabilidade):
                self.assertEqual(evasao.nivel_da_probabilidade(probabilidade), nivel)

    def test_motivos_do_aluno_em_risco(self):
        motivos = evasao.explicar(variaveis("63", "4.8", "-1.2", 2))
        # No máximo três: as justificativas pendentes, o motivo mais leve, ficam de fora.
        self.assertEqual(
            motivos,
            [
                "Frequência de 63,0%, abaixo do mínimo de 75%",
                "Média 4,8, abaixo de 6",
                "Notas em queda: 1,2 ponto(s) a menos da primeira para a última avaliação",
            ],
        )

    def test_motivos_em_atencao_e_pendencias(self):
        motivos = evasao.explicar(variaveis("77.5", "6.55", "0", 1))
        self.assertEqual(
            motivos,
            [
                "Frequência de 77,5%, perto do mínimo de 75%",
                "Média 6,5, abaixo de 7",
                "1 justificativa de falta aguardando o professor",
            ],
        )

    def test_numero_no_limite_nao_parece_o_limite(self):
        # 74,96% arredondado viraria "75,0%, abaixo do mínimo de 75%".
        motivos = evasao.explicar(variaveis("74.96", "5.96"))
        self.assertIn("Frequência de 74,9%, abaixo do mínimo de 75%", motivos)
        self.assertIn("Média 5,9, abaixo de 6", motivos)

    def test_aluno_regular_nao_tem_motivo(self):
        self.assertEqual(evasao.explicar(variaveis("92", "8.4", "0.3")), [])


class TreinoTests(ModeloTreinadoMixin, SimpleTestCase):
    def test_salva_o_modelo_e_acerta_mais_que_o_chute(self):
        self.assertTrue(evasao.modelo_treinado())
        self.assertGreater(self.resultado["acuracia"], self.resultado["acuracia_chute"])
        self.assertAlmostEqual(sum(self.resultado["importancias"].values()), 1, places=5)
        modelo = evasao.carregar_modelo()
        self.assertEqual(list(modelo.feature_names_in_), evasao.VARIAVEIS)

    @SEM_MODELO
    def test_sem_arquivo_avisa_que_falta_treinar(self):
        self.assertFalse(evasao.modelo_treinado())
        with self.assertRaisesMessage(evasao.ModeloNaoTreinado, "treinar_modelo"):
            evasao.carregar_modelo()


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class CalculoDeRiscoTests(ModeloTreinadoMixin, BaseCoordenacaoMixin, TestCase):
    """Bia vai bem (média 7,5 e 100% de presença); Caio vai mal (média 3 e 0% de presença)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Uma segunda prova de Matemática, para existir tendência: Bia cai de 9 para 8 e
        # Caio cai de 4 para 2.
        a2 = Avaliacao.objects.create(
            oferta=cls.oferta, nome="A2", data_hora=timezone.now() + timedelta(days=7)
        )
        Nota.objects.create(avaliacao=a2, matricula=cls.matricula, valor=Decimal("8"))
        Nota.objects.create(avaliacao=a2, matricula=cls.matricula2, valor=Decimal("2"))
        Justificativa.objects.create(
            frequencia=Frequencia.objects.get(matricula=cls.matricula2), motivo="Consulta"
        )
        # Aluno sem nota nem chamada: fica fora do cálculo.
        cls.aluno3 = Usuario.objects.create_user("aluno3", "senha", first_name="Davi")
        cls.matricula3 = Matricula.objects.create(aluno=cls.aluno3, turma=cls.turma)

    def riscos(self):
        return {risco.matricula_id: risco for risco in RiscoEvasao.objects.all()}

    def ids_da_pagina(self, resposta):
        return [risco.matricula_id for risco in resposta.context["pagina"]]

    def test_variaveis_dos_alunos(self):
        dados = evasao.variaveis_dos_alunos([self.matricula, self.matricula2, self.matricula3])
        self.assertNotIn(self.matricula3.pk, dados)
        # Bia: Matemática (9 + 8) / 2 = 8,5 e Física 6,5 -> média 7,5. Só Matemática tem
        # duas notas, então a tendência é 8 - 9 = -1.
        self.assertEqual(dados[self.matricula.pk], variaveis("100.00", "7.50", "-1.00", 0))
        self.assertEqual(dados[self.matricula2.pk], variaveis("0.00", "3.00", "-2.00", 1))

    def test_justificativa_avaliada_nao_conta(self):
        Justificativa.objects.update(status=Justificativa.Status.APROVADA)
        dados = evasao.variaveis_dos_alunos([self.matricula2])
        self.assertEqual(dados[self.matricula2.pk]["justificativas_pendentes"], 0)

    def test_calcula_e_grava_o_risco(self):
        self.assertEqual(evasao.calcular_riscos(), 2)
        riscos = self.riscos()
        bia, caio = riscos[self.matricula.pk], riscos[self.matricula2.pk]
        self.assertGreater(caio.probabilidade, bia.probabilidade)
        self.assertEqual(caio.nivel, RiscoEvasao.Nivel.ALTO)
        self.assertEqual(caio.motivos[0], "Frequência de 0,0%, abaixo do mínimo de 75%")
        self.assertEqual(caio.justificativas_pendentes, 1)

    def test_recalcular_substitui_o_resultado_anterior(self):
        evasao.calcular_riscos()
        Matricula.objects.filter(pk=self.matricula2.pk).update(
            situacao=Matricula.Situacao.TRANCADA
        )
        self.assertEqual(evasao.calcular_riscos(), 1)
        self.assertEqual(list(self.riscos()), [self.matricula.pk])

    def test_sem_modelo_mantem_o_calculo_anterior(self):
        evasao.calcular_riscos()
        with SEM_MODELO, self.assertRaises(evasao.ModeloNaoTreinado):
            evasao.calcular_riscos()
        self.assertEqual(RiscoEvasao.objects.count(), 2)

    def test_comando_calcular_riscos(self):
        saida = StringIO()
        call_command("calcular_riscos", stdout=saida)
        self.assertIn("2 aluno(s)", saida.getvalue())
        with SEM_MODELO, self.assertRaisesMessage(CommandError, "treinar_modelo"):
            call_command("calcular_riscos", stdout=StringIO())

    # --- Telas ---

    def test_tela_lista_do_maior_para_o_menor_risco(self):
        evasao.calcular_riscos()
        resposta = self.client.get(reverse("coordenacao:risco"))
        self.assertEqual(self.ids_da_pagina(resposta), [self.matricula2.pk, self.matricula.pk])
        self.assertEqual(resposta.context["alto"], 1)
        self.assertEqual(resposta.context["sem_dados"], 1)  # o Davi
        self.assertContains(resposta, "Frequência de 0,0%, abaixo do mínimo de 75%")

    def test_tela_filtra_por_nivel_e_busca(self):
        evasao.calcular_riscos()
        url = reverse("coordenacao:risco")
        resposta = self.client.get(url, {"nivel": "ALTO"})
        self.assertEqual(self.ids_da_pagina(resposta), [self.matricula2.pk])
        resposta = self.client.get(url, {"busca": "bia"})
        self.assertEqual(self.ids_da_pagina(resposta), [self.matricula.pk])

    def test_tela_antes_do_primeiro_calculo(self):
        resposta = self.client.get(reverse("coordenacao:risco"))
        self.assertContains(resposta, "Risco ainda não calculado")
        self.assertContains(resposta, "Recalcular agora")

    @SEM_MODELO
    def test_tela_sem_modelo_explica_como_treinar(self):
        resposta = self.client.get(reverse("coordenacao:risco"))
        self.assertContains(resposta, "python manage.py treinar_modelo")
        self.assertNotContains(resposta, "Recalcular agora")

    def test_botao_recalcular(self):
        resposta = self.client.post(reverse("coordenacao:risco_recalcular"), follow=True)
        self.assertRedirects(resposta, reverse("coordenacao:risco"))
        self.assertContains(resposta, "recalculado para 2 aluno(s)")
        self.assertEqual(RiscoEvasao.objects.count(), 2)

    def test_recalcular_so_por_post(self):
        resposta = self.client.get(reverse("coordenacao:risco_recalcular"))
        self.assertEqual(resposta.status_code, 405)

    @SEM_MODELO
    def test_recalcular_sem_modelo_mostra_erro(self):
        resposta = self.client.post(reverse("coordenacao:risco_recalcular"), follow=True)
        self.assertContains(resposta, "ainda não foi treinado")

    def test_professor_e_aluno_nao_recalculam(self):
        for usuario in (self.professor, self.aluno):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.matricula):
                resposta = self.client.post(reverse("coordenacao:risco_recalcular"))
                self.assertEqual(resposta.status_code, 403)
        self.assertFalse(RiscoEvasao.objects.exists())

    def test_painel_mostra_os_maiores_riscos(self):
        resposta = self.client.get(reverse("coordenacao:painel"))
        self.assertContains(resposta, "Risco ainda não calculado")
        evasao.calcular_riscos()
        resposta = self.client.get(reverse("coordenacao:painel"))
        maiores = resposta.context["maiores_riscos"]
        self.assertEqual(maiores[0].matricula_id, self.matricula2.pk)
        self.assertTrue(all(risco.nivel != RiscoEvasao.Nivel.BAIXO for risco in maiores))
