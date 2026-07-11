# Changelog

## v3.2

### Changed
- Lowered `MIN_PORTFOLIO_RISK_ADJUSTED_SCORE` from `78` to `74`.
- Lowered `MAX_BASE_CAGR` from `0.30` to `0.24`.
- Lowered `MAX_BULL_CAGR` from `0.38` to `0.32`.

### Reasoning
The prior version's portfolio optimizer became too restrictive and only selected LOTR. The new threshold keeps the quality filter but allows other strong candidates back into the recommendation. The CAGR caps were reduced to make 5-year projections more realistic and less aggressive.
