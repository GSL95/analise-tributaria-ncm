import os
import sys
import warnings

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # runserver sobe dois processos (watcher + processo real do autoreload).
        # Só executa no processo real, para não rodar duas vezes seguidas.
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return
        self._resetar_processamentos_travados()

    def _resetar_processamentos_travados(self):
        """Marca como ERRO filas/lotes que ficaram 'processando' sem worker vivo.

        O processamento roda em threading.Thread dentro do próprio processo
        (core/services/fila_analise.py e fila_upload.py). Se o servidor for
        encerrado no meio de uma análise/upload, a thread morre mas o registro
        no banco continua com status PROCESSANDO/ANALISANDO, deixando a tela
        de status presa para sempre. Como nenhuma thread sobrevive a um
        restart, qualquer registro nesses status ao subir o app está órfão.
        """
        from django.db import connection
        from django.db.utils import OperationalError, ProgrammingError

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)

            try:
                tabelas = connection.introspection.table_names()
            except Exception:
                return

            if "core_filaanalise" not in tabelas or "core_uploadlote" not in tabelas:
                return

            try:
                from core.models import FilaAnalise, UploadLote

                FilaAnalise.objects.filter(
                    status__in=[FilaAnalise.Status.PENDENTE, FilaAnalise.Status.ANALISANDO]
                ).update(
                    status=FilaAnalise.Status.ERRO,
                    erro_msg="Processamento interrompido (servidor reiniciado). Dispare a análise novamente.",
                )
                UploadLote.objects.filter(
                    status__in=[UploadLote.Status.PENDENTE, UploadLote.Status.PROCESSANDO]
                ).update(
                    status=UploadLote.Status.ERRO,
                    observacao="Processamento interrompido (servidor reiniciado). Reenvie o arquivo.",
                )
            except (OperationalError, ProgrammingError):
                pass
