from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render, redirect

from core.services.authorization import get_empresa_ativa
import core.repositories.produto_ncm as produto_repo
import core.repositories.upload_lote as upload_repo


@login_required
def ncm_lista(request):
    empresa = get_empresa_ativa(request)
    if not empresa:
        return redirect("empresas")

    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("f", "")
    lote_id = request.GET.get("lote")

    base_ncms = produto_repo.listar_ncms_com_cache(empresa, q=q, filtro=filtro, lote_id=lote_id)

    if filtro == "sem_cache":
        base_ncms = base_ncms.filter(cache_id__isnull=True)
    elif filtro == "erro":
        base_ncms = base_ncms.filter(cache_status="ERRO")
    elif filtro == "ok":
        base_ncms = base_ncms.filter(cache_status="OK")

    kpis = produto_repo.kpis_ncm(base_ncms)

    paginator = Paginator(base_ncms, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    uf_origem = empresa.uf or "DF"
    rows = []
    for r in page_obj:
        resultado = r.get("cache_resultado") or {}
        rows.append({
            "ncm": r["ncm"],
            "qtd_produtos": r["qtd_produtos"],
            "cache_id": r.get("cache_id"),
            "status": r.get("cache_status"),
            "consultado_em": r.get("cache_consultado_em"),
            "desc_tipi": resultado.get("desc_tipi", ""),
            "uf_origem": uf_origem,
            "uf_destino": "GO",
            "regime_label": empresa.get_regime_tributario_display(),
        })
    page_obj.object_list = rows

    return render(request, "core/ncm_lista.html", {
        "empresa": empresa,
        "conta": empresa.conta,
        "page_obj": page_obj,
        "kpi_total_ncms": kpis["total_ncms"],
        "kpi_sem_cache": kpis["sem_cache"],
        "kpi_com_erro": kpis["com_erro"],
        "kpi_atualizados_30d": kpis["atualizados_30d"],
        "lotes": upload_repo.listar_por_empresa(empresa, limit=50),
    })


@login_required
def ncm_detalhe(request, ncm: str):
    empresa = get_empresa_ativa(request)
    produtos = produto_repo.listar_por_ncm(empresa, ncm)
    cache = produto_repo.cache_mais_recente(empresa, ncm)

    return render(request, "core/ncm_detalhe.html", {
        "empresa": empresa,
        "conta": empresa.conta if empresa else None,
        "ncm": ncm,
        "produtos": produtos,
        "cache": cache,
    })


@login_required
def ncm_cache(request, cache_id: int):
    empresa = get_empresa_ativa(request)
    cache = produto_repo.get_cache_por_id_e_empresa(cache_id, empresa)
    return render(request, "core/ncm_cache.html", {
        "empresa": empresa,
        "conta": empresa.conta if empresa else None,
        "cache": cache,
    })
