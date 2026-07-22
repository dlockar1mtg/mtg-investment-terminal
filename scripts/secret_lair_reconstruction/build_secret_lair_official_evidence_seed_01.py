from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

RESEARCH_BATCH_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_official_research_batch_01_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

EVIDENCE_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_bundle_evidence_seed_01_2026-07-22.csv"
)

PARENT_COVERAGE_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_bundle_parent_coverage_01_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_bundle_evidence_seed_01_summary_2026-07-22.json"
)

CAPTURE_DATE = "2026-07-22"

EVIDENCE_COLUMNS = [
    "evidence_batch",
    "parent_tcgplayer_product_id",
    "parent_canonical_product_id",
    "local_parent_product_name",
    "official_parent_product_name",
    "parent_finish_class",
    "official_component_ordinal",
    "official_component_name",
    "official_component_finish_class",
    "local_expected_finish_class",
    "component_quantity",
    "official_source_domain",
    "official_source_url",
    "source_capture_date",
    "evidence_excerpt",
    "evidence_authority",
    "evidence_state",
    "resolved_component_tcgplayer_product_id",
    "component_resolution_state",
    "mapping_finalized",
    "derived_value_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]

PARENT_COLUMNS = [
    "evidence_batch",
    "parent_tcgplayer_product_id",
    "parent_canonical_product_id",
    "local_parent_product_name",
    "official_parent_product_name",
    "parent_finish_class",
    "official_component_rows",
    "official_total_component_quantity",
    "official_source_url",
    "official_evidence_complete",
    "local_component_resolution_complete",
    "mapping_finalized",
    "derived_value_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]


def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required input is missing: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return [
            {
                clean(key): clean(value)
                for key, value in row.items()
            }
            for row in csv.DictReader(handle)
        ]


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    column: row.get(column, "")
                    for column in columns
                }
            )


def evidence_record(
    *,
    parent_id: str,
    official_parent_name: str,
    ordinal: int,
    component_name: str,
    official_finish: str,
    local_finish: str,
    quantity: int,
    source_url: str,
    excerpt: str,
) -> dict[str, Any]:
    return {
        "parent_tcgplayer_product_id": parent_id,
        "official_parent_product_name": (
            official_parent_name
        ),
        "official_component_ordinal": ordinal,
        "official_component_name": component_name,
        "official_component_finish_class": (
            official_finish
        ),
        "local_expected_finish_class": (
            local_finish
        ),
        "component_quantity": quantity,
        "official_source_domain": (
            "secretlair.wizards.com"
        ),
        "official_source_url": source_url,
        "source_capture_date": CAPTURE_DATE,
        "evidence_excerpt": excerpt,
    }


def build_evidence_seed() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    rows.extend(
        [
            evidence_record(
                parent_id="632031",
                official_parent_name=(
                    "EVERYTHING IS ON FIRE "
                    "Playset Bundle Foil Edition"
                ),
                ordinal=1,
                component_name=(
                    "EVERYTHING IS ON FIRE "
                    "Foil Edition"
                ),
                official_finish="foil",
                local_finish="rainbow_foil",
                quantity=4,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1231835/"
                    "everything-is-on-fire-playset-"
                    "bundle-foil-edition"
                ),
                excerpt=(
                    "Contents: 4x EVERYTHING IS ON "
                    "FIRE Foil Edition."
                ),
            ),
            evidence_record(
                parent_id="632029",
                official_parent_name=(
                    "EVERYTHING IS ON FIRE "
                    "Playset Bundle Raised Foil Edition"
                ),
                ordinal=1,
                component_name=(
                    "EVERYTHING IS ON FIRE "
                    "Raised Foil Edition"
                ),
                official_finish="raised_foil",
                local_finish="raised_foil",
                quantity=4,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1231834/"
                    "everything-is-on-fire-playset-"
                    "bundle-raised-foil-edition"
                ),
                excerpt=(
                    "Contents: 4x EVERYTHING IS ON "
                    "FIRE Raised Foil Edition."
                ),
            ),
            evidence_record(
                parent_id="632023",
                official_parent_name=(
                    "Secret Lair x KEXP: Where the "
                    "Music Matters Bundle"
                ),
                ordinal=1,
                component_name=(
                    "Secret Lair x KEXP: Where the "
                    "Music Matters"
                ),
                official_finish="nonfoil",
                local_finish="nonfoil",
                quantity=5,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1245204/"
                    "secret-lair-x-kexp-where-the-"
                    "music-mattersr-bundle"
                ),
                excerpt=(
                    "Contents: 5x Secret Lair x KEXP: "
                    "Where the Music Matters."
                ),
            ),
            evidence_record(
                parent_id="632021",
                official_parent_name=(
                    "Secret Lair x KEXP: Where the "
                    "Music Matters Foil Bundle"
                ),
                ordinal=1,
                component_name=(
                    "Secret Lair x KEXP: Where the "
                    "Music Matters Foil Edition"
                ),
                official_finish="foil",
                local_finish="rainbow_foil",
                quantity=5,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1231833/"
                    "secret-lair-x-kexp-where-the-"
                    "music-mattersr-foil-bundle"
                ),
                excerpt=(
                    "Contents: 5x Secret Lair x KEXP: "
                    "Where the Music Matters Foil Edition."
                ),
            ),
            evidence_record(
                parent_id="632025",
                official_parent_name=(
                    "vroooOOOMMMMMM! Playset Bundle"
                ),
                ordinal=1,
                component_name="vroooOOOMMMMMM!",
                official_finish="nonfoil",
                local_finish="nonfoil",
                quantity=4,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1231839/"
                    "vroooooommmmmm-playset-bundle"
                ),
                excerpt=(
                    "Contents: 4x vroooOOOMMMMMM."
                ),
            ),
            evidence_record(
                parent_id="632027",
                official_parent_name=(
                    "vroooOOOMMMMMM! Playset Bundle "
                    "Foil Edition"
                ),
                ordinal=1,
                component_name=(
                    "vroooOOOMMMMMM! Foil Edition"
                ),
                official_finish="foil",
                local_finish="rainbow_foil",
                quantity=4,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1231838/"
                    "vroooooommmmmm-playset-bundle-"
                    "foil-edition"
                ),
                excerpt=(
                    "Contents: 4x vroooOOOMMMMMM! "
                    "Foil Edition."
                ),
            ),
            evidence_record(
                parent_id="632028",
                official_parent_name=(
                    "vroooOOOMMMMMM! Playset Bundle "
                    "Raised Foil Edition"
                ),
                ordinal=1,
                component_name=(
                    "vroooOOOMMMMMM! "
                    "Raised Foil Edition"
                ),
                official_finish="raised_foil",
                local_finish="raised_foil",
                quantity=4,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/1231837/"
                    "vroooooommmmmm-playset-bundle-"
                    "raised-foil-edition"
                ),
                excerpt=(
                    "Contents: 4x vroooOOOMMMMMM! "
                    "Raised Foil Edition."
                ),
            ),
        ]
    )

    places_foil = [
        "Secret Lair x Doctor Who: The Dalek Lands",
        "Meditations on Nature",
        "PixelLands_v02.jpg",
    ]

    for ordinal, component_name in enumerate(
        places_foil,
        start=1,
    ):
        rows.append(
            evidence_record(
                parent_id="518841",
                official_parent_name=(
                    "Places to Trick or Treat "
                    "Foil Lands Bundle"
                ),
                ordinal=ordinal,
                component_name=(
                    component_name + " Foil Edition"
                ),
                official_finish="foil",
                local_finish="traditional_foil",
                quantity=1,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/872731/"
                    "places-to-trick-or-treat-"
                    "foil-lands-bundle"
                ),
                excerpt=(
                    "Contents list includes this "
                    "foil drop once."
                ),
            )
        )

    places_nonfoil = [
        "Secret Lair x Doctor Who: The Dalek Lands",
        "Meditations on Nature",
        "PixelLands_v02.jpg",
    ]

    for ordinal, component_name in enumerate(
        places_nonfoil,
        start=1,
    ):
        rows.append(
            evidence_record(
                parent_id="518840",
                official_parent_name=(
                    "Places to Trick or Treat "
                    "Non-Foil Lands Bundle"
                ),
                ordinal=ordinal,
                component_name=component_name,
                official_finish="nonfoil",
                local_finish="nonfoil",
                quantity=1,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/872732/"
                    "places-to-trick-or-treat-"
                    "non-foil-lands-bundle"
                ),
                excerpt=(
                    "Contents list includes this "
                    "non-foil drop once."
                ),
            )
        )

    outlaws_components = [
        "Poker Faces",
        (
            "Outlaw Anthology Vol. 1: "
            "Rebellious Renegades"
        ),
        (
            "Outlaw Anthology Vol. 2: "
            "Sinister Scoundrels"
        ),
        "Showcase: Outlaws of Thunder Junction",
    ]

    for ordinal, component_name in enumerate(
        outlaws_components,
        start=1,
    ):
        rows.append(
            evidence_record(
                parent_id="551419",
                official_parent_name=(
                    "Outlaws of Thunder Junction "
                    "Bundle Non-Foil Edition"
                ),
                ordinal=ordinal,
                component_name=component_name,
                official_finish="nonfoil",
                local_finish="nonfoil",
                quantity=1,
                source_url=(
                    "https://secretlair.wizards.com/"
                    "us/en/product/965782/"
                    "outlaws-of-thunder-junction-"
                    "bundle-non-foil-edition"
                ),
                excerpt=(
                    "Official contents list includes "
                    "this non-foil drop once."
                ),
            )
        )

    return rows


def main() -> int:
    research_batch = read_csv(
        RESEARCH_BATCH_PATH
    )

    if len(research_batch) != 30:
        raise RuntimeError(
            "Expected 30 research-batch parents, "
            f"found {len(research_batch)}."
        )

    research_by_parent_id = {
        clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        ): row
        for row in research_batch
    }

    if len(research_by_parent_id) != 30:
        raise RuntimeError(
            "Research batch contains duplicate or "
            "blank parent product IDs."
        )

    evidence_seed = build_evidence_seed()

    if len(evidence_seed) != 17:
        raise RuntimeError(
            "Expected 17 official evidence rows, "
            f"found {len(evidence_seed)}."
        )

    expected_parent_ids = {
        "632031",
        "632029",
        "632023",
        "632021",
        "632025",
        "632027",
        "632028",
        "518841",
        "518840",
        "551419",
    }

    evidence_parent_ids = {
        clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        for row in evidence_seed
    }

    if evidence_parent_ids != expected_parent_ids:
        raise RuntimeError(
            "Official evidence parent identity set "
            "does not match the expected ten parents."
        )

    missing_research_parents = (
        expected_parent_ids
        - set(research_by_parent_id)
    )

    if missing_research_parents:
        raise RuntimeError(
            "Official evidence parents are absent "
            "from Research Batch 01: "
            + ", ".join(
                sorted(missing_research_parents)
            )
        )

    evidence_rows: list[dict[str, Any]] = []

    for seed in evidence_seed:
        parent_id = clean(
            seed.get(
                "parent_tcgplayer_product_id"
            )
        )

        research_parent = (
            research_by_parent_id[parent_id]
        )

        evidence_rows.append(
            {
                "evidence_batch": "01",
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_canonical_product_id": clean(
                    research_parent.get(
                        "parent_canonical_product_id"
                    )
                ),
                "local_parent_product_name": clean(
                    research_parent.get(
                        "parent_product_name"
                    )
                ),
                "official_parent_product_name": clean(
                    seed.get(
                        "official_parent_product_name"
                    )
                ),
                "parent_finish_class": clean(
                    research_parent.get(
                        "parent_finish_class"
                    )
                ),
                "official_component_ordinal": (
                    seed[
                        "official_component_ordinal"
                    ]
                ),
                "official_component_name": clean(
                    seed.get(
                        "official_component_name"
                    )
                ),
                "official_component_finish_class": (
                    clean(
                        seed.get(
                            "official_component_finish_class"
                        )
                    )
                ),
                "local_expected_finish_class": clean(
                    seed.get(
                        "local_expected_finish_class"
                    )
                ),
                "component_quantity": (
                    seed["component_quantity"]
                ),
                "official_source_domain": clean(
                    seed.get(
                        "official_source_domain"
                    )
                ),
                "official_source_url": clean(
                    seed.get(
                        "official_source_url"
                    )
                ),
                "source_capture_date": clean(
                    seed.get(
                        "source_capture_date"
                    )
                ),
                "evidence_excerpt": clean(
                    seed.get(
                        "evidence_excerpt"
                    )
                ),
                "evidence_authority": (
                    "official_wizards_product_page"
                ),
                "evidence_state": (
                    "official_evidence_captured"
                ),
                "resolved_component_tcgplayer_product_id": (
                    ""
                ),
                "component_resolution_state": (
                    "pending_local_component_resolution"
                ),
                "mapping_finalized": "false",
                "derived_value_allowed": "false",
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

    evidence_rows.sort(
        key=lambda row: (
            row["local_parent_product_name"].lower(),
            int(
                row[
                    "official_component_ordinal"
                ]
            ),
        )
    )

    parent_rows: list[dict[str, Any]] = []

    for parent_id in sorted(
        expected_parent_ids,
        key=lambda value: (
            research_by_parent_id[value][
                "parent_product_name"
            ].lower()
        ),
    ):
        parent_evidence = [
            row
            for row in evidence_rows
            if row[
                "parent_tcgplayer_product_id"
            ]
            == parent_id
        ]

        source_urls = {
            row["official_source_url"]
            for row in parent_evidence
        }

        if len(source_urls) != 1:
            raise RuntimeError(
                "Expected one official source URL "
                f"for parent {parent_id}."
            )

        research_parent = (
            research_by_parent_id[parent_id]
        )

        parent_rows.append(
            {
                "evidence_batch": "01",
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_canonical_product_id": clean(
                    research_parent.get(
                        "parent_canonical_product_id"
                    )
                ),
                "local_parent_product_name": clean(
                    research_parent.get(
                        "parent_product_name"
                    )
                ),
                "official_parent_product_name": (
                    parent_evidence[0][
                        "official_parent_product_name"
                    ]
                ),
                "parent_finish_class": clean(
                    research_parent.get(
                        "parent_finish_class"
                    )
                ),
                "official_component_rows": len(
                    parent_evidence
                ),
                "official_total_component_quantity": (
                    sum(
                        int(
                            row[
                                "component_quantity"
                            ]
                        )
                        for row in parent_evidence
                    )
                ),
                "official_source_url": (
                    next(iter(source_urls))
                ),
                "official_evidence_complete": (
                    "true"
                ),
                "local_component_resolution_complete": (
                    "false"
                ),
                "mapping_finalized": "false",
                "derived_value_allowed": "false",
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

    if len(parent_rows) != 10:
        raise RuntimeError(
            "Expected ten official-evidence "
            f"parent rows, found {len(parent_rows)}."
        )

    write_csv(
        EVIDENCE_PATH,
        evidence_rows,
        EVIDENCE_COLUMNS,
    )

    write_csv(
        PARENT_COVERAGE_PATH,
        parent_rows,
        PARENT_COLUMNS,
    )

    finish_discrepancy_rows = sum(
        1
        for row in evidence_rows
        if row[
            "official_component_finish_class"
        ]
        != row[
            "local_expected_finish_class"
        ]
    )

    parent_component_counts = Counter(
        int(row["official_component_rows"])
        for row in parent_rows
    )

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    summary = {
        "schema_version": "10.5R.3.6B.1",
        "generated_at_utc": generated_at,
        "certification_status": "PASS",
        "evidence_batch": "01",
        "official_parent_rows": len(
            parent_rows
        ),
        "official_component_evidence_rows": (
            len(evidence_rows)
        ),
        "unique_parent_product_ids": len(
            evidence_parent_ids
        ),
        "official_total_component_quantity": (
            sum(
                int(
                    row[
                        "component_quantity"
                    ]
                )
                for row in evidence_rows
            )
        ),
        "finish_taxonomy_discrepancy_rows": (
            finish_discrepancy_rows
        ),
        "parent_component_row_distribution": {
            str(key): value
            for key, value in sorted(
                parent_component_counts.items()
            )
        },
        "governance": {
            "network_requests_performed_by_script": (
                False
            ),
            "official_evidence_captured": True,
            "component_ids_resolved": False,
            "component_mappings_finalized": False,
            "component_quantities_derived": False,
            "derived_bundle_values_created": False,
            "observed_prices_overwritten": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "official_evidence_seed": (
                EVIDENCE_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "parent_coverage": (
                PARENT_COVERAGE_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
        },
    }

    SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print(
        "Phase 10.5R.3.6B.1 Secret Lair "
        "Official Evidence Seed 01"
    )
    print("=" * 76)
    print(
        f"Official parent rows: "
        f"{len(parent_rows)}"
    )
    print(
        "Official component evidence rows: "
        f"{len(evidence_rows)}"
    )
    print(
        "Official total component quantity: "
        f"{sum(int(row['component_quantity']) for row in evidence_rows)}"
    )
    print(
        "Finish-taxonomy discrepancy rows: "
        f"{finish_discrepancy_rows}"
    )
    print()
    print("Official evidence captured: YES")
    print("Component IDs resolved: NO")
    print("Component mappings finalized: NO")
    print("Derived bundle values created: NO")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print()
    print(
        "OFFICIAL EVIDENCE SEED STATUS: PASS"
    )
    print(
        "Summary: "
        + SUMMARY_PATH
        .relative_to(ROOT)
        .as_posix()
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())