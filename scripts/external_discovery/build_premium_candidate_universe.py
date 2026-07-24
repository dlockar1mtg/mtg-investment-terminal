from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SEALED_PATH = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_sealed_product_candidates_2026-07-22.csv"
)

DEFAULT_SECRET_LAIR_PATH = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
    / "tcgcsv_secret_lair_product_evidence_2026-07-22.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "staging"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
)

VALIDATION_ROOT = (
    ROOT
    / "data"
    / "validation"
    / "phase_10"
    / "external_discovery"
    / "tcgcsv"
)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )


def normalize_name(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_text(value).casefold(),
    ).strip()


def classify_secret_lair_product(
    *,
    group_name: object,
    product_name: object,
) -> str:
    group = normalize_name(group_name)
    product = normalize_name(product_name)
    combined = f"{group} {product}".strip()

    if any(
        term in product
        for term in (
            "bundle case",
            "display case",
            "sealed case",
            "box case",
        )
    ):
        return "secret_lair_case"

    if any(
        term in product
        for term in (
            "bundle",
            "countdown kit",
            "drop series",
        )
    ):
        return "secret_lair_bundle_or_kit"

    if any(
        term in product
        for term in (
            "insert card",
            "letter card",
            "question mark insert",
        )
    ):
        return "secret_lair_insert"

    if any(
        term in product
        for term in (
            "halo foil",
            "rainbow foil",
            "etched foil",
            "galaxy foil",
            "traditional foil",
        )
    ):
        return "secret_lair_card_variant"

    if "foil" in product:
        return "secret_lair_card_variant"

    if "secret lair" in combined:
        return "secret_lair_card_or_product"

    return "secret_lair_product_record"


def build_candidate_universe(
    *,
    sealed_path: Path,
    secret_lair_path: Path,
) -> dict[str, Any]:
    if not sealed_path.is_file():
        raise FileNotFoundError(
            f"Sealed candidate file not found: "
            f"{sealed_path}"
        )

    if not secret_lair_path.is_file():
        raise FileNotFoundError(
            f"Secret Lair candidate file not found: "
            f"{secret_lair_path}"
        )

    sealed = pd.read_csv(
        sealed_path,
        low_memory=False,
    )

    secret_lair = pd.read_csv(
        secret_lair_path,
        low_memory=False,
    )

    sealed_rows: list[dict[str, Any]] = []
    secret_lair_rows: list[
        dict[str, Any]
    ] = []

    for row in sealed.itertuples(index=False):
        product_id = clean_text(
            row.tcgplayer_product_id
        )

        sealed_rows.append(
            {
                "candidate_record_id": (
                    f"TCGCSV-CANDIDATE-{product_id}"
                ),
                "source_name": "tcgcsv",
                "source_snapshot_record_id": (
                    clean_text(
                        row.snapshot_record_id
                    )
                ),
                "tcgcsv_category_id": (
                    clean_text(
                        row.tcgcsv_category_id
                    )
                ),
                "tcgcsv_group_id": (
                    clean_text(
                        row.tcgcsv_group_id
                    )
                ),
                "tcgplayer_product_id": (
                    product_id
                ),
                "group_name": clean_text(
                    row.group_name
                ),
                "group_published_on": (
                    clean_text(
                        row.group_published_on
                    )
                ),
                "product_name": clean_text(
                    row.product_name
                ),
                "candidate_class": (
                    "sealed_product"
                ),
                "candidate_product_type": (
                    clean_text(
                        row.candidate_product_type
                    )
                ),
                "candidate_status": (
                    "potential_candidate"
                ),
                "eligibility_status": (
                    "not_evaluated"
                ),
                "scoring_status": (
                    "not_scored"
                ),
                "review_reason": "",
            }
        )

    for row in secret_lair.itertuples(
        index=False
    ):
        product_id = clean_text(
            row.tcgplayer_product_id
        )

        product_type = (
            classify_secret_lair_product(
                group_name=row.group_name,
                product_name=row.product_name,
            )
        )

        secret_lair_rows.append(
            {
                "candidate_record_id": (
                    f"TCGCSV-CANDIDATE-{product_id}"
                ),
                "source_name": "tcgcsv",
                "source_snapshot_record_id": (
                    clean_text(
                        row.snapshot_record_id
                    )
                ),
                "tcgcsv_category_id": (
                    clean_text(
                        row.tcgcsv_category_id
                    )
                ),
                "tcgcsv_group_id": (
                    clean_text(
                        row.tcgcsv_group_id
                    )
                ),
                "tcgplayer_product_id": (
                    product_id
                ),
                "group_name": clean_text(
                    row.group_name
                ),
                "group_published_on": (
                    clean_text(
                        row.group_published_on
                    )
                ),
                "product_name": clean_text(
                    row.product_name
                ),
                "candidate_class": (
                    "secret_lair_product"
                ),
                "candidate_product_type": (
                    product_type
                ),
                "candidate_status": (
                    "potential_candidate"
                ),
                "eligibility_status": (
                    "not_evaluated"
                ),
                "scoring_status": (
                    "not_scored"
                ),
                "review_reason": (
                    "secret_lair_product_level_"
                    "candidate_not_sealed_drop"
                ),
            }
        )

    universe = pd.DataFrame(
        sealed_rows + secret_lair_rows
    )

    if universe.empty:
        raise RuntimeError(
            "Candidate universe is empty."
        )

    universe = universe.sort_values(
        [
            "candidate_class",
            "candidate_product_type",
            "group_name",
            "product_name",
            "tcgplayer_product_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    duplicate_candidate_ids = int(
        universe[
            "candidate_record_id"
        ].duplicated(keep=False).sum()
    )

    duplicate_product_ids = int(
        universe[
            "tcgplayer_product_id"
        ].duplicated(keep=False).sum()
    )

    if duplicate_candidate_ids:
        raise RuntimeError(
            "Candidate record identifiers "
            "are not unique."
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    universe_path = (
        OUTPUT_ROOT
        / "tcgcsv_premium_candidate_universe_2026-07-22.csv"
    )

    summary_path = (
        VALIDATION_ROOT
        / "tcgcsv_premium_candidate_universe_summary_2026-07-22.json"
    )

    universe.to_csv(
        universe_path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    class_counts = {
        str(key): int(value)
        for key, value in (
            universe[
                "candidate_class"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    product_type_counts = {
        str(key): int(value)
        for key, value in (
            universe[
                "candidate_product_type"
            ]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary = {
        "generated_at_utc": utc_now(),
        "candidate_universe_status": (
            "POTENTIAL_CANDIDATES_ONLY"
        ),
        "sealed_product_candidate_rows": int(
            len(sealed)
        ),
        "secret_lair_candidate_rows": int(
            len(secret_lair)
        ),
        "total_candidate_rows": int(
            len(universe)
        ),
        "unique_candidate_record_ids": int(
            universe[
                "candidate_record_id"
            ].nunique()
        ),
        "unique_tcgplayer_product_ids": int(
            universe[
                "tcgplayer_product_id"
            ].nunique()
        ),
        "duplicate_candidate_id_rows": (
            duplicate_candidate_ids
        ),
        "duplicate_product_id_rows": (
            duplicate_product_ids
        ),
        "candidate_class_counts": (
            class_counts
        ),
        "candidate_product_type_counts": (
            product_type_counts
        ),
        "eligibility_evaluated": False,
        "scoring_applied": False,
        "buy_recommendations_created": False,
        "registry_changed": False,
        "database_changed": False,
        "source_files": {
            "sealed_candidates": str(
                sealed_path
            ),
            "secret_lair_candidates": str(
                secret_lair_path
            ),
        },
        "output_file": str(
            universe_path
        ),
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
        "Phase 10.5R Premium MTG "
        "Candidate Universe"
    )
    print("=" * 76)
    print(
        f"Sealed-product candidates: "
        f"{len(sealed)}"
    )
    print(
        f"Secret Lair candidates: "
        f"{len(secret_lair)}"
    )
    print(
        f"Total potential candidates: "
        f"{len(universe)}"
    )
    print(
        f"Unique TCGplayer IDs: "
        f"{summary['unique_tcgplayer_product_ids']}"
    )
    print(
        f"Duplicate candidate-ID rows: "
        f"{duplicate_candidate_ids}"
    )
    print()
    print("Candidate classes:")

    for name, count in sorted(
        class_counts.items()
    ):
        print(f"  {name}: {count}")

    print()
    print(f"Universe: {universe_path}")
    print(f"Summary: {summary_path}")
    print()
    print(
        "PREMIUM MTG CANDIDATE "
        "UNIVERSE: PASS"
    )
    print(
        "Eligibility: NOT EVALUATED"
    )
    print(
        "Scoring: NOT APPLIED"
    )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--sealed-candidates",
        type=Path,
        default=DEFAULT_SEALED_PATH,
    )

    parser.add_argument(
        "--secret-lair-candidates",
        type=Path,
        default=DEFAULT_SECRET_LAIR_PATH,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    build_candidate_universe(
        sealed_path=(
            args.sealed_candidates.resolve()
        ),
        secret_lair_path=(
            args.secret_lair_candidates.resolve()
        ),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())