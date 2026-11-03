from django.urls import reverse

from .menu import AREAS


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
            "ativo": item["rota"] == rota_atual,
        }
        for item in area["itens"]
    ]
    return {"menu_area": area["titulo"], "menu_itens": itens}
