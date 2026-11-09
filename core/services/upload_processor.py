from decimal import Decimal, InvalidOperation
import re
import zipfile
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET

from openpyxl import load_workbook
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.models import UploadLote, UploadArquivo, ProdutoNcm, PlanilhaLinhaOriginal, AnaliseItem, NotaFiscal, ItemNotaFiscal

BATCH_PROGRESS = 100  # atualiza progresso a cada N itens (planilha)


def _limpar_ncm(value) -> str:
    ncm = re.sub(r"\D+", "", str(value or ""))
    return ncm[:8] if len(ncm) >= 8 else ncm


def _limpar_produto(value) -> str:
    return (value or "").strip()


def _tick(lote_id: int, delta: int = 1, arquivo_atual: str = "") -> None:
    UploadLote.objects.filter(pk=lote_id).update(
        processados=F("processados") + delta,
        arquivo_atual=arquivo_atual[:255],
        atualizado_em=timezone.now(),
    )


def processar_lote_upload(lote_id: int) -> dict:
    """
    Processa um lote inteiro e salva Produto+NCM no banco.
    Retorna resumo: {total, inseridos, ignorados, erros}
    """
    lote = UploadLote.objects.select_related("empresa").prefetch_related("arquivos").get(id=lote_id)

    UploadLote.objects.filter(pk=lote_id).update(
        status=UploadLote.Status.PROCESSANDO,
        processados=0,
        total=0,
        arquivo_atual="",
        atualizado_em=timezone.now(),
    )
    lote.refresh_from_db()

    total = inseridos = ignorados = 0
    erros = []

    try:
        if lote.tipo == UploadLote.Tipo.PLANILHA:
            for arq in lote.arquivos.all():
                if Path(arq.nome_original).suffix.lower() == ".xlsx":
                    r = _processar_planilha(lote, arq)
                    total += r["total"]
                    inseridos += r["inseridos"]
                    ignorados += r["ignorados"]
                    erros.extend(r["erros"])
        else:
            for arq in lote.arquivos.all():
                ext = Path(arq.nome_original).suffix.lower()
                if ext == ".xml":
                    # conta os itens do XML e atualiza total
                    xml_bytes = arq.arquivo.read()
                    root_tmp = ET.fromstring(xml_bytes)
                    n_itens = len(root_tmp.findall(".//{*}det"))
                    UploadLote.objects.filter(pk=lote_id).update(
                        total=F("total") + max(n_itens, 1),
                        atualizado_em=timezone.now(),
                    )
                    r = _processar_xml_bytes(lote, xml_bytes, arq.nome_original)
                    _tick(lote_id, max(n_itens, 1), arq.nome_original)
                elif ext == ".zip":
                    r = _processar_zip(lote, arq)
                else:
                    continue

                total += r["total"]
                inseridos += r["inseridos"]
                ignorados += r["ignorados"]
                erros.extend(r["erros"])

        UploadLote.objects.filter(pk=lote_id).update(
            status=UploadLote.Status.CONCLUIDO if not erros else UploadLote.Status.ERRO,
            observacao=f"Total: {total} | Inseridos: {inseridos} | Ignorados: {ignorados} | Erros: {len(erros)}"[:255],
            arquivo_atual="",
            atualizado_em=timezone.now(),
        )

        return {"total": total, "inseridos": inseridos, "ignorados": ignorados, "erros": erros}

    except Exception as e:
        UploadLote.objects.filter(pk=lote_id).update(
            status=UploadLote.Status.ERRO,
            observacao=f"Falha no processamento: {e}"[:255],
            atualizado_em=timezone.now(),
        )
        return {"total": total, "inseridos": inseridos, "ignorados": ignorados, "erros": [str(e)]}

def _processar_planilha(lote: UploadLote, arq: UploadArquivo) -> dict:
    total = inseridos = ignorados = 0
    erros = []

    arq.arquivo.open("rb")
    try:
        wb = load_workbook(arq.arquivo, read_only=True, data_only=True)
        ws = wb.active

        # header completo (todas as colunas)
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        headers = [str(h or "").strip() for h in header_row]

        # mapa header normalizado -> índice
        norm = lambda s: (s or "").strip().upper()
        idx_map = {norm(name): i for i, name in enumerate(headers) if norm(name)}

        if "PRODUTO" not in idx_map or "NCM" not in idx_map:
            return {
                "total": 0, "inseridos": 0, "ignorados": 0,
                "erros": ["Planilha fora do padrão: precisa ter colunas 'PRODUTO' e 'NCM' (em qualquer ordem)."]
            }

        idx_prod = idx_map["PRODUTO"]
        idx_ncm = idx_map["NCM"]

        linhas_originais = []
        produtos_ncm = []

        linha_idx = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            # monta dict completo (todas as colunas)
            dados_originais = {}
            for i, col_name in enumerate(headers):
                if not col_name:
                    continue
                v = row[i] if i < len(row) else ""
                dados_originais[col_name] = "" if v is None else v

            # pula linha totalmente vazia (todas as colunas)
            if not any(str(v).strip() for v in dados_originais.values()):
                continue

            total += 1

            linhas_originais.append(
                PlanilhaLinhaOriginal(
                    upload_lote=lote,
                    linha_idx=linha_idx,
                    dados=dados_originais,
                )
            )
            linha_idx += 1

            # pega produto/ncm a partir dos índices reais
            raw_produto = row[idx_prod] if idx_prod < len(row) else ""
            raw_ncm = row[idx_ncm] if idx_ncm < len(row) else ""

            produto = _limpar_produto(raw_produto if raw_produto is not None else "")
            ncm = _limpar_ncm(raw_ncm if raw_ncm is not None else "")

            if not produto:
                erros.append("Planilha: PRODUTO vazio em uma linha.")
                continue

            produtos_ncm.append(
                ProdutoNcm(
                    empresa=lote.empresa,
                    produto=produto[:255],
                    ncm=ncm,
                    upload_lote=lote,
                    origem="PLANILHA",
                )
            )

        if not linhas_originais:
            return {"total": 0, "inseridos": 0, "ignorados": 0, "erros": ["Planilha sem linhas válidas."]}

        # Informa total antes de salvar
        UploadLote.objects.filter(pk=lote.id).update(
            total=len(linhas_originais),
            arquivo_atual=arq.nome_original[:255],
            atualizado_em=timezone.now(),
        )

        with transaction.atomic():
            PlanilhaLinhaOriginal.objects.filter(upload_lote=lote).delete()
            AnaliseItem.objects.filter(upload_lote=lote).delete()

            # Salva em batches e atualiza processados incrementalmente
            batch = 1000
            for i in range(0, len(linhas_originais), batch):
                PlanilhaLinhaOriginal.objects.bulk_create(linhas_originais[i:i+batch])
                _tick(lote.id, min(batch, len(linhas_originais) - i))

            if produtos_ncm:
                created = ProdutoNcm.objects.bulk_create(produtos_ncm, ignore_conflicts=True, batch_size=1000)
                inseridos += len(created)
                ignorados += (len(produtos_ncm) - len(created))

            linhas_db = list(
                PlanilhaLinhaOriginal.objects.filter(upload_lote=lote).order_by("linha_idx")
            )

            analises = []
            for pl in linhas_db:
                # agora busca pelas chaves reais (qualquer nome original), mas usa o mapeamento
                raw_produto = pl.dados.get(headers[idx_prod], "")
                raw_ncm = pl.dados.get(headers[idx_ncm], "")

                produto_norm = _limpar_produto(raw_produto)
                ncm_norm = _limpar_ncm(raw_ncm)

                analises.append(
                    AnaliseItem(
                        empresa=lote.empresa,
                        upload_lote=lote,
                        planilha_linha=pl,
                        produto=produto_norm[:255],
                        ncm=ncm_norm,
                    )
                )
            AnaliseItem.objects.bulk_create(analises, batch_size=1000)

        return {"total": total, "inseridos": inseridos, "ignorados": ignorados, "erros": erros}

    finally:
        arq.arquivo.close()

def _processar_zip(lote: UploadLote, arq: UploadArquivo) -> dict:
    total = inseridos = ignorados = 0
    erros = []

    arq.arquivo.open("rb")
    try:
        zdata = arq.arquivo.read()
        with zipfile.ZipFile(BytesIO(zdata), "r") as zf:
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]

            # Informa total de XMLs antes de começar
            UploadLote.objects.filter(pk=lote.id).update(
                total=F("total") + len(xml_names),
                arquivo_atual=arq.nome_original[:255],
                atualizado_em=timezone.now(),
            )

            for name in xml_names:
                try:
                    r = _processar_xml_bytes(lote, zf.read(name), name)
                    total += r["total"]
                    inseridos += r["inseridos"]
                    ignorados += r["ignorados"]
                    erros.extend(r["erros"])
                except Exception as e:
                    erros.append(f"ZIP {arq.nome_original} / {name}: {e}")
                finally:
                    _tick(lote.id, 1, name)

        return {"total": total, "inseridos": inseridos, "ignorados": ignorados, "erros": erros}
    finally:
        arq.arquivo.close()

def _processar_xml_bytes(lote: UploadLote, xml_bytes: bytes, origem_nome: str) -> dict:
    """
    Extrai itens NFe/CTe genéricos procurando <det><prod><xProd> e <NCM>.
    """
    total = inseridos = ignorados = 0
    erros = []

    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        return {"total": 0, "inseridos": 0, "ignorados": 0, "erros": [f"XML inválido {origem_nome}: {e}"]}

    objs = []
    # procura por quaisquer namespaces
    for det in root.findall(".//{*}det"):
        prod = det.find(".//{*}prod")
        if prod is None:
            continue

        xprod_el = prod.find(".//{*}xProd")
        ncm_el = prod.find(".//{*}NCM")

        produto = _limpar_produto(xprod_el.text if xprod_el is not None else "")
        ncm = _limpar_ncm(ncm_el.text if ncm_el is not None else "")

        if not produto and not ncm:
            continue

        total += 1
        if not produto:
            erros.append(f"{origem_nome}: item sem xProd.")
            continue

        objs.append(
            ProdutoNcm(
                empresa=lote.empresa,
                produto=produto[:255],
                ncm=ncm,
                upload_lote=lote,
                origem="XML",
            )
        )

    if objs:
        with transaction.atomic():
            created = ProdutoNcm.objects.bulk_create(objs, ignore_conflicts=True)
        inseridos += len(created)
        ignorados += (len(objs) - len(created))

    return {"total": total, "inseridos": inseridos, "ignorados": ignorados, "erros": erros}

def _d(value, default="0"):
    try:
        if value is None:
            return Decimal(default)
        s = str(value).strip().replace(",", ".")
        return Decimal(s) if s else Decimal(default)
    except (InvalidOperation, ValueError):
        return Decimal(default)

def _first_child(parent):
    if parent is None:
        return None
    for ch in list(parent):
        return ch
    return None

def _get_text(node, tag):
    el = node.find(f".//{{*}}{tag}") if node is not None else None
    return (el.text or "").strip() if el is not None and el.text else ""

def _extrair_chave(root) -> str:
    inf = root.find(".//{*}infNFe")
    if inf is None:
        return ""
    return (inf.get("Id", "") or "").replace("NFe", "").strip()

def _extrair_cabecalho_nfe(root) -> dict:
    ide = root.find(".//{*}ide")
    emit = root.find(".//{*}emit")
    dest = root.find(".//{*}dest")
    tot = root.find(".//{*}ICMSTot")

    chave = _extrair_chave(root)

    return {
        "chave": chave,
        "numero": _get_text(ide, "nNF"),
        "serie": _get_text(ide, "serie"),
        "modelo": _get_text(ide, "mod") or "55",
        "cnpj_emitente": re.sub(r"\D+", "", _get_text(emit, "CNPJ"))[:14],
        "cnpj_destinatario": re.sub(r"\D+", "", _get_text(dest, "CNPJ"))[:14],
        "valor_total": _d(_get_text(tot, "vNF")),
        "valor_produtos": _d(_get_text(tot, "vProd")),
        "raw_resumo": {},
        "emissao_em": None,  # se quiser, parse de dhEmi aqui
    }

def _extrair_impostos_item(det) -> dict:
    imposto = det.find(".//{*}imposto")

    # ICMS
    icms = imposto.find(".//{*}ICMS") if imposto is not None else None
    icms_grp = _first_child(icms)

    icms_cst = _get_text(icms_grp, "CST")
    icms_csosn = _get_text(icms_grp, "CSOSN")

    icms_base = _d(_get_text(icms_grp, "vBC"))
    icms_aliq = _d(_get_text(icms_grp, "pICMS"))
    icms_valor = _d(_get_text(icms_grp, "vICMS"))

    icmsst_base = _d(_get_text(icms_grp, "vBCST"))
    icmsst_aliq = _d(_get_text(icms_grp, "pICMSST"))
    icmsst_valor = _d(_get_text(icms_grp, "vICMSST"))

    # PIS
    pis = imposto.find(".//{*}PIS") if imposto is not None else None
    pis_grp = _first_child(pis)
    pis_cst = _get_text(pis_grp, "CST")
    pis_base = _d(_get_text(pis_grp, "vBC"))
    pis_aliq = _d(_get_text(pis_grp, "pPIS"))
    pis_valor = _d(_get_text(pis_grp, "vPIS"))

    # COFINS
    cof = imposto.find(".//{*}COFINS") if imposto is not None else None
    cof_grp = _first_child(cof)
    cofins_cst = _get_text(cof_grp, "CST")
    cofins_base = _d(_get_text(cof_grp, "vBC"))
    cofins_aliq = _d(_get_text(cof_grp, "pCOFINS"))
    cofins_valor = _d(_get_text(cof_grp, "vCOFINS"))

    return {
        "icms_cst": icms_cst,
        "icms_csosn": icms_csosn,
        "icms_base": icms_base,
        "icms_aliq": icms_aliq,
        "icms_valor": icms_valor,
        "icmsst_base": icmsst_base,
        "icmsst_aliq": icmsst_aliq,
        "icmsst_valor": icmsst_valor,

        "pis_cst": pis_cst,
        "pis_base": pis_base,
        "pis_aliq": pis_aliq,
        "pis_valor": pis_valor,

        "cofins_cst": cofins_cst,
        "cofins_base": cofins_base,
        "cofins_aliq": cofins_aliq,
        "cofins_valor": cofins_valor,

        "raw_imposto": {},
    }

def _processar_xml_bytes(lote: UploadLote, xml_bytes: bytes, origem_nome: str) -> dict:
    print("\n" + "=" * 80)
    print(f"[INÍCIO XML] Arquivo: {origem_nome}")
    print(f"Lote ID: {lote.id} | Empresa: {lote.empresa_id}")
    print("=" * 80)

    total = inseridos = ignorados = 0
    erros = []

    try:
        root = ET.fromstring(xml_bytes)
        print("[OK] XML parseado com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao parsear XML: {e}")
        return {"total": 0, "inseridos": 0, "ignorados": 0, "erros": [f"XML inválido {origem_nome}: {e}"]}

    cab = _extrair_cabecalho_nfe(root)
    chave = cab.get("chave", "")

    print(f"[INFO] Chave extraída: {chave}")

    if not chave or len(chave) != 44:
        print("[ERRO] Chave NF-e inválida ou ausente.")
        return {"total": 0, "inseridos": 0, "ignorados": 0, "erros": [f"{origem_nome}: chave NF-e inválida/ausente."]}

    itens_objs = []
    dets = root.findall(".//{*}det")
    print(f"[INFO] Total de <det> encontrados no XML: {len(dets)}")

    for det in dets:
        prod = det.find(".//{*}prod")
        if prod is None:
            print("[WARN] <det> sem <prod>")
            continue

        n_item_raw = det.get("nItem")
        try:
            n_item = int(n_item_raw)
        except Exception:
            n_item = 0

        produto = _limpar_produto(_get_text(prod, "xProd"))[:255]
        ncm = _limpar_ncm(_get_text(prod, "NCM"))
        cfop = (_get_text(prod, "CFOP") or "")[:4]

        qtd = _d(_get_text(prod, "qCom"), "0")
        v_prod = _d(_get_text(prod, "vProd"), "0")

        if not produto:
            print(f"[WARN] Item {n_item} sem produto.")
            continue

        imp = _extrair_impostos_item(det)

        print(f"""
        ───────────────────────────────────────────────
        Item: {n_item}
        Produto: {produto}
        NCM: {ncm} | CFOP: {cfop}
        ICMS CST: {imp['icms_cst']} | ICMS Valor: {imp['icms_valor']}
        PIS CST: {imp['pis_cst']} | PIS Valor: {imp['pis_valor']}
        COFINS CST: {imp['cofins_cst']} | COFINS Valor: {imp['cofins_valor']}
        ───────────────────────────────────────────────
        """)

        itens_objs.append({
            "n_item": n_item,
            "produto": produto,
            "ncm": ncm,
            "cfop": cfop,
            "cest": "",
            "qtd": qtd,
            "v_un": _d(_get_text(prod, "vUnCom"), "0"),
            "v_prod": v_prod,
            **imp
        })

    if not itens_objs:
        print("[ERRO] Nenhum item válido encontrado.")
        return {"total": 0, "inseridos": 0, "ignorados": 0, "erros": [f"{origem_nome}: sem itens válidos."]}

    total = len(itens_objs)
    print(f"[INFO] Total de itens válidos extraídos: {total}")

    with transaction.atomic():
        nota, nota_criada = NotaFiscal.objects.get_or_create(
            empresa=lote.empresa,
            chave=chave,
            defaults={
                "upload_lote": lote,
                "tipo": NotaFiscal.Tipo.NFE,
                "numero": cab["numero"],
                "serie": cab["serie"],
                "modelo": cab["modelo"],
                "emissao_em": cab["emissao_em"],
                "cnpj_emitente": cab["cnpj_emitente"],
                "cnpj_destinatario": cab["cnpj_destinatario"],
                "valor_total": cab["valor_total"],
                "valor_produtos": cab["valor_produtos"],
                "raw_resumo": cab.get("raw_resumo", {}),
            }
        )

        print(f"[INFO] Nota {'CRIADA' if nota_criada else 'JÁ EXISTENTE'} (ID: {nota.id})")

        itens_existentes = set(
            ItemNotaFiscal.objects.filter(nota=nota).values_list("n_item", flat=True)
        )

        print(f"[INFO] Itens já existentes na nota: {len(itens_existentes)}")

        itens_bulk = []
        produtos_ncm_bulk = []

        seen = set()

        for it in itens_objs:
            key = (it["produto"], it["ncm"])

            if key not in seen:
                seen.add(key)
                produtos_ncm_bulk.append(
                    ProdutoNcm(
                        empresa=lote.empresa,
                        produto=it["produto"][:255],
                        ncm=it["ncm"],
                        upload_lote=lote,
                        origem="XML",
                    )
                )

            if it["n_item"] in itens_existentes:
                ignorados += 1
                continue

            itens_bulk.append(
                ItemNotaFiscal(
                    nota=nota,
                    empresa=lote.empresa,
                    upload_lote=lote,
                    n_item=it["n_item"],
                    produto=it["produto"],
                    ncm=it["ncm"],
                    cfop=it["cfop"],
                    cest=it["cest"],
                    qtd=it["qtd"],
                    v_un=it["v_un"],
                    v_prod=it["v_prod"],
                    icms_cst=it["icms_cst"],
                    icms_csosn=it["icms_csosn"],
                    icms_base=it["icms_base"],
                    icms_aliq=it["icms_aliq"],
                    icms_valor=it["icms_valor"],
                    icmsst_base=it["icmsst_base"],
                    icmsst_aliq=it["icmsst_aliq"],
                    icmsst_valor=it["icmsst_valor"],
                    pis_cst=it["pis_cst"],
                    pis_base=it["pis_base"],
                    pis_aliq=it["pis_aliq"],
                    pis_valor=it["pis_valor"],
                    cofins_cst=it["cofins_cst"],
                    cofins_base=it["cofins_base"],
                    cofins_aliq=it["cofins_aliq"],
                    cofins_valor=it["cofins_valor"],
                    raw_imposto=it.get("raw_imposto", {}),
                )
            )

        if produtos_ncm_bulk:
            ProdutoNcm.objects.bulk_create(
                produtos_ncm_bulk,
                ignore_conflicts=True,
                batch_size=2000
            )
            print(f"[INFO] ProdutoNcm inseridos/tentados: {len(produtos_ncm_bulk)}")

        if itens_bulk:
            ItemNotaFiscal.objects.bulk_create(itens_bulk, batch_size=2000)
            inseridos += len(itens_bulk)
            print(f"[OK] Itens inseridos: {len(itens_bulk)}")

    print(f"[FINAL] Total: {total} | Inseridos: {inseridos} | Ignorados: {ignorados}")
    print("=" * 80 + "\n")

    return {"total": total, "inseridos": inseridos, "ignorados": ignorados, "erros": erros}