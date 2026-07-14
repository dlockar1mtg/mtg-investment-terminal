# Core Investment Intelligence Architecture

## Principle

Phase 1 is an interpretation layer. It reuses the existing forecast universe
and forecast engine instead of creating a second competing forecast.

## Engines

- Risk: volatility, liquidity, drawdown, data quality, and forecast uncertainty
- Confidence: history depth, observations, forecast confidence, market
  confidence, and model coverage
- Recommendation: return, conviction, regime, risk quality, and confidence
- Explanation: threshold-based positive, risk, and evidence statements

## Recommendation safeguards

A product is labeled `Insufficient Data` when confidence is below 35 or model
coverage is below 50. High expected return alone cannot produce an actionable
recommendation when evidence is inadequate.
