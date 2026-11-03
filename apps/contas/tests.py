from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

Usuario = get_user_model()


class UsuarioModelTests(TestCase):
    def test_modelo_de_usuario_do_projeto(self):
        self.assertEqual(Usuario._meta.label, "contas.Usuario")
        self.assertEqual(Usuario.USERNAME_FIELD, "matricula")
        # O campo username herdado do Django foi removido de propósito.
        self.assertNotIn("username", [campo.name for campo in Usuario._meta.get_fields()])

    def test_create_user_guarda_senha_com_hash_e_perfil_padrao(self):
        usuario = Usuario.objects.create_user(matricula="202410284", password="senha-teste")
        self.assertEqual(usuario.perfil, Usuario.Perfil.ALUNO)
        self.assertNotEqual(usuario.password, "senha-teste")
        self.assertTrue(usuario.check_password("senha-teste"))
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)

    def test_create_user_exige_matricula(self):
        with self.assertRaises(ValueError):
            Usuario.objects.create_user(matricula="", password="senha-teste")

    def test_matricula_nao_pode_repetir(self):
        Usuario.objects.create_user(matricula="aluno01", password="senha-teste")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user(matricula="aluno01", password="outra-senha")

    def test_superusuario_sempre_tem_perfil_admin(self):
        admin = Usuario.objects.create_superuser(
            matricula="admin01",
            password="senha-teste",
            email="admin@exemplo.com",
            perfil=Usuario.Perfil.ALUNO,  # deve ser ignorado
        )
        self.assertEqual(admin.perfil, Usuario.Perfil.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_str_mostra_matricula_e_nome(self):
        sem_nome = Usuario(matricula="aluno01")
        com_nome = Usuario(matricula="aluno02", first_name="Maria", last_name="Alves")
        self.assertEqual(str(sem_nome), "aluno01")
        self.assertEqual(str(com_nome), "aluno02 - Maria Alves")


class UsuarioAdminTests(TestCase):
    """O Admin padrão espera um campo username; estes testes garantem a adaptação."""

    def setUp(self):
        self.admin = Usuario.objects.create_superuser(
            matricula="admin01", password="senha-teste", email="admin@exemplo.com"
        )

    def test_login_por_matricula_e_senha(self):
        self.assertTrue(self.client.login(matricula="admin01", password="senha-teste"))
        self.assertFalse(self.client.login(matricula="admin01", password="senha-errada"))

    def test_telas_de_usuario_abrem(self):
        self.client.force_login(self.admin)
        for url in (
            reverse("admin:contas_usuario_changelist"),
            reverse("admin:contas_usuario_add"),
            reverse("admin:contas_usuario_change", args=[self.admin.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_cria_conta_de_professor(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("admin:contas_usuario_add"),
            {
                "matricula": "prof01",
                "first_name": "Ricardo",
                "last_name": "Almeida",
                "email": "ricardo@exemplo.com",
                "perfil": Usuario.Perfil.PROFESSOR,
                "usable_password": "true",
                "password1": "Senha-Forte-2026",
                "password2": "Senha-Forte-2026",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        professor = Usuario.objects.get(matricula="prof01")
        self.assertEqual(professor.perfil, Usuario.Perfil.PROFESSOR)
        self.assertTrue(professor.check_password("Senha-Forte-2026"))
