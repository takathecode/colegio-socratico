"""Pequenas ajudas usadas pelos formulários e pelas views de várias áreas."""

import os

from django.http import FileResponse, Http404

# Aparência dos campos de formulário. O Tailwind encontra estas classes porque também lê os .py.
CLASSES_CAMPO = (
    "w-full rounded-lg border border-[#E5E9F0] bg-white px-3 py-2.5 text-sm outline-none "
    "focus:border-[#1F4E8C] focus:ring-2 focus:ring-[#1F4E8C]/30 "
    "aria-[invalid=true]:border-[#C62828]"
)
FORMATOS_ANEXO = ".pdf,.jpg,.jpeg,.png"


def baixar_anexo(arquivo):
    """Entrega um anexo como download. Quem chama a função é que confere a permissão.

    O arquivo fica em media/, na máquina que recebeu o envio, enquanto o banco é compartilhado.
    Por isso ele pode não existir neste computador: nesse caso a resposta é 404, não um erro 500.
    """
    try:
        return FileResponse(
            arquivo.open("rb"), as_attachment=True, filename=os.path.basename(arquivo.name)
        )
    except FileNotFoundError as erro:
        raise Http404("O arquivo não está disponível neste computador.") from erro
