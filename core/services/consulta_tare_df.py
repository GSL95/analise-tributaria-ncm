import json
import re
from time import sleep

from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage


URL_BASE = "https://ww1.receita.fazenda.df.gov.br/regimes-especiais/consulta"
URL_TARE = "https://ww1.receita.fazenda.df.gov.br/WPI/api/publica/regimesEspeciais/consulta/Tare"
URL_DOC_TARE = "https://ww1.receita.fazenda.df.gov.br/WPI/api/publica/regimesEspeciais/consulta/DocTare"


# Legenda dos tipos:
# 30 = ATO DECLARATÓRIO - DECRETO 34063/2012 | SUBSTITUTO TRIBUTÁRIO INTERNO
# 35 = Lei nº 5.005/2012
# 49 = DECRETO 39.753/2019 INCLUSÃO | Regime Especial


def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D+", "", cnpj or "")


def consultar_tares_por_cnpj(page, cnpj: str) -> list[dict]:
    payload = {
        "Tipo": "",
        "Numero": "",
        "NumeroAno": "",
        "Situacao": "",
        "Assunto": "",
        "Processo": "",
        "ProcessoAno": "",
        "Cfdf": "",
        "Cnpj": limpar_cnpj(cnpj),
        "RazaoSocial": "",
        "Email": "",
        "Telefone": "",
        "BuscaTextualDocumento": "",
    }

    script = f"""
    return fetch("{URL_TARE}", {{
        method: "POST",
        headers: {{
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json"
        }},
        body: JSON.stringify({json.dumps(payload)})
    }}).then(r => r.text())
    """

    resultado = page.run_js(script)
    return json.loads(resultado)


def consultar_doc_tare(page, co_tipo_tare, numero, ano) -> dict:
    payload = {
        "CoTipoTare": str(co_tipo_tare),
        "Numero": str(numero),
        "Ano": str(ano),
    }

    script = f"""
    return fetch("{URL_DOC_TARE}", {{
        method: "POST",
        headers: {{
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json"
        }},
        body: JSON.stringify({json.dumps(payload)})
    }}).then(r => r.text())
    """
    
    resultado = page.run_js(script)
    return json.loads(resultado)


def extrair_itens_do_documento(dados_doc: dict) -> list[str]:
    html = dados_doc.get("DsDocumento", "")

    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)

    itens = []

    # item XX do Caderno I/II...
    match = re.search(
        r"produtos constantes no item\s+(\d+)",
        texto,
        re.IGNORECASE
    )

    if match:
        return [match.group(1)]

    return []

def consultar_tares_df(cnpj: str, tipos_permitidos: list[int] | None = None) -> list[dict]:
    page = ChromiumPage()

    try:
        page.get(URL_BASE)

        lista_tares = consultar_tares_por_cnpj(page, cnpj)
        resultados = []

        for tare in lista_tares:
            co_tipo_tare = tare.get("CoTipoTare")
            numero = tare.get("NuNumero")
            ano = tare.get("NuNumeroAno")

            if tipos_permitidos and co_tipo_tare not in tipos_permitidos:
                continue

            dados_doc = consultar_doc_tare(page, co_tipo_tare, numero, ano)
            itens = extrair_itens_do_documento(dados_doc)

            print(f"Processando TARE: {co_tipo_tare} - {numero}/{ano} - Itens: {itens}")
            
            resultados.append({
                "empresa": tare.get("NoRazaoSocial"),
                "cfdf": tare.get("NuCfdf"),
                "situacao": tare.get("NoSituacaoTare"),
                "tipo_codigo": co_tipo_tare,
                "tipo_nome": tare.get("NoTipoTare"),
                "assunto": tare.get("NoAssuntoTare"),
                "numero": numero,
                "ano": ano,
                "numero_formatado": tare.get("Numero"),
                "itens": itens,
                "data_publicacao": dados_doc.get("DtPublicacao"),
                "data_inicio_vigencia": dados_doc.get("DtInicioVigencia"),
                "data_assinatura": dados_doc.get("DtAssinatura"),
                "observacao": dados_doc.get("DsObservacao"),
            })

        return resultados

    finally:
        page.quit()