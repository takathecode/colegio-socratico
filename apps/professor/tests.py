"""Testes da área do professor: permissões, notas, chamada e justificativas."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academico.calculos import EM_RISCO, indicadores_da_turma, resumo_da_oferta
from apps.academico.models import (
    Aula,
    Avaliacao,
    Curso,
    Disciplina,
    Frequencia,
    Justificativa,
    Matricula,
    Nota,
    Oferta,
    Turma,
)

Usuario = get_user_model()

TELAS = ("painel", "turmas", "notas", "chamada", "justificativas")
HASH_RAPIDO = ["django.contrib.auth.hashers.MD5PasswordHasher"]


class BaseProfessorMixin:
    """Dois professores, cada um com a sua disciplina na mesma turma."""

    @classmethod
    def setUpTestData(cls):
        curso = Curso.objects.create(nome="Curso", total_creditos=200)
        cls.turma = Turma.objects.create(curso=curso, codigo="T1", semestre="2026.2", periodo=1)
        matematica = Disciplina.objects.create(
            curso=curso, codigo="MAT1", nome="Matemática", creditos=4, carga_horaria=40
        )
        fisica = Disciplina.objects.create(
            curso=curso, codigo="FIS1", nome="Física", creditos=4, carga_horaria=40
        )
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil="PROFESSOR", first_name="Ana", last_name="Dias"
        )
        cls.outro_professor = Usuario.objects.create_user(
            "prof2", "senha", perfil="PROFESSOR", first_name="Rui"
        )
        cls.oferta = Oferta.objects.create(
            turma=cls.turma, disciplina=matematica, professor=cls.professor
        )
        cls.oferta_do_outro = Oferta.objects.create(
            turma=cls.turma, disciplina=fisica, professor=cls.outro_professor
        )
        cls.aluno = Usuario.objects.create_user("aluno", "senha", first_name="Bia", last_name="Reis")
        cls.aluno2 = Usuario.objects.create_user("aluno2", "senha", first_name="Caio", last_name="Lima")
        cls.matricula = Matricula.objects.create(aluno=cls.aluno, turma=cls.turma)
        cls.matricula2 = Matricula.objects.create(aluno=cls.aluno2, turma=cls.turma)

        cls.avaliacao = Avaliacao.objects.create(
            oferta=cls.oferta, nome="A1", data_hora=timezone.now() - timedelta(days=5)
        )
        Nota.objects.create(avaliacao=cls.avaliacao, matricula=cls.matricula, valor=Decimal("8"))
        Nota.objects.create(avaliacao=cls.avaliacao, matricula=cls.matricula2, valor=Decimal("4"))

        ontem = timezone.localdate() - timedelta(days=1)
        cls.aula = Aula.objects.create(oferta=cls.oferta, data=ontem, horas_aula=2)
        Frequencia.objects.create(aula=cls.aula, matricula=cls.matricula, presente=True)
        cls.falta = Frequencia.objects.create(
            aula=cls.aula, matricula=cls.matricula2, presente=False
        )
        cls.justificativa = Justificativa.objects.create(
            frequencia=cls.falta, motivo="Consulta médica."
        )

        # Uma falta na disciplina do outro professor, com justificativa.
        aula_do_outro = Aula.objects.create(oferta=cls.oferta_do_outro, data=ontem, horas_aula=2)
        falta_do_outro = Frequencia.objects.create(
            aula=aula_do_outro, matricula=cls.matricula, presente=False
        )
        cls.justificativa_do_outro = Justificativa.objects.create(
            frequencia=falta_do_outro, motivo="Doença."
        )


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class PermissoesTests(BaseProfessorMixin, TestCase):
    def test_visitante_vai_para_o_login(self):
        for tela in TELAS:
            with self.subTest(tela=tela):
                resposta = self.client.get(reverse(f"professor:{tela}"))
                self.assertEqual(resposta.status_code, 302)
                self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_aluno_e_coordenador_recebem_403(self):
        coordenador = Usuario.objects.create_user("coord", "senha", perfil="COORDENADOR")
        for usuario in (self.aluno, coordenador):
            self.client.force_login(usuario)
            for tela in TELAS:
                with self.subTest(usuario=usuario.matricula, tela=tela):
                    self.assertEqual(
                        self.client.get(reverse(f"professor:{tela}")).status_code, 403
                    )

    def test_professor_abre_todas_as_telas(self):
        self.client.force_login(self.professor)
        for tela in TELAS:
            with self.subTest(tela=tela):
                self.assertEqual(self.client.get(reverse(f"professor:{tela}")).status_code, 200)
        resposta = self.client.get(reverse("professor:turma", args=[self.oferta.pk]))
        self.assertEqual(resposta.status_code, 200)

    def test_disciplina_de_outro_professor_da_404(self):
        self.client.force_login(self.professor)
        outra = self.oferta_do_outro.pk
        self.assertEqual(
            self.client.get(reverse("professor:turma", args=[outra])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("professor:notas"), {"oferta": outra}).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("professor:chamada"), {"oferta": outra}).status_code, 404
        )

    def test_nao_avalia_nem_baixa_justificativa_de_outra_disciplina(self):
        self.client.force_login(self.professor)
        pk = self.justificativa_do_outro.pk
        resposta = self.client.post(
            reverse("professor:avaliar_justificativa", args=[pk]),
            {f"j{pk}-decisao": "APROVADA"},
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(
            self.client.get(reverse("professor:anexo_justificativa", args=[pk])).status_code, 404
        )
        self.justificativa_do_outro.refresh_from_db()
        self.assertEqual(self.justificativa_do_outro.status, Justificativa.Status.PENDENTE)

    def test_lista_so_mostra_justificativas_das_proprias_disciplinas(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("professor:justificativas"))
        self.assertEqual(list(resposta.context["lista"]), [self.justificativa])

    def test_professor_sem_disciplina_ve_aviso(self):
        novo = Usuario.objects.create_user("prof3", "senha", perfil="PROFESSOR")
        self.client.force_login(novo)
        for tela in ("notas", "chamada"):
            with self.subTest(tela=tela):
                self.assertContains(
                    self.client.get(reverse(f"professor:{tela}")),
                    "ainda não leciona nenhuma disciplina",
                )


class CalculosDaTurmaTests(BaseProfessorMixin, TestCase):
    def test_resumo_da_oferta_usa_as_regras_do_boletim(self):
        avaliacoes, linhas = resumo_da_oferta(self.oferta)
        self.assertEqual(avaliacoes, [self.avaliacao])
        por_aluno = {linha["matricula"]: linha for linha in linhas}
        self.assertEqual(por_aluno[self.matricula]["media"], Decimal("8.00"))
        self.assertEqual(por_aluno[self.matricula]["frequencia"], Decimal("100.00"))
        # Média 4 e frequência 0%: em risco.
        self.assertEqual(por_aluno[self.matricula2]["situacao"], EM_RISCO)

        indicadores = indicadores_da_turma(linhas)
        self.assertEqual(indicadores["alunos"], 2)
        self.assertEqual(indicadores["media"], Decimal("6.00"))
        self.assertEqual(indicadores["risco"], 1)

    def test_aluno_trancado_fica_fora_da_turma(self):
        self.matricula2.situacao = Matricula.Situacao.TRANCADA
        self.matricula2.save()
        _avaliacoes, linhas = resumo_da_oferta(self.oferta)
        self.assertEqual([linha["matricula"] for linha in linhas], [self.matricula])


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class NotasTests(BaseProfessorMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.professor)
        self.url = (
            f"{reverse('professor:notas')}?oferta={self.oferta.pk}&avaliacao={self.avaliacao.pk}"
        )

    def enviar(self, nota1, nota2):
        return self.client.post(
            self.url,
            {
                "acao": "salvar_notas",
                f"nota_{self.matricula.pk}": nota1,
                f"nota_{self.matricula2.pk}": nota2,
            },
        )

    def test_salva_nota_com_virgula_e_apaga_campo_vazio(self):
        resposta = self.enviar("9,5", "")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            Nota.objects.get(avaliacao=self.avaliacao, matricula=self.matricula).valor,
            Decimal("9.5"),
        )
        self.assertFalse(
            Nota.objects.filter(avaliacao=self.avaliacao, matricula=self.matricula2).exists()
        )

    def test_nota_fora_de_0_a_10_nao_salva_nada(self):
        resposta = self.enviar("7", "11")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "A nota vai de 0 a 10.")
        # Nenhuma nota mudou, nem a que estava certa.
        self.assertEqual(
            Nota.objects.get(avaliacao=self.avaliacao, matricula=self.matricula).valor,
            Decimal("8"),
        )

    def test_cria_avaliacao_na_propria_disciplina(self):
        quando = (timezone.localtime() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        resposta = self.client.post(
            f"{reverse('professor:notas')}?oferta={self.oferta.pk}",
            {"acao": "nova_avaliacao", "nome": "A2", "tipo": "PROVA", "data_hora": quando},
        )
        nova = Avaliacao.objects.get(oferta=self.oferta, nome="A2")
        self.assertRedirects(
            resposta,
            f"{reverse('professor:notas')}?oferta={self.oferta.pk}&avaliacao={nova.pk}",
            fetch_redirect_response=False,
        )

    def test_nao_repete_nome_de_avaliacao(self):
        resposta = self.client.post(
            f"{reverse('professor:notas')}?oferta={self.oferta.pk}",
            {
                "acao": "nova_avaliacao",
                "nome": "a1",
                "tipo": "PROVA",
                "data_hora": "2026-12-01T10:00",
            },
        )
        self.assertContains(resposta, "Já existe uma avaliação com este nome")
        self.assertEqual(Avaliacao.objects.filter(oferta=self.oferta).count(), 1)

    def test_avaliacao_de_outra_disciplina_da_404(self):
        de_outro = Avaliacao.objects.create(
            oferta=self.oferta_do_outro, nome="P1", data_hora=timezone.now()
        )
        resposta = self.client.get(
            reverse("professor:notas"), {"oferta": self.oferta.pk, "avaliacao": de_outro.pk}
        )
        self.assertEqual(resposta.status_code, 404)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class ChamadaTests(BaseProfessorMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.professor)

    def dados(self, data, **extras):
        return {
            "oferta": self.oferta.pk,
            "data_aula": data.isoformat(),
            "horas_aula": 2,
            "conteudo": "Revisão",
            **extras,
        }

    def test_cria_aula_e_presencas(self):
        hoje = timezone.localdate()
        resposta = self.client.post(
            reverse("professor:chamada"),
            self.dados(
                hoje,
                **{
                    f"presenca_{self.matricula.pk}": "presente",
                    f"metodo_{self.matricula.pk}": "BIOMETRIA",
                    f"presenca_{self.matricula2.pk}": "falta",
                    f"metodo_{self.matricula2.pk}": "BIOMETRIA",
                },
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        aula = Aula.objects.get(oferta=self.oferta, data=hoje)
        self.assertEqual(aula.conteudo, "Revisão")
        presenca = Frequencia.objects.get(aula=aula, matricula=self.matricula)
        falta = Frequencia.objects.get(aula=aula, matricula=self.matricula2)
        self.assertTrue(presenca.presente)
        self.assertEqual(presenca.metodo, Frequencia.Metodo.BIOMETRIA)
        self.assertFalse(falta.presente)
        # Falta nunca é registrada como biometria.
        self.assertEqual(falta.metodo, Frequencia.Metodo.MANUAL)

    def test_exige_marcacao_de_todos(self):
        hoje = timezone.localdate()
        resposta = self.client.post(
            reverse("professor:chamada"),
            self.dados(hoje, **{f"presenca_{self.matricula.pk}": "presente"}),
        )
        self.assertContains(resposta, "Marque presença ou falta para todos")
        self.assertFalse(Aula.objects.filter(oferta=self.oferta, data=hoje).exists())

    def test_recusa_data_futura(self):
        amanha = timezone.localdate() + timedelta(days=1)
        resposta = self.client.post(
            reverse("professor:chamada"),
            self.dados(
                amanha,
                **{
                    f"presenca_{self.matricula.pk}": "presente",
                    f"presenca_{self.matricula2.pk}": "presente",
                },
            ),
        )
        self.assertContains(resposta, "aula futura")
        self.assertFalse(Aula.objects.filter(oferta=self.oferta, data=amanha).exists())

    def test_falta_justificada_nao_muda(self):
        """Mesmo que o formulário peça "presente", a falta com justificativa é mantida."""
        resposta = self.client.post(
            reverse("professor:chamada") + f"?data={self.aula.data.isoformat()}",
            self.dados(
                self.aula.data,
                **{
                    f"presenca_{self.matricula.pk}": "falta",
                    f"presenca_{self.matricula2.pk}": "presente",
                },
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        self.falta.refresh_from_db()
        self.assertFalse(self.falta.presente)
        corrigida = Frequencia.objects.get(aula=self.aula, matricula=self.matricula)
        self.assertFalse(corrigida.presente)

    def test_chamada_existente_abre_marcada(self):
        resposta = self.client.get(
            reverse("professor:chamada"),
            {"oferta": self.oferta.pk, "data": self.aula.data.isoformat()},
        )
        self.assertEqual(resposta.context["aula"], self.aula)
        travadas = [linha["travada"] for linha in resposta.context["linhas"]]
        self.assertEqual(travadas, [False, True])


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class JustificativasTests(BaseProfessorMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.professor)
        self.url = reverse("professor:avaliar_justificativa", args=[self.justificativa.pk])
        self.prefixo = f"j{self.justificativa.pk}"

    def test_aprova_sem_mudar_a_frequencia(self):
        resposta = self.client.post(self.url, {f"{self.prefixo}-decisao": "APROVADA"})
        self.assertRedirects(resposta, reverse("professor:justificativas"))
        self.justificativa.refresh_from_db()
        self.assertEqual(self.justificativa.status, Justificativa.Status.APROVADA)
        self.assertEqual(self.justificativa.avaliada_por, self.professor)
        self.assertIsNotNone(self.justificativa.avaliada_em)
        self.falta.refresh_from_db()
        self.assertFalse(self.falta.presente)

    def test_rejeitar_exige_resposta(self):
        resposta = self.client.post(self.url, {f"{self.prefixo}-decisao": "REJEITADA"})
        self.assertContains(resposta, "Explique ao aluno o motivo da rejeição.")
        self.justificativa.refresh_from_db()
        self.assertEqual(self.justificativa.status, Justificativa.Status.PENDENTE)

        self.client.post(
            self.url,
            {f"{self.prefixo}-decisao": "REJEITADA", f"{self.prefixo}-resposta": "Sem atestado."},
        )
        self.justificativa.refresh_from_db()
        self.assertEqual(self.justificativa.status, Justificativa.Status.REJEITADA)
        self.assertEqual(self.justificativa.resposta, "Sem atestado.")

    def test_nao_avalia_duas_vezes(self):
        self.client.post(self.url, {f"{self.prefixo}-decisao": "APROVADA"})
        self.client.post(
            self.url,
            {f"{self.prefixo}-decisao": "REJEITADA", f"{self.prefixo}-resposta": "Mudei de ideia."},
        )
        self.justificativa.refresh_from_db()
        self.assertEqual(self.justificativa.status, Justificativa.Status.APROVADA)
