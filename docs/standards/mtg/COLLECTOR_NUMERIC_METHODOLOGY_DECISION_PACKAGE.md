# Collector Numeric Methodology Decision Package

## Purpose

This package identifies the Collector forecast methodology decisions that are not fully defined by the canonical MTG standards. It does not approve or implement any numeric formula.

## Already defined and not awaiting a new decision

The canonical standard already defines:

- explicit method routing or deferral for every governed product;
- supported Collector methods;
- one-, three-, and five-year horizons;
- downside, base, and upside scenarios;
- approved use and disclosure of comparable evidence;
- the owner-approved Japanese FINAL FANTASY hybrid route;
- required output and disclosure fields;
- separation of forecast generation, purchase analysis, and purchase authorization;
- fail-closed identity and current-price handling.

## Numeric decisions still required

### Decision group 1 — Direct-history methods

The standard does not define the equations for DIRECT_HISTORY_CALIBRATED or DIRECT_HISTORY_LIMITED. A future approval package must specify which historical measures may influence the projection, how they are calibrated, and how limited history changes confidence and uncertainty.

### Decision group 2 — Comparable aggregation

The standard approves comparable evidence and defines selection factors, but it does not define how selected comparable histories are aggregated, weighted, normalized, or adjusted into target-product forecasts.

### Decision group 3 — Hybrid weighting

The Japanese FINAL FANTASY override authorizes a hybrid route and identifies its primary comparable, but it does not define numeric comparable and fundamental weights or the fundamental adjustment equation.

### Decision group 4 — Confidence and uncertainty

The standard requires confidence and uncertainty to reflect the evidence used. It does not define a confidence-score formula, confidence-class thresholds, scenario-width equation, or numeric penalty schedule.

### Decision group 5 — Market-factor adjustments

Supply, demand, liquidity, reprint exposure, premium contents, franchise strength, and historical behavior are required evidence factors. The standard does not define the equation or magnitude by which those factors alter forecast values.

### Decision group 6 — Caps, floors, anchors, and limits

No canonical forecast caps, floors, anchors, growth limits, price-age thresholds, or minimum observation counts are currently defined. Values embedded in historical scripts are not authoritative.

### Decision group 7 — Purchase analysis

The standard separates purchase analysis and authorization from forecasting. It does not define transaction-cost assumptions, required return, margin of safety, buy-below calculations, decision labels, or position-size thresholds.

## Required process before implementation

For each unresolved decision group:

1. identify relevant evidence and prior implementation behavior;
2. present alternatives and consequences;
3. make a recommended choice;
4. obtain explicit owner approval;
5. record the approval in a versioned governance artifact;
6. implement only the approved behavior;
7. backtest and perform semantic and economic review;
8. keep projection and purchase authorization false until final certification.

## Current authorization state

- Methodology changed: false
- Projection authorized: false
- Purchase recommendation authorized: false
- Owner approval requested: no
