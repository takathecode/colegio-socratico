"""Testes dos alertas automáticos: regras, tarefas do Celery, e-mail e telas.

Nos testes o Celery roda as tarefas na hora (CELERY_TASK_ALWAYS_EAGER em settings.py),
então não é preciso ter Redis. O Django guarda os e-mails em mail.outbox, sem enviar nada.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.academico.models import Frequencia, Justificativa, Matricula
from apps.analytics.models import RiscoEvasao
from apps.professor.tests import HASH_RAPIDO, BaseProfessorMixin

from . import regras, tasks
from .fila import enfileirar
from .models import Alerta

Usuario = get_user_model()

# Um caminho que não existe: a rotina roda como se o modelo de evasão não estivesse treinado.
SEM_MODELO = Path("ml-inexistente") / "modelo.joblib"


class BaseAlertasMixin(BaseProfessorMixin):
    """A turma do professor: Bia (nota 8, presente) vai bem; Caio (nota 4, faltou) vai mal."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # O mixin do professor dá a Bia uma falta na disciplina do outro professor.
        # Aqui ela vira presença, para a Bia ficar regular e só o Caio receber alertas.
        cls.justificativa_do_outro.delete()
        Frequencia.objects.filter(matricula=cls.matricula).update(presente=True)
        cls.aluno2.email = "caio@x.com"
        cls.aluno2.save()
        cls.coordenador = Usuario.objects.create_user(
            "coord", "senha", perfil="COORDENADOR", first_name="Lia", email="lia@x.com"
        )

    def tipos_de(self, usuario):
        return set(Alerta.objects.filter(destinatario=usuario).values_list("tipo", flat=True))

    def criar_risco_alto(self, matricula):
        return RiscoEvasao.objects.create(
            matricula=matricula,
            probabilidade=Decimal("82.5"),
            nivel=RiscoEvasao.Nivel.ALTO,
            motivos=["Média 4,0, abaixo de 6"],
            frequencia=Decimal("0"),
            media=Decimal("4"),
            tendencia=Decimal("0"),
            justificativas_pendentes=1,
        )


class RegrasTests(BaseAlertasMixin, TestCase):
    def test_frequencia_e_media_baixas_avisam_o_aluno(self):
        regras.alertas_do_dia()
        self.assertEqual(
            self.tipos_de(self.aluno2), {Alerta.Tipo.FREQUENCIA_BAIXA, Alerta.Tipo.MEDIA_BAIXA}
        )
        self.assertEqual(self.tipos_de(self.aluno), set())  # Bia está regular

        frequencia = Alerta.objects.get(destinatario=self.aluno2, tipo=Alerta.Tipo.FREQUENCIA_BAIXA)
        self.assertEqual(frequencia.gravidade, Alerta.Gravidade.RISCO)
        self.assertTrue(frequencia.por_email)
        self.assertIn("0,0%", frequencia.texto)
        self.assertEqual(frequencia.link, reverse("aluno:frequencia"))

    def test_mesmo_assunto_nao_se_repete_em_7_dias(self):
        self.assertEqual(len(regras.alertas_do_dia()), 2)
        self.assertEqual(regras.alertas_do_dia(), [])  # no dia seguinte, nada de novo

        # Passada a janela, o aluno é lembrado de novo.
        Alerta.objects.update(criado_em=timezone.now() - timedelta(days=8))
        self.assertEqual(len(regras.alertas_do_dia()), 2)

    def test_aluno_inativo_ou_com_matricula_trancada_nao_recebe(self):
        Matricula.objects.filter(pk=self.matricula2.pk).update(
            situacao=Matricula.Situacao.TRANCADA
        )
        self.assertEqual(regras.alertas_do_dia(), [])

        Matricula.objects.filter(pk=self.matricula2.pk).update(situacao=Matricula.Situacao.ATIVA)
        Usuario.objects.filter(pk=self.aluno2.pk).update(is_active=False)
        self.assertEqual(regras.alertas_do_dia(), [])

    def test_risco_alto_avisa_os_coordenadores_ativos(self):
        inativo = Usuario.objects.create_user("coord2", "senha", perfil="COORDENADOR", is_active=False)
        self.criar_risco_alto(self.matricula2)
        regras.alertas_do_dia()

        alerta = Alerta.objects.get(tipo=Alerta.Tipo.RISCO_EVASAO)
        self.assertEqual(alerta.destinatario, self.coordenador)
        self.assertEqual(self.tipos_de(inativo), set())
        self.assertIn("82,5%", alerta.texto)
        self.assertIn("Média 4,0, abaixo de 6", alerta.texto)
        self.assertIn("busca=aluno2", alerta.link)

    def test_risco_medio_nao_gera_alerta(self):
        risco = self.criar_risco_alto(self.matricula2)
        risco.nivel = RiscoEvasao.Nivel.MEDIO
        risco.save()
        regras.alertas_do_dia()
        self.assertEqual(self.tipos_de(self.coordenador), set())

    def test_lembra_o_professor_de_justificativa_parada_ha_3_dias(self):
        regras.alertas_do_dia()
        self.assertEqual(self.tipos_de(self.professor), set())  # enviada hoje: ainda no prazo

        Justificativa.objects.update(criada_em=timezone.now() - timedelta(days=4))
        regras.alertas_do_dia()
        alerta = Alerta.objects.get(destinatario=self.professor)
        self.assertEqual(alerta.tipo, Alerta.Tipo.JUSTIFICATIVA_ATRASADA)
        self.assertIn("1 justificativa aguarda", alerta.texto)
        self.assertFalse(alerta.por_email)
        self.assertEqual(self.tipos_de(self.outro_professor), set())

    def test_justificativa_avaliada_nao_gera_lembrete(self):
        Justificativa.objects.update(
            criada_em=timezone.now() - timedelta(days=4), status=Justificativa.Status.APROVADA
        )
        regras.alertas_do_dia()
        self.assertEqual(self.tipos_de(self.professor), set())


@override_settings(MODELO_EVASAO=SEM_MODELO)
class TarefasTests(BaseAlertasMixin, TestCase):
    def test_rotina_diaria_sem_modelo_treinado_roda_as_outras_regras(self):
        with self.assertLogs("apps.alertas.tasks", "WARNING"):
            resumo = tasks.rotina_diaria()
        self.assertEqual(resumo, {"Frequência abaixo do mínimo": 1, "Média abaixo de 6": 1})

    def test_so_os_alertas_em_risco_vao_por_email(self):
        with self.assertLogs("apps.alertas.tasks", "WARNING"):
            tasks.rotina_diaria()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["caio@x.com"])
        self.assertTrue(mail.outbox[0].subject.startswith("[Instituto Socrático]"))
        self.assertIn("http://127.0.0.1:8000/aluno/", mail.outbox[0].body)
        self.assertFalse(Alerta.objects.filter(email_enviado_em__isnull=True).exists())

        # Aviso informativo (nota publicada) fica só no sistema.
        tasks.avisar_notas_publicadas(self.avaliacao.pk)
        self.assertEqual(len(mail.outbox), 2)

    def test_pessoa_sem_email_so_recebe_no_sistema(self):
        self.aluno2.email = ""
        self.aluno2.save()
        with self.assertLogs("apps.alertas.tasks", "WARNING"):
            tasks.rotina_diaria()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Alerta.objects.filter(destinatario=self.aluno2).count(), 2)

    def test_falha_no_email_sem_fila_nao_derruba_a_rotina(self):
        with (
            mock.patch("apps.alertas.tasks.send_mail", side_effect=OSError("servidor fora")),
            self.assertLogs("apps.alertas.tasks", "WARNING"),
        ):
            tasks.rotina_diaria()
        # Os alertas ficam no sistema, e o e-mail fica marcado como não enviado.
        self.assertEqual(Alerta.objects.filter(email_enviado_em__isnull=True).count(), 2)

    def test_email_nao_e_enviado_duas_vezes(self):
        with self.assertLogs("apps.alertas.tasks", "WARNING"):
            tasks.rotina_diaria()
        alerta = Alerta.objects.filter(por_email=True).first()
        self.assertFalse(tasks.enviar_email(alerta.pk))
        self.assertEqual(len(mail.outbox), 2)

    def test_aviso_de_notas_publicadas(self):
        self.assertEqual(tasks.avisar_notas_publicadas(self.avaliacao.pk), 2)
        alerta = Alerta.objects.get(destinatario=self.aluno)
        self.assertEqual(alerta.tipo, Alerta.Tipo.NOTA_LANCADA)
        self.assertIn("A1 de Matemática", alerta.texto)
        self.assertNotIn("8", alerta.texto)  # a nota em si não vai no aviso
        # Corrigir a nota na mesma semana não gera outro aviso.
        self.assertEqual(tasks.avisar_notas_publicadas(self.avaliacao.pk), 0)

    def test_avaliacao_apagada_antes_da_tarefa(self):
        self.assertEqual(tasks.avisar_notas_publicadas(999999), 0)
        self.assertEqual(tasks.avisar_justificativa_avaliada(999999), 0)

    def test_justificativa_pendente_nao_gera_aviso(self):
        self.assertEqual(tasks.avisar_justificativa_avaliada(self.justificativa.pk), 0)


class FilaTests(TestCase):
    def test_sem_redis_a_tarefa_roda_na_hora(self):
        tarefa = mock.Mock()
        tarefa.name = "tarefa_de_teste"
        tarefa.delay.side_effect = OperationalError("conexão recusada")
        with self.assertLogs("apps.alertas.fila", "WARNING"):
            enfileirar(tarefa, 7)
        tarefa.apply.assert_called_once_with(args=(7,))

    def test_com_redis_a_tarefa_vai_para_a_fila(self):
        tarefa = mock.Mock()
        enfileirar(tarefa, 7)
        tarefa.delay.assert_called_once_with(7)
        tarefa.apply.assert_not_called()


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class AvisosDoProfessorTests(BaseAlertasMixin, TestCase):
    """As telas do professor colocam o aviso na fila depois de salvar (transaction.on_commit)."""

    def test_publicar_notas_avisa_os_alunos(self):
        self.client.force_login(self.professor)
        url = f"{reverse('professor:notas')}?oferta={self.oferta.pk}&avaliacao={self.avaliacao.pk}"
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                url, {f"nota_{self.matricula.pk}": "9", f"nota_{self.matricula2.pk}": "4"}
            )
        self.assertEqual(self.tipos_de(self.aluno), {Alerta.Tipo.NOTA_LANCADA})
        self.assertEqual(self.tipos_de(self.aluno2), {Alerta.Tipo.NOTA_LANCADA})

    def test_salvar_sem_alterar_nada_nao_avisa(self):
        self.client.force_login(self.professor)
        url = f"{reverse('professor:notas')}?oferta={self.oferta.pk}&avaliacao={self.avaliacao.pk}"
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                url, {f"nota_{self.matricula.pk}": "8", f"nota_{self.matricula2.pk}": "4"}
            )
        self.assertFalse(Alerta.objects.exists())

    def test_rejeitar_justificativa_avisa_o_aluno(self):
        self.client.force_login(self.professor)
        prefixo = f"j{self.justificativa.pk}"
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("professor:avaliar_justificativa", args=[self.justificativa.pk]),
                {f"{prefixo}-decisao": "REJEITADA", f"{prefixo}-resposta": "Falta o atestado."},
            )
        alerta = Alerta.objects.get(destinatario=self.aluno2)
        self.assertEqual(alerta.tipo, Alerta.Tipo.JUSTIFICATIVA_AVALIADA)
        self.assertEqual(alerta.gravidade, Alerta.Gravidade.ATENCAO)
        self.assertEqual(alerta.titulo, "Justificativa rejeitada")
        self.assertIn("Falta o atestado.", alerta.texto)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO)
class NotificacoesTests(BaseAlertasMixin, TestCase):
    def setUp(self):
        regras.alertas_do_dia()  # Caio recebe dois alertas
        self.alerta = Alerta.objects.filter(destinatario=self.aluno2).first()

    def test_visitante_vai_para_o_login(self):
        resposta = self.client.get(reverse("alertas:lista"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_admin_recebe_403_e_nao_tem_sino(self):
        admin = Usuario.objects.create_superuser("admin", "senha")
        self.client.force_login(admin)
        resposta = self.client.get(reverse("alertas:lista"))
        self.assertEqual(resposta.status_code, 403)
        self.assertNotIn("sino_nao_lidos", resposta.context)

    def test_lista_mostra_so_os_alertas_da_pessoa(self):
        self.client.force_login(self.aluno)
        resposta = self.client.get(reverse("alertas:lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(resposta.context["pagina"].object_list), 0)
        self.assertContains(resposta, "Nenhuma notificação ainda")

    def test_sino_conta_os_nao_lidos(self):
        self.client.force_login(self.aluno2)
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertEqual(resposta.context["sino_nao_lidos"], 2)
        self.assertContains(resposta, "Notificações: 2 não lidas")

    def test_abrir_marca_como_lido_e_leva_para_a_tela(self):
        self.client.force_login(self.aluno2)
        resposta = self.client.post(reverse("alertas:abrir", args=[self.alerta.pk]))
        self.assertRedirects(resposta, self.alerta.link, fetch_redirect_response=False)
        self.alerta.refresh_from_db()
        self.assertIsNotNone(self.alerta.lido_em)

    def test_alerta_de_outra_pessoa_da_404(self):
        self.client.force_login(self.aluno)
        resposta = self.client.post(reverse("alertas:abrir", args=[self.alerta.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_abrir_exige_post(self):
        self.client.force_login(self.aluno2)
        resposta = self.client.get(reverse("alertas:abrir", args=[self.alerta.pk]))
        self.assertEqual(resposta.status_code, 405)

    def test_marcar_todos_como_lidos(self):
        self.client.force_login(self.aluno2)
        resposta = self.client.post(
            reverse("alertas:marcar_todos"), {"proxima": reverse("aluno:painel")}
        )
        self.assertRedirects(resposta, reverse("aluno:painel"), fetch_redirect_response=False)
        self.assertFalse(Alerta.objects.filter(lido_em__isnull=True).exists())

    def test_marcar_todos_nao_redireciona_para_outro_site(self):
        self.client.force_login(self.aluno2)
        resposta = self.client.post(
            reverse("alertas:marcar_todos"), {"proxima": "https://exemplo.com/"}
        )
        self.assertRedirects(resposta, reverse("alertas:lista"), fetch_redirect_response=False)

    def test_filtro_de_nao_lidos(self):
        self.alerta.lido_em = timezone.now()
        self.alerta.save()
        self.client.force_login(self.aluno2)
        resposta = self.client.get(reverse("alertas:lista"), {"filtro": "nao_lidos"})
        self.assertEqual(len(resposta.context["pagina"].object_list), 1)


@override_settings(PASSWORD_HASHERS=HASH_RAPIDO, MODELO_EVASAO=SEM_MODELO)
class CentralDeAlertasTests(BaseAlertasMixin, TestCase):
    def test_so_a_coordenacao_entra(self):
        for usuario in (self.aluno, self.professor):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.matricula):
                self.assertEqual(self.client.get(reverse("coordenacao:alertas")).status_code, 403)
                resposta = self.client.post(reverse("coordenacao:alertas_rotina"))
                self.assertEqual(resposta.status_code, 403)

    def test_rodar_rotina_agora_gera_os_alertas(self):
        self.client.force_login(self.coordenador)
        with self.assertLogs("apps.alertas.tasks", "WARNING"):
            resposta = self.client.post(reverse("coordenacao:alertas_rotina"), follow=True)
        self.assertContains(resposta, "Rotina de alertas iniciada")
        self.assertEqual(resposta.context["indicadores"]["total"], 2)
        self.assertEqual(resposta.context["indicadores"]["emails"], 2)
        self.assertContains(resposta, "Sua média está abaixo de 6")

    def test_filtros(self):
        regras.alertas_do_dia()
        self.client.force_login(self.coordenador)
        url = reverse("coordenacao:alertas")
        resposta = self.client.get(url, {"tipo": Alerta.Tipo.MEDIA_BAIXA})
        self.assertEqual(resposta.context["pagina"].paginator.count, 1)
        resposta = self.client.get(url, {"busca": "Caio"})
        self.assertEqual(resposta.context["pagina"].paginator.count, 2)
        resposta = self.client.get(url, {"leitura": "lidos"})
        self.assertContains(resposta, "Nenhum alerta encontrado")

    def test_menu_da_coordenacao_tem_alertas_ativo(self):
        self.client.force_login(self.coordenador)
        resposta = self.client.get(reverse("coordenacao:alertas"))
        item = next(i for i in resposta.context["menu_itens"] if i["nome"] == "Alertas")
        self.assertTrue(item["ativo"])
        self.assertEqual(item["url"], reverse("coordenacao:alertas"))
