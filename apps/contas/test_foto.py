"""Foto de perfil: quem pode enviar, o que é aceito e como ela é entregue."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.academico.models import ArquivoAnexo

from .foto import TAMANHO_MAXIMO_FOTO
from .test_login import SENHA, criar_usuarios

# Só os primeiros bytes importam para a conferência do tipo.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def imagem(nome="foto.png", conteudo=PNG, tipo="image/png"):
    return SimpleUploadedFile(nome, conteudo, content_type=tipo)


class FotoDePerfilTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()

    def entrar(self, perfil="ALUNO"):
        usuario = self.usuarios[perfil]
        self.client.login(matricula=usuario.matricula, password=SENHA)
        return usuario

    def enviar(self, arquivo, aceite=True, proxima="/aluno/"):
        dados = {"foto": arquivo, "proxima": proxima}
        if aceite:
            dados["aceite"] = "on"
        return self.client.post(reverse("contas:foto_enviar"), dados)

    # --- Permissões ---

    def test_visitante_vai_para_o_login(self):
        for rota in ("contas:foto", "contas:foto_enviar", "contas:foto_remover"):
            resposta = self.client.get(reverse(rota))
            self.assertEqual(resposta.status_code, 302, rota)
            self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_admin_nao_usa_a_foto_do_portal(self):
        self.entrar("ADMIN")
        self.assertEqual(self.client.get(reverse("contas:foto")).status_code, 403)
        self.assertEqual(self.enviar(imagem()).status_code, 403)

    def test_os_tres_perfis_enviam_a_propria_foto(self):
        for perfil in ("ALUNO", "PROFESSOR", "COORDENADOR"):
            with self.subTest(perfil=perfil):
                usuario = self.entrar(perfil)
                self.enviar(imagem())
                usuario.refresh_from_db()
                self.assertTrue(usuario.foto.name.startswith("fotos/"))
                self.client.logout()

    def test_enviar_so_aceita_post(self):
        self.entrar()
        self.assertEqual(self.client.get(reverse("contas:foto_enviar")).status_code, 405)

    # --- Regras do envio ---

    def test_sem_confirmar_as_regras_a_foto_nao_e_salva(self):
        usuario = self.entrar()
        resposta = self.enviar(imagem(), aceite=False)
        usuario.refresh_from_db()
        self.assertFalse(usuario.foto)
        self.assertContains(self.client.get(resposta["Location"]), "Confirme que leu as regras")

    def test_aceita_jpg_png_e_webp(self):
        usuario = self.entrar()
        for nome, conteudo in (("a.jpg", JPEG), ("b.png", PNG), ("c.webp", WEBP)):
            with self.subTest(nome=nome):
                self.enviar(imagem(nome, conteudo))
                usuario.refresh_from_db()
                self.assertTrue(usuario.foto.name.endswith(nome.split(".")[1]))

    def test_recusa_arquivo_que_so_tem_nome_de_imagem(self):
        usuario = self.entrar()
        self.enviar(imagem("foto.png", b"<html><script>alert(1)</script></html>"))
        usuario.refresh_from_db()
        self.assertFalse(usuario.foto)

    def test_recusa_svg(self):
        usuario = self.entrar()
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.enviar(imagem("foto.svg", svg, "image/svg+xml"))
        usuario.refresh_from_db()
        self.assertFalse(usuario.foto)

    def test_recusa_foto_acima_de_2_mb(self):
        usuario = self.entrar()
        grande = PNG + b"\x00" * TAMANHO_MAXIMO_FOTO
        self.enviar(imagem(conteudo=grande))
        usuario.refresh_from_db()
        self.assertFalse(usuario.foto)

    def test_nome_do_arquivo_e_sorteado(self):
        usuario = self.entrar()
        self.enviar(imagem("Mariana Oliveira RG.png"))
        usuario.refresh_from_db()
        self.assertNotIn("Mariana", usuario.foto.name)

    def test_trocar_a_foto_apaga_a_antiga_do_banco(self):
        usuario = self.entrar()
        self.enviar(imagem("a.png"))
        usuario.refresh_from_db()
        antiga = usuario.foto.name
        self.enviar(imagem("b.jpg", JPEG))
        self.assertFalse(ArquivoAnexo.objects.filter(nome=antiga).exists())
        self.assertEqual(ArquivoAnexo.objects.filter(nome__startswith="fotos/").count(), 1)

    def test_remover_volta_para_as_iniciais(self):
        usuario = self.entrar()
        self.enviar(imagem())
        self.client.post(reverse("contas:foto_remover"), {"proxima": "/aluno/"})
        usuario.refresh_from_db()
        self.assertEqual(usuario.foto.name, "")
        self.assertFalse(ArquivoAnexo.objects.filter(nome__startswith="fotos/").exists())

    def test_volta_so_para_enderecos_do_proprio_site(self):
        self.entrar()
        resposta = self.enviar(imagem(), proxima="https://site-malicioso.com/")
        self.assertEqual(resposta["Location"], reverse("contas:inicio"))
        resposta = self.enviar(imagem(), proxima="/aluno/notas/")
        self.assertEqual(resposta["Location"], "/aluno/notas/")

    # --- Entrega da foto ---

    def test_sem_foto_responde_404(self):
        self.entrar()
        self.assertEqual(self.client.get(reverse("contas:foto")).status_code, 404)

    def test_entrega_a_foto_com_o_tipo_do_conteudo(self):
        self.entrar()
        self.enviar(imagem("foto.webp", WEBP))
        resposta = self.client.get(reverse("contas:foto"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "image/webp")
        self.assertEqual(resposta.content, WEBP)
        self.assertIn("private", resposta["Cache-Control"])
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")

    def test_cada_um_ve_so_a_propria_foto(self):
        self.entrar("ALUNO")
        self.enviar(imagem())
        self.client.logout()
        self.entrar("PROFESSOR")  # o professor não tem foto
        self.assertEqual(self.client.get(reverse("contas:foto")).status_code, 404)

    # --- Tela ---

    def test_topo_mostra_o_avatar_que_abre_a_janela_com_as_regras(self):
        self.entrar()
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertContains(resposta, 'data-abrir-modal="janela-foto"')
        self.assertContains(resposta, "sujeito a penalizações")
        self.assertNotContains(resposta, reverse("contas:foto") + "?v=")  # ainda sem foto

    def test_com_foto_o_topo_mostra_a_imagem(self):
        self.entrar()
        self.enviar(imagem())
        resposta = self.client.get(reverse("aluno:painel"))
        self.assertContains(resposta, reverse("contas:foto") + "?v=")
        self.assertContains(resposta, "Remover foto atual")
