from django.db.models import Count, Q
from django.shortcuts import get_object_or_404


def listar_por_empresa(empresa, q: str = "", ncm: str = "", lote_id: str = "", status: str = ""):
    """Retorna QuerySet filtrado para a listagem de análises."""
    from core.models import AnaliseItem
    qs = (
        AnaliseItem.objects
        .filter(empresa=empresa)
        .select_related("cache", "upload_lote", "produto_ncm")
        .order_by("-criado_em")
    )
    if q:
        qs = qs.filter(produto__icontains=q)
    if ncm:
        qs = qs.filter(ncm=ncm)
    if lote_id and str(lote_id).isdigit():
        qs = qs.filter(upload_lote_id=int(lote_id))
    status = status.upper()
    if status == "OK":
        qs = qs.filter(cache__status="OK")
    elif status == "ERRO":
        qs = qs.filter(cache__status="ERRO")
    elif status == "PENDENTE":
        qs = qs.filter(cache__isnull=True)
    return qs


def get_por_empresa_e_id(empresa, item_id: int):
    from core.models import AnaliseItem
    return get_object_or_404(
        AnaliseItem.objects.select_related("cache", "upload_lote", "produto_ncm"),
        id=item_id,
        empresa=empresa,
    )


def filas_ativas(empresa):
    from core.models import FilaAnalise
    return (
        FilaAnalise.objects
        .filter(
            empresa=empresa,
            status__in=[FilaAnalise.Status.PENDENTE, FilaAnalise.Status.ANALISANDO],
        )
        .order_by("-criado_em")
    )


def filas_recentes(empresa, limit: int = 5):
    from core.models import FilaAnalise
    return (
        FilaAnalise.objects
        .filter(
            empresa=empresa,
            status__in=[
                FilaAnalise.Status.CONCLUIDO,
                FilaAnalise.Status.ERRO,
                FilaAnalise.Status.CANCELADO,
            ],
        )
        .order_by("-criado_em")[:limit]
    )


# ──── Dashboard KPIs ────

def listar_por_conta(conta):
    from core.models import AnaliseItem
    return AnaliseItem.objects.filter(empresa__conta=conta)


def kpis_snapshot_30d(itens_30d_qs):
    """Retorna dict com métricas derivadas do resultado_snapshot."""
    total = itens_30d_qs.count()

    sem_ncm = itens_30d_qs.filter(Q(ncm="") | Q(ncm__isnull=True)).count()
    ncm_unicos = itens_30d_qs.exclude(ncm="").values("ncm").distinct().count()

    snapshot_ok = itens_30d_qs.filter(resultado_snapshot__status="OK").count()
    snapshot_erro = itens_30d_qs.filter(resultado_snapshot__status="ERRO").count()
    sem_base_pis = itens_30d_qs.filter(resultado_snapshot__base_legal_pis_cofins="").count()

    st_interna_q = (
        ~Q(resultado_snapshot__cest="")
        & ~Q(resultado_snapshot__cest__isnull=True)
        & ~Q(resultado_snapshot__descricao_st__icontains="NÃO TEM")
    )
    com_st_interna = itens_30d_qs.filter(st_interna_q).count()
    com_st_inter = itens_30d_qs.filter(
        ~Q(resultado_snapshot__cest_interestadual__icontains="NÃO TEM")
    ).count()

    com_obs_icms = itens_30d_qs.exclude(resultado_snapshot__observacao_icms="").count()
    com_obs_st = itens_30d_qs.exclude(resultado_snapshot__observacao_st="").count()

    def _perc(num, den):
        return round(num / den * 100, 2) if den else 0

    return {
        "total": total,
        "ncm_unicos": ncm_unicos,
        "sem_ncm": sem_ncm,
        "perc_sem_ncm": _perc(sem_ncm, total),
        "perc_snapshot_ok": _perc(snapshot_ok, total),
        "perc_snapshot_erro": _perc(snapshot_erro, total),
        "sem_base_pis": sem_base_pis,
        "perc_sem_base_pis": _perc(sem_base_pis, total),
        "com_st_interna": com_st_interna,
        "perc_st_interna": _perc(com_st_interna, total),
        "com_st_inter": com_st_inter,
        "perc_st_inter": _perc(com_st_inter, total),
        "com_obs_icms": com_obs_icms,
        "com_obs_st": com_obs_st,
        "st_interna_q": st_interna_q,
    }


def top_segmentos_st(itens_30d_qs, st_interna_q, limit: int = 10):
    return (
        itens_30d_qs
        .filter(st_interna_q)
        .exclude(resultado_snapshot__segmentos_st="")
        .values("resultado_snapshot__segmentos_st")
        .annotate(qtd=Count("id"))
        .order_by("-qtd", "resultado_snapshot__segmentos_st")[:limit]
    )


def top_bases_icms(itens_30d_qs, limit: int = 10):
    return (
        itens_30d_qs
        .exclude(resultado_snapshot__base_legal_icms_retornado="")
        .values("resultado_snapshot__base_legal_icms_retornado")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")[:limit]
    )


def distribuicao_aliquota_icms(itens_30d_qs, limit: int = 10):
    return (
        itens_30d_qs
        .exclude(resultado_snapshot__aliquota_icms_retornado__isnull=True)
        .values("resultado_snapshot__aliquota_icms_retornado")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")[:limit]
    )


def distribuicao_cst_pis(itens_30d_qs, limit: int = 10):
    return (
        itens_30d_qs
        .exclude(resultado_snapshot__cst_pis="")
        .values("resultado_snapshot__cst_pis")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")[:limit]
    )


def distribuicao_cst_cofins(itens_30d_qs, limit: int = 10):
    return (
        itens_30d_qs
        .exclude(resultado_snapshot__cst_cofins="")
        .values("resultado_snapshot__cst_cofins")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")[:limit]
    )


def top_produtos_sem_ncm(itens_30d_qs, limit: int = 10):
    return (
        itens_30d_qs
        .filter(Q(ncm="") | Q(ncm__isnull=True))
        .values("produto")
        .annotate(qtd=Count("id"))
        .order_by("-qtd", "produto")[:limit]
    )


def top_ncms(itens_30d_qs, limit: int = 10):
    return (
        itens_30d_qs
        .exclude(ncm="")
        .values("ncm")
        .annotate(qtd=Count("id"))
        .order_by("-qtd", "ncm")[:limit]
    )
