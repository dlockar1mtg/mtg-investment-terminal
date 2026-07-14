# Secret Lair Discovery Architecture

Discovery never writes to the production registry. It publishes candidate records and can optionally stage them for the 2.7.0 acquisition and 2.6.2 guarded backfill workflows.

Supported parsers: official product-link HTML, normalized JSON, Scryfall card metadata, and MTGJSON set metadata. Card metadata remains review-only until a purchasable product variant is confirmed.
