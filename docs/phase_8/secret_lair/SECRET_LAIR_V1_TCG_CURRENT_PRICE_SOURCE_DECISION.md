# Secret Lair V1 — TCG Current-Price Source Rule Decision

## Status

TCG_SOURCE_RULE_CERTIFIED

## Evidence population

- Secret Lair seed products: 993
- Fresh TCG current-price rows: 894 products
- No fresh TCG current-price row: 99 products
- Positive TCG market_price: 787 products
- Fresh row but missing market_price: 107 products
- Positive low_price: 894 products
- Positive mid_price: 894 products
- Positive high_price: 894 products
- Positive direct_low_price: 0 products

## TCG source interpretation

### market_price

A positive TCG market_price is the preferred TCG market-value observation.

It does not by itself grant unified Secret Lair current-price authority because fresh eBay evidence and the final multi-source governance decision remain outstanding.

### low_price

A positive TCG low_price is preserved as listing-side / executable-price evidence.

It is not silently substituted for a missing market_price.

The empirical market-to-low comparison is centered near parity but contains substantial product-level dispersion, so treating both fields as interchangeable would change their economic meaning.

### mid_price and high_price

These fields are preserved as supporting descriptive TCG evidence.

They are not automatic replacements for missing market_price.

### direct_low_price

No positive direct_low_price observations were returned in the certification snapshot.

It is not part of Secret Lair V1 TCG authority at this stage.

## Missing-price treatment

Products missing TCG market_price or a complete TCG price row are not automatically excluded.

They remain explicit evidence gaps and may receive independent current-market and liquidity evidence from fresh eBay acquisition.

## Source separation

TCG and eBay observations remain separate.

No cross-source blending or unified source precedence has been authorized.

## Downstream authority

NOT AUTHORIZED:

- final canonical Secret Lair universe;
- unified production current-price authority;
- model tournament;
- production forecast;
- investment ranking;
- purchase recommendations;
- automatic execution;
- UIP delivery.

## Next gate

SL2C_FRESH_EBAY_MARKET_AND_LIQUIDITY_ACQUISITION