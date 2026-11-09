import re
from django import forms
from core.models import Empresa


def somente_digitos(valor: str) -> str:
    return re.sub(r"\D+", "", valor or "")


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = [
            "cnpj",
            "razao_social",
            "nome_fantasia",
            "inscricao_estadual",
            "regime_tributario",
            "atividade_origem",
            "atividade_destino",
            "cep",
            "endereco",
            "numero",
            "bairro",
            "municipio",
            "uf",
            "data_abertura",
            "cnae_principal",
            "cnaes_secundarios",
            'itens_substituto_tributario',
        ]
        widgets = {
            "data_abertura": forms.DateInput(attrs={"type": "date"}),
            "cnaes_secundarios": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["atividade_origem"].choices = Empresa.Atividade.choices
        self.fields["atividade_destino"].choices = Empresa.Atividade.choices
        self.fields["regime_tributario"].choices = Empresa.RegimeTributario.choices

        for f in ("regime_tributario", "atividade_origem", "atividade_destino"):
            self.fields[f].required = True

    def clean_regime_tributario(self):
        v = self.cleaned_data.get("regime_tributario")
        if v in (None, "", Empresa.RegimeTributario.OUTRO):
            raise forms.ValidationError("Selecione um regime tributário válido.")
        return v

    def clean_atividade_origem(self):
        v = self.cleaned_data.get("atividade_origem")
        if v in (None, "", Empresa.Atividade.OUTRO):
            raise forms.ValidationError("Selecione a atividade de origem.")
        return v

    def clean_atividade_destino(self):
        v = self.cleaned_data.get("atividade_destino")
        if v in (None, "", Empresa.Atividade.OUTRO):
            raise forms.ValidationError("Selecione a atividade de destino.")
        return v

    def clean_cnpj(self):
        cnpj = somente_digitos(self.cleaned_data.get("cnpj"))
        if len(cnpj) != 14:
            raise forms.ValidationError("CNPJ inválido. Informe 14 dígitos.")
        return cnpj

    def clean_cep(self):
        cep = somente_digitos(self.cleaned_data.get("cep"))
        if cep and len(cep) != 8:
            raise forms.ValidationError("CEP inválido. Informe 8 dígitos.")
        return cep
