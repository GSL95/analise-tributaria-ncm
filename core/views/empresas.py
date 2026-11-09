import datetime
import json
import re
import urllib.request
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.forms.empresa import EmpresaForm
from core.models import Empresa
from core.services.authorization import get_conta_id_unica, get_contas_do_usuario
from core.services.cnpj_service import consultar_dados_cnpj
from core.services.consulta_tare_df import consultar_tares_df

_conta_id_unica = get_conta_id_unica
_contas_do_usuario = get_contas_do_usuario


def _somente_digitos(v: str) -> str:
    return re.sub(r"\D+", "", v or "")


@login_required
def empresas(request):
    contas_ids = _contas_do_usuario(request.user)
    empresas_qs = Empresa.objects.filter(conta_id__in=contas_ids, ativa=True).order_by("razao_social")
    return render(request, "core/empresas_lista.html", {"empresas": empresas_qs})


@login_required
def empresa_criar(request):
    conta_id = _conta_id_unica(request.user)
    if not conta_id:
        messages.error(request, "Seu usuário não está vinculado a nenhuma conta. Fale com o administrador.")
        return redirect("empresas")

    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            cnpj = form.cleaned_data["cnpj"]
            if Empresa.objects.filter(conta_id=conta_id, cnpj=cnpj).exists():
                messages.warning(request, "Já existe uma empresa cadastrada com esse CNPJ.")
                return redirect("empresas")

            empresa = form.save(commit=False)
            empresa.conta_id = conta_id
            empresa.ativa = True
            empresa.save()

            messages.success(request, "Empresa cadastrada com sucesso.")
            return redirect("empresas")
        messages.error(request, "Corrija os campos do formulário.")
    else:
        form = EmpresaForm()

    return render(request, "core/empresa_form.html", {"form": form, "titulo": "Cadastrar Empresa"})


@login_required
def selecionar_empresa(request, empresa_id: int):
    if request.method != "POST":
        return HttpResponseForbidden("Método não permitido")

    contas_ids = _contas_do_usuario(request.user)
    empresa = get_object_or_404(Empresa, id=empresa_id, conta_id__in=contas_ids, ativa=True)

    request.session["empresa_ativa_id"] = empresa.id
    messages.success(request, f"Empresa ativa: {empresa.razao_social}")
    return redirect("dashboard")


def validar_cnpj(cnpj):
    cnpj = re.sub(r"\D", "", cnpj)

    if len(cnpj) != 14:
        return False

    # evita sequências repetidas
    if cnpj == cnpj[0] * 14:
        return False

    def calcular_digito(cnpj_parcial, pesos):
        soma = sum(int(num) * peso for num, peso in zip(cnpj_parcial, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos_1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    pesos_2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]

    digito_1 = calcular_digito(cnpj[:12], pesos_1)
    digito_2 = calcular_digito(cnpj[:12] + digito_1, pesos_2)

    return cnpj[-2:] == digito_1 + digito_2



@login_required
def consultar_cnpj(request):
    cnpj = request.GET.get("cnpj", "")

    if not cnpj:
        return JsonResponse(
            {"error": "CNPJ não informado."},
            status=400
        )

    cnpj_limpo = re.sub(r"\D", "", cnpj)

    if not validar_cnpj(cnpj_limpo):
        return JsonResponse(
            {"error": "CNPJ inválido."},
            status=400
        )

    dados = consultar_dados_cnpj(cnpj_limpo)

    if not dados:
        return JsonResponse(
            {"error": "Não foi possível consultar o CNPJ nas fontes disponíveis."},
            status=404
        )
    tares_st = consultar_tares_df(cnpj_limpo, tipos_permitidos=[30])
        
    if tares_st:
        substituto_tributario = tares_st[0]

        dados["itens_substituto_tributario"] = ", ".join(
            substituto_tributario.get("itens", [])
        )

        dados["beneficios_fiscais"] = substituto_tributario
    else:
        dados["itens_substituto_tributario"] = ""
        dados["beneficios_fiscais"] = {}
        
    # dados["itens_substituto_tributario"] = substituto_tributario['itens']
    
    return JsonResponse(dados, safe=False)

def empresa_editar(request, empresa_id: int):
    contas_ids = _contas_do_usuario(request.user)

    empresa = get_object_or_404(
        Empresa,
        id=empresa_id,
        conta_id__in=contas_ids,
        ativa=True,
    )

    if request.method == "POST":
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa atualizada com sucesso.")
            return redirect("empresas")
        messages.error(request, "Corrija os campos do formulário.")
    else:
        form = EmpresaForm(instance=empresa)

    return render(request, "core/empresa_form.html", {"form": form, "titulo": "Editar Empresa"})

def empresa_excluir(request, id):
    if request.method == "POST":
        empresa = get_object_or_404(Empresa, id=id)

        nome = empresa.razao_social
        empresa.delete()

        messages.success(request, f'Empresa "{nome}" excluída com sucesso.')

    else:
        messages.error(request, 'Método inválido para exclusão.')

    return redirect('empresas')