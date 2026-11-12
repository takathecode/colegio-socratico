"""Armazenamento dos anexos no banco de dados (modelo ArquivoAnexo).

Por que não a pasta media/: o banco é compartilhado (Supabase), mas cada computador tem a sua
pasta media/. O anexo enviado em uma máquina não chegava a quem abria a conversa em outra.
Guardando o conteúdo no banco, quem tem acesso à mensagem também tem acesso ao arquivo.

Os FileField continuam iguais (Mensagem.anexo e Justificativa.anexo): só muda o lugar onde o
Django grava e lê o arquivo. Ativado em settings.STORAGES["default"].

Anexos antigos, enviados antes desta mudança, ainda são lidos da pasta media/ quando não estão
no banco. O comando "python manage.py migrar_anexos" copia esses arquivos para o banco.
"""

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class ArmazenamentoNoBanco(Storage):
    def __init__(self):
        # Só para ler arquivos antigos que ficaram na pasta media/ deste computador.
        self.disco_local = FileSystemStorage()

    @staticmethod
    def _modelo():
        # Importação tardia: o armazenamento é criado antes de os apps estarem prontos.
        from .models import ArquivoAnexo

        return ArquivoAnexo

    def _save(self, name, content):
        content.seek(0)
        dados = content.read()
        self._modelo().objects.create(nome=name, conteudo=dados, tamanho=len(dados))
        return name

    def _open(self, name, mode="rb"):
        registro = self._modelo().objects.filter(nome=name).only("conteudo").first()
        if registro is not None:
            return ContentFile(bytes(registro.conteudo), name=name)
        # Anexo antigo: pode estar no disco deste computador. Se não estiver, o FileSystemStorage
        # levanta FileNotFoundError, e baixar_anexo responde 404.
        return self.disco_local.open(name, mode)

    def exists(self, name):
        return self._modelo().objects.filter(nome=name).exists() or self.disco_local.exists(name)

    def delete(self, name):
        self._modelo().objects.filter(nome=name).delete()

    def size(self, name):
        tamanho = self._modelo().objects.filter(nome=name).values_list("tamanho", flat=True).first()
        if tamanho is not None:
            return tamanho
        return self.disco_local.size(name)

    def url(self, name):
        # De propósito, não existe endereço público: o anexo só sai por uma view que confere a
        # permissão (mensagens:anexo, justificativas). Ver docs/SEGURANCA.md.
        raise NotImplementedError("Anexos são entregues só pelas views que conferem a permissão.")
