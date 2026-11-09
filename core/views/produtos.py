from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from core.authz import empresa_ativa_required
from core.services.authorization import get_empresa_ativa, get_empresa_or_404
import core.repositories.produto_ncm as produto_repo


@empresa_ativa_required
@login_required
def produtos_importados(request):
    empresa = get_empresa_ativa(request)

    if not empresa:
        return render(request, "core/produtos_lista.html", {"empresa": None, "produtos": []})

    q = (request.GET.get("q") or "").strip()
    qs = produto_repo.listar_por_empresa(empresa, q=q)

    return render(request, "core/produtos_lista.html", {
        "empresa": empresa,
        "produtos": qs[:1000],
        "q": q,
    })


def produto_excluir(request, empresa_id, produto_id):
    if request.method != "POST":
        messages.error(request, "Método inválido para exclusão.")
        return redirect("produtos_importados")

    empresa = get_empresa_or_404(request, empresa_id)
    produto = produto_repo.get_por_id_e_empresa(produto_id, empresa)

    nome = getattr(produto, "produto", "Produto")
    produto.delete()
    messages.success(request, f'"{nome}" excluído com sucesso.')
    return redirect("produtos_importados")
