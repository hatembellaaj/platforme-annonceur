# Windsor Google Ad Manager Field Map

This file is a focused working summary of the Windsor Google Ad Manager field reference PDF currently stored in this folder.

The PDF indicates:

- `51 metrics`
- `62 dimensions`

The goal here is not to copy the full PDF verbatim, but to capture the fields that are most useful for the advertiser platform.

## Core advertiser and campaign identity

| Field | Type | Meaning |
| --- | --- | --- |
| `account_id` | `TEXT` | Advertising company ID |
| `account_name` | `TEXT` | Advertising company name, corresponds to advertiser/company context |
| `advertiser` | `TEXT` | Advertiser company assigned to an order |
| `advertiser_id` | `TEXT` | Advertiser company ID |
| `campaign` | `TEXT` | Windsor label mapped from GAM placement-style campaign breakdown |
| `date` | `DATE` | Reporting date |
| `datasource` | `TEXT` | Windsor connector source |

## Core performance fields

| Field | Type | Meaning |
| --- | --- | --- |
| `impressions` | `NUMERIC` | Impression count |
| `clicks` | `NUMERIC` | Click count |
| `ad_server_impressions` | `NUMERIC` | Ad server impressions |
| `ad_server_clicks` | `NUMERIC` | Ad server clicks |
| `ad_server_ctr` | `PERCENT` | Ad server CTR |
| `ad_server_all_revenue` | `NUMERIC` | Ad server revenue |

## Inventory fields

| Field | Type | Meaning |
| --- | --- | --- |
| `ad_unit_id` | `TEXT` | Ad unit ID |
| `ad_unit_name` | `TEXT` | Ad unit / slot name |
| `country` | `COUNTRY` | Country associated with request IP |

## Creative fields

| Field | Type | Meaning |
| --- | --- | --- |
| `creative_id` | `TEXT` | Creative ID |
| `creative_name` | `TEXT` | Creative name |
| `creative_size` | `TEXT` | Creative size |
| `creative_type` | `TEXT` | Creative type |

## Custom targeting and segmentation

| Field | Type | Meaning |
| --- | --- | --- |
| `custom_criteria` | `TEXT` | GAM key-value / custom targeting breakdown |
| `day_of_month` | `TEXT` | Day-of-month breakdown |

## Line item and delivery fields

| Field | Type | Meaning |
| --- | --- | --- |
| `line_item_contracted_quantity` | `TEXT` | Contracted quantity |
| `line_item_cost_per_unit` | `NUMERIC` | Line item rate |
| `line_item_cost_type` | `TEXT` | Cost type |
| `line_item_delivery_indicator` | `TEXT` | Delivery progress indicator |
| `line_item_delivery_pacing` | `TEXT` | Delivery pacing |
| `line_item_end_date_time` | `DATE` | Line item end date |
| `line_item_creative_start_date` | `DATE` | Creative start date on the line item |
| `line_item_creative_end_date` | `DATE` | Creative end date on the line item |

## Ad Exchange and AdSense related fields

These may be useful if the advertiser product later exposes monetization context:

- `ad_exchange_line_item_average_ecpm`
- `ad_exchange_line_item_clicks`
- `ad_exchange_line_item_ctr`
- `ad_exchange_line_item_revenue`
- `ad_exchange_line_item_targeted_impressions`
- `adsense_line_item_level_impressions`

## First platform field priorities

The initial version of the advertiser platform should focus on these fields first:

### Identity

- `advertiser`
- `advertiser_id`
- `campaign`
- `date`

### Performance

- `impressions`
- `clicks`
- `ad_server_ctr`
- `ad_server_all_revenue`

### Creative

- `creative_id`
- `creative_name`
- `creative_size`
- `creative_type`

### Inventory

- `ad_unit_id`
- `ad_unit_name`
- `country`

### Delivery

- `line_item_contracted_quantity`
- `line_item_delivery_indicator`
- `line_item_delivery_pacing`
- `line_item_end_date_time`

## Recommended first datasets

Based on these fields, the first backend should expose datasets like:

1. Advertiser campaign overview
2. Daily performance by campaign
3. Creative performance by advertiser
4. Creative size / format breakdown
5. Ad unit / slot breakdown
6. Country breakdown
7. Delivery pacing / contracted quantity analysis

## Gaps to resolve during implementation

The PDF is a raw field reference. Before using it directly in product logic, we still need:

- actual API query examples
- which fields are reliably populated in your Windsor account
- which fields match the existing dashboard business logic
- which Windsor "campaign" field best corresponds to advertiser-facing campaign naming in your data
