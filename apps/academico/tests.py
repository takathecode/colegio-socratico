from decimal import Decimal
from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import calculos
from .management.commands.popular_demo import ALUNOS_EM_RISCO, FERIADOS
from .models import (
    Aula,
    Avaliacao,
    Curso,
    Disciplina,
    Evento,
    Frequencia,
    Justificativa,
    Matricula,
    Nota,
    Oferta,
    Turma,
)

Usuario = get_user_model()

# Um algoritmo de senha rápido deixa os testes do popular_demo muito mais curtos.
HASH_RAPIDO = ["django.contrib.auth.hashers.MD5PasswordHasher"]


class CalculosTests(SimpleTestCase):
    def test_media_simples_das_notas(self):
        self.assertEqual(calculos.calcular_media([Decimal("8.5"), Decimal("8.9")]), Decimal("8.70"))
        self.assertIsNone(calculos.calcular_media([]))

    def test_frequencia_igual_ao_prototipo(self):
        self.assertEqual(calculos.calcular_frequencia(50, 4), Decimal("92.00"))
        self.assertEqual(calculos.calcular_frequencia(50, 12), Decimal("76.00"))
        self.assertEqual(calculos.calcular_frequencia(40, 2), Decimal("95.00"))
        self.assertIsNone(calculos.calcular_frequencia(0, 0))

    def test_limites_do_selo(self):
        casos = [
            ("7", "80", calculos.REGULAR),
            ("6.99", "80", calculos.EM_ATENCAO),
            ("7", "79.99", calculos.EM_ATENCAO),
            ("6", "75", calculos.EM_ATENCAO),
            ("5.99", "90", calculos.EM_RISCO),
            ("9", "74.99", calculos.EM_RISCO),
        ]
        for media, frequencia, esperado in casos:
            with self.subTest(media=media, frequencia=frequencia):
                resultado = calculos.calcular_situacao(Decimal(media), Decimal(frequencia))
                self.assertEqual(resultado, esperado)

    def test_dado_inexistente_nao_conta_contra_o_aluno(self):
        self.assertIsNone(calculos.calcular_situacao(None, None))
        self.assertEqual(calculos.calcular_situacao(None, Decimal("90")), calculos.REGULAR)
        self.assertEqual(calculos.calcular_situacao(Decimal("5"), None), calculos.EM_RISCO)


class BaseAcademicaMixin:
    """Monta o mínimo necessário: duas turmas, uma oferta e um aluno matriculado."""

    @classmethod
    def setUpTestData(cls):
        cls.professor = Usuario.objects.create_user(
            "prof", "senha", perfil=Usuario.Perfil.PROFESSOR
        )
        cls.aluno = Usuario.objects.create_user("aluno", "senha", perfil=Usuario.Perfil.ALUNO)
        cls.curso = Curso.objects.create(nome="Curso", total_creditos=200)
        cls.disciplina = Disciplina.objects.create(
            curso=cls.curso, codigo="D1", nome="Disciplina", creditos=4, carga_horaria=40
        )
        cls.turma = Turma.objects.create(
            curso=cls.curso, codigo="T1", semestre="2026.2", periodo=1
        )
        cls.outra_turma = Turma.objects.create(
            curso=cls.curso, codigo="T2", semestre="2026.2", periodo=1
        )
        cls.oferta = Oferta.objects.create(
            turma=cls.turma, disciplina=cls.disciplina, professor=cls.professor
        )
        cls.matricula = Matricula.objects.create(aluno=cls.aluno, turma=cls.turma)
        cls.avaliacao = Avaliacao.objects.create(
            oferta=cls.oferta, nome="A1", data_hora=timezone.now()
        )
        cls.aula = Aula.objects.create(oferta=cls.oferta, data=timezone.localdate())


class ModelosTests(BaseAcademicaMixin, TestCase):
    def test_banco_recusa_nota_fora_de_0_a_10(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Nota.objects.create(
                avaliacao=self.avaliacao, matricula=self.matricula, valor=Decimal("10.5")
            )

    def test_aluno_tem_uma_nota_por_avaliacao(self):
        Nota.objects.create(avaliacao=self.avaliacao, matricula=self.matricula, valor=Decimal("8"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Nota.objects.create(
                avaliacao=self.avaliacao, matricula=self.matricula, valor=Decimal("9")
            )

    def test_nota_exige_aluno_da_turma_da_avaliacao(self):
        outro = Usuario.objects.create_user("outro", "senha", perfil=Usuario.Perfil.ALUNO)
        de_fora = Matricula.objects.create(aluno=outro, turma=self.outra_turma)
        nota = Nota(avaliacao=self.avaliacao, matricula=de_fora, valor=Decimal("8"))
        with self.assertRaises(ValidationError):
            nota.full_clean()

    def test_frequencia_exige_aluno_da_turma_da_aula(self):
        outro = Usuario.objects.create_user("outro", "senha", perfil=Usuario.Perfil.ALUNO)
        de_fora = Matricula.objects.create(aluno=outro, turma=self.outra_turma)
        with self.assertRaises(ValidationError):
            Frequencia(aula=self.aula, matricula=de_fora).full_clean()

    def test_oferta_exige_usuario_com_perfil_professor(self):
        oferta = Oferta(turma=self.outra_turma, disciplina=self.disciplina, professor=self.aluno)
        with self.assertRaises(ValidationError):
            oferta.full_clean()

    def test_oferta_exige_disciplina_do_curso_da_turma(self):
        outro_curso = Curso.objects.create(nome="Outro", total_creditos=100)
        disciplina = Disciplina.objects.create(
            curso=outro_curso, codigo="D2", nome="Outra", creditos=4, carga_horaria=40
        )
        oferta = Oferta(turma=self.turma, disciplina=disciplina, professor=self.professor)
        with self.assertRaises(ValidationError):
            oferta.full_clean()

    def test_matricula_exige_usuario_com_perfil_aluno(self):
        with self.assertRaises(ValidationError):
            Matricula(aluno=self.professor, turma=self.outra_turma).full_clean()

    def test_semestre_precisa_do_formato_correto(self):
        turma = Turma(curso=self.curso, codigo="T3", semestre="2026-2", periodo=1)
        with self.assertRaises(ValidationError):
            turma.full_clean()

    def test_justificativa_so_vale_para_falta(self):
        presenca = Frequencia.objects.create(
            aula=self.aula, matricula=self.matricula, presente=True
        )
        with self.assertRaises(ValidationError):
            Justificativa(frequencia=presenca, motivo="Motivo").full_clean()

    def test_anexo_recusa_formato_nao_permitido(self):
        falta = Frequencia.objects.create(aula=self.aula, matricula=self.matricula, presente=False)
        justificativa = Justificativa(
            frequencia=falta, motivo="Motivo", anexo=ContentFile(b"x", name="virus.exe")
        )
        with self.assertRaises(ValidationError) as erro:
            justificativa.full_clean()
        self.assertIn("anexo", erro.exception.message_dict)

    def test_anexo_recusa_arquivo_maior_que_5_mb(self):
        falta = Frequencia.objects.create(aula=self.aula, matricula=self.matricula, presente=False)
        grande = ContentFile(b"x" * (5 * 1024 * 1024 + 1), name="atestado.pdf")
        justificativa = Justificativa(frequencia=falta, motivo="Motivo", anexo=grande)
        with self.assertRaises(ValidationError) as erro:
            justificativa.full_clean()
        self.assertIn("anexo", erro.exception.message_dict)

    def test_evento_nao_termina_antes_de_comecar(self):
        agora = timezone.now()
        evento = Evento(titulo="X", inicio=agora, fim=agora - timezone.timedelta(hours=1))
        with self.assertRaises(ValidationError):
            evento.full_clean()

    def test_nao_apaga_turma_com_alunos(self):
        with self.assertRaises(ProtectedError):
            self.turma.delete()

    def test_resumo_calcula_uma_linha_por_disciplina(self):
        Nota.objects.create(avaliacao=self.avaliacao, matricula=self.matricula, valor=Decimal("8"))
        Frequencia.objects.create(aula=self.aula, matricula=self.matricula, presente=False)
        linhas = calculos.resumo_por_disciplina(self.matricula)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["media"], Decimal("8.00"))
        self.assertEqual(linhas[0]["horas_dadas"], 2)
        self.assertEqual(linhas[0]["horas_faltas"], 2)
        self.assertEqual(linhas[0]["frequencia"], Decimal("0.00"))
        self.assertEqual(linhas[0]["situacao"], calculos.EM_RISCO)

    def test_justificativa_aprovada_nao_altera_frequencia(self):
        falta = Frequencia.objects.create(aula=self.aula, matricula=self.matricula, presente=False)
        Justificativa.objects.create(
            frequencia=falta, motivo="Motivo", status=Justificativa.Status.APROVADA
        )
        self.assertEqual(calculos.frequencia_global(self.matricula), Decimal("0.00"))


class AdminAcademicoTests(TestCase):
    def test_telas_de_todos_os_modelos_abrem(self):
        administrador = Usuario.objects.create_superuser(
            "admin01", "senha", email="admin@exemplo.com"
        )
        self.client.force_login(administrador)
        modelos = [
            modelo for modelo in admin.site._registry if modelo._meta.app_label == "academico"
        ]
        self.assertEqual(len(modelos), 11)
        for modelo in modelos:
            nome = modelo._meta.model_name
            for acao in ("changelist", "add"):
                with self.subTest(modelo=nome, acao=acao):
                    resposta = self.client.get(reverse(f"admin:academico_{nome}_{acao}"))
                    self.assertEqual(resposta.status_code, 200)


@override_settings(DEBUG=True, PASSWORD_HASHERS=HASH_RAPIDO)
class PopularDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrador = Usuario.objects.create_superuser(
            "admin01", "senha", email="admin@exemplo.com"
        )
        call_command("popular_demo", stdout=StringIO())
        cls.mariana = Matricula.objects.select_related("aluno", "turma").get(
            aluno__matricula="aluno01"
        )

    def test_cria_a_quantidade_combinada(self):
        contagem = Usuario.objects.exclude(pk=self.administrador.pk)
        self.assertEqual(contagem.filter(perfil=Usuario.Perfil.COORDENADOR).count(), 1)
        self.assertEqual(contagem.filter(perfil=Usuario.Perfil.PROFESSOR).count(), 6)
        self.assertEqual(contagem.filter(perfil=Usuario.Perfil.ALUNO).count(), 40)
        self.assertEqual(Turma.objects.count(), 2)
        self.assertEqual(Oferta.objects.count(), 12)
        self.assertEqual(Matricula.objects.count(), 40)
        for turma in Turma.objects.all():
            self.assertEqual(turma.matriculas.count(), 20)

    def test_login_com_senha_igual_a_matricula(self):
        for matricula in ("coord01", "prof01", "aluno01", "aluno40"):
            with self.subTest(matricula=matricula):
                self.assertTrue(self.client.login(matricula=matricula, password=matricula))
                self.client.logout()

    def test_aluno01_reproduz_o_prototipo(self):
        self.assertEqual(self.mariana.aluno.get_full_name(), "Mariana Alves")
        self.assertEqual(self.mariana.creditos_concluidos, 112)
        self.assertEqual(self.mariana.coeficiente_rendimento, Decimal("8.40"))

        esperado = [
            ("MAT204", "Prof. Ricardo Almeida", [Decimal("8.5"), Decimal("8.9")], "8.7", 50, 4, 92, calculos.REGULAR),
            ("COM203", "Profa. Ana Ribeiro", [Decimal("7.0"), Decimal("7.4")], "7.2", 50, 6, 88, calculos.REGULAR),
            ("FIS202", "Prof. Paulo Mendes", [Decimal("6.0"), Decimal("6.8")], "6.4", 50, 12, 76, calculos.EM_ATENCAO),
            ("GES201", "Profa. Camila Costa", [Decimal("9.0"), Decimal("9.2")], "9.1", 40, 2, 95, calculos.REGULAR),
            ("MAT206", "Prof. Bruno Lima", [Decimal("7.6"), Decimal("8.0")], "7.8", 40, 4, 90, calculos.REGULAR),
            ("LET201", "Profa. Helena Dias", [Decimal("8.8"), Decimal("9.0")], "8.9", 50, 3, 94, calculos.REGULAR),
        ]
        linhas = calculos.resumo_por_disciplina(self.mariana)
        self.assertEqual(len(linhas), len(esperado))
        for linha, item in zip(linhas, esperado):
            codigo, professor, notas, media, dadas, faltas, frequencia, situacao = item
            with self.subTest(disciplina=codigo):
                self.assertEqual(linha["oferta"].disciplina.codigo, codigo)
                self.assertEqual(linha["oferta"].professor.nome_com_tratamento, professor)
                self.assertEqual(linha["notas"], notas)
                self.assertEqual(linha["media"], Decimal(media))
                self.assertEqual(linha["horas_dadas"], dadas)
                self.assertEqual(linha["horas_faltas"], faltas)
                self.assertEqual(linha["frequencia"], Decimal(frequencia))
                self.assertEqual(linha["situacao"], situacao)

        # 249 horas presentes de 280: aparece como 89% no painel do protótipo.
        self.assertEqual(calculos.frequencia_global(self.mariana), Decimal("88.93"))

    def test_aluno01_tem_falta_para_justificar_na_demonstracao(self):
        self.assertFalse(
            Justificativa.objects.filter(frequencia__matricula=self.mariana).exists()
        )
        self.assertTrue(self.mariana.frequencias.filter(presente=False).exists())

    def test_oito_alunos_em_risco_e_regulares_fora_de_risco(self):
        em_risco = set()
        matriculas = Matricula.objects.select_related("aluno")
        for matricula in matriculas:
            linhas = calculos.resumo_por_disciplina(matricula)
            if any(linha["situacao"] == calculos.EM_RISCO for linha in linhas):
                em_risco.add(matricula.aluno.matricula)
        self.assertEqual(em_risco, set(ALUNOS_EM_RISCO))

    def test_alunos_em_risco_tem_notas_em_queda_e_frequencia_baixa(self):
        for codigo in ALUNOS_EM_RISCO:
            matricula = Matricula.objects.get(aluno__matricula=codigo)
            with self.subTest(aluno=codigo):
                self.assertLess(calculos.frequencia_global(matricula), Decimal("75"))
                for linha in calculos.resumo_por_disciplina(matricula):
                    self.assertLess(linha["notas"][1], linha["notas"][0])

    def test_datas_de_aula_respeitam_a_regra(self):
        hoje = timezone.localdate()
        feriados = {(mes, dia) for mes, dia, _titulo in FERIADOS}
        for aula in Aula.objects.all():
            self.assertLess(aula.data, hoje)
            self.assertLess(aula.data.weekday(), 5)
            self.assertNotIn((aula.data.month, aula.data.day), feriados)

    def test_existem_avaliacoes_futuras_e_justificativas_para_avaliar(self):
        agora = timezone.now()
        self.assertEqual(Avaliacao.objects.filter(data_hora__gt=agora).count(), 4)
        pendentes = Justificativa.objects.filter(status=Justificativa.Status.PENDENTE)
        self.assertEqual(pendentes.count(), 16)

    def test_rodar_de_novo_recria_sem_duplicar_nem_apagar_outros_dados(self):
        outro = Usuario.objects.create_user("real01", "senha")
        antes = {
            "notas": Nota.objects.count(),
            "frequencias": Frequencia.objects.count(),
            "eventos": Evento.objects.count(),
            "usuarios": Usuario.objects.count(),
        }
        primeira_mariana = self.mariana.pk
        call_command("popular_demo", stdout=StringIO())

        self.assertEqual(Nota.objects.count(), antes["notas"])
        self.assertEqual(Frequencia.objects.count(), antes["frequencias"])
        self.assertEqual(Evento.objects.count(), antes["eventos"])
        self.assertEqual(Usuario.objects.count(), antes["usuarios"])
        self.assertTrue(Usuario.objects.filter(pk=outro.pk).exists())
        self.assertTrue(Usuario.objects.filter(pk=self.administrador.pk).exists())
        self.assertFalse(Matricula.objects.filter(pk=primeira_mariana).exists())

    def test_erro_de_dados_protegidos_nao_apaga_nada(self):
        # Uma turma real com um professor da demonstração impede que esse professor seja apagado.
        professor = Usuario.objects.get(matricula="prof01")
        curso = Curso.objects.create(nome="Real", total_creditos=100)
        turma = Turma.objects.create(curso=curso, codigo="REAL", semestre="2026.2", periodo=1)
        disciplina = Disciplina.objects.create(
            curso=curso, codigo="REAL1", nome="Real", creditos=4, carga_horaria=40
        )
        Oferta.objects.create(turma=turma, disciplina=disciplina, professor=professor)
        quantidade = Nota.objects.count()

        with self.assertRaises(CommandError):
            call_command("popular_demo", stdout=StringIO())
        self.assertEqual(Nota.objects.count(), quantidade)


class PopularDemoSegurancaTests(TestCase):
    @override_settings(DEBUG=False)
    def test_recusa_rodar_com_debug_desligado(self):
        with self.assertRaises(CommandError):
            call_command("popular_demo", stdout=StringIO())
        self.assertFalse(Usuario.objects.filter(matricula="coord01").exists())
