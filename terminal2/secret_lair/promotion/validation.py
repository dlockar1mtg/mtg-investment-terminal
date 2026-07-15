from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
import pandas as pd
from terminal2.warehouse_core import get_warehouse_config
from .contracts import PROMOTION_CONTRACTS

@dataclass(frozen=True)
class PromotionValidationResult:
    passed: bool
    errors: tuple[str,...]
    warnings: tuple[str,...]
    datasets_checked: int
    eligible_products: int
    production_registry: int
    production_prices: int

def validate_secret_lair_promotion(project_root=None):
    config = get_warehouse_config(project_root)
    manifest_path = config.manifests_root / "dataset_manifest.csv"
    errors=[]; warnings=[]; frames={}
    if not manifest_path.exists():
        return PromotionValidationResult(
            False,(f"Missing dataset manifest: {manifest_path}",),(),
            0,0,0,0
        )
    with manifest_path.open("r",newline="",encoding="utf-8") as handle:
        manifest={row["dataset_name"]:row for row in csv.DictReader(handle)}

    for name, contract in PROMOTION_CONTRACTS.items():
        row=manifest.get(name)
        if row is None:
            errors.append(f"Missing promotion dataset: {name}")
            continue
        path=Path(row["current_path"])
        if not path.exists():
            errors.append(f"Missing promotion file: {path}")
            continue
        frame=pd.read_csv(path);frames[name]=frame
        missing=set(contract.required_columns)-set(frame.columns)
        if missing:
            errors.append(f"{name} missing columns: {sorted(missing)}")
        if contract.primary_key and not frame.empty:
            keys=frame[list(contract.primary_key)]
            if keys.isna().any(axis=None):
                errors.append(f"{name} contains null primary-key values.")
            if keys.duplicated().any():
                errors.append(f"{name} contains duplicate primary keys.")

    summary=frames.get("secret_lair_promotion_summary",pd.DataFrame())
    eligible=production_registry=production_prices=0
    if len(summary)!=1:
        errors.append("Promotion summary must contain exactly one row.")
    else:
        row=summary.iloc[0]
        eligible=int(row["eligible_product_count"])
        production_registry=int(row["production_registry_count"])
        production_prices=int(row["production_price_count"])
        if eligible == 0:
            warnings.append("No products currently pass the promotion safeguards.")
        if production_registry == 0:
            warnings.append("Production Secret Lair registry is still empty.")

    health=frames.get("secret_lair_registry_health",pd.DataFrame())
    if len(health)==1 and str(health.iloc[0]["integrity_status"])=="FAIL":
        errors.append("Production registry health checks failed.")

    return PromotionValidationResult(
        not errors,tuple(errors),tuple(warnings),
        len(PROMOTION_CONTRACTS),eligible,
        production_registry,production_prices
    )
