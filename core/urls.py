from django.urls import path

from core.views.dashboard import dashboard_geral
from core.views.empresas import empresas, empresa_criar, selecionar_empresa, consultar_cnpj, empresa_editar, empresa_excluir
from core.views.uploads import uploads, criar_upload_lote, baixar_modelo_planilha, upload_lote_progresso_json
from core.views.notas import notas
from core.views.ncm import ncm_lista, ncm_detalhe, ncm_cache
from core.views.relatorios import relatorios
from core.views.produtos import produtos_importados, produto_excluir
from core.views.analise import analise_tributaria_detail, analise_tributaria_list, analise_tributaria_reprocessar, analise_tributaria_disparar, analise_tributaria_retomar, analise_tributaria_analisar_produto, analise_tributaria_exportar_xlsx, analise_tributaria_analisar_item, fila_analise_status, fila_analise_status_json, fila_analise_cancelar
from core.views.divergencias import divergencias_fiscais
from core.views.consultar_tare_df import consultar_tare_df


urlpatterns = [
    path("", dashboard_geral, name="dashboard"),

    path("empresas/", empresas, name="empresas"),
    path("empresas/nova/", empresa_criar, name="empresa_criar"),
    path("empresas/selecionar/<int:empresa_id>/", selecionar_empresa, name="selecionar_empresa"),

    path("consultar-cnpj/", consultar_cnpj, name="consultar_cnpj"),
    path("consultar-tare-df/", consultar_tare_df, name="consultar_tare_df"),


    path("uploads/", uploads, name="uploads"),
    path("notas/", notas, name="notas"),
    path("ncm/", ncm_lista, name="ncm_lista"),
    path("ncm/<str:ncm>/", ncm_detalhe, name="ncm_detalhe"),
    path("ncm/cache/<int:cache_id>/", ncm_cache, name="ncm_cache"),
    path("relatorios/", relatorios, name="relatorios"),
    
    path("empresas/<int:empresa_id>/editar/", empresa_editar, name="empresa_editar"),

    path("uploads/", uploads, name="uploads"),
    path("uploads/enviar/", criar_upload_lote, name="criar_upload_lote"),
    path("uploads/modelo-planilha.xlsx", baixar_modelo_planilha, name="baixar_modelo_planilha"),
    path("uploads/lote/<int:lote_id>/json/", upload_lote_progresso_json, name="upload_lote_progresso_json"),
    path("produtos/", produtos_importados, name="produtos_importados"),
    
    path("empresas/<int:empresa_id>/analise-tributaria/", analise_tributaria_list, name="analise_tributaria_list",),
    path("empresas/<int:empresa_id>/analise-tributaria/<int:item_id>/", analise_tributaria_detail,name="analise_tributaria_detail",),
    path("empresas/<int:empresa_id>/analise-tributaria/<int:item_id>/reprocessar/", analise_tributaria_reprocessar, name="analise_tributaria_reprocessar",),
    path("empresas/<int:empresa_id>/analise-tributaria/disparar/", analise_tributaria_disparar, name="analise_tributaria_disparar",),
    path("empresas/<int:empresa_id>/analise-tributaria/fila/<int:fila_id>/retomar/", analise_tributaria_retomar, name="analise_tributaria_retomar",),
    path("empresas/<int:empresa_id>/analise-tributaria/analisar-produto/<int:produto_id>/", analise_tributaria_analisar_produto, name="analise_tributaria_analisar_produto",),
    
    path("empresas/<int:empresa_id>/analise-tributaria/exportar/", analise_tributaria_exportar_xlsx, name="analise_tributaria_exportar_xlsx"),
    path('empresas/excluir/<int:id>/', empresa_excluir, name='empresa_excluir'),
    path("analise-tributaria/<int:empresa_id>/produtos/<int:produto_id>/excluir/", produto_excluir, name="produto_excluir",),
    path("empresas/<int:empresa_id>/analise-tributaria/analisar-item/",analise_tributaria_analisar_item,
    name="analise_tributaria_analisar_item"),
    path("divergencias/", divergencias_fiscais, name="divergencias_fiscais"),

    path("fila-analise/<int:fila_id>/", fila_analise_status, name="fila_analise_status"),
    path("fila-analise/<int:fila_id>/json/", fila_analise_status_json, name="fila_analise_status_json"),
    path("fila-analise/<int:fila_id>/cancelar/", fila_analise_cancelar, name="fila_analise_cancelar"),

]
