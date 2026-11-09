"""Testes dos gráficos: as funções de desenho e as telas que os mostram."""

import base64
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.academico.models import Turma
from apps.professor.tests import HASH_RAPIDO, BaseProfessorMixin

from . import graficos
from .dados import contar_por_faixa, frequencia_mensal_por_turma

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
