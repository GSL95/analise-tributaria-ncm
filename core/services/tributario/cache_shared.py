from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

CACHE_TTL_DIAS = 60


def cache_ainda_valido(status: str, resultado: dict, consultado_em, ttl_dias: int = CACHE_TTL_DIAS) -> bool:
    """True se um cache (por-empresa ou compartilhado) ainda pode ser reaproveitado sem
    reconsultar o legisweb: precisa ter dado certo, ter resultado, e não ter passado do TTL."""
    from core.models import AnaliseNcmCache

    if status != AnaliseNcmCache.Status.OK or not resultado:
        return False
    if consultado_em is None:
        return False
    return timezone.now() - consultado_em < timedelta(days=ttl_dias)


def buscar_cache_compartilhado(
    *,
    ncm: str,
    uf_origem: str,
    uf_destino: str,
    regime_tributario: str,
    atividade_origem: int,
    atividade_destino: int,
):
    """Busca um resultado já consultado por QUALQUER empresa para o mesmo contexto fiscal."""
    from core.models import AnaliseNcmCacheCompartilhado

    return AnaliseNcmCacheCompartilhado.objects.filter(
        ncm=ncm,
        uf_origem=uf_origem,
        uf_destino=uf_destino,
        regime_tributario=regime_tributario,
        atividade_origem=atividade_origem,
        atividade_destino=atividade_destino,
    ).first()


def salvar_cache_compartilhado(
    *,
    ncm: str,
    uf_origem: str,
    uf_destino: str,
    regime_tributario: str,
    atividade_origem: int,
    atividade_destino: int,
    resultado: dict,
    consultado_em,
):
    """Grava/atualiza o resultado compartilhado para que outras empresas com o mesmo
    contexto fiscal reaproveitem sem bater na API. Só chamado após consulta bem-sucedida —
    erros não são compartilhados, cada empresa tenta de novo em caso de falha anterior."""
    from core.models import AnaliseNcmCache, AnaliseNcmCacheCompartilhado

    AnaliseNcmCacheCompartilhado.objects.update_or_create(
        ncm=ncm,
        uf_origem=uf_origem,
        uf_destino=uf_destino,
        regime_tributario=regime_tributario,
        atividade_origem=atividade_origem,
        atividade_destino=atividade_destino,
        defaults={
            "status": AnaliseNcmCache.Status.OK,
            "erro_msg": "",
            "resultado": resultado,
            "consultado_em": consultado_em,
        },
    )
