# MTG Forecasting and Decision Standard

## Status

Canonical baseline version 1.0.0.

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

## Change control

Changes to methods, weights, thresholds, source hierarchy, product universe,
or eligibility rules require approval, a version change, and recertification.
