# Secret Lair V1 — Purchase Recommendations

## Status

SECRET_LAIR_V1_PURCHASE_RECOMMENDATIONS_CERTIFIED

## V1 recommendation policy

Policy:

SECRET_LAIR_V1_Q10_CONSERVATIVE_ENTRY_POLICY

The policy uses the previously governed 1Y Q10 downside quantile as the
conservative V1 entry boundary.

It was not selected or tuned to produce a target number of candidates.

## BUY_CANDIDATE_NOW

A product receives BUY_CANDIDATE_NOW when:

1. its current governed TCG price is at or below its governed 1Y Q10
   break-even entry level; and
2. its evidence gate passes.

Direct-history products pass the evidence gate.

A no-direct-history product may pass when exact structural comparable evidence
is available.

Current BUY_CANDIDATE_NOW count:

88

## REVIEW_GLOBAL_COMPARABLE_ONLY

A no-history product that reaches the Q10 entry condition but has only the
broad global-comparable route does not silently receive the same recommendation
strength as a product with direct history or exact structural comparables.

It is labeled:

REVIEW_GLOBAL_COMPARABLE_ONLY

Current count:

1

## WAIT_FOR_Q10_ENTRY

Products trading above their governed Q10 entry level are labeled:

WAIT_FOR_Q10_ENTRY

The recommendation ledger provides the governed Q10 target entry price and
the price movement required to reach it.

Current count:

698

## Q25 / Q50

Q25 and Q50 remain economic diagnostics.

They are not BUY thresholds in Secret Lair V1.

## Ranking

There is no maximum-rank requirement.

The existing certified competition ranking remains available to prioritize
products inside a recommendation category, but rank does not override the
Q10/evidence policy.

## Prohibited policy inputs

- Collector purchase thresholds;
- weighted purchase scores;
- Monte Carlo random seed;
- current dollar-price level as investment quality;
- product name or product ID;
- directly unvalidated 3Y/5Y scenarios as BUY triggers.

## Long horizon

3Y and 5Y remain scenarios.

Direct 3Y validation:

FALSE

Direct 5Y validation:

FALSE

They are displayed for context but are not purchase triggers.

## Transaction limitations

Transaction costs:

NOT MODELED

Execution liquidity:

NOT GUARANTEED

Automatic purchase execution:

FALSE

A certified purchase recommendation is an analytical decision output, not an
automatic order instruction.

## Dynamic universe

No fixed Secret Lair product count is embedded in recommendation logic.

Future Secret Lairs use this same policy after passing governed identity,
current-price, forecast, comparable, uncertainty, Monte Carlo, ranking, and
purchase-analysis gates.

## Authority

Purchase recommendations:

CERTIFIED

Secret Lair V1 final closeout execution:

AUTHORIZED NEXT

Secret Lair V1 closed:

FALSE

Unified MTG authority:

FALSE

UIP delivery:

FALSE

Automatic purchase execution:

FALSE

## Next gate

SL7_SECRET_LAIR_V1_FINAL_CLOSEOUT