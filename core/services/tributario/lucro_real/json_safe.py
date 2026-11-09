from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

def json_safe(obj):
    """
    Converte recursivamente tipos não serializáveis em JSON (Decimal, datetime, etc.).
    Use antes de salvar em JSONField.
    """
    if isinstance(obj, Decimal):
        # escolha: float ou str. Para tributário, str costuma preservar melhor.
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj
