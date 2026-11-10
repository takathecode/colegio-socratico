"""Teste de fumaça: todas as telas abrem com os dados de demonstração, sem erro 500.

Os testes de cada app usam poucos dados, montados à mão. Aqui o sistema fica como na
apresentação: popular_demo, modelo de evasão treinado e rotina diária (riscos e alertas).
Depois, cada perfil abre todas as telas da sua área. Um erro em um template ou em um
cálculo com dados reais (divisão por zero, aluno sem nota...) faz o teste falhar.
"""

import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academico.management.commands.popular_demo import ALUNOS_EM_ATENCAO, ALUNOS_EM_RISCO
from apps.academico.models import Disciplina, Matricula, Oferta, Turma
from apps.alertas.models import Alerta
from apps.alertas.tasks import rotina_diaria
from apps.analytics.evasao import nivel_da_probabilidade
from apps.analytics.models import RiscoEvasao
from apps.analytics.tests import ModeloTreinadoMixin
from apps.contas.models import Usuario
from apps.mensagens.models import Conversa, Mensagem
from apps.professor.tests import HASH_RAPIDO

from .test_permissoes import areas_do_sistema, rotas_das_telas

# Pasta temporária: o PDF de exemplo do popular_demo não vai para a pasta media/ real.
MEDIA_DE_TESTE = tempfile.mkdtemp(prefix="testes-telas-")


def tearDownModule():
    shutil.rmtree(MEDIA_DE_TESTE, ignore_errors=True)


# Contas da demonstração usadas no teste (a aluno05 é uma das que estão em risco).
CONTAS = ["aluno01", "aluno05", "prof01", "coord01"]

# Respostas esperadas sem número na URL: 200 (tela), 302 (a tela manda para outra, como
# Relatório da turma sem ?turma=) ou 405 (a rota só aceita POST, como "Recalcular agora").
RESPOSTAS_ACEITAS = {200, 302, 405}


@override_settings(DEBUG=True, PASSWORD_HASHERS=HASH_RAPIDO, MEDIA_ROOT=MEDIA_DE_TESTE)
class TelasComDadosDeDemonstracaoTests(ModeloTreinadoMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("popular_demo", stdout=StringIO())
        rotina_diaria()  # grava os riscos e os alertas, como a tarefa das 6h
        cls.contas = {c: Usuario.objects.get(matricula=c) for c in CONTAS}

    def entrar(self, matricula):
        self.client.force_login(self.contas[matricula])

    def abrir(self, url, esperado=200):
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, esperado, url)
        return resposta

    def test_a_demonstracao_tem_riscos_e_alertas(self):
        # Sem isso, as telas de risco e de alertas abririam só com o estado vazio.
        self.assertTrue(RiscoEvasao.objects.exists())
        self.assertTrue(Alerta.objects.exists())

    def test_modelo_encontra_os_alunos_montados_em_risco(self):
        """O popular_demo monta 8 alunos em risco; o modelo precisa achá-los sozinho."""
        riscos = list(RiscoEvasao.objects.select_related("matricula__aluno"))
        em_risco = [r for r in riscos if r.matricula.aluno.matricula in ALUNOS_EM_RISCO]
        outros = [r for r in riscos if r.matricula.aluno.matricula not in ALUNOS_EM_RISCO]
        regulares = [r for r in outros if r.matricula.aluno.matricula not in ALUNOS_EM_ATENCAO]

        self.assertEqual(len(em_risco), len(ALUNOS_EM_RISCO))
        self.assertTrue(all(r.nivel == RiscoEvasao.Nivel.ALTO for r in em_risco))
        self.assertTrue(all(r.nivel == RiscoEvasao.Nivel.BAIXO for r in regulares))
        # Todo aluno em risco tem probabilidade maior que a de qualquer outro aluno.
        self.assertGreater(
            min(r.probabilidade for r in em_risco), max(r.probabilidade for r in outros)
        )
        # O nível gravado sempre corresponde à probabilidade (baixo < 30%, alto a partir de 60%).
        for risco in riscos:
            with self.subTest(aluno=risco.matricula.aluno.matricula):
                self.assertTrue(0 <= risco.probabilidade <= 100)
                self.assertEqual(risco.nivel, nivel_da_probabilidade(risco.probabilidade))

    def test_cada_perfil_abre_todas_as_telas_sem_numero_na_url(self):
        # A mesma lista de rotas da varredura de permissões (test_permissoes.py).
        rotas = list(rotas_das_telas(areas_do_sistema()))
        for matricula, usuario in self.contas.items():
            self.client.force_login(usuario)
            for namespace, nome, url, permitidos, tem_numero in rotas:
                # As telas com número na URL são abertas, com registros reais, nos testes abaixo.
                if usuario.perfil not in permitidos or tem_numero:
                    continue
                with self.subTest(conta=matricula, rota=f"{namespace}:{nome}"):
                    self.assertIn(self.client.get(url).status_code, RESPOSTAS_ACEITAS)

    def test_telas_do_aluno_com_numero_na_url(self):
        self.entrar("aluno01")
        conversa = Conversa.objects.filter(aluno__matricula="aluno01").first()
        self.abrir(f"{reverse('mensagens:caixa')}?conversa={conversa.pk}")
        mensagem = Mensagem.objects.filter(conversa__aluno__matricula="aluno01").exclude(anexo="")
        # A demonstração não tem atestado anexado; esse download é testado em apps/aluno.
        self.abrir(reverse("mensagens:anexo", args=[mensagem.first().pk]))
        self.abrir(reverse("relatorios:meu_boletim"))

    def test_telas_do_professor_com_numero_na_url(self):
        self.entrar("prof01")
        for oferta in Oferta.objects.filter(professor__matricula="prof01"):
            with self.subTest(oferta=str(oferta)):
                self.abrir(reverse("professor:turma", args=[oferta.pk]))
                for tela in ("professor:notas", "professor:chamada", "professor:desempenho"):
                    self.abrir(f"{reverse(tela)}?oferta={oferta.pk}")
                for formato in ("pdf", "xlsx"):
                    url = reverse("relatorios:disciplina", args=[oferta.pk])
                    self.abrir(f"{url}?formato={formato}")
        self.abrir(f"{reverse('professor:justificativas')}?aba=avaliadas")

    def test_telas_da_coordenacao_com_numero_na_url(self):
        self.entrar("coord01")
        turma = Turma.objects.first()
        oferta = Oferta.objects.first()
        disciplina = Disciplina.objects.first()
        matricula = Matricula.objects.get(aluno__matricula="aluno05")
        professor = Usuario.objects.get(matricula="prof01")
        for url in (
            reverse("coordenacao:turma", args=[turma.pk]),
            reverse("coordenacao:turma_editar", args=[turma.pk]),
            reverse("coordenacao:turma_excluir", args=[turma.pk]),
            reverse("coordenacao:oferta_editar", args=[oferta.pk]),
            reverse("coordenacao:oferta_excluir", args=[oferta.pk]),
            reverse("coordenacao:disciplina_editar", args=[disciplina.pk]),
            reverse("coordenacao:disciplina_excluir", args=[disciplina.pk]),
            reverse("coordenacao:aluno_editar", args=[matricula.aluno.pk]),
            reverse("coordenacao:professor_editar", args=[professor.pk]),
            reverse("relatorios:boletim", args=[matricula.pk]),
            f"{reverse('relatorios:turma')}?turma={turma.pk}&formato=xlsx",
            f"{reverse('relatorios:risco')}?formato=xlsx",
            f"{reverse('relatorios:alunos')}?formato=xlsx",
            f"{reverse('coordenacao:risco')}?nivel=ALTO",
        ):
            with self.subTest(url=url):
                self.abrir(url)
