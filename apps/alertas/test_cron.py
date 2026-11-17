"""Rota chamada pelo Cron da Vercel: só roda a rotina com o CRON_SECRET certo."""

from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

URL = reverse("cron_rotina_diaria")
ROTINA = "apps.alertas.cron.tasks.rotina_diaria"


@override_settings(CRON_SECRET="segredo-de-teste")
class CronDaVercelTests(TestCase):
    def test_com_o_segredo_certo_roda_a_rotina(self):
        with mock.patch(ROTINA, return_value={"Média abaixo de 6": 2}) as rotina:
            resposta = self.client.get(URL, HTTP_AUTHORIZATION="Bearer segredo-de-teste")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"ok": True, "alertas_novos": {"Média abaixo de 6": 2}})
        rotina.assert_called_once()

    def test_sem_segredo_ou_com_segredo_errado_responde_404(self):
        with mock.patch(ROTINA) as rotina:
            self.assertEqual(self.client.get(URL).status_code, 404)
            resposta = self.client.get(URL, HTTP_AUTHORIZATION="Bearer outro")
            self.assertEqual(resposta.status_code, 404)
        rotina.assert_not_called()

    def test_so_aceita_get(self):
        with mock.patch(ROTINA) as rotina:
            resposta = self.client.post(URL, HTTP_AUTHORIZATION="Bearer segredo-de-teste")
        self.assertEqual(resposta.status_code, 405)
        rotina.assert_not_called()

    @override_settings(CRON_SECRET="")
    def test_sem_cron_secret_configurado_a_rota_fica_desligada(self):
        with mock.patch(ROTINA) as rotina:
            resposta = self.client.get(URL, HTTP_AUTHORIZATION="Bearer ")
        self.assertEqual(resposta.status_code, 404)
        rotina.assert_not_called()

    def test_rotina_de_verdade_roda_sem_dados(self):
        # Sem mock: confere que a rotina real roda pela rota (sem modelo, só pula a evasão).
        resposta = self.client.get(URL, HTTP_AUTHORIZATION="Bearer segredo-de-teste")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])
