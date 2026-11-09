from __future__ import annotations

from datetime import datetime
from io import BytesIO

from django.http import Http404
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from core.models import AnaliseItem, Empresa, PlanilhaLinhaOriginal, UploadLote

ANALISE_COLS = [
    ("ncm", "ncm"),
    ("nome_item", "nome_item"),
    ("desc tipi", "desc_tipi"),
    ("descricao st", "descricao_st"),
    ("aliquota icms retornado", "aliquota_icms_retornado"),
    ("descricao icms retornado", "descricao_icms_retornado"),
    ("base legal icms retornado", "base_legal_icms_retornado"),
    ("vigencia inicial icms", "vigencia_inicial_icms"),
    ("observacao icms", "observacao_icms"),
    ("CST ICMS", "cst_icms"),
    ("cest", "cest"),
    ("descricao ncm st", "descricao_ncm_st"),
    ("base legal st", "base_legal_st"),
    ("vigencia inicial st", "vigencia_inicial_st"),
    ("observacao st", "observacao_st"),
    ("segmentos st", "segmentos_st"),
    ("mva", "mva"),
    ("mva_ajustada_4", "mva_ajustada_4"),
    ("mva_ajustada_7", "mva_ajustada_7"),
    ("mva_ajustada_12", "mva_ajustada_12"),
    ("CST PIS COFINS", "cst_pis"),
    ("aliquota pis", "aliquota_pis"),
    ("cst_cofins", "cst_cofins"),
    ("aliquota cofins", "aliquota_cofins"),
    ("base legal pis cofins", "base_legal_pis_cofins"),
    ("cest st interestadual", "cest_st_interestadual"),
    ("descricao st interestadual", "descricao_st_interestadual"),
    ("segmento st interestadual", "segmento_st_interestadual"),
    ("mva original st interestadual", "mva_original_st_interestadual"),
    ("mva ajustada 4 st interestadual", "mva_ajustada_4_st_interestadual"),
    ("mva ajustada 12 st interestadual", "mva_ajustada_12_st_interestadual"),
    ("vigencia inicial st interestadual", "vigencia_inicial_st_interestadual"),
    ("base legal st interestadual", "base_legal_st_interestadual"),
    ("base legal interna st interestadual", "base_legal_interna_st_interestadual"),
    ("aplicabilidade st interestadual", "aplicabilidade_st_interestadual"),
    ("nao aplicabilidade st interestadual", "nao_aplicabilidade_st_interestadual"),
    ("reducao icms", "aliquota_reducao_interna"),
    # CBS — Contribuição sobre Bens e Serviços (LC 214/2025)
    ("CBS CST", "cst_cbs"),
    ("CBS aliquota", "aliquota_cbs"),
    ("CBS base legal", "base_legal_cbs"),
    # IBS Estadual — Imposto sobre Bens e Serviços (LC 214/2025)
    ("IBS Estadual aliquota", "aliquota_ibs_estadual"),
    ("IBS Estadual base legal", "base_legal_ibs_estadual"),
    # Benefícios Reforma Tributária
    ("Reforma Trib tipo beneficio", "reforma_tipo_beneficio"),
    ("Reforma Trib reducoes", "reforma_reducoes"),
    ("Reforma Trib creditos", "reforma_creditos"),
    ("Reforma Trib aplicabilidade", "reforma_aplicabilidade"),
    ("Reforma Trib base legal", "reforma_base_legal"),
]


def _fmt_xlsx(val) -> str:
    """Serializa listas/dicts para string legível no XLSX."""
    if val is None:
        return ""
    if isinstance(val, list):
        if not val:
            return ""
        partes = []
        for item in val:
            if isinstance(item, dict):
                tipo = item.get("tipo_reducao") or item.get("descricao") or ""
                perc = item.get("percentual") or item.get("valor") or ""
                desc = item.get("descricao", "")
                if tipo and perc:
                    partes.append(
                        f"{tipo}: {perc}" + (f" ({desc})" if desc and desc != tipo else "")
                    )
                elif desc:
                    partes.append(desc)
                else:
                    partes.append(str(item))
            else:
                partes.append(str(item))
        return " | ".join(partes)
    if isinstance(val, dict):
        return str(val)
    return val


def _get_resultado_item(item: AnaliseItem) -> dict:
    if item.resultado_snapshot:
        base = dict(item.resultado_snapshot)
    elif item.cache and item.cache.resultado:
        base = dict(item.cache.resultado)
    else:
        base = {}
    base.setdefault("ncm", item.ncm or "")
    base.setdefault("nome_item", item.produto or "")
    return base


def _ajustar_colunas(ws, header: list[str]) -> None:
    for idx, col_name in enumerate(header, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = min(
            max(len(str(col_name)) + 2, 14), 45
        )


def gerar_xlsx_analise(empresa: Empresa, lote_id: str | int | None) -> tuple[BytesIO, str]:
    """
    Gera o XLSX de análise tributária.
    Retorna (BytesIO com o conteúdo, nome do arquivo).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Export"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Caso 1: lote do tipo PLANILHA — preserva colunas originais
    if lote_id:
        lote = UploadLote.objects.filter(id=lote_id, empresa=empresa).first()
        if lote and lote.tipo == UploadLote.Tipo.PLANILHA:
            linhas = (
                PlanilhaLinhaOriginal.objects
                .filter(upload_lote=lote)
                .order_by("linha_idx")
            )
            if not linhas.exists():
                raise Http404(
                    "Não há linhas originais (PlanilhaLinhaOriginal) para este lote. Reprocesse o lote."
                )

            first = linhas.first()
            orig_cols = list((first.dados or {}).keys()) if first else []
            header = orig_cols + [f"AN_{c[0]}" for c in ANALISE_COLS]
            ws.append(header)
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(vertical="center")

            analises = (
                AnaliseItem.objects
                .filter(empresa=empresa, upload_lote=lote, planilha_linha__isnull=False)
                .select_related("cache", "planilha_linha")
            )
            mapa = {a.planilha_linha_id: a for a in analises}

            for pl in linhas:
                base = pl.dados or {}
                row = ["" if v is None else v for v in (base.get(k, "") for k in orig_cols)]
                item = mapa.get(pl.id)
                r = _get_resultado_item(item) if item else {}
                row += [_fmt_xlsx(r.get(key, "")) for _, key in ANALISE_COLS]
                ws.append(row)

            _ajustar_colunas(ws, header)
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            filename = f"analise_tributaria_original_{empresa.id}_lote_{lote_id}_{ts}.xlsx"
            return output, filename

    # Caso 2: fallback — apenas análise, sem planilha original
    qs = (
        AnaliseItem.objects.filter(empresa=empresa)
        .select_related("cache")
        .order_by("-criado_em")
    )
    if lote_id:
        qs = qs.filter(upload_lote_id=lote_id)

    header = [c[0] for c in ANALISE_COLS]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center")

    for item in qs:
        r = _get_resultado_item(item)
        ws.append([_fmt_xlsx(r.get(key, "")) for _, key in ANALISE_COLS])

    _ajustar_colunas(ws, header)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"analise_tributaria_{empresa.id}_{ts}.xlsx"
    return output, filename
