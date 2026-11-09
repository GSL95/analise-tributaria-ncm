from .models import Empresa


def empresa_ativa(request):
    empresa_id = request.session.get("empresa_ativa_id")
    if not empresa_id or not request.user.is_authenticated:
        return {"empresa_ativa": None}

    empresa = Empresa.objects.filter(id=empresa_id).select_related("conta").first()
    return {"empresa_ativa": empresa}
