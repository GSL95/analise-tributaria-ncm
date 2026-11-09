from django.db.models import Q


def listar_por_empresa(empresa, q: str = "", data_ini: str = "", data_fim: str = ""):
    from core.models import NotaFiscal
    qs = NotaFiscal.objects.filter(empresa=empresa).order_by("-id")
    if q:
        qs = qs.filter(
            Q(chave__icontains=q)
            | Q(numero__icontains=q)
            | Q(cnpj_emitente__icontains=q)
            | Q(cnpj_destinatario__icontains=q)
        )
    if data_ini:
        qs = qs.filter(emissao_em__date__gte=data_ini)
    if data_fim:
        qs = qs.filter(emissao_em__date__lte=data_fim)
    return qs


def get_por_id_e_empresa(nota_id: int, empresa):
    from core.models import NotaFiscal
    return NotaFiscal.objects.filter(id=nota_id, empresa=empresa).first()


def itens_da_nota(nota):
    from core.models import ItemNotaFiscal
    return ItemNotaFiscal.objects.filter(nota=nota).order_by("n_item")
