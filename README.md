# Análise Tributária

Sistema web em Django para **classificação e conferência tributária de produtos por NCM**, voltado a escritórios de contabilidade e departamentos fiscais. Desenvolvido por **Elias Silva** ([Morpho Automações](https://morphoautomacoes.com.br)).

> Este sistema está sendo substituído por agentes de IA; o código foi aberto como portfólio e referência.

## O problema

Definir a tributação correta de cada produto (ICMS, substituição tributária, PIS/COFINS, benefícios fiscais) depende do NCM, da UF, do regime tributário da empresa e da atividade de origem e destino. Fazer isso item a item, consultando legislação, é lento e sujeito a erro, e os erros aparecem depois nas notas fiscais emitidas (CST/CSOSN errado, ST não destacada, PIS/COFINS indevido).

O sistema automatiza esse trabalho: recebe a lista de produtos (ou as próprias NF-e), consulta as regras tributárias por NCM em uma base de legislação, guarda o resultado e compara o que **deveria** ter sido aplicado com o que **foi** aplicado nas notas.

## Funcionalidades

- **Multiempresa / multiusuário**: contas (workspaces) com usuários e papéis (Owner, Admin, Member); empresa ativa por sessão.
- **Cadastro de empresas** com validação de CNPJ e preenchimento automático via APIs públicas (`publica.cnpj.ws`, com fallback para `receitaws.com.br`); regime tributário (Simples Nacional, Lucro Presumido, Lucro Real) e atividade de origem/destino.
- **Consulta de TARE no DF**: busca, no portal público da Receita do DF, os regimes especiais (TARE) da empresa e extrai os itens com substituição tributária.
- **Upload de dados** em lote, processado em segundo plano com barra de progresso:
  - planilha XLSX de produtos (`PRODUTO | NCM`, com modelo para download);
  - XML de NF-e/NFC-e, avulsos ou em ZIP (cabeçalho, itens, ICMS, ICMS-ST, PIS e COFINS).
- **Análise tributária por NCM** em fila com processamento concorrente, cancelamento e retomada:
  - Simples Nacional e Lucro Real/Presumido têm motores separados;
  - consultas de alíquota de ICMS, ST interna e interestadual, PIS/COFINS (com exceções da TIPI), benefícios fiscais, alíquota padrão da UF e benefícios da reforma tributária.
- **Cache de resultados** por empresa e cache compartilhado por contexto fiscal (NCM + UF + regime + atividades), evitando consultas repetidas à API paga.
- **Vínculo automático** entre itens das notas e produtos analisados por similaridade de descrição (Jaccard).
- **Divergências fiscais** com severidade: CST de ICMS/CSOSN, CST de PIS e COFINS, valores de PIS/COFINS e ICMS-ST (expectativa de ST pela análise x CST encontrado no XML).
- **Dashboard** com indicadores, **navegador de NCM** e **relatório de diagnóstico tributário** em Word (.docx); exportação da análise em XLSX.

## Arquitetura e stack

- **Python 3.12 / Django 5.1**, templates com Bootstrap 5 e DataTables
- **SQLite** em desenvolvimento; **PostgreSQL** opcional (psycopg)
- **pandas / openpyxl** (planilhas e tabela TIPI), **lxml** (XML de NF-e), **python-docx** (relatório Word)
- **requests** com sessão HTTP reaproveitada e retentativas para a API externa
- **DrissionPage** (Chromium) para a consulta de TARE no portal da Receita do DF
- Processamento em segundo plano com `threading` dentro do próprio processo; filas órfãs são marcadas como erro ao reiniciar o servidor
- **WhiteNoise** para arquivos estáticos

```
config/                      settings (via variáveis de ambiente), urls, wsgi
accounts/                    app de autenticação
core/
  models.py                  Conta, Membership, Empresa, UploadLote, NotaFiscal, ItemNotaFiscal,
                             AnaliseItem, AnaliseNcmCache(+Compartilhado), FilaAnalise, DivergenciaItem
  views/                     dashboard, empresas, uploads, notas, ncm, análise, divergências, relatórios
  services/
    upload_processor.py      leitura de XLSX, XML e ZIP de NF-e
    fila_upload.py           processamento de uploads em background
    fila_analise.py          fila de análise tributária (concorrente)
    tributario/simples/      motor e cache do Simples Nacional
    tributario/lucro_real/   motor e cache do Lucro Real/Presumido
    apis/                    clientes da API LegisWeb
    pos_analise.py           vínculo item da nota x análise (similaridade)
    divergencias.py          regras de divergência fiscal
    cnpj_service.py          consulta de CNPJ
    consulta_tare_df.py      consulta de TARE (SEFAZ-DF)
  utils/relatorio_word.py    geração do relatório .docx
templates/  static/
_RECURSOS_/tipi.xlsx         tabela TIPI (dado público)
```

## API externa

As regras tributárias por NCM vêm da **API da [LegisWeb](https://www.legisweb.com.br)**, serviço pago: é preciso ter conta contratada e informar o código de usuário e o token no `.env`. O manual da API não acompanha este repositório (é material do fornecedor).

## Como executar

```bash
python -m venv venv
venv\Scripts\activate          # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

copy .env.example .env         # Linux/macOS: cp .env.example .env
# edite o .env: DJANGO_SECRET_KEY, LEGISWEB_USER_ID, LEGISWEB_TOKEN

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/` e entre com o usuário criado. Pelo admin (`/admin/`) crie uma **Conta** e um **Membership** ligando o usuário à conta; depois cadastre as empresas pela interface.

Para gerar uma `DJANGO_SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | sim | chave secreta do Django |
| `DJANGO_DEBUG` | não | `True` em desenvolvimento (padrão `False`) |
| `DJANGO_ALLOWED_HOSTS` | não | hosts separados por vírgula (padrão `localhost,127.0.0.1`) |
| `CORS_ALLOW_ALL_ORIGINS` | não | padrão `True` |
| `LEGISWEB_USER_ID` | sim, para a análise | código do usuário na API LegisWeb |
| `LEGISWEB_TOKEN` | sim, para a análise | token da API LegisWeb |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | não | se `POSTGRES_DB` estiver definido, usa PostgreSQL no lugar do SQLite |

A consulta de TARE-DF abre um navegador Chromium (DrissionPage); é preciso ter Chrome/Chromium instalado.

## Observações

- A migração `core/migrations/0012_upload_lote_progresso.py` consolida as migrações 0007 a 0012, que não estavam versionadas no repositório original.
- Não versione documentos fiscais reais, bancos de dados nem o arquivo `.env` (veja `.gitignore`).

## Licença

[MIT](LICENSE) © 2026 Elias Silva
