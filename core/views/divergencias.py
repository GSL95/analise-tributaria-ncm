# core/views/divergencias.py
from django.core.paginator import Paginator
from django.shortcuts import render

from core.services.authorization import get_empresa_ativa
import core.repositories.divergencia as div_repo


def divergencias_fiscais(request):
    empresa = get_empresa_ativa(request)
    if empresa is None:
        return render(request, "core/divergencias.html", {
            "page": None,
            "empresa": None,
            "q": "",
            "sev": "",
            "tipo": "",
            "nota_id": "",
            "tipos": [],
        })

    q = (request.GET.get("q") or "").strip()
    sev = (request.GET.get("sev") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    nota_id = (request.GET.get("nota") or "").strip()

    qs = div_repo.listar_por_empresa(empresa, q=q, sev=sev, tipo=tipo, nota_id=nota_id)
    tipos = list(div_repo.tipos_por_empresa(empresa))

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "core/divergencias.html", {
        "page": page,
        "empresa": empresa,
        "q": q,
        "sev": sev,
        "tipo": tipo,
        "nota_id": nota_id,
        "tipos": tipos,
    })
