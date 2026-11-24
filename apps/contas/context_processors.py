from urllib.parse import urlencode

from django.urls import reverse

from .menu import AREAS


def endereco_da_ajuda(usuario):
    """Link do card "Precisa de ajuda?" da barra lateral (None: o card não aparece).

    - Aluno: abre uma mensagem nova já endereçada à Secretaria. As conversas do portal
      sempre têm um aluno de um dos lados, então só o aluno consegue escrever à Secretaria.
    - Professor e coordenação: a Central de Atendimento, que explica como falar com ela.
    - Secretaria: sem card (ela é a própria ajuda).
    """
    if usuario.perfil == "SECRETARIA":
        return None
    if usuario.perfil == "ALUNO":
        # Importado aqui: o app de mensagens depende do app de contas.
        from apps.mensagens.forms import secretaria

        conta = secretaria()
        if conta is not None:
            parametros = urlencode({"para": conta.pk, "assunto": "Acesso ao portal"})
            return f"{reverse('mensagens:caixa')}?{parametros}"
    return reverse("contas:atendimento")


def menu_lateral(request):
    """Entrega aos templates o menu do perfil logado, marcando o item da página atual."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}

    area = AREAS.get(usuario.perfil)
    if area is None:  # O perfil ADMIN usa o Django Admin, que não tem esta barra lateral.
        return {}

    rota_atual = getattr(getattr(request, "resolver_match", None), "view_name", None)
    itens = [
        {
            "nome": item["nome"],
            "icone": item["icone"],
            "url": reverse(item["rota"]) if item["rota"] else None,
            "ativo": rota_atual in (item["rota"], *item.get("tambem_ativo", ())),
        }
        for item in area["itens"]
    ]
    return {
        "menu_area": area["titulo"],
        "menu_itens": itens,
        "ajuda_url": endereco_da_ajuda(usuario),
    }
