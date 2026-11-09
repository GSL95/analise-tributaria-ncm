# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run development server
python manage.py runserver

# Apply migrations
python manage.py migrate

# Create migrations after model changes
python manage.py makemigrations

# Django shell for debugging
python manage.py shell

# Run tests
python manage.py test
```

Install dependencies into the `venv/` virtual environment:

```bash
pip install -r requirements.txt
```

## Architecture Overview

This is a **multi-tenant Django 5.1 application for Brazilian fiscal/tax (tributária) analysis**. The project revolves around three concepts: companies (empresas), invoice uploads, and tax analysis.

### Multi-Tenancy Model

- **Conta** — workspace that groups companies and users
- **Membership** — links users to contas with roles (OWNER, ADMIN, MEMBER)
- **Empresa** — main business entity; one conta has many empresas
- An "active company" is tracked per session via `core/context_processors.py` and enforced with the `@empresa_ativa_required` decorator in `core/authz.py`

### Data Flow

1. User uploads XML NFe files (ZIP) or XLSX spreadsheets via `core/views/uploads.py`
2. `core/services/upload_processor.py` parses them → creates `NotaFiscal` + `ItemNotaFiscal` records
3. Tax analysis engine (`core/services/tributario/engine.py`) queries external APIs per NCM code and tax regime
4. Results are cached in `AnaliseNcmCache` to avoid redundant API calls
5. `core/services/pos_analise.py` links invoice items to analysis results using Jaccard similarity on product descriptions
6. `core/services/divergencias.py` compares expected vs. actual CST/CSOSN codes and flags discrepancies with severity levels

### Tax Regimes

The system handles three Brazilian tax regimes, with separate cache services:

- **Simples Nacional** → `core/services/tributario/simples/cache_service.py`
- **Lucro Real** → `core/services/tributario/lucro_real/cache_service.py`
- **Lucro Presumido** → handled within the main engine

### Key Services

| File                                   | Purpose                                             |
| -------------------------------------- | --------------------------------------------------- |
| `core/services/upload_processor.py`  | Parses NFe XML/ZIP and XLSX, populates DB           |
| `core/services/tributario/engine.py` | Main NCM tax analysis engine                        |
| `core/services/cnpj_service.py`      | CNPJ lookup via `publica.cnpj.ws` / `receitaws` |
| `core/services/divergencias.py`      | Detects fiscal divergences with severity levels     |
| `core/services/pos_analise.py`       | Links invoice items to analysis via text similarity |
| `core/services/consulta_tare_df.py`  | TARE (DF tax authority) API integration             |

### URL Structure

All routes are in `core/urls.py`, included at root from `config/urls.py`.

- `/` — dashboard with KPIs
- `/empresas/` — company CRUD + CNPJ lookup
- `/uploads/` — file upload and processing
- `/notas/` — NFe invoice list and details
- `/ncm/` — NCM tariff code browser
- `/empresas/<id>/analise-tributaria/` — tax analysis view and XLSX export
- `/divergencias/` — divergence detection report

### Configuration

- Settings: `config/settings.py` (single file; secrets and DEBUG read from `.env`, see `.env.example`; SQLite in dev)
- Static files: served via WhiteNoise
- CORS: `CORS_ALLOW_ALL_ORIGINS = True`
- Environment variables loaded via `python-dotenv`
- PostgreSQL supported via psycopg (not active in dev)

### External Integrations

- **CNPJ APIs**: `publica.cnpj.ws` and `receitaws.com.br` (public, no auth needed)
- **LegisWeb**: tax database API used in `core/services/tributario/legisweb_client.py`
- **TARE-DF**: Distrito Federal tax authority integration in `core/services/apis/`
