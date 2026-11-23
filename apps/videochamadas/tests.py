"""Testes das videochamadas: quem chama quem, quem entra na sala, convite no sino e histórico.

VideochamadasTests roda no modo "jitsi" (plano B) e confere que ele continua como antes.
SinalizacaoTests confere a sala própria: as rotas sinal/ e ice/.
As permissões por perfil (aluno e ADMIN levam 403) também estão na varredura de
apps/contas/test_permissoes.py.
"""

import json
from datetime import timedelta
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.professor.tests import HASH_RAPIDO

from .forms import pessoas_para_chamar
from .models import DURACAO_MAXIMA, Chamada, SinalChamada, nome_na_chamada
from .views import LIMITE_DO_SINAL, STUN_PADRAO

Usuario = get_user_model()


@override_settings(
    PASSWORD_HASHERS=HASH_RAPIDO, JITSI_SERVIDOR="https://meet.jit.si", VIDEO_MODO="jitsi"
)
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

    # --- Modo jitsi (plano B) ---

    def test_modo_jitsi_mantem_a_sala_antiga(self):
        self.chamar(self.coordenador, self.professor)
        chamada = Chamada.objects.get()
        resposta = self.client.get(reverse("videochamadas:sala", args=[chamada.pk]))
        self.assertContains(resposta, "Entrar na chamada")
        self.assertNotContains(resposta, "data-sala-propria")
        self.assertNotContains(resposta, "chamada.js")
        self.assertContains(self.client.get(reverse("videochamadas:inicio")), "Jitsi Meet, em outra aba")

    def test_modo_jitsi_desliga_a_sinalizacao(self):
        self.chamar(self.coordenador, self.professor)
        chamada = Chamada.objects.get()
        for rota in ("videochamadas:sinal", "videochamadas:ice"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota, args=[chamada.pk])).status_code, 404)


SEM_TURN = {"TURN_URLS": [], "TURN_USUARIO": "", "TURN_SENHA": ""}


@override_settings(
    PASSWORD_HASHERS=HASH_RAPIDO, JITSI_SERVIDOR="https://meet.jit.si", VIDEO_MODO="proprio",
    **SEM_TURN,
)
class SinalizacaoTests(TestCase):
    """Sala própria: os navegadores trocam sinais pelo portal (sinal/) e pedem os servidores
    STUN/TURN (ice/). O vídeo não passa pelo portal, então não há nada de vídeo para testar aqui."""

    @classmethod
    def setUpTestData(cls):
        cls.coordenador = Usuario.objects.create_user("coord", "senha", perfil="COORDENADOR")
        cls.professor = Usuario.objects.create_user("prof", "senha", perfil="PROFESSOR")
        cls.outro_coordenador = Usuario.objects.create_user("coord2", "senha", perfil="COORDENADOR")
        cls.outro_professor = Usuario.objects.create_user("prof2", "senha", perfil="PROFESSOR")
        cls.aluno = Usuario.objects.create_user("aluno", "senha", perfil="ALUNO")
        cls.admin = Usuario.objects.create_user("admin", "senha", perfil="ADMIN", is_staff=True)
        cls.chamada = Chamada.objects.create(criada_por=cls.coordenador, convidado=cls.professor)

    def url_sinal(self, chamada=None, depois=None):
        url = reverse("videochamadas:sinal", args=[(chamada or self.chamada).pk])
        return url if depois is None else f"{url}?depois={depois}"

    def url_ice(self, chamada=None):
        return reverse("videochamadas:ice", args=[(chamada or self.chamada).pk])

    def enviar(self, pessoa, tipo="oferta", conteudo=None, chamada=None):
        self.client.force_login(pessoa)
        corpo = {"tipo": tipo, "conteudo": conteudo if conteudo is not None else {"sessao": "a1"}}
        return self.client.post(
            self.url_sinal(chamada), json.dumps(corpo), content_type="application/json"
        )

    def ler(self, pessoa, depois=0, chamada=None):
        self.client.force_login(pessoa)
        return self.client.get(self.url_sinal(chamada, depois))

    # --- Quem pode usar as rotas ---

    def test_quem_nao_participa_recebe_404(self):
        for pessoa in (self.outro_coordenador, self.outro_professor):
            with self.subTest(pessoa=pessoa.matricula):
                self.assertEqual(self.ler(pessoa).status_code, 404)
                self.assertEqual(self.enviar(pessoa).status_code, 404)
                self.assertEqual(self.client.get(self.url_ice()).status_code, 404)
        self.assertFalse(SinalChamada.objects.exists())

    def test_aluno_e_admin_recebem_403(self):
        for pessoa in (self.aluno, self.admin):
            with self.subTest(pessoa=pessoa.matricula):
                self.assertEqual(self.ler(pessoa).status_code, 403)
                self.assertEqual(self.enviar(pessoa).status_code, 403)
                self.assertEqual(self.client.get(self.url_ice()).status_code, 403)

    def test_visitante_vai_para_o_login(self):
        for url in (self.url_sinal(), self.url_ice()):
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 302)
                self.assertTrue(resposta.url.startswith(reverse("contas:entrar")))

    def test_post_exige_o_token_csrf_no_cabecalho(self):
        navegador = Client(enforce_csrf_checks=True)
        navegador.force_login(self.coordenador)
        navegador.get(reverse("videochamadas:sala", args=[self.chamada.pk]))  # recebe o cookie
        corpo = json.dumps({"tipo": "entrei", "conteudo": {"sessao": "a1"}})
        sem_token = navegador.post(self.url_sinal(), corpo, content_type="application/json")
        self.assertEqual(sem_token.status_code, 403)
        com_token = navegador.post(
            self.url_sinal(), corpo, content_type="application/json",
            headers={"X-CSRFToken": navegador.cookies["csrftoken"].value},
        )
        self.assertEqual(com_token.status_code, 201)

    # --- Quem lê o quê ---

    def test_sinal_vai_so_para_o_outro_participante(self):
        resposta = self.enviar(self.coordenador, "oferta", {"sessao": "a1", "descricao": {"sdp": "v=0"}})
        self.assertEqual(resposta.status_code, 201)
        sinal = SinalChamada.objects.get()
        self.assertEqual((sinal.de, sinal.para), (self.coordenador, self.professor))

        recebidos = self.ler(self.professor).json()["sinais"]
        self.assertEqual(
            recebidos,
            [{"id": sinal.id, "tipo": "oferta", "conteudo": {"sessao": "a1", "descricao": {"sdp": "v=0"}}}],
        )
        # Quem mandou não lê o próprio sinal.
        self.assertEqual(self.ler(self.coordenador).json()["sinais"], [])

    def test_ninguem_le_sinal_de_outra_chamada(self):
        outra = Chamada.objects.create(criada_por=self.coordenador, convidado=self.outro_professor)
        self.enviar(self.coordenador, "oferta", chamada=self.chamada)  # para o professor
        # O outro professor participa de outra chamada com o mesmo coordenador: não vê nada.
        self.assertEqual(self.ler(self.outro_professor, chamada=outra).json()["sinais"], [])
        self.assertEqual(self.ler(self.outro_professor, chamada=self.chamada).status_code, 404)

    def test_depois_devolve_so_o_que_e_novo(self):
        ids = [self.enviar(self.coordenador, "candidato").json()["id"] for _ in range(3)]
        recebidos = self.ler(self.professor, depois=ids[0]).json()["sinais"]
        self.assertEqual([s["id"] for s in recebidos], ids[1:])
        self.assertEqual(self.ler(self.professor, depois=ids[-1]).json()["sinais"], [])
        for valor in ("abc", "-1"):
            with self.subTest(depois=valor):
                self.assertEqual(self.ler(self.professor, depois=valor).status_code, 400)

    def test_consulta_de_cada_segundo_usa_poucas_consultas_ao_banco(self):
        self.enviar(self.coordenador, "oferta")
        self.client.force_login(self.professor)
        # 2 do login (sessão e usuário) + 1 da chamada + 1 dos sinais.
        with self.assertNumQueries(4):
            self.client.get(self.url_sinal(depois=0))

    # --- O que é recusado ---

    def test_chamada_encerrada_nao_aceita_sinal(self):
        self.chamada.encerrada_em = timezone.now()
        self.chamada.save()
        resposta = self.enviar(self.coordenador, "entrei")
        self.assertEqual(resposta.status_code, 400)
        self.assertTrue(resposta.json()["encerrada"])
        self.assertFalse(SinalChamada.objects.exists())
        self.assertEqual(self.ler(self.professor).json(), {"sinais": [], "encerrada": True})
        self.assertEqual(self.client.get(self.url_ice()).status_code, 400)

    def test_chamada_de_mais_de_3_horas_nao_aceita_sinal(self):
        Chamada.objects.filter(pk=self.chamada.pk).update(
            criada_em=timezone.now() - DURACAO_MAXIMA - timedelta(minutes=1)
        )
        self.assertEqual(self.enviar(self.coordenador, "entrei").status_code, 400)

    def test_pedidos_invalidos_dao_400(self):
        self.client.force_login(self.coordenador)
        grande = {"sessao": "a1", "sdp": "x" * LIMITE_DO_SINAL}
        corpos = {
            "tipo desconhecido": {"tipo": "video", "conteudo": {}},
            "sem tipo": {"conteudo": {}},
            "conteúdo que não é objeto": {"tipo": "oferta", "conteudo": "texto"},
            "conteúdo grande demais": {"tipo": "oferta", "conteudo": grande},
            "JSON que não é objeto": ["oferta"],
        }
        for motivo, corpo in corpos.items():
            with self.subTest(motivo=motivo):
                resposta = self.client.post(
                    self.url_sinal(), json.dumps(corpo), content_type="application/json"
                )
                self.assertEqual(resposta.status_code, 400)
        for texto in ("isto não é JSON", "[" * 5000):
            with self.subTest(corpo=texto[:20]):
                resposta = self.client.post(self.url_sinal(), texto, content_type="application/json")
                self.assertEqual(resposta.status_code, 400)
        self.assertFalse(SinalChamada.objects.exists())

    def test_sinal_sem_conteudo_e_aceito(self):
        self.client.force_login(self.professor)
        resposta = self.client.post(
            self.url_sinal(), json.dumps({"tipo": "saiu"}), content_type="application/json"
        )
        self.assertEqual(resposta.status_code, 201)

    # --- Faxina dos sinais ---

    def test_encerrar_apaga_os_sinais(self):
        self.enviar(self.coordenador, "oferta")
        self.client.post(reverse("videochamadas:encerrar", args=[self.chamada.pk]))
        self.assertFalse(SinalChamada.objects.exists())

    def test_entrar_apaga_os_sinais_de_mais_de_2_horas(self):
        antigo = SinalChamada.objects.create(
            chamada=self.chamada, de=self.professor, para=self.coordenador, tipo="entrei",
            criado_em=timezone.now() - timedelta(hours=2, minutes=1),
        )
        recente = SinalChamada.objects.create(
            chamada=self.chamada, de=self.professor, para=self.coordenador, tipo="entrei"
        )
        self.enviar(self.coordenador, "entrei")
        self.assertFalse(SinalChamada.objects.filter(pk=antigo.pk).exists())
        self.assertTrue(SinalChamada.objects.filter(pk=recente.pk).exists())

    # --- Servidores STUN/TURN ---

    def test_ice_sem_turn_devolve_so_o_stun(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_ice())
        self.assertEqual(resposta.json(), {"iceServers": [{"urls": [STUN_PADRAO]}]})
        self.assertIn("no-cache", resposta["Cache-Control"])

    @override_settings(
        TURN_URLS=["turn:turn.exemplo.com:80", "turns:turn.exemplo.com:443?transport=tcp"],
        TURN_USUARIO="usuario-teste",
        TURN_SENHA="senha-teste",
    )
    def test_ice_inclui_o_turn_quando_configurado(self):
        self.client.force_login(self.coordenador)
        servidores = self.client.get(self.url_ice()).json()["iceServers"]
        self.assertEqual(servidores[0], {"urls": [STUN_PADRAO]})
        self.assertEqual(
            servidores[1],
            {
                "urls": ["turn:turn.exemplo.com:80", "turns:turn.exemplo.com:443?transport=tcp"],
                "username": "usuario-teste",
                "credential": "senha-teste",
            },
        )

    @override_settings(TURN_URLS=["turn:turn.exemplo.com:80"], TURN_USUARIO="usuario-teste")
    def test_turn_incompleto_fica_de_fora(self):
        self.client.force_login(self.coordenador)
        self.assertEqual(len(self.client.get(self.url_ice()).json()["iceServers"]), 1)

    @override_settings(
        TURN_URLS=["turn:turn.exemplo.com:80"], TURN_USUARIO="usuario-teste", TURN_SENHA="senha-teste"
    )
    def test_credenciais_do_turn_nao_aparecem_na_pagina(self):
        # Elas só chegam pela rota ice/, nunca escritas no HTML ou no JavaScript.
        self.client.force_login(self.coordenador)
        resposta = self.client.get(reverse("videochamadas:sala", args=[self.chamada.pk]))
        self.assertNotContains(resposta, "senha-teste")
        self.assertNotContains(resposta, "turn.exemplo.com")

    # --- Tela da sala própria ---

    def test_sala_propria_dentro_do_portal(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("videochamadas:sala", args=[self.chamada.pk]))
        self.assertContains(resposta, "data-sala-propria")
        self.assertContains(resposta, 'data-sou-quem-chamou="false"')
        self.assertContains(resposta, f'data-url-sinal="{self.url_sinal()}"')
        self.assertContains(resposta, "js/chamada.js")
        self.assertContains(resposta, "Não conectou? Entrar pelo Jitsi")
        self.assertContains(resposta, f"https://meet.jit.si/{self.chamada.sala}#")
        self.assertNotContains(resposta, "Entrar na chamada")

    def test_sala_propria_tem_os_controles_e_a_conversa(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("videochamadas:sala", args=[self.chamada.pk]))
        for controle in ("data-botao-microfone", "data-botao-camera", "data-botao-tela", "data-botao-tela-cheia"):
            self.assertContains(resposta, controle)
        # A conversa vai pelo canal de dados do WebRTC: o formulário não aponta para o portal.
        self.assertContains(resposta, '<form data-form-conversa class="flex gap-2 border-t border-[#E5E9F0] p-3" autocomplete="off">')
        self.assertContains(resposta, "não são gravadas")
        self.assertContains(resposta, f'data-nome-do-outro="{nome_na_chamada(self.coordenador)}"')

    def test_nome_do_outro_e_escapado_na_sala(self):
        # O nome vai num atributo lido pelo chamada.js: precisa chegar escapado.
        self.coordenador.first_name = 'Ana" onclick="x'
        self.coordenador.save()
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("videochamadas:sala", args=[self.chamada.pk]))
        self.assertContains(resposta, "Ana&quot; onclick=&quot;x")
        self.assertNotContains(resposta, 'Ana" onclick="x')

    def test_sala_comeca_depois_dos_sinais_antigos(self):
        # Sinais de uma aba que já foi fechada não são lidos de novo.
        ultimo = self.enviar(self.coordenador, "entrei").json()["id"]
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("videochamadas:sala", args=[self.chamada.pk]))
        self.assertContains(resposta, f'data-ultimo-sinal="{ultimo}"')

    def test_chamada_encerrada_nao_abre_a_sala_propria(self):
        self.chamada.encerrada_em = timezone.now()
        self.chamada.save()
        self.client.force_login(self.coordenador)
        resposta = self.client.get(reverse("videochamadas:sala", args=[self.chamada.pk]))
        self.assertNotContains(resposta, "data-sala-propria")
        self.assertNotContains(resposta, "chamada.js")
        self.assertContains(resposta, "Esta chamada foi encerrada.")

    def test_inicio_explica_que_a_chamada_e_no_portal(self):
        self.client.force_login(self.coordenador)
        self.assertContains(
            self.client.get(reverse("videochamadas:inicio")), "A chamada acontece aqui mesmo, no portal."
        )
