"""Testes da área do aluno: permissões, cálculos mostrados na tela e envio de justificativa."""

import shutil
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import (
    Aula,
    Avaliacao,
    Curso,
    Disciplina,
    Evento,
    Frequencia,
    Justificativa,
    Matricula,
    Nota,
    Oferta,
    Turma,
)
from apps.financeiro.models import Mensalidade

from . import servicos

Usuario = get_user_model()

TELAS = ("painel", "notas", "frequencia", "calendario", "financeiro")
HASH_RAPIDO = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_DE_TESTE = tempfile.mkdtemp(prefix="testes-aluno-")


def tearDownModule():
    shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)


class BaseAlunoMixin:
    """Dois alunos em turmas diferentes, para provar que um não enxerga os dados do outro."""

    @classmethod
    def setUpTestData(cls):
        cls.curso = Curso.objects.create(nome="Curso", total_creditos=200)
        cls.disciplina = Disciplina.objects.create(
            curso=cls.curso, codigo="MAT1", nome="Matemática", creditos=4, carga_horaria=40
        )
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil="PROFESSOR", first_name="Ana", last_name="Dias", tratamento="Profa."
        )
        cls.turma = Turma.objects.create(curso=cls.curso, codigo="T1", semestre="2026.2", periodo=1)
        cls.outra_turma = Turma.objects.create(
            curso=cls.curso, codigo="T2", semestre="2026.2", periodo=1
        )
        cls.oferta = Oferta.objects.create(
            turma=cls.turma, disciplina=cls.disciplina, professor=cls.professor
        )
        cls.outra_oferta = Oferta.objects.create(
            turma=cls.outra_turma, disciplina=cls.disciplina, professor=cls.professor
        )
        cls.aluno = Usuario.objects.create_user("aluno", "senha", first_name="Bia", last_name="Reis")
        cls.outro_aluno = Usuario.objects.create_user("outro", "senha", first_name="Caio")
        cls.matricula = Matricula.objects.create(
            aluno=cls.aluno,
            turma=cls.turma,
            creditos_concluidos=100,
            coeficiente_rendimento=Decimal("8.40"),
        )
        cls.outra_matricula = Matricula.objects.create(aluno=cls.outro_aluno, turma=cls.outra_turma)

        hoje = timezone.localdate()
        cls.aula_presente = Aula.objects.create(
            oferta=cls.oferta, data=hoje - timedelta(days=2), horas_aula=2
        )
        cls.aula_falta = Aula.objects.create(
            oferta=cls.oferta, data=hoje - timedelta(days=1), horas_aula=2
        )
        Frequencia.objects.create(aula=cls.aula_presente, matricula=cls.matricula, presente=True)
        cls.falta = Frequencia.objects.create(
            aula=cls.aula_falta, matricula=cls.matricula, presente=False
        )
        aula_do_outro = Aula.objects.create(
            oferta=cls.outra_oferta, data=hoje - timedelta(days=1), horas_aula=2
        )
        cls.falta_do_outro = Frequencia.objects.create(
            aula=aula_do_outro, matricula=cls.outra_matricula, presente=False
        )
        avaliacao = Avaliacao.objects.create(
            oferta=cls.oferta, nome="A1", data_hora=timezone.now() - timedelta(days=5)
        )
        Nota.objects.create(avaliacao=avaliacao, matricula=cls.matricula, valor=Decimal("6.50"))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class PermissoesTests(BaseAlunoMixin, TestCase):
    def test_visitante_vai_para_o_login(self):
        for tela in TELAS:
            with self.subTest(tela=tela):
                resposta = self.client.get(reverse(f"aluno:{tela}"))
                self.assertEqual(resposta.status_code, 302)
                self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_outros_perfis_recebem_403(self):
        self.client.force_login(self.professor)
        for tela in TELAS:
            with self.subTest(tela=tela):
                self.assertEqual(self.client.get(reverse(f"aluno:{tela}")).status_code, 403)

    def test_aluno_abre_todas_as_telas(self):
        self.client.force_login(self.aluno)
        for tela in TELAS:
            with self.subTest(tela=tela):
                self.assertEqual(self.client.get(reverse(f"aluno:{tela}")).status_code, 200)

    def test_sem_matricula_ativa_mostra_aviso_e_nao_erro(self):
        sem_turma = Usuario.objects.create_user("novo", "senha")
        self.client.force_login(sem_turma)
        for tela in TELAS:
            with self.subTest(tela=tela):
                resposta = self.client.get(reverse(f"aluno:{tela}"))
                self.assertContains(resposta, "não tem uma matrícula ativa")


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class PainelENotasTests(BaseAlunoMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.aluno)

    def test_painel_mostra_os_dados_do_proprio_aluno(self):
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertContains(resposta, "100/200")
        self.assertContains(resposta, "8,4")
        self.assertContains(resposta, "Matemática")
        self.assertEqual(resposta.context["frequencia"]["percentual"], Decimal("50.00"))

    def test_largura_da_barra_nao_usa_virgula(self):
        """Em pt-BR "88,9" quebraria o CSS, então a largura precisa ser um inteiro."""
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertContains(resposta, "width: 50%")
        self.assertIsInstance(resposta.context["frequencia"]["largura"], int)

    def test_varias_faltas_contam_como_uma_pendencia(self):
        outra_aula = Aula.objects.create(
            oferta=self.oferta, data=timezone.localdate() - timedelta(days=9), horas_aula=2
        )
        Frequencia.objects.create(aula=outra_aula, matricula=self.matricula, presente=False)
        pendencias = servicos.montar_pendencias(self.matricula)
        self.assertEqual(len(pendencias), 1)
        self.assertIn("2", pendencias[0]["detalhe"])

    def test_entrega_proxima_e_parcela_atrasada_viram_pendencia(self):
        Avaliacao.objects.create(
            oferta=self.oferta,
            nome="Trabalho",
            tipo=Avaliacao.Tipo.ENTREGA,
            data_hora=timezone.now() + timedelta(days=3),
        )
        Mensalidade.objects.create(
            matricula=self.matricula,
            competencia=date(2026, 1, 1),
            parcela=1,
            total_parcelas=6,
            valor=Decimal("100"),
            vencimento=timezone.localdate() - timedelta(days=1),
        )
        titulos = [item["titulo"] for item in servicos.montar_pendencias(self.matricula)]
        self.assertIn("Trabalho: Matemática", titulos)
        self.assertIn("Mensalidade em atraso", titulos)

    def test_proxima_prova_nao_conta_entrega_nem_outra_turma(self):
        momento = timezone.now() + timedelta(days=3)
        Avaliacao.objects.create(
            oferta=self.oferta, nome="Trabalho", tipo=Avaliacao.Tipo.ENTREGA, data_hora=momento
        )
        Avaliacao.objects.create(oferta=self.outra_oferta, nome="Prova outra", data_hora=momento)
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertIsNone(resposta.context["proxima_prova"])
        Avaliacao.objects.create(oferta=self.oferta, nome="A2", data_hora=momento)
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertEqual(resposta.context["proxima_prova"].nome, "A2")
        self.assertEqual(resposta.context["dias_ate_a_prova"], "Em 3 dias")

    def test_boletim_avisa_disciplina_que_merece_atencao(self):
        resposta = self.client.get(reverse("aluno:notas"))
        self.assertContains(resposta, "Matemática merece sua atenção")
        self.assertContains(resposta, "6,5")
        self.assertContains(resposta, f"para={self.professor.pk}")

    def test_situacoes_calculam_os_trechos_da_rosca(self):
        linhas = [{"situacao": s} for s in ("Regular", "Regular", "Em atenção", "Em risco", None)]
        resumo = servicos.resumo_de_situacoes(linhas)
        self.assertEqual((resumo["regulares"], resumo["atencao"], resumo["risco"]), (2, 1, 1))
        self.assertEqual((resumo["inicio_atencao"], resumo["inicio_risco"]), (-2, -3))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO, MEDIA_ROOT=MEDIA_DE_TESTE)
class JustificativaTests(BaseAlunoMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.aluno)
        self.url = reverse("aluno:frequencia")

    def enviar(self, **dados):
        return self.client.post(self.url, {"frequencia": self.falta.pk, "motivo": "Consulta", **dados})

    def test_envio_valido_cria_pedido_pendente_com_anexo(self):
        anexo = SimpleUploadedFile("atestado.pdf", b"%PDF-1.4", content_type="application/pdf")
        resposta = self.enviar(anexo=anexo)
        self.assertRedirects(resposta, self.url)
        justificativa = Justificativa.objects.get()
        self.assertEqual(justificativa.status, Justificativa.Status.PENDENTE)
        self.assertEqual(justificativa.frequencia, self.falta)
        self.assertTrue(justificativa.anexo)

    def test_nao_justifica_falta_de_outro_aluno(self):
        resposta = self.client.post(
            self.url, {"frequencia": self.falta_do_outro.pk, "motivo": "Tentativa"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Justificativa.objects.exists())
        self.assertTrue(resposta.context["abrir_modal"])

    def test_nao_justifica_presenca(self):
        presenca = Frequencia.objects.get(aula=self.aula_presente, matricula=self.matricula)
        self.client.post(self.url, {"frequencia": presenca.pk, "motivo": "Tentativa"})
        self.assertFalse(Justificativa.objects.exists())

    def test_nao_repete_pedido_pendente_mas_reenvia_apos_rejeicao(self):
        self.enviar()
        self.enviar()
        self.assertEqual(Justificativa.objects.count(), 1)
        Justificativa.objects.update(status=Justificativa.Status.REJEITADA)
        self.enviar()
        self.assertEqual(Justificativa.objects.count(), 2)

    def test_recusa_anexo_de_formato_invalido(self):
        anexo = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        resposta = self.enviar(anexo=anexo)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Justificativa.objects.exists())
        self.assertTrue(resposta.context["form"].errors["anexo"])

    def test_motivo_e_obrigatorio(self):
        resposta = self.client.post(self.url, {"frequencia": self.falta.pk, "motivo": " "})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Justificativa.objects.exists())

    def test_anexo_so_e_baixado_pelo_dono(self):
        anexo = SimpleUploadedFile("atestado.pdf", b"%PDF-1.4", content_type="application/pdf")
        self.enviar(anexo=anexo)
        url = reverse("aluno:anexo_justificativa", args=[Justificativa.objects.get().pk])

        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])
        b"".join(resposta.streaming_content)  # lê até o fim, para o Windows liberar o arquivo

        self.client.force_login(self.outro_aluno)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_anexo_ausente_neste_computador_responde_404(self):
        justificativa = Justificativa.objects.create(
            frequencia=self.falta, motivo="Consulta", anexo="justificativas/nao_existe.pdf"
        )
        url = reverse("aluno:anexo_justificativa", args=[justificativa.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_sem_faltas_nao_mostra_o_modal(self):
        self.client.force_login(Usuario.objects.get(matricula="outro"))
        Frequencia.objects.filter(pk=self.falta_do_outro.pk).update(presente=True)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, '<dialog id="modal-justificar"')
        self.assertContains(resposta, "Nenhuma falta aguardando justificativa")


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class CalendariosTests(BaseAlunoMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.aluno)

    def test_dia_com_alguma_falta_aparece_como_ausencia(self):
        outra_disciplina = Disciplina.objects.create(
            curso=self.curso, codigo="FIS1", nome="Física", creditos=4, carga_horaria=40
        )
        oferta = Oferta.objects.create(
            turma=self.turma, disciplina=outra_disciplina, professor=self.professor
        )
        aula = Aula.objects.create(oferta=oferta, data=self.aula_falta.data, horas_aula=2)
        Frequencia.objects.create(aula=aula, matricula=self.matricula, presente=True)

        mes = self.aula_falta.data.replace(day=1)
        dias = [dia for semana in servicos.semanas_de_frequencia(self.matricula, mes) for dia in semana]
        dia = next(d for d in dias if d["data"] == self.aula_falta.data)
        self.assertEqual(dia["status"], "falta")

        # Filtrando só a disciplina em que estava presente, o mesmo dia vira presença.
        dias = [
            dia
            for semana in servicos.semanas_de_frequencia(self.matricula, mes, oferta.pk)
            for dia in semana
        ]
        dia = next(d for d in dias if d["data"] == self.aula_falta.data)
        self.assertEqual(dia["status"], "presenca")

    def test_filtro_ignora_disciplina_de_outra_turma(self):
        resposta = self.client.get(
            reverse("aluno:frequencia"), {"disciplina": self.outra_oferta.pk}
        )
        self.assertIsNone(resposta.context["oferta_id"])

    def test_valores_invalidos_na_url_nao_quebram_as_telas(self):
        for mes in ("abc", "2026-13", "2026-00", "0000-01", "9999-12", "2026-10-05", ""):
            with self.subTest(mes=mes):
                resposta = self.client.get(reverse("aluno:frequencia"), {"mes": mes})
                self.assertEqual(resposta.status_code, 200)
        for data in ("abc", "2026-13-45", "0001-01-01", "9999-12-31", ""):
            for visao in ("mes", "semana", "lista", "outra"):
                with self.subTest(data=data, visao=visao):
                    resposta = self.client.get(
                        reverse("aluno:calendario"), {"data": data, "visao": visao}
                    )
                    self.assertEqual(resposta.status_code, 200)

    def test_calendario_junta_avaliacoes_e_eventos_da_turma(self):
        momento = timezone.make_aware(datetime(2026, 10, 30, 19, 10))
        Avaliacao.objects.create(oferta=self.oferta, nome="A3", data_hora=momento, local="Sala 1")
        Avaliacao.objects.create(oferta=self.outra_oferta, nome="Outra", data_hora=momento)
        Evento.objects.create(titulo="Feriado X", tipo=Evento.Tipo.FERIADO, inicio=momento)
        Evento.objects.create(
            titulo="Evento da outra turma",
            tipo=Evento.Tipo.ATIVIDADE,
            oferta=self.outra_oferta,
            inicio=momento,
        )
        for visao in ("mes", "semana", "lista"):
            with self.subTest(visao=visao):
                resposta = self.client.get(
                    reverse("aluno:calendario"), {"visao": visao, "data": "2026-10-30"}
                )
                self.assertContains(resposta, "Prova de Matemática")
                self.assertContains(resposta, "Feriado X")
                self.assertNotContains(resposta, "Evento da outra turma")

    def test_evento_de_varios_dias_aparece_em_todos_eles(self):
        inicio = timezone.make_aware(datetime(2026, 10, 12, 8, 0))
        Evento.objects.create(titulo="Semana X", inicio=inicio, fim=inicio + timedelta(days=2))
        resultado = servicos.montar_calendario(self.turma, "mes", date(2026, 10, 1))
        dias = [
            dia["data"].day
            for semana in resultado["semanas"]
            for dia in semana
            if any(item["titulo"] == "Semana X" for item in dia["itens"])
        ]
        self.assertEqual(dias, [12, 13, 14])

    def test_titulo_da_semana_que_atravessa_o_mes(self):
        resultado = servicos.montar_calendario(self.turma, "semana", date(2026, 10, 30))
        self.assertEqual(resultado["titulo"], "26 de outubro a 1 de novembro de 2026")


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class FinanceiroTests(BaseAlunoMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.aluno)
        hoje = timezone.localdate()

        def parcela(matricula, numero, vencimento, paga_em=None):
            return Mensalidade.objects.create(
                matricula=matricula,
                competencia=date(2026, numero, 1),
                parcela=numero,
                total_parcelas=6,
                valor=Decimal("1480.00"),
                bolsa_percentual=20,
                vencimento=vencimento,
                paga_em=paga_em,
            )

        self.paga = parcela(self.matricula, 1, hoje - timedelta(days=40), hoje - timedelta(days=41))
        self.a_vencer = parcela(self.matricula, 2, hoje + timedelta(days=5))
        self.parcela = parcela
        parcela(self.outra_matricula, 3, hoje - timedelta(days=9))

    def test_situacao_depende_do_pagamento_e_da_data(self):
        self.assertEqual(self.paga.situacao, Mensalidade.PAGA)
        self.assertEqual(self.a_vencer.situacao, Mensalidade.A_VENCER)
        atrasada = self.parcela(self.matricula, 3, timezone.localdate() - timedelta(days=1))
        self.assertEqual(atrasada.situacao, Mensalidade.EM_ATRASO)

    def test_tela_mostra_apenas_as_parcelas_do_aluno(self):
        resposta = self.client.get(reverse("aluno:financeiro"))
        self.assertEqual(len(resposta.context["mensalidades"]), 2)
        self.assertEqual(resposta.context["proxima"], self.a_vencer)
        self.assertEqual(resposta.context["atrasadas"], 0)
        self.assertContains(resposta, "R$ 1.480,00")
        self.assertContains(resposta, "Tudo em dia")

    def test_parcela_atrasada_e_a_proxima_e_gera_aviso(self):
        atrasada = self.parcela(self.matricula, 3, timezone.localdate() - timedelta(days=1))
        resposta = self.client.get(reverse("aluno:financeiro"))
        self.assertEqual(resposta.context["proxima"], atrasada)
        self.assertContains(resposta, "Mensalidades em atraso: 1")
        self.assertNotContains(resposta, "Tudo em dia")

    def test_sem_parcelas_mostra_estado_vazio(self):
        Mensalidade.objects.all().delete()
        resposta = self.client.get(reverse("aluno:financeiro"))
        self.assertContains(resposta, "Nenhuma mensalidade cadastrada")
