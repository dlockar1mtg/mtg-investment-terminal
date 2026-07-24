from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

RESEARCH_BATCH_01_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_official_research_batch_01_2026-07-22.csv"
)

RESEARCH_CANDIDATES_01_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_official_research_batch_01_candidates_2026-07-22.csv"
)

CERTIFIED_PARENT_MAP_01_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_certified_parent_map_01_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

RESEARCH_BATCH_02_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_02_2026-07-22.csv"
)

RESEARCH_CANDIDATES_02_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_02_candidates_2026-07-22.csv"
)

RESEARCH_GROUPS_02_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_02_groups_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_02_summary_2026-07-22.json"
)

BATCH_COLUMNS = [
    "research_batch",
    "research_priority",
    "research_group",
    "parent_canonical_product_id",
    "parent_tcgplayer_product_id",
    "parent_product_name",
    "parent_product_class",
    "parent_finish_class",
    "candidate_rows",
    "strong_candidate_rows",
    "top_candidate_score",
    "official_search_term",
    "alternate_search_term",
    "preferred_official_domain",
    "research_state",
    "batch_01_certified",
    "mapping_finalized",
    "component_quantity_assigned",
    "derived_value_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]

CANDIDATE_COLUMNS = [
    "research_batch",
    "research_group",
    "parent_canonical_product_id",
    "parent_tcgplayer_product_id",
    "parent_product_name",
    "parent_finish_class",
    "candidate_rank",
    "candidate_tcgplayer_product_id",
    "candidate_product_name",
    "candidate_finish_class",
    "candidate_market_price",
    "candidate_low_price",
    "candidate_mid_price",
    "shared_distinctive_tokens",
    "exact_name_containment",
    "finish_compatibility",
    "candidate_score",
    "candidate_state",
    "official_confirmation_required",
]

GROUP_COLUMNS = [
    "research_batch",
    "research_group",
    "research_order",
    "parent_rows",
    "candidate_rows",
    "research_description",
    "official_evidence_captured",
    "mapping_finalized",
    "scoring_allowed",
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


def research_group(
    product_name: str,
) -> tuple[str, int, str]:
    name = product_name.lower()

    if "astrology lands" in name:
        return (
            "astrology_lands",
            1,
            "Verify the zodiac-specific sealed drop and finish for each bundle.",
        )

    if "march of the machine" in name:
        return (
            "march_of_the_machine",
            2,
            "Verify all March of the Machine volumes included in the bundle.",
        )

    if "hatsune miku" in name:
        return (
            "hatsune_miku",
            3,
            "Verify language and finish variants included in the Sakura Superstar bundle.",
        )

    if "our boss is on vacation" in name:
        return (
            "our_boss_is_on_vacation",
            4,
            "Verify every nonfoil drop included in the superdrop bundle.",
        )

    if (
        "all-natural" in name
        or "totally refreshing" in name
    ):
        return (
            "all_natural_totally_refreshing",
            5,
            "Verify the complete composition of the All 4 U bundle.",
        )

    return (
        "other_strong_candidate",
        6,
        "Verify the complete official bundle composition.",
    )


def main() -> int:
    batch_01 = read_csv(
        RESEARCH_BATCH_01_PATH
    )

    candidates_01 = read_csv(
        RESEARCH_CANDIDATES_01_PATH
    )

    certified_01 = read_csv(
        CERTIFIED_PARENT_MAP_01_PATH
    )

    if len(batch_01) != 30:
        raise RuntimeError(
            "Expected 30 Research Batch 01 parents, "
            f"found {len(batch_01)}."
        )

    if len(certified_01) != 10:
        raise RuntimeError(
            "Expected 10 certified Batch 01 parents, "
            f"found {len(certified_01)}."
        )

    certified_parent_ids = {
        clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        for row in certified_01
        if clean(
            row.get(
                "parent_mapping_certified"
            )
        ).lower()
        == "true"
    }

    if len(certified_parent_ids) != 10:
        raise RuntimeError(
            "Expected 10 uniquely certified parent IDs."
        )

    remaining_parents = [
        row
        for row in batch_01
        if clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        not in certified_parent_ids
    ]

    if len(remaining_parents) != 20:
        raise RuntimeError(
            "Expected 20 remaining strong-candidate parents, "
            f"found {len(remaining_parents)}."
        )

    remaining_parent_ids = {
        clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        for row in remaining_parents
    }

    remaining_candidates = [
        row
        for row in candidates_01
        if clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        in remaining_parent_ids
    ]

    batch_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    group_metadata: dict[
        str,
        tuple[int, str],
    ] = {}

    parent_group_by_id: dict[str, str] = {}

    for parent in remaining_parents:
        parent_id = clean(
            parent.get(
                "parent_tcgplayer_product_id"
            )
        )

        product_name = clean(
            parent.get(
                "parent_product_name"
            )
        )

        (
            group_name,
            group_order,
            description,
        ) = research_group(
            product_name
        )

        parent_group_by_id[parent_id] = (
            group_name
        )

        group_metadata[group_name] = (
            group_order,
            description,
        )

        batch_rows.append(
            {
                "research_batch": "02",
                "research_priority": "high",
                "research_group": group_name,
                "parent_canonical_product_id": clean(
                    parent.get(
                        "parent_canonical_product_id"
                    )
                ),
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_product_name": (
                    product_name
                ),
                "parent_product_class": clean(
                    parent.get(
                        "parent_product_class"
                    )
                ),
                "parent_finish_class": clean(
                    parent.get(
                        "parent_finish_class"
                    )
                ),
                "candidate_rows": clean(
                    parent.get(
                        "candidate_rows"
                    )
                ),
                "strong_candidate_rows": clean(
                    parent.get(
                        "strong_candidate_rows"
                    )
                ),
                "top_candidate_score": clean(
                    parent.get(
                        "top_candidate_score"
                    )
                ),
                "official_search_term": clean(
                    parent.get(
                        "official_search_term"
                    )
                ),
                "alternate_search_term": clean(
                    parent.get(
                        "alternate_search_term"
                    )
                ),
                "preferred_official_domain": clean(
                    parent.get(
                        "preferred_official_domain"
                    )
                ),
                "research_state": "not_started",
                "batch_01_certified": "false",
                "mapping_finalized": "false",
                "component_quantity_assigned": (
                    "false"
                ),
                "derived_value_allowed": "false",
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

    for candidate in remaining_candidates:
        parent_id = clean(
            candidate.get(
                "parent_tcgplayer_product_id"
            )
        )

        candidate_rows.append(
            {
                "research_batch": "02",
                "research_group": (
                    parent_group_by_id[parent_id]
                ),
                "parent_canonical_product_id": clean(
                    candidate.get(
                        "parent_canonical_product_id"
                    )
                ),
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_product_name": clean(
                    candidate.get(
                        "parent_product_name"
                    )
                ),
                "parent_finish_class": clean(
                    candidate.get(
                        "parent_finish_class"
                    )
                ),
                "candidate_rank": clean(
                    candidate.get(
                        "candidate_rank"
                    )
                ),
                "candidate_tcgplayer_product_id": clean(
                    candidate.get(
                        "candidate_tcgplayer_product_id"
                    )
                ),
                "candidate_product_name": clean(
                    candidate.get(
                        "candidate_product_name"
                    )
                ),
                "candidate_finish_class": clean(
                    candidate.get(
                        "candidate_finish_class"
                    )
                ),
                "candidate_market_price": clean(
                    candidate.get(
                        "candidate_market_price"
                    )
                ),
                "candidate_low_price": clean(
                    candidate.get(
                        "candidate_low_price"
                    )
                ),
                "candidate_mid_price": clean(
                    candidate.get(
                        "candidate_mid_price"
                    )
                ),
                "shared_distinctive_tokens": clean(
                    candidate.get(
                        "shared_distinctive_tokens"
                    )
                ),
                "exact_name_containment": clean(
                    candidate.get(
                        "exact_name_containment"
                    )
                ),
                "finish_compatibility": clean(
                    candidate.get(
                        "finish_compatibility"
                    )
                ),
                "candidate_score": clean(
                    candidate.get(
                        "candidate_score"
                    )
                ),
                "candidate_state": (
                    "candidate_only"
                ),
                "official_confirmation_required": (
                    "true"
                ),
            }
        )

    batch_rows.sort(
        key=lambda row: (
            group_metadata[
                row["research_group"]
            ][0],
            row[
                "parent_product_name"
            ].lower(),
        )
    )

    candidate_rows.sort(
        key=lambda row: (
            group_metadata[
                row["research_group"]
            ][0],
            row[
                "parent_product_name"
            ].lower(),
            int(
                row["candidate_rank"]
                or "999"
            ),
        )
    )

    group_rows: list[
        dict[str, Any]
    ] = []

    for group_name, (
        group_order,
        description,
    ) in sorted(
        group_metadata.items(),
        key=lambda item: item[1][0],
    ):
        group_parent_rows = [
            row
            for row in batch_rows
            if row["research_group"]
            == group_name
        ]

        group_candidate_rows = [
            row
            for row in candidate_rows
            if row["research_group"]
            == group_name
        ]

        group_rows.append(
            {
                "research_batch": "02",
                "research_group": group_name,
                "research_order": group_order,
                "parent_rows": len(
                    group_parent_rows
                ),
                "candidate_rows": len(
                    group_candidate_rows
                ),
                "research_description": (
                    description
                ),
                "official_evidence_captured": (
                    "false"
                ),
                "mapping_finalized": "false",
                "scoring_allowed": "false",
            }
        )

    write_csv(
        RESEARCH_BATCH_02_PATH,
        batch_rows,
        BATCH_COLUMNS,
    )

    write_csv(
        RESEARCH_CANDIDATES_02_PATH,
        candidate_rows,
        CANDIDATE_COLUMNS,
    )

    write_csv(
        RESEARCH_GROUPS_02_PATH,
        group_rows,
        GROUP_COLUMNS,
    )

    group_counts = Counter(
        row["research_group"]
        for row in batch_rows
    )

    candidate_count_distribution = Counter(
        int(row["candidate_rows"])
        for row in batch_rows
    )

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    summary = {
        "schema_version": "10.5R.3.6C.1",
        "generated_at_utc": generated_at,
        "certification_status": "PASS",
        "research_batch": "02",
        "source_research_batch_01_rows": (
            len(batch_01)
        ),
        "excluded_certified_parent_rows": (
            len(certified_parent_ids)
        ),
        "remaining_parent_rows": len(
            batch_rows
        ),
        "remaining_candidate_rows": len(
            candidate_rows
        ),
        "research_group_rows": len(
            group_rows
        ),
        "research_group_counts": dict(
            sorted(group_counts.items())
        ),
        "candidate_count_distribution": {
            str(key): value
            for key, value in sorted(
                candidate_count_distribution.items()
            )
        },
        "governance": {
            "network_requests_performed": False,
            "official_evidence_captured": False,
            "component_mappings_finalized": False,
            "component_quantities_assigned": False,
            "derived_bundle_values_created": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "research_batch_02": (
                RESEARCH_BATCH_02_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "research_candidates_02": (
                RESEARCH_CANDIDATES_02_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "research_groups_02": (
                RESEARCH_GROUPS_02_PATH
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
        "Phase 10.5R.3.6C.1 Secret Lair "
        "Official Research Batch 02"
    )
    print("=" * 76)
    print(
        f"Source Batch 01 parents: "
        f"{len(batch_01)}"
    )
    print(
        f"Excluded certified parents: "
        f"{len(certified_parent_ids)}"
    )
    print(
        f"Remaining parent rows: "
        f"{len(batch_rows)}"
    )
    print(
        f"Remaining candidate rows: "
        f"{len(candidate_rows)}"
    )
    print(
        f"Research groups: "
        f"{len(group_rows)}"
    )
    print()
    print("Research group counts:")

    for group_name, count in sorted(
        group_counts.items()
    ):
        print(
            f"  {group_name}: {count}"
        )

    print()
    print("Network requests performed: NO")
    print("Official evidence captured: NO")
    print("Component mappings finalized: NO")
    print("Derived bundle values created: NO")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print()
    print(
        "OFFICIAL RESEARCH BATCH 02 STATUS: PASS"
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