from dataclasses import dataclass
from pathlib import Path
import csv,pandas as pd
from terminal2.warehouse_core import get_warehouse_config
from .contracts import CALIBRATION_CONTRACTS

@dataclass(frozen=True)
class CalibrationValidationResult:
    passed:bool
    errors:tuple[str,...]
    warnings:tuple[str,...]
    datasets_checked:int
    products:int
    score_spread:float
    actionable_buys:int

def validate_secret_lair_calibration(project_root=None):
    cfg=get_warehouse_config(project_root)
    manifest_path=cfg.manifests_root/"dataset_manifest.csv"
    errors=[];warnings=[];frames={}
    if not manifest_path.exists():
        return CalibrationValidationResult(False,(f"Missing manifest: {manifest_path}",),(),0,0,0,0)
    with manifest_path.open("r",newline="",encoding="utf-8") as h:
        manifest={r["dataset_name"]:r for r in csv.DictReader(h)}
    for name,contract in CALIBRATION_CONTRACTS.items():
        row=manifest.get(name)
        if row is None:errors.append(f"Missing calibration dataset: {name}");continue
        path=Path(row["current_path"])
        if not path.exists():errors.append(f"Missing calibration file: {path}");continue
        frame=pd.read_csv(path);frames[name]=frame
        missing=set(contract.required_columns)-set(frame.columns)
        if missing:errors.append(f"{name} missing columns: {sorted(missing)}")
        if contract.primary_key and not frame.empty and frame[list(contract.primary_key)].duplicated().any():
            errors.append(f"{name} has duplicate primary keys")
    summary=frames.get("secret_lair_calibration_summary",pd.DataFrame())
    products=0;spread=0;buys=0
    if len(summary)!=1:errors.append("Calibration summary must contain exactly one row.")
    else:
        row=summary.iloc[0]
        products=int(row["product_count"]);spread=float(row["score_spread"]);buys=int(row["actionable_buy_count"])
        if int(row["historical_count"])==0:
            warnings.append("No Secret Lair products have sufficient historical evidence; Buy and Strong Buy remain disabled.")
        if spread<10:
            warnings.append("Calibrated score spread remains narrow; additional metadata and history are still needed.")
    rec=frames.get("secret_lair_calibrated_recommendations",pd.DataFrame())
    if not rec.empty:
        invalid=rec[
            rec["evidence_tier"].isin(["Current Price Only","Insufficient"])
            & rec["recommendation"].isin(["Buy","Strong Buy"])
        ]
        if not invalid.empty:errors.append("Current-price-only products received actionable Buy recommendations.")
    return CalibrationValidationResult(not errors,tuple(errors),tuple(warnings),len(CALIBRATION_CONTRACTS),products,spread,buys)
