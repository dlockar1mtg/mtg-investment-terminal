from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

BUNDLE_QUEUE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_bundle_component_review_queue_2026-07-22.csv"
)

CANDIDATES_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_bundle_component_candidates_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

RESEARCH_BATCH_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_01_2026-07-22.csv"
)

CANDIDATE_DETAIL_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_01_candidates_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_research_batch_01_summary_2026-07-22.json"
)

BATCH_COLUMNS = [
    "research_batch",
    "research_priority",
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
    "required_evidence_fields",
    "research_state",
    "mapping_finalized",
    "component_quantity_assigned",
    "scoring_allowed",
    "universal_investable_allowed",
]

CANDIDATE_COLUMNS = [
    "research_batch",
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


def simplify_search_name(value: Any) -> str:
    text = clean(value)

    text = re.sub(
        r"^Secret Lair Drop:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def main() -> int:
    bundle_queue = read_csv(
        BUNDLE_QUEUE_PATH
    )

    candidates = read_csv(
        CANDIDATES_PATH
    )

    if len(bundle_queue) != 179:
        raise RuntimeError(
            "Expected 179 bundle-review rows, "
            f"found {len(bundle_queue)}."
        )

    strong_bundles = [
        row
        for row in bundle_queue
        if row.get("mapping_state")
        == "candidate_review_ready"
    ]

    if len(strong_bundles) != 30:
        raise RuntimeError(
            "Expected 30 strong-candidate bundles, "
            f"found {len(strong_bundles)}."
        )

    strong_parent_ids = {
        clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        for row in strong_bundles
    }

    candidate_rows = [
        row
        for row in candidates
        if clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )
        in strong_parent_ids
    ]

    candidates_by_parent: dict[
        str,
        list[dict[str, str]],
    ] = {}

    for row in candidate_rows:
        parent_id = clean(
            row.get(
                "parent_tcgplayer_product_id"
            )
        )

        candidates_by_parent.setdefault(
            parent_id,
            [],
        ).append(row)

    batch_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    for bundle in strong_bundles:
        parent_id = clean(
            bundle.get(
                "parent_tcgplayer_product_id"
            )
        )

        parent_name = clean(
            bundle.get(
                "parent_product_name"
            )
        )

        simplified = simplify_search_name(
            parent_name
        )

        parent_candidates = sorted(
            candidates_by_parent.get(
                parent_id,
                [],
            ),
            key=lambda row: int(
                row.get("candidate_rank")
                or 999
            ),
        )

        if not parent_candidates:
            raise RuntimeError(
                "Strong bundle has no candidate rows: "
                f"{parent_name}"
            )

        batch_rows.append(
            {
                "research_batch": "01",
                "research_priority": "high",
                "parent_canonical_product_id": clean(
                    bundle.get(
                        "parent_canonical_product_id"
                    )
                ),
                "parent_tcgplayer_product_id": (
                    parent_id
                ),
                "parent_product_name": (
                    parent_name
                ),
                "parent_product_class": clean(
                    bundle.get(
                        "parent_product_class"
                    )
                ),
                "parent_finish_class": clean(
                    bundle.get(
                        "parent_finish_class"
                    )
                ),
                "candidate_rows": clean(
                    bundle.get(
                        "candidate_rows"
                    )
                ),
                "strong_candidate_rows": clean(
                    bundle.get(
                        "strong_candidate_rows"
                    )
                ),
                "top_candidate_score": clean(
                    bundle.get(
                        "top_candidate_score"
                    )
                ),
                "official_search_term": (
                    f'site:magic.wizards.com '
                    f'"{simplified}"'
                ),
                "alternate_search_term": (
                    f'site:secretlair.wizards.com '
                    f'"{simplified}"'
                ),
                "preferred_official_domain": (
                    "magic.wizards.com|"
                    "secretlair.wizards.com"
                ),
                "required_evidence_fields": (
                    "official_parent_name|"
                    "official_component_name|"
                    "component_finish|"
                    "component_quantity|"
                    "sale_start_date|"
                    "sale_end_date|"
                    "original_sale_price|"
                    "official_source_url|"
                    "source_capture_date|"
                    "evidence_excerpt"
                ),
                "research_state": "not_started",
                "mapping_finalized": "false",
                "component_quantity_assigned": (
                    "false"
                ),
                "scoring_allowed": "false",
                "universal_investable_allowed": (
                    "false"
                ),
            }
        )

        for candidate in parent_candidates:
            detail_rows.append(
                {
                    "research_batch": "01",
                    "parent_canonical_product_id": clean(
                        candidate.get(
                            "parent_canonical_product_id"
                        )
                    ),
                    "parent_tcgplayer_product_id": (
                        parent_id
                    ),
                    "parent_product_name": (
                        parent_name
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
            row["parent_product_name"].lower()
        )
    )

    detail_rows.sort(
        key=lambda row: (
            row["parent_product_name"].lower(),
            int(row["candidate_rank"]),
        )
    )

    write_csv(
        RESEARCH_BATCH_PATH,
        batch_rows,
        BATCH_COLUMNS,
    )

    write_csv(
        CANDIDATE_DETAIL_PATH,
        detail_rows,
        CANDIDATE_COLUMNS,
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
        "schema_version": "10.5R.3.6A",
        "generated_at_utc": generated_at,
        "certification_status": "PASS",
        "research_batch": "01",
        "bundle_rows": len(batch_rows),
        "candidate_detail_rows": len(
            detail_rows
        ),
        "unique_parent_product_ids": len(
            {
                row[
                    "parent_tcgplayer_product_id"
                ]
                for row in batch_rows
            }
        ),
        "candidate_count_distribution": {
            str(key): value
            for key, value in sorted(
                candidate_count_distribution.items()
            )
        },
        "governance": {
            "network_requests_performed": False,
            "official_evidence_collected": False,
            "component_mappings_finalized": False,
            "component_quantities_assigned": False,
            "derived_bundle_values_created": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "research_batch": (
                RESEARCH_BATCH_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "candidate_details": (
                CANDIDATE_DETAIL_PATH
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
        "Phase 10.5R.3.6A Secret Lair "
        "Official Research Batch 01"
    )
    print("=" * 76)
    print(
        f"Strong-candidate bundles: "
        f"{len(batch_rows)}"
    )
    print(
        f"Candidate-detail rows: "
        f"{len(detail_rows)}"
    )
    print(
        "Unique parent product IDs: "
        f"{len({row['parent_tcgplayer_product_id'] for row in batch_rows})}"
    )
    print()
    print("Network requests performed: NO")
    print("Official evidence collected: NO")
    print("Component mappings finalized: NO")
    print("Component quantities assigned: NO")
    print("Derived bundle values created: NO")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print()
    print(
        "OFFICIAL RESEARCH BATCH STATUS: PASS"
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