from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from core.services.consulta_tare_df import consultar_tares_df


@login_required
def consultar_tare_df(request):
    cnpj = request.GET.get("cnpj", "")
    tipo = request.GET.get("tipo", "")

    if not cnpj:
        return JsonResponse({"erro": "CNPJ não informado."}, status=400)

    tipos_permitidos = None

    if tipo:
        tipos_permitidos = [int(tipo)]

    resultado = consultar_tares_df(
        cnpj=cnpj,
        tipos_permitidos=tipos_permitidos,
    )

    return JsonResponse({
        "cnpj_consultado": cnpj,
        "quantidade": len(resultado),
        "resultados": resultado,
    })