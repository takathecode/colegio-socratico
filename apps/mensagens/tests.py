"""Testes da caixa de mensagens: quem participa, quem pode escrever e o controle de leitura."""

import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Curso, Disciplina, Matricula, Oferta, Turma

from .forms import contatos_do_aluno
from .models import Conversa, Mensagem
from .views import rotulo_de_tempo

Usuario = get_user_model()

MEDIA_DE_TESTE = tempfile.mkdtemp(prefix="testes-mensagens-")


def tearDownModule():
    shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], MEDIA_ROOT=MEDIA_DE_TESTE
)
class MensagensTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        curso = Curso.objects.create(nome="Curso", total_creditos=200)
        disciplina = Disciplina.objects.create(
            curso=curso, codigo="MAT1", nome="Matemática", creditos=4, carga_horaria=40
        )
        turma = Turma.objects.create(curso=curso, codigo="T1", semestre="2026.2", periodo=1)
        outra_turma = Turma.objects.create(curso=curso, codigo="T2", semestre="2026.2", periodo=1)
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil="PROFESSOR", first_name="Ana", last_name="Dias", tratamento="Profa."
        )
        cls.professor_de_fora = Usuario.objects.create_user("prof2", "senha", perfil="PROFESSOR")
        cls.coordenador = Usuario.objects.create_user("coord", "senha", perfil="COORDENADOR")
        cls.oferta = Oferta.objects.create(turma=turma, disciplina=disciplina, professor=cls.professor)
        Oferta.objects.create(
            turma=outra_turma, disciplina=disciplina, professor=cls.professor_de_fora
        )
        cls.aluno = Usuario.objects.create_user("aluno", "senha", first_name="Bia", last_name="Reis")
        cls.outro_aluno = Usuario.objects.create_user("outro", "senha")
        Matricula.objects.create(aluno=cls.aluno, turma=turma)
        Matricula.objects.create(aluno=cls.outro_aluno, turma=outra_turma)

        cls.conversa = Conversa.objects.create(
            aluno=cls.aluno, contato=cls.professor, assunto="Dúvida da prova", oferta=cls.oferta
        )
        cls.recebida = Mensagem.objects.create(
            conversa=cls.conversa, remetente=cls.professor, texto="Olá, Bia"
        )

    def setUp(self):
        self.client.force_login(self.aluno)
        self.caixa = reverse("mensagens:caixa")

    def test_visitante_vai_para_o_login_e_admin_recebe_403(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.caixa).status_code, 302)
        admin = Usuario.objects.create_superuser("admin", "senha", email="a@exemplo.com")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.caixa).status_code, 403)

    def test_lista_so_tem_conversas_do_usuario(self):
        Conversa.objects.create(
            aluno=self.outro_aluno, contato=self.professor_de_fora, assunto="Assunto do outro"
        )
        resposta = self.client.get(self.caixa)
        self.assertContains(resposta, "Dúvida da prova")
        self.assertNotContains(resposta, "Assunto do outro")

    def test_conversa_de_outra_pessoa_responde_404(self):
        self.client.force_login(self.outro_aluno)
        pk = self.conversa.pk
        self.assertEqual(self.client.get(self.caixa, {"conversa": pk}).status_code, 404)
        url = reverse("mensagens:responder", args=[pk])
        self.assertEqual(self.client.post(url, {"texto": "Invasão"}).status_code, 404)
        self.assertEqual(self.conversa.mensagens.count(), 1)

    def test_abrir_a_conversa_marca_como_lida_so_o_que_foi_recebido(self):
        enviada = Mensagem.objects.create(conversa=self.conversa, remetente=self.aluno, texto="Oi")
        self.assertEqual(self.client.get(self.caixa).context["total_nao_lidas"], 1)
        # Só carregar a caixa não conta como leitura: a pessoa ainda não clicou na conversa.
        self.recebida.refresh_from_db()
        self.assertIsNone(self.recebida.lida_em)

        resposta = self.client.get(self.caixa, {"conversa": self.conversa.pk})
        self.assertEqual(resposta.context["total_nao_lidas"], 0)
        self.recebida.refresh_from_db()
        enviada.refresh_from_db()
        self.assertIsNotNone(self.recebida.lida_em)
        self.assertIsNone(enviada.lida_em)

    def test_filtro_e_busca(self):
        lida = Conversa.objects.create(
            aluno=self.aluno, contato=self.coordenador, assunto="Cadastro"
        )
        Mensagem.objects.create(
            conversa=lida, remetente=self.coordenador, texto="x", lida_em=timezone.now()
        )
        assuntos = lambda **p: [c.assunto for c in self.client.get(self.caixa, p).context["conversas"]]
        self.assertEqual(len(assuntos()), 2)
        self.assertEqual(assuntos(filtro="nao_lidas"), ["Dúvida da prova"])
        self.assertEqual(assuntos(q="cadastro"), ["Cadastro"])
        self.assertEqual(assuntos(q="secretaria"), ["Cadastro"])
        self.assertEqual(assuntos(q="matemática"), ["Dúvida da prova"])
        self.assertEqual(assuntos(q="nada disso"), [])

    def test_responder_cria_mensagem_e_professor_tambem_responde(self):
        url = reverse("mensagens:responder", args=[self.conversa.pk])
        resposta = self.client.post(url, {"texto": "Obrigada"})
        self.assertRedirects(resposta, f"{self.caixa}?conversa={self.conversa.pk}")
        self.assertEqual(self.conversa.mensagens.last().remetente, self.aluno)

        self.client.force_login(self.professor)
        self.client.post(url, {"texto": "De nada"})
        self.assertEqual(self.conversa.mensagens.last().remetente, self.professor)

    def test_resposta_vazia_mostra_erro_e_nao_salva(self):
        url = reverse("mensagens:responder", args=[self.conversa.pk])
        resposta = self.client.post(url, {"texto": "  "})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.conversa.mensagens.count(), 1)
        self.assertEqual(resposta.context["conversa"].pk, self.conversa.pk)

    def test_tela_com_erro_mantem_os_links_no_endereco_da_caixa(self):
        """A tela com erro é mostrada em /responder/, que só aceita POST: um link relativo daria 405."""
        url = reverse("mensagens:responder", args=[self.conversa.pk])
        resposta = self.client.post(url, {"texto": ""})
        self.assertContains(resposta, f'href="{self.caixa}?conversa={self.conversa.pk}&')
        self.assertContains(resposta, f'href="{self.caixa}?filtro=nao_lidas"')
        self.assertContains(resposta, f'action="{self.caixa}"')
        self.assertNotContains(resposta, 'href="?')

    def test_contatos_sao_professores_da_turma_e_secretaria(self):
        contatos = set(contatos_do_aluno(self.aluno))
        self.assertEqual(contatos, {self.professor, self.coordenador})

    def test_nova_conversa_liga_a_disciplina_do_professor(self):
        resposta = self.client.post(
            reverse("mensagens:nova"),
            {"contato": self.professor.pk, "assunto": "Nova dúvida", "texto": "Pode me ajudar?"},
        )
        conversa = Conversa.objects.get(assunto="Nova dúvida")
        self.assertRedirects(resposta, f"{self.caixa}?conversa={conversa.pk}")
        self.assertEqual(conversa.aluno, self.aluno)
        self.assertEqual(conversa.oferta, self.oferta)
        self.assertEqual(conversa.mensagens.get().remetente, self.aluno)

    def test_nao_escreve_para_professor_de_outra_turma(self):
        resposta = self.client.post(
            reverse("mensagens:nova"),
            {"contato": self.professor_de_fora.pk, "assunto": "Oi", "texto": "Oi"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Conversa.objects.filter(assunto="Oi").exists())
        self.assertTrue(resposta.context["abrir_modal"])

    def test_professor_nao_inicia_conversa(self):
        self.client.force_login(self.professor)
        self.assertEqual(
            self.client.post(reverse("mensagens:nova"), {"assunto": "x"}).status_code, 403
        )

    def test_link_de_outra_tela_abre_o_modal_ja_preenchido(self):
        resposta = self.client.get(self.caixa, {"para": self.professor.pk, "assunto": "Física"})
        self.assertTrue(resposta.context["abrir_modal"])
        self.assertContains(resposta, 'value="Física"')

    def test_anexo_so_e_baixado_por_quem_participa(self):
        arquivo = SimpleUploadedFile("lista.pdf", b"%PDF-1.4", content_type="application/pdf")
        self.client.post(
            reverse("mensagens:responder", args=[self.conversa.pk]),
            {"texto": "Segue", "anexo": arquivo},
        )
        mensagem = self.conversa.mensagens.last()
        self.assertEqual(mensagem.nome_do_anexo, "lista.pdf")
        url = reverse("mensagens:anexo", args=[mensagem.pk])

        for participante in (self.aluno, self.professor):
            self.client.force_login(participante)
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200)
            b"".join(resposta.streaming_content)  # lê até o fim, para o Windows liberar o arquivo

        self.client.force_login(self.outro_aluno)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_mensagem_sem_anexo_responde_404(self):
        url = reverse("mensagens:anexo", args=[self.recebida.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_recusa_anexo_de_formato_invalido(self):
        arquivo = SimpleUploadedFile("virus.exe", b"MZ")
        self.client.post(
            reverse("mensagens:responder", args=[self.conversa.pk]),
            {"texto": "Segue", "anexo": arquivo},
        )
        self.assertEqual(self.conversa.mensagens.count(), 1)

    def test_rotulo_de_tempo(self):
        agora = timezone.localtime()
        self.assertEqual(rotulo_de_tempo(agora), agora.strftime("%Hh%M"))
        self.assertEqual(rotulo_de_tempo(agora - timedelta(days=1)), "Ontem")
        antes = agora - timedelta(days=5)
        self.assertEqual(rotulo_de_tempo(antes), antes.strftime("%d/%m"))

    def test_menu_marca_mensagens_e_cada_perfil_tem_o_item(self):
        for usuario in (self.aluno, self.professor, self.coordenador):
            self.client.force_login(usuario)
            resposta = self.client.get(self.caixa)
            ativos = [item["nome"] for item in resposta.context["menu_itens"] if item["ativo"]]
            self.assertEqual(ativos, ["Mensagens"])
