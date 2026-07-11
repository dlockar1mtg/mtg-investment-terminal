from __future__ import annotations

from pathlib import Path
import pandas as pd

from terminal2.market.config import (
    MARKET_INPUT_DIR,
    SUPPLY_INPUT_FILE,
    SALES_INPUT_FILE,
)
from terminal2.db.loaders import load_products_df


SUPPLY_COLUMNS = [
    "observation_date",
    "investment_product_id",
    "box_name",
    "source_name",
    "listing_count",
    "seller_count",
    "inventory_units",
    "inventory_change_7d",
    "inventory_change_30d",
    "source_confidence",
    "notes",
]

SALES_COLUMNS = [
    "observation_date",
    "investment_product_id",
    "box_name",
    "source_name",
    "sales_7d",
    "sales_30d",
    "median_sold_price_30d",
    "sell_through_rate_30d",
    "average_days_to_sale",
    "source_confidence",
    "notes",
]


def create_market_input_templates():
    MARKET_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    products = load_products_df()

    base = products[["investment_product_id", "box_name"]].copy() if not products.empty else pd.DataFrame(
        columns=["investment_product_id", "box_name"]
    )
    today = pd.Timestamp.now("UTC").date().isoformat()

    supply = base.copy()
    supply.insert(0, "observation_date", today)
    supply["source_name"] = "manual_or_external"
    for col in [
        "listing_count", "seller_count", "inventory_units",
        "inventory_change_7d", "inventory_change_30d",
    ]:
        supply[col] = ""
    supply["source_confidence"] = ""
    supply["notes"] = ""
    supply = supply[SUPPLY_COLUMNS]
    supply.to_csv(SUPPLY_INPUT_FILE, index=False)

    sales = base.copy()
    sales.insert(0, "observation_date", today)
    sales["source_name"] = "manual_or_external"
    for col in [
        "sales_7d", "sales_30d", "median_sold_price_30d",
        "sell_through_rate_30d", "average_days_to_sale",
    ]:
        sales[col] = ""
    sales["source_confidence"] = ""
    sales["notes"] = ""
    sales = sales[SALES_COLUMNS]
    sales.to_csv(SALES_INPUT_FILE, index=False)

    return {
        "supply": SUPPLY_INPUT_FILE,
        "sales": SALES_INPUT_FILE,
        "products": len(base),
    }
