"""Pequenas ajudas usadas pelos formulários e pelas views de várias áreas."""

import os

from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_date

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


# Datas fora deste intervalo vindas da URL são ignoradas, para evitar erros de cálculo.
ANO_MINIMO, ANO_MAXIMO = 2000, 2100


def data_valida(texto):
    """Converte o texto AAAA-MM-DD da URL em data, ou None se o valor não servir."""
    try:
        data = parse_date(texto)
    except ValueError:  # formato certo com data impossível, como 2026-13-45
        return None
    if data is None or not ANO_MINIMO <= data.year <= ANO_MAXIMO:
        return None
    return data


def saudacao():
    """Bom dia, Boa tarde ou Boa noite, conforme a hora atual."""
    hora = timezone.localtime().hour
    if hora < 12:
        return "Bom dia"
    return "Boa tarde" if hora < 18 else "Boa noite"


def texto_dias_ate(momento):
    """Texto do indicador "Próxima prova": Hoje, Amanhã ou Em N dias."""
    dias = (timezone.localtime(momento).date() - timezone.localdate()).days
    if dias <= 0:
        return "Hoje"
    return "Amanhã" if dias == 1 else f"Em {dias} dias"
