"""Cria dados fictícios para demonstração: python manage.py popular_demo

Rodar de novo apaga e recria apenas os dados de demonstração. As datas são calculadas a partir
do dia em que o comando roda, então vale rodá-lo pouco antes de apresentar o sistema.
"""

import io
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.utils import timezone
from reportlab.pdfgen import canvas

from apps.academico.calculos import somar_meses
from apps.academico.models import (
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
from apps.financeiro.models import Mensalidade
from apps.mensagens.models import Conversa, Mensagem

Usuario = get_user_model()

CURSO = "Ciência da Computação"
TURMAS = ("CC-6A", "CC-6B")
ALUNOS_POR_TURMA = 20

# Dias da semana: 0 = segunda ... 4 = sexta.
# código, nome, créditos, carga horária, dias da semana da aula
DISCIPLINAS = (
    ("MAT204", "Cálculo Diferencial II", 5, 50, (0, 3)),
    ("COM203", "Estruturas de Dados", 5, 50, (1, 4)),
    ("FIS202", "Física Experimental", 5, 50, (2, 4)),
    ("GES201", "Gestão de Projetos", 4, 40, (0, 2)),
    ("MAT206", "Estatística Aplicada", 4, 40, (1, 3)),
    ("LET201", "Inglês Instrumental", 5, 50, (2, 3)),
)

# matrícula, tratamento, nome, sobrenome, código da disciplina
PROFESSORES = (
    ("prof01", "Prof.", "Ricardo", "Almeida", "MAT204"),
    ("prof02", "Profa.", "Ana", "Ribeiro", "COM203"),
    ("prof03", "Prof.", "Paulo", "Mendes", "FIS202"),
    ("prof04", "Profa.", "Camila", "Costa", "GES201"),
    ("prof05", "Prof.", "Bruno", "Lima", "MAT206"),
    ("prof06", "Profa.", "Helena", "Dias", "LET201"),
)

# A aluno01 reproduz os valores do protótipo: (A1, A2, horas de falta) por disciplina.
PROTOTIPO_ALUNO01 = {
    "MAT204": ("8.5", "8.9", 4),
    "COM203": ("7.0", "7.4", 6),
    "FIS202": ("6.0", "6.8", 12),
    "GES201": ("9.0", "9.2", 2),
    "MAT206": ("7.6", "8.0", 4),
    "LET201": ("8.8", "9.0", 3),
}

ALUNOS_EM_RISCO = (
    "aluno05", "aluno09", "aluno14", "aluno18", "aluno23", "aluno27", "aluno32", "aluno38",
)
ALUNOS_EM_ATENCAO = ("aluno03", "aluno11", "aluno16", "aluno25", "aluno30", "aluno36")

NOMES_ALUNOS = (
    "Mariana Alves", "Lucas Ferreira", "Beatriz Souza", "Gabriel Rocha", "Larissa Martins",
    "Thiago Barbosa", "Camila Nunes", "Rafael Pereira", "Julia Cardoso", "Pedro Teixeira",
    "Amanda Moreira", "Felipe Araujo", "Isabela Ramos", "Matheus Correia", "Letícia Vieira",
    "Bruno Monteiro", "Fernanda Lopes", "Vinícius Freitas", "Natália Pires", "Gustavo Campos",
    "Carolina Duarte", "Diego Fernandes", "Aline Batista", "Rodrigo Cavalcante", "Bianca Azevedo",
    "Eduardo Santana", "Patrícia Melo", "Henrique Xavier", "Vanessa Tavares", "Leonardo Reis",
    "Renata Farias", "André Coelho", "Sabrina Pacheco", "Caio Nogueira", "Tatiane Borges",
    "Marcelo Antunes", "Priscila Rezende", "Igor Macedo", "Daniela Fonseca", "Murilo Guimarães",
)

# Feriados sem aula: (mês, dia, título).
FERIADOS = (
    (9, 7, "Independência do Brasil"),
    (10, 12, "Feriado nacional"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (11, 20, "Dia da Consciência Negra"),
)
EVENTOS_INSTITUCIONAIS = ((10, 15, "Dia dos Professores"), (12, 18, "Encerramento do semestre"))

# Mensalidades: 6 parcelas por semestre, com vencimento sempre neste dia do mês.
VALOR_MENSALIDADE = Decimal("1480.00")
BOLSA_PERCENTUAL = 20
TOTAL_PARCELAS = 6
PARCELA_A_VENCER = 5  # como no protótipo: a próxima a vencer é a parcela 5 de 6
DIA_VENCIMENTO = 5

MOTIVOS = (
    "Não pude comparecer à aula por motivo de saúde.",
    "Tive uma consulta médica no horário da aula.",
    "Precisei acompanhar um familiar em atendimento médico.",
)


class Command(BaseCommand):
    help = "Apaga e recria os dados fictícios de demonstração (somente com DEBUG=True)."

    def handle(self, *args, **opcoes):
        # Trava de segurança: as contas de demonstração têm senhas fáceis de adivinhar.
        if not settings.DEBUG:
            raise CommandError("O popular_demo só pode rodar com DEBUG=True.")

        # Semente fixa: toda execução sorteia os mesmos valores.
        self.sorteio = random.Random(2026)
        self.hoje = timezone.localdate()
        self.matriculas_demo = (
            ["coord01"]
            + [professor[0] for professor in PROFESSORES]
            + [f"aluno{numero:02d}" for numero in range(1, 41)]
        )

        try:
            # atomic: se algo falhar no meio, o banco volta exatamente ao estado anterior.
            with transaction.atomic():
                self.limpar()
                self.criar_tudo()
        except ProtectedError as erro:
            raise CommandError(
                "Não foi possível recriar a demonstração: há outros dados ligados a ela "
                f"({erro.args[0]})"
            ) from erro

        self.mostrar_resumo()

    def limpar(self):
        """Apaga os dados de demonstração, dos mais dependentes para os menos dependentes."""
        turmas = Turma.objects.filter(codigo__in=TURMAS, curso__nome=CURSO)
        titulos = [item[2] for item in FERIADOS + EVENTOS_INSTITUCIONAIS]

        # Apaga também os arquivos: os anexos podem conter dados pessoais, como atestados.
        for mensagem in Mensagem.objects.filter(
            conversa__aluno__matricula__in=self.matriculas_demo
        ).exclude(anexo=""):
            mensagem.anexo.delete(save=False)
        for justificativa in Justificativa.objects.filter(
            frequencia__matricula__turma__in=turmas
        ).exclude(anexo=""):
            justificativa.anexo.delete(save=False)

        Conversa.objects.filter(
            Q(aluno__matricula__in=self.matriculas_demo)
            | Q(contato__matricula__in=self.matriculas_demo)
            | Q(oferta__turma__in=turmas)
        ).delete()
        Mensalidade.objects.filter(matricula__turma__in=turmas).delete()
        Justificativa.objects.filter(frequencia__matricula__turma__in=turmas).delete()
        Frequencia.objects.filter(matricula__turma__in=turmas).delete()
        Aula.objects.filter(oferta__turma__in=turmas).delete()
        Nota.objects.filter(matricula__turma__in=turmas).delete()
        Avaliacao.objects.filter(oferta__turma__in=turmas).delete()
        Evento.objects.filter(oferta__turma__in=turmas).delete()
        Evento.objects.filter(oferta__isnull=True, titulo__in=titulos).delete()
        Matricula.objects.filter(turma__in=turmas).delete()
        Oferta.objects.filter(turma__in=turmas).delete()
        turmas.delete()
        Disciplina.objects.filter(codigo__in=[item[0] for item in DISCIPLINAS]).delete()
        Curso.objects.filter(nome=CURSO).delete()
        Usuario.objects.filter(matricula__in=self.matriculas_demo).delete()

    def criar_tudo(self):
        curso = Curso.objects.create(nome=CURSO, total_creditos=200)
        disciplinas = {
            codigo: Disciplina.objects.create(
                curso=curso, codigo=codigo, nome=nome, creditos=creditos, carga_horaria=carga
            )
            for codigo, nome, creditos, carga, _dias in DISCIPLINAS
        }
        professores = self.criar_usuarios()
        semestre = f"{self.hoje.year}.{1 if self.hoje.month <= 6 else 2}"
        self.criar_eventos_institucionais()

        for indice, codigo_turma in enumerate(TURMAS):
            turma = Turma.objects.create(
                curso=curso, codigo=codigo_turma, semestre=semestre, periodo=6
            )
            ofertas = {
                codigo: Oferta.objects.create(
                    turma=turma,
                    disciplina=disciplina,
                    professor=professores[codigo],
                )
                for codigo, disciplina in disciplinas.items()
            }
            # A primeira turma recebe aluno01 a aluno20; a segunda, aluno21 a aluno40.
            inicio = indice * ALUNOS_POR_TURMA + 1
            numeros = range(inicio, inicio + ALUNOS_POR_TURMA)
            matriculas = self.criar_matriculas(turma, numeros)
            avaliacoes = self.criar_avaliacoes(ofertas)
            aulas = self.criar_aulas(ofertas)
            self.criar_eventos_das_disciplinas(ofertas)
            self.criar_notas(matriculas, avaliacoes)
            faltas = self.criar_frequencias(matriculas, aulas)
            self.criar_justificativas(faltas, ofertas)
            self.criar_mensalidades(matriculas)
            if indice == 0:  # a aluno01 fica na primeira turma
                self.criar_conversas(matriculas[0], ofertas)

    def criar_usuarios(self):
        """Cria as contas, com a senha igual à matrícula. Retorna os professores por disciplina."""
        usuarios = [self.novo_usuario("coord01", Usuario.Perfil.COORDENADOR, "Marta", "Oliveira")]
        for matricula, tratamento, nome, sobrenome, _codigo in PROFESSORES:
            usuarios.append(
                self.novo_usuario(
                    matricula, Usuario.Perfil.PROFESSOR, nome, sobrenome, tratamento
                )
            )
        for numero, nome_completo in enumerate(NOMES_ALUNOS, start=1):
            nome, sobrenome = nome_completo.split(" ", 1)
            usuarios.append(
                self.novo_usuario(f"aluno{numero:02d}", Usuario.Perfil.ALUNO, nome, sobrenome)
            )
        criados = {
            usuario.matricula: usuario for usuario in Usuario.objects.bulk_create(usuarios)
        }
        self.alunos = criados
        return {codigo: criados[matricula] for matricula, _t, _n, _s, codigo in PROFESSORES}

    def novo_usuario(self, matricula, perfil, nome, sobrenome, tratamento=""):
        return Usuario(
            matricula=matricula,
            password=make_password(matricula),
            perfil=perfil,
            first_name=nome,
            last_name=sobrenome,
            tratamento=tratamento,
            # O domínio .example é reservado: nenhum e-mail chega a uma pessoa real.
            email=f"{matricula}@institutosocratico.example",
        )

    def perfil_do_aluno(self, matricula):
        if matricula in ALUNOS_EM_RISCO:
            return "risco"
        if matricula in ALUNOS_EM_ATENCAO:
            return "atencao"
        return "regular"

    def criar_matriculas(self, turma, numeros):
        matriculas = []
        for numero in numeros:
            codigo = f"aluno{numero:02d}"
            perfil = self.perfil_do_aluno(codigo)
            if codigo == "aluno01":
                creditos, coeficiente = 112, Decimal("8.40")  # valores do protótipo
            else:
                faixa = {"risco": (5.0, 6.2), "atencao": (6.3, 7.2), "regular": (7.3, 9.4)}[perfil]
                creditos = self.sorteio.randrange(96, 130, 2)
                coeficiente = Decimal(str(round(self.sorteio.uniform(*faixa), 2)))
            matriculas.append(
                Matricula(
                    aluno=self.alunos[codigo],
                    turma=turma,
                    creditos_concluidos=creditos,
                    coeficiente_rendimento=coeficiente,
                    data_matricula=self.hoje.replace(month=1, day=15),
                )
            )
        return Matricula.objects.bulk_create(matriculas)

    def no_dia(self, dias, hora=19, minuto=10):
        """Data e hora relativas a hoje, no fuso do sistema. dias negativos = passado."""
        data = self.hoje + timedelta(days=dias)
        return timezone.make_aware(datetime.combine(data, time(hora, minuto)))

    def criar_avaliacoes(self, ofertas):
        """Cria A1 e A2 já realizadas, além de uma prova e uma entrega nos próximos dias."""
        passadas = {}
        for codigo, oferta in ofertas.items():
            passadas[codigo] = (
                Avaliacao.objects.create(oferta=oferta, nome="A1", data_hora=self.no_dia(-42)),
                Avaliacao.objects.create(oferta=oferta, nome="A2", data_hora=self.no_dia(-14)),
            )
        Avaliacao.objects.create(
            oferta=ofertas["MAT204"], nome="A3", data_hora=self.no_dia(3), local="Sala B204"
        )
        Avaliacao.objects.create(
            oferta=ofertas["FIS202"],
            nome="Atividade prática",
            tipo=Avaliacao.Tipo.ENTREGA,
            data_hora=self.no_dia(2, 23, 59),
        )
        return passadas

    def dia_tem_feriado(self, dia):
        return any(dia.month == mes and dia.day == numero for mes, numero, _ in FERIADOS)

    def criar_aulas(self, ofertas):
        """Cria as aulas até ontem, para a chamada de hoje ainda estar por fazer."""
        aulas_por_codigo = {}
        for codigo, _nome, _creditos, carga, dias_da_semana in DISCIPLINAS:
            # Duas aulas de Inglês têm 1 hora: o protótipo mostra 3 horas de falta nessa disciplina.
            duracoes = [2] * (carga // 2)
            if codigo == "LET201":
                duracoes = [2] * ((carga - 2) // 2) + [1, 1]
            aulas = []
            dia = self.hoje - timedelta(days=1)
            for duracao in duracoes:
                while dia.weekday() not in dias_da_semana or self.dia_tem_feriado(dia):
                    dia -= timedelta(days=1)
                aulas.append(Aula(oferta=ofertas[codigo], data=dia, horas_aula=duracao))
                dia -= timedelta(days=1)
            aulas_por_codigo[codigo] = Aula.objects.bulk_create(aulas)
        return aulas_por_codigo

    def nota_sorteada(self, minimo, maximo):
        return round(self.sorteio.uniform(minimo, maximo), 1)

    def notas_do_aluno(self, matricula, codigo):
        """Retorna (A1, A2). Quem está em risco tem notas baixas e em queda."""
        if matricula == "aluno01":
            a1, a2, _faltas = PROTOTIPO_ALUNO01[codigo]
            return Decimal(a1), Decimal(a2)
        perfil = self.perfil_do_aluno(matricula)
        if perfil == "risco":
            a1 = self.nota_sorteada(4.5, 6.0)
            a2 = max(round(a1 - self.sorteio.uniform(0.4, 1.5), 1), 0)
        elif perfil == "atencao":
            a1, a2 = self.nota_sorteada(6.2, 6.9), self.nota_sorteada(6.2, 6.9)
        else:
            a1 = self.nota_sorteada(7.0, 9.5)
            a2 = min(max(round(a1 + self.sorteio.uniform(-0.4, 0.6), 1), 7.0), 10.0)
        return Decimal(str(a1)), Decimal(str(a2))

    def criar_notas(self, matriculas, avaliacoes):
        notas = []
        for matricula in matriculas:
            for codigo, (a1, a2) in avaliacoes.items():
                valor_a1, valor_a2 = self.notas_do_aluno(matricula.aluno.matricula, codigo)
                notas.append(Nota(avaliacao=a1, matricula=matricula, valor=valor_a1))
                notas.append(Nota(avaliacao=a2, matricula=matricula, valor=valor_a2))
        Nota.objects.bulk_create(notas)

    def horas_de_falta(self, matricula, codigo, carga):
        """Define quantas horas o aluno falta na disciplina, conforme o perfil dele."""
        if matricula == "aluno01":
            return PROTOTIPO_ALUNO01[codigo][2]
        perfil = self.perfil_do_aluno(matricula)
        faixa = {"risco": (55, 72), "atencao": (76, 79), "regular": (84, 99)}[perfil]
        frequencia = self.sorteio.uniform(*faixa)
        # Arredonda para um número par, pois as aulas normais têm 2 horas.
        return round(carga * (100 - frequencia) / 100 / 2) * 2

    def escolher_aulas_faltadas(self, aulas, horas):
        """Sorteia as aulas em que o aluno faltou, somando exatamente as horas pedidas."""
        de_uma_hora = [aula for aula in aulas if aula.horas_aula == 1]
        de_duas_horas = [aula for aula in aulas if aula.horas_aula == 2]
        escolhidas = []
        if horas % 2:  # um número ímpar de horas exige uma aula de 1 hora
            escolhidas.append(self.sorteio.choice(de_uma_hora))
            horas -= 1
        return escolhidas + self.sorteio.sample(de_duas_horas, horas // 2)

    def criar_frequencias(self, matriculas, aulas_por_codigo):
        """Registra a presença em todas as aulas. Retorna as faltas de cada matrícula."""
        cargas = {item[0]: item[3] for item in DISCIPLINAS}
        frequencias = []
        faltas = {matricula.pk: [] for matricula in matriculas}
        for matricula in matriculas:
            codigo_aluno = matricula.aluno.matricula
            for codigo, aulas in aulas_por_codigo.items():
                horas = self.horas_de_falta(codigo_aluno, codigo, cargas[codigo])
                faltadas = self.escolher_aulas_faltadas(aulas, horas)
                for aula in aulas:
                    presente = aula not in faltadas
                    usou_biometria = presente and self.sorteio.random() < 0.7
                    frequencia = Frequencia(
                        aula=aula,
                        matricula=matricula,
                        presente=presente,
                        metodo=(
                            Frequencia.Metodo.BIOMETRIA
                            if usou_biometria
                            else Frequencia.Metodo.MANUAL
                        ),
                    )
                    frequencias.append(frequencia)
                    if not presente:
                        faltas[matricula.pk].append((frequencia, codigo))
        # batch_size divide o envio em lotes, para não mandar milhares de linhas de uma vez.
        Frequencia.objects.bulk_create(frequencias, batch_size=1000)
        self.matriculas_por_pk = {matricula.pk: matricula for matricula in matriculas}
        return faltas

    def criar_justificativas(self, faltas_por_matricula, ofertas):
        """Cria pendências para o professor avaliar. A aluno01 fica sem nenhuma justificativa,
        para a demonstração do envio partir da falta ainda não justificada."""
        justificativas = []
        regulares_avaliados = 0
        agora = timezone.now()
        for matricula_pk, faltas in faltas_por_matricula.items():
            codigo_aluno = self.matriculas_por_pk[matricula_pk].aluno.matricula
            if codigo_aluno == "aluno01" or not faltas:
                continue
            if self.perfil_do_aluno(codigo_aluno) == "risco":
                for frequencia, _codigo in self.sorteio.sample(faltas, min(2, len(faltas))):
                    justificativas.append(
                        Justificativa(frequencia=frequencia, motivo=self.sorteio.choice(MOTIVOS))
                    )
            elif regulares_avaliados < 2:
                frequencia, codigo = faltas[0]
                aprovada = regulares_avaliados == 0
                justificativas.append(
                    Justificativa(
                        frequencia=frequencia,
                        motivo=self.sorteio.choice(MOTIVOS),
                        status=(
                            Justificativa.Status.APROVADA
                            if aprovada
                            else Justificativa.Status.REJEITADA
                        ),
                        avaliada_por=ofertas[codigo].professor,
                        avaliada_em=agora,
                        resposta=(
                            "Justificativa aceita."
                            if aprovada
                            else "Envie um comprovante para nova análise."
                        ),
                    )
                )
                regulares_avaliados += 1
        Justificativa.objects.bulk_create(justificativas)

    def criar_mensalidades(self, matriculas):
        """Cria as parcelas com datas relativas a hoje: sempre há uma próxima parcela a vencer.

        Quem está em risco deixa a parcela anterior em aberto, para aparecer "Em atraso".
        """
        primeiro_dia = self.hoje.replace(day=1)
        mes_a_vencer = primeiro_dia
        if self.hoje.day > DIA_VENCIMENTO:
            mes_a_vencer = somar_meses(primeiro_dia, 1)
        parcelas = []
        for matricula in matriculas:
            em_risco = self.perfil_do_aluno(matricula.aluno.matricula) == "risco"
            for numero in range(1, TOTAL_PARCELAS + 1):
                competencia = somar_meses(mes_a_vencer, numero - PARCELA_A_VENCER)
                vencimento = competencia.replace(day=DIA_VENCIMENTO)
                atrasada = em_risco and numero == PARCELA_A_VENCER - 1
                parcelas.append(
                    Mensalidade(
                        matricula=matricula,
                        competencia=competencia,
                        parcela=numero,
                        total_parcelas=TOTAL_PARCELAS,
                        valor=VALOR_MENSALIDADE,
                        bolsa_percentual=BOLSA_PERCENTUAL,
                        vencimento=vencimento,
                        paga_em=(
                            vencimento - timedelta(days=2)
                            if vencimento < self.hoje and not atrasada
                            else None
                        ),
                    )
                )
        Mensalidade.objects.bulk_create(parcelas)

    def pdf_de_exemplo(self, titulo):
        """Gera um PDF simples, para a demonstração do anexo baixar um arquivo de verdade."""
        memoria = io.BytesIO()
        pagina = canvas.Canvas(memoria)
        pagina.drawString(72, 760, titulo)
        pagina.drawString(72, 736, "Arquivo de demonstração do Instituto Socrático.")
        pagina.save()
        return memoria.getvalue()

    def criar_conversas(self, matricula, ofertas):
        """Conversas da aluno01, iguais às do protótipo. Duas ficam como não lidas."""
        agora = timezone.now()
        aluna = matricula.aluno
        data_prova = self.no_dia(3)
        prazo_entrega = self.no_dia(2)

        def conversa(contato, assunto, oferta, mensagens):
            """mensagens: lista de (remetente, texto, quanto tempo atrás, foi lida)."""
            nova = Conversa.objects.create(
                aluno=aluna, contato=contato, assunto=assunto, oferta=oferta
            )
            criadas = []
            for remetente, texto, tempo_atras, lida in mensagens:
                enviada_em = agora - tempo_atras
                criadas.append(
                    Mensagem.objects.create(
                        conversa=nova,
                        remetente=remetente,
                        texto=texto,
                        enviada_em=enviada_em,
                        lida_em=enviada_em if lida else None,
                    )
                )
            return criadas

        professor_calculo = ofertas["MAT204"].professor
        mensagens_calculo = conversa(
            professor_calculo,
            "Orientações para a prova de Cálculo II",
            ofertas["MAT204"],
            [
                (
                    professor_calculo,
                    f"Olá, {aluna.first_name}! A prova de Cálculo Diferencial II será em "
                    f"{data_prova:%d/%m/%Y}, às 19h10, na sala B204.\n\n"
                    "Revise integrais definidas e suas aplicações. A lista de revisão está "
                    "anexada. Leve documento de identificação e calculadora científica não "
                    "programável.",
                    timedelta(minutes=33),
                    True,
                ),
                (
                    aluna,
                    "Obrigada, professor! Vou revisar a lista. A prova também terá questões sobre "
                    "área entre curvas?",
                    timedelta(minutes=13),
                    True,
                ),
                (
                    professor_calculo,
                    f"Sim, {aluna.first_name}. Área entre curvas faz parte do conteúdo. Priorize os "
                    "exercícios 4 a 8. Bons estudos!",
                    timedelta(minutes=1),
                    False,
                ),
            ],
        )
        mensagens_calculo[0].anexo.save(
            "lista_de_revisao_calculo_ii.pdf",
            ContentFile(self.pdf_de_exemplo("Lista de revisão: Cálculo Diferencial II")),
        )

        conversa(
            self.alunos["coord01"],
            "Atualização dos seus dados cadastrais",
            None,
            [
                (
                    self.alunos["coord01"],
                    "Confira telefone e endereço no cadastro.",
                    timedelta(days=1),
                    False,
                )
            ],
        )
        conversa(
            ofertas["FIS202"].professor,
            "Atividade de Física Experimental",
            ofertas["FIS202"],
            [
                (
                    ofertas["FIS202"].professor,
                    f"A entrega está disponível até {prazo_entrega:%d/%m}.",
                    timedelta(days=2),
                    True,
                )
            ],
        )
        conversa(
            ofertas["COM203"].professor,
            "Material de Estruturas de Dados",
            ofertas["COM203"],
            [
                (
                    ofertas["COM203"].professor,
                    "Lista de exercícios sobre árvores e grafos.",
                    timedelta(days=3),
                    True,
                )
            ],
        )
        conversa(
            ofertas["GES201"].professor,
            "Encontro de orientação de projetos",
            ofertas["GES201"],
            [
                (
                    ofertas["GES201"].professor,
                    "Nosso próximo encontro será na sala C102.",
                    timedelta(days=5),
                    True,
                )
            ],
        )

    def criar_eventos_institucionais(self):
        eventos = [
            Evento(
                titulo=titulo,
                tipo=Evento.Tipo.FERIADO,
                descricao="Feriado nacional",
                inicio=self.inicio_do_dia(mes, dia),
            )
            for mes, dia, titulo in FERIADOS
        ]
        eventos += [
            Evento(titulo=titulo, inicio=self.inicio_do_dia(mes, dia))
            for mes, dia, titulo in EVENTOS_INSTITUCIONAIS
        ]
        Evento.objects.bulk_create(eventos)

    def inicio_do_dia(self, mes, dia):
        data = self.hoje.replace(month=mes, day=dia)
        return timezone.make_aware(datetime.combine(data, time(0, 0)))

    def criar_eventos_das_disciplinas(self, ofertas):
        Evento.objects.bulk_create(
            [
                Evento(
                    titulo="Orientação de projetos",
                    tipo=Evento.Tipo.ATIVIDADE,
                    oferta=ofertas["GES201"],
                    inicio=self.no_dia(5, 19, 0),
                    local="Sala C102",
                ),
                Evento(
                    titulo="Seminário de Estatística",
                    tipo=Evento.Tipo.ATIVIDADE,
                    oferta=ofertas["MAT206"],
                    inicio=self.no_dia(8, 19, 0),
                ),
            ]
        )

    def mostrar_resumo(self):
        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados."))
        contagens = (
            ("Usuários de demonstração", Usuario.objects.filter(matricula__in=self.matriculas_demo)),
            ("Turmas", Turma.objects.filter(codigo__in=TURMAS)),
            ("Matrículas", Matricula.objects.filter(turma__codigo__in=TURMAS)),
            ("Aulas", Aula.objects.filter(oferta__turma__codigo__in=TURMAS)),
            ("Notas", Nota.objects.filter(matricula__turma__codigo__in=TURMAS)),
            ("Presenças e faltas", Frequencia.objects.filter(matricula__turma__codigo__in=TURMAS)),
            ("Mensalidades", Mensalidade.objects.filter(matricula__turma__codigo__in=TURMAS)),
            ("Conversas", Conversa.objects.filter(aluno__matricula__in=self.matriculas_demo)),
        )
        for nome, consulta in contagens:
            self.stdout.write(f"  {nome}: {consulta.count()}")
        self.stdout.write("Acessos (senha igual à matrícula): coord01, prof01, aluno01")
