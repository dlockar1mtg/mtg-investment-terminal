# Phase 10.15 — Portfolio Allocation and Purchase Planning

## Purpose

Translate governed Phase 10.14 marketplace decisions into an executable monthly MTG purchase plan while preserving whole-box, budget, reserve, holdings, and concentration constraints.

## Production inputs

- `certified_marketplace_decisions.csv`
- `product_master_model_input.csv`
- Optional `data/terminal2/portfolio_holdings.csv`
- Monthly MTG capital input
- Cash reserve percentage input

## Default operating policy

- Monthly MTG capital: `$600`
- Required cash reserve: `10%`
- Maximum units per product per run: `2`
- Mature-portfolio product concentration ceiling: `35%`
- Bootstrap concentration ceiling: `100%` until existing portfolio value reaches `$1,200`
- Only final governed `STRONG_BUY` and `BUY` decisions may receive new capital
- Recommendations must use whole units
- Unused capital carries forward

All policy values are configurable through the command line. Monthly capital and reserve percentage are also GitHub Actions workflow inputs.

## Whole-unit policy exception

Phase 10.14 allocation bands are advisory. A whole sealed product can cost more than the advisory maximum percentage of one month's capital. Phase 10.15 may recommend that whole unit when:

1. The product has a deployable final signal.
2. The full unit fits inside deployable capital after reserve.
3. Concentration controls pass.
4. The exception is explicitly recorded as `WHOLE_UNIT_POLICY_BAND_EXCEPTION`.

The exception never permits spending above monthly capital or consuming the required reserve.

## Outputs

- `monthly_purchase_plan.csv`
- `projected_portfolio_after_purchase.csv`
- `monthly_purchase_plan_summary.json`

## Plan actions

- `BUY_NOW`
- `CARRY_FORWARD_INSUFFICIENT_CAPITAL`
- `DEFER_PORTFOLIO_OPTIMIZATION`

## Fail-closed controls

The plan becomes `INCOMPLETE` when a deployable product cannot be matched to the approved model or when an existing holding references an unknown investment product ID. It becomes `FAILED` if the configured cash reserve is not preserved.

## Remaining user-maintained input

The system can operate in bootstrap mode without a holdings file. For mature portfolio-aware planning, populate:

`data/terminal2/portfolio_holdings.csv`

using the existing columns:

```text
investment_product_id,quantity,acquisition_cost_total,acquisition_date,notes
```

This is the only recurring manual portfolio input required unless holdings are later connected to an external inventory source.
