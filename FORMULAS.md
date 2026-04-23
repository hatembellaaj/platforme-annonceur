# Shared Formulas

This platform reuses the metric logic already present in the repo and applies it with explicit source vs override handling.

## Objective fields

- `objective_source_value`
  - value returned by the source data
- `objective_override_value`
  - manual correction stored locally
- `objective_effective_value`
  - override value when present, otherwise source value

## Core formulas

### CTR

```text
CTR = clicks / impressions * 100
```

Meaning:

- click-through rate for the selected entity or period

### Monthly objective

```text
Objectif mensuel = objectif total / nb_mois
```

Meaning:

- target pace per month based on the effective objective

### Raw objective progress

```text
Taux objectif brut = impressions / objectif total * 100
```

Meaning:

- real completion percentage
- can exceed `100%`

### UI progress

```text
Progression UI = min(taux objectif brut, 100)
```

Meaning:

- capped progress value for progress bars

### Monthly average

```text
Moyenne mensuelle = impressions annee / mois ecoules
```

Meaning:

- current average monthly delivery pace

### Gap

```text
Ecart = moyenne mensuelle - objectif mensuel
```

Meaning:

- difference between actual pace and target pace

### Percent gap

```text
% Ecart = ecart / moyenne mensuelle * 100
```

Meaning:

- proportional gap relative to achieved average pace

## Effective status rules

### Source active status in V1

```text
active_source = impressions > 0 on the latest Windsor reporting date
```

### Effective active status

```text
effective_status = status_override if defined else active_source
```

## Alerts

All alerts use effective values.

### Missing objective

```text
objective_effective_value <= 0
```

### Objective reached

```text
taux_objectif_brut >= 100
```

### Below target

```text
objective_effective_value > 0 and taux_objectif_brut < 100 and entity is active
```

### Inactive

```text
is_active = false
```
