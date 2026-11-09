from __future__ import annotations

import os
import pandas as pd
from functools import lru_cache
from django.conf import settings

TIPI_PATH = os.path.join(settings.BASE_DIR, "_RECURSOS_", "tipi.xlsx")

@lru_cache(maxsize=1)
def get_tipi_df() -> pd.DataFrame:
    df = pd.read_excel(TIPI_PATH, dtype=str)
    df.columns = [c.strip().upper() for c in df.columns]
    return df
