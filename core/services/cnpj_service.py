import requests

def consultar_dados_cnpj(cnpj):
    cnpj = cnpj.replace('.', '').replace('/', '').replace('-', '')

    if len(cnpj) != 14:
        return None

    fontes = [
        ("https://publica.cnpj.ws/cnpj/", "publica_cnpj_ws"),
        ("https://www.receitaws.com.br/v1/cnpj/", "receitaws"),
    ]

    for base_url, origem in fontes:
        try:
            response = requests.get(f"{base_url}{cnpj}", timeout=10)
            response.raise_for_status()
            dados = response.json()
            

            if 'error' not in dados:
                return formatar_dados(dados, origem)

        except requests.exceptions.RequestException as e:
            print(f"[ERRO API CNPJ - {origem}] {e}")
            continue

    return None

def formatar_dados(dados, origem):
    """
    Redireciona os dados brutos para o parser correto baseado na origem.
    """
    if origem == "publica_cnpj_ws":
        return parse_publica_cnpj_ws(dados)
    elif origem == "receitaws":
        return parse_receitaws(dados)
    return {}

def parse_publica_cnpj_ws(dados):
    try:
        estabelecimento = dados.get('estabelecimento', {})
        inscricao_estadual = (
            estabelecimento.get('inscricoes_estaduais', [{}])[0].get('inscricao_estadual', '')
            if estabelecimento.get('inscricoes_estaduais') else ''
        )

        atividades_secundarias = estabelecimento.get('atividades_secundarias', 'MERDA')

        return {
            'razao_social': dados.get('razao_social', ''),
            'nome_fantasia': estabelecimento.get('nome_fantasia', ''),
            'inscricao_estadual': inscricao_estadual,
            'cep': estabelecimento.get('cep', ''),
            'endereco': estabelecimento.get('logradouro', ''),
            'numero': estabelecimento.get('numero', ''),
            'bairro': estabelecimento.get('bairro', ''),
            'municipio': estabelecimento.get('cidade', {}).get('nome', ''),
            'uf': estabelecimento.get('estado', {}).get('sigla', ''),
            'data_abertura': estabelecimento.get('data_inicio_atividade', ''),
            'cnae_principal': {
                'codigo': estabelecimento.get('atividade_principal', {}).get('id'),
                'descricao': estabelecimento.get('atividade_principal', {}).get('descricao'),
            },
            'cnaes_secundarios': [
                {'codigo': cnae.get('id'), 'descricao': cnae.get('descricao')}
                for cnae in atividades_secundarias
            ]
        }

    except Exception as e:
        print(f"[ERRO PARSE PUBLICA_CNPJ_WS] {e}")
        return {}

def parse_receitaws(dados):
    try:
        atividade_principal = dados.get('atividade_principal', [{}])[0]
        atividades_secundarias = dados.get('atividades_secundarias', [])

        return {
            'razao_social': dados.get('nome', ''),
            'nome_fantasia': dados.get('fantasia', ''),
            'inscricao_estadual': '',  # Não fornecido pela Receitaws
            'cep': dados.get('cep', ''),
            'endereco': dados.get('logradouro', ''),
            'numero': dados.get('numero', ''),
            'bairro': dados.get('bairro', ''),
            'municipio': dados.get('municipio', ''),
            'uf': dados.get('uf', ''),
            'data_abertura': dados.get('abertura', ''),
            'cnae_principal': {
                'codigo': atividade_principal.get('code'),
                'descricao': atividade_principal.get('text'),
            },
            'cnaes_secundarios': [
                {'codigo': cnae.get('code'), 'descricao': cnae.get('text')}
                for cnae in atividades_secundarias
            ]
        }
    except Exception as e:
        print(f"[ERRO PARSE RECEITAWS] {e}")
        return {}