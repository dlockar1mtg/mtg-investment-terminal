# Collector Early-Lifecycle Breakout Replay

## Purpose

Evaluate whether early-lifecycle Collector forecasts identify major 365-day winners before most appreciation occurs.

## Scope

The replay evaluates historical decision rows in four age bands: 0-3, 4-8, 9-12, and 13-17 months.

## Outcomes

Historical realized 365-day returns are used only for scoring. They may not enter forecast features.

## Metrics

- Breakout recall at +25%, +50%, and +70%
- False-negative rate at each threshold
- Top-20% capture at each threshold
- False-positive rate at each threshold
- Mean missed upside for false negatives
- Rank correlation
- Top-bottom realized-return spread

## Interpretation

The replay is diagnostic. Passing the structural audit does not authorize methodology changes, production forecasts, purchases, automatic updates, technical freeze, or UIP acceptance.

## Outputs

- `collector_early_lifecycle_breakout_replay_cases.csv`
- `collector_early_lifecycle_breakout_replay_summary.csv`
- `collector_early_lifecycle_breakout_replay_summary.json`
