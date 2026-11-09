from django.db.models import Q


def listar_por_empresa(empresa, q: str = "", sev: str = "", tipo: str = "", nota_id: str = ""):
    from core.models import DivergenciaItem
    qs = (
        DivergenciaItem.objects
        .filter(item__empresa=empresa)
        .exclude(encontrado__isnull=True)
        .exclude(encontrado__exact="(vazio)")
        .select_related("item", "item__nota")
        .order_by("-criado_em")
    )
    if sev:
        qs = qs.filter(severidade=sev)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if nota_id and nota_id.isdigit():
        qs = qs.filter(item__nota_id=int(nota_id))
    if q:
        qs = qs.filter(
            Q(item__produto__icontains=q)
            | Q(item__ncm__icontains=q)
            | Q(item__cfop__icontains=q)
            | Q(item__nota__chave__icontains=q)
            | Q(item__nota__numero__icontains=q)
            | Q(esperado__icontains=q)
            | Q(encontrado__icontains=q)
        )
    return qs


def tipos_por_empresa(empresa):
    from core.models import DivergenciaItem
    return (
        DivergenciaItem.objects
        .filter(item__empresa=empresa)
        .values_list("tipo", flat=True)
        .distinct()
        .order_by("tipo")
    )
