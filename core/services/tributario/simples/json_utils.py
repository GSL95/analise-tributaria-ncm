from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from typing import Any


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, Decimal):
        # opção A (mais prática para frontend): float
        return float(value)

        # opção B (mais fiel, evita arredondamento binário): str
        # return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]

    return value
