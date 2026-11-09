from django.http import Http404
from django.shortcuts import get_object_or_404

from core.models import Empresa, FilaAnalise, Membership


def get_empresa_ativa(request) -> Empresa:
    """Retorna a empresa ativa na sessão ou levanta 404."""
    empresa_id = request.session.get("empresa_ativa_id")
    return get_object_or_404(Empresa, id=empresa_id)


def get_empresa_or_404(request, empresa_id: int) -> Empresa:
    """Retorna empresa verificando membership do usuário autenticado."""
    empresa = get_object_or_404(Empresa, id=empresa_id)
    if not empresa.conta.memberships.filter(usuario=request.user).exists():
        raise Http404("Empresa não encontrada.")
    return empresa


def get_contas_do_usuario(user):
    """Retorna QuerySet de conta_ids do usuário."""
    return Membership.objects.filter(usuario=user).values_list("conta_id", flat=True)


def get_conta_id_unica(user):
    """Retorna a primeira conta_id do usuário (para criação de empresa)."""
    return Membership.objects.filter(usuario=user).values_list("conta_id", flat=True).first()


def get_fila_or_404(request, fila_id: int) -> FilaAnalise:
    """Retorna fila de análise verificando membership."""
    fila = get_object_or_404(FilaAnalise, id=fila_id)
    if not fila.empresa.conta.memberships.filter(usuario=request.user).exists():
        raise Http404("Fila não encontrada.")
    return fila
