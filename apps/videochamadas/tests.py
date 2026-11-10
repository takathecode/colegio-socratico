"""Testes das videochamadas: quem chama quem, quem entra na sala, convite no sino e histórico.

As permissões por perfil (aluno e ADMIN levam 403) estão na varredura de
apps/contas/test_permissoes.py.
"""

from datetime import timedelta
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.professor.tests import HASH_RAPIDO

from .forms import pessoas_para_chamar
from .models import DURACAO_MAXIMA, Chamada

Usuario = get_user_model()


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO, JITSI_SERVIDOR="https://meet.jit.si")
class VideochamadasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordenador = Usuario.objects.create_user(
            "coord", "senha", perfil="COORDENADOR", first_name="Carla", last_name="Souza"
        )
        cls.outro_coordenador = Usuario.objects.create_user(
            "coord2", "senha", perfil="COORDENADOR", first_name="Davi"
        )
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil="PROFESSOR", first_name="Ana", last_name="Dias",
            tratamento="Profa.",
        )
        cls.outro_professor = Usuario.objects.create_user(
            "prof2", "senha", perfil="PROFESSOR", first_name="Bruno"
        )
        cls.professor_desativado = Usuario.objects.create_user(
            "prof3", "senha", perfil="PROFESSOR", first_name="Caio", is_active=False
        )
        cls.aluno = Usuario.objects.create_user("aluno", "senha", perfil="ALUNO")

    def chamar(self, de, para, assunto=""):
        self.client.force_login(de)
        return self.client.post(
            reverse("videochamadas:nova"), {"convidado": para.pk, "assunto": assunto}
        )

    # --- Quem pode ser chamado ---

    def test_coordenacao_chama_so_professores_ativos(self):
        self.assertEqual(
            list(pessoas_para_chamar(self.coordenador)), [self.professor, self.outro_professor]
        )

    def test_professor_chama_so_coordenadores_ativos(self):
        self.assertEqual(
            list(pessoas_para_chamar(self.professor)), [self.coordenador, self.outro_coordenador]
        )

    def test_nao_cria_chamada_com_quem_esta_fora_da_lista(self):
        # Coordenador com coordenador, com aluno ou com conta desativada: o formulário recusa.
        for convidado in (self.outro_coordenador, self.aluno, self.professor_desativado):
            with self.subTest(convidado=convidado.matricula):
                resposta = self.chamar(self.coordenador, convidado)
                self.assertEqual(resposta.status_code, 200)
                self.assertFalse(Chamada.objects.exists())
                self.assertFalse(Alerta.objects.exists())

    # --- Criar a chamada ---

    def test_coordenador_cria_chamada_e_o_professor_recebe_o_convite(self):
        resposta = self.chamar(self.coordenador, self.professor, assunto="Planejamento")
        chamada = Chamada.objects.get()
        self.assertRedirects(resposta, reverse("videochamadas:sala", args=[chamada.pk]))
        self.assertEqual(chamada.criada_por, self.coordenador)
        self.assertEqual(chamada.convidado, self.professor)
        self.assertTrue(chamada.em_andamento)

        alerta = Alerta.objects.get()
        self.assertEqual(alerta.destinatario, self.professor)
        self.assertEqual(alerta.tipo, Alerta.Tipo.VIDEOCHAMADA)
        self.assertEqual(alerta.link, reverse("videochamadas:sala", args=[chamada.pk]))
        self.assertIn("Carla Souza", alerta.titulo)
        self.assertEqual(alerta.texto, "Assunto: Planejamento")
        self.assertFalse(alerta.por_email)

    def test_professor_tambem_chama_a_coordenacao(self):
        self.chamar(self.professor, self.coordenador)
        chamada = Chamada.objects.get()
        self.assertEqual(chamada.criada_por, self.professor)
        self.assertEqual(Alerta.objects.get().destinatario, self.coordenador)

    def test_quem_chama_e_sempre_quem_esta_logado(self):
        # Um campo "criada_por" enviado à mão é ignorado.
        self.client.force_login(self.professor)
        self.client.post(
            reverse("videochamadas:nova"),
            {"convidado": self.coordenador.pk, "criada_por": self.outro_professor.pk},
        )
        self.assertEqual(Chamada.objects.get().criada_por, self.professor)

    def test_cada_chamada_tem_uma_sala_sorteada(self):
        self.chamar(self.coordenador, self.professor)
        self.chamar(self.coordenador, self.professor)
        salas = list(Chamada.objects.values_list("sala", flat=True))
        self.assertEqual(len(set(salas)), 2)
        for sala in salas:
            self.assertRegex(sala, r"^InstitutoSocratico-[0-9a-f]{24}$")
        # Duas chamadas, dois convites: não há a janela de 7 dias dos outros alertas.
        self.assertEqual(Alerta.objects.count(), 2)

    def test_botao_chamar_ja_escolhe_a_pessoa(self):
        self.client.force_login(self.coordenador)
        resposta = self.client.get(f"{reverse('videochamadas:inicio')}?para={self.professor.pk}")
        self.assertContains(resposta, f'<option value="{self.professor.pk}" selected>')

    def test_lista_de_professores_tem_o_botao_chamar_so_para_contas_ativas(self):
        self.client.force_login(self.coordenador)
        resposta = self.client.get(reverse("coordenacao:professores"))
        url = reverse("videochamadas:inicio")
        self.assertContains(resposta, f"{url}?para={self.professor.pk}")
        self.assertNotContains(resposta, f"{url}?para={self.professor_desativado.pk}")

    # --- Sala ---

    def test_participantes_abrem_a_sala_com_o_link_do_jitsi(self):
        self.chamar(self.coordenador, self.professor, assunto="Notas")
        chamada = Chamada.objects.get()
        for pessoa in (self.coordenador, self.professor):
            with self.subTest(pessoa=pessoa.matricula):
                self.client.force_login(pessoa)
                resposta = self.client.get(reverse("videochamadas:sala", args=[chamada.pk]))
                self.assertContains(resposta, f"https://meet.jit.si/{chamada.sala}#")
                self.assertContains(resposta, 'target="_blank"')

    def test_quem_nao_participa_recebe_404(self):
        self.chamar(self.coordenador, self.professor)
        chamada = Chamada.objects.get()
        for pessoa in (self.outro_coordenador, self.outro_professor):
            with self.subTest(pessoa=pessoa.matricula):
                self.client.force_login(pessoa)
                self.assertEqual(
                    self.client.get(reverse("videochamadas:sala", args=[chamada.pk])).status_code,
                    404,
                )
                url = reverse("videochamadas:encerrar", args=[chamada.pk])
                self.assertEqual(self.client.post(url).status_code, 404)
        chamada.refresh_from_db()
        self.assertIsNone(chamada.encerrada_em)

    def test_abrir_a_sala_marca_o_convite_como_lido(self):
        self.chamar(self.coordenador, self.professor)
        chamada = Chamada.objects.get()
        self.client.force_login(self.professor)
        self.client.get(reverse("videochamadas:sala", args=[chamada.pk]))
        self.assertIsNotNone(Alerta.objects.get().lido_em)

    def test_link_do_jitsi_leva_o_nome_e_o_assunto(self):
        self.chamar(self.coordenador, self.professor, assunto='Reunião "urgente"')
        chamada = Chamada.objects.get()
        link = chamada.link_do_jitsi(self.professor)
        self.assertTrue(link.startswith(f"https://meet.jit.si/{chamada.sala}#"))
        # Os valores vão em JSON: aspas em volta e aspas internas escapadas.
        self.assertIn('userInfo.displayName="Profa. Ana Dias"', unquote(link))
        self.assertIn('config.subject="Reunião \\"urgente\\""', unquote(link))
        # Nada de espaço ou aspas soltas no endereço.
        self.assertNotIn(" ", link)
        self.assertNotIn('"', link)

    # --- Encerrar e histórico ---

    def test_encerrar_a_chamada(self):
        self.chamar(self.coordenador, self.professor)
        chamada = Chamada.objects.get()
        self.client.force_login(self.professor)  # qualquer um dos dois pode encerrar
        resposta = self.client.post(reverse("videochamadas:encerrar", args=[chamada.pk]))
        self.assertRedirects(resposta, reverse("videochamadas:inicio"))
        chamada.refresh_from_db()
        self.assertIsNotNone(chamada.encerrada_em)
        self.assertFalse(chamada.em_andamento)

        resposta = self.client.get(reverse("videochamadas:sala", args=[chamada.pk]))
        self.assertNotContains(resposta, "meet.jit.si")
        self.assertContains(resposta, "Chamar de novo")

    def test_encerrar_so_aceita_post(self):
        self.chamar(self.coordenador, self.professor)
        chamada = Chamada.objects.get()
        url = reverse("videochamadas:encerrar", args=[chamada.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_chamada_esquecida_deixa_de_estar_em_andamento(self):
        chamada = Chamada.objects.create(
            criada_por=self.coordenador,
            convidado=self.professor,
            criada_em=timezone.now() - DURACAO_MAXIMA - timedelta(minutes=1),
        )
        self.assertFalse(chamada.em_andamento)
        self.assertEqual(chamada.situacao, "Encerrada")

    def test_historico_mostra_so_as_chamadas_da_pessoa(self):
        Chamada.objects.create(
            criada_por=self.coordenador, convidado=self.professor, assunto="Minha chamada"
        )
        Chamada.objects.create(
            criada_por=self.outro_coordenador, convidado=self.outro_professor, assunto="De outros"
        )
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("videochamadas:inicio"))
        self.assertContains(resposta, "Minha chamada")
        self.assertContains(resposta, "Recebida")
        self.assertNotContains(resposta, "De outros")

    def test_historico_vazio(self):
        self.client.force_login(self.coordenador)
        self.assertContains(self.client.get(reverse("videochamadas:inicio")), "Nenhuma chamada ainda")

    def test_sem_ninguem_para_chamar(self):
        Usuario.objects.filter(perfil="COORDENADOR").update(is_active=False)
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("videochamadas:inicio"))
        self.assertContains(resposta, "Nenhum coordenador ativo")
        self.assertNotContains(resposta, "Chamar agora")

    def test_menu_mostra_videochamadas_para_professor_e_coordenacao(self):
        for pessoa in (self.coordenador, self.professor):
            with self.subTest(pessoa=pessoa.matricula):
                self.client.force_login(pessoa)
                resposta = self.client.get(reverse("videochamadas:inicio"))
                self.assertContains(resposta, f'href="{reverse("videochamadas:inicio")}"')
