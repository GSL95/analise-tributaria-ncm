from __future__ import annotations

from dataclasses import dataclass
from core.services.apis.consulta_lucro_real import ncm_eh_valido, consultar_dados_ncm
from django.conf import settings


# importe (ou mova) do seu script as funções necessárias:
# - ncm_eh_valido
# - consultar_dados_ncm  (que chama ICMS/ST/PIS-COFINS/TIPI/Redução)
# Observação: aqui a ideia é reutilizar as funções, só “empacotar” num engine.

@dataclass(frozen=True)
class ContextoLucroReal:
    ncm: str
    nome_item: str
    uf_origem: str
    uf_destino: str
    atividade_origem: int
    atividade_destino: int
    modo_busca: int = 1
    aliquota_padrao: int = 0


def analisar_ncm_unico_lucro_real(
    *,
    ncm: str,
    nome_item: str,
    uf_origem: str = "DF",
    uf_destino: str = "GO",
    atividade_origem: int = 4,
    atividade_destino: int = 4,
    modo_busca: int = 1,
    aliquota_padrao: int = 0,
    tipi_df=None,
    regime = None,
) -> dict:
    """
    Retorna um dict com a análise (mesmo formato do seu consultar_dados_ncm),
    SEM side-effects (sem Excel, sem print, sem loop).
    """

    # monte exatamente o dicionário que suas funções esperam hoje
    dados_para_consultar = {
        "nome_item": nome_item,
        "ncm": str(ncm).strip().replace(".", "")[:8].zfill(8),
        "estado": uf_origem,
        "modo_busca": modo_busca,
        "regime_tributario_origem": regime,
        "atividade_origem": atividade_origem,
        "atividade_destino": atividade_destino,
        "aliquota_padrao": aliquota_padrao,
        "id_usuario": settings.LEGISWEB_USER_ID,
        "token": settings.LEGISWEB_TOKEN,
    }

    # validação (se você quiser manter sua regra atual)
    if tipi_df is not None:
        # ncm_eh_valido do seu script
        if not ncm_eh_valido(dados_para_consultar["ncm"]):
            return {
                "status": "ERRO",
                "erro": "NCM INVÁLIDO",
            }

    # consultar_dados_ncm do seu script
    resultado = consultar_dados_ncm(dados_para_consultar)

    # padronize status
    resultado["status"] = "OK"
    return resultado
