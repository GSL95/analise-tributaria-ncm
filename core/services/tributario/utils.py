import re
import string

import requests


def sanitize(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = text.strip()
    return text


def jaccard_similarity(str1: str, str2: str) -> float:
    str1 = re.sub(r"[^\w\s]", "", str1.lower())
    str2 = re.sub(r"[^\w\s]", "", str2.lower())
    set1 = set(str1.split())
    set2 = set(str2.split())
    union = set1.union(set2)
    if not union:
        return 0.0
    return len(set1.intersection(set2)) / len(union)


_CBS_FALLBACK = {
    "cst_cbs": "000 - Tributação Integral",
    "aliquota_cbs": "0.9000",
    "base_legal_cbs": "Artigo 346 da Lei Complementar Nº 214 DE 16/01/2025",
}


def _extrair_cbs_de_aliquota_padrao(trib_list: list) -> dict:
    for trib in trib_list:
        for ap in (trib.get("aliquota_padrao") or []):
            if ap.get("tributo") == "CBS":
                return {
                    "cst_cbs": ap.get("cst", "000 - Tributação Integral"),
                    "aliquota_cbs": ap.get("valor", "0.9000"),
                    "base_legal_cbs": ap.get(
                        "desc_base_legal",
                        "Artigo 346 da Lei Complementar Nº 214 DE 16/01/2025",
                    ),
                }
    return dict(_CBS_FALLBACK)


def consultar_api_ibs_estadual(dados_ncm: dict) -> dict:
    estado = dados_ncm["estado"]
    id_usuario = dados_ncm["id_usuario"]
    token = dados_ncm["token"]

    _fallback = {
        "aliquota_ibs_estadual": "",
        "base_legal_ibs_estadual": "",
        "descricao_ibs_estadual": "",
    }

    url = f"https://www.legisweb.com.br/api/aliquota-padrao/?estado={estado}&c={id_usuario}&t={token}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        dados = resp.json()
    except Exception as exc:
        print(f"[ERRO IBS Estadual] {exc}")
        return _fallback

    if dados.get("registros", 0) == 0:
        return _fallback

    respostas = dados.get("resposta", [])
    if isinstance(respostas, dict):
        respostas = [respostas]

    for item in respostas:
        if item.get("tributo") == "IBS Estadual":
            return {
                "aliquota_ibs_estadual": item.get("aliquota", ""),
                "base_legal_ibs_estadual": item.get("base_legal", ""),
                "descricao_ibs_estadual": item.get("descricao", ""),
            }
    return _fallback


def consultar_api_reforma_tributaria(dados_ncm: dict) -> dict:
    ncm = dados_ncm["ncm"]
    id_usuario = dados_ncm["id_usuario"]
    token = dados_ncm["token"]

    _fallback = {
        "reforma_tipo_beneficio": "",
        "reforma_reducoes": [],
        "reforma_creditos": [],
        "reforma_aplicabilidade": "",
        "reforma_base_legal": "",
    }

    url = (
        f"https://www.legisweb.com.br/api/reforma_tributaria_beneficios/"
        f"?tipo-busca=1&ncm={ncm}&c={id_usuario}&t={token}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        dados = resp.json()
    except Exception as exc:
        print(f"[ERRO Reforma Tributária] {exc}")
        return _fallback

    if dados.get("registros", 0) == 0:
        return _fallback

    respostas = dados.get("resposta", [])
    if not respostas:
        return _fallback

    primeiro = respostas[0] if isinstance(respostas, list) else respostas
    return {
        "reforma_tipo_beneficio": (primeiro.get("beneficio") or {}).get("tipo_beneficio", ""),
        "reforma_reducoes": primeiro.get("reducoes", []),
        "reforma_creditos": primeiro.get("creditos", []),
        "reforma_aplicabilidade": (primeiro.get("detalhes") or {}).get("aplicabilidade", ""),
        "reforma_base_legal": (primeiro.get("detalhes") or {}).get("base_legal", ""),
    }
