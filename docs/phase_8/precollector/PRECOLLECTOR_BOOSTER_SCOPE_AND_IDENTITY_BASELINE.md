# Pre-Collector Booster Scope and Identity Baseline

## Document control

- Repository: `dlockar1mtg/mtg-investment-terminal`
- Branch: `phase-8.3-precollector-scope-governance`
- Decision version: `1.0.0`
- Owner approval date: `2026-08-02`
- Operating timezone: `America/Chicago`
- Governing decision: `config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json`

## Purpose

This document establishes the first owner-approved scope baseline for the Pre-Collector Booster Box lane. It defines which products may enter the candidate-universe inventory. It does not authorize source certification, forecasting, ranking, purchase recommendations, or automatic execution.

The Collector Booster lane remains a structural governance template only. Collector methods, weights, thresholds, source hierarchy, comparable rules, eligibility rules, ranking policy, and purchase policy are not inherited by this lane without separate approval and recertification.

## Primary scope decision

The lane does **not** use a fixed calendar cutoff such as “all products released before 2019.” Eligibility is determined product by product.

A product may enter the initial candidate universe only when all of the following are true:

1. It is an English-language product.
2. It is a complete factory-sealed booster box.
3. Its seals and box are not materially damaged.
4. It is not a Collector Booster box.
5. It is not a Draft Booster box.
6. It is not a Play Booster box.
7. The associated set or release does not have a Collector Booster option.

The presence of a Collector Booster option excludes the associated booster-box product from this lane even when another booster format also exists for that set.

## Included product families

The following product families may be included when they satisfy every primary scope condition:

- regular expansion booster boxes;
- Masters booster boxes;
- supplemental-set booster boxes;
- premium-set booster boxes;
- Un-set booster boxes;
- other complete factory-sealed booster boxes that are neither Collector, Draft, nor Play Booster products.

Supplemental or specialty status alone does not disqualify a product. The governed unit must still be a complete sealed booster box.

## Explicit exclusions

The initial universe excludes:

- all Collector Booster boxes;
- all Draft Booster boxes, including those released during the early Collector Booster era;
- all Play Booster boxes;
- foreign-language boxes;
- foreign first-edition printings;
- loose booster packs;
- tournament packs;
- starter decks;
- theme decks;
- special sealed cases;
- opened or partially opened products;
- products with damaged seals;
- materially damaged boxes.

## Vintage high-price products

Alpha, Beta, Unlimited, Revised, Fourth Edition, and other expensive vintage booster boxes are not automatically excluded from the initial inventory.

Their initial treatment is:

- preserve them as governed candidate-universe rows when they satisfy the scope;
- do not presume they are practical purchase candidates;
- measure their price, liquidity, scarcity, and evidence profile;
- identify whether they distort comparable groups, model fitting, normalization, or ranking competition;
- exclude, segment, or quarantine them only through a documented owner decision supported by evidence.

This preserves evidence without forcing very expensive products into the eventual practical purchase universe.

## Canonical identity baseline

Each governed asset must distinguish at minimum:

- set or release;
- edition or printing;
- booster-box configuration;
- English-language status;
- factory-sealed status;
- acceptable condition status.

Foreign-language variants are excluded rather than represented as separate governed assets.

Authentication is not required. Authenticated and unauthenticated intact boxes are not separate governed asset classes at this stage. Authentication or provenance may later be retained as optional evidence fields, but they must not be mandatory identity keys unless separately approved.

Damaged products are excluded rather than modeled as a separate condition class.

## Interpretation controls

### No calendar shortcut

A release year may be retained as a feature, but it cannot be used by itself to admit or reject a product.

### No format-name shortcut without verification

The universe builder must verify the actual booster format and whether the set had a Collector Booster option. Product names alone may be insufficient because marketplace naming is inconsistent.

### No automatic vintage exclusion

High price alone does not remove a product from the evidence universe. Practical-investment eligibility is a later decision authority and must remain separate from source and identity authority.

### No Collector policy inheritance

This scope approval does not approve Collector ranking weights, purchase thresholds, comparable pools, liquidity measures, or forecast methods for Pre-Collector products.

## Candidate-universe inventory requirements

The next stage must produce a row-level candidate universe with, at minimum:

- canonical product identifier;
- product name;
- set or release name;
- release date;
- edition or printing;
- language;
- booster format;
- full booster-box indicator;
- factory-sealed eligibility indicator;
- damaged-product exclusion indicator;
- Collector Booster option indicator for the associated release;
- Draft Booster indicator;
- Play Booster indicator;
- product-family classification;
- initial inclusion status;
- inclusion or exclusion reason;
- source path or source reference for each classification;
- unresolved review status where evidence is insufficient.

The inventory must fail closed on unresolved identity, format, language, or sealed-product classification. An unresolved product may remain in a review queue but may not enter forecasting.

## Required next owner decisions

The following decisions remain open and are not implied by this scope approval:

1. Authoritative source hierarchy for product identity and booster-format classification.
2. Authoritative sources for current executable price and realized sales.
3. Minimum condition evidence required from marketplace listings.
4. Treatment of shipping, taxes, buyer premiums, and selling fees.
5. Historical reconstruction rules for sparse vintage transactions.
6. Liquidity and supply measures.
7. Comparable taxonomy and vintage-product segmentation.
8. Forecast routes and calibration methods.
9. Ranking factors, weights, penalties, and eligibility.
10. Purchase thresholds, entry ceilings, maximum quantities, and human-review requirements.

## Authorization state

- Candidate-universe inventory design: **authorized**.
- Candidate-universe evidence collection: **authorized only under the approved scope and existing MTG governance controls**.
- Forecast generation: **not authorized**.
- Ranking execution: **not authorized**.
- Purchase recommendation generation: **not authorized**.
- Automatic purchase execution: **not authorized**.

## Next governed stage

Build and certify the Pre-Collector candidate product-universe inventory. The inventory must show exactly which products qualify under the product-level format rule and must preserve explicit exclusion reasons for Collector, Draft, Play, foreign-language, loose, damaged, and non-box products.
