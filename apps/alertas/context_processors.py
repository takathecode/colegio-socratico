from .models import Alerta

# Quantos alertas a lista do sino mostra. Os outros ficam na tela "Notificações".
ALERTAS_NO_SINO = 5

PERFIS_COM_SINO = ("ALUNO", "PROFESSOR", "COORDENADOR")


def sino(request):
    """Entrega ao topo das páginas o número de alertas não lidos e os mais recentes.

    O ADMIN usa o Django Admin, que não tem o sino. São duas consultas pequenas por página,
    ajudadas pelo índice (destinatário, lido em) do model Alerta.
    """
    usuario = getattr(request, "user", None)
    if usuario is None or getattr(usuario, "perfil", None) not in PERFIS_COM_SINO:
        return {}
    alertas = Alerta.objects.filter(destinatario=usuario)
    return {
        "sino_nao_lidos": alertas.filter(lido_em__isnull=True).count(),
        "sino_recentes": list(alertas[:ALERTAS_NO_SINO]),
    }
