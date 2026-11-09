from django.db.models import Count, Q


def listar_por_empresa(empresa, limit: int = 50):
    from core.models import UploadLote
    return (
        UploadLote.objects
        .filter(empresa=empresa)
        .order_by("-criado_em")[:limit]
    )


def get_por_empresa_e_id(empresa, lote_id: int):
    from core.models import UploadLote
    return UploadLote.objects.filter(id=lote_id, empresa=empresa).first()


def listar_por_conta(conta):
    from core.models import UploadLote
    return UploadLote.objects.filter(empresa__conta=conta)


def contagem_30d(uploads_qs, dt_ini):
    return uploads_qs.filter(criado_em__gte=dt_ini).count()


def contagem_erro_30d(uploads_qs, dt_ini):
    from core.models import UploadLote
    return uploads_qs.filter(criado_em__gte=dt_ini, status=UploadLote.Status.ERRO).count()


def contagem_pendentes(uploads_qs):
    from core.models import UploadLote
    return uploads_qs.filter(
        status__in=[UploadLote.Status.PENDENTE, UploadLote.Status.PROCESSANDO]
    ).count()


def lotes_travados(uploads_qs, travado_limite):
    """Lotes em PROCESSANDO há mais de N horas."""
    from core.models import UploadLote
    return (
        uploads_qs
        .filter(status=UploadLote.Status.PROCESSANDO, criado_em__lt=travado_limite)
        .select_related("empresa")
        .order_by("criado_em")[:10]
    )


def ultimos_lotes(uploads_qs, limit: int = 10):
    return (
        uploads_qs
        .select_related("empresa", "criado_por")
        .order_by("-criado_em")[:limit]
    )


def empresas_com_mais_erros(uploads_qs, dt_ini, limit: int = 10):
    from core.models import UploadLote
    return (
        uploads_qs
        .filter(criado_em__gte=dt_ini, status=UploadLote.Status.ERRO)
        .values("empresa__id", "empresa__razao_social")
        .annotate(qtd=Count("id"))
        .order_by("-qtd", "empresa__razao_social")[:limit]
    )
