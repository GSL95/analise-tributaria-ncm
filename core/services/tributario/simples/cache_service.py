from __future__ import annotations

from django.utils import timezone

from core.models import AnaliseNcmCache, Empresa
from core.services.tributario.cache_locks import lock_para_chave
from core.services.tributario.cache_shared import (
    buscar_cache_compartilhado,
    cache_ainda_valido,
    salvar_cache_compartilhado,
)
from core.services.tributario.simples.engine import analisar_ncm_unico
from core.services.tributario.simples.json_utils import to_jsonable


def get_or_create_cache_simples(
    *,
    empresa: Empresa,
    ncm: str,
    nome_item: str,
    atividade_origem: int,
    atividade_destino: int,
    uf_origem: str | None = None,
    uf_destino: str = "GO",
    forcar_recalculo: bool = False,
) -> AnaliseNcmCache:
    uf_origem = (uf_origem or empresa.uf or "DF").strip().upper()

    filtros = dict(
        empresa=empresa,
        ncm=ncm,
        uf_origem=uf_origem,
        uf_destino=uf_destino,
        regime_tributario=empresa.regime_tributario,
        atividade_origem=atividade_origem,
        atividade_destino=atividade_destino,
    )

    chave_compartilhada = (ncm, uf_origem, uf_destino, empresa.regime_tributario, atividade_origem, atividade_destino)

    # Lock por chave de contexto fiscal (sem empresa): evita que empresas/produtos diferentes
    # com o mesmo NCM/contexto, processados em paralelo, disparem consultas duplicadas à API
    # externa. A 2ª+ thread que chegar aqui encontra o cache já resolvido pela 1ª.
    with lock_para_chave(chave_compartilhada):
        obj, created = AnaliseNcmCache.objects.get_or_create(
            **filtros,
            defaults={
                "status": AnaliseNcmCache.Status.ERRO,
                "resultado": {},
                "consultado_em": timezone.now(),
            },
        )

        # Cache por-empresa válido, não forçado e dentro do prazo de 60 dias — devolve sem recalcular
        if not created and not forcar_recalculo and cache_ainda_valido(obj.status, obj.resultado, obj.consultado_em):
            return obj

        # Antes de bater na API, tenta reaproveitar o resultado de OUTRA empresa com o
        # mesmo contexto fiscal (mesmo NCM/UF/regime/atividades) — a resposta do legisweb
        # não depende de qual empresa pergunta.
        if not forcar_recalculo:
            compartilhado = buscar_cache_compartilhado(
                ncm=ncm,
                uf_origem=uf_origem,
                uf_destino=uf_destino,
                regime_tributario=empresa.regime_tributario,
                atividade_origem=atividade_origem,
                atividade_destino=atividade_destino,
            )
            if compartilhado and cache_ainda_valido(compartilhado.status, compartilhado.resultado, compartilhado.consultado_em):
                obj.status = compartilhado.status
                obj.erro_msg = compartilhado.erro_msg
                obj.resultado = compartilhado.resultado
                obj.consultado_em = compartilhado.consultado_em
                obj.save(update_fields=["status", "erro_msg", "resultado", "consultado_em"])
                return obj

        try:
            if empresa.regime_tributario != Empresa.RegimeTributario.SN:
                raise ValueError("Empresa não é Simples Nacional para este motor.")

            resultado = analisar_ncm_unico(
                ncm=ncm,
                nome_item=nome_item,
                regime_tributario=1,
                atividade_origem=atividade_origem,
                atividade_destino=atividade_destino,
                estado=uf_origem,
                estado_destino_st_inter=uf_destino,
            )
            resultado = to_jsonable(resultado)
            agora = timezone.now()

            obj.status = AnaliseNcmCache.Status.OK
            obj.erro_msg = ""
            obj.resultado = resultado
            obj.consultado_em = agora
            obj.save(update_fields=["status", "erro_msg", "resultado", "consultado_em"])

            salvar_cache_compartilhado(
                ncm=ncm,
                uf_origem=uf_origem,
                uf_destino=uf_destino,
                regime_tributario=empresa.regime_tributario,
                atividade_origem=atividade_origem,
                atividade_destino=atividade_destino,
                resultado=resultado,
                consultado_em=agora,
            )
            return obj

        except Exception as e:
            obj.status = AnaliseNcmCache.Status.ERRO
            obj.erro_msg = str(e)
            obj.resultado = {}
            obj.consultado_em = timezone.now()
            obj.save(update_fields=["status", "erro_msg", "resultado", "consultado_em"])
            return obj
