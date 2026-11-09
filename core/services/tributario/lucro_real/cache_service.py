from __future__ import annotations

from django.utils import timezone

from core.models import AnaliseNcmCache, Empresa
from core.services.tributario.cache_locks import lock_para_chave
from core.services.tributario.cache_shared import (
    buscar_cache_compartilhado,
    cache_ainda_valido,
    salvar_cache_compartilhado,
)
from core.services.tributario.lucro_real.json_safe import json_safe
from core.services.tributario.lucro_real.engine import analisar_ncm_unico_lucro_real


def get_or_create_cache_lucro_real(
    empresa,
    ncm: str,
    nome_item: str,
    atividade_origem,
    atividade_destino,
    uf_origem="DF",
    uf_destino="GO",
    forcar_recalculo=False,
    regime = None,
):
    chave_compartilhada = (ncm, uf_origem, uf_destino, empresa.regime_tributario, atividade_origem, atividade_destino)

    # Lock por chave de contexto fiscal (sem empresa): evita que empresas/produtos diferentes
    # com o mesmo NCM/contexto, processados em paralelo, disparem consultas duplicadas à API
    # externa. A 2ª+ thread que chegar aqui encontra o cache já resolvido pela 1ª.
    with lock_para_chave(chave_compartilhada):
        obj, created = AnaliseNcmCache.objects.get_or_create(
            empresa=empresa,
            ncm=ncm,
            uf_origem=uf_origem,
            uf_destino=uf_destino,
            regime_tributario=empresa.regime_tributario,
            atividade_origem=atividade_origem,
            atividade_destino=atividade_destino,
            defaults={
                "status": AnaliseNcmCache.Status.ERRO,
                "resultado": {},
                "consultado_em": timezone.now(),
            },
        )

        # Cache por-empresa válido, não forçado e dentro do prazo de 60 dias — devolve sem
        # recalcular. Muitos produtos diferentes costumam compartilhar o mesmo NCM, então isso
        # evita reconsultar a API para cada produto individualmente.
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
                obj.save(update_fields=["status", "erro_msg", "resultado", "consultado_em", "atualizado_em"])
                return obj

        try:
            resultado = analisar_ncm_unico_lucro_real(
                ncm=ncm,
                nome_item=nome_item,
                uf_origem=uf_origem,
                uf_destino=uf_destino,
                atividade_origem=atividade_origem,
                atividade_destino=atividade_destino,
                tipi_df=None,  # depois você pode carregar a TIPI uma vez e cachear em memória
                regime=regime,
            )
            resultado = json_safe(resultado)
            agora = timezone.now()

            obj.status = AnaliseNcmCache.Status.OK
            obj.erro_msg = ""
            obj.resultado = resultado
            obj.consultado_em = agora
            obj.save(update_fields=["status", "erro_msg", "resultado", "consultado_em", "atualizado_em"])

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
            obj.save(update_fields=["status", "erro_msg", "resultado", "consultado_em", "atualizado_em"])
            return obj
