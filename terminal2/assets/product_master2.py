from __future__ import annotations
from pathlib import Path
import pandas as pd
from terminal2.config import PRODUCT_MASTER_FILE, DISCOVERY_CANDIDATES_FILE


def merge_candidates(auto_approve=True):
    master = pd.read_csv(PRODUCT_MASTER_FILE, dtype=str) if Path(PRODUCT_MASTER_FILE).exists() else pd.DataFrame()
    candidates = pd.read_csv(DISCOVERY_CANDIDATES_FILE, dtype=str)
    existing = set(master.get("investment_product_id", pd.Series(dtype=str)).astype(str))
    additions = []
    for _, row in candidates.iterrows():
        product_id = str(row["investment_product_id"])
        if product_id in existing:
            continue
        score = float(row.get("candidate_score") or 0)
        product_type = row.get("investment_product_type")
        status = "review_required"
        if auto_approve and score >= 190 and product_type != "Secret Lair Drop":
            status = "approved"
        additions.append({
            "investment_product_id": product_id,
            "set_name": row.get("set_name"),
            "box_name": row.get("box_name"),
            "approved_tcgplayer_product_id": row.get("approved_tcgplayer_product_id"),
            "approved_product_name": row.get("approved_product_name"),
            "tcgcsv_category_id": row.get("tcgcsv_category_id"),
            "tcgcsv_group_id": row.get("tcgcsv_group_id"),
            "investment_product_type": product_type,
            "approval_status": status,
            "approval_method": "module1_auto" if status == "approved" else "module1_review",
            "notes": f"candidate_score={score}",
        })
    if additions:
        master = pd.concat([master, pd.DataFrame(additions)], ignore_index=True, sort=False)
    master.to_csv(PRODUCT_MASTER_FILE, index=False)
    return master, pd.DataFrame(additions)
