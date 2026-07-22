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
    / "secret_lair_official_research_batch_02_2026-07-22.csv"
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
    / "secret_lair_official_bundle_evidence_seed_02a_2026-07-22.csv"
)

PARENT_COVERAGE_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_bundle_parent_coverage_02a_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_bundle_evidence_seed_02a_summary_2026-07-22.json"
)

CAPTURE_DATE = "2026-07-22"

EVIDENCE_COLUMNS = [
    "evidence_batch",
    "research_group",
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
    "research_group",
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
    source_url: str,
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
        "component_quantity": 1,
        "official_source_domain": (
            "secretlair.wizards.com"
        ),
        "official_source_url": source_url,
        "source_capture_date": CAPTURE_DATE,
        "evidence_excerpt": (
            "Official contents list includes "
            f"1x {component_name}."
        ),
    }


def add_components(
    rows: list[dict[str, Any]],
    *,
    parent_id: str,
    official_parent_name: str,
    source_url: str,
    components: list[
        tuple[str, str, str]
    ],
) -> None:
    for ordinal, (
        component_name,
        official_finish,
        local_finish,
    ) in enumerate(
        components,
        start=1,
    ):
        rows.append(
            evidence_record(
                parent_id=parent_id,
                official_parent_name=(
                    official_parent_name
                ),
                ordinal=ordinal,
                component_name=component_name,
                official_finish=official_finish,
                local_finish=local_finish,
                source_url=source_url,
            )
        )


def build_evidence_seed() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    add_components(
        rows,
        parent_id="493796",
        official_parent_name=(
            "March of the Machine Bundle"
        ),
        source_url=(
            "https://secretlair.wizards.com/"
            "us/en/product/814014/"
            "march-of-the-machine-bundle"
        ),
        components=[
            (
                "Showcase: March of the Machine Vol. 1",
                "halo_foil",
                "halo_foil",
            ),
            (
                "Showcase: March of the Machine Vol. 2",
                "halo_foil",
                "halo_foil",
            ),
            (
                "Showcase: March of the Machine Vol. 3",
                "halo_foil",
                "halo_foil",
            ),
        ],
    )

    add_components(
        rows,
        parent_id="551411",
        official_parent_name=(
            "Hatsune Miku: Sakura Superstar Bundle"
        ),
        source_url=(
            "https://secretlair.wizards.com/"
            "us/en/product/965785/"
            "hatsune-miku-sakura-superstar-bundle"
        ),
        components=[
            (
                "Secret Lair x Hatsune Miku: "
                "Sakura Superstar EN Foil Edition",
                "foil",
                "rainbow_foil",
            ),
            (
                "Secret Lair x Hatsune Miku: "
                "Sakura Superstar JP Foil Edition",
                "foil",
                "rainbow_foil",
            ),
            (
                "Secret Lair x Hatsune Miku: "
                "Sakura Superstar EN",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Secret Lair x Hatsune Miku: "
                "Sakura Superstar JP",
                "nonfoil",
                "nonfoil",
            ),
        ],
    )

    add_components(
        rows,
        parent_id="624751",
        official_parent_name=(
            "Desk Fort Made of Non-Foils Bundle"
        ),
        source_url=(
            "https://secretlair.wizards.com/"
            "us/en/product/1161120/"
            "desk-fort-made-of-non-foils-bundle"
        ),
        components=[
            (
                "Secret Lair x SpongeBob SquarePants: "
                "Legends of Bikini Bottom",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Secret Lair x SpongeBob SquarePants: "
                "Internet Sensation",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Secret Lair x SpongeBob SquarePants: "
                "Lands Under the Sea",
                "nonfoil",
                "nonfoil",
            ),
            (
                "They Grow Up So Fast",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Garden Buds",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Tragic Romance",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Twisted Toons",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Pick 'Em and Stick 'Em",
                "nonfoil",
                "nonfoil",
            ),
            (
                "Secret Lair High: Class of '87",
                "nonfoil",
                "nonfoil",
            ),
        ],
    )

    all_four_u_base_names = [
        "Artist Series: Mark Poole",
        "Dan Frazier Is Back: The Allied Signets",
        "Dan Frazier Is Back: The Enemy Signets",
        "Mother's Day 2021",
        "Phyrexian Praetors: Compleat Edition",
        "Saturday Morning D&D",
        "Special Guest: Fiona Staples",
        "Special Guest: Jen Bartel",
    ]

    all_four_u_components: list[
        tuple[str, str, str]
    ] = []

    for base_name in all_four_u_base_names:
        all_four_u_components.extend(
            [
                (
                    base_name,
                    "nonfoil",
                    "nonfoil",
                ),
                (
                    base_name + " Foil Edition",
                    "foil",
                    "traditional_foil",
                ),
            ]
        )

    add_components(
        rows,
        parent_id="242354",
        official_parent_name="All 4 U Bundle",
        source_url=(
            "https://secretlair.wizards.com/"
            "us/en/product/648197/"
            "all-4-u-bundle"
        ),
        components=all_four_u_components,
    )

    return rows


def main() -> int:
    research_batch = read_csv(
        RESEARCH_BATCH_PATH
    )

    if len(research_batch) != 20:
        raise RuntimeError(
            "Expected 20 Research Batch 02 parents, "
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

    if len(research_by_parent_id) != 20:
        raise RuntimeError(
            "Research Batch 02 contains duplicate "
            "or blank parent IDs."
        )

    evidence_seed = build_evidence_seed()

    if len(evidence_seed) != 32:
        raise RuntimeError(
            "Expected 32 official evidence rows, "
            f"found {len(evidence_seed)}."
        )

    expected_parent_ids = {
        "493796",
        "551411",
        "624751",
        "242354",
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
            "Evidence parent identity set does not "
            "match the expected four parents."
        )

    missing_research_parents = (
        expected_parent_ids
        - set(research_by_parent_id)
    )

    if missing_research_parents:
        raise RuntimeError(
            "Evidence parents are absent from "
            "Research Batch 02: "
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
                "evidence_batch": "02A",
                "research_group": clean(
                    research_parent.get(
                        "research_group"
                    )
                ),
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
                "official_component_finish_class": clean(
                    seed.get(
                        "official_component_finish_class"
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
            row[
                "local_parent_product_name"
            ].lower(),
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
                "evidence_batch": "02A",
                "research_group": clean(
                    research_parent.get(
                        "research_group"
                    )
                ),
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

    if len(parent_rows) != 4:
        raise RuntimeError(
            "Expected four parent coverage rows, "
            f"found {len(parent_rows)}."
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

    group_counts = Counter(
        row["research_group"]
        for row in parent_rows
    )

    parent_component_counts = Counter(
        int(row["official_component_rows"])
        for row in parent_rows
    )

    total_component_quantity = sum(
        int(row["component_quantity"])
        for row in evidence_rows
    )

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    summary = {
        "schema_version": "10.5R.3.6C.2",
        "generated_at_utc": generated_at,
        "certification_status": "PASS",
        "evidence_batch": "02A",
        "official_parent_rows": len(
            parent_rows
        ),
        "official_component_evidence_rows": (
            len(evidence_rows)
        ),
        "official_total_component_quantity": (
            total_component_quantity
        ),
        "unique_parent_product_ids": len(
            evidence_parent_ids
        ),
        "finish_taxonomy_discrepancy_rows": (
            finish_discrepancy_rows
        ),
        "research_group_counts": dict(
            sorted(group_counts.items())
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
        "Phase 10.5R.3.6C.2 Secret Lair "
        "Official Evidence Seed 02A"
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
        f"{total_component_quantity}"
    )
    print(
        "Finish-taxonomy discrepancy rows: "
        f"{finish_discrepancy_rows}"
    )
    print()
    print("Research groups:")

    for group_name, count in sorted(
        group_counts.items()
    ):
        print(f"  {group_name}: {count}")

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
        "OFFICIAL EVIDENCE SEED 02A STATUS: PASS"
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