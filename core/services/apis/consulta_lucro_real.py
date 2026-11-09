import concurrent.futures
import re

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

# Sessão compartilhada com pool de conexões: reaproveita conexões keep-alive
# para o legisweb.com.br em vez de abrir uma conexão TCP/TLS nova a cada
# requisição (várias chamadas independentes são feitas por NCM analisado).
SESSION = requests.Session()
_ADAPTER = HTTPAdapter(pool_connections=20, pool_maxsize=20)
SESSION.mount("https://", _ADAPTER)
SESSION.mount("http://", _ADAPTER)

from core.services.tributario.lucro_real.tipi_repository import get_tipi_df
from core.services.tributario.utils import (
    sanitize,
    jaccard_similarity,
    _extrair_cbs_de_aliquota_padrao,
    consultar_api_ibs_estadual,
    consultar_api_reforma_tributaria,
)

def aliquotas_padrao_pis_cofins(regime: int) -> tuple[str, str]:
    """
    regime:
      1 = PRESUMIDO (cumulativo)
      2 = REAL (não-cumulativo)
      3 = SN (decisão: aqui vou tratar como cumulativo pra fallback)
    """
    if regime == 2:  # REAL
        return "1.65%", "7.60%"
    # PRESUMIDO ou SN ou desconhecido -> cumulativo (fallback)
    return "0.65%", "3.00%"

def fallback_padrao_pis_cofins(regime: int) -> dict:
    aliq_pis, aliq_cofins = aliquotas_padrao_pis_cofins(regime)
    return {
        "cst_pis": "01 - Operação Tributável com Alíquota Básica",
        "aliquota_pis": aliq_pis,
        "cst_cofins": "01 - Operação Tributável com Alíquota Básica",
        "aliquota_cofins": aliq_cofins,
        "base_legal_pis": "Lei nº 9.715/1998, art. 8º, inciso I",
        "base_legal_cofins": "Lei nº 9.718/1998, art. 8º",
        "aplicablidade": "Lei nº 9.718/1998, art. 8º; Lei nº 9.715/1998, art. 8º, inciso I",
        "cst_cbs": "000 - Tributação Integral",
        "aliquota_cbs": "0.9000",
        "base_legal_cbs": "Artigo 346 da Lei Complementar Nº 214 DE 16/01/2025",
    }


def ncm_eh_valido(ncm):
    """Verifica se o NCM é válido com base em regras numéricas e presença na TIPI"""
    ncm = str(ncm).strip().replace('.', '').zfill(8)
    
    # Regras básicas de formato
    if not ncm.isdigit() or len(ncm) != 8:
        return False

    # NCM todo zero ou inválido conhecido
    if ncm in ['00000000', '0000000', '000000', '00000', '0000', '000', '00', '0']:
        return False

    # Verifica se está na tabela TIPI (opcional, mas reforça a verificação)
    ncm_formatado = f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}"
    return True

# CONSULTA API ALIQUOTA DIFERENCIADA ICMS
def consultar_api_aliquota_diferenciada_icms(dados_ncm):
    ncm = dados_ncm['ncm']
    estado = dados_ncm['estado']
    id_usuario = dados_ncm['id_usuario']
    token = dados_ncm['token']
    modo_busca = dados_ncm['modo_busca']
    url_aliq_icms = f'https://www.legisweb.com.br/api/icms/?ncm={ncm}&estado={estado}&c={id_usuario}&t={token}&modo_busca={modo_busca}'
    
    ncms_isentos = {
        "4901": "Livros, brochuras e impressos semelhantes, mesmo em folhas soltas - Em folhas soltas, mesmo dobradas",
        "49011000": "Livros, brochuras e impressos semelhantes, mesmo em folhas soltas - Outros: Dicionários e enciclopédias, mesmo em fascículos",
        "49019": "Livros, brochuras e impressos semelhantes, mesmo em folhas soltas - Outros: Outros",
        "49019100": "Jornais e publicações periódicas, impressos, mesmo ilustrados ou que contenham publicidade - Que se publiquem pelo menos quatro vezes por semana",
        "49019900": "Jornais e publicações periódicas, impressos, mesmo ilustrados ou que contenham publicidade - Que se publiquem pelo menos quatro vezes por semana: Com publicidade",
        "4902": "Jornais e publicações periódicas, impressos, mesmo ilustrados ou que contenham publicidade - Outros",
        "49021000": "Jornais e publicações periódicas, impressos, mesmo ilustrados ou que contenham publicidade - Outros: Com publicidade",
        "49029000": "Música manuscrita ou impressa, ilustrada ou não, mesmo encadernada",
        "49030000": "Obras cartográficas de qualquer espécie, incluindo as cartas murais, as plantas topográficas e os globos, impressas - Outras",
        "49040000": "Obras cartográficas de qualquer espécie, incluindo as cartas murais, as plantas topográficas e os globos, impressas - Outras",
        "4905": "Obras cartográficas de qualquer espécie, incluindo as cartas murais, as plantas topográficas e os globos, impressas - Outras",
        "49052000": "Obras cartográficas de qualquer espécie, incluindo as cartas murais, as plantas topográficas e os globos, impressas - Outras",
        "49059000": "Obras cartográficas de qualquer espécie, incluindo as cartas murais, as plantas topográficas e os globos, impressas - Outras",
    }
    
    # Isentos constitucionais – nem chama API
    if ncm in ncms_isentos:
        resposta_api_icms = {
            'ncm_retornado' : ncm,
            'aliquota_icms_retornado' : 0,
            'descricao_icms_retornado' : 'Aliquota Zero ou isenção com base no Art. 150, VI, "d", da CF.',
            'base_legal_retornado' : 'Artigo 150, inciso VI, alínea d, da Constituição Federal.',
            'cst_icms' : '040',
            'vigencia_inicial' : '?',
            'observacao_icms' : '?'
        }
        return resposta_api_icms

    try:
        resposta_aliq_icms = SESSION.get(url_aliq_icms, timeout=(5, 20))
        resposta_aliq_icms.raise_for_status()
        retorno_aliq_icms = resposta_aliq_icms.json()
        print(retorno_aliq_icms)
    except (requests.Timeout, requests.RequestException) as e:
        print(f"[ERRO ICMS] Falha ao consultar API para NCM {ncm}: {e}")
        # Fallback: alíquota interna padrão DF
        return {
            'ncm_retornado' : ncm,
            'aliquota_icms_retornado' : 20.00,
            'descricao_icms_retornado' : 'Alíquota Interna Padrão para Distrito Federal (fallback por erro na API).',
            'base_legal_retornado' : 'Base Legal: Alínea "c", Inciso II, Art. 18º da Lei Nº 1254 DE 08/11/1996',
            'cst_icms' : '000',
            'vigencia_inicial' : '22/01/2024',
            'observacao_icms' : 'Para datas anteriores a 22/01/2024, a alíquota padrão era de 18%.'
        }

    # Verifica se existem registros
    if retorno_aliq_icms.get('registros', 0) == 0:
        resposta_api_icms = {
            'ncm_retornado' : ncm,
            'aliquota_icms_retornado' : 20.00,
            'descricao_icms_retornado' : 'Alíquota Interna Padrão para Distrito Federal:',
            'base_legal_retornado' : 'Base Legal: Alínea "c", Inciso II, Art. 18º da Lei Nº 1254 DE 08/11/1996',
            'cst_icms' : '000',
            'vigencia_inicial' : '22/01/2024',
            'observacao_icms' : 'Para datas anteriores a Vigencia de 22/01/2024 a aliquota padrão era de 18%'
        }
        return resposta_api_icms
    else:
        # Pegando a última resposta
        resposta = retorno_aliq_icms['resposta'][-1]        
        resposta_api_icms = {
            'ncm_retornado' : resposta.get('ncm', ncm),
            'aliquota_icms_retornado' : resposta.get('aliquota', 'Alíquota não disponível'),
            'descricao_icms_retornado' : resposta.get('descricao', 'Descrição não disponível'),
            'base_legal_retornado' : resposta.get('base_legal', 'Base legal não disponível'),
            'vigencia_inicial' : resposta.get('vigencia_inicial', 'Vigência inicial não disponível'),
            'observacao_icms' : resposta.get('observacao', 'Observação não disponível'),
            'cst_icms' : '000',
        }
        return resposta_api_icms
    
# CONSULTA API DE SUBSTITUIÇÃO TRIBUTARIA INTERESTADUAL
def consultar_api_st_interestadual(dados_ncm):
    atividade_origem = dados_ncm['atividade_origem']
    ncm = dados_ncm['ncm']
    estado = dados_ncm['estado']
    id_usuario = dados_ncm['id_usuario']
    token = dados_ncm['token']
    nome_item = dados_ncm['nome_item']

    atividade_destino = dados_ncm.get('atividade_destino', 1)
    # destinacao_mercadoria=4 quando destino é varejista; 1 para os demais
    destinacao_mercadoria = 4 if atividade_destino == 4 else 1

    url_api_st_interestadual = (
        f"https://www.legisweb.com.br/api/st-interestadual/?ncm={ncm}"
        f"&estado_origem={estado}&estado_destino=GO&destinacao_mercadoria={destinacao_mercadoria}"
        f"&c={id_usuario}&t={token}"
    )

    if atividade_origem == 1:
        buscar_por_atividade = ["ATACADISTAS", "ATACADISTA", "ATACADO"]
    elif atividade_origem == 2:
        buscar_por_atividade = ["DISTRIBUIDORES", "DISTRIBUIDOR", "DISTRIBUIÇÃO"]
    elif atividade_origem == 3:
        buscar_por_atividade = ["FABRICANTES", "INDUSTRIAS", "INDUSTRIAL", "INDUSTRIA", "FABRICANTE"]
    elif atividade_origem == 4:
        buscar_por_atividade = ["VAREJISTAS", "VAREJISTA", "VAREJO"]
    else:
        buscar_por_atividade = []

    def _retorno_sem_st(motivo="NÃO TEM ST INTERESTADUAL"):
        return {
            'cest_interestadual' : motivo,
            'descricao_st_interestadual' : motivo,
            'observacao_st_interestadual' : motivo,
            'segmento_st_interestadual' : motivo,
            'aliquota_interna_st_interestadual' : motivo,
            'aliquota_interestadual_st_interestadual' : motivo,
            'mva_st_interestadual' : motivo,
            'mva_ajustada_st_interestadual' : motivo,
            'mva_ajustada_4_st_interestadual' : motivo,
            'vigencia_inicial_st_interestadual' : motivo,
            'base_legal_st_interestadual' : motivo,
            'aplicabilidade_st_interestadual' : motivo,
            'nao_aplicabilidade_st_interestadual' : motivo,
        }

    try:
        resposta_api_st_interestadual = SESSION.get(url_api_st_interestadual, timeout=(5, 20))
        resposta_api_st_interestadual.raise_for_status()
        retorno_api_st_interestadual = resposta_api_st_interestadual.json()
    except (requests.Timeout, requests.RequestException) as e:
        print(f"[ERRO ST-INTER] Falha ao consultar ST interestadual para NCM {ncm}: {e}")
        return _retorno_sem_st("ERRO NA CONSULTA ST INTERESTADUAL")

    if retorno_api_st_interestadual.get('registros', 0) == 0:
        print("Nenhum registro encontrado NA API DE CONSULTA A ST INTERESTADUAL.")
        return _retorno_sem_st()

    respostas = retorno_api_st_interestadual['resposta']
    maior_similaridade = -1
    resposta_mais_similar = None

    # 1ª passada: filtra por atividade
    for resposta in respostas:
        descricao = resposta.get('descricao', '')
        if any(sanitize(atividade) in sanitize(descricao) for atividade in buscar_por_atividade):
            similaridade = jaccard_similarity(nome_item, descricao) * 100
            if similaridade > maior_similaridade:
                maior_similaridade = similaridade
                resposta_mais_similar = resposta

    # Se não achou por atividade, pega maior similaridade geral
    if resposta_mais_similar is None:
        maior_similaridade = -1
        for resposta in respostas:
            descricao = resposta.get('descricao', '')
            similaridade = jaccard_similarity(nome_item, descricao) * 100
            if similaridade > maior_similaridade:
                maior_similaridade = similaridade
                resposta_mais_similar = resposta

    if not resposta_mais_similar:
        return _retorno_sem_st("ST INTERESTADUAL NÃO ENCONTRADA")

    r = resposta_mais_similar
    return {
        'cest_interestadual' : r.get('cest', ''),
        'descricao_st_interestadual' : r.get('descricao', ''),
        'observacao_st_interestadual' : r.get('observacao', ''),
        'segmento_st_interestadual' : r.get('segmento', ''),
        'aliquota_interna_st_interestadual' : r.get('aliquota_interna', ''),
        'aliquota_interestadual_st_interestadual' : r.get('aliquota_interestadual', ''),
        'mva_st_interestadual' : r.get('mva', ''),
        'mva_ajustada_st_interestadual' : r.get('mva_ajustada', ''),
        'mva_ajustada_4_st_interestadual' : r.get('mva_ajustada_4', ''),
        'vigencia_inicial_st_interestadual' : r.get('vigencia_inicial', ''),
        'base_legal_st_interestadual' : r.get('base_legal_st', ''),
        'aplicabilidade_st_interestadual' : r.get('aplicabilidade', ''),
        'nao_aplicabilidade_st_interestadual' : r.get('nao_aplicabilidade', ''),
    }

# CONSULTA API SUBSTITUIÇÃO TRIBUTARIA INTERNA
def consultar_api_st_interna(dados_ncm):
    maior_similaridade = 0
    resposta_mais_similar = None
    atividade_origem = dados_ncm['atividade_origem']
    ncm = dados_ncm['ncm']
    estado = dados_ncm['estado']
    id_usuario = dados_ncm['id_usuario']
    token = dados_ncm['token']
    nome_item = dados_ncm['nome_item']

    url_api_st_interna = (
        f'https://www.legisweb.com.br/api/st-interna/?ncm={ncm}&estado={estado}'
        f'&c={id_usuario}&t={token}'
    )

    if atividade_origem == 1:
        buscar_por_atividade = "ATACADISTAS"
    elif atividade_origem == 2:
        buscar_por_atividade = "DISTRIBUIDORES"
    elif atividade_origem == 3:
        buscar_por_atividade = "INDÚSTRIA"
    elif atividade_origem == 4:
        buscar_por_atividade = "VAREJISTAS"
    else:
        buscar_por_atividade = ""

    def _retorno_sem_st(motivo="NÃO TEM ST"):
        return {
            'descricao' : motivo,
            'cest' : motivo,
            'descricao_ncm' : motivo,
            'mva' : motivo,
            'mva_ajustada_4' : motivo,
            'mva_ajustada_7' : motivo,
            'mva_ajustada_12' : motivo,
            'base_legal_st' : motivo,
            'vigencia_inicial' : motivo,
            'observacao' : motivo,
            'segmento' : motivo,
        }

    try:
        resposta_api_st_interna = SESSION.get(url_api_st_interna, timeout=(5, 20))
        resposta_api_st_interna.raise_for_status()
        retorno_api_st_interna = resposta_api_st_interna.json()
    except (requests.Timeout, requests.RequestException) as e:
        print(f"[ERRO ST-INTERNA] Falha ao consultar ST interna para NCM {ncm}: {e}")
        return _retorno_sem_st("ERRO NA CONSULTA ST INTERNA")

    # Verificando se existem registros
    if retorno_api_st_interna.get('registros', 0) == 0:
        return _retorno_sem_st()
    
    print(50*"-")
    print("Resposta mais similar encontrada na API de ST Interna:")
    print(retorno_api_st_interna)
    print(50*"-")

    respostas = retorno_api_st_interna['resposta']

    # Iterando corretamente sobre a lista de respostas
    for resposta in respostas:
        descricao = resposta.get('descricao', '')
        if buscar_por_atividade and buscar_por_atividade in descricao:
            similaridade = jaccard_similarity(nome_item, descricao)
            if similaridade > maior_similaridade:
                maior_similaridade = similaridade
                resposta_mais_similar = resposta

    # Se não achou por atividade, pega a última ou a mais genérica
    if resposta_mais_similar is None:
        resposta_mais_similar = respostas[-1]
        


    descricao = resposta_mais_similar.get('descricao', '')
    cest = resposta_mais_similar.get('cest', 'não tem cest')
    descricao_ncm = resposta_mais_similar.get('descricao', 'Descrição não disponível')
    mva = resposta_mais_similar.get('mva', '')
    mva_ajustada_4 = resposta_mais_similar.get('mva_ajustada_4', '')
    mva_ajustada_7 = resposta_mais_similar.get('mva_ajustada_7', '')
    mva_ajustada_12 = resposta_mais_similar.get('mva_ajustada_12', '')
    base_legal_st = resposta_mais_similar.get('base_legal_st', 'Base legal não disponível')
    observacao = resposta_mais_similar.get('observacao', '')
    vigencia_inicial = resposta_mais_similar.get('vigencia_inicial', '')
    segmento = resposta_mais_similar.get('segmento', '')

    dados_st = {
        'descricao' : descricao,
        'cest' : cest,
        'descricao_ncm' : descricao_ncm,
        'mva' : mva,
        'mva_ajustada_4' : mva_ajustada_4,
        'mva_ajustada_7' : mva_ajustada_7,
        'mva_ajustada_12' : mva_ajustada_12,
        'base_legal_st' : base_legal_st,
        'vigencia_inicial' : vigencia_inicial,
        'observacao' : observacao,
        'segmento' : segmento,
    }

    return dados_st

# CONSULTA API DE PIS E COFINS
def consultar_api_pis_cofins(dados_ncm: dict, dados_tipi: dict) -> dict:
    ncm = dados_ncm["ncm"]
    id_usuario = dados_ncm["id_usuario"]
    token = dados_ncm["token"]
    regime_tributario_origem = int(dados_ncm["regime_tributario_origem"])
    atividade_origem = dados_ncm["atividade_origem"]
    atividade_destino = dados_ncm["atividade_destino"]
    aliquota_padrao = dados_ncm["aliquota_padrao"]
    excecao_num = dados_tipi.get('ex', '')
    
    # Trata EX
    if pd.notna(excecao_num) and str(excecao_num).strip() != '':
        excecao_num = str(excecao_num).strip()
        print(f"[INPUT] EXCEÇÃO NUM: {excecao_num}")
    else:
        excecao_num = ''
        print("[INPUT] EXCEÇÃO NUM: vazio")

    print(f"[INPUT] NCM: {ncm}")
    print(f"[INPUT] Regime: {regime_tributario_origem}")
    print(f"[INPUT] Atividade Origem: {atividade_origem}")
    print(f"[INPUT] Atividade Destino: {atividade_destino}")

    aliq_pis_padrao, aliq_cofins_padrao = aliquotas_padrao_pis_cofins(regime_tributario_origem)

    url_aliq_pis_cofins = (
        f"https://www.legisweb.com.br/api/piscofins/?ncm={ncm}&c={id_usuario}&t={token}"
        f"&regime_tributario_origem={regime_tributario_origem}&atividade_origem={atividade_origem}"
        f"&atividade_destino={atividade_destino}&aliquota_padrao={aliquota_padrao}"
    )
    if excecao_num:
        url_aliq_pis_cofins += f"&excecao_num={excecao_num}"

    try:
        resposta = SESSION.get(url_aliq_pis_cofins, timeout=10)
        resposta.raise_for_status()
        retorno = resposta.json()
    except Exception as e:
        print(f"Erro na requisição PIS/COFINS: {e}")
        return fallback_padrao_pis_cofins(regime_tributario_origem)

    if retorno.get("registros", 0) == 0:
        print("caiu em 0 registros")
        return fallback_padrao_pis_cofins(regime_tributario_origem)

    resposta_list = retorno.get("resposta", []) or []
    resposta_obj = resposta_list[0] if resposta_list else {}

    # Modelo antigo: 2 respostas separadas (PIS e COFINS)
    if retorno.get("registros") == 2 and len(resposta_list) == 2:
        try:
            dados_pis = resposta_list[0] or {}
            dados_cofins = resposta_list[1] or {}
            return {
                "cst_pis": dados_pis.get("cst", "01 - Operação Tributável com Alíquota Básica"),
                "aliquota_pis": (dados_pis.get("valor") or aliq_pis_padrao),
                "base_legal_pis": dados_pis.get("desc_base_legal", ""),
                "cst_cofins": dados_cofins.get("cst", "01 - Operação Tributável com Alíquota Básica"),
                "aliquota_cofins": (dados_cofins.get("valor") or aliq_cofins_padrao),
                "base_legal_cofins": dados_cofins.get("desc_base_legal", ""),
                "aplicablidade": "Lei nº 9.718/1998, art. 8º; Lei nº 9.715/1998, art. 8º, inciso I",
            }
        except Exception:
            pass  # se der erro, cai na lógica abaixo

    aplicabilidade = resposta_obj.get("aplicabilidade", "") or ""
    soup = BeautifulSoup(aplicabilidade, "html.parser")
    aplicabilidade_limpa = soup.get_text().strip()

    # Benefícios indesejados (não incluir "" — "" in any_str é sempre True)
    beneficios_indesejados = ["RECINE", "RECAP", "REPAS"]
    if beneficios_indesejados and any(b in aplicabilidade_limpa.upper() for b in beneficios_indesejados):
        print("CAIU EM BENEFICIOS INDESEJADOS")
        return fallback_padrao_pis_cofins(regime_tributario_origem)

    tribs = resposta_obj.get("trib", []) or []

    # Identifica PIS e COFINS pelo campo "tributo" (não por posição)
    pis = next((t for t in tribs if t.get("tributo") == "Pis"), tribs[0] if tribs else {})
    cofins = next((t for t in tribs if t.get("tributo") == "Cofins"), tribs[1] if len(tribs) > 1 else {})

    dados_cbs = _extrair_cbs_de_aliquota_padrao(tribs)

    return {
        "cst_pis": pis.get("cst_pis", "01 - Operação Tributável com Alíquota Básica"),
        "aliquota_pis": (pis.get("valor") or aliq_pis_padrao),
        "cst_cofins": cofins.get("cst_cofins", "01 - Operação Tributável com Alíquota Básica"),
        "aliquota_cofins": (cofins.get("valor") or aliq_cofins_padrao),
        "aplicablidade": aplicabilidade_limpa,
        **dados_cbs,
    }


def consultar_api_beneficios_fiscais_reducao(dados_ncm):
    nome_item = dados_ncm['nome_item']
    ncm = dados_ncm['ncm']
    estado = dados_ncm['estado']
    id_usuario = dados_ncm['id_usuario']
    token = dados_ncm['token']
    
    url_api = f'https://www.legisweb.com.br/api/beneficio-fiscal/?estado={estado}&c={id_usuario}&t={token}&categoria=2&ncm={ncm}'
    
    try:
        resposta = SESSION.get(url_api, timeout=10)
        resposta.raise_for_status()
        dados_json = resposta.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na requisição para: {url_api}")
        print(f"Erro: {e}")
        return montar_reducao_padrao("ERRO NA CONSULTA")
    except ValueError:
        print(f"❌ Erro ao decodificar JSON da resposta para: {url_api}")
        print("Resposta:", resposta.text[:300])
        return montar_reducao_padrao("RESPOSTA INVÁLIDA")

    if dados_json.get('registros', 0) == 0:
        return montar_reducao_padrao("NÃO TEM REDUÇÃO")
    
    try:
        resposta = dados_json['resposta'][0]
        descricao_reducao = resposta['descricao']
        reducoes = resposta.get('reducoes', [])
        
        # Interna
        reducao_interna = reducoes[0]
        operacao_interna = reducao_interna['operacao']
        base_legal_reducao_interna = reducao_interna['desc_base_legal']
        descricao_interna = reducao_interna['descricao']
        aliquota_reducao_interna = descricao_interna.split(' ')[-1]
        codigo_beneficio_interno = resposta.get('cbenef', 'N/A')

        # Externa
        if len(reducoes) > 1:
            reducao_externa = reducoes[1]
            operacao_externa = reducao_externa['operacao']
            base_legal_reducao_externa = reducao_externa['desc_base_legal']
            descricao_externa = reducao_externa['descricao']
            aliquota_reducao_externa = descricao_externa.split(' ')[-1]
        else:
            operacao_externa = base_legal_reducao_externa = descricao_externa = aliquota_reducao_externa = 'NÃO TEM REDUÇÃO INTERESTADUAL'

        return {
            'descricao_reducao': descricao_reducao,
            'cbenef': codigo_beneficio_interno,
            'operacao_interna': operacao_interna,
            'base_legal_reducao_interna': base_legal_reducao_interna,
            'descricao_interna': descricao_interna,
            'aliquota_reducao_interna': aliquota_reducao_interna,
            'operacao_externa': operacao_externa,
            'base_legal_reducao_externa': base_legal_reducao_externa,
            'descricao_externa': descricao_externa,
            'aliquota_reducao_externa': aliquota_reducao_externa
        }
    except Exception as e:
        print("❌ Erro ao processar estrutura de dados da API:", e)
        return montar_reducao_padrao("ERRO NA ESTRUTURA")

def montar_reducao_padrao(motivo='NÃO TEM REDUÇÃO'):
    return {
        'descricao_reducao': motivo,
        'operacao_interna': motivo,
        'base_legal_reducao_interna': motivo,
        'descricao_interna': motivo,
        'aliquota_reducao_interna': motivo,
        'operacao_externa': motivo,
        'base_legal_reducao_externa': motivo,
        'descricao_externa': motivo,
        'aliquota_reducao_externa': motivo,
        'cbenef': motivo,
    }

# CONSOME AS APIS NECESSARIAS
def consultar_dados_ncm(dados_ncm):

    tipi_df = get_tipi_df()
    dados_tipi = consultar_tipi(dados_ncm, tipi_df)

    # As 6 chamadas abaixo são independentes entre si (cada uma bate numa
    # rota diferente do legisweb) — rodam em paralelo em vez de sequencial
    # para não pagar 6 round-trips de rede em série por NCM.
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futuro_icms = executor.submit(consultar_api_aliquota_diferenciada_icms, dados_ncm)
        futuro_st_interna = executor.submit(consultar_api_st_interna, dados_ncm)
        futuro_st_interestadual = executor.submit(consultar_api_st_interestadual, dados_ncm)
        futuro_pis_cofins = executor.submit(consultar_api_pis_cofins, dados_ncm, dados_tipi)
        futuro_reducao = executor.submit(consultar_api_beneficios_fiscais_reducao, dados_ncm)
        futuro_ibs = executor.submit(consultar_api_ibs_estadual, dados_ncm)
        futuro_reforma = executor.submit(consultar_api_reforma_tributaria, dados_ncm)

        dados_aliquota_icms = futuro_icms.result()
        dados_st_interna = futuro_st_interna.result()
        dados_st_interestadual = futuro_st_interestadual.result()
        dados_pis_cofins = futuro_pis_cofins.result()
        dados_reducao = futuro_reducao.result()
        dados_ibs = futuro_ibs.result()
        dados_reforma = futuro_reforma.result()

    desc_tipi = dados_tipi.get('descricao', 'Descrição TIPI não disponível')
    print('Chegou aqui desc tipi')
    
    dados_consultados = {
        'ncm' : dados_ncm['ncm'],
        'nome_item' : dados_ncm['nome_item'],
        'desc_tipi' : desc_tipi,
        
        'aliquota_icms_retornado': dados_aliquota_icms['aliquota_icms_retornado'],
        'descricao_icms_retornado': dados_aliquota_icms['descricao_icms_retornado'],
        'base_legal_icms_retornado': dados_aliquota_icms['base_legal_retornado'],
        'vigencia_inicial_icms' : dados_aliquota_icms['vigencia_inicial'],
        'observacao_icms' : dados_aliquota_icms['observacao_icms'],
        'cst_icms' : '010 ou 030 ou 070' if dados_st_interna['cest'] != 'NÃO TEM ST' else dados_aliquota_icms['cst_icms'],
        
        'descricao_st': dados_st_interna['descricao'],
        'cest': dados_st_interna['cest'],
        'descricao_ncm_st': dados_st_interna['descricao_ncm'],
        'mva': dados_st_interna['mva'],
        'mva_ajustada_4': dados_st_interna['mva_ajustada_4'],
        'mva_ajustada_7': dados_st_interna['mva_ajustada_7'],
        'mva_ajustada_12': dados_st_interna['mva_ajustada_12'],
        'base_legal_st': dados_st_interna['base_legal_st'],
        'vigencia_inicial_st': dados_st_interna['vigencia_inicial'],
        'observacao_st': dados_st_interna['observacao'],
        'segmentos_st': dados_st_interna['segmento'],
        
        'cest_interestadual' : dados_st_interestadual['cest_interestadual'],
        'descricao_st_interestadual' : dados_st_interestadual['descricao_st_interestadual'],
        'segmento_st_interestadual' : dados_st_interestadual['segmento_st_interestadual'],
        
        'mva_st_interestadual' : dados_st_interestadual['mva_st_interestadual'],
        'mva_ajustada_st_interestadual' : dados_st_interestadual['mva_ajustada_st_interestadual'],
        'mva_ajustada_4_st_interestadual' : dados_st_interestadual['mva_ajustada_4_st_interestadual'],
        'vigencia_inicial_st_interestadual' : dados_st_interestadual['vigencia_inicial_st_interestadual'],
        'base_legal_st_interestadual' : dados_st_interestadual['base_legal_st_interestadual'],
        'aplicabilidade_st_interestadual' : dados_st_interestadual['aplicabilidade_st_interestadual'],
        'nao_aplicabilidade_st_interestadual' : dados_st_interestadual['nao_aplicabilidade_st_interestadual'],
        'observacao_st_interestadual' : dados_st_interestadual['observacao_st_interestadual'],
        'aliquota_interna_st_interestadual' : dados_st_interestadual['aliquota_interna_st_interestadual'],
        'aliquota_interestadual_st_interestadual' : dados_st_interestadual['aliquota_interestadual_st_interestadual'],
        
        'cst_pis': dados_pis_cofins['cst_pis'],
        'aliquota_pis': dados_pis_cofins['aliquota_pis'],
        'cst_cofins': dados_pis_cofins['cst_cofins'],
        'aliquota_cofins': dados_pis_cofins['aliquota_cofins'],
        'base_legal_pis_cofins' : dados_pis_cofins['aplicablidade'],

        'cst_cbs': dados_pis_cofins.get('cst_cbs', ''),
        'aliquota_cbs': dados_pis_cofins.get('aliquota_cbs', ''),
        'base_legal_cbs': dados_pis_cofins.get('base_legal_cbs', ''),

        'aliquota_ibs_estadual': dados_ibs['aliquota_ibs_estadual'],
        'base_legal_ibs_estadual': dados_ibs['base_legal_ibs_estadual'],
        'descricao_ibs_estadual': dados_ibs['descricao_ibs_estadual'],

        'reforma_tipo_beneficio': dados_reforma['reforma_tipo_beneficio'],
        'reforma_reducoes': dados_reforma['reforma_reducoes'],
        'reforma_creditos': dados_reforma['reforma_creditos'],
        'reforma_aplicabilidade': dados_reforma['reforma_aplicabilidade'],
        'reforma_base_legal': dados_reforma['reforma_base_legal'],

        'descricao_reducao' : dados_reducao['descricao_reducao'],
        'operacao_interna' : dados_reducao['operacao_interna'],
        'cbenef' : dados_reducao['cbenef'],
        'base_legal_reducao_interna' : dados_reducao['base_legal_reducao_interna'],
        'descricao_interna' : dados_reducao['descricao_interna'],
        'aliquota_reducao_interna' : dados_reducao['aliquota_reducao_interna'],
        'operacao_externa' : dados_reducao['operacao_externa'],
        'base_legal_reducao_externa' : dados_reducao['base_legal_reducao_externa'],
        'descricao_externa' : dados_reducao['descricao_externa'],
        'aliquota_reducao_externa' : dados_reducao['aliquota_reducao_externa'],
        'ncm': dados_ncm['ncm'],
        'nome_item': dados_ncm['nome_item'],
    }
    
    return dados_consultados

# FORMATA O NCM PARA BUSCAR NA TIPI
def formatar_ncm(ncm):
    if len(ncm) == 8:
        return f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}"
    else:
        return None

# BUSCA A DESCRIÇÃO DO NCM NA TIPI
def consultar_tipi(dados_ncm, tabela_tipi):

    ncm_para_buscar = dados_ncm['ncm']
    ncm_formatado = formatar_ncm(ncm_para_buscar)

    if not ncm_formatado:
        return {
            "descricao": 'NCM FORMATADO',
            "ex": None
        }

    linha_tipi = tabela_tipi[tabela_tipi['NCM'] == ncm_formatado]
    
    if linha_tipi.empty:
        return {
            "descricao": 'NCM NÃO ENCONTRADO',
            "ex": None
        }

    # 🔥 PRIORIDADE PARA EX
    linha_com_ex = linha_tipi[linha_tipi['EX'].notna()]

    if not linha_com_ex.empty:
        linha_escolhida = linha_com_ex.iloc[0]
    else:
        linha_escolhida = linha_tipi.iloc[0]

    descricao = linha_escolhida['DESCRIÇÃO']
    ex = linha_escolhida['EX']

    return {
    "descricao": descricao,
    "ex": ex
}
