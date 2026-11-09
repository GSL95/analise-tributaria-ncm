import os
from datetime import datetime
from pathlib import Path
from io import BytesIO

import re
from openpyxl import load_workbook

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from openpyxl import Workbook

from core.authz import empresa_ativa_required
from core.models import Empresa
from core.models import UploadLote, UploadArquivo
from core.services.authorization import get_empresa_ativa
from core.services.fila_upload import processar_lote_em_background
import core.repositories.upload_lote as upload_repo

ALLOWED_EXTS = {".xml", ".zip", ".xlsx"}

_empresa_ativa = get_empresa_ativa


@login_required
@empresa_ativa_required
def uploads(request):
    empresa = _empresa_ativa(request)
    lotes = upload_repo.listar_por_empresa(empresa, limit=50)
    return render(request, "core/uploads.html", {"empresa": empresa, "lotes": lotes})


def _normalizar_header(s: str) -> str:
    return (s or "").strip().upper()

def validar_planilha_produtos_ncm(file_obj) -> tuple[bool, str, list[str]]:
    avisos = []

    try:
        wb = load_workbook(file_obj, read_only=True, data_only=True)
        ws = wb.active

        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        header = [_normalizar_header(h) for h in header]

        if header[:2] != ["PRODUTO", "NCM"]:
            return False, "Planilha fora do padrão. Cabeçalho deve ser: PRODUTO | NCM.", avisos

        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            produto = str(row[0] or "").strip() if len(row) > 0 else ""
            ncm = re.sub(r"\D+", "", str(row[1] or "")) if len(row) > 1 else ""

            if not produto and not ncm:
                continue

            if not produto:
                avisos.append(f"Linha {idx}: PRODUTO vazio.")

            if not ncm:
                avisos.append(f"Linha {idx}: NCM vazio.")
            elif len(ncm) != 8:
                avisos.append(f"Linha {idx}: NCM inválido: {ncm}.")

        return True, "OK", avisos

    except Exception as e:
        return False, f"Não foi possível ler a planilha. Envie um .xlsx válido. Erro: {e}", avisos

@login_required
@empresa_ativa_required
def criar_upload_lote(request):
    if request.method != "POST":
        return redirect("uploads")

    empresa = _empresa_ativa(request)

    files = request.FILES.getlist("arquivos")
    if not files:
        messages.error(request, "Selecione ao menos um arquivo.")
        return redirect("uploads")

    # valida extensões
    exts = {Path(f.name).suffix.lower() for f in files}
    if not exts.issubset(ALLOWED_EXTS):
        messages.error(request, f"Extensões permitidas: {', '.join(sorted(ALLOWED_EXTS))}")
        return redirect("uploads")

    # valida planilhas (se houver)
    avisos_planilha = []

    for f in files:
        if Path(f.name).suffix.lower() == ".xlsx":
            ok, msg, avisos = validar_planilha_produtos_ncm(f)

            if not ok:
                messages.error(request, msg)
                return redirect("uploads")

            avisos_planilha.extend(avisos)
            f.seek(0)

    # regra simples: se tiver xlsx -> PLANILHA, senão XML
    tipo = UploadLote.Tipo.PLANILHA if ".xlsx" in exts else UploadLote.Tipo.XML

    # cria lote
    lote = UploadLote.objects.create(
        empresa=empresa,
        criado_por=request.user,
        tipo=tipo,
        status=UploadLote.Status.PENDENTE,
        observacao="\n".join(avisos_planilha) if avisos_planilha else "",
    )

    # salva arquivos do lote
    for f in files:
        ext = Path(f.name).suffix.lower()
        UploadArquivo.objects.create(
            lote=lote,
            arquivo=f,
            nome_original=f.name,
            extensao=ext,
            tamanho=getattr(f, "size", 0) or 0,
        )

    # dispara processamento em background
    processar_lote_em_background(lote.id)
    messages.info(request, f"Lote #{lote.id} enviado para processamento em background.")

    return redirect("uploads")


@login_required
@empresa_ativa_required
def upload_lote_progresso_json(request, lote_id: int):
    empresa = _empresa_ativa(request)
    lote = upload_repo.get_por_empresa_e_id(empresa, lote_id)
    if lote is None:
        return JsonResponse({"erro": "Lote não encontrado."}, status=404)

    STATUS_FINAIS = {UploadLote.Status.CONCLUIDO, UploadLote.Status.ERRO}

    # Estimativa de término
    eta_segundos = None
    if lote.status == UploadLote.Status.PROCESSANDO and lote.processados > 0 and lote.total > 0:
        from django.utils import timezone as tz
        inicio = lote.atualizado_em or lote.criado_em
        elapsed = (tz.now() - lote.criado_em).total_seconds()
        if elapsed > 0:
            velocidade = lote.processados / elapsed  # itens/segundo
            restantes = lote.total - lote.processados
            if velocidade > 0:
                eta_segundos = round(restantes / velocidade)

    return JsonResponse({
        "status": lote.status,
        "status_display": lote.get_status_display(),
        "total": lote.total,
        "processados": lote.processados,
        "percentual": lote.percentual,
        "arquivo_atual": lote.arquivo_atual,
        "observacao": lote.observacao,
        "eta_segundos": eta_segundos,
        "concluido": lote.status in STATUS_FINAIS,
    })



@login_required
def baixar_modelo_planilha(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "PRODUTOS"

    # Cabeçalho
    ws.append(["PRODUTO", "NCM"])

    # Exemplo
    ws.append(["TINTA ACRÍLICA FOSCA 18L", "32091010"])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    filename = "modelo_produtos_ncm.xlsx"
    resp = HttpResponse(
        bio.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
