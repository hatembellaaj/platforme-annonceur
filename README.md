# Platform Annonceur

`platform annonceur` is a standalone Streamlit app built on direct Google Ad Manager data.

It has two surfaces:
- `Admin`
- `Annonceur`

## Data source

The app now uses direct GAM service-account access for:
- order snapshot
- campaign snapshot
- dated impressions / clicks / CTR reports
- active / inactive status logic
- order and campaign dates

The admin table is designed to move on a GAM `order` model instead of the older advertiser aggregate model.

## Durable corrections

The app keeps manual corrections outside Streamlit cache:
- `order_overrides.json`
- `campaign_overrides.json`
- `platform_settings.json`

Supported corrections:
- objective override
- campaign status override
- campaign start date override
- campaign end date override

If Supabase credentials are configured, overrides can be stored there.
If Supabase is missing or unreachable, the app falls back to local JSON.

## Required secrets

For Streamlit Cloud, add these secrets:

```toml
GAM_NETWORK_CODE = "9167326"
GAM_API_VERSION = "v202508"
GAM_SERVICE_ACCOUNT_JSON = """{ ... full service account json ... }"""
```

Optional Supabase secrets for override persistence:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_DB_PASSWORD = "..."
SUPABASE_DB_HOST = "db.your-project.supabase.co"
SUPABASE_DB_USER = "postgres"
SUPABASE_DB_NAME = "postgres"
SUPABASE_DB_PORT = "5432"
```

## Run locally

```powershell
python -m streamlit run app.py
```

## Deploy

Point Streamlit Cloud at this repo and set the app file to:

```text
app.py
```
