# MTG Forecasting and Decision Standard

## Status

Canonical baseline version 1.0.1.

## Governing rule

Implementation must conform to this standard. The standard must not be
weakened merely to accommodate existing code or data.

## Core requirements

1. Every governed product receives an explicit forecast method or an
   explicit deferred reason.
2. Comparable-product analysis is an approved forecasting method.
3. Insufficient direct history does not automatically prohibit forecasting.
4. Direct-history quarantine applies to the historical method and does not
   automatically reject the product.
5. Identity and executable-price failures remain fail-closed.
6. Forecast outputs disclose method, evidence, confidence, uncertainty,
   limitations, source information, and standard version.
7. Required horizons are one, three, and five years.
8. Required scenarios are downside, base, and upside.
9. Forecast generation and purchase authorization remain separate.
10. Automated tests are necessary but do not replace production semantic
    certification.

## Pre-Collector model-eligibility requirement

The Pre-Collector booster-box lane has an additional governed distinction
between canonical-universe membership and model-specific training eligibility.
The certified canonical universe must not be reduced merely to improve model
fit, and model-training exclusions do not alter canonical product identity.

Pre-Collector models must not use arbitrary release-year, product-age, or
vintage cutoffs. A canonical product may be down-weighted, isolated for
holdout diagnostics, or excluded from fitting only when governed empirical
diagnostics support that treatment. Relevant evidence includes pricing-history
coverage and continuity, availability and liquidity, scarcity behavior,
statistical influence, parameter or prediction stability, and out-of-sample
performance across validation windows, required horizons, and multiple model
families where practical.

A product must not be excluded solely because it is old, expensive, scarce, or
because removing it improves a preferred metric. Persistent exclusions require
an explicit reason code, diagnostic evidence, model or horizon scope, and owner
review. Training exclusion does not automatically prohibit forecasting or
ranking; those remain separate governed applicability and downstream decisions.

The controlling Pre-Collector authorities are:

- `config/mtg/governance/precollector_model_eligibility_owner_decision_v1.json`
- `config/mtg/standards/precollector_model_eligibility_and_exclusion_contract_v1.json`

## Change control

Changes to methods, weights, thresholds, source hierarchy, product universe,
or eligibility rules require approval, a version change, and recertification.
