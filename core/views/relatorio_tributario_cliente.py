from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Max, Sum
from django.shortcuts import render
from django.utils import timezone

from core.authz import empresa_ativa_required
from core.models import (
    Empresa,
    AnaliseItem,
    AnaliseNcmCache,
    ProdutoNcm,
    UploadLote,
    UploadArquivo,
)


def _empresa_ativa(request):
    empresa_id = request.session.get("empresa_ativa_id")
    return Empresa.objects.filter(id=empresa_id).select_related("conta").first()


@login_required
@empresa_ativa_required
def relatorio_tributario_cliente(request):

    empresa = _empresa_ativa(request)
    if not empresa:
        return render(request, "core/relatorios.html", {"sem_empresa": True})

    agora = timezone.now()
    dt_30 = agora - timedelta(days=30)

    # ============================
    # BASE DE DADOS
    # ============================

    itens = AnaliseItem.objects.filter(empresa=empresa).select_related("cache")
    caches = AnaliseNcmCache.objects.filter(empresa=empresa)
    produtos = ProdutoNcm.objects.filter(empresa=empresa)
    lotes = UploadLote.objects.filter(empresa=empresa)
    arquivos = UploadArquivo.objects.filter(lote__empresa=empresa)

    # ============================
    # INDICADORES ESTRATÉGICOS
    # ============================

    qtd_itens = itens.count()
    qtd_ncms = itens.exclude(ncm="").values("ncm").distinct().count()
    qtd_produtos = produtos.count()
    qtd_lotes = lotes.count()

    qtd_enquadrados = itens.exclude(resultado_snapshot={}).count()
    cobertura_pct = round((qtd_enquadrados / qtd_itens) * 100, 1) if qtd_itens else 0

    qtd_consultas_30d = caches.filter(consultado_em__gte=dt_30).count()

    # Período de análise
    periodo_itens = itens.aggregate(
        dt_min=Min("criado_em"),
        dt_max=Max("criado_em"),
    )

    periodo_consultas = caches.aggregate(
        dt_min=Min("consultado_em"),
        dt_max=Max("consultado_em"),
    )

    # Volume de dados processados
    resumo_arquivos = arquivos.aggregate(
        total_arquivos=Count("id"),
        total_bytes=Sum("tamanho"),
    )

    # ============================
    # ANÁLISES INTELIGENTES
    # ============================

    bases_counter = Counter()
    segmentos_counter = Counter()
    ncm_counter = Counter()

    for item in itens.exclude(resultado_snapshot={}):
        snap = item.resultado_snapshot or {}
        ncm_counter[item.ncm] += 1

        base = snap.get("base_legal_icms_retornado")
        if base:
            bases_counter[str(base).strip()] += 1

        segmentos = snap.get("segmentos_st")
        if isinstance(segmentos, list):
            for s in segmentos:
                segmentos_counter[str(s).strip()] += 1
        elif isinstance(segmentos, str) and segmentos.strip():
            segmentos_counter[segmentos.strip()] += 1

    top_bases = bases_counter.most_common(5)
    top_segmentos = segmentos_counter.most_common(5)
    top_ncms = ncm_counter.most_common(5)

    # ============================
    # TEXTO EXECUTIVO PROFISSIONAL
    # ============================

    resumo_executivo = f"""
Foi realizada uma análise técnica detalhada sobre o cadastro fiscal da empresa {empresa.razao_social},
abrangendo {qtd_itens} itens vinculados ao cadastro de produtos e totalizando {qtd_ncms} NCMs distintos.

A cobertura atual de enquadramento tributário encontra-se em {cobertura_pct}%,
indicando o grau de maturidade do cadastro tributário da empresa.

Foram processados {resumo_arquivos.get("total_arquivos", 0) or 0} arquivos fiscais,
consolidando dados estruturados para suporte à tomada de decisão tributária.

A análise contemplou regras de ICMS, Substituição Tributária (ST),
segmentação por atividade econômica, regime tributário ({empresa.get_regime_tributario_display()})
e cruzamento com contexto operacional (UF origem/destino).
"""

    # ============================
    # DIAGNÓSTICO CONSULTIVO
    # ============================

    diagnostico = f"""
Com base nos dados avaliados, observa-se que o cadastro tributário da empresa
apresenta nível de cobertura de {cobertura_pct}%.

Os NCMs mais recorrentes representam parte relevante da operação e devem
ser priorizados para validação estratégica junto ao departamento fiscal.

A análise evidencia padrões de enquadramento predominantes,
especialmente no que se refere às bases legais aplicáveis ao ICMS
e aos segmentos sujeitos à Substituição Tributária.

Recomenda-se institucionalizar um cadastro tributário padronizado
para garantir consistência fiscal em emissões, compras e auditorias.
"""

    # ============================
    # CONTEXTO
    # ============================

    context = {
        "empresa": empresa,
        "emitido_em": agora,

        # Indicadores
        "qtd_itens": qtd_itens,
        "qtd_ncms": qtd_ncms,
        "qtd_produtos": qtd_produtos,
        "qtd_lotes": qtd_lotes,
        "cobertura_pct": cobertura_pct,
        "qtd_consultas_30d": qtd_consultas_30d,

        "periodo_itens": periodo_itens,
        "periodo_consultas": periodo_consultas,
        "resumo_arquivos": resumo_arquivos,

        # Análises
        "top_bases": top_bases,
        "top_segmentos": top_segmentos,
        "top_ncms": top_ncms,

        # Texto estratégico
        "resumo_executivo": resumo_executivo.strip(),
        "diagnostico": diagnostico.strip(),
    }

    return render(request, "core/relatorio_analise_cliente.html", context)
