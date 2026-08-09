from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/mtg/standards/precollector_candidate_universe_inventory_contract_v1.json"
SCOPE_PATH = ROOT / "config/mtg/governance/precollector_booster_product_scope_owner_decision_v1.json"


@dataclass(frozen=True)
class SourceCandidate:
    path: Path
    frame: pd.DataFrame
    product_id_col: str
    product_name_col: str
    group_id_col: str
    group_name_col: str | None
    score: int


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_table(path: Path) -> pd.DataFrame | None:
    try:
        if path.suffix.casefold() == ".csv":
            return pd.read_csv(path, low_memory=False)
        if path.suffix.casefold() == ".json":
            payload = _load_json(path)
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            if isinstance(payload, dict):
                for key in ("results", "data", "products", "items"):
                    rows = payload.get(key)
                    if isinstance(rows, list):
                        return pd.DataFrame(rows)
    except Exception:
        return None
    return None


def _first_column(columns: Iterable[str], aliases: tuple[str, ...]) -> str | None:
    lookup = {_norm(column).replace(" ", ""): column for column in columns}
    for alias in aliases:
        found = lookup.get(_norm(alias).replace(" ", ""))
        if found:
            return found
    return None


def _discover_sources(contract: dict) -> list[SourceCandidate]:
    roots = []
    for configured in contract["source_discovery"]["roots"]:
        root = ROOT / configured
        if root.exists() and root not in roots:
            roots.append(root)

    seen: set[Path] = set()
    candidates: list[SourceCandidate] = []
    minimum_rows = int(contract["source_discovery"]["product_source_minimum_rows"])

    for source_root in roots:
        for path in source_root.rglob("*"):
            if path in seen or not path.is_file() or path.suffix.casefold() not in {".csv", ".json"}:
                continue
            seen.add(path)
            frame = _read_table(path)
            if frame is None or len(frame) < minimum_rows:
                continue

            product_id = _first_column(frame.columns, ("productId", "product_id", "tcgplayer_product_id", "id"))
            product_name = _first_column(frame.columns, ("name", "productName", "product_name", "box_name"))
            group_id = _first_column(frame.columns, ("groupId", "group_id", "tcgcsv_group_id", "set_id"))
            group_name = _first_column(frame.columns, ("groupName", "group_name", "set_name", "release_name"))
            if not product_id or not product_name or not group_id:
                continue

            filename = _norm(path.name)
            score = len(frame)
            if "product" in filename:
                score += 1_000_000
            if "tcgcsv" in _norm(path.as_posix()):
                score += 500_000
            if "snapshot" in filename:
                score += 100_000
            candidates.append(SourceCandidate(path, frame, product_id, product_name, group_id, group_name, score))

    return sorted(candidates, key=lambda item: (-item.score, item.path.as_posix()))


def _select_source(candidates: list[SourceCandidate]) -> SourceCandidate:
    if not candidates:
        raise RuntimeError("NO_GOVERNED_LOCAL_PRODUCT_SOURCE_FOUND")
    best = candidates[0]
    tied = [candidate for candidate in candidates if candidate.score == best.score]
    if len(tied) > 1:
        paths = ", ".join(candidate.path.as_posix() for candidate in tied)
        raise RuntimeError(f"UNRESOLVED_PRODUCT_SOURCE_TIE: {paths}")
    return best


FOREIGN_MARKERS = (
    " japanese ", " french ", " german ", " italian ", " spanish ", " portuguese ",
    " russian ", " korean ", " chinese ", " simplified chinese ", " traditional chinese ",
)


def classify_product(product_name: object, release_has_collector: bool) -> dict[str, object]:
    raw = str(product_name or "").strip()
    padded = f" {_norm(raw)} "

    is_collector = " collector booster" in padded
    is_draft = " draft booster" in padded
    is_play = " play booster" in padded
    is_booster_box = "booster box" in padded or "display box" in padded
    is_foreign = any(marker in padded for marker in FOREIGN_MARKERS)
    is_damaged = any(marker in padded for marker in (" damaged ", " opened ", " resealed ", " empty box "))

    if is_collector:
        status, reason, fmt = "EXCLUDED_SCOPE", "COLLECTOR_BOOSTER_PRODUCT", "COLLECTOR_BOOSTER"
    elif is_draft:
        status, reason, fmt = "EXCLUDED_SCOPE", "DRAFT_BOOSTER_PRODUCT", "DRAFT_BOOSTER"
    elif is_play:
        status, reason, fmt = "EXCLUDED_SCOPE", "PLAY_BOOSTER_PRODUCT", "PLAY_BOOSTER"
    elif is_foreign:
        status, reason, fmt = "EXCLUDED_SCOPE", "FOREIGN_LANGUAGE_PRODUCT", "OTHER_BOOSTER_BOX" if is_booster_box else "NON_BOX"
    elif is_damaged:
        status, reason, fmt = "EXCLUDED_SCOPE", "DAMAGED_OR_OPENED_PRODUCT", "OTHER_BOOSTER_BOX" if is_booster_box else "NON_BOX"
    elif not is_booster_box:
        status, reason, fmt = "EXCLUDED_SCOPE", "NOT_COMPLETE_BOOSTER_BOX", "NON_BOX"
    elif release_has_collector:
        status, reason, fmt = "EXCLUDED_SCOPE", "RELEASE_HAS_COLLECTOR_OPTION", "OTHER_BOOSTER_BOX"
    else:
        status, reason, fmt = "INCLUDED_CANDIDATE", "MEETS_INITIAL_SCOPE", "OTHER_BOOSTER_BOX"

    return {
        "language": "FOREIGN" if is_foreign else "ENGLISH",
        "booster_format": fmt,
        "full_booster_box_indicator": bool(is_booster_box),
        "factory_sealed_product_class_indicator": bool(is_booster_box and not is_damaged),
        "damaged_or_opened_indicator": bool(is_damaged),
        "collector_product_indicator": bool(is_collector),
        "draft_product_indicator": bool(is_draft),
        "play_product_indicator": bool(is_play),
        "collector_option_indicator": bool(release_has_collector),
        "initial_inclusion_status": status,
        "classification_reason": reason,
    }


def build_inventory(source: SourceCandidate) -> pd.DataFrame:
    frame = source.frame.copy()
    group_values = frame[source.group_id_col].astype(str)
    names = frame[source.product_name_col].fillna("").astype(str)

    collector_groups = set(group_values[names.str.casefold().str.contains("collector booster", regex=False)])
    rows: list[dict[str, object]] = []

    for index, row in frame.iterrows():
        product_name = row.get(source.product_name_col)
        group_id = str(row.get(source.group_id_col, "")).strip()
        classified = classify_product(product_name, group_id in collector_groups)
        product_id = str(row.get(source.product_id_col, "")).strip()
        group_name = str(row.get(source.group_name_col, "")).strip() if source.group_name_col else ""

        if not product_id or product_id.casefold() == "nan" or not str(product_name or "").strip() or not group_id or group_id.casefold() == "nan":
            classified["initial_inclusion_status"] = "UNRESOLVED_REVIEW"
            classified["classification_reason"] = "MISSING_IDENTITY_FIELD"

        rows.append({
            "canonical_product_id": f"tcgplayer:{product_id}" if product_id else "",
            "source_product_id": product_id,
            "product_name": str(product_name or "").strip(),
            "release_or_group_id": group_id,
            "release_or_group_name": group_name,
            "edition_or_printing": "UNRESOLVED",
            "product_family": "BOOSTER_BOX" if classified["full_booster_box_indicator"] else "NON_BOX",
            "source_reference": source.path.relative_to(ROOT).as_posix(),
            "source_row_number": int(index) + 2,
            **classified,
        })

    inventory = pd.DataFrame(rows)
    inventory = inventory.sort_values(["initial_inclusion_status", "release_or_group_name", "product_name", "canonical_product_id"], kind="stable")
    return inventory.reset_index(drop=True)


def _validate_inventory(inventory: pd.DataFrame) -> None:
    required = {
        "canonical_product_id", "product_name", "release_or_group_id", "booster_format", "language",
        "full_booster_box_indicator", "collector_option_indicator", "initial_inclusion_status",
        "classification_reason", "source_reference",
    }
    missing = sorted(required - set(inventory.columns))
    if missing:
        raise RuntimeError(f"MISSING_REQUIRED_INVENTORY_COLUMNS: {missing}")
    if inventory.empty:
        raise RuntimeError("EMPTY_CANDIDATE_UNIVERSE_INVENTORY")
    if inventory["canonical_product_id"].duplicated().any():
        duplicates = inventory.loc[inventory["canonical_product_id"].duplicated(False), "canonical_product_id"].head(20).tolist()
        raise RuntimeError(f"DUPLICATE_CANONICAL_PRODUCT_IDS: {duplicates}")
    if inventory["classification_reason"].fillna("").str.strip().eq("").any():
        raise RuntimeError("BLANK_CLASSIFICATION_REASON")

    included = inventory[inventory["initial_inclusion_status"] == "INCLUDED_CANDIDATE"]
    forbidden = included[
        included["collector_product_indicator"]
        | included["draft_product_indicator"]
        | included["play_product_indicator"]
        | included["collector_option_indicator"]
        | included["damaged_or_opened_indicator"]
        | included["language"].ne("ENGLISH")
        | ~included["full_booster_box_indicator"]
    ]
    if not forbidden.empty:
        raise RuntimeError("SCOPE_VIOLATION_IN_INCLUDED_CANDIDATES")


def main() -> int:
    contract = _load_json(CONTRACT_PATH)
    scope = _load_json(SCOPE_PATH)
    if contract["scope_authority"] != SCOPE_PATH.relative_to(ROOT).as_posix():
        raise RuntimeError("CONTRACT_SCOPE_AUTHORITY_DRIFT")
    if scope["governance_controls"]["next_required_stage"] != "Build and certify the candidate product-universe inventory against this scope decision.":
        raise RuntimeError("OWNER_SCOPE_NEXT_STAGE_DRIFT")

    candidates = _discover_sources(contract)
    selected = _select_source(candidates)
    inventory = build_inventory(selected)
    _validate_inventory(inventory)

    output_dir = ROOT / contract["outputs"]["directory"]
    output_dir.mkdir(parents=True, exist_ok=True)

    files = contract["outputs"]
    inventory.to_csv(output_dir / files["inventory_csv"], index=False)
    inventory[inventory["initial_inclusion_status"] == "INCLUDED_CANDIDATE"].to_csv(output_dir / files["included_csv"], index=False)
    inventory[inventory["initial_inclusion_status"] == "EXCLUDED_SCOPE"].to_csv(output_dir / files["excluded_csv"], index=False)
    inventory[inventory["initial_inclusion_status"] == "UNRESOLVED_REVIEW"].to_csv(output_dir / files["review_csv"], index=False)

    counts = inventory["initial_inclusion_status"].value_counts().to_dict()
    reasons = inventory["classification_reason"].value_counts().to_dict()
    summary = {
        "certification_status": "PASS_PRECOLLECTOR_CANDIDATE_UNIVERSE_BUILD",
        "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"],
        "source_path": selected.path.relative_to(ROOT).as_posix(),
        "source_sha256": _sha256(selected.path),
        "source_rows": int(len(selected.frame)),
        "inventory_rows": int(len(inventory)),
        "status_counts": {str(key): int(value) for key, value in counts.items()},
        "reason_counts": {str(key): int(value) for key, value in reasons.items()},
        "forecast_generation_authorized": False,
        "ranking_execution_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_purchase_execution_authorized": False,
        "next_stage": contract["next_stage_if_certified"],
    }
    (output_dir / files["summary_json"]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "selected_source": {
            "path": selected.path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(selected.path),
            "rows": int(len(selected.frame)),
            "columns": [str(column) for column in selected.frame.columns],
        },
        "discovered_candidates": [
            {
                "path": candidate.path.relative_to(ROOT).as_posix(),
                "rows": int(len(candidate.frame)),
                "score": int(candidate.score),
                "sha256": _sha256(candidate.path),
            }
            for candidate in candidates[:25]
        ],
    }
    (output_dir / files["source_manifest_json"]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PASS_PRECOLLECTOR_CANDIDATE_UNIVERSE_BUILD")
    print(f"SOURCE={summary['source_path']}")
    print(f"SOURCE_ROWS={summary['source_rows']}")
    print(f"INVENTORY_ROWS={summary['inventory_rows']}")
    print(f"INCLUDED_CANDIDATES={counts.get('INCLUDED_CANDIDATE', 0)}")
    print(f"EXCLUDED_SCOPE={counts.get('EXCLUDED_SCOPE', 0)}")
    print(f"UNRESOLVED_REVIEW={counts.get('UNRESOLVED_REVIEW', 0)}")
    print("NEXT_STAGE=OWNER_REVIEW_AND_SOURCE_HIERARCHY_DECISION")
    print("FORECAST_AUTHORIZED=FALSE")
    print("RANKING_AUTHORIZED=FALSE")
    print("PURCHASE_RECOMMENDATION_AUTHORIZED=FALSE")
    print("AUTOMATIC_EXECUTION_AUTHORIZED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
