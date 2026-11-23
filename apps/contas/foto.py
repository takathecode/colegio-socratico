"""Foto de perfil: regras de validação, nome do arquivo e tipo da imagem.

A foto fica no banco, como os anexos (apps/academico/armazenamento.py), para aparecer em
qualquer computador e na Vercel. Não existe endereço público: ela só sai pelas views
contas:foto (a própria) e contas:foto_de (a de outra pessoa, conferida por pode_ver_foto).

Por segurança, o tipo da imagem é conferido pelos primeiros bytes do arquivo (a "assinatura"),
e não só pela extensão: um arquivo "foto.png" que na verdade é HTML ou SVG é recusado.
Isso é feito sem bibliotecas novas.

No navegador, o portal.js recorta a foto em quadrado, reduz para 512×512 e regrava em JPEG
antes do envio. Isso deixa o arquivo pequeno e apaga os metadados (EXIF), como a localização
GPS das fotos de celular. Sem JavaScript a foto chega como foi escolhida, e estas regras
continuam valendo.
"""

import uuid
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

TAMANHO_MAXIMO_FOTO = 2 * 1024 * 1024  # 2 MB
EXTENSOES_FOTO = ["jpg", "jpeg", "png", "webp"]
TIPOS_FOTO = "image/jpeg,image/png,image/webp"  # atributo accept do campo no HTML


def tipo_da_imagem(cabecalho):
    """Devolve o tipo (ex.: "image/png") pelos primeiros bytes, ou None se não for JPG/PNG/WebP."""
    if cabecalho.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if cabecalho.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if cabecalho[:4] == b"RIFF" and cabecalho[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_foto(arquivo):
    """Confere o tamanho e se o conteúdo é mesmo uma imagem JPG, PNG ou WebP."""
    if arquivo.size > TAMANHO_MAXIMO_FOTO:
        raise ValidationError("A foto deve ter no máximo 2 MB.")
    arquivo.seek(0)
    cabecalho = arquivo.read(12)
    arquivo.seek(0)
    if tipo_da_imagem(cabecalho) is None:
        raise ValidationError("O arquivo não é uma imagem JPG, PNG ou WebP válida.")


VALIDADORES_FOTO = [
    FileExtensionValidator(
        EXTENSOES_FOTO, message="Use uma imagem JPG, PNG ou WebP."
    ),
    validar_foto,
]


def pode_ver_foto(quem, dono):
    """Diz se `quem` pode ver a foto de `dono`.

    Sem hierarquia: aluno, professor e coordenação veem a foto de qualquer conta do portal.
    Quem chega até aqui já passou pelo login e pelo @perfil_requerido da view, então um
    visitante nunca vê foto nenhuma. A única exceção é a conta ADMIN, que não usa o portal.
    """
    from .models import Usuario  # importado aqui: models.py importa este arquivo

    return dono.perfil != Usuario.Perfil.ADMIN


def caminho_da_foto(usuario, nome_enviado):
    """Nome sorteado para o arquivo: não guarda o nome original nem a matrícula da pessoa."""
    extensao = PurePath(nome_enviado).suffix.lower().lstrip(".")
    return f"fotos/{uuid.uuid4().hex}.{extensao}"
