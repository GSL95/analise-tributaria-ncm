from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def empresa_ativa_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("empresa_ativa_id"):
            messages.warning(request, "Selecione uma empresa para continuar.")
            return redirect("empresas")
        return view_func(request, *args, **kwargs)
    return _wrapped
