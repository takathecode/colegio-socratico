"""Testes da área da coordenação: permissões, contas, CRUDs e cálculos da visão geral."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academico.calculos import EM_ATENCAO, EM_RISCO, REGULAR, resumo_das_matriculas
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

Usuario = get_user_model()

TELAS = ("painel", "alunos", "professores", "contas", "turmas", "disciplinas")
HASH_RAPIDO = ["django.contrib.auth.hashers.MD5PasswordHasher"]


class BaseCoordenacaoMixin:
    """Uma turma com duas disciplinas, um professor e dois alunos com notas e presenças."""

    @classmethod
    def setUpTestData(cls):
        cls.curso = Curso.objects.create(nome="Curso", total_creditos=200)
        cls.outro_curso = Curso.objects.create(nome="Outro curso", total_creditos=100)
        cls.turma = Turma.objects.create(
            curso=cls.curso, codigo="T1", semestre="2026.2", periodo=1
        )
        cls.turma_vazia = Turma.objects.create(
            curso=cls.curso, codigo="T2", semestre="2026.2", periodo=1
        )
        cls.matematica = Disciplina.objects.create(
            curso=cls.curso, codigo="MAT1", nome="Matemática", creditos=4, carga_horaria=40
        )
        cls.fisica = Disciplina.objects.create(
            curso=cls.curso, codigo="FIS1", nome="Física", creditos=4, carga_horaria=40
        )
        cls.coordenador = Usuario.objects.create_user(
            "coord", "senha", perfil="COORDENADOR", first_name="Lia", email="coord@x.com"
        )
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil="PROFESSOR", first_name="Ana", email="prof@x.com"
        )
        cls.oferta = Oferta.objects.create(
            turma=cls.turma, disciplina=cls.matematica, professor=cls.professor
        )
        cls.oferta_fisica = Oferta.objects.create(
            turma=cls.turma, disciplina=cls.fisica, professor=cls.professor
        )
        cls.aluno = Usuario.objects.create_user(
            "aluno", "senha", first_name="Bia", last_name="Reis", email="bia@x.com"
        )
        cls.aluno2 = Usuario.objects.create_user("aluno2", "senha", first_name="Caio")
        cls.matricula = Matricula.objects.create(aluno=cls.aluno, turma=cls.turma)
        cls.matricula2 = Matricula.objects.create(aluno=cls.aluno2, turma=cls.turma)

        # Bia: 9 em Matemática e 6,5 em Física (Em atenção). Caio: 4 em Matemática (Em risco).
        a1 = Avaliacao.objects.create(oferta=cls.oferta, nome="A1", data_hora=timezone.now())
        a1_fisica = Avaliacao.objects.create(
            oferta=cls.oferta_fisica, nome="A1", data_hora=timezone.now()
        )
        Nota.objects.create(avaliacao=a1, matricula=cls.matricula, valor=Decimal("9"))
        Nota.objects.create(avaliacao=a1_fisica, matricula=cls.matricula, valor=Decimal("6.5"))
        Nota.objects.create(avaliacao=a1, matricula=cls.matricula2, valor=Decimal("4"))

        aula = Aula.objects.create(
            oferta=cls.oferta, data=timezone.localdate() - timedelta(days=1), horas_aula=2
        )
        Frequencia.objects.create(aula=aula, matricula=cls.matricula, presente=True)
        Frequencia.objects.create(aula=aula, matricula=cls.matricula2, presente=False)

    def setUp(self):
        self.client.force_login(self.coordenador)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class PermissoesTests(BaseCoordenacaoMixin, TestCase):
    def test_coordenador_abre_todas_as_telas(self):
        for tela in TELAS:
            with self.subTest(tela=tela):
                self.assertEqual(self.client.get(reverse(f"coordenacao:{tela}")).status_code, 200)
        for rota, pk in (
            ("turma", self.turma.pk),
            ("aluno_editar", self.aluno.pk),
            ("professor_editar", self.professor.pk),
            ("oferta_editar", self.oferta.pk),
            ("disciplina_editar", self.matematica.pk),
        ):
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(f"coordenacao:{rota}", args=[pk]))
                self.assertEqual(resposta.status_code, 200)

    def test_aluno_e_professor_recebem_403(self):
        for usuario in (self.aluno, self.professor):
            self.client.force_login(usuario)
            for tela in TELAS:
                with self.subTest(usuario=usuario.matricula, tela=tela):
                    resposta = self.client.get(reverse(f"coordenacao:{tela}"))
                    self.assertEqual(resposta.status_code, 403)

    def test_visitante_vai_para_o_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("coordenacao:alunos"))
        self.assertRedirects(resposta, f"{reverse('contas:entrar')}?next=/coordenacao/alunos/")

    def test_rota_de_edicao_confere_o_perfil(self):
        # Um professor aberto na rota de aluno não existe para aquela tela.
        resposta = self.client.get(reverse("coordenacao:aluno_editar", args=[self.professor.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_conta_admin_nao_e_gerenciada(self):
        admin = Usuario.objects.create_superuser("admin", "senha", email="a@x.com")
        resposta = self.client.post(reverse("coordenacao:conta_alternar_ativa", args=[admin.pk]))
        self.assertEqual(resposta.status_code, 404)
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)


class ResumoDasMatriculasTests(BaseCoordenacaoMixin, TestCase):
    def test_pior_situacao_entre_as_disciplinas(self):
        resumo = resumo_das_matriculas([self.matricula, self.matricula2])
        bia, caio = resumo[self.matricula.pk], resumo[self.matricula2.pk]
        # Bia: Matemática Regular, Física Em atenção -> Em atenção. Média = (9 + 6,5) / 2.
        self.assertEqual(bia["situacao"], EM_ATENCAO)
        self.assertEqual(bia["media"], Decimal("7.75"))
        self.assertEqual(bia["frequencia"], Decimal("100.00"))
        self.assertEqual(caio["situacao"], EM_RISCO)
        self.assertEqual(caio["disciplinas_em_risco"], 1)
        self.assertEqual(caio["frequencia"], Decimal("0.00"))

    def test_sem_dados_nao_tem_situacao(self):
        novo = Usuario.objects.create_user("novo", "senha")
        matricula = Matricula.objects.create(aluno=novo, turma=self.turma_vazia)
        dados = resumo_das_matriculas([matricula])[matricula.pk]
        self.assertIsNone(dados["situacao"])
        self.assertIsNone(dados["media"])

    def test_lista_filtra_por_situacao(self):
        resposta = self.client.get(reverse("coordenacao:alunos"), {"situacao": EM_RISCO})
        nomes = [linha["aluno"].matricula for linha in resposta.context["pagina"]]
        self.assertEqual(nomes, ["aluno2"])
        resposta = self.client.get(reverse("coordenacao:alunos"), {"situacao": REGULAR})
        self.assertEqual(resposta.context["total"], 0)

    def test_painel_conta_alunos_em_risco(self):
        resposta = self.client.get(reverse("coordenacao:painel"))
        self.assertEqual(resposta.context["indicadores"]["risco"], 1)
        self.assertEqual(resposta.context["indicadores"]["alunos"], 2)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class ContasTests(BaseCoordenacaoMixin, TestCase):
    def dados_aluno(self, **extra):
        return {
            "matricula": "2026001",
            "first_name": "Davi",
            "last_name": "Souza",
            "email": "Davi@X.com",
            "turma": self.turma_vazia.pk,
            **extra,
        }

    def test_criar_aluno_cria_conta_e_matricula_e_mostra_a_senha_uma_vez(self):
        resposta = self.client.post(reverse("coordenacao:aluno_novo"), self.dados_aluno())
        # fetch_redirect_response=False: abrir a página agora tiraria a senha da sessão.
        self.assertRedirects(
            resposta, reverse("coordenacao:senha_provisoria"), fetch_redirect_response=False
        )

        aluno = Usuario.objects.get(matricula="2026001")
        self.assertEqual(aluno.perfil, Usuario.Perfil.ALUNO)
        self.assertEqual(aluno.email, "davi@x.com")
        self.assertEqual(aluno.matriculas.get().turma, self.turma_vazia)

        tela = self.client.get(reverse("coordenacao:senha_provisoria"))
        senha = tela.context["dados"]["senha"]
        self.assertTrue(aluno.check_password(senha))
        # Ao abrir de novo, a senha já saiu da sessão.
        self.assertRedirects(
            self.client.get(reverse("coordenacao:senha_provisoria")), reverse("coordenacao:contas")
        )

        # A conta nova consegue entrar com a senha provisória.
        self.client.logout()
        self.assertTrue(self.client.login(matricula="2026001", password=senha))

    def test_matricula_e_email_repetidos_sao_recusados(self):
        resposta = self.client.post(
            reverse("coordenacao:aluno_novo"),
            self.dados_aluno(matricula="aluno", email="BIA@x.com"),
        )
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context["form"]
        self.assertIn("Já existe uma conta com esta matrícula.", form.errors["matricula"])
        self.assertIn("Este e-mail já está em uso por outra conta.", form.errors["email"])

    def test_aluno_com_historico_nao_troca_de_turma(self):
        dados = self.dados_aluno(
            matricula="aluno", email="bia@x.com", turma=self.turma_vazia.pk, situacao="TRANCADA"
        )
        self.client.post(reverse("coordenacao:aluno_editar", args=[self.aluno.pk]), dados)
        self.matricula.refresh_from_db()
        self.assertEqual(self.matricula.turma, self.turma)  # campo travado: turma ignorada
        self.assertEqual(self.matricula.situacao, Matricula.Situacao.TRANCADA)

    def test_aluno_sem_historico_troca_de_turma(self):
        novo = Usuario.objects.create_user("novo", "senha", first_name="Eva", email="eva@x.com")
        matricula = Matricula.objects.create(aluno=novo, turma=self.turma)
        dados = self.dados_aluno(
            matricula="novo", email="eva@x.com", turma=self.turma_vazia.pk, situacao="ATIVA"
        )
        self.client.post(reverse("coordenacao:aluno_editar", args=[novo.pk]), dados)
        matricula.refresh_from_db()
        self.assertEqual(matricula.turma, self.turma_vazia)

    def test_criar_professor(self):
        resposta = self.client.post(
            reverse("coordenacao:professor_novo"),
            {
                "matricula": "prof9",
                "tratamento": "Profa.",
                "first_name": "Rita",
                "last_name": "Melo",
                "email": "rita@x.com",
            },
        )
        self.assertRedirects(resposta, reverse("coordenacao:senha_provisoria"))
        professor = Usuario.objects.get(matricula="prof9")
        self.assertEqual(professor.perfil, Usuario.Perfil.PROFESSOR)
        self.assertEqual(professor.nome_com_tratamento, "Profa. Rita Melo")

    def test_desativar_e_reativar_conta(self):
        url = reverse("coordenacao:conta_alternar_ativa", args=[self.aluno.pk])
        self.client.post(url)
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.is_active)
        self.client.post(url)
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.is_active)

    def test_nao_desativa_a_propria_conta(self):
        self.client.post(reverse("coordenacao:conta_alternar_ativa", args=[self.coordenador.pk]))
        self.coordenador.refresh_from_db()
        self.assertTrue(self.coordenador.is_active)

    def test_acoes_de_conta_so_aceitam_post(self):
        for rota in ("conta_alternar_ativa", "conta_nova_senha"):
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(f"coordenacao:{rota}", args=[self.aluno.pk]))
                self.assertEqual(resposta.status_code, 405)

    def test_nova_senha_troca_a_senha(self):
        self.client.post(reverse("coordenacao:conta_nova_senha", args=[self.aluno.pk]))
        senha = self.client.get(reverse("coordenacao:senha_provisoria")).context["dados"]["senha"]
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.check_password("senha"))
        self.assertTrue(self.aluno.check_password(senha))

    def test_proxima_externa_e_ignorada(self):
        resposta = self.client.post(
            reverse("coordenacao:conta_alternar_ativa", args=[self.aluno.pk]),
            {"proxima": "https://site-malicioso.example/"},
        )
        self.assertRedirects(resposta, reverse("coordenacao:contas"))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class TurmasEDisciplinasTests(BaseCoordenacaoMixin, TestCase):
    def test_criar_turma_e_recusar_codigo_repetido_no_semestre(self):
        dados = {"curso": self.curso.pk, "codigo": "T3", "semestre": "2026.2", "periodo": 2}
        resposta = self.client.post(reverse("coordenacao:turma_nova"), dados)
        turma = Turma.objects.get(codigo="T3")
        self.assertRedirects(resposta, reverse("coordenacao:turma", args=[turma.pk]))

        resposta = self.client.post(reverse("coordenacao:turma_nova"), dados)
        self.assertIn(
            "Já existe a turma T3 no semestre 2026.2.", resposta.context["form"].errors["codigo"]
        )

    def test_adicionar_disciplina_e_professor_na_turma(self):
        resposta = self.client.post(
            reverse("coordenacao:turma", args=[self.turma_vazia.pk]),
            {"disciplina": self.matematica.pk, "professor": self.professor.pk},
        )
        self.assertRedirects(resposta, reverse("coordenacao:turma", args=[self.turma_vazia.pk]))
        self.assertTrue(
            Oferta.objects.filter(turma=self.turma_vazia, disciplina=self.matematica).exists()
        )

    def test_disciplina_de_outro_curso_nao_pode_ser_oferecida(self):
        quimica = Disciplina.objects.create(
            curso=self.outro_curso, codigo="QUI1", nome="Química", creditos=2, carga_horaria=20
        )
        resposta = self.client.post(
            reverse("coordenacao:turma", args=[self.turma_vazia.pk]),
            {"disciplina": quimica.pk, "professor": self.professor.pk},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("disciplina", resposta.context["form"].errors)

    def test_trocar_professor_da_oferta(self):
        novo = Usuario.objects.create_user("prof2", "senha", perfil="PROFESSOR")
        self.client.post(
            reverse("coordenacao:oferta_editar", args=[self.oferta.pk]), {"professor": novo.pk}
        )
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.professor, novo)

    def test_turma_com_registros_nao_e_excluida(self):
        resposta = self.client.post(reverse("coordenacao:turma_excluir", args=[self.turma.pk]))
        self.assertRedirects(resposta, reverse("coordenacao:turma", args=[self.turma.pk]))
        self.assertTrue(Turma.objects.filter(pk=self.turma.pk).exists())

    def test_turma_vazia_e_excluida(self):
        url = reverse("coordenacao:turma_excluir", args=[self.turma_vazia.pk])
        self.assertEqual(self.client.get(url).status_code, 200)  # tela de confirmação
        self.assertRedirects(self.client.post(url), reverse("coordenacao:turmas"))
        self.assertFalse(Turma.objects.filter(pk=self.turma_vazia.pk).exists())

    def test_disciplina_crud(self):
        dados = {
            "curso": self.curso.pk,
            "codigo": "HIS1",
            "nome": "História",
            "creditos": 2,
            "carga_horaria": 30,
        }
        self.client.post(reverse("coordenacao:disciplina_nova"), dados)
        historia = Disciplina.objects.get(codigo="HIS1")

        self.client.post(
            reverse("coordenacao:disciplina_editar", args=[historia.pk]),
            {**dados, "nome": "História da Ciência"},
        )
        historia.refresh_from_db()
        self.assertEqual(historia.nome, "História da Ciência")

        self.client.post(reverse("coordenacao:disciplina_excluir", args=[historia.pk]))
        self.assertFalse(Disciplina.objects.filter(pk=historia.pk).exists())

    def test_disciplina_oferecida_nao_troca_de_curso(self):
        resposta = self.client.post(
            reverse("coordenacao:disciplina_editar", args=[self.matematica.pk]),
            {
                "curso": self.outro_curso.pk,
                "codigo": "MAT1",
                "nome": "Matemática",
                "creditos": 4,
                "carga_horaria": 40,
            },
        )
        self.assertIn("curso", resposta.context["form"].errors)
        self.matematica.refresh_from_db()
        self.assertEqual(self.matematica.curso, self.curso)
