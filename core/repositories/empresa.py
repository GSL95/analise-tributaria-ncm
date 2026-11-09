from datetime import timedelta

from django.db.models import Count, Q


def listar_por_conta_ids(conta_ids):
    from core.models import Empresa
    return (
        Empresa.objects
        .filter(conta_id__in=conta_ids, ativa=True)
        .order_by("razao_social")
    )


def listar_ativas_por_conta(conta):
    from core.models import Empresa
    return Empresa.objects.filter(conta=conta, ativa=True)


def inativas_sem_upload(conta, dt_ini):
    """Empresas ativas sem nenhum upload nos últimos N dias."""
    from core.models import Empresa
    return (
        Empresa.objects
        .filter(conta=conta, ativa=True)
        .annotate(
            uploads_periodo=Count(
                "uploads_lotes",
                filter=Q(uploads_lotes__criado_em__gte=dt_ini),
            )
        )
        .filter(uploads_periodo=0)
        .order_by("razao_social")[:20]
    )


def distribuicao_regime(conta):
    """Contagem de empresas ativas agrupadas por regime tributário."""
    from core.models import Empresa
    return (
        Empresa.objects
        .filter(conta=conta, ativa=True)
        .values("regime_tributario")
        .annotate(qtd=Count("id"))
        .order_by("regime_tributario")
    )
