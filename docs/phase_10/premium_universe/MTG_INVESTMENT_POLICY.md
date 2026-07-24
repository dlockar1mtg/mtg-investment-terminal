# Premium MTG Investment Universe Policy

## Purpose

The MTG Investment Terminal models a deliberately curated universe of
premium sealed Magic: The Gathering products.

The platform does not attempt to model every Magic product. Products are
included only when they align with the user's long-term premium sealed
investment strategy.

## Core eligible classes

### 1. Collector Booster Displays

Include sealed Collector Booster Displays, Collector Booster Boxes, and
equivalent marketplace naming variants.

Collector Booster products may use terms including:

- Collector Booster Display
- Collector Booster Box
- Collector Booster Display Box
- Collector Booster Case Break Display

The eligible unit must be one sealed retail display, not:

- a single booster pack;
- a sample pack;
- an empty display box;
- a case containing multiple displays;
- a damaged or opened product.

### 2. Legacy Premium Booster Boxes

Include sealed booster boxes from the era before Collector Booster
Displays became the primary premium sealed product.

A legacy booster candidate must:

- predate the Collector Booster era;
- represent a complete sealed booster display or booster box;
- not be a modern Draft, Play, or Set Booster product;
- not be a single pack, case, bundle, deck, or accessory.

Release-date evidence is required before final certification as a legacy
booster box.

### 3. Multi-card Secret Lair Products

Include sealed Secret Lair releases containing multiple collectible
cards.

Preferred eligible Secret Lair products include:

- standard multi-card drops;
- foil and non-foil multi-card variants;
- Artist Series drops;
- Universes Beyond and licensed collaborations;
- premium multi-card specialty drops.

Single-card Secret Lair releases are excluded by default.

A Secret Lair record with unknown card count remains under review rather
than being automatically included.

## Explicit exclusions

The following products are excluded by default:

- modern Draft Booster Displays;
- Play Booster Displays;
- Set Booster Displays;
- individual booster packs;
- sample packs;
- booster cases;
- Commander decks;
- preconstructed decks;
- bundles and gift bundles;
- prerelease kits;
- theme boosters;
- Jumpstart products;
- accessories;
- tokens;
- empty packaging;
- opened or damaged products;
- single-card Secret Lair releases.

## Eligibility statuses

Every candidate receives one status:

- `eligible`
- `excluded`
- `review_required`
- `missing_metadata`

## Investment classes

Eligible and candidate records use these investment classes:

- `collector_booster_display`
- `legacy_booster_box`
- `secret_lair_multi_card`
- `excluded`
- `unclassified`

## Evidence standard

A product must not be marked eligible solely because its name contains
a broad term such as "booster."

Classification should consider, when available:

- canonical product type;
- product name;
- release date;
- release year;
- sealed unit configuration;
- number of packs;
- Secret Lair card count;
- language;
- edition or variant;
- authoritative marketplace identifiers.

## Conservative classification

When required evidence is absent, the classifier must use
`review_required` or `missing_metadata`.

The classifier must not silently infer:

- a release year;
- a Secret Lair card count;
- sealed condition;
- box-versus-case configuration;
- product language.

## Downstream use

Only certified `eligible` products may enter:

- historical price acquisition;
- supply and sales intelligence;
- forecast generation;
- deal sourcing;
- purchase recommendations;
- Universal Investment Platform exports.