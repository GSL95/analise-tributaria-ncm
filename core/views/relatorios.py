from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Min, Max
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core.authz import empresa_ativa_required
from core.models import (
    AnaliseItem,
    AnaliseNcmCache,
    Membership,
    ProdutoNcm,
    UploadArquivo,
    UploadLote,
)
from core.services.authorization import get_empresa_ativa

from core.utils.relatorio_word import gerar_relatorio_word


def _pct(num, den, ndigits=1):
    if not den:
        return 0
    return round((num / den) * 100, ndigits)


def _fmt_bytes(n):
    if not n:
        return "0 B"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _get_cache_ncm_field():
    """
    Descobre automaticamente o nome do campo de NCM no model AnaliseNcmCache.
    Evita depender de "ncm" caso você use outro nome (ex.: "ncm_codigo", etc.).
    """
    candidates = ("ncm", "ncm_codigo", "codigo_ncm", "ncm_code")
    field_names = {f.name for f in AnaliseNcmCache._meta.fields}
    for c in candidates:
        if c in field_names:
            return c
    return None


@login_required
@empresa_ativa_required
def relatorios(request):
    empresa = get_empresa_ativa(request)
    if not empresa:
        return render(request, "core/relatorios.html", {"sem_empresa": True})

    agora = timezone.now()
    dt_ini_30d = agora - timedelta(days=30)

    # ================================
    # CONTA / PAPEL DO USUÁRIO
    # ================================
    conta = empresa.conta
    membership = (
        Membership.objects
        .filter(conta=conta, usuario=request.user)
        .only("papel", "criado_em")
        .first()
    )
    papel_usuario = membership.papel if membership else None

    # ================================
    # BASE (querysets)
    # ================================
    itens_qs = (
        AnaliseItem.objects
        .filter(empresa=empresa)
        .select_related("cache", "upload_lote", "produto_ncm", "planilha_linha")
    )
    caches_qs = AnaliseNcmCache.objects.filter(empresa=empresa)
    produtos_qs = ProdutoNcm.objects.filter(empresa=empresa)
    lotes_qs = UploadLote.objects.filter(empresa=empresa).select_related("criado_por")
    arquivos_qs = UploadArquivo.objects.filter(lote__empresa=empresa)

    # ================================
    # MÉTRICAS OPERACIONAIS (interno)
    # ================================
    qtd_itens_operacionais = itens_qs.count()
    qtd_itens_com_cache_operacionais = itens_qs.filter(cache__isnull=False).count()
    qtd_itens_sem_cache_operacionais = itens_qs.filter(cache__isnull=True).count()

    # ================================
    # MÉTRICAS DO CLIENTE (cadastro) — usa ProdutoNcm + Cache por NCM
    # ================================
    qtd_produtos = produtos_qs.count()

    # NCMs distintos do cadastro (ProdutoNcm)
    produto_ncms_distintos = list(
        produtos_qs.exclude(ncm="")
        .values_list("ncm", flat=True)
        .distinct()
    )
    qtd_ncms_distintos = len(produto_ncms_distintos)

    # Cache OK/ERRO (quantidade de registros)
    qtd_ok = caches_qs.filter(status=AnaliseNcmCache.Status.OK).count()
    qtd_erro = caches_qs.filter(status=AnaliseNcmCache.Status.ERRO).count()
    qtd_total_cache = qtd_ok + qtd_erro

    qtd_atualizados_30d = caches_qs.filter(consultado_em__gte=dt_ini_30d).count()

    taxa_sucesso_cache_pct = _pct(qtd_ok, qtd_total_cache)
    taxa_erro_cache_pct = _pct(qtd_erro, qtd_total_cache)

    # Campo NCM no cache (auto)
    cache_ncm_field = _get_cache_ncm_field()

    cache_ok_ncms_set = set()
    if cache_ncm_field:
        cache_ok_ncms_set = set(
            caches_qs.filter(status=AnaliseNcmCache.Status.OK)
            .exclude(**{f"{cache_ncm_field}__isnull": True})
            .exclude(**{cache_ncm_field: ""})
            .values_list(cache_ncm_field, flat=True)
            .distinct()
        )

    # Cobertura por NCM (cliente)
    produto_ncms_set = set(produto_ncms_distintos)
    ncms_cobertos = len(produto_ncms_set & cache_ok_ncms_set) if cache_ncm_field else 0
    cobertura_ncms_pct = _pct(ncms_cobertos, qtd_ncms_distintos)

    # Cobertura por PRODUTO (cliente): produto coberto se NCM do produto está OK no cache
    if cache_ncm_field and cache_ok_ncms_set:
        produtos_cobertos = produtos_qs.exclude(ncm="").filter(ncm__in=cache_ok_ncms_set).count()
    else:
        produtos_cobertos = 0

    cobertura_produtos_pct = _pct(produtos_cobertos, qtd_produtos)

    # Pendência REAL do cadastro (cliente)
    produtos_sem_ncm = produtos_qs.filter(ncm="").count()
    if cache_ncm_field and cache_ok_ncms_set:
        produtos_com_ncm_sem_ok = produtos_qs.exclude(ncm="").exclude(ncm__in=cache_ok_ncms_set).count()
    else:
        # Sem campo NCM no cache: não dá para provar cobertura por produto; assume tudo pendente
        produtos_com_ncm_sem_ok = produtos_qs.exclude(ncm="").count()

    pendencias_cadastro = produtos_sem_ncm + produtos_com_ncm_sem_ok

    # ================================
    # INTERVALOS
    # ================================
    range_itens = itens_qs.aggregate(dt_min=Min("criado_em"), dt_max=Max("criado_em"))
    range_caches = caches_qs.aggregate(dt_min=Min("consultado_em"), dt_max=Max("consultado_em"))

    # ================================
    # UPLOADS / LOTES
    # ================================
    lotes_por_status = list(
        lotes_qs.values("status").annotate(qtd=Count("id")).order_by("-qtd")
    )
    lotes_por_tipo = list(
        lotes_qs.values("tipo").annotate(qtd=Count("id")).order_by("-qtd")
    )

    ultimo_lote = lotes_qs.order_by("-criado_em").first()
    resumo_arquivos = arquivos_qs.aggregate(
        qtd_arquivos=Count("id"),
        total_bytes=Sum("tamanho"),
        dt_min=Min("criado_em"),
        dt_max=Max("criado_em"),
    )
    resumo_arquivos_fmt = {
        **resumo_arquivos,
        "total_bytes_fmt": _fmt_bytes(resumo_arquivos.get("total_bytes") or 0),
    }

    # ================================
    # PRODUTOS / NCMs (ranking)
    # ================================
    top_ncms_por_produtos = list(
        produtos_qs.exclude(ncm="")
        .values("ncm")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")[:10]
    )
    top_ncms = top_ncms_por_produtos  # compatibilidade com template

    origem_produtos = list(
        produtos_qs.values("origem").annotate(qtd=Count("id")).order_by("-qtd")
    )

    # ================================
    # ACHADOS (snapshot / cache.resultado)
    # ================================
    bases_counter = Counter()
    segmentos_counter = Counter()
    cfop_counter = Counter()
    cst_counter = Counter()

    erros_counter = Counter(
        str(e).strip()
        for e in caches_qs.filter(status=AnaliseNcmCache.Status.ERRO)
        .exclude(erro_msg="")
        .values_list("erro_msg", flat=True)
    )

    for snap in itens_qs.exclude(resultado_snapshot={}).values_list("resultado_snapshot", flat=True):
        if not isinstance(snap, dict):
            continue

        base = snap.get("base_legal_st")
        if base:
            bases_counter[str(base).strip()] += 1

        segs = snap.get("segmentos_st") or snap.get("segmentos_st_retornado")
        if isinstance(segs, list):
            for s in segs:
                if s:
                    segmentos_counter[str(s).strip()] += 1
        elif isinstance(segs, str) and segs.strip():
            parts = [p.strip() for p in segs.replace(";", ",").split(",")]
            for p in parts:
                if p:
                    segmentos_counter[p] += 1

        cfop = snap.get("cfop")
        if cfop:
            cfop_counter[str(cfop).strip()] += 1

        cst = snap.get("cst_icms") or snap.get("cst")
        if cst:
            cst_counter[str(cst).strip()] += 1

    top_bases = [{"base": k, "qtd": v} for k, v in bases_counter.most_common(8)]
    top_segmentos = [{"segmento": k, "qtd": v} for k, v in segmentos_counter.most_common(8)]
    top_cfops = [{"cfop": k, "qtd": v} for k, v in cfop_counter.most_common(8)]
    top_csts = [{"cst": k, "qtd": v} for k, v in cst_counter.most_common(8)]
    top_erros = [{"erro": k, "qtd": v} for k, v in erros_counter.most_common(5)]

    # ================================
    # CONTEXTO OPERACIONAL (Empresa)
    # ================================
    regime_label = empresa.get_regime_tributario_display()
    atividade_origem_label = empresa.get_atividade_origem_display()
    atividade_destino_label = empresa.get_atividade_destino_display()

    # ================================
    # TEXTO PRINCIPAL
    # ================================
    texto_principal = f"""
    RELATÓRIO DE DIAGNÓSTICO TRIBUTÁRIO — VERSÃO EXECUTIVA (APRESENTAÇÃO AO CLIENTE)

    Empresa: {empresa.razao_social} (CNPJ {empresa.cnpj}) | UF {empresa.uf or "—"}
    Regime: {regime_label} | Operação: {atividade_origem_label} → {atividade_destino_label}
    Emissão: {agora.strftime("%d/%m/%Y %H:%M")}

    SUMÁRIO EXECUTIVO (O QUE IMPORTA)
    Este documento consolida um diagnóstico tributário-operacional com base no cadastro de produtos e nas análises disponíveis no sistema.
    O foco é entregar previsibilidade: padronizar o cadastro, reduzir risco e eliminar retrabalho fiscal no dia a dia.

    A lógica é simples:
    • Cadastro padronizado = menos divergência e menos correção manual
    • Enquadramento consolidado por NCM = regra reaproveitável e escalável
    • Rastreabilidade = segurança para auditoria e tomada de decisão

    1) ESCOPO E METODOLOGIA (O QUE FOI ANALISADO)
    Foram avaliados:
    • Cadastro de produtos e seus NCMs
    • Consultas consolidadas em cache (resultado reaproveitável)
    • Padrões recorrentes (bases legais, segmentos/ST, CST e CFOP quando presentes no snapshot)
    • Indicadores de cobertura e rastreabilidade (para governança do cadastro)

    Este relatório não é “texto bonito”: ele é uma fotografia do cadastro com um plano de ação prático para estabilizar a operação.

    2) DIMENSÃO DO CADASTRO (TAMANHO REAL DO TRABALHO)
    • Produtos cadastrados: {qtd_produtos}
    • NCMs distintos identificados: {qtd_ncms_distintos}

    Interpretação:
    NCM distinto = variação de regra possível.
    Ao consolidar regra por NCM, o cadastro deixa de ser “manual e frágil” e passa a ser “padronizado e reaproveitável”.

    3) COBERTURA DO CADASTRO (MATURIDADE / PRONTIDÃO)
    Cobertura significa: “quantos produtos já têm enquadramento confiável para reaproveitamento operacional”.

    • Produtos cobertos (NCM com cache OK): {produtos_cobertos} ({cobertura_produtos_pct}%)
    • NCMs cobertos (cache OK): {ncms_cobertos} ({cobertura_ncms_pct}%)
    • Pendências no cadastro: {pendencias_cadastro}

    Interpretação gerencial:
    • Cobertura alta = previsibilidade tributária (menos surpresa, menos retrabalho).
    • Pendências são o melhor alvo para ganho rápido: cada pendência resolvida diminui risco e padroniza o cadastro.

    4) QUALIDADE DAS ANÁLISES (ROBUSTEZ DO PROCESSO)
    O sistema mantém análises consolidadas em cache para garantir consistência e evitar reprocessamento desnecessário.

    • Consultas em cache: {qtd_total_cache}
    - OK: {qtd_ok}
    - ERRO: {qtd_erro}
    - Sucesso: {taxa_sucesso_cache_pct}%
    • Atualizações nos últimos 30 dias: {qtd_atualizados_30d}

    Interpretação:
    • Taxa de sucesso alta é indicativo de estabilidade.
    • Atualizações representam melhoria contínua do cadastro: o sistema “aprende” e consolida padrões de forma progressiva.

    5) PRINCIPAIS ACHADOS (PADRÕES DA OPERAÇÃO)
    O que aparece com mais frequência revela o padrão do seu mix de produtos e do tratamento tributário dominante.

    5.1 Bases legais recorrentes (ICMS)
    Quando uma base legal se repete, geralmente indica padronização de critério.
    Isso é positivo: reduz divergência em compras/escrituração e simplifica governança.

    5.2 Segmentos e ST
    Segmentos de ST recorrentes apontam impacto direto em compra e precificação.
    Acertar ST no cadastro reduz risco de recolhimento incorreto e evita correções posteriores.

    5.3 NCMs mais presentes (prioridade 80/20)
    Os NCMs mais frequentes devem ser o primeiro foco de validação: padronizando o top 10, normalmente você estabiliza a maior parte do cadastro.

    6) BENEFÍCIOS PRÁTICOS (POR QUE ISSO SE PAGA)
    Após padronização, os ganhos mais comuns são:
    • Menos tempo com conferência manual e correções recorrentes
    • Redução de divergência entre entrada (compra) e saída (venda/emissão)
    • Base confiável para precificação e margem (principalmente quando há ST)
    • Cadastro reaproveitável: novos produtos herdam regra do NCM validado
    • Auditoria e rastreabilidade: histórico e justificativa para decisões

    7) PLANO DE AÇÃO (PASSO A PASSO OBJETIVO)
    Objetivo: transformar o cadastro em um padrão operacional validado e escalável.

    PASSO 1 — Fechar pendências do cadastro (ganho rápido)
    • Priorizar pendências e NCMs mais recorrentes
    • Meta recomendada: ≥ 95% de cobertura por produto

    PASSO 2 — Validação fiscal (segurança)
    • Validar contexto: UF, regime, cadeia operacional e CFOPs típicos
    • Confirmar se os tratamentos dominantes fazem sentido para a realidade da empresa

    PASSO 3 — Padronização e governança (escala)
    • Consolidar um “cadastro tributário padrão”
    • Definir regra de manutenção: novo produto herda regra do NCM já validado

    PASSO 4 — Rotina de melhoria contínua (sustentação)
    • Revisão periódica para incorporar mudanças operacionais e ajustes legais
    • Monitoramento de inconsistências para manter alta taxa de sucesso do cache

    8) NOTA OPERACIONAL (PARA AUDITORIA INTERNA)
    Este relatório também registra indicadores de processamento para rastreabilidade:
    • Linhas processadas (AnaliseItem): {qtd_itens_operacionais}
    - Com cache: {qtd_itens_com_cache_operacionais}
    - Sem cache: {qtd_itens_sem_cache_operacionais}

    9) CONCLUSÃO (MENSAGEM FINAL PARA FECHAMENTO)
    O cadastro tributário é um multiplicador de eficiência: quando está validado e padronizado, ele reduz retrabalho,
    diminui risco e dá previsibilidade para a operação fiscal.

    O Morpho transforma o cadastro em um ativo: reaproveitável, auditável e escalável.
    Com a execução do plano de ação, a empresa passa a operar com mais segurança tributária e menos custo operacional.

    Assinatura técnica:
    Sistema Morpho • Módulo Análise Tributária
    """.strip()


    # ================================
    # CONTEXT FINAL
    # ================================
    context = {
        "conta": conta,
        "papel_usuario": papel_usuario,
        "empresa": empresa,
        "emitido_em": agora,

        # Texto
        "texto_principal": texto_principal,

        # KPIs (CLIENTE) — mantemos as mesmas chaves do template
        "qtd_itens": qtd_produtos,                       # "Itens processados" = produtos
        "qtd_ncms": qtd_ncms_distintos,
        "qtd_produtos": qtd_produtos,
        "qtd_lotes": lotes_qs.count(),
        "qtd_ok": qtd_ok,
        "qtd_erro": qtd_erro,
        "qtd_sem_cache": pendencias_cadastro,            # "Pendências" = cadastro pendente
        "qtd_itens_com_cache": produtos_cobertos,        # "Itens com enquadramento" = produtos cobertos
        "qtd_atualizados_30d": qtd_atualizados_30d,

        # Percentuais
        "cobertura_pct": cobertura_produtos_pct,         # cobertura por produto
        "cobertura_ncms_pct": cobertura_ncms_pct,
        "taxa_sucesso_cache_pct": taxa_sucesso_cache_pct,
        "taxa_erro_cache_pct": taxa_erro_cache_pct,

        # Intervalos
        "range_itens": range_itens,                      # ainda útil para auditoria
        "range_caches": range_caches,
        "dt_ini_30d": dt_ini_30d,

        # Uploads / arquivos
        "ultimo_lote": ultimo_lote,
        "lotes_por_status": lotes_por_status,
        "lotes_por_tipo": lotes_por_tipo,
        "resumo_arquivos": resumo_arquivos_fmt,

        # Rankings
        "top_ncms_por_produtos": top_ncms_por_produtos,
        "top_ncms": top_ncms,
        "origem_produtos": origem_produtos,

        # Achados (snapshot)
        "top_bases": top_bases,
        "top_segmentos": top_segmentos,
        "top_cfops": top_cfops,
        "top_csts": top_csts,
        "top_erros": top_erros,

        # Extras (debug / auditoria interna)
        "cache_ncm_field": cache_ncm_field,
        "qtd_itens_operacionais": qtd_itens_operacionais,
        "qtd_itens_com_cache_operacionais": qtd_itens_com_cache_operacionais,
        "qtd_sem_cache_itens_operacionais": qtd_itens_sem_cache_operacionais,

        "tem_dados": (qtd_produtos > 0 or lotes_qs.exists()),
    }
    
    if request.GET.get("export") == "word":
        doc = gerar_relatorio_word(context)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="Relatorio_Diagnostico_Tributario_{empresa.cnpj}.docx"'
            )

        doc.save(response)
        return response

    return render(request, "core/relatorios.html", context)
