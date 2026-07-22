# Phase 10.5R.1B.2 - TCGCSV External Discovery Snapshot

## Status

**PASS - TCGCSV DISCOVERY SNAPSHOT COMPLETE**

This phase certifies source acquisition and candidate staging only.

It does not certify investment eligibility or complete Secret Lair drop
coverage.

## Source snapshot

The TCGCSV Magic category was detected as category ID 1.

The complete remote snapshot processed:

- 453 groups attempted;
- 453 successful groups;
- 0 failed groups;
- 116,546 product records;
- 116,546 unique TCGplayer product identifiers; and
- 0 duplicate snapshot identifiers.

No prices were requested during this discovery phase.

The raw product snapshot is retained locally and excluded from Git because
the file exceeds normal GitHub individual-file size limits.

The retrieval script, compact group snapshot, audit, and manifest remain in
the repository so the raw snapshot can be reproduced.

## Existing registry comparison

The existing registry contains 4,675 TCGplayer product identifiers.

Of those identifiers:

- 4,674 were present in the July 22, 2026 TCGCSV snapshot; and
- 1 was absent.

The absent record was:

- TCGplayer product ID: 704940
- Product: Path of Ancestry (2684)
- Registry type: Secret Lair Drop
- Registry status: review_required

The record was preserved. It was not removed, downgraded, or otherwise
modified.

## Sealed-product candidate extraction

The raw 116,546-product catalog produced two candidate tracks:

- 892 sealed-product candidates; and
- 4,347 Secret Lair product-level candidates.

Together, these tracks create a Premium MTG Candidate Universe containing
5,239 potential candidates.

The sealed-product candidate counts were:

- Commander deck: 210
- Sealed case: 205
- Bundle: 173
- Traditional Booster Display: 138
- Collector Booster Display: 78
- Draft Booster Display: 25
- Play Booster Display: 20
- Set Booster Display: 18
- Theme Booster Display: 14
- Jumpstart Booster Display: 11

All 5,239 records are potential discovery candidates. They are not approved
investment products, scored recommendations, or buy decisions.

## Secret Lair correction

The initial extraction identified 4,347 TCGCSV records associated with
Secret Lair-related group or product names.

Inspection showed that these records include:

- individual cards;
- foil variants;
- insert cards;
- bonus or related products;
- bundles; and
- other product-level records.

They do not represent 4,347 distinct sealed Secret Lair drops.

The 4,347 records are retained as a distinct Secret Lair product-level
candidate track and are also included in the combined Premium MTG Candidate
Universe.

Each record remains clearly labeled as a Secret Lair product rather than a
certified sealed drop. Eligibility, scoring, and buy status remain
unevaluated.

The sealed Secret Lair drop count remains not determined.

Secret Lair drop discovery will require a drop-level source such as official
Wizards release metadata, a curated Secret Lair catalog, or another source
that represents complete drops rather than individual cards.

## Classification safeguards

The extraction logic now:

- classifies cases before displays;
- recognizes Booster Box Case variants;
- distinguishes Play Booster Displays;
- distinguishes Set Booster Displays;
- excludes individual and sample booster packs;
- avoids treating every Secret Lair card as a sealed drop; and
- changes no registry or database state.

## Certification conclusion

Phase 10.5R.1B.2 certifies that:

1. the current TCGCSV Magic product catalog was captured successfully;
2. the source snapshot contains no duplicate product identifiers;
3. the existing registry was compared against the live source;
4. a 5,239-record Premium MTG Candidate Universe was created;
5. Play Booster and Set Booster products were preserved as candidates;
6. cases were separated from display boxes;
7. Secret Lair card-level evidence was separated from sealed-drop coverage;
8. no investment eligibility was changed; and
9. no production database records were changed.

## Next step

**Phase 10.5R.1B.3 - TCGCSV Candidate Reconciliation**

The next phase will compare the 5,239 Premium MTG candidates with the
existing registry using:

1. exact TCGplayer product identifiers;
2. normalized source names;
3. group and set identity;
4. packaging type;
5. language and edition variants; and
6. explicit conflict and review queues.

Secret Lair drop-level discovery will proceed through a separate source
track.
