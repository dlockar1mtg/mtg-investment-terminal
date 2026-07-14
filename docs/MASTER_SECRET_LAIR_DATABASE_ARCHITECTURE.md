# Master Secret Lair Database Architecture
Official store evidence establishes product identity and URLs. TCGCSV supplies
sealed-product identifiers and current market prices. Scryfall supplies card-level
Secret Lair metadata. The engine merges evidence into stable product identities,
never auto-imports uncertain records into the production registry, and stores each
observed price snapshot without fabricating missing history.
