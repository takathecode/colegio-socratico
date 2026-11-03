from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.contas.decorators import perfil_requerido


@login_required
@perfil_requerido("ALUNO")
def painel(request):
    """Painel provisório: a tela completa é feita na etapa 4."""
    return render(request, "aluno/painel.html")
