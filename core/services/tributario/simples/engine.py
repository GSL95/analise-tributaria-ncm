from __future__ import annotations

import concurrent.futures

from django.conf import settings
from .tipi_repository import get_tipi_df
from .normalizers import formatar_ncm, parse_decimal, parse_date_br

# por enquanto, mantemos seu serviço atual (CONSULTA_SIMPLES.PY) como backend de consulta
from core.services.apis.consulta_simples import (
    consultar_api_aliquota_diferenciada_icms,
    consultar_api_st_interna,
    consultar_api_st_interestadual,
    consultar_api_pis_cofins,
    consultar_api_beneficios_fiscais_isencao,
    consultar_api_ibs_estadual,
    consultar_api_reforma_tributaria,
)

DECIMAL_FIELDS = (
    "aliquota_icms_retornado",
    "mva",
    "mva_ajustada_4",
    "mva_ajustada_7",
    "mva_ajustada_12",
    "mva_original_st_interestadual",
    "mva_ajustada_4_st_interestadual",
    "mva_ajustada_12_st_interestadual",
)

DATE_FIELDS = (
    "vigencia_inicial",
    "vigencia_inicial_st",
    "vigencia_inicial_st_interestadual",
    "vigencia_inicial_icms",
)

def consultar_tipi(ncm: str) -> str:
    df = get_tipi_df()
    ncm_fmt = formatar_ncm(ncm)
    if not ncm_fmt:
        return "NCM inválido"

    linha = df[df["NCM"] == ncm_fmt]
    if linha.empty:
        return f"NCM {ncm_fmt} não encontrado na TIPI"

    return str(linha["DESCRIÇÃO"].iloc[0])

def _tratar_campos(dados: dict) -> dict:
    for k in DECIMAL_FIELDS:
        dados[k] = parse_decimal(dados.get(k))
    for k in DATE_FIELDS:
        dados[k] = parse_date_br(dados.get(k))
    return dados

def analisar_ncm_unico(
    ncm: str,
    nome_item: str,
    regime_tributario: int,
    atividade_origem: int,
    atividade_destino: int,
    estado: str = "DF",
    estado_destino_st_inter: str = "GO",
) -> dict:
    payload = {
        "nome_item": nome_item,
        "ncm": ncm,
        "estado": estado,
        "id_usuario": settings.LEGISWEB_USER_ID,
        "token": settings.LEGISWEB_TOKEN,
        "modo_busca": 1,
        "regime_tributario_origem": regime_tributario,
        "atividade_origem": atividade_origem,
        "atividade_destino": atividade_destino,
        "aliquota_padrao": 0,
        "estado_destino": estado_destino_st_inter,
    }

    # As 7 chamadas abaixo são independentes entre si (cada uma bate numa
    # rota diferente do legisweb) — rodam em paralelo em vez de sequencial
    # para não pagar 7 round-trips de rede em série por NCM.
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futuro_icms = executor.submit(consultar_api_aliquota_diferenciada_icms, payload)
        futuro_st_int = executor.submit(consultar_api_st_interna, payload)
        futuro_st_inter = executor.submit(consultar_api_st_interestadual, payload)
        futuro_pis_cofins = executor.submit(consultar_api_pis_cofins, payload)
        futuro_beneficio = executor.submit(consultar_api_beneficios_fiscais_isencao, payload)
        futuro_ibs = executor.submit(consultar_api_ibs_estadual, payload)
        futuro_reforma = executor.submit(consultar_api_reforma_tributaria, payload)

        icms = futuro_icms.result() or {}
        st_int = futuro_st_int.result() or {}
        st_inter = futuro_st_inter.result() or {}
        pis_cofins = futuro_pis_cofins.result() or {}
        beneficio_isencao = futuro_beneficio.result()
        dados_ibs = futuro_ibs.result() or {}
        dados_reforma = futuro_reforma.result() or {}

    resultado = {
        "ncm": ncm,
        "nome_item": nome_item,
        "desc_tipi": consultar_tipi(ncm),

        "aliquota_icms_retornado": icms.get("aliquota_icms_retornado", ""),
        "descricao_icms_retornado": icms.get("descricao_icms_retornado", ""),
        "base_legal_icms_retornado": icms.get("base_legal_retornado", ""),
        "vigencia_inicial_icms": icms.get("vigencia_inicial", ""),
        "observacao_icms": icms.get("observacao_icms", ""),
        "cst_icms": ("201 ou 202 ou 500" if st_int.get("cest") != "NÃO TEM ST" else icms.get("cst_icms", "")),

        "descricao_st": st_int.get("descricao_ncm", ""),
        "cest": st_int.get("cest", ""),
        "descricao_ncm_st": st_int.get("descricao_ncm", ""),
        "mva": st_int.get("mva", ""),
        "mva_ajustada_4": st_int.get("mva_ajustada_4", ""),
        "mva_ajustada_7": st_int.get("mva_ajustada_7", ""),
        "mva_ajustada_12": st_int.get("mva_ajustada_12", ""),
        "base_legal_st": st_int.get("base_legal_st", ""),
        "vigencia_inicial_st": st_int.get("vigencia_inicial", ""),
        "observacao_st": st_int.get("observacao", ""),
        "segmentos_st": st_int.get("segmento", ""),

        "cest_interestadual": st_inter.get("cest_st_interestadual", ""),
        "descricao_st_interestadual": st_inter.get("descricao_st_interestadual", ""),
        "segmento_st_interestadual": st_inter.get("segmento_st_interestadual", ""),
        
        "mva_st_interestadual": st_inter.get("mva_original_st_interestadual", ""),
        "mva_ajustada_4_st_interestadual": st_inter.get("mva_ajustada_4_st_interestadual", ""),
        "mva_ajustada_12_st_interestadual": st_inter.get("mva_ajustada_12_st_interestadual", ""),
        "vigencia_inicial_st_interestadual": st_inter.get("vigencia_inicial_st_interestadual", ""),
        "base_legal_st_interestadual": st_inter.get("base_legal_st_interestadual", ""),
        "base_legal_interna_st_interestadual": st_inter.get("base_legal_int_st_interestadual", ""),
        "aplicabilidade_st_interestadual": st_inter.get("aplicabilidade_st_interestadual", ""),
        "nao_aplicabilidade_st_interestadual": st_inter.get("nao_aplicabilidade_st_interestadual", ""),

        "beneficio_isencao": beneficio_isencao,

        "cst_pis": pis_cofins.get("cst_simples", ""),
        "base_legal_pis_cofins": pis_cofins.get("base_legal", ""),

        "cst_cbs": pis_cofins.get("cst_cbs", ""),
        "aliquota_cbs": pis_cofins.get("aliquota_cbs", ""),
        "base_legal_cbs": pis_cofins.get("base_legal_cbs", ""),

        "aliquota_ibs_estadual": dados_ibs.get("aliquota_ibs_estadual", ""),
        "base_legal_ibs_estadual": dados_ibs.get("base_legal_ibs_estadual", ""),
        "descricao_ibs_estadual": dados_ibs.get("descricao_ibs_estadual", ""),

        "reforma_tipo_beneficio": dados_reforma.get("reforma_tipo_beneficio", ""),
        "reforma_reducoes": dados_reforma.get("reforma_reducoes", []),
        "reforma_creditos": dados_reforma.get("reforma_creditos", []),
        "reforma_aplicabilidade": dados_reforma.get("reforma_aplicabilidade", ""),
        "reforma_base_legal": dados_reforma.get("reforma_base_legal", ""),
    }

    return _tratar_campos(resultado)
