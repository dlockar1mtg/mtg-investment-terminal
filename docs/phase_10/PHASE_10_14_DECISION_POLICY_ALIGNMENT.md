# Phase 10.14 — Decision Policy Alignment

## Purpose

Align MTG marketplace rank, signal, risk controls, and new-capital guidance so the production output communicates one governed recommendation.

## Policy version

`10.14.0`

## Base valuation signals

| Expected upside to governed forecast anchor | Base signal |
|---:|---|
| 25% or greater | STRONG_BUY |
| 15% to less than 25% | BUY |
| 5% to less than 15% | WATCH |
| -10% to less than 5% | HOLD |
| Less than -10% | AVOID |

## Risk and evidence overrides

A positive forecast alone cannot produce a deployable recommendation when evidence or risk is insufficient.

- Fewer than two independent certified sources caps the signal at `WATCH`.
- Cross-source price divergence of 25% or more caps the signal at `WATCH`.
- Monte Carlo probability of loss of 35% or more caps the signal at `WATCH`.
- Reprint risk of 75 or more caps the signal at `WATCH`.
- Data quality below 50 or liquidity below 40 caps the signal at `HOLD`.

Overrides can only weaken a signal. They can never promote it.

## Ranking alignment

Decisions are ranked first by final governed signal and then by deal score:

1. STRONG_BUY
2. BUY
3. WATCH
4. HOLD
5. AVOID

This prevents a high raw score with a risk override from ranking above a deployable recommendation.

## New-capital guidance

| Final signal | Action | Suggested share of currently available MTG new capital |
|---|---|---:|
| STRONG_BUY | ACCUMULATE_PRIORITY | 35%–50% |
| BUY | ACCUMULATE | 15%–30% |
| WATCH | WAIT_FOR_CONFIRMATION | 0% |
| HOLD | MAINTAIN_ONLY | 0% |
| AVOID | EXCLUDE_NEW_CAPITAL | 0% |

These are policy bands, not automated orders. When multiple deployable products exist, a later portfolio-allocation layer must normalize allocations so the total does not exceed 100% of available MTG capital.

## Required production fields

- `policy_version`
- `base_signal`
- `signal`
- `allocation_action`
- `suggested_new_capital_min_pct`
- `suggested_new_capital_max_pct`
- `policy_override_applied`
- `decision_reason_codes`

## Certification criteria

Phase 10.14 passes when:

- all decisioning and marketplace tests pass on Windows and GitHub-hosted Linux;
- risk overrides are deterministic and fail closed;
- ranking order cannot contradict final signal strength;
- every decision contains an action and capital-guidance band;
- decision summaries report policy version, override count, deployable count, and signal counts.
