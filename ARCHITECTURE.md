# Platform Architecture

## Goal

Build a separate advertiser platform on top of Windsor / GAM reporting with two explicit surfaces:

- `Admin`
- `Advertiser`

The platform must expose delivery status, objectives, progress, and time-based reporting while keeping source values and manual corrections visible side by side.

## Architecture

### 1. Source layer

The app uses Windsor reporting as the primary V1 source.

Input fields used in V1:

- `account_name`
- `advertiser_id` when available
- `line_item_name`
- `line_item_goal_quantity`
- `date`
- `impressions`
- `clicks`

### 2. Normalization layer

The source layer is normalized into two internal record families:

#### `CampaignRecord`

- identity:
  - `advertiser_id`
  - `advertiser_name`
  - `campaign_id`
  - `campaign_name`
- source fields:
  - `objective_source_value`
  - `is_active_source`
  - `start_date_source`
  - `end_date_source`
- override fields:
  - `objective_override_value`
  - `is_active_override`
  - `start_date_override`
  - `end_date_override`
- effective fields:
  - `objective_effective_value`
  - `is_active`
  - `start_date`
  - `end_date`
  - `duration_days`
  - `active_status_label`
- performance:
  - `impressions`
  - `clicks`
  - `ctr`

#### `AdvertiserRecord`

- identity:
  - `advertiser_id`
  - `advertiser_name`
- objective fields:
  - `objective_source_value`
  - `objective_override_value`
  - `objective_effective_value`
  - `objective_value_origin`
- activity fields:
  - `active_campaign_count`
  - `is_active`
  - `active_status_label`
- interval fields:
  - `official_start_date`
  - `official_end_date`
  - `duration_days`
- performance:
  - `impressions`
  - `clicks`
  - `ctr`

### 3. Formula layer

One shared metrics layer is used by both surfaces.

Core formulas:

- `CTR = clicks / impressions * 100`
- `Objectif mensuel = objectif total / nb_mois`
- `Taux objectif brut = impressions / objectif total * 100`
- `Progression UI = min(taux objectif brut, 100)`
- `Moyenne mensuelle = impressions annee / mois ecoules`
- `Ecart = moyenne mensuelle - objectif mensuel`
- `% Ecart = ecart / moyenne mensuelle * 100`

All progress, alerts, and status summaries use effective values, not raw source values, when an override exists.

### 4. Override layer

Manual corrections are stored in local JSON files, not in cache.

Files:

- `platform_settings.json`
- `advertiser_overrides.json`
- `campaign_overrides.json`

Overrides persist across:

- reruns
- cache clears
- new app sessions

### 5. Presentation layer

#### Admin page

- KPI cards
- total active advertisers
- total active campaigns
- global source objective vs effective objective
- formula explanation section
- day / week / month aggregation toggle
- trend chart
- advertiser summary table
- campaign correction table

#### Advertiser page

- advertiser selector
- advertiser summary cards
- active campaign count
- official interval from active campaigns
- campaign performance and correction table
- advertiser trend chart
- detailed grain table

## Activity rules

### Source activity rule in V1

- Windsor source status is treated as active when a campaign has impressions on the latest reporting date returned by Windsor

### Effective activity rule

- use source status by default
- if a manual override exists, use the override

### Advertiser official interval

- derived only from effective active campaigns
- start = earliest effective start among active campaigns
- end = latest effective end among active campaigns

## Implementation note

V1 stays inside the current Python / Streamlit stack so it can reuse:

- the Windsor credentials and config already in the repo
- the existing objective persistence pattern
- the existing metric logic already used in the GAM / Revive dashboards
