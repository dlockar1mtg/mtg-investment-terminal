from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from terminal2.config import ROOT_DIR

from .identifiers import normalize_text, stable_key
from .metadata import (
    VALID_AVAILABILITY_MODELS,
    VALID_EVENT_TYPES,
    VALID_FINISHES,
    VALID_PRODUCT_FAMILIES,
    VALID_STATUSES,
)


REGISTRY_PATH = (
    Path(ROOT_DIR) / "data" / "terminal2"
    / "secret_lair_registry.csv"
)
TEMPLATE_PATH = (
    Path(ROOT_DIR) / "data" / "templates"
    / "secret_lair_registry_template.csv"
)

REGISTRY_COLUMNS = (
    "secret_lair_id",
    "drop_name",
    "variant_name",
    "finish",
    "product_family",
    "release_date",
    "sale_start_date",
    "sale_end_date",
    "msrp_usd",
    "currency",
    "franchise",
    "ip_category",
    "universes_beyond",
    "artist_names",
    "card_count",
    "superdrop_name",
    "event_type",
    "availability_model",
    "status",
    "official_url",
    "source_name",
    "source_record_id",
    "notes",
)


@dataclass(frozen=True)
class RegistryBuildResult:
    datasets: dict[str, pd.DataFrame]
    registry_path: str
    registry_exists: bool


def create_registry_template(
    destination: Path = REGISTRY_PATH,
    *,
    overwrite: bool = False,
) -> Path:
    destination = Path(destination)
    if destination.exists() and not overwrite:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = pd.read_csv(TEMPLATE_PATH, dtype=str)
    template.to_csv(destination, index=False)
    return destination


def load_secret_lair_registry(
    path: Path = REGISTRY_PATH,
) -> tuple[pd.DataFrame, bool]:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=REGISTRY_COLUMNS), False

    frame = pd.read_csv(path)
    for column in REGISTRY_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[list(REGISTRY_COLUMNS)].copy()
    return frame, True


def _quality_findings(registry: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "validation_id",
        "secret_lair_id",
        "severity",
        "rule_name",
        "message",
    ]
    rows = []

    def add(asset_id, severity, rule, message):
        rows.append({
            "validation_id": stable_key(
                "SLV",
                f"{asset_id}|{rule}|{message}",
            ),
            "secret_lair_id": asset_id or "UNASSIGNED",
            "severity": severity,
            "rule_name": rule,
            "message": message,
        })

    if registry.empty:
        add(
            "UNASSIGNED",
            "Warning",
            "empty_registry",
            "No Secret Lair assets have been imported.",
        )
        return pd.DataFrame(rows, columns=columns)

    duplicate_ids = registry[
        registry["secret_lair_id"].duplicated(keep=False)
    ]
    for asset_id in sorted(
        duplicate_ids["secret_lair_id"].astype(str).unique()
    ):
        add(
            asset_id,
            "Error",
            "duplicate_secret_lair_id",
            "Secret Lair ID appears more than once.",
        )

    for _, row in registry.iterrows():
        asset_id = str(row.get("secret_lair_id") or "UNASSIGNED")
        for field in (
            "drop_name",
            "variant_name",
            "finish",
            "franchise",
        ):
            if normalize_text(row.get(field)) == "":
                add(
                    asset_id,
                    "Error",
                    f"missing_{field}",
                    f"Required field '{field}' is missing.",
                )

        release = pd.to_datetime(
            row.get("release_date"),
            errors="coerce",
        )
        if pd.isna(release):
            add(
                asset_id,
                "Warning",
                "missing_release_date",
                "Release date is missing or invalid.",
            )

        msrp = pd.to_numeric(
            pd.Series([row.get("msrp_usd")]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(msrp) or msrp <= 0:
            add(
                asset_id,
                "Warning",
                "missing_msrp",
                "MSRP is missing or nonpositive.",
            )

        finish = normalize_text(row.get("finish")).lower()
        if finish not in VALID_FINISHES:
            add(
                asset_id,
                "Error",
                "invalid_finish",
                f"Unsupported finish '{finish}'.",
            )

        family = normalize_text(
            row.get("product_family")
        ).lower()
        if family and family not in VALID_PRODUCT_FAMILIES:
            add(
                asset_id,
                "Warning",
                "invalid_product_family",
                f"Unrecognized product family '{family}'.",
            )

        availability = normalize_text(
            row.get("availability_model")
        ).lower()
        if (
            availability
            and availability not in VALID_AVAILABILITY_MODELS
        ):
            add(
                asset_id,
                "Warning",
                "invalid_availability_model",
                f"Unrecognized availability model '{availability}'.",
            )

        status = normalize_text(row.get("status")).lower()
        if status and status not in VALID_STATUSES:
            add(
                asset_id,
                "Warning",
                "invalid_status",
                f"Unrecognized status '{status}'.",
            )

        event = normalize_text(row.get("event_type")).lower()
        if event and event not in VALID_EVENT_TYPES:
            add(
                asset_id,
                "Warning",
                "invalid_event_type",
                f"Unrecognized event type '{event}'.",
            )

        if normalize_text(row.get("artist_names")) == "":
            add(
                asset_id,
                "Warning",
                "missing_artist",
                "Artist metadata has not been entered.",
            )

    return pd.DataFrame(rows, columns=columns)


def _release_calendar(registry: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "secret_lair_id",
        "drop_name",
        "release_date",
        "release_year",
        "release_quarter",
        "release_month",
        "release_month_name",
        "sale_start_date",
        "sale_end_date",
        "sale_window_days",
        "superdrop_name",
        "event_type",
        "status",
    ]
    if registry.empty:
        return pd.DataFrame(columns=columns)

    frame = registry.copy()
    release = pd.to_datetime(
        frame["release_date"],
        errors="coerce",
    )
    start = pd.to_datetime(
        frame["sale_start_date"],
        errors="coerce",
    )
    end = pd.to_datetime(
        frame["sale_end_date"],
        errors="coerce",
    )
    frame["release_year"] = release.dt.year.astype("Int64")
    frame["release_quarter"] = (
        "Q" + release.dt.quarter.astype("Int64").astype("string")
    )
    frame["release_month"] = release.dt.month.astype("Int64")
    frame["release_month_name"] = release.dt.month_name()
    frame["sale_window_days"] = (end - start).dt.days.astype("Int64")
    return frame[columns]


def _ip_catalog(registry: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "ip_key",
        "franchise",
        "ip_category",
        "universes_beyond",
        "asset_count",
        "drop_count",
    ]
    if registry.empty:
        return pd.DataFrame(columns=columns)

    frame = registry.copy()
    frame["franchise"] = frame["franchise"].fillna(
        "Unknown"
    )
    grouped = (
        frame.groupby(
            [
                "franchise",
                "ip_category",
                "universes_beyond",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            asset_count=("secret_lair_id", "nunique"),
            drop_count=("drop_name", "nunique"),
        )
    )
    grouped["ip_key"] = grouped.apply(
        lambda row: stable_key(
            "IP",
            f"{row['franchise']}|{row['ip_category']}|"
            f"{row['universes_beyond']}",
        ),
        axis=1,
    )
    return grouped[columns]


def _artist_catalog(registry: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "artist_key",
        "artist_name",
        "secret_lair_id",
        "drop_name",
        "variant_name",
    ]
    rows = []
    for _, row in registry.iterrows():
        artists = [
            normalize_text(value)
            for value in str(
                row.get("artist_names") or ""
            ).split("|")
            if normalize_text(value)
        ]
        for artist in sorted(set(artists)):
            rows.append({
                "artist_key": stable_key("ART", artist),
                "artist_name": artist,
                "secret_lair_id": row["secret_lair_id"],
                "drop_name": row["drop_name"],
                "variant_name": row["variant_name"],
            })
    return pd.DataFrame(rows, columns=columns)


def _summary(
    registry: pd.DataFrame,
    artists: pd.DataFrame,
) -> pd.DataFrame:
    finish = (
        registry["finish"].astype(str).str.lower()
        if not registry.empty
        else pd.Series(dtype=str)
    )
    return pd.DataFrame([{
        "snapshot_date": datetime.now(
            timezone.utc
        ).date().isoformat(),
        "asset_count": int(len(registry)),
        "drop_count": int(
            registry["drop_name"].nunique()
            if not registry.empty else 0
        ),
        "foil_asset_count": int(
            finish.str.contains("foil", na=False).sum()
        ),
        "nonfoil_asset_count": int(
            finish.eq("nonfoil").sum()
        ),
        "franchise_count": int(
            registry["franchise"].nunique()
            if not registry.empty else 0
        ),
        "artist_count": int(
            artists["artist_name"].nunique()
            if not artists.empty else 0
        ),
        "average_msrp_usd": round(
            float(
                pd.to_numeric(
                    registry["msrp_usd"],
                    errors="coerce",
                ).mean()
            ),
            2,
        )
        if not registry.empty
        else 0.0,
        "earliest_release_date": (
            str(registry["release_date"].dropna().min())
            if not registry.empty
            and registry["release_date"].notna().any()
            else ""
        ),
        "latest_release_date": (
            str(registry["release_date"].dropna().max())
            if not registry.empty
            and registry["release_date"].notna().any()
            else ""
        ),
    }])


def build_secret_lair_datasets(
    *,
    registry_path: Path = REGISTRY_PATH,
) -> RegistryBuildResult:
    registry, exists = load_secret_lair_registry(
        registry_path
    )
    quality = _quality_findings(registry)
    variants = registry[
        [
            "secret_lair_id",
            "drop_name",
            "variant_name",
            "finish",
            "product_family",
            "msrp_usd",
            "currency",
            "availability_model",
            "status",
        ]
    ].copy()
    calendar = _release_calendar(registry)
    ip_catalog = _ip_catalog(registry)
    artists = _artist_catalog(registry)
    summary = _summary(registry, artists)

    return RegistryBuildResult(
        datasets={
            "secret_lair_registry": registry,
            "secret_lair_variants": variants,
            "secret_lair_release_calendar": calendar,
            "secret_lair_ip_catalog": ip_catalog,
            "secret_lair_artist_catalog": artists,
            "secret_lair_data_quality": quality,
            "secret_lair_summary": summary,
        },
        registry_path=str(registry_path),
        registry_exists=exists,
    )
