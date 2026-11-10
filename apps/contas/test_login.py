"""Testes do login, do redirecionamento por perfil, das permissões e da redefinição de senha."""

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .models import BloqueioDeLogin

Usuario = get_user_model()
SENHA = "senha-de-teste-123"

# Painel de cada área e o único perfil que pode abri-lo.
PAINEIS = {
    "/aluno/": "ALUNO",
    "/professor/": "PROFESSOR",
    "/coordenacao/": "COORDENADOR",
}


def criar_usuarios():
    """Cria um usuário de cada perfil. Devolve um dicionário {perfil: usuário}."""
    usuarios = {
        perfil: Usuario.objects.create_user(
            matricula=perfil.lower(),
            password=SENHA,
            perfil=perfil,
            first_name="Teste",
            email=f"{perfil.lower()}@exemplo.com",
        )
        for perfil in PAINEIS.values()
    }
    usuarios["ADMIN"] = Usuario.objects.create_superuser(
        matricula="admin", password=SENHA, email="admin@exemplo.com"
    )
    return usuarios


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()

    def entrar(self, matricula="aluno", senha=SENHA, **extras):
        dados = {"username": matricula, "password": senha, **extras}
        return self.client.post(reverse("contas:entrar"), dados)

    def test_tela_de_login_abre_sem_opcao_de_cadastro(self):
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Manter conectado")
        self.assertContains(resposta, "Esqueci minha senha")
        conteudo = resposta.content.decode().lower()
        self.assertNotIn("cadastr", conteudo)
        self.assertNotIn("criar conta", conteudo)

    def test_nao_existem_rotas_de_cadastro(self):
        for nome in ("cadastro", "registro", "criar_conta", "signup", "register"):
            with self.subTest(nome=nome), self.assertRaises(NoReverseMatch):
                reverse(f"contas:{nome}")
        for caminho in ("/cadastro/", "/registro/", "/signup/", "/register/"):
            with self.subTest(caminho=caminho):
                self.assertEqual(self.client.get(caminho).status_code, 404)

    def test_login_correto_redireciona_para_a_area_do_perfil(self):
        destinos = {
            "aluno": "/aluno/",
            "professor": "/professor/",
            "coordenador": "/coordenacao/",
            "admin": "/admin/",
        }
        for matricula, destino in destinos.items():
            with self.subTest(matricula=matricula):
                self.client.logout()
                self.assertRedirects(self.entrar(matricula), "/", target_status_code=302)
                self.assertRedirects(self.client.get("/"), destino)

    def test_senha_errada_mostra_erro_e_nao_entra(self):
        resposta = self.entrar(senha="senha-errada")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Matrícula ou senha incorreta")
        self.assertContains(resposta, 'value="aluno"')  # a matrícula digitada é mantida
        self.assertNotContains(resposta, "senha-errada")  # a senha digitada não volta na página
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_matricula_inexistente_mostra_o_mesmo_erro(self):
        # A mensagem igual impede descobrir quais matrículas existem.
        resposta = self.entrar(matricula="nao-existe")
        self.assertContains(resposta, "Matrícula ou senha incorreta")

    def test_conta_desativada_nao_entra(self):
        Usuario.objects.filter(matricula="aluno").update(is_active=False)
        self.assertContains(self.entrar(), "Matrícula ou senha incorreta")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sem_manter_conectado_a_sessao_termina_ao_fechar_o_navegador(self):
        self.entrar()
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_com_manter_conectado_a_sessao_continua(self):
        self.entrar(manter_conectado="on")
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_next_leva_de_volta_a_pagina_pedida(self):
        resposta = self.client.post(
            reverse("contas:entrar"),
            {"username": "aluno", "password": SENHA, "next": "/aluno/"},
        )
        self.assertRedirects(resposta, "/aluno/")

    def test_next_para_site_externo_e_ignorado(self):
        resposta = self.client.post(
            reverse("contas:entrar"),
            {"username": "aluno", "password": SENHA, "next": "https://site-malicioso.example/"},
        )
        self.assertRedirects(resposta, "/", target_status_code=302)

    def test_quem_ja_esta_logado_nao_ve_o_login(self):
        self.client.force_login(self.usuarios["ALUNO"])
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertRedirects(resposta, "/", target_status_code=302)

    def test_sair_exige_post_e_encerra_a_sessao(self):
        self.client.force_login(self.usuarios["ALUNO"])
        self.assertEqual(self.client.get(reverse("contas:sair")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

        resposta = self.client.post(reverse("contas:sair"))
        self.assertRedirects(resposta, reverse("contas:entrar"))
        self.assertNotIn("_auth_user_id", self.client.session)


class BloqueioTests(TestCase):
    """5 senhas erradas seguidas bloqueiam a matrícula por 15 minutos (apps/contas/bloqueio.py)."""

    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()

    def setUp(self):
        cache.clear()  # zera o limite de pedidos da API entre um teste e outro

    def entrar(self, matricula="aluno", senha=SENHA):
        return self.client.post(
            reverse("contas:entrar"), {"username": matricula, "password": senha}
        )

    def errar(self, vezes, matricula="aluno"):
        for _ in range(vezes):
            resposta = self.entrar(matricula, "senha-errada")
        return resposta

    def entrou(self):
        return "_auth_user_id" in self.client.session

    def test_quatro_erros_nao_bloqueiam_e_o_acerto_zera_a_contagem(self):
        self.errar(4)
        self.entrar()
        self.assertTrue(self.entrou())
        self.assertFalse(BloqueioDeLogin.objects.exists())

    def test_quinto_erro_bloqueia_mesmo_com_a_senha_certa(self):
        self.assertContains(self.errar(5), "Acesso bloqueado temporariamente")
        resposta = self.entrar()
        self.assertContains(resposta, "Acesso bloqueado temporariamente")
        self.assertContains(resposta, "daqui a 15 minutos")
        self.assertFalse(self.entrou())

    def test_outras_matriculas_continuam_entrando(self):
        self.errar(5)
        self.entrar("professor")
        self.assertTrue(self.entrou())

    def test_matricula_inexistente_tem_o_mesmo_bloqueio(self):
        # A mesma mensagem para quem existe e quem não existe: o login não revela matrículas.
        self.assertContains(self.errar(5, "nao-existe"), "Acesso bloqueado temporariamente")

    def test_bloqueio_acaba_depois_de_15_minutos(self):
        self.errar(5)
        BloqueioDeLogin.objects.update(bloqueado_ate=timezone.now() - timedelta(seconds=1))
        self.entrar()
        self.assertTrue(self.entrou())

    def test_erros_antigos_nao_contam(self):
        self.errar(4)
        BloqueioDeLogin.objects.update(ultimo_erro_em=timezone.now() - timedelta(minutes=16))
        self.assertContains(self.errar(1), "Matrícula ou senha incorreta")
        self.assertEqual(BloqueioDeLogin.objects.get().erros, 1)

    def test_senha_nova_desbloqueia(self):
        self.errar(5)
        aluno = self.usuarios["ALUNO"]
        aluno.set_password("senha-nova-456")
        aluno.save()
        self.entrar(senha="senha-nova-456")
        self.assertTrue(self.entrou())

    def test_token_da_api_tambem_respeita_o_bloqueio(self):
        self.errar(5)
        resposta = self.client.post(reverse("api:token"), {"matricula": "aluno", "senha": SENHA})
        self.assertEqual(resposta.status_code, 400)


class RedirecionamentoTests(TestCase):
    def test_visitante_em_inicio_vai_para_o_login(self):
        self.assertRedirects(self.client.get("/"), reverse("contas:entrar"))


class PermissoesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()

    def test_visitante_e_mandado_ao_login(self):
        for painel in PAINEIS:
            with self.subTest(painel=painel):
                self.assertRedirects(
                    self.client.get(painel), f"{reverse('contas:entrar')}?next={painel}"
                )

    def test_cada_perfil_so_abre_a_propria_area(self):
        for perfil, usuario in self.usuarios.items():
            self.client.force_login(usuario)
            for painel, perfil_permitido in PAINEIS.items():
                with self.subTest(perfil=perfil, painel=painel):
                    esperado = 200 if perfil == perfil_permitido else 403
                    self.assertEqual(self.client.get(painel).status_code, esperado)

    def test_pagina_403_e_amigavel(self):
        self.client.force_login(self.usuarios["ALUNO"])
        resposta = self.client.get("/coordenacao/")
        self.assertEqual(resposta.status_code, 403)
        self.assertTemplateUsed(resposta, "403.html")
        self.assertContains(resposta, "Acesso não permitido", status_code=403)
        self.assertContains(resposta, "Voltar ao meu painel", status_code=403)

    def test_decorator_bloqueia_visitante_mesmo_sem_login_required(self):
        from django.contrib.auth.models import AnonymousUser
        from django.core.exceptions import PermissionDenied
        from django.http import HttpResponse
        from django.test import RequestFactory

        from apps.contas.decorators import perfil_requerido

        view = perfil_requerido("ALUNO")(lambda request: HttpResponse("ok"))
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        with self.assertRaises(PermissionDenied):
            view(request)


class LayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()

    def test_barra_lateral_mostra_o_menu_do_perfil_e_marca_a_pagina_atual(self):
        self.client.force_login(self.usuarios["PROFESSOR"])
        resposta = self.client.get("/professor/")
        self.assertContains(resposta, "Área do professor")
        self.assertContains(resposta, "Lançar notas")
        # "Relatórios" só existe no menu do coordenador. ("Alunos em risco" não serve mais:
        # desde a etapa 5 o painel do professor tem um card com esse título.)
        self.assertNotContains(resposta, "Relatórios")
        self.assertContains(resposta, 'aria-current="page"', count=1)

    def test_menu_nao_tem_links_para_telas_que_nao_existem(self):
        # Item de tela ainda não feita aparece desativado, nunca como link quebrado.
        self.client.force_login(self.usuarios["COORDENADOR"])
        resposta = self.client.get("/coordenacao/")
        # Desde a etapa 10 todos os itens do coordenador têm tela, então nenhum fica "em breve".
        self.assertNotContains(resposta, "Relatórios: em breve")
        self.assertContains(resposta, 'href="/relatorios/"')
        self.assertNotContains(resposta, 'href="#"')

    def test_topo_mostra_iniciais_e_matricula(self):
        aluna = Usuario.objects.create_user(
            matricula="202410284", password=SENHA, first_name="Mariana", last_name="Alves"
        )
        self.client.force_login(aluna)
        resposta = self.client.get("/aluno/")
        self.assertContains(resposta, "MA")
        self.assertContains(resposta, "RA 202410284")


class RedefinirSenhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()

    def pedir_link(self, email="aluno@exemplo.com"):
        return self.client.post(reverse("contas:senha_esqueci"), {"email": email})

    def test_fluxo_completo(self):
        self.assertRedirects(self.pedir_link(), reverse("contas:senha_enviada"))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["aluno@exemplo.com"])
        self.assertIn("Instituto Socrático", mail.outbox[0].subject)
        link = re.search(r"https?://[^/]+(/senha/nova/\S+)", mail.outbox[0].body).group(1)

        # O Django troca o código do link por um endereço sem o código, guardado na sessão.
        pagina = self.client.get(link, follow=True)
        self.assertContains(pagina, "Criar nova senha")
        nova_senha = "Nova-Senha-Forte-2026"
        resposta = self.client.post(
            pagina.redirect_chain[-1][0],
            {"new_password1": nova_senha, "new_password2": nova_senha},
        )
        self.assertRedirects(resposta, reverse("contas:senha_concluida"))
        self.assertTrue(self.client.login(matricula="aluno", password=nova_senha))

    def test_email_desconhecido_nao_revela_que_nao_existe(self):
        self.assertRedirects(
            self.pedir_link("ninguem@exemplo.com"), reverse("contas:senha_enviada")
        )
        self.assertEqual(mail.outbox, [])

    def test_link_invalido_mostra_aviso(self):
        url = reverse("contas:senha_nova", args=["abc", "codigo-invalido"])
        self.assertContains(self.client.get(url), "Link inválido")

    def test_telas_publicas_abrem(self):
        for nome in ("senha_esqueci", "senha_enviada", "senha_concluida", "atendimento"):
            with self.subTest(nome=nome):
                self.assertEqual(self.client.get(reverse(f"contas:{nome}")).status_code, 200)
