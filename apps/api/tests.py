"""Testes da API: token, permissões por perfil, escopo (404), números e arquivos.

Usa a mesma turma dos testes de relatórios: Matemática (Profa. Ana) e Física (Rui);
Bia tem 7 e 6,5 em Matemática (média 6,75, Em atenção) e Caio tem 4 (Em risco).
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.relatorios.tests import TIPO_EXCEL, BaseRelatoriosMixin

Usuario = get_user_model()


class BaseApiMixin(BaseRelatoriosMixin):
    client_class = APIClient

    def entrar(self, usuario):
        self.client.force_authenticate(usuario)

    def get(self, nome, *args, **parametros):
        return self.client.get(reverse(f"api:{nome}", args=args), parametros)


class TokenTests(BaseApiMixin, TestCase):
    def setUp(self):
        cache.clear()  # zera o limite de tentativas entre um teste e outro

    def pedir_token(self, matricula, senha):
        return self.client.post(reverse("api:token"), {"matricula": matricula, "senha": senha})

    def test_sem_login_responde_401(self):
        resposta = self.get("turma-list")
        self.assertEqual(resposta.status_code, 401)
        self.assertEqual(resposta["WWW-Authenticate"], "Token")

    def test_token_com_matricula_e_senha(self):
        resposta = self.pedir_token("2026001", "senha")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["perfil"], "ALUNO")

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {resposta.json()['token']}")
        eu = self.get("eu")
        self.assertEqual(eu.status_code, 200)
        self.assertEqual(eu.json()["ra"], "2026001")
        self.assertEqual(eu.json()["nome"], "Bia Reis")

    def test_pedir_de_novo_devolve_o_mesmo_token(self):
        primeiro = self.pedir_token("2026001", "senha").json()["token"]
        self.assertEqual(self.pedir_token("2026001", "senha").json()["token"], primeiro)

    def test_senha_errada_e_conta_desativada(self):
        self.assertEqual(self.pedir_token("2026001", "errada").status_code, 400)
        Usuario.objects.filter(pk=self.aluno.pk).update(is_active=False)
        self.assertEqual(self.pedir_token("2026001", "senha").status_code, 400)
        self.assertFalse(Token.objects.exists())

    def test_conta_desativada_perde_o_token(self):
        token = Token.objects.create(user=self.aluno)
        Usuario.objects.filter(pk=self.aluno.pk).update(is_active=False)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.get("eu").status_code, 401)

    def test_admin_nao_usa_a_api(self):
        Usuario.objects.create_superuser("admin", "senha", email="admin@exemplo.com")
        self.assertEqual(self.pedir_token("admin", "senha").status_code, 403)

    def test_apagar_o_token(self):
        token = self.pedir_token("prof", "senha").json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.client.delete(reverse("api:token")).status_code, 204)
        self.assertEqual(self.get("eu").status_code, 401)

    def test_limite_de_tentativas(self):
        for _ in range(10):
            self.pedir_token("2026001", "errada")
        self.assertEqual(self.pedir_token("2026001", "senha").status_code, 429)


class PermissoesTests(BaseApiMixin, TestCase):
    def test_admin_logado_recebe_403(self):
        self.entrar(Usuario.objects.create_superuser("admin", "senha", email="a@exemplo.com"))
        self.assertEqual(self.get("turma-list").status_code, 403)

    def test_api_so_consulta(self):
        self.entrar(self.coordenador)
        resposta = self.client.post(reverse("api:turma-list"), {"codigo": "T9"})
        self.assertEqual(resposta.status_code, 405)

    def test_endpoints_da_coordenacao(self):
        self.entrar(self.aluno)
        self.assertEqual(self.get("risco-list").status_code, 403)
        self.assertEqual(self.get("turma-desempenho", self.turma.pk).status_code, 403)
        self.assertEqual(self.get("oferta-desempenho", self.oferta.pk).status_code, 403)
        self.entrar(self.professor)
        self.assertEqual(self.get("risco-list").status_code, 403)
        self.assertEqual(self.get("matricula-list").status_code, 403)

    def test_documentacao_e_publica(self):
        self.assertEqual(self.client.get(reverse("api:docs")).status_code, 200)
        self.assertEqual(self.client.get(reverse("api:schema")).status_code, 200)


class AlunoTests(BaseApiMixin, TestCase):
    def setUp(self):
        self.entrar(self.aluno)

    def test_so_as_proprias_matriculas(self):
        resposta = self.get("matricula-list").json()
        self.assertEqual(resposta["count"], 1)
        self.assertEqual(resposta["results"][0]["aluno"]["ra"], "2026001")
        self.assertEqual(self.get("matricula-detail", self.matricula2.pk).status_code, 404)
        self.assertEqual(self.get("matricula-boletim", self.matricula2.pk).status_code, 404)

    def test_boletim_com_os_numeros_das_telas(self):
        boletim = self.get("matricula-boletim", self.matricula.pk).json()
        matematica = next(d for d in boletim["disciplinas"] if d["disciplina"]["codigo"] == "MAT1")
        self.assertEqual(matematica["media"], 6.75)  # número no JSON, não texto
        self.assertEqual(matematica["situacao"], "Em atenção")
        self.assertEqual(matematica["professor"], "Profa. Ana")
        self.assertEqual(
            matematica["notas"], [{"avaliacao": "A1", "valor": 7.0}, {"avaliacao": "A2", "valor": 6.5}]
        )
        self.assertEqual(boletim["frequencia_global"], 100.0)

    def test_turmas_e_ofertas_da_propria_turma(self):
        self.assertEqual(self.get("turma-list").json()["count"], 1)
        self.assertEqual(self.get("oferta-list").json()["count"], 2)


class ProfessorTests(BaseApiMixin, TestCase):
    def setUp(self):
        self.entrar(self.professor)

    def test_so_as_proprias_ofertas(self):
        ofertas = self.get("oferta-list").json()["results"]
        self.assertEqual([oferta["id"] for oferta in ofertas], [self.oferta.pk])
        self.assertEqual(self.get("oferta-detail", self.oferta_fisica.pk).status_code, 404)
        self.assertEqual(self.get("oferta-desempenho", self.oferta_fisica.pk).status_code, 404)

    def test_desempenho_da_disciplina(self):
        desempenho = self.get("oferta-desempenho", self.oferta.pk).json()
        self.assertEqual([a["nome"] for a in desempenho["avaliacoes"]], ["A1", "A2"])
        caio = next(a for a in desempenho["alunos"] if a["aluno"]["ra"] == "2026002")
        # A nota que ainda não foi lançada aparece como null, na posição da avaliação.
        self.assertEqual(caio["notas"], [{"avaliacao": "A1", "valor": 4.0}, {"avaliacao": "A2", "valor": None}])
        self.assertEqual(caio["situacao"], "Em risco")
        self.assertEqual(desempenho["indicadores"]["alunos"], 2)
        self.assertEqual(desempenho["indicadores"]["risco"], 1)


class CoordenacaoTests(BaseApiMixin, TestCase):
    def setUp(self):
        self.entrar(self.coordenador)

    def test_lista_de_alunos_com_resumo_e_filtro(self):
        resposta = self.get("matricula-list").json()
        self.assertEqual(resposta["count"], 2)
        bia = resposta["results"][0]
        self.assertEqual(bia["aluno"]["nome"], "Bia Reis")
        self.assertEqual(bia["media"], 7.38)  # média de 6,75 (Matemática) e 8 (Física)
        self.assertEqual(bia["situacao"], "Em atenção")

        filtrada = self.get("matricula-list", busca="caio lima").json()
        self.assertEqual([m["aluno"]["ra"] for m in filtrada["results"]], ["2026002"])

    def test_paginacao(self):
        resposta = self.get("matricula-list", tamanho=1).json()
        self.assertEqual(resposta["count"], 2)
        self.assertEqual(len(resposta["results"]), 1)
        self.assertIn("pagina=2", resposta["next"])

    def test_desempenho_da_turma(self):
        desempenho = self.get("turma-desempenho", self.turma.pk).json()
        self.assertEqual(len(desempenho["disciplinas"]), 2)
        self.assertEqual(desempenho["indicadores"]["atencao"], 1)
        self.assertEqual(desempenho["indicadores"]["risco"], 1)

    def test_riscos_do_maior_para_o_menor_e_filtro(self):
        riscos = self.get("risco-list").json()["results"]
        self.assertEqual([r["probabilidade"] for r in riscos], [74.96, 12.5])
        self.assertEqual(self.get("risco-list", nivel="ALTO").json()["count"], 1)
        detalhe = self.get("risco-detail", self.matricula2.pk).json()
        self.assertEqual(detalhe["nivel_nome"], "Risco alto")
        self.assertEqual(len(detalhe["motivos"]), 2)


class RelatoriosTests(BaseApiMixin, TestCase):
    def test_boletim_em_pdf_so_do_proprio_aluno(self):
        self.entrar(self.aluno)
        resposta = self.get("relatorio_boletim", self.matricula.pk)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertTrue(resposta.content.startswith(b"%PDF"))
        self.assertEqual(self.get("relatorio_boletim", self.matricula2.pk).status_code, 404)

    def test_disciplina_em_excel_mesmo_com_accept_de_arquivo(self):
        # O Swagger pede o arquivo com "Accept: <tipo do Excel>"; a resposta não pode ser 406.
        self.entrar(self.professor)
        resposta = self.client.get(
            reverse("api:relatorio_disciplina", args=[self.oferta.pk]),
            {"formato": "xlsx"},
            HTTP_ACCEPT=TIPO_EXCEL,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], TIPO_EXCEL)
        self.assertEqual(self.get("relatorio_disciplina", self.oferta_fisica.pk).status_code, 404)

    def test_formato_invalido_responde_404(self):
        self.entrar(self.coordenador)
        self.assertEqual(self.get("relatorio_turma", self.turma.pk, formato="doc").status_code, 404)
        self.assertEqual(self.get("relatorio_alunos", formato="pdf").status_code, 404)

    def test_relatorios_da_coordenacao(self):
        self.entrar(self.coordenador)
        self.assertEqual(self.get("relatorio_risco", formato="xlsx", nivel="ALTO").status_code, 200)
        self.assertEqual(self.get("relatorio_alunos", formato="xlsx").status_code, 200)
        self.assertEqual(self.get("relatorio_turma", self.turma.pk).status_code, 200)
        self.entrar(self.professor)
        self.assertEqual(self.get("relatorio_risco").status_code, 403)
