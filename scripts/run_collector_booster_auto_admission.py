from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONFIG = (
    ROOT
    / "config"
    / "mtg"
    / "governance"
    / "collector_booster_auto_admission_v1.json"
)

DEFAULT_REGISTRY = (
    ROOT
    / "data"
    / "product_master"
    / "investment_products.csv"
)

DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "data"
    / "operations"
    / "collector_booster_admission"
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalized(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def number(value: Any) -> float | None:
    text = clean(value).replace("$", "").replace(",", "")
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def parse_note_number(notes: str, key: str) -> float | None:
    pattern = rf"(?:^|;\s*){re.escape(key)}=([-+]?[0-9]*\.?[0-9]+)"
    match = re.search(pattern, clean(notes), flags=re.IGNORECASE)

    if not match:
        return None

    return number(match.group(1))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if fieldnames is None:
        fieldnames = []

        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest().upper()


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_candidate(
    row: dict[str, str],
    config: dict[str, Any],
    existing_ids: set[str],
    existing_tcgplayer_ids: set[str],
    existing_identity_keys: set[tuple[str, str]],
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []

    required_fields = config["required_fields"]

    for field in required_fields:
        if not clean(row.get(field)):
            reasons.append(f"MISSING_REQUIRED_FIELD:{field}")

    investment_id = clean(row.get("investment_product_id"))
    tcgplayer_id = clean(row.get("approved_tcgplayer_product_id"))
    group_id = clean(row.get("tcgcsv_group_id"))
    product_type = clean(row.get("investment_product_type"))
    approval_status = normalized(row.get("approval_status"))
    approval_method = clean(row.get("approval_method"))
    box_name = clean(row.get("box_name"))
    approved_name = clean(row.get("approved_product_name"))
    notes = clean(row.get("notes"))

    candidate_score = parse_note_number(notes, "candidate_score")
    market_price = parse_note_number(notes, "market_price")

    if investment_id in existing_ids:
        reasons.append("PRODUCT_ALREADY_EXISTS")

    if tcgplayer_id and tcgplayer_id in existing_tcgplayer_ids:
        reasons.append("TCGPLAYER_PRODUCT_ID_ALREADY_EXISTS")

    identity_key = (
        normalized(box_name),
        tcgplayer_id,
    )

    if identity_key in existing_identity_keys:
        reasons.append("IDENTITY_KEY_ALREADY_EXISTS")

    if product_type not in config["allowed_product_types"]:
        reasons.append("PRODUCT_TYPE_NOT_ALLOWED")

    allowed_statuses = {
        normalized(value)
        for value in config["required_approval_statuses"]
    }

    if approval_status not in allowed_statuses:
        reasons.append("APPROVAL_STATUS_NOT_ALLOWED")

    if approval_method not in config["allowed_discovery_methods"]:
        reasons.append("DISCOVERY_METHOD_NOT_ALLOWED")

    if candidate_score is None:
        reasons.append("CANDIDATE_SCORE_MISSING")
    elif candidate_score < float(config["minimum_candidate_score"]):
        reasons.append("CANDIDATE_SCORE_BELOW_THRESHOLD")

    if market_price is None:
        reasons.append("MARKET_PRICE_MISSING")
    elif market_price < float(config["minimum_market_price"]):
        reasons.append("MARKET_PRICE_BELOW_THRESHOLD")

    combined_name = normalized(f"{box_name} {approved_name}")

    for conflict_term in config["identity_conflict_terms"]:
        normalized_term = normalized(conflict_term)

        if normalized_term and normalized_term in combined_name:
            reasons.append(
                f"IDENTITY_CONFLICT_TERM:{normalized_term}"
            )

    if not tcgplayer_id.isdigit():
        reasons.append("TCGPLAYER_PRODUCT_ID_INVALID")

    if not group_id.isdigit():
        reasons.append("TCGCSV_GROUP_ID_INVALID")

    if "collector booster display" not in combined_name:
        reasons.append("DISPLAY_IDENTITY_NOT_CONFIRMED")

    auto_admit = len(reasons) == 0

    metadata = {
        "candidate_score": candidate_score,
        "market_price": market_price,
        "identity_key": "|".join(identity_key),
    }

    return auto_admit, reasons, metadata


def run(
    candidate_path: Path,
    registry_path: Path,
    config_path: Path,
    output_root: Path,
    apply: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    candidates = read_csv(candidate_path)
    registry = read_csv(registry_path)

    existing_ids = {
        clean(row.get("investment_product_id"))
        for row in registry
        if clean(row.get("investment_product_id"))
    }

    existing_tcgplayer_ids = {
        clean(row.get("approved_tcgplayer_product_id"))
        for row in registry
        if clean(row.get("approved_tcgplayer_product_id"))
    }

    existing_identity_keys = {
        (
            normalized(row.get("box_name")),
            clean(row.get("approved_tcgplayer_product_id")),
        )
        for row in registry
    }

    admitted: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for candidate in candidates:
        auto_admit, reasons, metadata = validate_candidate(
            candidate,
            config,
            existing_ids,
            existing_tcgplayer_ids,
            existing_identity_keys,
        )

        evaluated = dict(candidate)
        evaluated["admission_policy_version"] = config["policy_version"]
        evaluated["evaluated_at_utc"] = datetime.now(
            timezone.utc
        ).isoformat()
        evaluated["candidate_score_parsed"] = metadata[
            "candidate_score"
        ]
        evaluated["market_price_parsed"] = metadata[
            "market_price"
        ]
        evaluated["admission_reason_codes"] = "|".join(reasons)

        if auto_admit:
            evaluated["admission_status"] = "AUTO_ADMITTED"
            evaluated["identity_status"] = "VERIFIED"
            evaluated["forecast_status"] = "HISTORY_ACCUMULATING"
            evaluated["purchase_recommendation_authorized"] = "false"

            production_row = {
                key: candidate.get(key, "")
                for key in registry[0].keys()
            }
            production_row["approval_status"] = "approved"
            production_row["approval_method"] = (
                "governed_auto_admission_v1"
            )

            existing_notes = clean(production_row.get("notes"))
            production_row["notes"] = (
                existing_notes
                + (
                    "; "
                    if existing_notes
                    else ""
                )
                + "admission_policy=collector_booster_auto_admission_v1"
            )

            evaluated["production_row"] = production_row
            admitted.append(evaluated)

            existing_ids.add(
                clean(candidate.get("investment_product_id"))
            )
            existing_tcgplayer_ids.add(
                clean(
                    candidate.get(
                        "approved_tcgplayer_product_id"
                    )
                )
            )
            existing_identity_keys.add(
                (
                    normalized(candidate.get("box_name")),
                    clean(
                        candidate.get(
                            "approved_tcgplayer_product_id"
                        )
                    ),
                )
            )
        else:
            evaluated["admission_status"] = "REVIEW_REQUIRED"
            evaluated["identity_status"] = "UNRESOLVED"
            evaluated["forecast_status"] = "NOT_ELIGIBLE"
            evaluated["purchase_recommendation_authorized"] = "false"
            review.append(evaluated)

    output_root.mkdir(parents=True, exist_ok=True)

    admitted_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "production_row"
        }
        for row in admitted
    ]

    write_csv(
        output_root / "auto_admitted_candidates.csv",
        admitted_rows,
    )

    write_csv(
        output_root / "manual_review_candidates.csv",
        review,
    )

    proposed_registry = list(registry)
    proposed_registry.extend(
        row["production_row"]
        for row in admitted
    )

    registry_fields = list(registry[0].keys())

    write_csv(
        output_root / "proposed_investment_products.csv",
        proposed_registry,
        registry_fields,
    )

    backup_path: Path | None = None

    if apply and admitted:
        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        backup_path = (
            output_root
            / "backups"
            / timestamp
            / registry_path.name
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(registry_path, backup_path)

        write_csv(
            registry_path,
            proposed_registry,
            registry_fields,
        )

    manifest = {
        "status": (
            "CERTIFIED"
            if not review
            else "CERTIFIED_WITH_REVIEW_QUEUE"
        ),
        "policy_name": config["policy_name"],
        "policy_version": config["policy_version"],
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "apply_requested": apply,
        "production_registry_changed": bool(apply and admitted),
        "candidate_count": len(candidates),
        "auto_admitted_count": len(admitted),
        "manual_review_count": len(review),
        "registry_rows_before": len(registry),
        "registry_rows_proposed": len(proposed_registry),
        "registry_rows_after": (
            len(proposed_registry)
            if apply
            else len(registry)
        ),
        "backup_path": (
            str(backup_path.resolve())
            if backup_path
            else None
        ),
        "inputs": {
            "candidate_path": str(candidate_path.resolve()),
            "candidate_sha256": sha256(candidate_path),
            "registry_path": str(registry_path.resolve()),
            "registry_sha256_before": sha256(registry_path),
            "config_path": str(config_path.resolve()),
            "config_sha256": sha256(config_path),
        },
        "outputs": {
            "auto_admitted_candidates": str(
                (
                    output_root
                    / "auto_admitted_candidates.csv"
                ).resolve()
            ),
            "manual_review_candidates": str(
                (
                    output_root
                    / "manual_review_candidates.csv"
                ).resolve()
            ),
            "proposed_registry": str(
                (
                    output_root
                    / "proposed_investment_products.csv"
                ).resolve()
            ),
        },
    }

    manifest_path = output_root / "admission_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("COLLECTOR BOOSTER AUTO-ADMISSION: COMPLETE")
    print(json.dumps(manifest, indent=2))

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Collector Booster discovery candidates "
            "under the governed automatic admission policy."
        )
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply qualifying additions to the production "
            "registry after writing a backup."
        ),
    )

    args = parser.parse_args()

    run(
        candidate_path=args.candidates,
        registry_path=args.registry,
        config_path=args.config,
        output_root=args.output_root,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()