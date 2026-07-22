from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_CANDIDATE_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_premium_candidate_universe_2026-07-22.csv"
)

DEFAULT_REGISTRY_PATH = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "reconciliation"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "reconciliation"
)

SCHEMA_VERSION = "10.5R.1B.3"


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def is_missing(value: object) -> bool:
    if value is None:
        return True

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def clean_text(value: object) -> str:
    if is_missing(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def normalize_identifier(value: object) -> str:
    text = clean_text(value)

    if not text:
        return ""

    if re.fullmatch(
        r"\d+\.0",
        text,
    ):
        text = text[:-2]

    return text


def normalize_name(value: object) -> str:
    text = clean_text(value).casefold()

    replacements = {
        "&": " and ",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢": "'",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“": "-",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â": "-",
    }

    for source, target in replacements.items():
        text = text.replace(
            source,
            target,
        )

    text = re.sub(
        r"\bmagic\s*:\s*the\s+gathering\b",
        " ",
        text,
    )

    text = re.sub(
        r"\bmtg\b",
        " ",
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


def first_available(
    row: pd.Series,
    columns: tuple[str, ...],
) -> str:
    for column in columns:
        if column not in row.index:
            continue

        value = clean_text(
            row[column]
        )

        if value:
            return value

    return ""


def registry_display_name(
    row: pd.Series,
) -> str:
    return first_available(
        row,
        (
            "approved_product_name",
            "box_name",
            "product_name",
            "canonical_product_name",
            "name",
        ),
    )


def registry_set_name(
    row: pd.Series,
) -> str:
    return first_available(
        row,
        (
            "set_name",
            "group_name",
            "canonical_set_name",
        ),
    )


def registry_product_type(
    row: pd.Series,
) -> str:
    return first_available(
        row,
        (
            "investment_product_type",
            "product_type",
            "approved_product_type",
            "candidate_product_type",
        ),
    )


def registry_approval_status(
    row: pd.Series,
) -> str:
    return first_available(
        row,
        (
            "approval_status",
            "status",
            "registry_status",
        ),
    )


def registry_record_id(
    row: pd.Series,
) -> str:
    return first_available(
        row,
        (
            "investment_product_id",
            "registry_record_id",
            "product_id",
        ),
    )


def classify_type_family(
    value: object,
) -> str:
    text = normalize_name(value)

    if not text:
        return "unknown"

    if "secret lair" in text:
        if "insert" in text:
            return "secret_lair_insert"

        if any(
            term in text
            for term in (
                "foil",
                "variant",
                "single card",
                "card",
            )
        ):
            return "secret_lair_card"

        if any(
            term in text
            for term in (
                "bundle",
                "kit",
                "drop",
            )
        ):
            return "secret_lair_product"

        return "secret_lair_product"

    if "case" in text:
        return "sealed_case"

    if "collector" in text:
        return "collector_booster_display"

    if "play booster" in text:
        return "play_booster_display"

    if "set booster" in text:
        return "set_booster_display"

    if "draft booster" in text:
        return "draft_booster_display"

    if "theme booster" in text:
        return "theme_booster_display"

    if "jumpstart" in text:
        return "jumpstart_booster_display"

    if any(
        term in text
        for term in (
            "traditional booster",
            "booster display",
            "booster box",
            "masters",
        )
    ):
        return "traditional_booster_display"

    if "bundle" in text:
        return "bundle"

    if "commander" in text:
        return "commander_deck"

    return "unknown"


def candidate_type_family(
    candidate_class: object,
    candidate_type: object,
) -> str:
    candidate_class_text = clean_text(
        candidate_class
    )

    candidate_type_text = clean_text(
        candidate_type
    )

    if candidate_class_text == (
        "secret_lair_product"
    ):
        if candidate_type_text == (
            "secret_lair_insert"
        ):
            return "secret_lair_insert"

        if candidate_type_text in {
            "secret_lair_card_variant",
            "secret_lair_card_or_product",
            "secret_lair_product_record",
        }:
            return "secret_lair_card"

        return "secret_lair_product"

    return classify_type_family(
        candidate_type_text
    )


def compare_type_families(
    candidate_family: str,
    registry_family: str,
) -> str:
    if registry_family == "unknown":
        return "registry_type_unknown"

    if candidate_family == "unknown":
        return "candidate_type_unknown"

    if candidate_family == registry_family:
        return "compatible"

    booster_display_families = {
        "traditional_booster_display",
        "draft_booster_display",
        "theme_booster_display",
        "jumpstart_booster_display",
        "play_booster_display",
        "set_booster_display",
    }

    if (
        candidate_family in booster_display_families
        and registry_family
        == "traditional_booster_display"
    ):
        return (
            "compatible_registry_generic_"
            "booster_display"
        )

    registry_display_families = {
        "traditional_booster_display",
        "draft_booster_display",
        "collector_booster_display",
    }

    if (
        candidate_family == "sealed_case"
        and registry_family
        in registry_display_families
    ):
        return (
            "compatible_registry_generic_"
            "case_packaging"
        )

    secret_lair_families = {
        "secret_lair_card",
        "secret_lair_insert",
        "secret_lair_product",
    }

    if (
        candidate_family in secret_lair_families
        and registry_family
        in secret_lair_families
    ):
        return (
            "compatible_registry_generic_"
            "secret_lair"
        )

    return "type_conflict"


def build_registry_indexes(
    registry: pd.DataFrame,
) -> tuple[
    dict[str, list[int]],
    dict[str, list[int]],
    dict[str, list[int]],
]:
    id_index: dict[
        str,
        list[int],
    ] = defaultdict(list)

    name_index: dict[
        str,
        list[int],
    ] = defaultdict(list)

    set_product_index: dict[
        str,
        list[int],
    ] = defaultdict(list)

    for index, row in registry.iterrows():
        product_id = normalize_identifier(
            first_available(
                row,
                (
                    "approved_tcgplayer_product_id",
                    "tcgplayer_product_id",
                    "source_product_id",
                ),
            )
        )

        if product_id:
            id_index[product_id].append(
                index
            )

        product_name = normalize_name(
            registry_display_name(row)
        )

        set_name = normalize_name(
            registry_set_name(row)
        )

        if product_name:
            name_index[
                product_name
            ].append(index)

        if set_name and product_name:
            key = (
                f"{set_name}|"
                f"{product_name}"
            )

            set_product_index[
                key
            ].append(index)

    return (
        dict(id_index),
        dict(name_index),
        dict(set_product_index),
    )


def registry_match_values(
    registry: pd.DataFrame,
    indexes: list[int],
) -> dict[str, str]:
    if not indexes:
        return {
            "matched_registry_row_count": "0",
            "matched_registry_record_ids": "",
            "matched_registry_product_ids": "",
            "matched_registry_names": "",
            "matched_registry_types": "",
            "matched_registry_statuses": "",
        }

    record_ids: list[str] = []
    product_ids: list[str] = []
    names: list[str] = []
    product_types: list[str] = []
    statuses: list[str] = []

    for index in indexes:
        row = registry.loc[index]

        record_ids.append(
            registry_record_id(row)
        )

        product_ids.append(
            normalize_identifier(
                first_available(
                    row,
                    (
                        "approved_tcgplayer_product_id",
                        "tcgplayer_product_id",
                        "source_product_id",
                    ),
                )
            )
        )

        names.append(
            registry_display_name(row)
        )

        product_types.append(
            registry_product_type(row)
        )

        statuses.append(
            registry_approval_status(row)
        )

    def joined(values: list[str]) -> str:
        cleaned = sorted(
            {
                value
                for value in values
                if value
            }
        )

        return "|".join(cleaned)

    return {
        "matched_registry_row_count": str(
            len(indexes)
        ),
        "matched_registry_record_ids": joined(
            record_ids
        ),
        "matched_registry_product_ids": joined(
            product_ids
        ),
        "matched_registry_names": joined(
            names
        ),
        "matched_registry_types": joined(
            product_types
        ),
        "matched_registry_statuses": joined(
            statuses
        ),
    }


def reconcile_candidates(
    *,
    candidates: pd.DataFrame,
    registry: pd.DataFrame,
) -> pd.DataFrame:
    (
        id_index,
        name_index,
        set_product_index,
    ) = build_registry_indexes(
        registry
    )

    output_rows: list[
        dict[str, Any]
    ] = []

    for _, candidate in candidates.iterrows():
        product_id = normalize_identifier(
            candidate.get(
                "tcgplayer_product_id"
            )
        )

        product_name = clean_text(
            candidate.get(
                "product_name"
            )
        )

        group_name = clean_text(
            candidate.get(
                "group_name"
            )
        )

        normalized_product_name = (
            normalize_name(product_name)
        )

        normalized_group_name = (
            normalize_name(group_name)
        )

        set_product_key = ""

        if (
            normalized_group_name
            and normalized_product_name
        ):
            set_product_key = (
                f"{normalized_group_name}|"
                f"{normalized_product_name}"
            )

        match_method = ""
        reconciliation_status = ""
        matched_indexes: list[int] = []

        if product_id and product_id in id_index:
            matched_indexes = id_index[
                product_id
            ]

            match_method = (
                "tcgplayer_product_id"
            )

            if len(matched_indexes) == 1:
                reconciliation_status = (
                    "exact_id_match"
                )
            else:
                reconciliation_status = (
                    "ambiguous_exact_id_match"
                )

        elif (
            set_product_key
            and set_product_key
            in set_product_index
        ):
            matched_indexes = (
                set_product_index[
                    set_product_key
                ]
            )

            match_method = (
                "normalized_set_and_name"
            )

            if len(matched_indexes) == 1:
                reconciliation_status = (
                    "normalized_name_match"
                )
            else:
                reconciliation_status = (
                    "ambiguous_name_match"
                )

        elif (
            normalized_product_name
            and normalized_product_name
            in name_index
        ):
            matched_indexes = name_index[
                normalized_product_name
            ]

            match_method = (
                "normalized_product_name"
            )

            if len(matched_indexes) == 1:
                reconciliation_status = (
                    "normalized_name_match"
                )
            else:
                reconciliation_status = (
                    "ambiguous_name_match"
                )

        elif not product_id:
            reconciliation_status = (
                "missing_candidate_id"
            )
            match_method = "none"

        else:
            reconciliation_status = (
                "new_candidate"
            )
            match_method = "none"

        candidate_family = (
            candidate_type_family(
                candidate.get(
                    "candidate_class"
                ),
                candidate.get(
                    "candidate_product_type"
                ),
            )
        )

        registry_families = sorted(
            {
                classify_type_family(
                    registry_product_type(
                        registry.loc[index]
                    )
                )
                for index in matched_indexes
            }
        )

        if not matched_indexes:
            type_alignment = (
                "not_applicable"
            )
            registry_family = ""
        elif len(registry_families) == 1:
            registry_family = (
                registry_families[0]
            )

            type_alignment = (
                compare_type_families(
                    candidate_family,
                    registry_family,
                )
            )
        else:
            registry_family = "|".join(
                registry_families
            )
            type_alignment = (
                "multiple_registry_types"
            )

        review_reasons: list[str] = []

        if reconciliation_status in {
            "ambiguous_exact_id_match",
            "ambiguous_name_match",
            "missing_candidate_id",
        }:
            review_reasons.append(
                reconciliation_status
            )

        if type_alignment in {
            "type_conflict",
            "multiple_registry_types",
            "candidate_type_unknown",
            "registry_type_unknown",
        }:
            review_reasons.append(
                type_alignment
            )

        review_required = bool(
            review_reasons
        )

        match_values = (
            registry_match_values(
                registry,
                matched_indexes,
            )
        )

        output = {
            "candidate_record_id": (
                clean_text(
                    candidate.get(
                        "candidate_record_id"
                    )
                )
            ),
            "source_name": clean_text(
                candidate.get(
                    "source_name"
                )
            ),
            "tcgplayer_product_id": (
                product_id
            ),
            "group_name": group_name,
            "product_name": product_name,
            "candidate_class": clean_text(
                candidate.get(
                    "candidate_class"
                )
            ),
            "candidate_product_type": (
                clean_text(
                    candidate.get(
                        "candidate_product_type"
                    )
                )
            ),
            "candidate_type_family": (
                candidate_family
            ),
            "reconciliation_status": (
                reconciliation_status
            ),
            "match_method": (
                match_method
            ),
            "type_alignment": (
                type_alignment
            ),
            "registry_type_family": (
                registry_family
            ),
            "review_required": (
                review_required
            ),
            "review_reason": "|".join(
                review_reasons
            ),
            "eligibility_status": (
                clean_text(
                    candidate.get(
                        "eligibility_status"
                    )
                )
            ),
            "scoring_status": (
                clean_text(
                    candidate.get(
                        "scoring_status"
                    )
                )
            ),
        }

        output.update(
            match_values
        )

        output_rows.append(output)

    result = pd.DataFrame(
        output_rows
    )

    return result.sort_values(
        [
            "reconciliation_status",
            "candidate_class",
            "candidate_product_type",
            "group_name",
            "product_name",
            "tcgplayer_product_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def write_outputs(
    *,
    reconciliation: pd.DataFrame,
    candidate_path: Path,
    registry_path: Path,
    candidate_count: int,
    registry_count: int,
) -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    full_path = (
        OUTPUT_ROOT
        / "tcgcsv_candidate_reconciliation_2026-07-22.csv"
    )

    exact_path = (
        VALIDATION_ROOT
        / "tcgcsv_exact_id_matches_2026-07-22.csv"
    )

    name_path = (
        VALIDATION_ROOT
        / "tcgcsv_normalized_name_matches_2026-07-22.csv"
    )

    new_path = (
        VALIDATION_ROOT
        / "tcgcsv_new_candidates_2026-07-22.csv"
    )

    ambiguous_path = (
        VALIDATION_ROOT
        / "tcgcsv_ambiguous_matches_2026-07-22.csv"
    )

    conflicts_path = (
        VALIDATION_ROOT
        / "tcgcsv_type_conflicts_2026-07-22.csv"
    )

    review_path = (
        VALIDATION_ROOT
        / "tcgcsv_reconciliation_review_queue_2026-07-22.csv"
    )

    summary_path = (
        VALIDATION_ROOT
        / "tcgcsv_candidate_reconciliation_summary_2026-07-22.json"
    )

    exact = reconciliation[
        reconciliation[
            "reconciliation_status"
        ].eq("exact_id_match")
    ].copy()

    name_matches = reconciliation[
        reconciliation[
            "reconciliation_status"
        ].eq("normalized_name_match")
    ].copy()

    new_candidates = reconciliation[
        reconciliation[
            "reconciliation_status"
        ].eq("new_candidate")
    ].copy()

    ambiguous = reconciliation[
        reconciliation[
            "reconciliation_status"
        ].isin(
            {
                "ambiguous_exact_id_match",
                "ambiguous_name_match",
                "missing_candidate_id",
            }
        )
    ].copy()

    conflicts = reconciliation[
        reconciliation[
            "type_alignment"
        ].isin(
            {
                "type_conflict",
                "multiple_registry_types",
                "candidate_type_unknown",
                "registry_type_unknown",
            }
        )
    ].copy()

    review_queue = reconciliation[
        reconciliation[
            "review_required"
        ].eq(True)
    ].copy()

    outputs = {
        full_path: reconciliation,
        exact_path: exact,
        name_path: name_matches,
        new_path: new_candidates,
        ambiguous_path: ambiguous,
        conflicts_path: conflicts,
        review_path: review_queue,
    }

    for path, frame in outputs.items():
        frame.to_csv(
            path,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )

    status_counts = {
        str(key): int(value)
        for key, value in (
            reconciliation[
                "reconciliation_status"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    alignment_counts = {
        str(key): int(value)
        for key, value in (
            reconciliation[
                "type_alignment"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    class_counts = {
        str(key): int(value)
        for key, value in (
            reconciliation[
                "candidate_class"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "reconciliation_status": (
            "COMPLETE"
        ),
        "candidate_source_path": str(
            candidate_path
        ),
        "registry_source_path": str(
            registry_path
        ),
        "candidate_rows": int(
            candidate_count
        ),
        "registry_rows": int(
            registry_count
        ),
        "reconciled_rows": int(
            len(reconciliation)
        ),
        "unique_candidate_record_ids": int(
            reconciliation[
                "candidate_record_id"
            ].nunique()
        ),
        "unique_candidate_product_ids": int(
            reconciliation[
                "tcgplayer_product_id"
            ].nunique()
        ),
        "reconciliation_status_counts": (
            status_counts
        ),
        "type_alignment_counts": (
            alignment_counts
        ),
        "candidate_class_counts": (
            class_counts
        ),
        "exact_id_match_rows": int(
            len(exact)
        ),
        "normalized_name_match_rows": int(
            len(name_matches)
        ),
        "new_candidate_rows": int(
            len(new_candidates)
        ),
        "ambiguous_or_missing_id_rows": int(
            len(ambiguous)
        ),
        "type_conflict_or_review_rows": int(
            len(conflicts)
        ),
        "review_queue_rows": int(
            len(review_queue)
        ),
        "eligibility_changed": False,
        "approval_status_changed": False,
        "registry_changed": False,
        "database_changed": False,
        "scoring_applied": False,
        "buy_recommendations_created": False,
        "output_files": {
            "full_reconciliation": str(
                full_path
            ),
            "exact_id_matches": str(
                exact_path
            ),
            "normalized_name_matches": str(
                name_path
            ),
            "new_candidates": str(
                new_path
            ),
            "ambiguous_matches": str(
                ambiguous_path
            ),
            "type_conflicts": str(
                conflicts_path
            ),
            "review_queue": str(
                review_path
            ),
        },
    }

    summary_path.write_text(
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
        "Phase 10.5R.1B.3 "
        "TCGCSV Candidate Reconciliation"
    )
    print("=" * 76)
    print(
        f"Candidate rows: "
        f"{candidate_count}"
    )
    print(
        f"Registry rows: "
        f"{registry_count}"
    )
    print(
        f"Reconciled rows: "
        f"{len(reconciliation)}"
    )
    print()
    print("Reconciliation outcomes:")

    for name, count in sorted(
        status_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(f"  {name}: {count}")

    print()
    print("Type alignment:")

    for name, count in sorted(
        alignment_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(f"  {name}: {count}")

    print()
    print(
        f"Review queue: "
        f"{len(review_queue)}"
    )
    print(f"Full output: {full_path}")
    print(f"Summary: {summary_path}")
    print()
    print(
        "PHASE 10.5R.1B.3 "
        "TCGCSV RECONCILIATION: PASS"
    )
    print(
        "Eligibility: UNCHANGED"
    )
    print(
        "Registry: UNCHANGED"
    )
    print(
        "Scoring: NOT APPLIED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_CANDIDATE_PATH,
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    candidate_path = (
        args.candidates.resolve()
    )

    registry_path = (
        args.registry.resolve()
    )

    if not candidate_path.is_file():
        raise FileNotFoundError(
            f"Candidate universe not found: "
            f"{candidate_path}"
        )

    if not registry_path.is_file():
        raise FileNotFoundError(
            f"Registry not found: "
            f"{registry_path}"
        )

    candidates = pd.read_csv(
        candidate_path,
        low_memory=False,
    )

    registry = pd.read_csv(
        registry_path,
        low_memory=False,
    )

    required_candidate_columns = {
        "candidate_record_id",
        "tcgplayer_product_id",
        "group_name",
        "product_name",
        "candidate_class",
        "candidate_product_type",
        "eligibility_status",
        "scoring_status",
    }

    missing_candidate_columns = sorted(
        required_candidate_columns
        - set(candidates.columns)
    )

    if missing_candidate_columns:
        raise ValueError(
            "Candidate universe is missing columns: "
            + ", ".join(
                missing_candidate_columns
            )
        )

    reconciliation = (
        reconcile_candidates(
            candidates=candidates,
            registry=registry,
        )
    )

    if len(reconciliation) != len(
        candidates
    ):
        raise RuntimeError(
            "Reconciliation row count does not "
            "match candidate row count."
        )

    write_outputs(
        reconciliation=reconciliation,
        candidate_path=candidate_path,
        registry_path=registry_path,
        candidate_count=len(candidates),
        registry_count=len(registry),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())