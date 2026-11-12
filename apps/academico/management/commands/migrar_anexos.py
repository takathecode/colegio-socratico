"""Copia para o banco os anexos antigos que ficaram na pasta media/ deste computador.

Antes, o anexo era salvo só no disco da máquina que recebeu o envio. Rode este comando em cada
computador que tiver uma pasta media/ com arquivos: depois dele, os anexos aparecem para todos.
Pode rodar mais de uma vez: o que já está no banco é pulado.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.academico.models import ArquivoAnexo, Justificativa
from apps.mensagens.models import Mensagem


class Command(BaseCommand):
    help = "Copia para o banco os anexos antigos da pasta media/ deste computador."

    def handle(self, *args, **options):
        nomes = set(Mensagem.objects.exclude(anexo="").values_list("anexo", flat=True))
        nomes |= set(Justificativa.objects.exclude(anexo="").values_list("anexo", flat=True))
        ja_no_banco = set(ArquivoAnexo.objects.filter(nome__in=nomes).values_list("nome", flat=True))

        copiados = faltando = 0
        for nome in sorted(nomes - ja_no_banco):
            caminho = Path(settings.MEDIA_ROOT) / nome
            if not caminho.is_file():
                faltando += 1
                continue
            dados = caminho.read_bytes()
            ArquivoAnexo.objects.create(nome=nome, conteudo=dados, tamanho=len(dados))
            copiados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{copiados} anexo(s) copiado(s) para o banco; {len(ja_no_banco)} já estavam lá; "
                f"{faltando} não estão neste computador (rode o comando na máquina que os recebeu)."
            )
        )
