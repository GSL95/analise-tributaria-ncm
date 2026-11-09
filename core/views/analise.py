# core/views/analise.py
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Empresa, AnaliseItem, ProdutoNcm, UploadLote, PlanilhaLinhaOriginal, FilaAnalise
from core.services.tributario.simples.cache_service import get_or_create_cache_simples
from core.services.tributario.lucro_real.cache_service import get_or_create_cache_lucro_real
from core.services.pos_analise import vincular_analise_itens_por_lote, pos_processar_divergencias
from core.services.fila_analise import iniciar_analise_em_background
from core.services.authorization import get_empresa_or_404, get_fila_or_404
from core.services.analise.exportador import gerar_xlsx_analise
import core.repositories.analise_item as analise_repo

_get_empresa_or_404 = get_empresa_or_404
_get_fila_or_404 = get_fila_or_404


@login_required
def analise_tributaria_list(request, empresa_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)

    q = (request.GET.get("q") or "").strip()
    ncm = (request.GET.get("ncm") or "").strip()
    lote_id = (request.GET.get("lote") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = analise_repo.listar_por_empresa(empresa, q=q, ncm=ncm, lote_id=lote_id, status=status)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    for item in page_obj:
        item.resultado = item.resultado_snapshot or (item.cache.resultado if item.cache else {})

    context = {
        "empresa": empresa,
        "page_obj": page_obj,
        "filters": {"q": q, "ncm": ncm, "lote": lote_id, "status": status},
        "filas_ativas": analise_repo.filas_ativas(empresa),
        "filas_recentes": analise_repo.filas_recentes(empresa),
    }
    return render(request, "core/analise_tributaria/list.html", context)


@login_required
def analise_tributaria_detail(request, empresa_id: int, item_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)
    item = analise_repo.get_por_empresa_e_id(empresa, item_id)
    resultado = item.resultado_snapshot or (item.cache.resultado if item.cache else {})

    context = {
        "empresa": empresa,
        "item": item,
        "resultado": resultado,
        "cache_status": item.cache.status if item.cache else "PENDENTE",
        "cache_erro": item.cache.erro_msg if item.cache else "",
        "raw_json": json.dumps(resultado or {}, ensure_ascii=False, indent=2, default=str),
    }
    return render(request, "core/analise_tributaria/detail.html", context)


@login_required
def analise_tributaria_exportar_xlsx(request, empresa_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)
    lote_id = request.GET.get("lote")

    output, filename = gerar_xlsx_analise(empresa, lote_id)

    resp = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@require_POST
def analise_tributaria_disparar(request, empresa_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)

    lote_id = (request.POST.get("lote") or "").strip()

    if empresa.regime_tributario in (None, "", Empresa.RegimeTributario.OUTRO):
        messages.error(request, "Selecione um regime tributário válido no cadastro da empresa.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    if empresa.atividade_origem in (None, Empresa.Atividade.OUTRO) or empresa.atividade_destino in (None, Empresa.Atividade.OUTRO):
        messages.error(request, "Selecione Atividade de Origem e Destino válidas no cadastro da empresa.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    lote_obj = None
    if lote_id.isdigit():
        lote_obj = UploadLote.objects.filter(id=int(lote_id), empresa=empresa).first()

    fila = FilaAnalise.objects.create(
        empresa=empresa,
        upload_lote=lote_obj,
        criado_por=request.user,
        status=FilaAnalise.Status.PENDENTE,
    )

    iniciar_analise_em_background(fila.id)
    return redirect("fila_analise_status", fila_id=fila.id)


@login_required
@require_POST
def analise_tributaria_analisar_produto(request, empresa_id: int, produto_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)

    produto = get_object_or_404(ProdutoNcm, id=produto_id, empresa=empresa)

    if not produto.ncm or len(produto.ncm) != 8:
        messages.error(request, "Produto sem NCM válido.")
        return redirect("produtos_importados")

    atividade_origem = empresa.atividade_origem
    atividade_destino = empresa.atividade_destino
    regime = empresa.regime_tributario

    if regime == Empresa.RegimeTributario.SN:
        cache = get_or_create_cache_simples(
            empresa=empresa,
            ncm=produto.ncm,
            nome_item=produto.produto,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            forcar_recalculo=False,
        )
    elif regime in (Empresa.RegimeTributario.REAL, Empresa.RegimeTributario.PRESUMIDO):
        cache = get_or_create_cache_lucro_real(
            empresa=empresa,
            ncm=produto.ncm,
            nome_item=produto.produto,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            regime=regime,
        )
    else:
        messages.error(request, "Regime tributário da empresa não suportado para análise. ORIGINAL")
        return redirect("produtos_importados")

    analise, created = AnaliseItem.objects.get_or_create(
        empresa=empresa,
        upload_lote=produto.upload_lote,
        produto_ncm=produto,
        defaults={
            "produto": produto.produto,
            "ncm": produto.ncm,
            "cache": cache,
            "resultado_snapshot": cache.resultado if cache.status == "OK" else {},
        },
    )

    if not created:
        analise.cache = cache
        analise.resultado_snapshot = cache.resultado if cache.status == "OK" else {}
        analise.save(update_fields=["cache", "resultado_snapshot"])

    if produto.upload_lote_id:
        pos_processar_divergencias(empresa_id=empresa.id, lote_id=produto.upload_lote_id)

    if cache.status == "OK":
        messages.success(request, "Produto analisado com sucesso.")
    else:
        messages.error(request, f"Produto analisado, porém houve erro: {cache.erro_msg or 'erro desconhecido'}")

    return redirect("analise_tributaria_detail", empresa_id=empresa.id, item_id=analise.id)


@login_required
@require_POST
def analise_tributaria_reprocessar(request, empresa_id: int, item_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)
    item = get_object_or_404(AnaliseItem, id=item_id, empresa=empresa)

    if not item.ncm or len(item.ncm) != 8:
        messages.error(request, "NCM inválido para reprocessar.")
        return redirect("analise_tributaria_detail", empresa_id=empresa.id, item_id=item.id)

    atividade_origem = empresa.atividade_origem
    atividade_destino = empresa.atividade_destino
    regime = empresa.regime_tributario

    if regime == Empresa.RegimeTributario.SN:
        cache = get_or_create_cache_simples(
            empresa=empresa,
            ncm=item.ncm,
            nome_item=item.produto,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            forcar_recalculo=True,
        )
    elif regime in (Empresa.RegimeTributario.PRESUMIDO, Empresa.RegimeTributario.REAL):
        cache = get_or_create_cache_lucro_real(
            empresa=empresa,
            ncm=item.ncm,
            nome_item=item.produto,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            regime=regime,
        )
    else:
        messages.error(request, "Regime tributário da empresa não suportado para análise.")
        return redirect("analise_tributaria_detail", empresa_id=empresa.id, item_id=item.id)

    item.cache = cache
    item.resultado_snapshot = cache.resultado if cache.status == "OK" else {}
    item.save(update_fields=["cache", "resultado_snapshot"])

    if item.upload_lote_id:
        pos_processar_divergencias(empresa_id=empresa.id, lote_id=item.upload_lote_id)

    if cache.status == "OK":
        messages.success(request, "Análise reprocessada com sucesso.")
    else:
        messages.error(request, f"Erro ao reprocessar: {cache.erro_msg or 'erro desconhecido'}")

    return redirect("analise_tributaria_detail", empresa_id=empresa.id, item_id=item.id)


@login_required
@require_POST
def analise_tributaria_analisar_item(request, empresa_id: int):
    empresa = _get_empresa_or_404(request, empresa_id)

    produto = (request.POST.get("produto") or "").strip()
    ncm = "".join(c for c in (request.POST.get("ncm") or "") if c.isdigit())

    if not produto:
        messages.error(request, "Informe o nome do produto.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    if not ncm or len(ncm) != 8:
        messages.error(request, "Informe um NCM válido com 8 dígitos.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    atividade_origem = empresa.atividade_origem
    atividade_destino = empresa.atividade_destino

    if empresa.regime_tributario in (None, "", Empresa.Regime.OUTRO):
        messages.error(request, "Selecione um regime tributário válido no cadastro da empresa.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    if atividade_origem in (None, Empresa.Atividade.OUTRO) or atividade_destino in (None, Empresa.Atividade.OUTRO):
        messages.error(request, "Selecione Atividade de Origem e Destino válidas no cadastro da empresa.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    if empresa.regime_tributario == Empresa.Regime.SN:
        cache = get_or_create_cache_simples(
            empresa=empresa,
            ncm=ncm,
            nome_item=produto,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            forcar_recalculo=False,
        )
    elif empresa.regime_tributario in (Empresa.Regime.REAL, Empresa.Regime.PRESUMIDO):
        cache = get_or_create_cache_lucro_real(
            empresa=empresa,
            ncm=ncm,
            nome_item=produto,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            regime=empresa.regime_tributario,
        )
    else:
        messages.error(request, "Regime tributário da empresa não suportado para análise.")
        return redirect("analise_tributaria_list", empresa_id=empresa.id)

    analise = AnaliseItem.objects.create(
        empresa=empresa,
        produto=produto,
        ncm=ncm,
        cache=cache,
        resultado_snapshot=cache.resultado if cache.status == "OK" else {},
    )

    if cache.status == "OK":
        messages.success(request, "Análise avulsa gerada com sucesso.")
    else:
        messages.error(request, f"Análise gerada, porém houve erro: {cache.erro_msg or 'erro desconhecido'}")

    return redirect("analise_tributaria_detail", empresa_id=empresa.id, item_id=analise.id)


@login_required
@require_POST
def analise_tributaria_retomar(request, empresa_id: int, fila_id: int):
    """Continua uma análise interrompida (ERRO/CANCELADO) pulando os produtos já processados."""
    empresa = _get_empresa_or_404(request, empresa_id)
    fila_anterior = _get_fila_or_404(request, fila_id)

    if fila_anterior.empresa_id != empresa.id:
        raise Http404("Fila não encontrada.")

    if fila_anterior.status not in (FilaAnalise.Status.ERRO, FilaAnalise.Status.CANCELADO):
        messages.error(request, "Essa análise não está interrompida, não há o que retomar.")
        return redirect("fila_analise_status", fila_id=fila_anterior.id)

    nova_fila = FilaAnalise.objects.create(
        empresa=empresa,
        upload_lote=fila_anterior.upload_lote,
        criado_por=request.user,
        status=FilaAnalise.Status.PENDENTE,
    )
    iniciar_analise_em_background(nova_fila.id, apenas_pendentes=True)
    return redirect("fila_analise_status", fila_id=nova_fila.id)


@login_required
@require_POST
def fila_analise_cancelar(request, fila_id: int):
    fila = _get_fila_or_404(request, fila_id)
    if fila.status in (FilaAnalise.Status.PENDENTE, FilaAnalise.Status.ANALISANDO):
        FilaAnalise.objects.filter(pk=fila_id).update(status=FilaAnalise.Status.CANCELADO)
    return redirect("fila_analise_status", fila_id=fila_id)


@login_required
def fila_analise_status(request, fila_id: int):
    fila = _get_fila_or_404(request, fila_id)
    return render(request, "core/fila_analise_status.html", {"fila": fila})


@login_required
def fila_analise_status_json(request, fila_id: int):
    try:
        fila = _get_fila_or_404(request, fila_id)
        percentual = round((fila.processados / fila.total * 100), 1) if fila.total > 0 else 0.0
        return JsonResponse({
            "status": str(fila.status),
            "status_display": str(fila.get_status_display()),
            "total": int(fila.total),
            "processados": int(fila.processados),
            "percentual": float(percentual),
            "produto_atual": (fila.produto_atual or "").encode("utf-8", errors="replace").decode("utf-8"),
            "erro_msg": (fila.erro_msg or "").encode("utf-8", errors="replace").decode("utf-8"),
        })
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)
