from __future__ import annotations
from pathlib import Path
import pandas as pd
from terminal2.config import METADATA_FILE, METADATA_TEMPLATE_FILE
from terminal2.db.loaders import load_products_df
from terminal2.db.schema import get_connection, init_db


def create_template():
    products = load_products_df()
    output = products[["investment_product_id", "box_name", "product_type"]].copy()
    fields = ["release_date", "msrp", "print_status", "print_window_months", "months_out_of_print", "franchise", "ip_strength_score", "serialized_cards", "premium_treatment_score", "reprint_risk_score", "commander_demand_score", "competitive_demand_score", "collector_demand_score", "supply_class", "source", "confidence", "notes"]
    for field in fields:
        output[field] = ""
    Path(METADATA_TEMPLATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(METADATA_TEMPLATE_FILE, index=False)
    return output


def import_metadata(path=None):
    path = Path(path or METADATA_FILE)
    if not path.exists():
        create_template()
        raise FileNotFoundError(f"Metadata file missing: {path}. Template created at {METADATA_TEMPLATE_FILE}")
    df = pd.read_csv(path, dtype=str)
    init_db()
    connection = get_connection()
    count = 0
    def numeric(row, field):
        try:
            value = row.get(field)
            return float(value) if pd.notna(value) and str(value).strip() else None
        except Exception:
            return None
    try:
        for _, row in df.iterrows():
            investment_id = row.get("investment_product_id")
            if not investment_id:
                continue
            connection.execute("""INSERT INTO product_metadata (investment_product_id,release_date,msrp,print_status,print_window_months,months_out_of_print,franchise,ip_strength_score,serialized_cards,premium_treatment_score,reprint_risk_score,commander_demand_score,competitive_demand_score,collector_demand_score,supply_class,source,confidence,notes,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(investment_product_id) DO UPDATE SET release_date=excluded.release_date,msrp=excluded.msrp,print_status=excluded.print_status,print_window_months=excluded.print_window_months,months_out_of_print=excluded.months_out_of_print,franchise=excluded.franchise,ip_strength_score=excluded.ip_strength_score,serialized_cards=excluded.serialized_cards,premium_treatment_score=excluded.premium_treatment_score,reprint_risk_score=excluded.reprint_risk_score,commander_demand_score=excluded.commander_demand_score,competitive_demand_score=excluded.competitive_demand_score,collector_demand_score=excluded.collector_demand_score,supply_class=excluded.supply_class,source=excluded.source,confidence=excluded.confidence,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP""", (investment_id, row.get("release_date"), numeric(row,"msrp"), row.get("print_status"), numeric(row,"print_window_months"), numeric(row,"months_out_of_print"), row.get("franchise"), numeric(row,"ip_strength_score"), int(numeric(row,"serialized_cards") or 0), numeric(row,"premium_treatment_score"), numeric(row,"reprint_risk_score"), numeric(row,"commander_demand_score"), numeric(row,"competitive_demand_score"), numeric(row,"collector_demand_score"), row.get("supply_class"), row.get("source"), numeric(row,"confidence"), row.get("notes")))
            count += 1
        connection.commit()
    finally:
        connection.close()
    return count
