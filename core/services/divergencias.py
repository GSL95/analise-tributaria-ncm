# core/services/divergencias.py
import re
from decimal import Decimal
from django.db import transaction
from core.models import DivergenciaItem, ItemNotaFiscal

ZERO = Decimal("0.00")

def extract_cst_codes(value: str) -> set[str]:
    if not value:
        return set()
    s = str(value).strip()
    codes = re.findall(r"\b\d{2,3}\b", s)
    return set(codes)

def snap(analise_item, key, default=""):
    d = analise_item.resultado_snapshot or {}
    return d.get(key, default)

def is_st_expected(analise_item) -> bool:
    desc = str(snap(analise_item, "descricao_st", "")).strip().upper()
    if not desc:
        return False
    if "NÃO TEM" in desc or "NAO TEM" in desc:
        return False
    return True

@transaction.atomic
def gerar_divergencias_para_itens(itens_qs) -> int:
    DivergenciaItem.objects.filter(item__in=itens_qs).delete()
    divergencias = []

    for it in itens_qs.select_related("analise_item"):
        ai = it.analise_item
        if not ai:
            divergencias.append(DivergenciaItem(
                item=it,
                tipo="SEM_ANALISE_ITEM",
                esperado="AnaliseItem vinculado",
                encontrado="(vazio)",
                severidade="alta",
                detalhe="Item da nota não está vinculado a um AnaliseItem; não é possível comparar."
            ))
            continue

        icms_real = (it.icms_cst or it.icms_csosn or "").strip()
        icms_real_codes = extract_cst_codes(icms_real)
        icms_esp_codes = extract_cst_codes(snap(ai, "cst_icms", ""))

        if icms_esp_codes and icms_real_codes and icms_real_codes.isdisjoint(icms_esp_codes):
            divergencias.append(DivergenciaItem(
                item=it,
                tipo="ICMS_CST",
                esperado=", ".join(sorted(icms_esp_codes)),
                encontrado=", ".join(sorted(icms_real_codes)),
                severidade="alta",
                detalhe="CST/CSOSN do item não está entre os CSTs aceitos pela análise tributária."
            ))

        pis_real_codes = extract_cst_codes(it.pis_cst or "")
        pis_esp_codes = extract_cst_codes(snap(ai, "cst_pis", ""))
        if pis_esp_codes and pis_real_codes and pis_real_codes.isdisjoint(pis_esp_codes):
            divergencias.append(DivergenciaItem(
                item=it,
                tipo="PIS_CST",
                esperado=", ".join(sorted(pis_esp_codes)),
                encontrado=", ".join(sorted(pis_real_codes)),
                severidade="media",
                detalhe="CST de PIS divergente do esperado."
            ))

        cof_real_codes = extract_cst_codes(it.cofins_cst or "")
        cof_esp_codes = extract_cst_codes(snap(ai, "cst_cofins", ""))
        if cof_esp_codes and cof_real_codes and cof_real_codes.isdisjoint(cof_esp_codes):
            divergencias.append(DivergenciaItem(
                item=it,
                tipo="COFINS_CST",
                esperado=", ".join(sorted(cof_esp_codes)),
                encontrado=", ".join(sorted(cof_real_codes)),
                severidade="media",
                detalhe="CST de COFINS divergente do esperado."
            ))

        pis_txt = str(snap(ai, "cst_pis", "")).upper()
        cof_txt = str(snap(ai, "cst_cofins", "")).upper()

        pis_val = it.pis_valor
        cof_val = it.cofins_valor

        if "ALIQUOTA ZERO" in pis_txt and pis_val is not None:
            if Decimal(str(pis_val)) > ZERO:
                divergencias.append(DivergenciaItem(
                    item=it,
                    tipo="PIS_VALOR",
                    esperado="0,00 (alíquota zero)",
                    encontrado=str(pis_val),
                    severidade="alta",
                    detalhe="Análise indica alíquota zero/monofásico, mas PIS veio com valor > 0."
                ))

        if "ALIQUOTA ZERO" in cof_txt and cof_val is not None:
            if Decimal(str(cof_val)) > ZERO:
                divergencias.append(DivergenciaItem(
                    item=it,
                    tipo="COFINS_VALOR",
                    esperado="0,00 (alíquota zero)",
                    encontrado=str(cof_val),
                    severidade="alta",
                    detalhe="Análise indica alíquota zero/monofásico, mas COFINS veio com valor > 0."
                ))

        st_esperado = is_st_expected(ai)
        st_encontrado = bool(set(extract_cst_codes(icms_real)) & {"10","30","60","70","201","202","203","500"})
        if st_esperado != st_encontrado:
            divergencias.append(DivergenciaItem(
                item=it,
                tipo="ICMS_ST",
                esperado="ST" if st_esperado else "Sem ST",
                encontrado="ST" if st_encontrado else "Sem ST",
                severidade="media",
                detalhe="A expectativa de ST (pela análise) não bate com indícios do XML."
            ))

    if divergencias:
        DivergenciaItem.objects.bulk_create(divergencias, batch_size=1000)

    return len(divergencias)

@transaction.atomic
def gerar_divergencias_nota(nota_id: int) -> dict:
    """
    Recalcula divergências de uma nota inteira.
    """
    itens_qs = ItemNotaFiscal.objects.filter(nota_id=nota_id)
    total = gerar_divergencias_para_itens(itens_qs)
    return {"nota_id": nota_id, "divergencias": total}