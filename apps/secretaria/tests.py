"""Testes da área da Secretaria: contas, senhas, bloqueios, auditoria e limites de privilégio."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contas.models import BloqueioDeLogin, RegistroDeAuditoria

Usuario = get_user_model()
Acao = RegistroDeAuditoria.Acao
HASH_RAPIDO = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SENHA = "Senha-Atual#2026"
IDENTIDADE = {"identidade": "conferida"}


class BaseSecretariaMixin:
    @classmethod
    def setUpTestData(cls):
        cls.secretaria = Usuario.objects.create_user(
            "secr01", SENHA, perfil="SECRETARIA", first_name="Sônia", email="secr@exemplo.com"
        )
        cls.aluno = Usuario.objects.create_user(
            "aluno01", SENHA, first_name="Bia", last_name="Reis", email="bia@exemplo.com"
        )
        cls.professor = Usuario.objects.create_user(
            "prof01", SENHA, perfil="PROFESSOR", first_name="Ana", email="ana@exemplo.com"
        )
        cls.coordenador = Usuario.objects.create_user(
            "coord01", SENHA, perfil="COORDENADOR", first_name="Lia", email="lia@exemplo.com"
        )

    def setUp(self):
        self.client.force_login(self.secretaria)

    def url(self, nome, conta):
        return reverse(f"secretaria:{nome}", args=[conta.pk])

    def acoes_de(self, conta):
        return list(RegistroDeAuditoria.objects.filter(conta=conta).values_list("acao", flat=True))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class TelasTests(BaseSecretariaMixin, TestCase):
    def test_telas_abrem(self):
        for url in (
            reverse("secretaria:painel"),
            reverse("secretaria:contas"),
            self.url("conta", self.aluno),
            self.url("conta_editar", self.professor),
            reverse("secretaria:conta_nova", args=["aluno"]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_tipo_de_conta_desconhecido_da_404(self):
        self.assertEqual(self.client.get(reverse("secretaria:conta_nova", args=["admin"])).status_code, 404)

    def test_coordenacao_e_aluno_recebem_403(self):
        for usuario in (self.coordenador, self.aluno):
            with self.subTest(usuario=usuario.matricula):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(reverse("secretaria:contas")).status_code, 403)

    def test_filtros_da_lista(self):
        Usuario.objects.filter(pk=self.professor.pk).update(is_active=False)
        BloqueioDeLogin.objects.create(
            matricula="aluno01", bloqueado_ate=timezone.now() + timedelta(minutes=10)
        )
        Usuario.objects.filter(pk=self.coordenador.pk).update(precisa_trocar_senha=True)
        contas = lambda **filtro: {
            c.matricula for c in self.client.get(reverse("secretaria:contas"), filtro).context["pagina"]
        }
        self.assertEqual(contas(), {"aluno01", "prof01", "coord01"})
        self.assertEqual(contas(perfil="PROFESSOR"), {"prof01"})
        self.assertEqual(contas(estado="inativas"), {"prof01"})
        self.assertEqual(contas(estado="ativas"), {"aluno01", "coord01"})
        self.assertEqual(contas(estado="bloqueadas"), {"aluno01"})
        self.assertEqual(contas(estado="troca"), {"coord01"})
        self.assertEqual(contas(busca="reis"), {"aluno01"})
        self.assertEqual(contas(busca="coord"), {"coord01"})

    def test_aviso_de_identidade_antes_de_redefinir(self):
        tela = self.client.get(self.url("conta", self.aluno))
        self.assertContains(tela, "Confirme a identidade da pessoa com documento com foto antes de redefinir.")
        self.assertContains(tela, "Enviar link de redefinição")
        self.assertContains(tela, "Gerar senha provisória")

    def test_secretaria_nao_ve_dados_academicos(self):
        for url in ("/coordenacao/", "/relatorios/", "/aluno/financeiro/", "/professor/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class EscaladaDePrivilegioTests(BaseSecretariaMixin, TestCase):
    """Admin, superusuário, staff e outra Secretaria ficam fora do alcance, no servidor."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.protegidas = [
            Usuario.objects.create_superuser("admin01", SENHA, email="admin@exemplo.com"),
            Usuario.objects.create_user("secr02", SENHA, perfil="SECRETARIA", email="s2@exemplo.com"),
            # Um coordenador com acesso ao Django Admin (staff) também é protegido.
            Usuario.objects.create_user(
                "staff01", SENHA, perfil="COORDENADOR", is_staff=True, email="staff@exemplo.com"
            ),
            Usuario.objects.create_user(
                "super01", SENHA, perfil="PROFESSOR", is_superuser=True, email="su@exemplo.com"
            ),
        ]

    def test_contas_protegidas_nao_aparecem_na_lista(self):
        lista = {c.matricula for c in self.client.get(reverse("secretaria:contas")).context["pagina"]}
        self.assertEqual(lista, {"aluno01", "prof01", "coord01"})

    def test_todas_as_acoes_dao_404_e_nada_muda(self):
        for conta in [*self.protegidas, self.secretaria]:
            hash_antes = conta.password
            for nome, metodo, dados in (
                ("conta", "get", {}),
                ("conta_editar", "get", {}),
                ("conta_editar", "post", {"first_name": "X", "last_name": "Y", "email": "x@exemplo.com"}),
                ("conta_redefinir", "post", {"acao": "provisoria", **IDENTIDADE}),
                ("conta_redefinir", "post", {"acao": "link", **IDENTIDADE}),
                ("conta_desbloquear", "post", {}),
                ("conta_alternar_ativa", "post", {}),
            ):
                with self.subTest(conta=conta.matricula, rota=nome, metodo=metodo):
                    resposta = getattr(self.client, metodo)(self.url(nome, conta), dados)
                    self.assertEqual(resposta.status_code, 404)
            conta.refresh_from_db()
            self.assertEqual(conta.password, hash_antes)
            self.assertTrue(conta.is_active)
            self.assertFalse(conta.precisa_trocar_senha)
            self.assertNotEqual(conta.first_name, "X")
        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroDeAuditoria.objects.exists())

    def test_criar_conta_ignora_perfil_e_admin_enviados(self):
        self.client.post(
            reverse("secretaria:conta_nova", args=["aluno"]),
            {
                "matricula": "2026001",
                "first_name": "Davi",
                "last_name": "Souza",
                "email": "davi@exemplo.com",
                "perfil": "ADMIN",
                "is_staff": "on",
                "is_superuser": "on",
            },
        )
        conta = Usuario.objects.get(matricula="2026001")
        self.assertEqual(conta.perfil, Usuario.Perfil.ALUNO)
        self.assertFalse(conta.is_staff)
        self.assertFalse(conta.is_superuser)

    def test_editar_nao_muda_matricula_nem_perfil(self):
        self.client.post(
            self.url("conta_editar", self.aluno),
            {
                "first_name": "Bia",
                "last_name": "Reis",
                "email": "bia@exemplo.com",
                "matricula": "admin01",
                "perfil": "SECRETARIA",
            },
        )
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.matricula, "aluno01")
        self.assertEqual(self.aluno.perfil, Usuario.Perfil.ALUNO)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class CriarContaTests(BaseSecretariaMixin, TestCase):
    def criar(self, tipo="aluno", **dados):
        padrao = {"matricula": "2026001", "first_name": "Davi", "last_name": "Souza", "email": "Davi@Exemplo.com"}
        return self.client.post(reverse("secretaria:conta_nova", args=[tipo]), {**padrao, **dados})

    def test_cria_a_conta_e_mostra_a_senha_uma_vez(self):
        resposta = self.criar()
        self.assertRedirects(resposta, reverse("secretaria:senha_provisoria"), fetch_redirect_response=False)
        conta = Usuario.objects.get(matricula="2026001")
        self.assertEqual(conta.email, "davi@exemplo.com")
        self.assertTrue(conta.precisa_trocar_senha)
        self.assertFalse(conta.matriculas.exists())  # a matrícula na turma é da coordenação

        tela = self.client.get(reverse("secretaria:senha_provisoria"))
        senha = tela.context["dados"]["senha"]
        self.assertTrue(conta.check_password(senha))
        self.assertRedirects(
            self.client.get(reverse("secretaria:senha_provisoria")), reverse("secretaria:contas")
        )
        self.assertEqual(sorted(self.acoes_de(conta)), sorted([Acao.CONTA_CRIADA, Acao.SENHA_PROVISORIA]))

        # No primeiro login, a pessoa é levada a criar a própria senha.
        self.client.logout()
        self.assertTrue(self.client.login(matricula="2026001", password=senha))
        self.assertRedirects(self.client.get("/aluno/"), reverse("contas:senha_alterar"))

    def test_cria_professor_e_coordenacao(self):
        self.criar("professor", tratamento="Profa.", matricula="prof9", email="rita@exemplo.com")
        self.criar("coordenacao", matricula="coord9", email="coord9@exemplo.com")
        self.assertEqual(Usuario.objects.get(matricula="prof9").perfil, Usuario.Perfil.PROFESSOR)
        self.assertEqual(Usuario.objects.get(matricula="coord9").perfil, Usuario.Perfil.COORDENADOR)

    def test_email_obrigatorio_valido_e_unico_entre_as_ativas(self):
        for email, erro in (
            ("", "Este campo é obrigatório."),
            ("nao-e-email", "Digite um e-mail válido"),
            ("BIA@exemplo.com", "Este e-mail já está em uso por outra conta ativa."),
        ):
            with self.subTest(email=email):
                resposta = self.criar(email=email)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn(erro, " ".join(resposta.context["form"].errors["email"]))
        self.assertFalse(Usuario.objects.filter(matricula="2026001").exists())

    def test_email_de_conta_desativada_pode_ser_reaproveitado(self):
        Usuario.objects.filter(pk=self.aluno.pk).update(is_active=False)
        self.criar(email="bia@exemplo.com")
        self.assertTrue(Usuario.objects.filter(matricula="2026001").exists())

    def test_matricula_repetida(self):
        resposta = self.criar(matricula="aluno01", email="outro@exemplo.com")
        self.assertIn("Já existe uma conta com esta matrícula.", resposta.context["form"].errors["matricula"])


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class EditarContaTests(BaseSecretariaMixin, TestCase):
    def editar(self, conta, **dados):
        padrao = {"first_name": conta.first_name, "last_name": conta.last_name or "Silva", "email": conta.email}
        if conta.perfil == "PROFESSOR":
            padrao["tratamento"] = "Profa."
        return self.client.post(self.url("conta_editar", conta), {**padrao, **dados})

    def test_trocar_email_registra_e_avisa_o_endereco_antigo(self):
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.editar(self.aluno, email="bia.nova@exemplo.com")
        self.assertRedirects(resposta, self.url("conta", self.aluno))
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.email, "bia.nova@exemplo.com")

        registro = RegistroDeAuditoria.objects.get(conta=self.aluno, acao=Acao.EMAIL_ALTERADO)
        self.assertEqual(registro.autor, self.secretaria)
        self.assertEqual(registro.ip, "127.0.0.1")
        self.assertEqual(registro.detalhe, "De b*a@e******.com para b******a@e******.com")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bia@exemplo.com"])  # o endereço ANTIGO
        self.assertIn("foi trocado pela Secretaria", mail.outbox[0].body)
        self.assertNotIn("bia.nova@exemplo.com", mail.outbox[0].body)

    def test_sem_trocar_o_email_nao_avisa(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.editar(self.aluno, first_name="Beatriz")
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.acoes_de(self.aluno), [Acao.DADOS_ALTERADOS])

    def test_trocar_o_email_invalida_o_link_antigo(self):
        from apps.contas.tokens import gerador_de_link

        self.aluno.ultimo_pedido_reset = timezone.now()
        self.aluno.save()
        codigo = gerador_de_link.make_token(self.aluno)
        self.editar(self.aluno, email="bia.nova@exemplo.com")
        self.aluno.refresh_from_db()
        self.assertFalse(gerador_de_link.check_token(self.aluno, codigo))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class RedefinirSenhaTests(BaseSecretariaMixin, TestCase):
    def redefinir(self, conta, acao, follow=False):
        dados = {"acao": acao, **IDENTIDADE}
        return self.client.post(self.url("conta_redefinir", conta), dados, follow=follow)

    def test_so_aceita_post(self):
        self.assertEqual(self.client.get(self.url("conta_redefinir", self.aluno)).status_code, 405)

    def test_exige_conferir_a_identidade(self):
        resposta = self.client.post(self.url("conta_redefinir", self.aluno), {"acao": "provisoria"}, follow=True)
        self.assertContains(resposta, "Confirme a identidade da pessoa")
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.check_password(SENHA))
        self.assertEqual(self.acoes_de(self.aluno), [])

    def test_enviar_link(self):
        resposta = self.redefinir(self.professor, "link", follow=True)
        self.assertContains(resposta, "Link enviado para a*a@e******.com")
        self.assertEqual(mail.outbox[0].to, ["ana@exemplo.com"])
        self.assertIn("/senha/redefinir/", mail.outbox[0].body)
        self.professor.refresh_from_db()
        self.assertTrue(self.professor.check_password(SENHA))  # a senha só muda pelo link
        registro = RegistroDeAuditoria.objects.get(conta=self.professor)
        self.assertEqual((registro.acao, registro.autor), (Acao.LINK_ENVIADO, self.secretaria))

    def test_link_sem_email_nao_envia(self):
        Usuario.objects.filter(pk=self.aluno.pk).update(email="")
        resposta = self.redefinir(self.aluno, "link", follow=True)
        self.assertContains(resposta, "A conta não tem e-mail")
        self.assertEqual(mail.outbox, [])

    def test_senha_provisoria(self):
        BloqueioDeLogin.objects.create(matricula="coord01", bloqueado_ate=timezone.now() + timedelta(minutes=9))
        self.redefinir(self.coordenador, "provisoria")
        senha = self.client.get(reverse("secretaria:senha_provisoria")).context["dados"]["senha"]
        self.coordenador.refresh_from_db()
        self.assertTrue(self.coordenador.check_password(senha))
        self.assertFalse(self.coordenador.check_password(SENHA))
        self.assertTrue(self.coordenador.precisa_trocar_senha)
        self.assertFalse(BloqueioDeLogin.objects.exists())  # senha nova desbloqueia
        registro = RegistroDeAuditoria.objects.get(conta=self.coordenador)
        self.assertEqual(registro.acao, Acao.SENHA_PROVISORIA)
        self.assertNotIn(senha, registro.detalhe)

    def test_conta_desativada_nao_e_redefinida(self):
        Usuario.objects.filter(pk=self.aluno.pk).update(is_active=False)
        self.redefinir(self.aluno, "provisoria")
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.check_password(SENHA))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class BloqueioEAtivacaoTests(BaseSecretariaMixin, TestCase):
    def test_desbloquear(self):
        BloqueioDeLogin.objects.create(matricula="aluno01", bloqueado_ate=timezone.now() + timedelta(minutes=9))
        tela = self.client.get(self.url("conta", self.aluno))
        self.assertContains(tela, "Desbloquear agora")
        self.client.post(self.url("conta_desbloquear", self.aluno))
        self.assertFalse(BloqueioDeLogin.objects.exists())
        self.assertEqual(self.acoes_de(self.aluno), [Acao.DESBLOQUEIO])
        # Sem bloqueio, nada é registrado.
        self.client.post(self.url("conta_desbloquear", self.aluno))
        self.assertEqual(self.acoes_de(self.aluno), [Acao.DESBLOQUEIO])

    def test_desativar_e_reativar(self):
        url = self.url("conta_alternar_ativa", self.aluno)
        self.client.post(url)
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.is_active)
        self.client.post(url)
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.is_active)
        self.assertEqual(sorted(self.acoes_de(self.aluno)), sorted([Acao.DESATIVACAO, Acao.REATIVACAO]))

    def test_reativar_com_email_em_uso_e_recusado(self):
        Usuario.objects.filter(pk=self.aluno.pk).update(is_active=False)
        Usuario.objects.create_user("aluno99", SENHA, email="bia@exemplo.com")
        resposta = self.client.post(self.url("conta_alternar_ativa", self.aluno), follow=True)
        self.assertContains(resposta, "Outra conta ativa já usa o e-mail")
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.is_active)

    def test_historico_aparece_na_tela_da_conta(self):
        self.client.post(self.url("conta_alternar_ativa", self.aluno))
        tela = self.client.get(self.url("conta", self.aluno))
        self.assertContains(tela, "Conta desativada")
        self.assertContains(tela, "Por Sônia")
        self.assertContains(tela, "IP 127.0.0.1")


CONSOLE = "django.core.mail.backends.console.EmailBackend"


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class EmailSemSmtpTests(BaseSecretariaMixin, TestCase):
    """Sem SMTP no servidor publicado, a tela não pode dizer que o link foi enviado."""

    def enviar_link(self):
        url = self.url("conta_redefinir", self.aluno)
        return self.client.post(url, {"acao": "link", **IDENTIDADE}, follow=True)

    @override_settings(EMAIL_BACKEND=CONSOLE, DEBUG=False)
    def test_servidor_sem_smtp_avisa_e_sugere_a_senha_provisoria(self):
        tela = self.client.get(self.url("conta", self.aluno))
        self.assertContains(tela, "O envio de e-mails ainda não está configurado neste servidor")
        resposta = self.enviar_link()
        self.assertContains(resposta, "o link não chega à pessoa")
        self.assertNotContains(resposta, "Link enviado para")

    @override_settings(EMAIL_BACKEND=CONSOLE, DEBUG=True)
    def test_em_desenvolvimento_lembra_do_terminal(self):
        self.assertNotContains(
            self.client.get(self.url("conta", self.aluno)), "ainda não está configurado"
        )
        self.assertContains(self.enviar_link(), "o e-mail aparece no terminal do runserver")

    def test_com_smtp_confirma_o_envio(self):
        # Nos testes o backend é o locmem (mail.outbox), que conta como entrega de verdade.
        self.assertContains(self.enviar_link(), "Link enviado para b*a@e******.com")

    def test_check_avisa_no_servidor_publicado(self):
        from apps.contas.envio_de_email import conferir_envio_de_email

        with self.settings(EMAIL_BACKEND=CONSOLE, DEBUG=False):
            self.assertEqual([aviso.id for aviso in conferir_envio_de_email(None)], ["contas.W001"])
        with self.settings(EMAIL_BACKEND=CONSOLE, DEBUG=True):
            self.assertEqual(conferir_envio_de_email(None), [])
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", DEBUG=False):
            self.assertEqual(conferir_envio_de_email(None), [])
