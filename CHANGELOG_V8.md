# v8 Changelog

## Added
- `models/market_consensus.py`
- `data/reference/manual_price_sources.csv`
- `data/source_cache/consensus_prices.csv`
- `data/source_cache/all_price_sources.csv`
- Consensus price application before scoring

## Changed
- Model scores from consensus price instead of raw TCGCSV market price.
- Latest source cache uses consensus market prices.
- Product map includes consensus and outlier fields.

## Fixed / Mitigated
- TCGCSV case-like prices can be rejected when verified/manual source prices exist.
- LOTR can use ~$1,925 display price instead of ~$5,357 case-like value.
