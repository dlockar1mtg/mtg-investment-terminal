from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EVIDENCE = (
    ROOT
    / "data"
    / "operations"
    / "collector_evidence_normalization"
    / "candidate_v1_0_0"
    / "collector_normalized_evidence.csv"
)

DEFAULT_ROUTER = (
    ROOT
    / "data"
    / "operations"
    / "collector_forecast_method_routing"
    / "candidate_v1_0_0"
    / "collector_forecast_method_routes.csv"
)

DEFAULT_HISTORY = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_history_certification"
    / "candidate_v1_0_0"
    / "collector_history_product_certification.csv"
)

DEFAULT_POLICY = (
    ROOT
    / "config"
    / "mtg"
    / "evidence"
    / "collector_comparable_selection_v1.json"
)

DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "operations"
    / "collector_comparable_selection"
    / "candidate_v1_0_0"
)


PAIR_FIELDS = [
    "target_product_id",
    "target_product_name",
    "peer_product_id",
    "peer_product_name",
    "peer_history_status",
    "peer_history_quality_band",
    "product_configuration_similarity",
    "product_family_similarity",
    "franchise_class_similarity",
    "edition_class_similarity",
    "semantic_compatibility_status",
    "semantic_exclusion_reason",
    "release_era_similarity",
    "lifecycle_stage_similarity",
    "price_band_similarity",
    "supply_profile_similarity",
    "liquidity_class_similarity",
    "demand_profile_similarity",
    "dimension_coverage",
    "raw_similarity_score",
    "peer_quality_multiplier",
    "adjusted_similarity_score",
    "minimum_similarity_score",
    "meets_similarity_threshold",
    "selected",
    "selection_rank",
    "selection_reason",
    "policy_version",
    "purchase_recommendation_authorized",
]

TARGET_FIELDS = [
    "target_product_id",
    "target_product_name",
    "forecast_method",
    "comparable_evidence_ready",
    "candidate_peer_count",
    "threshold_peer_count",
    "selected_peer_count",
    "selection_status",
    "minimum_comparables",
    "maximum_comparables",
    "minimum_similarity_score",
    "best_similarity_score",
    "lowest_selected_similarity_score",
    "selected_peer_ids",
    "limitations",
    "projection_authorized",
    "purchase_recommendation_authorized",
    "policy_version",
]


def clean(value: object) -> str:
    return str(value or "").strip()


def parse_bool(value: object) -> bool:
    return clean(value).lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def parse_float(value: object) -> float | None:
    text = clean(value).replace(",", "")

    if not text:
        return None

    try:
        result = float(text)
    except ValueError:
        return None

    if not math.isfinite(result):
        return None

    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
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
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def index_unique(
    rows: list[dict[str, str]],
    key: str,
    label: str,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    for row in rows:
        identity = clean(row.get(key))

        if not identity:
            raise RuntimeError(
                f"{label} contains blank {key}."
            )

        if identity in result:
            raise RuntimeError(
                f"{label} contains duplicate identity: "
                f"{identity}"
            )

        result[identity] = row

    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def categorical_similarity(
    target_value: object,
    peer_value: object,
) -> tuple[float, bool]:
    target = clean(target_value).upper()
    peer = clean(peer_value).upper()

    missing_values = {
        "",
        "UNKNOWN",
        "PRE_COLLECTOR_OR_UNKNOWN",
    }

    if target in missing_values or peer in missing_values:
        return 0.0, False

    return (
        1.0 if target == peer else 0.0,
        True,
    )


def numeric_similarity(
    target_value: object,
    peer_value: object,
    scale_maximum: float = 100.0,
) -> tuple[float, bool]:
    target = parse_float(target_value)
    peer = parse_float(peer_value)

    if target is None or peer is None:
        return 0.0, False

    distance = abs(target - peer)

    similarity = 1.0 - (
        distance / scale_maximum
    )

    return (
        max(0.0, min(1.0, similarity)),
        True,
    )


def score_pair(
    target: dict[str, str],
    peer: dict[str, str],
    peer_history: dict[str, str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    weights = policy["weights"]

    dimensions: dict[
        str,
        tuple[float, bool, float]
    ] = {}

    dimensions[
        "product_configuration"
    ] = (
        *categorical_similarity(
            target.get("product_configuration"),
            peer.get("product_configuration"),
        ),
        float(weights["product_configuration"]),
    )

    dimensions[
        "product_family"
    ] = (
        *categorical_similarity(
            target.get("product_family_class"),
            peer.get("product_family_class"),
        ),
        float(weights["product_family"]),
    )

    dimensions[
        "franchise_class"
    ] = (
        *categorical_similarity(
            target.get("franchise_class"),
            peer.get("franchise_class"),
        ),
        float(weights["franchise_class"]),
    )

    dimensions[
        "edition_class"
    ] = (
        *categorical_similarity(
            target.get("edition_class"),
            peer.get("edition_class"),
        ),
        float(weights["edition_class"]),
    )

    dimensions[
        "release_era"
    ] = (
        *categorical_similarity(
            target.get("release_era_class"),
            peer.get("release_era_class"),
        ),
        float(weights["release_era"]),
    )

    dimensions[
        "lifecycle_stage"
    ] = (
        *categorical_similarity(
            target.get("lifecycle_stage"),
            peer.get("lifecycle_stage"),
        ),
        float(weights["lifecycle_stage"]),
    )

    dimensions[
        "price_band"
    ] = (
        *categorical_similarity(
            target.get("price_band_class"),
            peer.get("price_band_class"),
        ),
        float(weights["price_band"]),
    )

    dimensions[
        "supply_profile"
    ] = (
        *categorical_similarity(
            target.get("supply_profile_class"),
            peer.get("supply_profile_class"),
        ),
        float(weights["supply_profile"]),
    )

    dimensions[
        "liquidity_class"
    ] = (
        *categorical_similarity(
            target.get("liquidity_class"),
            peer.get("liquidity_class"),
        ),
        float(weights["liquidity_class"]),
    )

    dimensions[
        "demand_profile"
    ] = (
        *numeric_similarity(
            target.get("demand_score"),
            peer.get("demand_score"),
            100.0,
        ),
        float(weights["demand_profile"]),
    )

    total_weight = sum(
        dimension[2]
        for dimension in dimensions.values()
    )

    observed_weight = sum(
        dimension[2]
        for dimension in dimensions.values()
        if dimension[1]
    )

    weighted_score = sum(
        dimension[0] * dimension[2]
        for dimension in dimensions.values()
    )

    raw_score = (
        100.0 * weighted_score / total_weight
        if total_weight
        else 0.0
    )

    dimension_coverage = (
        observed_weight / total_weight
        if total_weight
        else 0.0
    )

    history_status = clean(
        peer_history.get(
            "history_certification_status"
        )
    )

    quality_multiplier = float(
        policy[
            "peer_quality_weights"
        ].get(
            history_status,
            0.0,
        )
    )

    adjusted_score = (
        raw_score * quality_multiplier
    )

    minimum_score = float(
        policy["minimum_similarity_score"]
    )

    minimum_coverage = float(
        policy["minimum_dimension_coverage"]
    )

    target_edition = clean(
        target.get("edition_class")
    )

    peer_edition = clean(
        peer.get("edition_class")
    )

    target_name = clean(
        target.get("product_name")
    ).upper()

    peer_name = clean(
        peer.get("product_name")
    ).upper()

    semantic_compatible = True
    semantic_exclusion_reason = ""

    if target_edition == "JAPANESE_EDITION":
        same_final_fantasy_family = (
            "FINAL FANTASY" in target_name
            and "FINAL FANTASY" in peer_name
        )

        if (
            peer_edition != "JAPANESE_EDITION"
            and not same_final_fantasy_family
        ):
            semantic_compatible = False
            semantic_exclusion_reason = (
                "JAPANESE_EDITION_REQUIRES_"
                "SAME_SET_OR_JAPANESE_PEER"
            )

    if target_edition == "SPECIAL_EDITION":
        same_product_family = (
            clean(
                target.get(
                    "product_family_class"
                )
            )
            == clean(
                peer.get(
                    "product_family_class"
                )
            )
        )

        same_named_set = (
            "LORD OF THE RINGS" in target_name
            and "LORD OF THE RINGS" in peer_name
        )

        if (
            not same_product_family
            and not same_named_set
        ):
            semantic_compatible = False
            semantic_exclusion_reason = (
                "SPECIAL_EDITION_REQUIRES_"
                "SAME_SET_OR_PRODUCT_FAMILY"
            )

    meets_threshold = (
        adjusted_score >= minimum_score
        and dimension_coverage >= minimum_coverage
        and semantic_compatible
    )

    return {
        "product_configuration_similarity": round(
            dimensions[
                "product_configuration"
            ][0] * 100,
            6,
        ),
        "product_family_similarity": round(
            dimensions["product_family"][0] * 100,
            6,
        ),
        "franchise_class_similarity": round(
            dimensions["franchise_class"][0] * 100,
            6,
        ),
        "edition_class_similarity": round(
            dimensions["edition_class"][0] * 100,
            6,
        ),
        "semantic_compatibility_status": (
            "PASS"
            if semantic_compatible
            else "FAILED"
        ),
        "semantic_exclusion_reason": (
            semantic_exclusion_reason
        ),
        "release_era_similarity": round(
            dimensions["release_era"][0] * 100,
            6,
        ),
        "lifecycle_stage_similarity": round(
            dimensions["lifecycle_stage"][0] * 100,
            6,
        ),
        "price_band_similarity": round(
            dimensions["price_band"][0] * 100,
            6,
        ),
        "supply_profile_similarity": round(
            dimensions["supply_profile"][0] * 100,
            6,
        ),
        "liquidity_class_similarity": round(
            dimensions["liquidity_class"][0] * 100,
            6,
        ),
        "demand_profile_similarity": round(
            dimensions["demand_profile"][0] * 100,
            6,
        ),
        "dimension_coverage": round(
            dimension_coverage,
            6,
        ),
        "raw_similarity_score": round(
            raw_score,
            6,
        ),
        "peer_quality_multiplier": round(
            quality_multiplier,
            6,
        ),
        "adjusted_similarity_score": round(
            adjusted_score,
            6,
        ),
        "minimum_similarity_score": minimum_score,
        "meets_similarity_threshold": (
            meets_threshold
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE,
    )

    parser.add_argument(
        "--router",
        type=Path,
        default=DEFAULT_ROUTER,
    )

    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY,
    )

    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    policy = json.loads(
        args.policy.read_text(
            encoding="utf-8-sig"
        )
    )

    evidence_rows = read_csv(
        args.evidence
    )

    router_rows = read_csv(
        args.router
    )

    history_rows = read_csv(
        args.history
    )

    evidence = index_unique(
        evidence_rows,
        "investment_product_id",
        "normalized evidence",
    )

    router = index_unique(
        router_rows,
        "investment_product_id",
        "router",
    )

    history = index_unique(
        history_rows,
        "investment_product_id",
        "history",
    )

    target_ids = sorted(
        identity
        for identity, row in router.items()
        if clean(row.get("forecast_method"))
        == "COMPARABLE_PRODUCT_ADJUSTED"
    )

    permitted_peer_statuses = {
        clean(status)
        for status in policy[
            "minimum_peer_history_statuses"
        ]
    }

    peer_ids = sorted(
        identity
        for identity, row in history.items()
        if clean(
            row.get(
                "history_certification_status"
            )
        )
        in permitted_peer_statuses
        and identity in evidence
        and parse_bool(
            evidence[identity].get(
                "comparable_evidence_ready"
            )
        )
    )

    minimum_comparables = int(
        policy["minimum_comparables"]
    )

    maximum_comparables = int(
        policy["maximum_comparables"]
    )

    pair_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []

    for target_id in target_ids:
        target = evidence.get(target_id)

        if target is None:
            raise RuntimeError(
                "Comparable target missing normalized "
                f"evidence: {target_id}"
            )

        target_ready = parse_bool(
            target.get(
                "comparable_evidence_ready"
            )
        )

        candidates: list[dict[str, Any]] = []

        if target_ready:
            for peer_id in peer_ids:
                if peer_id == target_id:
                    continue

                peer = evidence[peer_id]
                peer_history = history[peer_id]

                scores = score_pair(
                    target,
                    peer,
                    peer_history,
                    policy,
                )

                candidates.append({
                    "target_product_id": target_id,
                    "target_product_name": clean(
                        target.get("product_name")
                    ),
                    "peer_product_id": peer_id,
                    "peer_product_name": clean(
                        peer.get("product_name")
                    ),
                    "peer_history_status": clean(
                        peer_history.get(
                            "history_certification_status"
                        )
                    ),
                    "peer_history_quality_band": clean(
                        peer_history.get(
                            "history_quality_band"
                        )
                    ),
                    **scores,
                    "selected": False,
                    "selection_rank": "",
                    "selection_reason": "",
                    "policy_version": policy[
                        "policy_version"
                    ],
                    "purchase_recommendation_authorized": False,
                })

        candidates.sort(
            key=lambda row: (
                -float(
                    row[
                        "adjusted_similarity_score"
                    ]
                ),
                clean(row["peer_product_id"]),
            )
        )

        threshold_candidates = [
            row
            for row in candidates
            if row["meets_similarity_threshold"]
        ]

        selected = threshold_candidates[
            :maximum_comparables
        ]

        for rank, row in enumerate(
            selected,
            start=1,
        ):
            row["selected"] = True
            row["selection_rank"] = rank
            row["selection_reason"] = (
                "Highest governed similarity among "
                "eligible certified-history peers."
            )

        if not target_ready:
            selection_status = (
                "TARGET_EVIDENCE_NOT_READY"
            )
        elif len(selected) < minimum_comparables:
            selection_status = (
                "INSUFFICIENT_COMPARABLES"
            )
        else:
            selection_status = "PASS"

        best_score = (
            candidates[0][
                "adjusted_similarity_score"
            ]
            if candidates
            else ""
        )

        lowest_selected = (
            selected[-1][
                "adjusted_similarity_score"
            ]
            if selected
            else ""
        )

        pair_rows.extend(candidates)

        target_rows.append({
            "target_product_id": target_id,
            "target_product_name": clean(
                target.get("product_name")
            ),
            "forecast_method": clean(
                target.get("forecast_method")
            ),
            "comparable_evidence_ready": (
                target_ready
            ),
            "candidate_peer_count": len(
                candidates
            ),
            "threshold_peer_count": len(
                threshold_candidates
            ),
            "selected_peer_count": len(
                selected
            ),
            "selection_status": selection_status,
            "minimum_comparables": minimum_comparables,
            "maximum_comparables": maximum_comparables,
            "minimum_similarity_score": policy[
                "minimum_similarity_score"
            ],
            "best_similarity_score": best_score,
            "lowest_selected_similarity_score": (
                lowest_selected
            ),
            "selected_peer_ids": "|".join(
                clean(row["peer_product_id"])
                for row in selected
            ),
            "limitations": (
                "Selection uses governed proxy "
                "evidence and approximate release-era "
                "classification. No projection is "
                "generated by this engine."
            ),
            "projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "policy_version": policy[
                "policy_version"
            ],
        })

    args.output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    pair_path = (
        args.output_root
        / "collector_comparable_pair_scores.csv"
    )

    selected_path = (
        args.output_root
        / "collector_selected_comparables.csv"
    )

    target_path = (
        args.output_root
        / "collector_comparable_target_status.csv"
    )

    review_path = (
        args.output_root
        / "collector_comparable_review_required.csv"
    )

    write_csv(
        pair_path,
        pair_rows,
        PAIR_FIELDS,
    )

    selected_rows = [
        row
        for row in pair_rows
        if row["selected"]
    ]

    write_csv(
        selected_path,
        selected_rows,
        PAIR_FIELDS,
    )

    write_csv(
        target_path,
        target_rows,
        TARGET_FIELDS,
    )

    review_rows = [
        row
        for row in target_rows
        if row["selection_status"] != "PASS"
    ]

    write_csv(
        review_path,
        review_rows,
        TARGET_FIELDS,
    )

    status_counts = Counter(
        row["selection_status"]
        for row in target_rows
    )

    manifest_status = (
        "PASS"
        if (
            len(target_rows) == len(target_ids)
            and not review_rows
        )
        else "REVIEW_REQUIRED"
    )

    manifest = {
        "status": manifest_status,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "policy_version": policy[
            "policy_version"
        ],
        "target_count": len(target_rows),
        "eligible_peer_count": len(peer_ids),
        "pair_score_count": len(pair_rows),
        "selected_pair_count": len(
            selected_rows
        ),
        "passed_target_count": sum(
            row["selection_status"] == "PASS"
            for row in target_rows
        ),
        "review_required_target_count": len(
            review_rows
        ),
        "selection_status_counts": dict(
            sorted(status_counts.items())
        ),
        "projection_authorized": False,
        "purchase_recommendations_authorized": False,
        "inputs": {
            "evidence_sha256": sha256(
                args.evidence
            ),
            "router_sha256": sha256(
                args.router
            ),
            "history_sha256": sha256(
                args.history
            ),
            "policy_sha256": sha256(
                args.policy
            ),
        },
        "outputs": {
            "pair_scores": str(
                pair_path.resolve()
            ),
            "selected_comparables": str(
                selected_path.resolve()
            ),
            "target_status": str(
                target_path.resolve()
            ),
            "review_required": str(
                review_path.resolve()
            ),
        },
    }

    (
        args.output_root
        / "collector_comparable_selection_manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "COLLECTOR COMPARABLE SELECTION COMPLETE"
    )
    print(
        json.dumps(
            manifest,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()