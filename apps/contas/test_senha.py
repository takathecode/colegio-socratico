"""Testes de senha: "Esqueci minha senha" pela matrícula, link (token), regras de senha forte,
máscara do e-mail, troca obrigatória da senha provisória e "Alterar minha senha".

Os e-mails ficam em mail.outbox (o Django troca o envio de verdade por uma lista nos testes).
O tempo é adiantado com unittest.mock, sem biblioteca nova.
"""

import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import bloqueio, redefinicao
from .mascara import mascarar_email
from .models import BloqueioDeLogin, PedidoDeSenha, RegistroDeAuditoria
from .senhas import gerar_senha_provisoria
from .tokens import GeradorDeLinkDeSenha
from .views import MENSAGEM_LIMITE, MENSAGEM_NEUTRA

Usuario = get_user_model()

SENHA_ANTIGA = "Primeira#Senha2026"
SENHA_NOVA = "Nuvem-Clara#2031"
HASH_RAPIDO = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LINK = re.compile(r"https?://[^/\s]+(/senha/redefinir/\S+/)")


@contextmanager
def daqui_a(minutos):
    """Faz o código achar que já se passaram alguns minutos (o token e o prazo do pedido)."""
    agora = timezone.now() + timedelta(minutes=minutos)
    local = datetime.now() + timedelta(minutes=minutos)
    with (
        mock.patch("apps.contas.tokens.timezone.now", return_value=agora),
        mock.patch.object(GeradorDeLinkDeSenha, "_now", return_value=local),
    ):
        yield


class MascaraDoEmailTests(SimpleTestCase):
    def test_exemplos(self):
        casos = {
            "fulana.souza@gmail.com": "f**********a@g****.com",
            "jose@escola.edu.br": "j**e@e*****.edu.br",
            # Subdomínio: só o primeiro pedaço do domínio é mascarado.
            "ana.lima9@turma.exemplo.br": "a*******9@t****.exemplo.br",
        }
        for email, esperado in casos.items():
            with self.subTest(email=email):
                self.assertEqual(mascarar_email(email), esperado)

    def test_usuario_curto(self):
        self.assertEqual(mascarar_email("a@exemplo.com"), "a@e******.com")
        self.assertEqual(mascarar_email("ab@exemplo.com"), "a*@e******.com")
        self.assertEqual(mascarar_email("abc@exemplo.com"), "a*c@e******.com")

    def test_maiusculas_viram_minusculas(self):
        self.assertEqual(mascarar_email("  Fulana.Souza@GMAIL.Com "), "f**********a@g****.com")

    def test_texto_que_nao_e_email(self):
        for valor in ("", None, "sem-arroba", "@exemplo.com", "fulana@"):
            with self.subTest(valor=valor):
                self.assertEqual(mascarar_email(valor), "")

    def test_nunca_mostra_o_endereco_inteiro(self):
        email = "fulana.souza@gmail.com"
        self.assertNotIn("fulana", mascarar_email(email))
        self.assertNotIn("gmail", mascarar_email(email))


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class RegrasDeSenhaTests(TestCase):
    """Validadores do AUTH_PASSWORD_VALIDATORS, cada regra sozinha e em português."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            "2026123",
            SENHA_ANTIGA,
            first_name="Fulana",
            last_name="Souza",
            email="fulana.souza@exemplo.com",
        )

    def erros(self, senha):
        try:
            validate_password(senha, self.usuario)
        except ValidationError as erro:
            return " ".join(erro.messages)
        return ""

    def test_senha_forte_passa(self):
        self.assertEqual(self.erros(SENHA_NOVA), "")

    def test_cada_regra_recusa_com_mensagem_em_portugues(self):
        casos = {
            "Cur#1a": "pelo menos 10 caracteres",
            "A1#" + "b" * 130: "no máximo 128 caracteres",
            "semmaiuscula#2031": "letra maiúscula",
            "SEMMINUSCULA#2031": "letra minúscula",
            "Sem-Numero#Aqui": "um número",
            "SemEspecial2031x": "caractere especial",
            "Fulana#Ok2031": "não pode conter a sua matrícula, o seu nome",
            "Ok#2026123abc": "não pode conter a sua matrícula",
            "Souza.Ok#2031": "não pode conter",
            "Password1!": "muito comum",
            "20312031203120": "inteiramente numérica",
            SENHA_ANTIGA: "diferente da senha atual",
        }
        for senha, trecho in casos.items():
            with self.subTest(senha=senha):
                self.assertIn(trecho, self.erros(senha))

    def test_senha_provisoria_cumpre_todas_as_regras(self):
        for _ in range(20):
            senha = gerar_senha_provisoria(self.usuario)
            self.assertEqual(len(senha), 12)
            self.assertEqual(self.erros(senha), "")

    def test_senha_provisoria_e_aleatoria(self):
        self.assertEqual(len({gerar_senha_provisoria() for _ in range(30)}), 30)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO, SITE_URL="https://portal.exemplo.br")
class EsqueciMinhaSenhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.aluno = Usuario.objects.create_user(
            "aluno01", SENHA_ANTIGA, first_name="Fulana", email="fulana.souza@exemplo.com.br"
        )
        cls.outro = Usuario.objects.create_user(
            "aluno02", SENHA_ANTIGA, first_name="Beltrano", email="beltrano@exemplo.com.br"
        )

    # --- Ajudantes ---

    def informar(self, matricula="aluno01", cliente=None):
        cliente = cliente or self.client
        return cliente.post(reverse("contas:senha_esqueci"), {"matricula": matricula})

    def pedir_link(self, matricula="aluno01"):
        self.informar(matricula)
        return self.client.post(reverse("contas:senha_confirmar"))

    def link_do_email(self, indice=-1):
        return LINK.search(mail.outbox[indice].body).group(1)

    def abrir_link(self, link):
        """Abre o link do e-mail. Devolve a resposta final e o endereço sem o código."""
        resposta = self.client.get(link, follow=True)
        endereco = resposta.redirect_chain[-1][0] if resposta.redirect_chain else link
        return resposta, endereco

    def trocar(self, link, senha=SENHA_NOVA, **extras):
        _, endereco = self.abrir_link(link)
        dados = {"new_password1": senha, "new_password2": senha, **extras}
        return self.client.post(endereco, dados)

    # --- Etapas 1 a 3 ---

    def test_etapa_1_tem_so_a_matricula(self):
        resposta = self.client.get(reverse("contas:senha_esqueci"))
        self.assertContains(resposta, 'autocomplete="username"')
        self.assertContains(resposta, "Continuar")
        self.assertContains(resposta, "Voltar para o login")
        self.assertNotContains(resposta, 'type="email"')

    def test_matricula_valida_mostra_o_email_mascarado(self):
        resposta = self.informar()
        # A matrícula vai para a sessão, nunca para a URL.
        self.assertRedirects(resposta, reverse("contas:senha_confirmar"))
        self.assertNotIn("?", resposta.url)
        tela = self.client.get(reverse("contas:senha_confirmar"))
        self.assertContains(tela, "Vamos enviar um link de redefinição para")
        self.assertContains(tela, "f**********a@e******.com.br")
        self.assertNotContains(tela, "fulana.souza@")
        self.assertContains(tela, "Enviar link")
        self.assertContains(tela, "csrfmiddlewaretoken")
        self.assertEqual(mail.outbox, [])  # só envia depois de confirmar

    def test_enviar_link_manda_o_email_com_o_link(self):
        resposta = self.pedir_link()
        self.assertRedirects(resposta, reverse("contas:senha_enviada"))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["fulana.souza@exemplo.com.br"])
        self.assertIn("Instituto Socrático", email.subject)
        self.assertIn("Olá, Fulana.", email.body)
        self.assertIn("10 minutos", email.body)
        self.assertIn("Se você não pediu, ignore este e-mail. Sua senha continua a mesma.", email.body)
        # Também em HTML, com o botão "Criar nova senha" e o link em texto puro.
        html, tipo = email.alternatives[0]
        self.assertEqual(tipo, "text/html")
        self.assertIn("Criar nova senha", html)
        self.assertIn(self.link_do_email(), html)

    def test_tela_verifique_seu_email_mostra_o_horario_exato(self):
        self.pedir_link()
        self.aluno.refresh_from_db()
        limite = timezone.localtime(self.aluno.ultimo_pedido_reset + timedelta(minutes=10))
        tela = self.client.get(reverse("contas:senha_enviada"))
        self.assertContains(tela, f"Válido até {limite:%H:%M}")
        self.assertContains(tela, "spam")
        self.assertContains(tela, "Reenviar link")
        self.assertIn(f"{limite:%H:%M}", mail.outbox[0].body)

    def test_reenviar_manda_outro_link(self):
        self.pedir_link()
        self.client.post(reverse("contas:senha_confirmar"))  # botão "Reenviar link"
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_link_usa_o_site_url_e_nao_o_cabecalho_host(self):
        self.client.post(
            reverse("contas:senha_esqueci"), {"matricula": "aluno01"}, HTTP_HOST="atacante.example"
        )
        self.client.post(reverse("contas:senha_confirmar"), HTTP_HOST="atacante.example")
        self.assertIn("https://portal.exemplo.br/senha/redefinir/", mail.outbox[0].body)
        self.assertNotIn("atacante.example", mail.outbox[0].body)

    def test_mensagem_neutra_para_inexistente_desativada_e_sem_email(self):
        Usuario.objects.create_user("inativa", SENHA_ANTIGA, email="inativa@exemplo.com", is_active=False)
        Usuario.objects.create_user("sememail", SENHA_ANTIGA)
        telas = []
        for matricula in ("nao-existe", "inativa", "sememail"):
            with self.subTest(matricula=matricula):
                self.informar(matricula)
                tela = self.client.get(reverse("contas:senha_confirmar"))
                self.assertContains(tela, MENSAGEM_NEUTRA)
                self.assertNotContains(tela, "Vamos enviar")
                self.assertNotContains(tela, "*@")
                # Mesmo forçando o envio à mão, nenhum e-mail sai.
                self.client.post(reverse("contas:senha_confirmar"))
                telas.append(tela.content.replace(matricula.encode(), b""))
        self.assertEqual(mail.outbox, [])
        # As três telas são iguais, a não ser pela matrícula digitada.
        self.assertEqual(len(set(telas)), 1)

    def test_sem_passar_pela_etapa_1_volta_para_o_inicio(self):
        for nome in ("senha_confirmar", "senha_enviada"):
            with self.subTest(nome=nome):
                self.assertRedirects(self.client.get(reverse(f"contas:{nome}")), reverse("contas:senha_esqueci"))

    def test_telas_nao_mandam_referer_a_outros_sites(self):
        self.informar()
        for nome in ("senha_esqueci", "senha_confirmar"):
            with self.subTest(nome=nome):
                resposta = self.client.get(reverse(f"contas:{nome}"))
                self.assertEqual(resposta["Referrer-Policy"], "no-referrer")

    # --- Limite de pedidos ---

    def test_limite_de_links_por_matricula(self):
        for _ in range(redefinicao.LINKS_POR_MATRICULA):
            self.pedir_link()
        resposta = self.client.post(reverse("contas:senha_confirmar"), follow=True)
        self.assertContains(resposta, MENSAGEM_LIMITE)
        self.assertEqual(len(mail.outbox), redefinicao.LINKS_POR_MATRICULA)

    def test_limite_de_links_por_ip(self):
        contas = [self.aluno, self.outro] + [
            Usuario.objects.create_user(f"extra{n}", SENHA_ANTIGA, email=f"extra{n}@exemplo.com")
            for n in range(2)
        ]
        enviados = 0
        while enviados < redefinicao.LINKS_POR_IP:
            conta = contas[enviados % len(contas)]
            self.pedir_link(conta.matricula)
            enviados += 1
        resposta = self.pedir_link("extra0")
        self.assertRedirects(resposta, reverse("contas:senha_confirmar"))
        self.assertEqual(len(mail.outbox), redefinicao.LINKS_POR_IP)

    def test_pedidos_antigos_nao_contam(self):
        for _ in range(redefinicao.LINKS_POR_MATRICULA):
            self.pedir_link()
        PedidoDeSenha.objects.update(criado_em=timezone.now() - timedelta(hours=2))
        self.pedir_link()
        self.assertEqual(len(mail.outbox), redefinicao.LINKS_POR_MATRICULA + 1)

    def test_limite_de_consultas_por_ip(self):
        for numero in range(redefinicao.CONSULTAS_POR_IP):
            self.informar(f"chute{numero}")
        resposta = self.informar("aluno01")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MENSAGEM_LIMITE)

    # --- Etapa 4: o link ---

    def test_link_tira_o_codigo_da_url_e_trava_a_matricula(self):
        self.pedir_link()
        tela, endereco = self.abrir_link(self.link_do_email())
        self.assertTrue(endereco.endswith("/set-password/"))  # o código foi para a sessão
        self.assertEqual(tela["Referrer-Policy"], "no-referrer")
        self.assertContains(tela, "Criar nova senha")
        self.assertContains(tela, 'value="aluno01" readonly aria-readonly="true"')
        self.assertContains(tela, 'autocomplete="new-password"', count=2)
        self.assertContains(tela, "data-mostrar-senha", count=2)
        self.assertContains(tela, 'aria-live="polite"')

    def test_troca_pelo_link(self):
        outra_sessao = Client()
        outra_sessao.force_login(self.aluno)
        bloqueio.registrar_erro("aluno01")
        Usuario.objects.filter(pk=self.aluno.pk).update(precisa_trocar_senha=True)
        self.pedir_link()
        link = self.link_do_email()
        mail.outbox.clear()

        # O aviso sai depois que a troca é gravada (transaction.on_commit).
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.trocar(link)
        # Sem login automático: volta ao login com a mensagem de sucesso.
        # fetch_redirect_response=False: abrir o login aqui consumiria a mensagem de sucesso.
        self.assertRedirects(resposta, reverse("contas:entrar"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("contas:entrar")), "Senha alterada.")

        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.password.startswith("md5$"))  # só o hash vai para o banco
        self.assertNotIn(SENHA_NOVA, self.aluno.password)
        self.assertFalse(self.client.login(matricula="aluno01", password=SENHA_ANTIGA))
        self.assertTrue(self.client.login(matricula="aluno01", password=SENHA_NOVA))
        self.assertFalse(BloqueioDeLogin.objects.filter(matricula="aluno01").exists())
        self.assertFalse(self.aluno.precisa_trocar_senha)
        # A outra sessão aberta (outro aparelho) foi encerrada.
        self.assertRedirects(outra_sessao.get("/aluno/"), f"{reverse('contas:entrar')}?next=/aluno/")
        # Aviso da troca.
        self.assertEqual(len(mail.outbox), 1)
        self.assertRegex(
            mail.outbox[0].body,
            r"Sua senha foi alterada em \d{2}/\d{2}/\d{4} às \d{2}:\d{2}\. "
            r"Se não foi você, procure a Secretaria imediatamente\.",
        )

    def test_link_funciona_uma_unica_vez(self):
        self.pedir_link()
        link = self.link_do_email()
        self.trocar(link)
        tela, _ = self.abrir_link(link)
        self.assertContains(tela, "Este link expirou ou já foi usado")
        self.assertContains(tela, "Pedir outro link")

    def test_entrar_com_a_senha_antiga_invalida_o_link(self):
        self.pedir_link()
        link = self.link_do_email()
        self.assertTrue(Client().login(matricula="aluno01", password=SENHA_ANTIGA))
        tela, _ = self.abrir_link(link)
        self.assertContains(tela, "Este link expirou ou já foi usado")

    def test_link_vale_10_minutos(self):
        self.pedir_link()
        link = self.link_do_email()
        with daqui_a(9):
            tela, _ = self.abrir_link(link)
            self.assertContains(tela, "Criar nova senha")
        self.client = Client()
        with daqui_a(11):
            tela, _ = self.abrir_link(link)
            self.assertContains(tela, "Este link expirou ou já foi usado")

    def test_link_vencido_entre_abrir_e_salvar_nao_troca(self):
        self.pedir_link()
        _, endereco = self.abrir_link(self.link_do_email())
        with daqui_a(11):
            resposta = self.client.post(
                endereco, {"new_password1": SENHA_NOVA, "new_password2": SENHA_NOVA}
            )
        self.assertContains(resposta, "Este link expirou ou já foi usado")
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.check_password(SENHA_ANTIGA))

    def test_pedir_link_novo_invalida_o_anterior(self):
        self.pedir_link()
        antigo = self.link_do_email(0)
        self.client.post(reverse("contas:senha_confirmar"))
        novo = self.link_do_email(1)
        self.assertNotEqual(antigo, novo)
        tela, _ = self.abrir_link(antigo)
        self.assertContains(tela, "Este link expirou ou já foi usado")
        self.client = Client()
        tela, _ = self.abrir_link(novo)
        self.assertContains(tela, "Criar nova senha")

    def test_link_adulterado_e_recusado(self):
        self.pedir_link()
        link = self.link_do_email()
        uid, codigo = link.strip("/").split("/")[-2:]
        trocado = "1" if codigo[-1] != "1" else "2"
        adulterados = [
            reverse("contas:senha_redefinir", args=[uid, codigo[:-1] + trocado]),
            reverse("contas:senha_redefinir", args=["MTIzNDU", codigo]),  # outro usuário
            reverse("contas:senha_redefinir", args=["abc", "codigo-invalido"]),
        ]
        for url in adulterados:
            with self.subTest(url=url):
                tela, _ = self.abrir_link(url)
                self.assertContains(tela, "Este link expirou ou já foi usado")

    def test_matricula_enviada_no_post_e_ignorada(self):
        self.pedir_link()
        self.trocar(self.link_do_email(), matricula="aluno02", username="aluno02")
        self.aluno.refresh_from_db()
        self.outro.refresh_from_db()
        self.assertTrue(self.aluno.check_password(SENHA_NOVA))
        self.assertTrue(self.outro.check_password(SENHA_ANTIGA))

    def test_senha_fraca_e_recusada_na_tela(self):
        self.pedir_link()
        resposta = self.trocar(self.link_do_email(), senha="fraca")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "pelo menos 10 caracteres")
        self.assertContains(resposta, 'role="alert"')
        self.assertContains(resposta, 'aria-describedby="id_new_password2-erros')
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.check_password(SENHA_ANTIGA))

    def test_confirmacao_diferente_e_recusada(self):
        self.pedir_link()
        resposta = self.trocar(self.link_do_email(), new_password2="Outra-Senha#2031")
        self.assertEqual(resposta.status_code, 200)
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.check_password(SENHA_ANTIGA))

    # --- Auditoria ---

    def test_auditoria_sem_senha_nem_codigo(self):
        self.pedir_link()
        link = self.link_do_email()
        self.trocar(link)
        acoes = list(
            RegistroDeAuditoria.objects.filter(conta=self.aluno).values_list("acao", flat=True)
        )
        Acao = RegistroDeAuditoria.Acao
        self.assertEqual(sorted(acoes), sorted([Acao.LINK_ENVIADO, Acao.SENHA_REDEFINIDA]))
        codigo = link.strip("/").split("/")[-1]
        for registro in RegistroDeAuditoria.objects.all():
            self.assertEqual(registro.ip, "127.0.0.1")
            self.assertNotIn(SENHA_NOVA, registro.detalhe)
            self.assertNotIn(codigo, registro.detalhe)
        # Pela tela pública não há ninguém logado; a troca foi feita pela própria pessoa.
        self.assertIsNone(RegistroDeAuditoria.objects.get(acao=Acao.LINK_ENVIADO).autor)
        self.assertEqual(RegistroDeAuditoria.objects.get(acao=Acao.SENHA_REDEFINIDA).autor, self.aluno)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class SenhaProvisoriaTests(TestCase):
    """Quem recebeu senha provisória só usa o portal depois de criar a própria senha."""

    @classmethod
    def setUpTestData(cls):
        cls.aluno = Usuario.objects.create_user(
            "aluno01", "Provisoria#2026", email="fulana@exemplo.com", precisa_trocar_senha=True
        )

    def setUp(self):
        self.client.login(matricula="aluno01", password="Provisoria#2026")

    def test_nenhuma_outra_tela_abre_antes_da_troca(self):
        destino = reverse("contas:senha_alterar")
        for url in ("/", "/aluno/", "/aluno/notas/", "/mensagens/", "/alertas/", "/conta/foto/", "/api/eu/"):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), destino, fetch_redirect_response=False
                )
        self.assertRedirects(self.client.post("/conta/foto/remover/"), destino)

    def test_tela_de_troca_explica_e_permite_sair(self):
        tela = self.client.get(reverse("contas:senha_alterar"))
        self.assertContains(tela, "Crie a sua senha")
        self.assertContains(tela, "Senha provisória")
        self.assertContains(tela, "Sair sem trocar")
        self.assertRedirects(self.client.post(reverse("contas:sair")), reverse("contas:entrar"))

    def test_depois_da_troca_o_portal_abre(self):
        resposta = self.client.post(
            reverse("contas:senha_alterar"),
            {"old_password": "Provisoria#2026", "new_password1": SENHA_NOVA, "new_password2": SENHA_NOVA},
        )
        self.assertRedirects(resposta, "/", target_status_code=302)
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.precisa_trocar_senha)
        self.assertEqual(self.client.get("/alertas/").status_code, 200)

    def test_nao_pode_repetir_a_provisoria(self):
        resposta = self.client.post(
            reverse("contas:senha_alterar"),
            {"old_password": "Provisoria#2026", "new_password1": "Provisoria#2026", "new_password2": "Provisoria#2026"},
        )
        self.assertContains(resposta, "diferente da senha atual")
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.precisa_trocar_senha)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class AlterarMinhaSenhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.professor = Usuario.objects.create_user(
            "prof01", SENHA_ANTIGA, perfil="PROFESSOR", email="prof@exemplo.com"
        )

    def setUp(self):
        self.client.force_login(self.professor)
        self.url = reverse("contas:senha_alterar")

    def alterar(self, atual=SENHA_ANTIGA, nova=SENHA_NOVA):
        return self.client.post(
            self.url, {"old_password": atual, "new_password1": nova, "new_password2": nova}
        )

    def test_visitante_vai_para_o_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f"{reverse('contas:entrar')}?next={self.url}")

    def test_senha_atual_errada(self):
        resposta = self.alterar(atual="Errada#2026x")
        self.assertContains(resposta, "A senha atual está incorreta.")
        self.professor.refresh_from_db()
        self.assertTrue(self.professor.check_password(SENHA_ANTIGA))

    def test_troca_mantem_esta_sessao_e_encerra_as_outras(self):
        outro_aparelho = Client()
        outro_aparelho.force_login(self.professor)
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.alterar()
        self.assertRedirects(resposta, "/", target_status_code=302)
        self.assertEqual(self.client.get("/professor/").status_code, 200)  # update_session_auth_hash
        self.assertEqual(outro_aparelho.get("/professor/").status_code, 302)
        self.assertTrue(
            RegistroDeAuditoria.objects.filter(
                conta=self.professor, acao=RegistroDeAuditoria.Acao.SENHA_ALTERADA, autor=self.professor
            ).exists()
        )
        self.assertIn("Sua senha foi alterada em", mail.outbox[0].body)

    def test_regras_de_senha_forte_valem_aqui(self):
        resposta = self.alterar(nova="semmaiuscula#2031")
        self.assertContains(resposta, "letra maiúscula")
