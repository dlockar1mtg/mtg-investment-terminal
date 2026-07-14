from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from terminal2.secret_lair.pricing import (
    PRICE_COLUMNS,
    PRICE_PATH,
    load_price_observations,
)
from terminal2.secret_lair.registry import (
    REGISTRY_COLUMNS,
    REGISTRY_PATH,
    load_secret_lair_registry,
)

from .matching import match_source_catalog
from .sources import (
    APPLY_LOG_PATH,
    MATCH_OVERRIDES_PATH,
    SOURCE_CATALOG_PATH,
    SOURCE_PRICES_PATH,
    load_match_overrides,
    load_source_catalog,
    load_source_prices,
)


@dataclass(frozen=True)
class BackfillBuildResult:
    datasets: dict[str, pd.DataFrame]
    catalog_exists: bool
    prices_exist: bool
    overrides_exist: bool


@dataclass(frozen=True)
class BackfillRunResult:
    registry_rows_written: int
    price_rows_written: int
    apply_log_path: str


def _proposed_registry(
    registry: pd.DataFrame,
    catalog: pd.DataFrame,
    matches: pd.DataFrame,
) -> pd.DataFrame:
    if matches.empty:
        return registry.copy()

    accepted = matches[
        matches["match_status"].isin(
            ["matched", "new_asset"]
        )
    ].copy()
    new_rows = accepted[
        accepted["match_status"].eq("new_asset")
    ].copy()

    proposed_rows = []
    for _, row in new_rows.iterrows():
        proposed = {
            column: row.get(column, "")
            for column in REGISTRY_COLUMNS
        }
        proposed["secret_lair_id"] = row["secret_lair_id"]
        proposed_rows.append(proposed)

    additions = pd.DataFrame(
        proposed_rows,
        columns=REGISTRY_COLUMNS,
    )
    combined = pd.concat(
        [registry, additions],
        ignore_index=True,
    )
    if combined.empty:
        return pd.DataFrame(columns=REGISTRY_COLUMNS)
    return (
        combined.drop_duplicates(
            "secret_lair_id",
            keep="first",
        )
        .sort_values("secret_lair_id")
        .reset_index(drop=True)
    )


def _proposed_prices(
    existing_prices: pd.DataFrame,
    source_prices: pd.DataFrame,
    matches: pd.DataFrame,
) -> pd.DataFrame:
    if source_prices.empty or matches.empty:
        return existing_prices.copy()

    mapping = matches[
        matches["match_status"].isin(
            ["matched", "new_asset"]
        )
    ][
        [
            "source_name",
            "source_record_id",
            "secret_lair_id",
        ]
    ].copy()

    prices = source_prices.merge(
        mapping,
        on=["source_name", "source_record_id"],
        how="left",
        validate="many_to_one",
    )
    prices = prices.dropna(subset=["secret_lair_id"])
    prices = prices[
        prices["secret_lair_id"].astype(str).ne("")
    ].copy()

    normalized = pd.DataFrame({
        "observation_date": prices["observation_date"],
        "secret_lair_id": prices["secret_lair_id"],
        "source_name": prices["source_name"],
        "market_price": prices["market_price"],
        "low_price": prices["low_price"],
        "listing_count": prices["listing_count"],
        "sales_count_30d": prices["sales_count_30d"],
        "currency": prices["currency"],
        "source_url": prices["source_url"],
        "source_record_id": prices["source_record_id"],
        "price_data_quality": prices["price_data_quality"],
        "notes": prices["notes"],
    })
    for column in PRICE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized = normalized[list(PRICE_COLUMNS)]

    combined = pd.concat(
        [existing_prices, normalized],
        ignore_index=True,
    )
    if combined.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    key = [
        "observation_date",
        "secret_lair_id",
        "source_name",
    ]
    return (
        combined.sort_values(
            key + ["price_data_quality"]
        )
        .drop_duplicates(key, keep="last")
        .sort_values(key)
        .reset_index(drop=True)
    )


def _coverage(
    catalog: pd.DataFrame,
    matches: pd.DataFrame,
    source_prices: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "source_name",
        "catalog_rows",
        "auto_matched_rows",
        "new_asset_rows",
        "review_rows",
        "rejected_rows",
        "priced_rows",
        "priced_source_records",
        "catalog_match_rate",
    ]
    sources = sorted(
        set(catalog["source_name"].tolist())
        | set(source_prices["source_name"].tolist())
    )
    rows = []
    for source in sources:
        source_catalog = catalog[
            catalog["source_name"].eq(source)
        ]
        source_matches = matches[
            matches["source_name"].eq(source)
        ]
        source_price = source_prices[
            source_prices["source_name"].eq(source)
        ]
        catalog_rows = len(source_catalog)
        matched = int(
            source_matches["match_status"].eq("matched").sum()
        )
        new_assets = int(
            source_matches["match_status"].eq("new_asset").sum()
        )
        rows.append({
            "source_name": source,
            "catalog_rows": catalog_rows,
            "auto_matched_rows": matched,
            "new_asset_rows": new_assets,
            "review_rows": int(
                source_matches["match_status"].eq("review").sum()
            ),
            "rejected_rows": int(
                source_matches["match_status"].eq("rejected").sum()
            ),
            "priced_rows": len(source_price),
            "priced_source_records": int(
                source_price["source_record_id"].nunique()
            ),
            "catalog_match_rate": (
                (matched + new_assets) / catalog_rows
                if catalog_rows else 0.0
            ),
        })
    return pd.DataFrame(rows, columns=columns)


def _summary(
    catalog: pd.DataFrame,
    matches: pd.DataFrame,
    source_prices: pd.DataFrame,
    proposed_registry: pd.DataFrame,
    proposed_prices: pd.DataFrame,
) -> pd.DataFrame:
    matched = int(
        matches["match_status"].eq("matched").sum()
    ) if not matches.empty else 0
    new_assets = int(
        matches["match_status"].eq("new_asset").sum()
    ) if not matches.empty else 0
    review = int(
        matches["match_status"].eq("review").sum()
    ) if not matches.empty else 0
    rejected = int(
        matches["match_status"].eq("rejected").sum()
    ) if not matches.empty else 0
    return pd.DataFrame([{
        "snapshot_date": datetime.now(
            timezone.utc
        ).date().isoformat(),
        "catalog_rows": int(len(catalog)),
        "matched_rows": matched,
        "new_asset_rows": new_assets,
        "review_rows": review,
        "rejected_rows": rejected,
        "price_rows": int(len(source_prices)),
        "proposed_registry_rows": int(
            len(proposed_registry)
        ),
        "proposed_price_rows": int(
            len(proposed_prices)
        ),
        "apply_ready": bool(
            len(catalog) > 0
            and review == 0
            and rejected == 0
        ),
    }])


def build_secret_lair_backfill(
    *,
    registry_path: Path = REGISTRY_PATH,
    price_path: Path = PRICE_PATH,
    source_catalog_path: Path = SOURCE_CATALOG_PATH,
    source_prices_path: Path = SOURCE_PRICES_PATH,
    overrides_path: Path = MATCH_OVERRIDES_PATH,
) -> BackfillBuildResult:
    registry, _ = load_secret_lair_registry(
        registry_path
    )
    existing_prices, _ = load_price_observations(
        price_path
    )
    catalog, catalog_exists = load_source_catalog(
        source_catalog_path
    )
    source_prices, prices_exist = load_source_prices(
        source_prices_path
    )
    overrides, overrides_exist = load_match_overrides(
        overrides_path
    )

    matches, review = match_source_catalog(
        catalog,
        registry,
        overrides,
    )
    proposed_registry = _proposed_registry(
        registry,
        catalog,
        matches,
    )
    proposed_prices = _proposed_prices(
        existing_prices,
        source_prices,
        matches,
    )
    coverage = _coverage(
        catalog,
        matches,
        source_prices,
    )
    summary = _summary(
        catalog,
        matches,
        source_prices,
        proposed_registry,
        proposed_prices,
    )

    return BackfillBuildResult(
        datasets={
            "secret_lair_source_catalog": catalog,
            "secret_lair_match_results": matches,
            "secret_lair_unmatched_review": review,
            "secret_lair_backfill_registry": proposed_registry,
            "secret_lair_backfill_prices": proposed_prices,
            "secret_lair_backfill_coverage": coverage,
            "secret_lair_backfill_summary": summary,
        },
        catalog_exists=catalog_exists,
        prices_exist=prices_exist,
        overrides_exist=overrides_exist,
    )


def apply_secret_lair_backfill(
    result: BackfillBuildResult,
    *,
    registry_path: Path = REGISTRY_PATH,
    price_path: Path = PRICE_PATH,
    apply_log_path: Path = APPLY_LOG_PATH,
) -> BackfillRunResult:
    summary = result.datasets[
        "secret_lair_backfill_summary"
    ].iloc[0]
    if not bool(summary["apply_ready"]):
        raise ValueError(
            "Backfill is not apply-ready. Resolve all review "
            "and rejected rows before applying."
        )

    registry = result.datasets[
        "secret_lair_backfill_registry"
    ]
    prices = result.datasets[
        "secret_lair_backfill_prices"
    ]

    registry_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    price_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    registry.to_csv(registry_path, index=False)
    prices.to_csv(price_path, index=False)

    log_row = pd.DataFrame([{
        "applied_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "registry_rows_written": len(registry),
        "price_rows_written": len(prices),
        "catalog_rows": int(summary["catalog_rows"]),
        "matched_rows": int(summary["matched_rows"]),
        "new_asset_rows": int(summary["new_asset_rows"]),
    }])
    if apply_log_path.exists():
        previous = pd.read_csv(apply_log_path)
        log_row = pd.concat(
            [previous, log_row],
            ignore_index=True,
        )
    apply_log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    log_row.to_csv(apply_log_path, index=False)

    return BackfillRunResult(
        registry_rows_written=len(registry),
        price_rows_written=len(prices),
        apply_log_path=str(apply_log_path),
    )
