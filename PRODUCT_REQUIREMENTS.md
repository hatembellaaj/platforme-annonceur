# Product Requirements

## Surfaces

The platform has two required pages:

- `Admin`
- `Advertiser`

## Admin page

The admin page must show:

- total active advertisers
- total active campaigns
- source global objective
- effective global objective
- total impressions
- global progress using the effective objective
- formula explanation blocks
- time-grain toggle:
  - `day`
  - `week`
  - `month`
- trend chart based on the selected grain
- advertiser summary table
- campaign correction table

The advertiser summary table must include:

- advertiser name
- active campaign count
- active / inactive label
- official advertiser interval
- source objective
- editable objective override
- effective objective
- impressions
- clicks
- ctr
- progress
- alert

The campaign correction table must include:

- advertiser
- campaign
- source status
- editable status override
- effective status
- source start
- editable start override
- effective start
- source end
- editable end override
- effective end
- source objective
- editable objective override
- effective objective

## Advertiser page

The advertiser page must show:

- advertiser selector
- advertiser summary cards
- active campaign count
- active / inactive status
- official interval from active campaigns
- source objective
- editable objective override
- effective objective
- advertiser progress
- campaign table with active / inactive visibility
- trend chart
- detailed table for the selected grain

The campaign table must include:

- campaign name
- source status
- editable status override
- effective status
- source objective
- editable objective override
- effective objective
- source start / end
- editable start / end
- effective start / end
- duration
- impressions
- clicks
- ctr
- progress
- alert

## Override behavior

Manual corrections must:

- be explicit in the UI
- never overwrite raw source values
- persist outside cache
- survive reruns and cache clears

## Alert behavior

Alerts must use effective values.

Required alert cases:

- no active campaigns
- missing objective
- inactive campaign
- below target
- objective reached or exceeded

## Design requirements

The interface must:

- use a cleaner palette than the legacy dashboards
- keep tables readable
- avoid compressed critical columns
- keep objective source and objective override visible at the same time
