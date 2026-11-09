import concurrent.futures
import logging
import threading

from django.db import connection
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

# Nº de produtos analisados em paralelo. Cada produto com NCM novo dispara
# até 7 chamadas simultâneas ao legisweb (ver simples/engine.py e
# consulta_lucro_real.py), então CONCORRENCIA_PRODUTOS=N gera até N×7
# conexões simultâneas à API externa. Mantido baixo pois o legisweb já
# respondeu com timeouts/400 quando isso passou de ~30 conexões concorrentes.
CONCORRENCIA_PRODUTOS = 2


def _processar_um_produto(fila_id, empresa, atividade_origem, atividade_destino, p) -> None:
    """Processa um produto e contabiliza o progresso da fila. Roda em thread própria."""
    from core.models import FilaAnalise, AnaliseItem, Empresa
    from core.services.tributario.simples.cache_service import get_or_create_cache_simples
    from core.services.tributario.lucro_real.cache_service import get_or_create_cache_lucro_real

    try:
        # Se a fila foi cancelada, produtos ainda não iniciados simplesmente
        # não são processados nem contados (mesmo comportamento do loop serial).
        if FilaAnalise.objects.filter(pk=fila_id, status=FilaAnalise.Status.CANCELADO).exists():
            return

        FilaAnalise.objects.filter(pk=fila_id).update(
            produto_atual=f"{p.produto} (NCM {p.ncm})",
            atualizado_em=timezone.now(),
        )

        try:
            cache = None
            if empresa.regime_tributario == Empresa.RegimeTributario.SN:
                cache = get_or_create_cache_simples(
                    empresa=empresa,
                    ncm=p.ncm,
                    nome_item=p.produto,
                    atividade_origem=atividade_origem,
                    atividade_destino=atividade_destino,
                    forcar_recalculo=False,
                )
            elif empresa.regime_tributario in (
                Empresa.RegimeTributario.REAL,
                Empresa.RegimeTributario.PRESUMIDO,
            ):
                cache = get_or_create_cache_lucro_real(
                    empresa=empresa,
                    ncm=p.ncm,
                    nome_item=p.produto,
                    atividade_origem=atividade_origem,
                    atividade_destino=atividade_destino,
                    regime=empresa.regime_tributario,
                )

            if cache is not None:
                obj, created = AnaliseItem.objects.get_or_create(
                    empresa=empresa,
                    upload_lote=p.upload_lote,
                    produto_ncm=p,
                    defaults={
                        "produto": p.produto,
                        "ncm": p.ncm,
                        "cache": cache,
                        "resultado_snapshot": cache.resultado if cache.status == "OK" else {},
                    },
                )
                if not created:
                    obj.cache = cache
                    obj.resultado_snapshot = cache.resultado if cache.status == "OK" else {}
                    obj.save(update_fields=["cache", "resultado_snapshot"])

        except Exception:
            logger.exception("Erro ao processar produto #%s (NCM %s)", p.id, p.ncm)

        FilaAnalise.objects.filter(pk=fila_id).update(
            processados=F("processados") + 1,
            atualizado_em=timezone.now(),
        )
    finally:
        connection.close()


def _worker(fila_id: int, apenas_pendentes: bool = False) -> None:
    """Executa a análise tributária em thread separada.

    apenas_pendentes=True pula produtos que já possuem AnaliseItem gerado
    (usado para "continuar de onde parou" após uma fila anterior ter sido
    interrompida por erro/queda do servidor).
    """
    # Importações locais para evitar imports circulares
    from core.models import FilaAnalise, ProdutoNcm, AnaliseItem
    from core.services.pos_analise import pos_processar_divergencias

    try:
        fila = FilaAnalise.objects.select_related("empresa").get(pk=fila_id)
    except FilaAnalise.DoesNotExist:
        logger.error("FilaAnalise #%s não encontrada.", fila_id)
        return

    empresa = fila.empresa
    lote_id = fila.upload_lote_id

    try:
        produtos_qs = ProdutoNcm.objects.filter(empresa=empresa)
        if lote_id:
            produtos_qs = produtos_qs.filter(upload_lote_id=lote_id)

        produtos_validos = [p for p in produtos_qs.order_by("-criado_em") if p.ncm and len(p.ncm) == 8]

        if apenas_pendentes and produtos_validos:
            ja_processados_ids = set(
                AnaliseItem.objects.filter(
                    empresa=empresa,
                    produto_ncm_id__in=[p.id for p in produtos_validos],
                ).values_list("produto_ncm_id", flat=True)
            )
            produtos_validos = [p for p in produtos_validos if p.id not in ja_processados_ids]

        total = len(produtos_validos)

        FilaAnalise.objects.filter(pk=fila_id).update(
            status=FilaAnalise.Status.ANALISANDO,
            total=total,
            atualizado_em=timezone.now(),
        )

        if total == 0:
            FilaAnalise.objects.filter(pk=fila_id).update(
                status=FilaAnalise.Status.CONCLUIDO,
                atualizado_em=timezone.now(),
            )
            return

        atividade_origem = empresa.atividade_origem
        atividade_destino = empresa.atividade_destino

        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCORRENCIA_PRODUTOS) as executor:
            futures = [
                executor.submit(
                    _processar_um_produto, fila_id, empresa, atividade_origem, atividade_destino, p
                )
                for p in produtos_validos
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        if FilaAnalise.objects.filter(pk=fila_id, status=FilaAnalise.Status.CANCELADO).exists():
            return

        if lote_id:
            try:
                pos_processar_divergencias(empresa_id=empresa.id, lote_id=lote_id)
            except Exception:
                logger.exception("Erro ao pós-processar divergências para lote #%s", lote_id)

        FilaAnalise.objects.filter(pk=fila_id).update(
            status=FilaAnalise.Status.CONCLUIDO,
            produto_atual="",
            atualizado_em=timezone.now(),
        )

    except Exception as exc:
        logger.exception("Erro fatal na FilaAnalise #%s", fila_id)
        FilaAnalise.objects.filter(pk=fila_id).update(
            status=FilaAnalise.Status.ERRO,
            erro_msg=str(exc),
            atualizado_em=timezone.now(),
        )
    finally:
        connection.close()


def iniciar_analise_em_background(fila_id: int, apenas_pendentes: bool = False) -> None:
    t = threading.Thread(target=_worker, args=(fila_id, apenas_pendentes), daemon=True)
    t.start()
