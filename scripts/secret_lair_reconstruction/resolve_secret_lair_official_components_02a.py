from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_official_bundle_evidence_seed_02a_2026-07-22.csv"
)

PARENT_COVERAGE_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_official_bundle_parent_coverage_02a_2026-07-22.csv"
)

COMPONENT_UNIVERSE_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_component_universe_2026-07-22.csv"
)

COMPONENT_PRICES_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_component_current_prices_2026-07-22.csv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "secret_lair_reconstruction"
)

RESOLUTION_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_component_resolution_02a_2026-07-22.csv"
)

REVIEW_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_component_resolution_review_02a_2026-07-22.csv"
)

CONFIRMED_MAP_PATH = (
    VALIDATION_ROOT
    / "secret_lair_confirmed_component_map_02a_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_official_component_resolution_02a_summary_2026-07-22.json"
)

RESOLUTION_COLUMNS = [
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
    "official_source_url",
    "source_capture_date",
    "resolved_component_tcgplayer_product_id",
    "resolved_component_product_name",
    "resolved_component_finish_class",
    "resolved_component_catalog_class",
    "resolved_component_market_price",
    "resolved_component_low_price",
    "resolved_component_mid_price",
    "resolution_method",
    "resolution_candidate_count",
    "component_resolution_state",
    "mapping_confirmed",
    "mapping_finalized",
    "derived_value_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]

REVIEW_COLUMNS = [
    "parent_tcgplayer_product_id",
    "local_parent_product_name",
    "official_component_ordinal",
    "official_component_name",
    "local_expected_finish_class",
    "resolution_candidate_count",
    "candidate_product_ids",
    "candidate_product_names",
    "candidate_finish_classes",
    "component_resolution_state",
    "review_reason",
]

CONFIRMED_COLUMNS = [
    "evidence_batch",
    "parent_tcgplayer_product_id",
    "parent_canonical_product_id",
    "local_parent_product_name",
    "official_parent_product_name",
    "official_component_ordinal",
    "official_component_name",
    "official_component_finish_class",
    "local_expected_finish_class",
    "component_quantity",
    "component_tcgplayer_product_id",
    "component_product_name",
    "component_finish_class",
    "component_catalog_class",
    "component_market_price",
    "component_low_price",
    "component_mid_price",
    "official_source_url",
    "source_capture_date",
    "resolution_method",
    "mapping_state",
    "derived_value_allowed",
    "scoring_allowed",
    "universal_investable_allowed",
]


def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalized_id(value: Any) -> str:
    text = clean(value)

    if text.endswith(".0"):
        text = text[:-2]

    return text


def bool_text(value: bool) -> str:
    return "true" if value else "false"


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


def normalize_component_name(value: Any) -> str:
    text = (
        clean(value)
        .lower()
        .replace("Ã¢â‚¬â„¢", "'")
        .replace("Ã¢â‚¬â€œ", "-")
        .replace("Ã¢â‚¬â€", "-")
        .replace("&", " and ")
    )

    prefixes = (
        r"^secret\s+lair\s+drop\s*:\s*",
        r"^secret\s+lair\s+drop\s+series\s*:\s*",
        r"^secret\s+lair\s*:\s*",
        r"^secret\s+lair\s+x\s+",
    )

    for pattern in prefixes:
        text = re.sub(
            pattern,
            "",
            text,
        )

    text = re.sub(
        r"\s*-\s*(?:"
        r"non[- ]?foil|"
        r"traditional foil|"
        r"rainbow foil|"
        r"raised foil|"
        r"etched foil|"
        r"galaxy foil|"
        r"halo foil|"
        r"foil"
        r")\s+edition\s*$",
        "",
        text,
    )

    text = re.sub(
        r"\s+(?:"
        r"non[- ]?foil|"
        r"traditional foil|"
        r"rainbow foil|"
        r"raised foil|"
        r"etched foil|"
        r"galaxy foil|"
        r"halo foil|"
        r"foil"
        r")\s+edition\s*$",
        "",
        text,
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def resolve_component(
    evidence: dict[str, str],
    components: list[dict[str, str]],
) -> tuple[
    dict[str, str] | None,
    str,
    list[dict[str, str]],
]:
    official_name = normalize_component_name(
        evidence.get("official_component_name")
    )

    expected_finish = clean(
        evidence.get(
            "local_expected_finish_class"
        )
    )

    exact_name_matches = [
        row
        for row in components
        if normalize_component_name(
            row.get("product_name")
        )
        == official_name
    ]

    exact_name_finish_matches = [
        row
        for row in exact_name_matches
        if clean(
            row.get("finish_class")
        )
        == expected_finish
    ]

    if len(exact_name_finish_matches) == 1:
        return (
            exact_name_finish_matches[0],
            "exact_normalized_name_and_finish",
            exact_name_finish_matches,
        )

    if len(exact_name_finish_matches) > 1:
        return (
            None,
            "ambiguous_exact_name_and_finish",
            exact_name_finish_matches,
        )

    if len(exact_name_matches) == 1:
        return (
            exact_name_matches[0],
            "unique_exact_normalized_name",
            exact_name_matches,
        )

    containment_matches = [
        row
        for row in components
        if (
            official_name
            and len(official_name) >= 8
            and (
                official_name
                in normalize_component_name(
                    row.get("product_name")
                )
                or normalize_component_name(
                    row.get("product_name")
                )
                in official_name
            )
        )
    ]

    containment_finish_matches = [
        row
        for row in containment_matches
        if clean(
            row.get("finish_class")
        )
        == expected_finish
    ]

    if len(containment_finish_matches) == 1:
        return (
            containment_finish_matches[0],
            "unique_normalized_containment_and_finish",
            containment_finish_matches,
        )

    if len(containment_finish_matches) > 1:
        return (
            None,
            "ambiguous_containment_and_finish",
            containment_finish_matches,
        )

    if len(containment_matches) == 1:
        return (
            containment_matches[0],
            "unique_normalized_containment",
            containment_matches,
        )

    candidates = (
        exact_name_matches
        if exact_name_matches
        else containment_matches
    )

    if candidates:
        return (
            None,
            "ambiguous_local_component",
            candidates,
        )

    return (
        None,
        "no_local_component_match",
        [],
    )


def main() -> int:
    evidence_rows = read_csv(
        EVIDENCE_PATH
    )

    parent_coverage = read_csv(
        PARENT_COVERAGE_PATH
    )

    components = read_csv(
        COMPONENT_UNIVERSE_PATH
    )

    prices = read_csv(
        COMPONENT_PRICES_PATH
    )

    if len(evidence_rows) != 32:
        raise RuntimeError(
            "Expected 32 official evidence rows, "
            f"found {len(evidence_rows)}."
        )

    if len(parent_coverage) != 4:
        raise RuntimeError(
            "Expected 4 parent-coverage rows, "
            f"found {len(parent_coverage)}."
        )

    if len(components) != 733:
        raise RuntimeError(
            "Expected 733 component-universe rows, "
            f"found {len(components)}."
        )

    if len(prices) != 733:
        raise RuntimeError(
            "Expected 733 component-price rows, "
            f"found {len(prices)}."
        )

    component_ids = [
        normalized_id(
            row.get(
                "tcgplayer_product_id"
            )
        )
        for row in components
    ]

    if len(component_ids) != len(
        set(component_ids)
    ):
        raise RuntimeError(
            "Component universe contains duplicate IDs."
        )

    prices_by_id = {
        normalized_id(
            row.get(
                "tcgplayer_product_id"
            )
        ): row
        for row in prices
    }

    if len(prices_by_id) != 733:
        raise RuntimeError(
            "Component-price identity set is invalid."
        )

    resolution_rows: list[
        dict[str, Any]
    ] = []

    review_rows: list[
        dict[str, Any]
    ] = []

    confirmed_rows: list[
        dict[str, Any]
    ] = []

    for evidence in evidence_rows:
        (
            resolved,
            method,
            candidates,
        ) = resolve_component(
            evidence,
            components,
        )

        resolved_id = (
            normalized_id(
                resolved.get(
                    "tcgplayer_product_id"
                )
            )
            if resolved
            else ""
        )

        price = (
            prices_by_id.get(
                resolved_id,
                {},
            )
            if resolved_id
            else {}
        )

        confirmed = resolved is not None

        if confirmed:
            resolution_state = (
                "resolved_unique_local_component"
            )
        elif candidates:
            resolution_state = (
                "ambiguous_local_component"
            )
        else:
            resolution_state = (
                "unresolved_no_local_component"
            )

        resolution_row = {
            "evidence_batch": clean(
                evidence.get("evidence_batch")
            ),
            "parent_tcgplayer_product_id": clean(
                evidence.get(
                    "parent_tcgplayer_product_id"
                )
            ),
            "parent_canonical_product_id": clean(
                evidence.get(
                    "parent_canonical_product_id"
                )
            ),
            "local_parent_product_name": clean(
                evidence.get(
                    "local_parent_product_name"
                )
            ),
            "official_parent_product_name": clean(
                evidence.get(
                    "official_parent_product_name"
                )
            ),
            "parent_finish_class": clean(
                evidence.get(
                    "parent_finish_class"
                )
            ),
            "official_component_ordinal": clean(
                evidence.get(
                    "official_component_ordinal"
                )
            ),
            "official_component_name": clean(
                evidence.get(
                    "official_component_name"
                )
            ),
            "official_component_finish_class": clean(
                evidence.get(
                    "official_component_finish_class"
                )
            ),
            "local_expected_finish_class": clean(
                evidence.get(
                    "local_expected_finish_class"
                )
            ),
            "component_quantity": clean(
                evidence.get(
                    "component_quantity"
                )
            ),
            "official_source_url": clean(
                evidence.get(
                    "official_source_url"
                )
            ),
            "source_capture_date": clean(
                evidence.get(
                    "source_capture_date"
                )
            ),
            "resolved_component_tcgplayer_product_id": (
                resolved_id
            ),
            "resolved_component_product_name": (
                clean(
                    resolved.get("product_name")
                )
                if resolved
                else ""
            ),
            "resolved_component_finish_class": (
                clean(
                    resolved.get("finish_class")
                )
                if resolved
                else ""
            ),
            "resolved_component_catalog_class": (
                clean(
                    resolved.get("catalog_class")
                )
                if resolved
                else ""
            ),
            "resolved_component_market_price": clean(
                price.get("market_price")
            ),
            "resolved_component_low_price": clean(
                price.get("low_price")
            ),
            "resolved_component_mid_price": clean(
                price.get("mid_price")
            ),
            "resolution_method": method,
            "resolution_candidate_count": len(
                candidates
            ),
            "component_resolution_state": (
                resolution_state
            ),
            "mapping_confirmed": bool_text(
                confirmed
            ),
            "mapping_finalized": "false",
            "derived_value_allowed": "false",
            "scoring_allowed": "false",
            "universal_investable_allowed": (
                "false"
            ),
        }

        resolution_rows.append(
            resolution_row
        )

        if confirmed:
            confirmed_rows.append(
                {
                    "evidence_batch": clean(
                        evidence.get(
                            "evidence_batch"
                        )
                    ),
                    "parent_tcgplayer_product_id": (
                        resolution_row[
                            "parent_tcgplayer_product_id"
                        ]
                    ),
                    "parent_canonical_product_id": (
                        resolution_row[
                            "parent_canonical_product_id"
                        ]
                    ),
                    "local_parent_product_name": (
                        resolution_row[
                            "local_parent_product_name"
                        ]
                    ),
                    "official_parent_product_name": (
                        resolution_row[
                            "official_parent_product_name"
                        ]
                    ),
                    "official_component_ordinal": (
                        resolution_row[
                            "official_component_ordinal"
                        ]
                    ),
                    "official_component_name": (
                        resolution_row[
                            "official_component_name"
                        ]
                    ),
                    "official_component_finish_class": (
                        resolution_row[
                            "official_component_finish_class"
                        ]
                    ),
                    "local_expected_finish_class": (
                        resolution_row[
                            "local_expected_finish_class"
                        ]
                    ),
                    "component_quantity": (
                        resolution_row[
                            "component_quantity"
                        ]
                    ),
                    "component_tcgplayer_product_id": (
                        resolved_id
                    ),
                    "component_product_name": (
                        resolution_row[
                            "resolved_component_product_name"
                        ]
                    ),
                    "component_finish_class": (
                        resolution_row[
                            "resolved_component_finish_class"
                        ]
                    ),
                    "component_catalog_class": (
                        resolution_row[
                            "resolved_component_catalog_class"
                        ]
                    ),
                    "component_market_price": (
                        resolution_row[
                            "resolved_component_market_price"
                        ]
                    ),
                    "component_low_price": (
                        resolution_row[
                            "resolved_component_low_price"
                        ]
                    ),
                    "component_mid_price": (
                        resolution_row[
                            "resolved_component_mid_price"
                        ]
                    ),
                    "official_source_url": (
                        resolution_row[
                            "official_source_url"
                        ]
                    ),
                    "source_capture_date": (
                        resolution_row[
                            "source_capture_date"
                        ]
                    ),
                    "resolution_method": method,
                    "mapping_state": (
                        "official_evidence_unique_local_resolution"
                    ),
                    "derived_value_allowed": (
                        "false"
                    ),
                    "scoring_allowed": "false",
                    "universal_investable_allowed": (
                        "false"
                    ),
                }
            )
        else:
            review_rows.append(
                {
                    "parent_tcgplayer_product_id": (
                        resolution_row[
                            "parent_tcgplayer_product_id"
                        ]
                    ),
                    "local_parent_product_name": (
                        resolution_row[
                            "local_parent_product_name"
                        ]
                    ),
                    "official_component_ordinal": (
                        resolution_row[
                            "official_component_ordinal"
                        ]
                    ),
                    "official_component_name": (
                        resolution_row[
                            "official_component_name"
                        ]
                    ),
                    "local_expected_finish_class": (
                        resolution_row[
                            "local_expected_finish_class"
                        ]
                    ),
                    "resolution_candidate_count": (
                        len(candidates)
                    ),
                    "candidate_product_ids": "|".join(
                        normalized_id(
                            row.get(
                                "tcgplayer_product_id"
                            )
                        )
                        for row in candidates
                    ),
                    "candidate_product_names": "|".join(
                        clean(
                            row.get("product_name")
                        )
                        for row in candidates
                    ),
                    "candidate_finish_classes": "|".join(
                        clean(
                            row.get("finish_class")
                        )
                        for row in candidates
                    ),
                    "component_resolution_state": (
                        resolution_state
                    ),
                    "review_reason": method,
                }
            )

    resolution_rows.sort(
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

    review_rows.sort(
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

    confirmed_rows.sort(
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

    write_csv(
        RESOLUTION_PATH,
        resolution_rows,
        RESOLUTION_COLUMNS,
    )

    write_csv(
        REVIEW_PATH,
        review_rows,
        REVIEW_COLUMNS,
    )

    write_csv(
        CONFIRMED_MAP_PATH,
        confirmed_rows,
        CONFIRMED_COLUMNS,
    )

    state_counts = Counter(
        row["component_resolution_state"]
        for row in resolution_rows
    )

    method_counts = Counter(
        row["resolution_method"]
        for row in resolution_rows
    )

    parent_ids = {
        row[
            "parent_tcgplayer_product_id"
        ]
        for row in resolution_rows
    }

    fully_resolved_parent_ids: set[str] = set()

    for parent_id in parent_ids:
        parent_resolution_rows = [
            row
            for row in resolution_rows
            if row[
                "parent_tcgplayer_product_id"
            ]
            == parent_id
        ]

        if all(
            row["mapping_confirmed"]
            == "true"
            for row in parent_resolution_rows
        ):
            fully_resolved_parent_ids.add(
                parent_id
            )

    duplicate_parent_component_pairs = (
        len(
            [
                (
                    row[
                        "parent_tcgplayer_product_id"
                    ],
                    row[
                        "official_component_ordinal"
                    ],
                )
                for row in resolution_rows
            ]
        )
        - len(
            {
                (
                    row[
                        "parent_tcgplayer_product_id"
                    ],
                    row[
                        "official_component_ordinal"
                    ],
                )
                for row in resolution_rows
            }
        )
    )

    certification_status = (
        "PASS"
        if (
            len(resolution_rows) == 32
            and duplicate_parent_component_pairs
            == 0
            and len(confirmed_rows)
            + len(review_rows)
            == 32
        )
        else "PARTIAL"
    )

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    summary = {
        "schema_version": "10.5R.3.6C.3",
        "generated_at_utc": generated_at,
        "certification_status": (
            certification_status
        ),
        "official_evidence_rows": len(
            evidence_rows
        ),
        "resolution_rows": len(
            resolution_rows
        ),
        "confirmed_component_map_rows": len(
            confirmed_rows
        ),
        "review_queue_rows": len(
            review_rows
        ),
        "fully_resolved_parent_rows": len(
            fully_resolved_parent_ids
        ),
        "partially_or_unresolved_parent_rows": (
            len(parent_ids)
            - len(fully_resolved_parent_ids)
        ),
        "duplicate_parent_component_pairs": (
            duplicate_parent_component_pairs
        ),
        "resolution_state_counts": dict(
            sorted(state_counts.items())
        ),
        "resolution_method_counts": dict(
            sorted(method_counts.items())
        ),
        "governance": {
            "official_evidence_preserved": True,
            "component_ids_resolved_where_unique": (
                True
            ),
            "component_mappings_finalized": False,
            "parent_mapping_finalized": False,
            "derived_bundle_values_created": False,
            "observed_prices_overwritten": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "component_resolution": (
                RESOLUTION_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "resolution_review_queue": (
                REVIEW_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "confirmed_component_map": (
                CONFIRMED_MAP_PATH
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
        "Phase 10.5R.3.6C.3 Secret Lair "
        "Official Component Resolution 02A"
    )
    print("=" * 76)
    print(
        f"Official evidence rows: "
        f"{len(evidence_rows)}"
    )
    print(
        f"Resolved component rows: "
        f"{len(confirmed_rows)}"
    )
    print(
        f"Review queue rows: "
        f"{len(review_rows)}"
    )
    print(
        "Fully resolved parents: "
        f"{len(fully_resolved_parent_ids)}"
    )
    print(
        "Partially or unresolved parents: "
        f"{len(parent_ids) - len(fully_resolved_parent_ids)}"
    )
    print()
    print("Resolution states:")

    for state, count in sorted(
        state_counts.items()
    ):
        print(f"  {state}: {count}")

    print()
    print(
        "OFFICIAL COMPONENT RESOLUTION STATUS: "
        + certification_status
    )
    print("Component mappings finalized: NO")
    print("Parent mappings finalized: NO")
    print("Derived bundle values created: NO")
    print("Final eligibility: NOT ASSIGNED")
    print("Scoring: DISABLED")
    print("Universal investable: DISABLED")
    print()
    print(
        "Summary: "
        + SUMMARY_PATH
        .relative_to(ROOT)
        .as_posix()
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())