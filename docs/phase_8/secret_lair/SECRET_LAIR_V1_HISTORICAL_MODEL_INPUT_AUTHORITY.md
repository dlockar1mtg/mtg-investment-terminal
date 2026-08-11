# Secret Lair V1 — Historical Model Input Authority

## Status

HISTORICAL_TCG_MARKET_INPUT_AUTHORITY_CERTIFIED

## Source scope

Secret Lair V1 production history is restricted to reconciled TCG market-price observations.

eBay history is not production authority for V1.

TCG low price is preserved as supporting evidence and is not automatically substituted for missing market price.

## Historical reconciliation

Candidate historical rows:

18107

Accepted TCG market-history rows:

16253

Rejected rows:

1854

Current snapshot products with accepted historical observations:

816

Current snapshot products with no accepted historical market history:

177

## Temporal validation support

Products with at least 1 year of observed history:

547

Products with at least 3 years of observed history:

0

Products with at least 5 years of observed history:

0

The 1-year horizon may proceed to direct temporal out-of-sample model validation where product history supports it.

Three-year and five-year outputs may not be represented as directly validated Secret Lair forecasts unless subsequent evidence establishes sufficient direct temporal support. Unsupported long horizons must remain scenario-labeled.

## Dynamic universe

No fixed Secret Lair product count is authoritative.

New Secret Lair products are expected.

Products are not permanently excluded merely because their history is shorter.

Each product receives a governed method class based on available evidence.

## Next gate

SL3C_SECRET_LAIR_FEATURE_MATRIX_AND_METHOD_ASSIGNMENT