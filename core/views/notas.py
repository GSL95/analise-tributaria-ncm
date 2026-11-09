from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from core.authz import empresa_ativa_required
from core.services.authorization import get_empresa_ativa
import core.repositories.nota_fiscal as nota_repo


@login_required
@empresa_ativa_required
def notas(request):
    empresa = get_empresa_ativa(request)

    q = (request.GET.get("q") or "").strip()
    data_ini = (request.GET.get("ini") or "").strip()
    data_fim = (request.GET.get("fim") or "").strip()

    notas_qs = nota_repo.listar_por_empresa(empresa, q=q, data_ini=data_ini, data_fim=data_fim)

    paginator = Paginator(notas_qs, 20)
    page = paginator.get_page(request.GET.get("page"))

    nota_id = request.GET.get("nota")
    itens = []
    nota_selecionada = None

    if nota_id:
        nota_selecionada = nota_repo.get_por_id_e_empresa(nota_id, empresa)
        if nota_selecionada:
            itens = nota_repo.itens_da_nota(nota_selecionada)

    return render(request, "core/notas.html", {
        "empresa": empresa,
        "q": q,
        "ini": data_ini,
        "fim": data_fim,
        "page": page,
        "nota_selecionada": nota_selecionada,
        "itens": itens,
        "abrir_modal": bool(nota_selecionada),
    })
