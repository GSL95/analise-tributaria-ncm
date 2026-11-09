# core/services/pos_analise.py
from django.db import transaction
from core.models import NotaFiscal
from core.services.divergencias import gerar_divergencias_nota

import re
import unicodedata
from django.db import transaction

def norm_txt(s: str) -> str:
    s = (s or "").upper().strip()
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokens(s: str) -> set[str]:
    s = norm_txt(s)
    parts = [p for p in s.split(" ") if len(p) >= 3]
    return set(parts)

def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0

@transaction.atomic
def vincular_analise_itens_por_lote(lote_id: int, empresa_id: int, threshold: float = 0.55) -> dict:
    """
    Vincula ItemNotaFiscal.analise_item com AnaliseItem do MESMO lote/empresa.
    Estratégia:
      - Prioridade 1: mesmo NCM + maior similaridade de produto
      - Fallback: só NCM (se existir apenas 1 AnaliseItem do NCM)
    """
    from core.models import ItemNotaFiscal, AnaliseItem

    itens = list(
        ItemNotaFiscal.objects
        .filter(upload_lote_id=lote_id, empresa_id=empresa_id)
        .select_related("analise_item")
        .only("id", "produto", "ncm", "analise_item_id")
    )

    analises = list(
        AnaliseItem.objects
        .filter(upload_lote_id=lote_id, empresa_id=empresa_id)
        .only("id", "produto", "ncm")
    )

    analise_por_ncm = {}
    for a in analises:
        ncm = (a.ncm or "").strip()
        analise_por_ncm.setdefault(ncm, []).append(a)

    analise_tokens = {a.id: tokens(a.produto) for a in analises}

    updates = []
    stats = {"itens_total": len(itens), "vinculados": 0, "sem_match": 0, "ja_vinculados": 0}

    for it in itens:
        if it.analise_item_id:
            stats["ja_vinculados"] += 1
            continue

        ncm = (it.ncm or "").strip()
        candidatos = analise_por_ncm.get(ncm, [])

        if not candidatos:
            stats["sem_match"] += 1
            continue

        if len(candidatos) == 1:
            it.analise_item_id = candidatos[0].id
            updates.append(it)
            stats["vinculados"] += 1
            continue

        it_toks = tokens(it.produto)
        best = None
        best_score = 0.0

        for cand in candidatos:
            score = jaccard(it_toks, analise_tokens.get(cand.id, set()))
            if score > best_score:
                best_score = score
                best = cand

        if best and best_score >= threshold:
            it.analise_item_id = best.id
            updates.append(it)
            stats["vinculados"] += 1
        else:
            stats["sem_match"] += 1

    if updates:
        ItemNotaFiscal.objects.bulk_update(updates, ["analise_item"])

    stats["threshold"] = threshold
    return stats

@transaction.atomic
def pos_processar_divergencias(empresa_id: int, lote_id: int) -> dict:
    """
    Após atualizar/criar AnaliseItem de um lote:
      1) Vincula ItemNotaFiscal -> AnaliseItem
      2) Recalcula divergências das notas do lote
    """
    if not lote_id:
        return {"ok": False, "motivo": "sem_lote"}

    stats_v = vincular_analise_itens_por_lote(lote_id=lote_id, empresa_id=empresa_id, threshold=0.55)

    notas = list(
        NotaFiscal.objects
        .filter(empresa_id=empresa_id, upload_lote_id=lote_id)
        .only("id")
    )

    total_div = 0
    for n in notas:
        s = gerar_divergencias_nota(n.id)
        total_div += s.get("divergencias", 0)

    return {
        "ok": True,
        "lote_id": lote_id,
        "vinculo": stats_v,
        "notas": len(notas),
        "divergencias_total": total_div,
    }
    
    