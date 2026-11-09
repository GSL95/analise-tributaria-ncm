from datetime import timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone


def listar_por_empresa(empresa, q: str = ""):
    from core.models import ProdutoNcm
    qs = ProdutoNcm.objects.filter(empresa=empresa).order_by("-criado_em")
    if q:
        qs = qs.filter(Q(produto__icontains=q) | Q(ncm__icontains=q))
    return qs


def listar_por_ncm(empresa, ncm: str, limit: int = 500):
    from core.models import ProdutoNcm
    return (
        ProdutoNcm.objects
        .filter(empresa=empresa, ncm=ncm)
        .order_by("produto")[:limit]
    )


def get_por_id_e_empresa(produto_id: int, empresa):
    from core.models import ProdutoNcm
    return get_object_or_404(ProdutoNcm, id=produto_id, empresa=empresa)


def listar_ncms_com_cache(empresa, q: str = "", filtro: str = "", lote_id=None):
    """
    Retorna QuerySet de NCMs únicos anotados com dados do cache mais recente.
    Inclui: cache_id, cache_status, cache_consultado_em, cache_resultado.
    """
    from core.models import AnaliseNcmCache, ProdutoNcm

    uf_origem = empresa.uf or "DF"
    uf_destino = "GO"

    produtos = ProdutoNcm.objects.filter(empresa=empresa)
    if lote_id:
        produtos = produtos.filter(upload_lote_id=lote_id)
    if q:
        produtos = produtos.filter(Q(ncm__icontains=q) | Q(produto__icontains=q))

    cache_subq = AnaliseNcmCache.objects.filter(
        empresa=empresa,
        ncm=OuterRef("ncm"),
        uf_origem=uf_origem,
        uf_destino=uf_destino,
        regime_tributario=empresa.regime_tributario,
        atividade_origem=empresa.atividade_origem,
        atividade_destino=empresa.atividade_destino,
    ).order_by("-consultado_em")

    return (
        produtos
        .values("ncm")
        .annotate(qtd_produtos=Count("id"))
        .order_by("ncm")
        .annotate(
            cache_id=Subquery(cache_subq.values("id")[:1]),
            cache_status=Subquery(cache_subq.values("status")[:1]),
            cache_consultado_em=Subquery(cache_subq.values("consultado_em")[:1]),
            cache_resultado=Subquery(cache_subq.values("resultado")[:1]),
        )
    )


def cache_mais_recente(empresa, ncm: str):
    from core.models import AnaliseNcmCache
    return (
        AnaliseNcmCache.objects
        .filter(empresa=empresa, ncm=ncm)
        .order_by("-consultado_em")
        .first()
    )


def get_cache_por_id_e_empresa(cache_id: int, empresa):
    from core.models import AnaliseNcmCache
    return get_object_or_404(AnaliseNcmCache, id=cache_id, empresa=empresa)


def kpis_ncm(base_ncms_qs):
    """Retorna KPIs a partir do QuerySet de NCMs com cache anotado."""
    trinta_dias_atras = timezone.now() - timedelta(days=30)
    return {
        "total_ncms": base_ncms_qs.count(),
        "sem_cache": base_ncms_qs.filter(cache_id__isnull=True).count(),
        "com_erro": base_ncms_qs.filter(cache_status="ERRO").count(),
        "atualizados_30d": base_ncms_qs.filter(
            cache_consultado_em__gte=trinta_dias_atras
        ).count(),
    }
