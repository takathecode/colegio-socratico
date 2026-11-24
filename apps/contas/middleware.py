"""Troca de senha obrigatória depois da senha provisória.

Quando a Secretaria gera uma senha provisória, a conta fica com precisa_trocar_senha=True.
Enquanto isso, qualquer tela leva para "Criar sua senha"; só essa tela e "Sair" abrem.
A conferência fica num middleware (e não em cada view) para nenhuma tela escapar,
inclusive as que forem criadas depois.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

# Rotas que continuam abrindo durante a troca obrigatória.
ROTAS_LIBERADAS = ("contas:senha_alterar", "contas:sair")


class TrocaDeSenhaObrigatoria:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and usuario.precisa_trocar_senha:
            liberados = [reverse(rota) for rota in ROTAS_LIBERADAS]
            # CSS, JavaScript e imagens também precisam abrir, para a tela ter o visual certo.
            if request.path not in liberados and not request.path.startswith(f"/{settings.STATIC_URL}"):
                return redirect("contas:senha_alterar")
        return self.get_response(request)
