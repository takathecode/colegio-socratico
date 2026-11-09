"""Treina o modelo de evasão com dados simulados e recalcula o risco dos alunos.

Uso: python manage.py treinar_modelo
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics import evasao

NOMES = {
    "frequencia": "Frequência",
    "media": "Média",
    "tendencia": "Tendência das notas",
    "justificativas_pendentes": "Justificativas pendentes",
}


def porcentagem(valor):
    return f"{valor * 100:.1f}%".replace(".", ",")


class Command(BaseCommand):
    help = "Treina o modelo de evasão (RandomForest com dados simulados) e recalcula os riscos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sem-calcular",
            action="store_true",
            help="Só treina, sem recalcular o risco dos alunos no banco.",
        )

    def handle(self, *args, **opcoes):
        self.stdout.write("Gerando alunos simulados e treinando o RandomForest...")
        resultado = evasao.treinar()

        self.stdout.write(f"Alunos simulados: {resultado['alunos_simulados']}")
        self.stdout.write(f"Evadiram na simulação: {porcentagem(resultado['taxa_evasao'])}")
        self.stdout.write(
            f"Acurácia nos 20% separados para teste: {porcentagem(resultado['acuracia'])} "
            f"(chutando que ninguém evade: {porcentagem(resultado['acuracia_chute'])})"
        )
        self.stdout.write("Peso de cada variável na decisão do modelo:")
        importancias = sorted(resultado["importancias"].items(), key=lambda item: -item[1])
        for nome, peso in importancias:
            self.stdout.write(f"  {NOMES[nome]}: {porcentagem(peso)}")
        self.stdout.write(self.style.SUCCESS(f"Modelo salvo em {settings.MODELO_EVASAO}"))

        if not opcoes["sem_calcular"]:
            total = evasao.calcular_riscos()
            self.stdout.write(self.style.SUCCESS(f"Risco recalculado para {total} aluno(s)."))
