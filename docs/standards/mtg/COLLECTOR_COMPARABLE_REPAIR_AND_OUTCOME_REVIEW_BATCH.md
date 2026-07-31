# Collector Comparable Repair and Outcome Review Batch

## Purpose

Repair the canonical-ID to numeric-TCGplayer-ID mismatch that caused 624 discovered comparable edges to produce zero peer contributions, then regenerate inactive Collector forecast diagnostics with explicit retrospective-only lineage.

## Owner-validated current prices

The following current prices are treated as accurate and must not be classified as data errors solely because they are extreme:

- The Lord of the Rings: Tales of Middle-earth - Special Edition Collector Booster Display
- Universes Beyond: The Lord of the Rings: Tales of Middle-earth Collector Booster Display
- FINAL FANTASY Collector Booster Display
- FINAL FANTASY - Collector Booster Display (Japanese)

They remain subject to model-output review, but not price correction.

## Batch outputs

- normalized comparable edges
- repaired peer contributions
- repaired candidate forecast diagnostics
- route summary
- owner methodology review table
- summary JSON

## Controls

- Canonical IDs are normalized to their terminal TCGplayer numeric identifier.
- Selected-comparable files take precedence over broader pair-score files.
- Duplicate target/peer edges are removed.
- Peer returns remain retrospective diagnostics only.
- Forecast and purchase authorizations remain false.
- Extreme prices and forecasts are visible and are not clipped.

## Interpretation

A successful audit proves that comparable edges can be mapped to available peer histories and that candidate route calculations are more complete. It does not prove forecast accuracy, establish historical decision-time availability, approve the numeric methodology, or authorize purchases.
