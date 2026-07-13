from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from terminal2.warehouse_core import Warehouse, get_warehouse_config


@dataclass(frozen=True)
class SemanticBuildResult:
    datasets: dict[str, pd.DataFrame]
    source_dataset_count: int


def _product_key(product_id: object) -> str:
    value = str(product_id or "").strip()
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16].upper()
    return f"P_{digest}"


def _date_key(value: object) -> int:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid date value for DateKey: {value}")
    return int(parsed.strftime("%Y%m%d"))


def _read_current(
    config,
    category: str,
    dataset_name: str,
    *,
    required: bool = True,
) -> pd.DataFrame:
    path = config.current_root / category / f"{dataset_name}.csv"
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"Required warehouse source is missing: {path}"
            )
        return pd.DataFrame()
    return pd.read_csv(path)


def _safe_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    output = frame.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = pd.NA
    return output[list(columns)]


def _dim_product(config) -> pd.DataFrame:
    history = _read_current(
        config,
        "products",
        "historical_prices",
    )
    forecast = _read_current(
        config,
        "intelligence",
        "forecast_product_summary",
    )

    history_columns = [
        column for column in (
            "investment_product_id",
            "box_name",
            "set_name",
            "product_type",
        )
        if column in history.columns
    ]
    product_history = (
        history[history_columns]
        .drop_duplicates("investment_product_id")
        if history_columns
        else pd.DataFrame()
    )

    forecast_columns = [
        column for column in (
            "investment_product_id",
            "box_name",
            "set_name",
            "product_type",
        )
        if column in forecast.columns
    ]
    product_forecast = (
        forecast[forecast_columns]
        .drop_duplicates("investment_product_id")
        if forecast_columns
        else pd.DataFrame()
    )

    products = pd.concat(
        [product_forecast, product_history],
        ignore_index=True,
        sort=False,
    ).drop_duplicates("investment_product_id", keep="first")

    products = _safe_columns(
        products,
        (
            "investment_product_id",
            "box_name",
            "set_name",
            "product_type",
        ),
    )
    products["ProductKey"] = products[
        "investment_product_id"
    ].map(_product_key)
    products["ProductDisplayName"] = products["box_name"]
    products["ProductTypeGroup"] = np.select(
        [
            products["product_type"].astype(str).str.contains(
                "collector", case=False, na=False
            ),
            products["product_type"].astype(str).str.contains(
                "draft|traditional|booster box",
                case=False,
                na=False,
            ),
            products["product_type"].astype(str).str.contains(
                "jumpstart", case=False, na=False
            ),
        ],
        [
            "Collector Booster Displays",
            "Draft / Traditional Booster Boxes",
            "Jumpstart",
        ],
        default="Other Sealed",
    )
    products["IsApproved"] = True
    return products[
        [
            "ProductKey",
            "investment_product_id",
            "box_name",
            "ProductDisplayName",
            "set_name",
            "product_type",
            "ProductTypeGroup",
            "IsApproved",
        ]
    ].sort_values("box_name").reset_index(drop=True)


def _dim_date(config) -> pd.DataFrame:
    prices = _read_current(
        config,
        "products",
        "historical_prices",
    )
    dates = pd.to_datetime(
        prices["observation_date"],
        errors="coerce",
    ).dropna()

    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    minimum = dates.min().normalize() if len(dates) else today
    maximum = max(
        dates.max().normalize() if len(dates) else today,
        today,
    )

    calendar = pd.DataFrame({
        "Date": pd.date_range(minimum, maximum, freq="D")
    })
    calendar["DateKey"] = calendar["Date"].dt.strftime(
        "%Y%m%d"
    ).astype(int)
    calendar["Year"] = calendar["Date"].dt.year
    calendar["QuarterNumber"] = calendar["Date"].dt.quarter
    calendar["Quarter"] = (
        "Q" + calendar["QuarterNumber"].astype(str)
    )
    calendar["MonthNumber"] = calendar["Date"].dt.month
    calendar["MonthName"] = calendar["Date"].dt.month_name()
    calendar["MonthShortName"] = calendar["Date"].dt.strftime("%b")
    calendar["YearMonth"] = calendar["Date"].dt.strftime("%Y-%m")
    calendar["YearMonthSort"] = (
        calendar["Year"] * 100 + calendar["MonthNumber"]
    )
    calendar["WeekOfYear"] = calendar["Date"].dt.isocalendar().week.astype(int)
    calendar["DayOfMonth"] = calendar["Date"].dt.day
    calendar["DayName"] = calendar["Date"].dt.day_name()
    calendar["IsMonthEnd"] = calendar["Date"].dt.is_month_end
    calendar["IsCurrentDate"] = calendar["Date"].eq(today)
    calendar["Date"] = calendar["Date"].dt.date.astype(str)
    return calendar


def _merge_product_snapshot(config, dim_product) -> pd.DataFrame:
    forecast = _read_current(
        config,
        "intelligence",
        "forecast_product_summary",
    )
    market = _read_current(
        config,
        "market",
        "market_intelligence",
    )
    coverage = _read_current(
        config,
        "metadata",
        "historical_coverage",
    )
    recommendations = _read_current(
        config,
        "portfolio",
        "portfolio_recommendations",
    )
    positions = _read_current(
        config,
        "portfolio",
        "portfolio_positions",
        required=False,
    )

    snapshot = dim_product[
        [
            "ProductKey",
            "investment_product_id",
        ]
    ].copy()

    sources = [
        forecast,
        market,
        coverage,
        recommendations,
    ]
    if not positions.empty:
        sources.append(positions)

    for source in sources:
        if source.empty or "investment_product_id" not in source.columns:
            continue
        source = source.drop_duplicates("investment_product_id")
        duplicate_columns = [
            column
            for column in source.columns
            if column in snapshot.columns
            and column != "investment_product_id"
        ]
        source = source.drop(columns=duplicate_columns)
        snapshot = snapshot.merge(
            source,
            on="investment_product_id",
            how="left",
        )

    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    snapshot["SnapshotDate"] = snapshot_date
    snapshot["SnapshotDateKey"] = _date_key(snapshot_date)

    required_numeric = {
        "current_price": 0.0,
        "investment_score": 0.0,
        "risk_adjusted_score": 0.0,
        "conviction_score": 0.0,
        "forecast_confidence": 0.0,
        "market_intelligence_score": 0.0,
        "market_intelligence_confidence": 0.0,
        "history_confidence": 0.0,
        "observation_count": 0.0,
        "expected_cagr": 0.0,
        "forecast_expected_cagr": 0.0,
        "prob_loss": 0.0,
        "probability_loss_12m": 0.0,
        "target_weight": 0.0,
        "current_portfolio_weight": 0.0,
    }
    for column, default in required_numeric.items():
        if column not in snapshot.columns:
            snapshot[column] = default
        snapshot[column] = pd.to_numeric(
            snapshot[column],
            errors="coerce",
        ).fillna(default)

    if "forecast_regime" not in snapshot.columns:
        snapshot["forecast_regime"] = "Unknown"
    if "conviction_tier" not in snapshot.columns:
        snapshot["conviction_tier"] = "Unknown"
    if "recommendation" not in snapshot.columns:
        snapshot["recommendation"] = "Not Rated"

    return snapshot


def _fact_price_history(config, product_map) -> pd.DataFrame:
    prices = _read_current(
        config,
        "products",
        "historical_prices",
    ).copy()
    prices["ProductKey"] = prices[
        "investment_product_id"
    ].map(product_map)
    prices["DateKey"] = prices["observation_date"].map(_date_key)
    prices = prices.dropna(subset=["ProductKey"])
    return prices


def _fact_forecast(config, product_map) -> pd.DataFrame:
    forecast = _read_current(
        config,
        "intelligence",
        "forecast_horizons",
    ).copy()
    forecast["ProductKey"] = forecast[
        "investment_product_id"
    ].map(product_map)
    forecast = forecast.dropna(subset=["ProductKey"])
    return forecast


def _fact_portfolio(config, product_map) -> pd.DataFrame:
    positions = _read_current(
        config,
        "portfolio",
        "portfolio_positions",
        required=False,
    ).copy()

    required = (
        "investment_product_id",
        "quantity",
        "current_price",
        "current_value",
        "portfolio_weight",
    )
    positions = _safe_columns(positions, required)
    positions["ProductKey"] = positions[
        "investment_product_id"
    ].map(product_map)
    return positions[
        [
            "ProductKey",
            *required,
        ]
    ].dropna(subset=["ProductKey"])


def _executive_kpis(config, snapshot) -> pd.DataFrame:
    forecast_summary = _read_current(
        config,
        "executive",
        "forecast_market_summary",
    )
    portfolio_summary = _read_current(
        config,
        "executive",
        "portfolio_summary",
    )
    historical_summary = _read_current(
        config,
        "executive",
        "historical_summary",
    )
    market_summary = _read_current(
        config,
        "executive",
        "market_health_summary",
    )

    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    snapshot_key = _date_key(snapshot_date)

    def value(frame, column, default=0):
        if frame.empty or column not in frame.columns:
            return default
        return frame.iloc[-1][column]

    rows = [
        (
            "Tracked Products",
            len(snapshot),
            "0",
            "Coverage",
            "Number of products represented in the current semantic model.",
        ),
        (
            "Average Investment Score",
            round(float(snapshot["investment_score"].mean()), 2),
            "0.00",
            "Investment",
            "Average current investment score across tracked products.",
        ),
        (
            "Average Risk-Adjusted Score",
            round(float(snapshot["risk_adjusted_score"].mean()), 2),
            "0.00",
            "Investment",
            "Average risk-adjusted score across tracked products.",
        ),
        (
            "Average Conviction Score",
            value(
                forecast_summary,
                "average_conviction_score",
                round(float(snapshot["conviction_score"].mean()), 2),
            ),
            "0.00",
            "Forecast",
            "Average combined conviction score across forecasted products.",
        ),
        (
            "Average Forecast Confidence",
            value(
                forecast_summary,
                "average_forecast_confidence",
                round(float(snapshot["forecast_confidence"].mean()), 2),
            ),
            "0.00",
            "Forecast",
            "Average evidence-weighted confidence of current forecasts.",
        ),
        (
            "Bullish Products",
            value(forecast_summary, "bullish_product_count", 0),
            "0",
            "Forecast",
            "Products classified as Bull or Positive forecast regimes.",
        ),
        (
            "Bearish Products",
            value(forecast_summary, "bearish_product_count", 0),
            "0",
            "Forecast",
            "Products classified as Weak or Bear forecast regimes.",
        ),
        (
            "Historical Observations",
            value(historical_summary, "observation_count", 0),
            "#,0",
            "Coverage",
            "Canonical historical price observations available to the model.",
        ),
        (
            "Historical Products",
            value(historical_summary, "product_count", 0),
            "0",
            "Coverage",
            "Products with at least one historical observation.",
        ),
        (
            "Current Portfolio Value",
            value(portfolio_summary, "current_value", 0),
            "$#,0.00",
            "Portfolio",
            "Current market value of entered portfolio holdings.",
        ),
        (
            "Portfolio Health Score",
            value(portfolio_summary, "portfolio_health_score", 0),
            "0.00",
            "Portfolio",
            "Combined quality, confidence, and diversification score.",
        ),
        (
            "Market Health Score",
            value(market_summary, "market_health_score", 0),
            "0.00",
            "Market",
            "Current sealed-market health indicator when available.",
        ),
    ]

    return pd.DataFrame([
        {
            "SnapshotDateKey": snapshot_key,
            "SnapshotDate": snapshot_date,
            "KPIName": name,
            "KPIValue": metric,
            "DisplayFormat": display,
            "KPIGroup": group,
            "BusinessDefinition": definition,
        }
        for name, metric, display, group, definition in rows
    ])


def _refresh_status(config) -> pd.DataFrame:
    manifest_path = config.manifests_root / "dataset_manifest.csv"
    if not manifest_path.exists():
        return pd.DataFrame(
            columns=[
                "DatasetName",
                "Category",
                "PublishedAtUTC",
                "RowCount",
                "Status",
                "IsCurrent",
                "CurrentPath",
                "RefreshID",
            ]
        )

    with manifest_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle))

    now = pd.Timestamp.now(tz="UTC")
    output = []
    for row in rows:
        published = pd.to_datetime(
            row.get("published_at_utc"),
            errors="coerce",
            utc=True,
        )
        age_hours = (
            (now - published).total_seconds() / 3600
            if pd.notna(published)
            else np.nan
        )
        output.append({
            "DatasetName": row.get("dataset_name"),
            "Category": row.get("category"),
            "PublishedAtUTC": row.get("published_at_utc"),
            "RowCount": int(float(row.get("row_count") or 0)),
            "Status": row.get("status") or "unknown",
            "IsCurrent": bool(
                pd.notna(age_hours) and age_hours <= 48
            ),
            "AgeHours": round(age_hours, 2)
            if pd.notna(age_hours) else np.nan,
            "CurrentPath": row.get("current_path"),
            "RefreshID": row.get("refresh_id"),
        })
    return pd.DataFrame(output)


def _relationship_map() -> pd.DataFrame:
    rows = [
        (
            "DimProduct_ProductSnapshot",
            "semantic_dim_product",
            "ProductKey",
            "semantic_fact_product_snapshot",
            "ProductKey",
            "One-to-many",
            "Single",
            True,
        ),
        (
            "DimProduct_PriceHistory",
            "semantic_dim_product",
            "ProductKey",
            "semantic_fact_price_history",
            "ProductKey",
            "One-to-many",
            "Single",
            True,
        ),
        (
            "DimDate_PriceHistory",
            "semantic_dim_date",
            "DateKey",
            "semantic_fact_price_history",
            "DateKey",
            "One-to-many",
            "Single",
            True,
        ),
        (
            "DimProduct_Forecast",
            "semantic_dim_product",
            "ProductKey",
            "semantic_fact_forecast",
            "ProductKey",
            "One-to-many",
            "Single",
            True,
        ),
        (
            "DimProduct_Portfolio",
            "semantic_dim_product",
            "ProductKey",
            "semantic_fact_portfolio",
            "ProductKey",
            "One-to-one",
            "Single",
            True,
        ),
        (
            "DimDate_ExecutiveKPIs",
            "semantic_dim_date",
            "DateKey",
            "semantic_executive_kpis",
            "SnapshotDateKey",
            "One-to-many",
            "Single",
            True,
        ),
    ]
    columns = [
        "RelationshipName",
        "FromTable",
        "FromColumn",
        "ToTable",
        "ToColumn",
        "Cardinality",
        "CrossFilterDirection",
        "IsActive",
    ]
    return pd.DataFrame(rows, columns=columns)


def _measure_catalog() -> pd.DataFrame:
    rows = [
        (
            "Tracked Products",
            "semantic_fact_product_snapshot",
            "DISTINCTCOUNT(semantic_fact_product_snapshot[ProductKey])",
            "0",
            "Executive",
            "Count of products represented in the current snapshot.",
        ),
        (
            "Average Investment Score",
            "semantic_fact_product_snapshot",
            "AVERAGE(semantic_fact_product_snapshot[investment_score])",
            "0.00",
            "Investment",
            "Average current product investment score.",
        ),
        (
            "Average Risk-Adjusted Score",
            "semantic_fact_product_snapshot",
            "AVERAGE(semantic_fact_product_snapshot[risk_adjusted_score])",
            "0.00",
            "Investment",
            "Average risk-adjusted product score.",
        ),
        (
            "Average Conviction",
            "semantic_fact_product_snapshot",
            "AVERAGE(semantic_fact_product_snapshot[conviction_score])",
            "0.00",
            "Forecast",
            "Average current product conviction score.",
        ),
        (
            "Current Portfolio Value",
            "semantic_fact_portfolio",
            "SUM(semantic_fact_portfolio[current_value])",
            "$#,0.00",
            "Portfolio",
            "Current value of all entered portfolio positions.",
        ),
        (
            "Portfolio Cost Basis",
            "semantic_fact_portfolio",
            "SUM(semantic_fact_portfolio[acquisition_cost_total])",
            "$#,0.00",
            "Portfolio",
            "Total entered acquisition cost.",
        ),
        (
            "Portfolio Unrealized Gain",
            "semantic_fact_portfolio",
            "[Current Portfolio Value] - [Portfolio Cost Basis]",
            "$#,0.00",
            "Portfolio",
            "Difference between current portfolio value and cost basis.",
        ),
        (
            "Latest Market Price",
            "semantic_fact_price_history",
            "CALCULATE(MAX(semantic_fact_price_history[market_price]), LASTDATE(semantic_dim_date[Date]))",
            "$#,0.00",
            "Prices",
            "Latest visible historical market price in filter context.",
        ),
        (
            "12M Base Forecast Return",
            "semantic_fact_forecast",
            "CALCULATE(AVERAGE(semantic_fact_forecast[expected_return]), semantic_fact_forecast[horizon_months] = 12)",
            "0.0%",
            "Forecast",
            "Average base expected return at the 12-month horizon.",
        ),
        (
            "12M Probability of Loss",
            "semantic_fact_forecast",
            "CALCULATE(AVERAGE(semantic_fact_forecast[probability_of_loss]), semantic_fact_forecast[horizon_months] = 12)",
            "0.0%",
            "Forecast",
            "Average modeled probability of loss at 12 months.",
        ),
    ]
    columns = [
        "MeasureName",
        "HomeTable",
        "DAXExpression",
        "DisplayFormat",
        "MeasureGroup",
        "BusinessDefinition",
    ]
    return pd.DataFrame(rows, columns=columns)


def _field_description(dataset: str, field: str) -> str:
    descriptions = {
        "ProductKey": "Stable hashed surrogate key used for Power BI relationships.",
        "DateKey": "Integer date key in YYYYMMDD format.",
        "SnapshotDateKey": "DateKey for the current snapshot publication date.",
        "investment_product_id": "Canonical Terminal product identifier.",
        "current_price": "Latest available sealed-product market price.",
        "investment_score": "Current composite investment attractiveness score.",
        "risk_adjusted_score": "Investment score adjusted for modeled risk.",
        "conviction_score": "Unified forecast conviction score from zero to one hundred.",
        "portfolio_weight": "Position share of total entered portfolio value.",
        "expected_return": "Base forecast price return over the selected horizon.",
        "probability_of_loss": "Modeled probability that horizon return is below zero.",
        "KPIValue": "Current numeric or text value for the named executive KPI.",
    }
    return descriptions.get(
        field,
        f"{field.replace('_', ' ').replace('Key', ' key').strip().title()} "
        f"from {dataset}.",
    )


def _field_dictionary(
    datasets: dict[str, pd.DataFrame],
    contracts,
) -> pd.DataFrame:
    rows = []
    for name, frame in datasets.items():
        if name == "semantic_field_dictionary":
            continue
        key_fields = set(contracts[name].primary_key)
        for ordinal, field in enumerate(frame.columns, start=1):
            series = frame[field]
            rows.append({
                "DatasetName": name,
                "FieldName": field,
                "FieldOrdinal": ordinal,
                "DataType": str(series.dtype),
                "IsKey": field in key_fields,
                "Nullable": bool(series.isna().any()),
                "BusinessDescription": _field_description(
                    name,
                    field,
                ),
            })
    return pd.DataFrame(rows)


def build_semantic_datasets(
    *,
    project_root: Path | None = None,
) -> SemanticBuildResult:
    from terminal2.semantic.contracts import SEMANTIC_DATASET_CONTRACTS

    config = get_warehouse_config(project_root)
    warehouse = Warehouse(config=config)
    warehouse.initialize()

    dim_product = _dim_product(config)
    product_map = dict(zip(
        dim_product["investment_product_id"],
        dim_product["ProductKey"],
    ))
    dim_date = _dim_date(config)
    product_snapshot = _merge_product_snapshot(
        config,
        dim_product,
    )
    price_history = _fact_price_history(config, product_map)
    forecast = _fact_forecast(config, product_map)
    portfolio = _fact_portfolio(config, product_map)
    executive_kpis = _executive_kpis(
        config,
        product_snapshot,
    )
    refresh_status = _refresh_status(config)
    relationships = _relationship_map()
    measures = _measure_catalog()

    datasets = {
        "semantic_dim_product": dim_product,
        "semantic_dim_date": dim_date,
        "semantic_fact_product_snapshot": product_snapshot,
        "semantic_fact_price_history": price_history,
        "semantic_fact_forecast": forecast,
        "semantic_fact_portfolio": portfolio,
        "semantic_executive_kpis": executive_kpis,
        "semantic_refresh_status": refresh_status,
        "semantic_relationship_map": relationships,
        "semantic_measure_catalog": measures,
    }
    datasets["semantic_field_dictionary"] = _field_dictionary(
        datasets,
        SEMANTIC_DATASET_CONTRACTS,
    )

    return SemanticBuildResult(
        datasets=datasets,
        source_dataset_count=len(refresh_status),
    )
