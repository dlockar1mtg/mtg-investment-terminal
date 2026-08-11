# Secret Lair V1 â€” eBay Query and Acceptance Contract

## Status

EBAY_QUERY_AND_ACCEPTANCE_CONTRACT_CERTIFIED

## Acquisition universe

The acquisition query plan contains exactly 993 registry-ready Secret Lair seed identities.

This is an acquisition seed, not final canonical Secret Lair V1 universe certification.

## Credential capability

Live credential capability at certification time:

READY

Credential values were not printed or persisted.

The eBay client may obtain EBAY_CLIENT_ID and EBAY_CLIENT_SECRET from either the current process environment or the repository-local .env file.

## Search policy

Search recall and match acceptance are separate operations.

Each governed acquisition-seed product receives a deterministic query ladder using the Secret Lair product identity plus sealed context, and finish/configuration terms where those attributes are known.

A query hit is never automatically an accepted match.

## V1 identity policy

The target is the sealed commercial Secret Lair SKU.

- Foil and nonfoil remain separate assets.
- Bundles remain distinct assets.
- Festival-in-a-Box products remain distinct commercial configurations.
- Commander decks remain distinct commercial configurations.
- Individual cards are not target assets.
- Opened or incomplete products are not target assets.
- Bundle/component prices are not decomposed into synthetic target prices.

## Match classification

Secret Lair V1 does not inherit the legacy numeric match-score thresholds.

Classification is predicate-based:

- ACCEPT_EXACT_OR_STRONG_IDENTITY
- REVIEW_AMBIGUOUS_IDENTITY
- REJECT_WRONG_PRODUCT_FORM
- REJECT_WRONG_FINISH
- REJECT_WRONG_CONFIGURATION
- REJECT_OPENED_OR_INCOMPLETE
- REJECT_INDIVIDUAL_CARD
- REJECT_UNRELATED_PRODUCT

Explicit contradictions reject.

Ambiguity goes to review rather than acceptance.

## Evidence capture

Raw listing evidence must preserve source query, item ID, title, URL, item price, shipping, landed price, currency, buying options, condition, seller hash, observation timestamp, and classification reason.

Raw listing acquisition does not itself grant eBay price or liquidity authority.

## Legacy mechanics

Existing OAuth, Browse API, item-deduplication, landed-price, seller-hashing, fail-fast rate-limit, and resume mechanics may be adapted.

Legacy Secret Lair match scores and thresholds are not V1 authority.

## Downstream authority

NOT AUTHORIZED:

- final canonical universe;
- eBay production current price;
- eBay production liquidity;
- TCG/eBay blending;
- unified current-price authority;
- model tournament;
- forecasts;
- ranking;
- purchase recommendation;
- UIP delivery;
- automatic execution.

## Next gate

SL2C3_FRESH_EBAY_RAW_LISTING_ACQUISITION
## SL-2C.2A Query-Plan Schema Correction

Contract version: 1.0.1

The original SL-2C.2 plan correctly calculated seven-query ladders for 81 products but serialized only query_01 through query_06.

The correction adds query_07 to the governed query-plan schema.

Certified invariants:

- acquisition population remains 993 products;
- all product query_count values are unchanged;
- query_01 through query_06 are unchanged;
- exactly 81 products require query_07;
- total theoretical Browse calls remain 5,555;
- legacy numeric matching remains unauthorized;
- raw listing evidence remains non-authoritative;
- the failed Wave-1 run directory is preserved unchanged.

The correction was required after the first Wave-1 attempt failed closed at SL-0170AA960296CD before that product executed an eBay search.