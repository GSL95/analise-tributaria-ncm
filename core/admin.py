from django.contrib import admin
from .models import (
    Conta,
    Membership,
    Empresa,
    UploadLote,
    UploadArquivo,
    ProdutoNcm,
    AnaliseNcmCache,
    AnaliseNcmCacheCompartilhado,
    AnaliseItem,
)

# ==========
# INLINES
# ==========

class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("usuario",)
    raw_id_fields = ("usuario",)


class EmpresaInline(admin.TabularInline):
    model = Empresa
    extra = 0


class UploadArquivoInline(admin.TabularInline):
    model = UploadArquivo
    extra = 0


class UploadLoteInline(admin.TabularInline):
    model = UploadLote
    extra = 0
    autocomplete_fields = ("empresa", "criado_por")
    raw_id_fields = ("criado_por",)


class AnaliseItemInline(admin.TabularInline):
    model = AnaliseItem
    extra = 0


# ==========
# ADMINS
# ==========

@admin.register(Conta)
class ContaAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "criada_em")
    search_fields = ("nome",)
    ordering = ("-criada_em",)
    inlines = (MembershipInline, EmpresaInline)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "conta", "usuario", "papel", "criado_em")
    list_filter = ("papel", "conta")
    search_fields = ("conta__nome", "usuario__email", "usuario__username")
    autocomplete_fields = ("conta", "usuario")
    raw_id_fields = ("usuario",)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("id", "razao_social", "cnpj", "conta", "get_regime_tributario_display", "ativa", "criada_em")
    list_filter = ("regime_tributario", "ativa", "uf", "conta")
    search_fields = ("razao_social", "nome_fantasia", "cnpj", "inscricao_estadual")
    ordering = ("-criada_em",)
    autocomplete_fields = ("conta",)
    inlines = (UploadLoteInline,)


@admin.register(UploadLote)
class UploadLoteAdmin(admin.ModelAdmin):
    list_display = ("id", "empresa", "tipo", "status", "criado_por", "criado_em")
    list_filter = ("tipo", "status", "empresa")
    search_fields = ("empresa__razao_social", "empresa__cnpj", "observacao")
    ordering = ("-criado_em",)
    autocomplete_fields = ("empresa", "criado_por")
    raw_id_fields = ("criado_por",)
    inlines = (UploadArquivoInline, AnaliseItemInline)


@admin.register(UploadArquivo)
class UploadArquivoAdmin(admin.ModelAdmin):
    list_display = ("id", "nome_original", "extensao", "tamanho", "lote", "criado_em")
    list_filter = ("extensao",)
    search_fields = ("nome_original", "lote__empresa__razao_social", "lote__empresa__cnpj")
    ordering = ("-criado_em",)
    autocomplete_fields = ("lote",)


@admin.register(ProdutoNcm)
class ProdutoNcmAdmin(admin.ModelAdmin):
    list_display = ("id", "empresa", "produto", "ncm", "origem", "upload_lote", "criado_em")
    list_filter = ("origem", "empresa")
    search_fields = ("produto", "ncm", "empresa__razao_social", "empresa__cnpj")
    ordering = ("-criado_em",)
    autocomplete_fields = ("empresa", "upload_lote")


@admin.register(AnaliseNcmCache)
class AnaliseNcmCacheAdmin(admin.ModelAdmin):
    list_display = ("id", "empresa", "ncm", "uf_origem", "uf_destino", "regime_tributario", "status", "consultado_em")
    list_filter = ("status", "uf_origem", "uf_destino", "regime_tributario", "empresa")
    search_fields = ("ncm", "empresa__razao_social", "empresa__cnpj", "erro_msg")
    ordering = ("-consultado_em",)
    autocomplete_fields = ("empresa",)
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = (AnaliseItemInline,)


@admin.register(AnaliseNcmCacheCompartilhado)
class AnaliseNcmCacheCompartilhadoAdmin(admin.ModelAdmin):
    list_display = ("id", "ncm", "uf_origem", "uf_destino", "regime_tributario", "atividade_origem", "atividade_destino", "status", "consultado_em")
    list_filter = ("status", "uf_origem", "uf_destino", "regime_tributario")
    search_fields = ("ncm", "erro_msg")
    ordering = ("-consultado_em",)
    readonly_fields = ("criado_em", "atualizado_em")


@admin.register(AnaliseItem)
class AnaliseItemAdmin(admin.ModelAdmin):
    list_display = ("id", "empresa", "upload_lote", "produto", "ncm", "produto_ncm", "cache", "criado_em")
    list_filter = ("empresa",)
    search_fields = ("produto", "ncm", "empresa__razao_social", "empresa__cnpj")
    ordering = ("-criado_em",)
    autocomplete_fields = ("empresa", "upload_lote", "produto_ncm", "cache")
