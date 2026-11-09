# core/views/dashboard.py
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from core.models import Empresa
import core.repositories.analise_item as analise_repo
import core.repositories.empresa as empresa_repo
import core.repositories.upload_lote as upload_repo


@login_required
def dashboard_geral(request):
    membership = request.user.memberships.select_related("conta").order_by("id").first()
    if not membership:
        return render(request, "core/dashboard.html", {"sem_conta": True})

    conta = membership.conta
    agora = timezone.now()
    dt_ini = agora - timedelta(days=30)

    uploads_qs = upload_repo.listar_por_conta(conta)
    itens_qs = analise_repo.listar_por_conta(conta)
    itens_30d_qs = itens_qs.filter(criado_em__gte=dt_ini)

    kpis = analise_repo.kpis_snapshot_30d(itens_30d_qs)
    st_interna_q = kpis.pop("st_interna_q")

    dist_regime_raw = empresa_repo.distribuicao_regime(conta)
    regime_map = dict(Empresa.RegimeTributario.choices)
    dist_regime = [
        {"regime": regime_map.get(r["regime_tributario"], "Outro"), "qtd": r["qtd"]}
        for r in dist_regime_raw
    ]

    return render(request, "core/dashboard.html", {
        "conta": conta,
        "dt_ini": dt_ini,

        # KPIs básicos
        "empresas_ativas": empresa_repo.listar_ativas_por_conta(conta).count(),
        "uploads_30d": upload_repo.contagem_30d(uploads_qs, dt_ini),
        "uploads_erro_30d": upload_repo.contagem_erro_30d(uploads_qs, dt_ini),
        "uploads_pendentes": upload_repo.contagem_pendentes(uploads_qs),
        "itens_30d": kpis["total"],
        "ncm_unicos_30d": kpis["ncm_unicos"],

        # Qualidade
        "itens_sem_ncm_30d": kpis["sem_ncm"],
        "perc_sem_ncm_30d": kpis["perc_sem_ncm"],

        # Snapshot: valor tributário
        "perc_snapshot_ok_30d": kpis["perc_snapshot_ok"],
        "perc_snapshot_erro_30d": kpis["perc_snapshot_erro"],
        "itens_sem_base_pis_cofins_30d": kpis["sem_base_pis"],
        "perc_sem_base_pis_cofins_30d": kpis["perc_sem_base_pis"],
        "perc_st_interna_30d": kpis["perc_st_interna"],
        "perc_st_inter_30d": kpis["perc_st_inter"],
        "itens_com_obs_icms_30d": kpis["com_obs_icms"],
        "itens_com_obs_st_30d": kpis["com_obs_st"],

        # Tabelas/Rankings
        "top_segmentos_st_30d": analise_repo.top_segmentos_st(itens_30d_qs, st_interna_q),
        "top_bases_icms_30d": analise_repo.top_bases_icms(itens_30d_qs),
        "dist_aliq_icms_30d": analise_repo.distribuicao_aliquota_icms(itens_30d_qs),
        "dist_cst_pis_30d": analise_repo.distribuicao_cst_pis(itens_30d_qs),
        "dist_cst_cofins_30d": analise_repo.distribuicao_cst_cofins(itens_30d_qs),
        "top_produtos_sem_ncm": analise_repo.top_produtos_sem_ncm(itens_30d_qs),
        "top_ncms_30d": analise_repo.top_ncms(itens_30d_qs),

        "lotes_travados": upload_repo.lotes_travados(uploads_qs, agora - timedelta(hours=6)),
        "ultimos_lotes": upload_repo.ultimos_lotes(uploads_qs),
        "empresas_com_erro_upload": upload_repo.empresas_com_mais_erros(uploads_qs, dt_ini),
        "empresas_inativas": empresa_repo.inativas_sem_upload(conta, dt_ini),
        "dist_regime": dist_regime,
    })
