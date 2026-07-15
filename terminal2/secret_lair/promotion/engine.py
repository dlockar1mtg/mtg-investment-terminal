from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import shutil

import pandas as pd

from terminal2.config import ROOT_DIR
from terminal2.secret_lair.master_database.config import (
    MASTER_HISTORY_PATH,
    MASTER_PRODUCTS_PATH,
    MASTER_ROOT,
)
from terminal2.secret_lair.pricing import PRICE_COLUMNS, PRICE_PATH
from terminal2.secret_lair.registry import REGISTRY_COLUMNS, REGISTRY_PATH
from terminal2.secret_lair.metadata import VALID_FINISHES
from terminal2.secret_lair.datetime_utils import date_string_series


PROMOTION_ROOT = (
    Path(ROOT_DIR) / "data" / "terminal2"
    / "secret_lair_promotion"
)
PROMOTION_LOG_PATH = PROMOTION_ROOT / "promotion_log.csv"
BACKUP_ROOT = PROMOTION_ROOT / "backups"


@dataclass(frozen=True)
class PromotionPlan:
    datasets: dict[str, pd.DataFrame]
    registry_frame: pd.DataFrame
    price_frame: pd.DataFrame
    apply_ready: bool


@dataclass(frozen=True)
class PromotionResult:
    promotion_run_id: str
    applied: bool
    registry_rows: int
    price_rows: int
    registry_backup: str
    price_backup: str
    status: str


def _empty(columns) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _read(path: Path, columns=()) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return _empty(columns)
    frame = pd.read_csv(path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame


def _review_path() -> Path:
    return (
        Path(ROOT_DIR) / "data" / "warehouse"
        / "current" / "secret_lair"
        / "master_secret_lair_review_queue.csv"
    )


def _current_master_prices_path() -> Path:
    return (
        Path(ROOT_DIR) / "data" / "warehouse"
        / "current" / "secret_lair"
        / "master_secret_lair_prices_current.csv"
    )


def _run_id(mode: str, minimum_confidence: int) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha1(
        f"{timestamp}|{mode}|{minimum_confidence}".encode("utf-8")
    ).hexdigest()[:12].upper()
    return f"SLP-{digest}"


def _candidate_and_rejection_frames(
    products: pd.DataFrame,
    review: pd.DataFrame,
    *,
    minimum_confidence: int,
    exclude_review: bool,
    allow_unknown_finish: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidate_columns = list(REGISTRY_COLUMNS) + [
        "product_name",
        "source_confidence",
        "promotion_eligibility",
        "promotion_reason",
    ]
    rejection_columns = [
        "secret_lair_id",
        "product_name",
        "rejection_code",
        "rejection_reason",
        "source_confidence",
    ]

    if products.empty:
        return (
            _empty(candidate_columns),
            _empty(rejection_columns),
            review.copy(),
        )

    frame = products.copy()
    for column in REGISTRY_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    if "product_name" not in frame.columns:
        frame["product_name"] = frame["drop_name"].fillna("")
    confidence = pd.to_numeric(
        frame.get("source_confidence"),
        errors="coerce",
    ).fillna(0)
    frame["source_confidence"] = confidence

    review_ids = set()
    if exclude_review and not review.empty and "source_record_id" in review.columns:
        # Review queues do not always carry canonical IDs. Match by product name as well.
        pass
    review_names = set(
        review.get("product_name", pd.Series(dtype=str))
        .dropna().astype(str).str.strip().str.lower()
    ) if exclude_review and not review.empty else set()

    duplicate_ids = set(
        frame.loc[
            frame["secret_lair_id"].astype(str).duplicated(keep=False),
            "secret_lair_id",
        ].astype(str)
    )
    duplicate_identity = frame.duplicated(
        ["drop_name","variant_name","finish"],
        keep=False,
    )

    rejection_rows = []
    eligible_mask = pd.Series(True, index=frame.index)

    for idx, row in frame.iterrows():
        reasons = []
        codes = []
        asset_id = str(row.get("secret_lair_id") or "")
        product_name = str(row.get("product_name") or row.get("drop_name") or "")
        finish = str(row.get("finish") or "").strip().lower()

        if not asset_id:
            codes.append("missing_id"); reasons.append("Secret Lair ID is missing.")
        if confidence.loc[idx] < minimum_confidence:
            codes.append("low_confidence"); reasons.append(
                f"Source confidence is below {minimum_confidence}."
            )
        if finish == "unknown" and not allow_unknown_finish:
            codes.append("unknown_finish")
            reasons.append(
                "Finish is unresolved and requires explicit override."
            )
        elif finish not in VALID_FINISHES:
            codes.append("invalid_finish")
            reasons.append(
                f"Finish '{finish}' is not production-valid."
            )
        if asset_id in duplicate_ids:
            codes.append("duplicate_id"); reasons.append(
                "Secret Lair ID occurs more than once in the master catalog."
            )
        if bool(duplicate_identity.loc[idx]):
            codes.append("duplicate_identity"); reasons.append(
                "Drop, variant, and finish identity occurs more than once."
            )
        if exclude_review and product_name.strip().lower() in review_names:
            codes.append("review_queue"); reasons.append(
                "Product remains in the master database review queue."
            )
        required_missing = [
            field for field in ("drop_name","variant_name","finish")
            if pd.isna(row.get(field)) or not str(row.get(field)).strip()
        ]
        if required_missing:
            codes.append("missing_identity"); reasons.append(
                "Missing required identity fields: " + ", ".join(required_missing)
            )

        if codes:
            eligible_mask.loc[idx] = False
            for code, reason in zip(codes, reasons):
                rejection_rows.append({
                    "secret_lair_id": asset_id or "UNASSIGNED",
                    "product_name": product_name,
                    "rejection_code": code,
                    "rejection_reason": reason,
                    "source_confidence": confidence.loc[idx],
                })

    eligible = frame.loc[eligible_mask].copy()
    eligible["promotion_eligibility"] = "eligible"
    eligible["promotion_reason"] = (
        "Passed confidence, identity, finish, duplicate, and review safeguards."
    )
    for column in candidate_columns:
        if column not in eligible.columns:
            eligible[column] = pd.NA
    eligible = eligible[candidate_columns].drop_duplicates("secret_lair_id")

    rejections = pd.DataFrame(rejection_rows, columns=rejection_columns)
    return eligible, rejections, review.copy()


def _price_candidates(
    eligible_registry: pd.DataFrame,
    history: pd.DataFrame,
    current: pd.DataFrame,
) -> pd.DataFrame:
    columns = list(PRICE_COLUMNS) + [
        "price_eligibility",
        "price_reason",
    ]
    valid_ids = set(
        eligible_registry["secret_lair_id"].astype(str)
        if not eligible_registry.empty else []
    )
    frames = []
    for frame in (history, current):
        if frame is not None and not frame.empty:
            frames.append(frame.copy())
    if not frames:
        return _empty(columns)

    prices = pd.concat(frames, ignore_index=True, sort=False)
    rename = {}
    prices = prices.rename(columns=rename)
    for column in PRICE_COLUMNS:
        if column not in prices.columns:
            prices[column] = pd.NA

    prices["observation_date"] = date_string_series(
        prices["observation_date"]
    )
    prices["market_price"] = pd.to_numeric(
        prices["market_price"], errors="coerce"
    )
    prices["low_price"] = pd.to_numeric(
        prices["low_price"], errors="coerce"
    )
    prices["source_name"] = prices["source_name"].fillna("tcgcsv").astype(str)
    prices["currency"] = prices["currency"].fillna("USD")
    prices["price_data_quality"] = pd.to_numeric(
        prices["price_data_quality"], errors="coerce"
    ).fillna(85)
    prices["notes"] = prices["notes"].fillna(
        "Promoted from Master Secret Lair Database"
    )
    prices["price_eligibility"] = "eligible"
    prices["price_reason"] = "Valid product reference, date, source, and positive market price."

    mask = (
        prices["secret_lair_id"].astype(str).isin(valid_ids)
        & prices["observation_date"].notna()
        & prices["source_name"].astype(str).str.strip().ne("")
        & prices["market_price"].gt(0)
    )
    prices = prices.loc[mask].copy()
    prices = prices.sort_values(
        ["observation_date","secret_lair_id","source_name","price_data_quality"]
    ).drop_duplicates(
        ["observation_date","secret_lair_id","source_name"],
        keep="last",
    )
    return prices[columns]


def _production_health(
    registry: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    snapshot = datetime.now(timezone.utc).date().isoformat()
    registry_ids = registry.get(
        "secret_lair_id", pd.Series(dtype=str)
    ).astype(str)
    price_ids = prices.get(
        "secret_lair_id", pd.Series(dtype=str)
    ).astype(str)
    finish = registry.get(
        "finish", pd.Series(dtype=str)
    ).fillna("").astype(str).str.lower()
    invalid = int((~finish.isin(VALID_FINISHES)).sum()) if not registry.empty else 0
    duplicates = int(registry_ids.duplicated().sum()) if not registry.empty else 0
    priced = len(set(price_ids) & set(registry_ids))
    orphan = int((~price_ids.isin(set(registry_ids))).sum()) if not prices.empty else 0
    coverage = priced / len(registry) if len(registry) else 0.0
    status = "PASS" if duplicates == 0 and invalid == 0 and orphan == 0 else "FAIL"
    return pd.DataFrame([{
        "snapshot_date": snapshot,
        "registry_product_count": len(registry),
        "unique_registry_id_count": registry_ids.nunique(),
        "duplicate_registry_id_count": duplicates,
        "valid_finish_count": len(registry) - invalid,
        "invalid_finish_count": invalid,
        "priced_product_count": priced,
        "orphan_price_count": orphan,
        "current_price_coverage": round(coverage, 4),
        "integrity_status": status,
    }])


def _load_log() -> pd.DataFrame:
    columns = [
        "promotion_run_id","promotion_timestamp_utc","mode",
        "minimum_confidence","candidate_count",
        "promoted_registry_rows","promoted_price_rows",
        "rejected_count","review_remaining_count","status",
    ]
    return _read(PROMOTION_LOG_PATH, columns)


def _append_log(row: dict) -> pd.DataFrame:
    log = _load_log()
    new = pd.DataFrame([row])
    combined = pd.concat(
        [frame for frame in (log, new) if not frame.empty],
        ignore_index=True,
    )
    PROMOTION_ROOT.mkdir(parents=True, exist_ok=True)
    combined.to_csv(PROMOTION_LOG_PATH, index=False)
    return combined


def build_secret_lair_promotion_plan(
    *,
    minimum_confidence: int = 75,
    exclude_review: bool = True,
    allow_unknown_finish: bool = False,
) -> PromotionPlan:
    products = _read(MASTER_PRODUCTS_PATH)
    review = _read(_review_path())
    history = _read(MASTER_HISTORY_PATH)
    current = _read(_current_master_prices_path())

    candidates, rejections, remaining_review = (
        _candidate_and_rejection_frames(
            products,
            review,
            minimum_confidence=minimum_confidence,
            exclude_review=exclude_review,
            allow_unknown_finish=allow_unknown_finish,
        )
    )
    price_candidates = _price_candidates(
        candidates,
        history,
        current,
    )
    production_registry = _read(REGISTRY_PATH, REGISTRY_COLUMNS)
    production_prices = _read(PRICE_PATH, PRICE_COLUMNS)
    health = _production_health(
        production_registry,
        production_prices,
    )

    last_log = _load_log()
    last_status = (
        str(last_log.iloc[-1]["status"])
        if not last_log.empty else "Never Applied"
    )
    summary = pd.DataFrame([{
        "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "master_product_count": len(products),
        "eligible_product_count": len(candidates),
        "rejected_product_count": (
            rejections["secret_lair_id"].nunique()
            if not rejections.empty else 0
        ),
        "review_remaining_count": len(remaining_review),
        "eligible_price_count": len(price_candidates),
        "production_registry_count": len(production_registry),
        "production_price_count": len(production_prices),
        "apply_ready": bool(
            len(candidates) > 0
            and len(price_candidates) > 0
            and candidates["secret_lair_id"].is_unique
        ),
        "last_apply_status": last_status,
    }])

    candidate_output = candidates[
        [
            "secret_lair_id","drop_name","variant_name","finish",
            "source_confidence","promotion_eligibility","promotion_reason",
        ]
    ].copy()

    return PromotionPlan(
        datasets={
            "secret_lair_promotion_candidates": candidate_output,
            "secret_lair_promotion_rejections": rejections,
            "secret_lair_promotion_prices": price_candidates[
                [
                    "observation_date","secret_lair_id","source_name",
                    "market_price","price_eligibility","price_reason",
                ]
            ].copy(),
            "secret_lair_promotion_review_remaining": remaining_review,
            "secret_lair_promotion_log": _load_log(),
            "secret_lair_promotion_summary": summary,
            "secret_lair_registry_health": health,
        },
        registry_frame=candidates[list(REGISTRY_COLUMNS)].copy(),
        price_frame=price_candidates[list(PRICE_COLUMNS)].copy(),
        apply_ready=bool(summary.iloc[0]["apply_ready"]),
    )


def _backup(path: Path, run_id: str) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    destination = BACKUP_ROOT / f"{path.stem}_{run_id}{path.suffix}"
    shutil.copy2(path, destination)
    return str(destination)


def apply_secret_lair_promotion(
    *,
    minimum_confidence: int = 75,
    exclude_review: bool = True,
    allow_unknown_finish: bool = False,
    replace: bool = False,
) -> PromotionResult:
    plan = build_secret_lair_promotion_plan(
        minimum_confidence=minimum_confidence,
        exclude_review=exclude_review,
        allow_unknown_finish=allow_unknown_finish,
    )
    run_id = _run_id("apply", minimum_confidence)
    timestamp = datetime.now(timezone.utc).isoformat()

    if not plan.apply_ready:
        _append_log({
            "promotion_run_id": run_id,
            "promotion_timestamp_utc": timestamp,
            "mode": "apply",
            "minimum_confidence": minimum_confidence,
            "candidate_count": len(plan.registry_frame),
            "promoted_registry_rows": 0,
            "promoted_price_rows": 0,
            "rejected_count": len(plan.datasets["secret_lair_promotion_rejections"]),
            "review_remaining_count": len(plan.datasets["secret_lair_promotion_review_remaining"]),
            "status": "BLOCKED_NOT_READY",
        })
        return PromotionResult(
            run_id, False, 0, 0, "", "",
            "BLOCKED_NOT_READY",
        )

    registry_backup = _backup(REGISTRY_PATH, run_id)
    price_backup = _backup(PRICE_PATH, run_id)

    existing_registry = _read(REGISTRY_PATH, REGISTRY_COLUMNS)
    existing_prices = _read(PRICE_PATH, PRICE_COLUMNS)

    if replace:
        registry = plan.registry_frame.copy()
        prices = plan.price_frame.copy()
    else:
        registry = pd.concat(
            [frame for frame in (existing_registry, plan.registry_frame)
             if not frame.empty],
            ignore_index=True,
        ) if (not existing_registry.empty or not plan.registry_frame.empty) else _empty(REGISTRY_COLUMNS)
        registry = registry.drop_duplicates(
            "secret_lair_id", keep="last"
        )

        prices = pd.concat(
            [frame for frame in (existing_prices, plan.price_frame)
             if not frame.empty],
            ignore_index=True,
        ) if (not existing_prices.empty or not plan.price_frame.empty) else _empty(PRICE_COLUMNS)
        prices = prices.sort_values(
            ["observation_date","secret_lair_id","source_name","price_data_quality"]
        ).drop_duplicates(
            ["observation_date","secret_lair_id","source_name"],
            keep="last",
        )

    valid_ids = set(registry["secret_lair_id"].astype(str))
    prices = prices[
        prices["secret_lair_id"].astype(str).isin(valid_ids)
    ].copy()
    health = _production_health(registry, prices)
    if str(health.iloc[0]["integrity_status"]) != "PASS":
        raise ValueError(
            "Promotion integrity checks failed; production files were not written."
        )

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    registry[list(REGISTRY_COLUMNS)].to_csv(REGISTRY_PATH, index=False)
    prices[list(PRICE_COLUMNS)].to_csv(PRICE_PATH, index=False)

    _append_log({
        "promotion_run_id": run_id,
        "promotion_timestamp_utc": timestamp,
        "mode": "replace" if replace else "merge",
        "minimum_confidence": minimum_confidence,
        "candidate_count": len(plan.registry_frame),
        "promoted_registry_rows": len(registry),
        "promoted_price_rows": len(prices),
        "rejected_count": len(plan.datasets["secret_lair_promotion_rejections"]),
        "review_remaining_count": len(plan.datasets["secret_lair_promotion_review_remaining"]),
        "status": "APPLIED",
    })
    return PromotionResult(
        run_id,
        True,
        len(registry),
        len(prices),
        registry_backup,
        price_backup,
        "APPLIED",
    )
