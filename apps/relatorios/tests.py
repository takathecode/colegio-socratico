"""Testes dos relatórios: permissões, arquivos PDF e Excel válidos e os números dentro deles."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academico.calculos import EM_ATENCAO, EM_RISCO
from apps.academico.models import (
    Aula,
    Avaliacao,
    Curso,
    Disciplina,
    Frequencia,
    Matricula,
    Nota,
    Oferta,
    Turma,
)
from apps.analytics.models import RiscoEvasao

from . import dados
from .excel import nome_da_aba

Usuario = get_user_model()

TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def abas_do_excel(resposta):
    """Lê o arquivo baixado: {nome da aba: DataFrame}. O RA é texto na planilha e continua texto."""
    return pd.read_excel(BytesIO(resposta.content), sheet_name=None, dtype={"RA": str})


class BaseRelatoriosMixin:
    """Turma com Matemática (Ana) e Física (Rui); Bia está em atenção e Caio, em risco."""

    @classmethod
    def setUpTestData(cls):
        cls.curso = Curso.objects.create(nome="Engenharia", total_creditos=200)
        cls.turma = Turma.objects.create(curso=cls.curso, codigo="T1", semestre="2026.2", periodo=1)
        matematica = Disciplina.objects.create(
            curso=cls.curso, codigo="MAT1", nome="Matemática", creditos=4, carga_horaria=40
        )
        fisica = Disciplina.objects.create(
            curso=cls.curso, codigo="FIS1", nome="Física & Lab", creditos=4, carga_horaria=40
        )
        cls.coordenador = Usuario.objects.create_user("coord", "senha", perfil="COORDENADOR")
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil="PROFESSOR", first_name="Ana", tratamento="Profa."
        )
        cls.outro_professor = Usuario.objects.create_user(
            "prof2", "senha", perfil="PROFESSOR", first_name="Rui"
        )
        cls.oferta = Oferta.objects.create(turma=cls.turma, disciplina=matematica, professor=cls.professor)
        cls.oferta_fisica = Oferta.objects.create(
            turma=cls.turma, disciplina=fisica, professor=cls.outro_professor
        )
        cls.aluno = Usuario.objects.create_user("2026001", "senha", first_name="Bia", last_name="Reis")
        cls.aluno2 = Usuario.objects.create_user("2026002", "senha", first_name="Caio", last_name="Lima")
        cls.matricula = Matricula.objects.create(aluno=cls.aluno, turma=cls.turma)
        cls.matricula2 = Matricula.objects.create(aluno=cls.aluno2, turma=cls.turma)

        agora = timezone.now()
        a1 = Avaliacao.objects.create(oferta=cls.oferta, nome="A1", data_hora=agora - timedelta(days=9))
        a2 = Avaliacao.objects.create(oferta=cls.oferta, nome="A2", data_hora=agora - timedelta(days=2))
        b1 = Avaliacao.objects.create(oferta=cls.oferta_fisica, nome="P1", data_hora=agora)
        # Bia: 7 e 6,5 em Matemática (média 6,75, Em atenção) e 8 em Física. Caio: 4 (Em risco).
        Nota.objects.create(avaliacao=a1, matricula=cls.matricula, valor=Decimal("7"))
        Nota.objects.create(avaliacao=a2, matricula=cls.matricula, valor=Decimal("6.5"))
        Nota.objects.create(avaliacao=b1, matricula=cls.matricula, valor=Decimal("8"))
        Nota.objects.create(avaliacao=a1, matricula=cls.matricula2, valor=Decimal("4"))

        aula = Aula.objects.create(oferta=cls.oferta, data=timezone.localdate() - timedelta(days=1))
        Frequencia.objects.create(aula=aula, matricula=cls.matricula, presente=True)
        Frequencia.objects.create(aula=aula, matricula=cls.matricula2, presente=False)

        RiscoEvasao.objects.create(
            matricula=cls.matricula2,
            probabilidade=Decimal("74.96"),
            nivel=RiscoEvasao.Nivel.ALTO,
            motivos=["Frequência de 0%, abaixo do mínimo de 75%", "Média 4,0, abaixo de 6"],
            frequencia=Decimal("0"),
            media=Decimal("4"),
            tendencia=Decimal("0"),
            justificativas_pendentes=0,
        )
        RiscoEvasao.objects.create(
            matricula=cls.matricula,
            probabilidade=Decimal("12.5"),
            nivel=RiscoEvasao.Nivel.BAIXO,
            motivos=[],
            frequencia=Decimal("100"),
            media=Decimal("7.37"),
            tendencia=Decimal("-0.5"),
            justificativas_pendentes=0,
        )


class PermissoesTests(BaseRelatoriosMixin, TestCase):
    def test_visitante_vai_para_o_login(self):
        resposta = self.client.get(reverse("relatorios:meu_boletim"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/entrar/", resposta["Location"])

    def test_aluno_nao_acessa_relatorios_da_coordenacao_nem_do_professor(self):
        self.client.force_login(self.aluno)
        urls = [
            reverse("relatorios:inicio"),
            reverse("relatorios:boletim", args=[self.matricula2.pk]),
            reverse("relatorios:turma") + f"?turma={self.turma.pk}",
            reverse("relatorios:risco"),
            reverse("relatorios:alunos") + "?formato=xlsx",
            reverse("relatorios:disciplina", args=[self.oferta.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_professor_so_baixa_as_proprias_disciplinas(self):
        self.client.force_login(self.professor)
        propria = reverse("relatorios:disciplina", args=[self.oferta.pk])
        alheia = reverse("relatorios:disciplina", args=[self.oferta_fisica.pk])
        self.assertEqual(self.client.get(propria).status_code, 200)
        self.assertEqual(self.client.get(alheia).status_code, 404)
        self.assertEqual(self.client.get(reverse("relatorios:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("relatorios:meu_boletim")).status_code, 403)

    def test_coordenador_nao_baixa_o_boletim_pela_rota_do_aluno(self):
        self.client.force_login(self.coordenador)
        self.assertEqual(self.client.get(reverse("relatorios:meu_boletim")).status_code, 403)


class BoletimTests(BaseRelatoriosMixin, TestCase):
    def test_aluno_baixa_o_proprio_boletim_em_pdf(self):
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("relatorios:meu_boletim"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="boletim-2026001-2026-2.pdf"', resposta["Content-Disposition"])
        self.assertTrue(resposta.content.startswith(b"%PDF"))

    def test_aluno_sem_matricula_ativa_volta_para_a_tela_de_notas(self):
        Matricula.objects.filter(aluno=self.aluno).update(situacao=Matricula.Situacao.TRANCADA)
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("relatorios:meu_boletim"))
        self.assertRedirects(resposta, reverse("aluno:notas"))

    def test_coordenador_baixa_o_boletim_de_qualquer_aluno(self):
        self.client.force_login(self.coordenador)
        resposta = self.client.get(reverse("relatorios:boletim", args=[self.matricula2.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(reverse("relatorios:boletim", args=[9999])).status_code, 404)

    def test_conteudo_do_boletim(self):
        relatorio = dados.boletim(self.matricula)
        linhas = {linha[0]: linha for linha in relatorio.tabelas[0].linhas}
        matematica = linhas["Matemática"]
        self.assertEqual(matematica[1], "Profa. Ana")
        self.assertEqual(matematica[2], "A1 7,0 · A2 6,5")
        self.assertEqual(matematica[3], Decimal("6.75"))
        self.assertEqual(matematica[6], EM_ATENCAO)
        self.assertEqual(len(relatorio.graficos), 1)  # o gráfico de barras das médias
        self.assertIn(("Frequência global", "100,0%"), relatorio.informacoes)

    def test_botao_da_tela_de_notas_aponta_para_o_pdf(self):
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("aluno:notas"))
        self.assertContains(resposta, reverse("relatorios:meu_boletim"))


class TurmaEDisciplinaTests(BaseRelatoriosMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.coordenador)

    def url_da_turma(self, formato):
        return reverse("relatorios:turma") + f"?turma={self.turma.pk}&formato={formato}"

    def test_pdf_da_turma(self):
        resposta = self.client.get(self.url_da_turma("pdf"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.content.startswith(b"%PDF"))

    def test_excel_da_turma_tem_resumo_uma_aba_por_disciplina_e_numeros(self):
        resposta = self.client.get(self.url_da_turma("xlsx"))
        self.assertEqual(resposta["Content-Type"], TIPO_EXCEL)
        abas = abas_do_excel(resposta)
        self.assertEqual(
            list(abas), ["Resumo por aluno", "Física & Lab", "Matemática", "Sobre o relatório"]
        )
        matematica = abas["Matemática"].set_index("RA")
        self.assertEqual(list(matematica.columns), ["Aluno", "A1", "A2", "Média", "Frequência (%)", "Faltas (h)", "Situação"])
        self.assertEqual(matematica.loc["2026001", "Média"], 6.75)  # número, não texto
        self.assertTrue(pd.isna(matematica.loc["2026002", "A2"]))  # nota não lançada fica em branco
        self.assertEqual(matematica.loc["2026002", "Situação"], EM_RISCO)

    def test_turma_ausente_ou_invalida_volta_para_a_tela_com_aviso(self):
        for url in (reverse("relatorios:turma"), reverse("relatorios:turma") + "?turma=abc"):
            with self.subTest(url=url):
                resposta = self.client.get(url, follow=True)
                self.assertRedirects(resposta, reverse("relatorios:inicio"))
                self.assertContains(resposta, "Escolha uma turma")

    def test_formato_desconhecido_responde_404(self):
        self.assertEqual(self.client.get(self.url_da_turma("docx")).status_code, 404)

    def test_excel_da_disciplina_do_professor(self):
        self.client.force_login(self.professor)
        url = reverse("relatorios:disciplina", args=[self.oferta.pk]) + "?formato=xlsx"
        abas = abas_do_excel(self.client.get(url))
        self.assertEqual(len(abas["Matemática"]), 2)  # os dois alunos ativos

    def test_botoes_nas_telas_de_turma_e_desempenho(self):
        resposta = self.client.get(reverse("coordenacao:turma", args=[self.turma.pk]))
        self.assertContains(resposta, f"?turma={self.turma.pk}&formato=pdf")
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("professor:desempenho") + f"?oferta={self.oferta.pk}")
        self.assertContains(resposta, reverse("relatorios:disciplina", args=[self.oferta.pk]))


class RiscoEAlunosTests(BaseRelatoriosMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.coordenador)

    def test_risco_em_pdf_e_excel(self):
        pdf = self.client.get(reverse("relatorios:risco") + "?formato=pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        abas = abas_do_excel(self.client.get(reverse("relatorios:risco") + "?formato=xlsx"))
        risco = abas["Alunos em risco"]
        self.assertEqual(list(risco["RA"]), ["2026002", "2026001"])  # do maior para o menor risco
        self.assertEqual(risco.loc[0, "Probabilidade (%)"], 74.96)
        self.assertIn("abaixo do mínimo", risco.loc[0, "Principais motivos"])

    def test_filtros_do_risco(self):
        url = reverse("relatorios:risco") + "?formato=xlsx&nivel=ALTO&turma=" + str(self.turma.pk)
        abas = abas_do_excel(self.client.get(url))
        self.assertEqual(list(abas["Alunos em risco"]["RA"]), ["2026002"])
        sobre = abas["Sobre o relatório"].set_index("Campo")["Valor"]
        self.assertEqual(sobre["Filtros"], "Turma T1 (2026.2) · Risco alto")

        # A busca usa o nome completo: "bia reis" encontra Bia Reis.
        abas = abas_do_excel(self.client.get(reverse("relatorios:risco") + "?formato=xlsx&busca=bia reis"))
        self.assertEqual(list(abas["Alunos em risco"]["RA"]), ["2026001"])

    def test_filtro_invalido_e_ignorado(self):
        abas = abas_do_excel(self.client.get(reverse("relatorios:risco") + "?formato=xlsx&turma=abc&nivel=X"))
        self.assertEqual(len(abas["Alunos em risco"]), 2)

    def test_tela_de_risco_usa_o_mesmo_filtro_e_leva_os_filtros_para_o_pdf(self):
        resposta = self.client.get(reverse("coordenacao:risco") + "?nivel=ALTO")
        self.assertEqual(resposta.context["total"], 1)
        self.assertContains(resposta, "?nivel=ALTO&formato=pdf")

    def test_lista_de_alunos_em_excel_com_filtro_de_situacao(self):
        abas = abas_do_excel(self.client.get(reverse("relatorios:alunos") + "?formato=xlsx"))
        self.assertEqual(len(abas["Alunos"]), 2)
        abas = abas_do_excel(
            self.client.get(reverse("relatorios:alunos") + "?formato=xlsx&situacao=" + EM_RISCO)
        )
        self.assertEqual(list(abas["Alunos"]["RA"]), ["2026002"])

    def test_lista_de_alunos_so_sai_em_excel(self):
        self.assertEqual(self.client.get(reverse("relatorios:alunos") + "?formato=pdf").status_code, 404)

    def test_tela_de_relatorios_e_item_do_menu(self):
        resposta = self.client.get(reverse("relatorios:inicio"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Desempenho da turma")
        self.assertContains(resposta, f'href="{reverse("relatorios:inicio")}"')  # menu ativo

    def test_lista_de_alunos_tem_link_do_boletim(self):
        resposta = self.client.get(reverse("coordenacao:alunos"))
        self.assertContains(resposta, reverse("relatorios:boletim", args=[self.matricula.pk]))


class FormatacaoTests(TestCase):
    def test_numeros_sao_cortados_e_nao_arredondados(self):
        self.assertEqual(dados.formatar(Decimal("74.96"), dados.PERCENTUAL), "74,9%")
        self.assertEqual(dados.formatar(Decimal("6.75"), dados.NOTA), "6,7")
        self.assertEqual(dados.formatar(None, dados.NOTA), "—")
        self.assertEqual(dados.formatar(Decimal("-0.04"), dados.NOTA), "0,0")

    def test_nome_da_aba_respeita_o_limite_do_excel(self):
        usados = set()
        longo = "Introdução à Programação Orientada a Objetos"
        primeiro = nome_da_aba(longo, usados)
        segundo = nome_da_aba(longo, usados)
        self.assertEqual(len(primeiro), 31)
        self.assertLessEqual(len(segundo), 31)
        self.assertTrue(segundo.endswith("(2)"))
        self.assertEqual(nome_da_aba("Notas: A/B", usados), "Notas- A-B")
