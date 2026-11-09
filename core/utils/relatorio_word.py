# core/utils/relatorio_word.py
# Gera .docx com layout “parecido” com o template HTML:
# - Cabeçalho em 2 colunas (esquerda/direita)
# - Seções numeradas
# - Callout “Objetivo”
# - KPIs em cartões (tabela 1x4)
# - Badges em linha
# - Tabelas de “Cobertura detalhada”, “Rastreabilidade”, “Achados”
# Sem depender de nova view/URL (usa ?export=word na mesma view)

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml.shared import OxmlElement, qn


# -----------------------------
# Helpers de estilo
# -----------------------------
def _set_cell_shading(cell, fill_hex: str):
    """fill_hex: 'F2F2F2' etc."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)
    tcPr.append(shd)


def _set_cell_borders(cell, **kwargs):
    """
    kwargs: top/bottom/left/right with dict {'sz': 8, 'val': 'single', 'color': 'D9D9D9'}
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = tcPr.first_child_found_in("w:tcBorders")
    if tcBorders is None:
        tcBorders = OxmlElement('w:tcBorders')
        tcPr.append(tcBorders)

    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        if edge in kwargs:
            edge_data = kwargs[edge]
            tag = OxmlElement(f'w:{edge}')
            tag.set(qn('w:val'), str(edge_data.get('val', 'single')))
            tag.set(qn('w:sz'), str(edge_data.get('sz', 6)))
            tag.set(qn('w:space'), str(edge_data.get('space', 0)))
            tag.set(qn('w:color'), str(edge_data.get('color', 'D9D9D9')))
            tcBorders.append(tag)


def _set_paragraph_run(p, text, *, bold=False, size=11, color=None):
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    return r


def _add_space(doc, pts=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(pts)
    return p


def _add_section_title(doc, title):
    p = doc.add_paragraph()
    _set_paragraph_run(p, title, bold=True, size=12)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(6)
    return p


def _add_label_value(doc, label, value):
    p = doc.add_paragraph()
    _set_paragraph_run(p, f"{label}: ", bold=True, size=10)
    _set_paragraph_run(p, str(value), bold=False, size=10)
    p.paragraph_format.space_after = Pt(2)
    return p


def _table_full_width(table):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True


def _style_table_basic(table):
    # borda cinza clara
    border = {'sz': 6, 'val': 'single', 'color': 'D9D9D9'}
    for row in table.rows:
        for cell in row.cells:
            _set_cell_borders(cell, top=border, bottom=border, left=border, right=border)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


# -----------------------------
# Componentes “parecidos” com o HTML
# -----------------------------
def _header_block(doc, emitido_em_str):
    # Cabeçalho em 2 colunas
    t = doc.add_table(rows=1, cols=2)
    _table_full_width(t)
    _style_table_basic(t)

    left = t.cell(0, 0)
    right = t.cell(0, 1)

    _set_cell_shading(left, "FFFFFF")
    _set_cell_shading(right, "FFFFFF")

    # esquerda
    p = left.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    _set_paragraph_run(p, "RELATÓRIO TÉCNICO", bold=False, size=9)
    p2 = left.add_paragraph()
    p2.paragraph_format.space_after = Pt(2)
    _set_paragraph_run(p2, "Relatório de Diagnóstico Tributário", bold=True, size=16)
    p3 = left.add_paragraph()
    _set_paragraph_run(p3, f"Emitido em {emitido_em_str}", bold=False, size=9)

    # direita
    pr = right.paragraphs[0]
    pr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_paragraph_run(pr, "Sistema", bold=False, size=9)
    pr2 = right.add_paragraph()
    pr2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_paragraph_run(pr2, "Morpho • Análise Tributária", bold=True, size=11)

    _add_space(doc, 8)


def _callout_objetivo(doc, texto):
    t = doc.add_table(rows=1, cols=1)
    _table_full_width(t)
    _style_table_basic(t)

    c = t.cell(0, 0)
    _set_cell_shading(c, "F3F7FF")  # azul bem leve
    p = c.paragraphs[0]
    _set_paragraph_run(p, "Objetivo", bold=True, size=11)
    p2 = c.add_paragraph(texto)
    p2.paragraph_format.space_before = Pt(2)
    p2.paragraph_format.space_after = Pt(4)
    _add_space(doc, 6)


def _kpis_grid(doc, items):
    """
    items: list of dict {k, v, h}
    Gera 1 linha com 4 colunas (ou quebra em múltiplas linhas se >4)
    """
    cols = 4
    rows = (len(items) + cols - 1) // cols
    t = doc.add_table(rows=rows, cols=cols)
    _table_full_width(t)
    _style_table_basic(t)

    idx = 0
    for r in range(rows):
        for c in range(cols):
            cell = t.cell(r, c)
            _set_cell_shading(cell, "FAFAFA")
            cell.paragraphs[0].clear() if hasattr(cell.paragraphs[0], "clear") else None
            if idx < len(items):
                kpi = items[idx]
                p1 = cell.paragraphs[0]
                _set_paragraph_run(p1, kpi["k"], bold=False, size=9)
                p2 = cell.add_paragraph()
                _set_paragraph_run(p2, str(kpi["v"]), bold=True, size=16)
                p3 = cell.add_paragraph()
                _set_paragraph_run(p3, kpi.get("h", ""), bold=False, size=9)
            idx += 1

    _add_space(doc, 6)


def _badges_line(doc, badges):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    for i, b in enumerate(badges):
        r = p.add_run(b)
        r.font.size = Pt(9)
        r.bold = True
        # “badge” visual simples: [ ... ]
        r.text = f"[ {b} ]"
        if i != len(badges) - 1:
            p.add_run("  ")
    _add_space(doc, 6)


def _two_tables_row(doc, left_title, left_rows, right_title, right_rows):
    """
    Cria 2 caixas lado a lado, cada uma com título e tabela 2 colunas.
    """
    t = doc.add_table(rows=1, cols=2)
    _table_full_width(t)
    # sem borda externa pesada, mas mantém cinza
    _style_table_basic(t)

    for i, (title, rows) in enumerate(((left_title, left_rows), (right_title, right_rows))):
        cell = t.cell(0, i)
        _set_cell_shading(cell, "FFFFFF")
        # título
        p = cell.paragraphs[0]
        _set_paragraph_run(p, title, bold=True, size=10)
        # tabela interna
        inner = cell.add_table(rows=1, cols=2)
        inner.alignment = WD_TABLE_ALIGNMENT.CENTER
        _style_table_basic(inner)
        _set_cell_shading(inner.cell(0, 0), "F2F2F2")
        _set_cell_shading(inner.cell(0, 1), "F2F2F2")
        inner.cell(0, 0).paragraphs[0].add_run("Indicador").bold = True
        inner.cell(0, 1).paragraphs[0].add_run("Valor").bold = True

        for k, v in rows:
            rr = inner.add_row().cells
            rr[0].text = str(k)
            rr[1].text = str(v)

    _add_space(doc, 6)


def _table_rank(doc, title, headers, rows):
    _add_section_title(doc, title)
    if not rows:
        doc.add_paragraph("Sem informações disponíveis.")
        return

    t = doc.add_table(rows=1, cols=len(headers))
    _table_full_width(t)
    _style_table_basic(t)

    for i, h in enumerate(headers):
        cell = t.cell(0, i)
        _set_cell_shading(cell, "F2F2F2")
        cell.paragraphs[0].add_run(h).bold = True

    for r in rows:
        rr = t.add_row().cells
        for i, val in enumerate(r):
            rr[i].text = str(val)

    _add_space(doc, 6)


def _footer(doc):
    _add_space(doc, 8)
    p = doc.add_paragraph("Documento gerado pelo sistema Morpho • Análise Tributária")
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT


# -----------------------------
# Função principal
# -----------------------------
def gerar_relatorio_word(context):
    doc = Document()

    # Margens parecidas com “paper”
    section = doc.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    # Fonte padrão
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    empresa = context["empresa"]
    emitido_em = context["emitido_em"]

    # Header
    _header_block(doc, emitido_em.strftime("%d/%m/%Y %H:%M"))

    # 1. Identificação e contexto
    _add_section_title(doc, "1. Identificação e contexto")
    _add_label_value(doc, "Empresa", empresa.razao_social)
    _add_label_value(doc, "CNPJ", empresa.cnpj)
    if getattr(empresa, "uf", None):
        _add_label_value(doc, "UF (referência)", empresa.uf)
    _add_label_value(doc, "Regime", empresa.get_regime_tributario_display() if hasattr(empresa, "get_regime_tributario_display") else "—")
    _add_label_value(
        doc,
        "Atividade",
        f"{empresa.get_atividade_origem_display() if hasattr(empresa, 'get_atividade_origem_display') else '—'} → "
        f"{empresa.get_atividade_destino_display() if hasattr(empresa, 'get_atividade_destino_display') else '—'}",
    )
    _add_space(doc, 6)

    # 2. Resumo executivo
    _add_section_title(doc, "2. Resumo executivo")
    _callout_objetivo(
        doc,
        "Consolidar a leitura e o enquadramento tributário do cadastro de produtos, destacando cobertura atual, "
        "qualidade das análises, achados recorrentes e recomendações práticas para reduzir risco, padronizar o cadastro "
        "e acelerar rotinas fiscais."
    )

    # KPIs (4 cards)
    kpis = [
        {"k": "Itens processados", "v": context.get("qtd_itens", 0), "h": "Base operacional"},
        {"k": "NCMs distintos", "v": context.get("qtd_ncms", 0), "h": "Variedade do cadastro"},
        {"k": "Cobertura (itens)", "v": f"{context.get('cobertura_pct', 0)}%", "h": "Itens com enquadramento"},
        {"k": "Pendências", "v": context.get("qtd_sem_cache", 0), "h": "Itens sem consulta"},
    ]
    _kpis_grid(doc, kpis)

    badges = [
        f"Produtos cadastrados: {context.get('qtd_produtos', 0)}",
        f"Lotes importados: {context.get('qtd_lotes', 0)}",
        f"Sucesso (cache): {context.get('taxa_sucesso_cache_pct', 0)}%",
        f"Erro (cache): {context.get('taxa_erro_cache_pct', 0)}%",
        f"Atualizações 30 dias: {context.get('qtd_atualizados_30d', 0)}",
    ]
    _badges_line(doc, badges)

    # Síntese (texto_principal) em “bloco”
    if context.get("texto_principal"):
        _add_section_title(doc, "Síntese gerada automaticamente")
        t = doc.add_table(rows=1, cols=1)
        _table_full_width(t)
        _style_table_basic(t)
        c = t.cell(0, 0)
        _set_cell_shading(c, "F7F7F7")
        p = c.paragraphs[0]
        # preserva quebras
        for i, line in enumerate(str(context["texto_principal"]).splitlines()):
            if i == 0:
                p.add_run(line)
            else:
                p.add_run("\n" + line)
        _add_space(doc, 6)

    # 3. Indicadores de qualidade e rastreabilidade
    _add_section_title(doc, "3. Indicadores de qualidade e rastreabilidade")

    resumo_arquivos = context.get("resumo_arquivos", {}) or {}
    ultimo_lote = context.get("ultimo_lote")
    range_itens = context.get("range_itens", {}) or {}

    left_rows = [
        ("Itens com enquadramento", context.get("qtd_itens_com_cache", 0)),
        ("Itens pendentes (sem cache)", context.get("qtd_sem_cache", 0)),
        ("Cobertura por itens", f"{context.get('cobertura_pct', 0)}%"),
        ("Cobertura por NCM (proxy)", f"{context.get('cobertura_ncms_pct', 0)}%"),
    ]
    right_rows = [
        ("Arquivos importados", resumo_arquivos.get("qtd_arquivos", 0)),
        ("Volume total", resumo_arquivos.get("total_bytes_fmt", "0 B")),
        ("Último lote", ultimo_lote.criado_em.strftime("%d/%m/%Y %H:%M") if ultimo_lote else "—"),
        ("Janela de itens", _fmt_janela(range_itens)),
    ]
    _two_tables_row(doc, "Cobertura detalhada", left_rows, "Rastreabilidade de importações", right_rows)

    # Erros mais recorrentes
    top_erros = context.get("top_erros") or []
    if top_erros:
        _table_rank(
            doc,
            "Erros mais recorrentes (prioridade de correção)",
            ["Ocorrência", "Quantidade"],
            [(e.get("erro", ""), e.get("qtd", 0)) for e in top_erros],
        )

    # 4. Achados
    _add_section_title(doc, "4. Principais achados (padrões recorrentes)")

    _table_rank(
        doc,
        "Bases legais mais frequentes (ICMS)",
        ["Base legal", "Qtd."],
        [(b.get("base", ""), b.get("qtd", 0)) for b in (context.get("top_bases") or [])],
    )

    _table_rank(
        doc,
        "NCMs mais presentes no cadastro",
        ["NCM", "Qtd."],
        [(n.get("ncm", ""), n.get("qtd", 0)) for n in (context.get("top_ncms") or [])],
    )

    _table_rank(
        doc,
        "Segmentos de ST recorrentes",
        ["Segmento", "Qtd."],
        [(s.get("segmento", ""), s.get("qtd", 0)) for s in (context.get("top_segmentos") or [])],
    )

    # 5. Recomendações
    _add_section_title(doc, "5. Recomendações (plano de ação objetivo)")
    recs = [
        (
            "Fechar cobertura do cadastro.",
            f"Priorizar os itens pendentes ({context.get('qtd_sem_cache', 0)}) e os NCMs mais recorrentes. "
            "Meta sugerida: elevar cobertura (itens) para ≥ 95%.",
        ),
        (
            "Padronizar regras por contexto.",
            "Validar com o time fiscal: UF de referência, operações (CFOPs praticados), regime e cadeia (origem → destino), "
            "reduzindo divergência entre compra, venda e escrituração.",
        ),
        (
            "Tratar causas de erro.",
            "Atacar os erros mais recorrentes (quando existirem), pois eles impactam a taxa de sucesso do cache e geram retrabalho.",
        ),
        (
            "Consolidar um “cadastro tributário padrão”.",
            "Após validação, transformar o resultado em padrão operacional para compras, precificação, faturamento e auditoria.",
        ),
    ]
    for i, (titul, desc) in enumerate(recs, 1):
        p = doc.add_paragraph()
        _set_paragraph_run(p, f"{i}. {titul} ", bold=True, size=11)
        _set_paragraph_run(p, desc, bold=False, size=11)
        p.paragraph_format.space_after = Pt(6)

    # 6. Observações
    _add_section_title(doc, "6. Observações e limitações")
    doc.add_paragraph(
        "Este documento apresenta um diagnóstico gerencial com base nos dados processados no sistema. "
        "A aplicação prática depende do contexto operacional, documental e das particularidades do contribuinte. "
        "Recomenda-se validação final pelo responsável fiscal antes de operacionalizar regras em larga escala."
    )

    _footer(doc)
    return doc


def _fmt_janela(range_itens):
    dt_min = range_itens.get("dt_min")
    dt_max = range_itens.get("dt_max")
    if dt_min and dt_max:
        return f"{dt_min.strftime('%d/%m/%Y')} → {dt_max.strftime('%d/%m/%Y')}"
    if dt_min and not dt_max:
        return dt_min.strftime("%d/%m/%Y")
    return "—"
