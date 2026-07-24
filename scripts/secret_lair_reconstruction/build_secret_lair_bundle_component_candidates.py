from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

CLASSIFICATION_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "secret_lair_reconstruction"
    / "secret_lair_price_recovery_candidates_2026-07-22.csv"
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

CANDIDATES_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_component_candidates_2026-07-22.csv"
)

BUNDLE_QUEUE_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_component_review_queue_2026-07-22.csv"
)

OFFICIAL_QUEUE_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_official_evidence_queue_2026-07-22.csv"
)

SUMMARY_PATH = (
    VALIDATION_ROOT
    / "secret_lair_bundle_component_candidate_summary_2026-07-22.json"
)

BUNDLE_CLASSES = {
    "superdrop_bundle",
    "multi_drop_bundle",
    "playset_bundle",
}

GENERIC_TOKENS = {
    "a",
    "all",
    "and",
    "bundle",
    "bundled",
    "bundles",
    "complete",
    "drop",
    "edition",
    "editions",
    "everything",
    "foil",
    "foils",
    "full",
    "lair",
    "magic",
    "non",
    "nonfoil",
    "nonfoils",
    "of",
    "playset",
    "secret",
    "series",
    "set",
    "superdrop",
    "the",
    "traditional",
    "with",
}

CANDIDATE_COLUMNS = [
    "parent_canonical_product_id",
    "parent_tcgplayer_product_id",
    "parent_product_name",
    "parent_product_class",
    "parent_finish_class",
    "candidate_rank",
    "candidate_tcgplayer_product_id",
    "candidate_product_name",
    "candidate_finish_class",
    "candidate_market_price",
    "candidate_low_price",
    "candidate_mid_price",
    "shared_distinctive_tokens",
    "shared_distinctive_token_count",
    "exact_name_containment",
    "finish_compatibility",
    "candidate_score",
    "candidate_state",
    "candidate_reason",
    "official_confirmation_required",
    "mapping_finalized",
    "component_quantity",
    "scoring_allowed",
    "universal_investable_allowed",
]

QUEUE_COLUMNS = [
    "parent_canonical_product_id",
    "parent_tcgplayer_product_id",
    "parent_product_name",
    "parent_product_class",
    "parent_finish_class",
    "candidate_rows",
    "strong_candidate_rows",
    "top_candidate_score",
    "mapping_state",
    "mapping_reason",
    "official_confirmation_required",
]

OFFICIAL_COLUMNS = [
    "parent_canonical_product_id",
    "parent_tcgplayer_product_id",
    "parent_product_name",
    "parent_product_class",
    "parent_finish_class",
    "research_priority",
    "required_evidence_fields",
    "preferred_source",
    "research_state",
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


def normalize_name(value: Any) -> str:
    text = (
        clean(value)
        .lower()
        .replace("â€™", "'")
        .replace("â€“", "-")
        .replace("â€”", "-")
        .replace("&", " and ")
    )

    text = re.sub(
        r"^secret\s+lair\s+drop\s*:\s*",
        "",
        text,
    )

    text = re.sub(
        r"^secret\s+lair\s*:\s*",
        "",
        text,
    )

    text = re.sub(
        r"^secret\s+lair\s+x\s+",
        "",
        text,
    )

    text = re.sub(
        r"\b(?:non[- ]?foil|traditional foil|"
        r"rainbow foil|raised foil|foil) edition\b",
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


def distinctive_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_name(value).split()
        if (
            len(token) >= 3
            and token not in GENERIC_TOKENS
            and not token.isdigit()
        )
    }


def finish_compatibility(
    parent_finish: str,
    component_finish: str,
) -> tuple[int, str]:
    parent = clean(parent_finish)
    component = clean(component_finish)

    foil_finishes = {
        "foil",
        "traditional_foil",
        "rainbow_foil",
        "raised_foil",
        "etched_foil",
        "galaxy_foil",
        "halo_foil",
    }

    if parent == "unspecified":
        return 0, "parent_finish_unspecified"

    if component == "unspecified":
        return 0, "component_finish_unspecified"

    if parent == component:
        return 5, "exact_finish_match"

    specialized_foil_finishes = {
        "rainbow_foil",
        "raised_foil",
        "etched_foil",
        "galaxy_foil",
        "halo_foil",
    }

    if (
        parent in specialized_foil_finishes
        and component != parent
    ):
        return -20, "specialized_finish_conflict"

    if (
        parent in {
            "foil",
            "traditional_foil",
        }
        and component in foil_finishes
    ):
        return 2, "foil_family_match"

    if (
        parent == "nonfoil"
        and component in foil_finishes
    ):
        return -20, "finish_conflict"

    if (
        parent in foil_finishes
        and component == "nonfoil"
    ):
        return -20, "finish_conflict"

    return 0, "finish_unconfirmed"


def score_candidate(
    parent_name: str,
    parent_finish: str,
    component_name: str,
    component_finish: str,
) -> tuple[int, list[str], bool, str]:
    parent_normalized = normalize_name(
        parent_name
    )

    component_normalized = normalize_name(
        component_name
    )

    parent_tokens = distinctive_tokens(
        parent_name
    )

    component_tokens = distinctive_tokens(
        component_name
    )

    shared_tokens = sorted(
        parent_tokens & component_tokens
    )

    exact_containment = bool(
        component_normalized
        and len(component_normalized) >= 8
        and component_normalized
        in parent_normalized
    )

    finish_score, finish_state = (
        finish_compatibility(
            parent_finish,
            component_finish,
        )
    )

    score = (
        len(shared_tokens) * 5
        + (20 if exact_containment else 0)
        + finish_score
    )

    return (
        score,
        shared_tokens,
        exact_containment,
        finish_state,
    )


def main() -> int:
    classification = read_csv(
        CLASSIFICATION_PATH
    )

    components = read_csv(
        COMPONENT_UNIVERSE_PATH
    )

    component_prices = read_csv(
        COMPONENT_PRICES_PATH
    )

    if len(classification) != 254:
        raise RuntimeError(
            "Expected 254 classified registry rows, "
            f"found {len(classification)}."
        )

    if len(components) != 733:
        raise RuntimeError(
            "Expected 733 component-universe rows, "
            f"found {len(components)}."
        )

    if len(component_prices) != 733:
        raise RuntimeError(
            "Expected 733 component-price rows, "
            f"found {len(component_prices)}."
        )

    parents = [
        row
        for row in classification
        if (
            row.get("recovery_required")
            == "true"
            and row.get(
                "component_mapping_required"
            )
            == "true"
            and row.get(
                "recovery_product_class"
            )
            in BUNDLE_CLASSES
        )
    ]

    if len(parents) != 179:
        raise RuntimeError(
            "Expected 179 bundle parents, "
            f"found {len(parents)}."
        )

    standalone_components = [
        row
        for row in components
        if (
            row.get("catalog_class")
            == "standalone_sealed_drop_candidate"
            and row.get(
                "classification_confidence"
            )
            == "high"
        )
    ]

    if len(standalone_components) != 713:
        raise RuntimeError(
            "Expected 713 high-confidence standalone "
            f"components, found {len(standalone_components)}."
        )

    prices_by_id = {
        normalized_id(
            row.get("tcgplayer_product_id")
        ): row
        for row in component_prices
    }

    if len(prices_by_id) != 733:
        raise RuntimeError(
            "Component-price identity set is invalid."
        )

    candidate_rows: list[dict[str, Any]] = []
    queue_rows: list[dict[str, Any]] = []
    official_rows: list[dict[str, Any]] = []

    for parent in parents:
        parent_name = clean(
            parent.get(
                "canonical_product_name"
            )
        )

        parent_finish = clean(
            parent.get("finish_class")
        )

        scored: list[dict[str, Any]] = []

        for component in standalone_components:
            component_id = normalized_id(
                component.get(
                    "tcgplayer_product_id"
                )
            )

            component_name = clean(
                component.get("product_name")
            )

            component_finish = clean(
                component.get("finish_class")
            )

            (
                score,
                shared_tokens,
                exact_containment,
                finish_state,
            ) = score_candidate(
                parent_name,
                parent_finish,
                component_name,
                component_finish,
            )

            if finish_state in {
                "finish_conflict",
                "specialized_finish_conflict",
            }:
                continue

            meaningful_match = (
                exact_containment
                or len(shared_tokens) >= 2
            )

            if not meaningful_match:
                continue

            if score < 10:
                continue

            price = prices_by_id[
                component_id
            ]

            scored.append(
                {
                    "parent_canonical_product_id": clean(
                        parent.get(
                            "canonical_product_id"
                        )
                    ),
                    "parent_tcgplayer_product_id": clean(
                        parent.get(
                            "tcgplayer_product_id"
                        )
                    ),
                    "parent_product_name": (
                        parent_name
                    ),
                    "parent_product_class": clean(
                        parent.get(
                            "recovery_product_class"
                        )
                    ),
                    "parent_finish_class": (
                        parent_finish
                    ),
                    "candidate_tcgplayer_product_id": (
                        component_id
                    ),
                    "candidate_product_name": (
                        component_name
                    ),
                    "candidate_finish_class": (
                        component_finish
                    ),
                    "candidate_market_price": clean(
                        price.get("market_price")
                    ),
                    "candidate_low_price": clean(
                        price.get("low_price")
                    ),
                    "candidate_mid_price": clean(
                        price.get("mid_price")
                    ),
                    "shared_distinctive_tokens": (
                        "|".join(shared_tokens)
                    ),
                    "shared_distinctive_token_count": (
                        len(shared_tokens)
                    ),
                    "exact_name_containment": (
                        bool_text(
                            exact_containment
                        )
                    ),
                    "finish_compatibility": (
                        finish_state
                    ),
                    "candidate_score": score,
                    "candidate_state": (
                        "candidate_only"
                    ),
                    "candidate_reason": (
                        "Candidate retained through "
                        "distinctive-name evidence; official "
                        "bundle composition is still required."
                    ),
                    "official_confirmation_required": (
                        "true"
                    ),
                    "mapping_finalized": "false",
                    "component_quantity": "",
                    "scoring_allowed": "false",
                    "universal_investable_allowed": (
                        "false"
                    ),
                }
            )

        scored.sort(
            key=lambda row: (
                -int(row["candidate_score"]),
                -int(
                    row[
                        "shared_distinctive_token_count"
                    ]
                ),
                row[
                    "candidate_product_name"
                ].lower(),
            )
        )

        top_candidates = scored[:25]

        for rank, row in enumerate(
            top_candidates,
            start=1,
        ):
            row["candidate_rank"] = rank
            candidate_rows.append(row)

        strong_rows = sum(
            1
            for row in top_candidates
            if (
                int(row["candidate_score"])
                >= 20
                or row[
                    "exact_name_containment"
                ]
                == "true"
            )
        )

        top_score = (
            int(
                top_candidates[0][
                    "candidate_score"
                ]
            )
            if top_candidates
            else 0
        )

        if strong_rows:
            mapping_state = (
                "candidate_review_ready"
            )
            mapping_reason = (
                "At least one strong name-based "
                "candidate exists, but official "
                "composition evidence is required."
            )
        elif top_candidates:
            mapping_state = (
                "weak_candidates_official_required"
            )
            mapping_reason = (
                "Only weak name-based candidates exist."
            )
        else:
            mapping_state = (
                "no_name_candidates_official_required"
            )
            mapping_reason = (
                "Bundle name does not identify its "
                "component drops."
            )

        queue_rows.append(
            {
                "parent_canonical_product_id": clean(
                    parent.get(
                        "canonical_product_id"
                    )
                ),
                "parent_tcgplayer_product_id": clean(
                    parent.get(
                        "tcgplayer_product_id"
                    )
                ),
                "parent_product_name": (
                    parent_name
                ),
                "parent_product_class": clean(
                    parent.get(
                        "recovery_product_class"
                    )
                ),
                "parent_finish_class": (
                    parent_finish
                ),
                "candidate_rows": len(
                    top_candidates
                ),
                "strong_candidate_rows": (
                    strong_rows
                ),
                "top_candidate_score": (
                    top_score
                ),
                "mapping_state": mapping_state,
                "mapping_reason": mapping_reason,
                "official_confirmation_required": (
                    "true"
                ),
            }
        )

        official_rows.append(
            {
                "parent_canonical_product_id": clean(
                    parent.get(
                        "canonical_product_id"
                    )
                ),
                "parent_tcgplayer_product_id": clean(
                    parent.get(
                        "tcgplayer_product_id"
                    )
                ),
                "parent_product_name": (
                    parent_name
                ),
                "parent_product_class": clean(
                    parent.get(
                        "recovery_product_class"
                    )
                ),
                "parent_finish_class": (
                    parent_finish
                ),
                "research_priority": (
                    "high"
                    if not top_candidates
                    else "standard"
                ),
                "required_evidence_fields": (
                    "official_product_name|"
                    "component_drop_names|"
                    "component_quantities|"
                    "foil_treatment|"
                    "original_sale_price|"
                    "sale_start_date|"
                    "sale_end_date|"
                    "official_source_url"
                ),
                "preferred_source": (
                    "wizards_secret_lair_official"
                ),
                "research_state": (
                    "not_started"
                ),
            }
        )

    candidate_rows.sort(
        key=lambda row: (
            row["parent_product_name"].lower(),
            int(row["candidate_rank"]),
        )
    )

    queue_rows.sort(
        key=lambda row: (
            row["parent_product_name"].lower()
        )
    )

    official_rows.sort(
        key=lambda row: (
            row["parent_product_name"].lower()
        )
    )

    write_csv(
        CANDIDATES_PATH,
        candidate_rows,
        CANDIDATE_COLUMNS,
    )

    write_csv(
        BUNDLE_QUEUE_PATH,
        queue_rows,
        QUEUE_COLUMNS,
    )

    write_csv(
        OFFICIAL_QUEUE_PATH,
        official_rows,
        OFFICIAL_COLUMNS,
    )

    state_counts = Counter(
        row["mapping_state"]
        for row in queue_rows
    )

    bundles_with_candidates = sum(
        1
        for row in queue_rows
        if int(row["candidate_rows"]) > 0
    )

    bundles_with_strong_candidates = sum(
        1
        for row in queue_rows
        if int(
            row["strong_candidate_rows"]
        )
        > 0
    )

    generic_only_rows = sum(
        1
        for row in candidate_rows
        if (
            int(
                row[
                    "shared_distinctive_token_count"
                ]
            )
            == 0
            and row[
                "exact_name_containment"
            ]
            != "true"
        )
    )

    certification_status = (
        "PASS"
        if (
            len(queue_rows) == 179
            and len(official_rows) == 179
            and generic_only_rows == 0
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
        "schema_version": "10.5R.3.5C",
        "generated_at_utc": generated_at,
        "certification_status": (
            certification_status
        ),
        "parent_bundle_rows": len(parents),
        "eligible_component_pool_rows": (
            len(standalone_components)
        ),
        "candidate_rows": len(
            candidate_rows
        ),
        "bundles_with_candidates": (
            bundles_with_candidates
        ),
        "bundles_without_candidates": (
            len(parents)
            - bundles_with_candidates
        ),
        "bundles_with_strong_candidates": (
            bundles_with_strong_candidates
        ),
        "generic_only_candidate_rows": (
            generic_only_rows
        ),
        "official_evidence_queue_rows": (
            len(official_rows)
        ),
        "mapping_state_counts": dict(
            sorted(state_counts.items())
        ),
        "governance": {
            "component_mappings_finalized": False,
            "component_quantities_assigned": False,
            "derived_bundle_values_created": False,
            "observed_prices_overwritten": False,
            "production_registry_changed": False,
            "final_eligibility_assigned": False,
            "scoring_enabled": False,
            "universal_investable_enabled": False,
        },
        "outputs": {
            "component_candidates": (
                CANDIDATES_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "bundle_review_queue": (
                BUNDLE_QUEUE_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
            "official_evidence_queue": (
                OFFICIAL_QUEUE_PATH
                .relative_to(ROOT)
                .as_posix()
            ),
        },
    }

    SUMMARY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        "Phase 10.5R.3.5C Secret Lair "
        "Bundle Component Candidates"
    )
    print("=" * 76)
    print(
        f"Parent bundles: {len(parents)}"
    )
    print(
        "Eligible component pool: "
        f"{len(standalone_components)}"
    )
    print(
        f"Candidate rows: "
        f"{len(candidate_rows)}"
    )
    print(
        "Bundles with candidates: "
        f"{bundles_with_candidates}"
    )
    print(
        "Bundles without candidates: "
        f"{len(parents) - bundles_with_candidates}"
    )
    print(
        "Bundles with strong candidates: "
        f"{bundles_with_strong_candidates}"
    )
    print(
        "Generic-only candidate rows: "
        f"{generic_only_rows}"
    )
    print()
    print("Mapping states:")

    for state, count in sorted(
        state_counts.items()
    ):
        print(f"  {state}: {count}")

    print()
    print(
        "BUNDLE COMPONENT CANDIDATE STATUS: "
        + certification_status
    )
    print("Component mappings finalized: NO")
    print("Component quantities assigned: NO")
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