import logging
import threading

from django.db import connection

logger = logging.getLogger(__name__)


def _worker(lote_id: int) -> None:
    from core.services.upload_processor import processar_lote_upload
    try:
        processar_lote_upload(lote_id)
    except Exception:
        logger.exception("Erro fatal no processamento do lote #%s", lote_id)
    finally:
        connection.close()


def processar_lote_em_background(lote_id: int) -> None:
    t = threading.Thread(target=_worker, args=(lote_id,), daemon=True)
    t.start()
