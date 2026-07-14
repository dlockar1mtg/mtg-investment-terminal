from __future__ import annotations

from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from terminal2.secret_lair.identifiers import (
    normalize_text,
    slug,
    stable_secret_lair_id,
)


def _text_score(left: object, right: object) -> float:
    a = slug(left)
    b = slug(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    return SequenceMatcher(None, a, b).ratio() * 100.0


def _date_score(left: object, right: object) -> float:
    a = pd.to_datetime(left, errors="coerce")
    b = pd.to_datetime(right, errors="coerce")
    if pd.isna(a) or pd.isna(b):
        return 50.0
    difference = abs((a - b).days)
    if difference == 0:
        return 100.0
    if difference <= 7:
        return 90.0
    if difference <= 31:
        return 70.0
    if difference <= 90:
        return 40.0
    return 0.0


def _candidate_score(source: pd.Series, target: pd.Series) -> float:
    drop = _text_score(source["drop_name"], target["drop_name"])
    variant = _text_score(
        source["variant_name"],
        target["variant_name"],
    )
    finish = (
        100.0
        if normalize_text(source["finish"]).lower()
        == normalize_text(target["finish"]).lower()
        else 0.0
    )
    release = _date_score(
        source.get("release_date"),
        target.get("release_date"),
    )
    franchise = _text_score(
        source.get("franchise"),
        target.get("franchise"),
    )
    return round(
        drop * 0.42
        + variant * 0.23
        + finish * 0.20
        + release * 0.10
        + franchise * 0.05,
        2,
    )


def match_source_catalog(
    source_catalog: pd.DataFrame,
    registry: pd.DataFrame,
    overrides: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result_columns = [
        "source_name",
        "source_record_id",
        "secret_lair_id",
        "match_status",
        "match_method",
        "match_confidence",
        "best_candidate_id",
        "best_candidate_score",
        "second_candidate_score",
        "drop_name",
        "variant_name",
        "finish",
    ]
    review_columns = [
        "source_name",
        "source_record_id",
        "drop_name",
        "variant_name",
        "finish",
        "review_reason",
        "best_candidate_id",
        "best_candidate_score",
        "second_candidate_score",
        "recommended_action",
    ]
    if source_catalog.empty:
        return (
            pd.DataFrame(columns=result_columns),
            pd.DataFrame(columns=review_columns),
        )

    registry = registry.copy()
    source_index = {}
    if not registry.empty:
        for _, row in registry.iterrows():
            source_key = (
                normalize_text(row.get("source_name")).lower(),
                normalize_text(row.get("source_record_id")),
            )
            if all(source_key):
                source_index[source_key] = row["secret_lair_id"]

    override_index = {}
    if not overrides.empty:
        for _, row in overrides.iterrows():
            override_index[
                (
                    row["source_name"].lower(),
                    row["source_record_id"],
                )
            ] = row

    results = []
    reviews = []
    for _, source in source_catalog.iterrows():
        key = (
            source["source_name"].lower(),
            source["source_record_id"],
        )
        required_complete = all(
            normalize_text(source.get(column))
            for column in (
                "source_name",
                "source_record_id",
                "drop_name",
                "variant_name",
                "finish",
            )
        )

        override = override_index.get(key)
        if override is not None:
            action = normalize_text(
                override.get("override_action")
            ).lower()
            if action == "reject":
                results.append({
                    **source.to_dict(),
                    "secret_lair_id": "",
                    "match_status": "rejected",
                    "match_method": "manual_override",
                    "match_confidence": 100.0,
                    "best_candidate_id": "",
                    "best_candidate_score": 0.0,
                    "second_candidate_score": 0.0,
                })
                continue
            if action in {"match", "accept"}:
                asset_id = normalize_text(
                    override.get("secret_lair_id")
                )
                results.append({
                    **source.to_dict(),
                    "secret_lair_id": asset_id,
                    "match_status": "matched",
                    "match_method": "manual_override",
                    "match_confidence": 100.0,
                    "best_candidate_id": asset_id,
                    "best_candidate_score": 100.0,
                    "second_candidate_score": 0.0,
                })
                continue

        if key in source_index:
            asset_id = source_index[key]
            results.append({
                **source.to_dict(),
                "secret_lair_id": asset_id,
                "match_status": "matched",
                "match_method": "exact_source_identity",
                "match_confidence": 100.0,
                "best_candidate_id": asset_id,
                "best_candidate_score": 100.0,
                "second_candidate_score": 0.0,
            })
            continue

        if not required_complete:
            reviews.append({
                **source.to_dict(),
                "review_reason": "missing_required_identity_fields",
                "best_candidate_id": "",
                "best_candidate_score": 0.0,
                "second_candidate_score": 0.0,
                "recommended_action": "complete_source_metadata",
            })
            results.append({
                **source.to_dict(),
                "secret_lair_id": "",
                "match_status": "review",
                "match_method": "incomplete_identity",
                "match_confidence": 0.0,
                "best_candidate_id": "",
                "best_candidate_score": 0.0,
                "second_candidate_score": 0.0,
            })
            continue

        candidates = []
        if not registry.empty:
            for _, target in registry.iterrows():
                candidates.append(
                    (
                        _candidate_score(source, target),
                        str(target["secret_lair_id"]),
                    )
                )
        candidates.sort(reverse=True)
        best_score, best_id = (
            candidates[0] if candidates else (0.0, "")
        )
        second_score = (
            candidates[1][0] if len(candidates) > 1 else 0.0
        )
        margin = best_score - second_score

        if best_score >= 92 and margin >= 8:
            results.append({
                **source.to_dict(),
                "secret_lair_id": best_id,
                "match_status": "matched",
                "match_method": "high_confidence_metadata",
                "match_confidence": best_score,
                "best_candidate_id": best_id,
                "best_candidate_score": best_score,
                "second_candidate_score": second_score,
            })
        elif best_score >= 75:
            reviews.append({
                **source.to_dict(),
                "review_reason": "ambiguous_existing_match",
                "best_candidate_id": best_id,
                "best_candidate_score": best_score,
                "second_candidate_score": second_score,
                "recommended_action": "review_match_or_add_override",
            })
            results.append({
                **source.to_dict(),
                "secret_lair_id": "",
                "match_status": "review",
                "match_method": "ambiguous_metadata",
                "match_confidence": best_score,
                "best_candidate_id": best_id,
                "best_candidate_score": best_score,
                "second_candidate_score": second_score,
            })
        else:
            generated = stable_secret_lair_id(
                drop_name=source["drop_name"],
                variant_name=source["variant_name"],
                finish=source["finish"],
                source_record_id=(
                    f"{source['source_name']}:"
                    f"{source['source_record_id']}"
                ),
            )
            results.append({
                **source.to_dict(),
                "secret_lair_id": generated,
                "match_status": "new_asset",
                "match_method": "deterministic_new_identity",
                "match_confidence": 100.0,
                "best_candidate_id": best_id,
                "best_candidate_score": best_score,
                "second_candidate_score": second_score,
            })

    result = pd.DataFrame(results)
    for column in result_columns:
        if column not in result.columns:
            result[column] = pd.NA
    review = pd.DataFrame(reviews)
    for column in review_columns:
        if column not in review.columns:
            review[column] = pd.NA
    return result[result_columns], review[review_columns]
