from __future__ import annotations

import threading

_registry_lock = threading.Lock()
_locks: dict[tuple, threading.Lock] = {}


def lock_para_chave(chave: tuple) -> threading.Lock:
    """Retorna (criando se necessário) um lock exclusivo para a chave dada.

    Usado por get_or_create_cache_simples/lucro_real para impedir que
    produtos diferentes com o mesmo NCM/contexto, processados em paralelo,
    disparem consultas duplicadas e concorrentes à API externa antes que a
    primeira termine e grave o cache.
    """
    with _registry_lock:
        lock = _locks.get(chave)
        if lock is None:
            lock = threading.Lock()
            _locks[chave] = lock
        return lock
