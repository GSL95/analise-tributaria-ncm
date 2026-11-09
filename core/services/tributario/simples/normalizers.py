from __future__ import annotations

import re
import string
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

def sanitize(text: str) -> str:
    text = (text or "").lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return text.strip()

def parse_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None

def parse_date_br(v: Any):
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return datetime.strptime(v, "%d/%m/%Y").date()
    except ValueError:
        return None

def formatar_ncm(ncm: str) -> str | None:
    ncm = re.sub(r"\D", "", ncm or "")
    if len(ncm) == 8:
        return f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}"
    return None
