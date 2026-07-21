from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class CalibrationResult:
    datasets:dict[str,pd.DataFrame]
    calibrated_scores:pd.DataFrame
    calibrated_recommendations:pd.DataFrame

def _num(df,col,default=0.0):
    if col not in df:return pd.Series(default,index=df.index,dtype=float)
    return pd.to_numeric(df[col],errors="coerce").fillna(default)

def _clip(values):
    series = pd.Series(
        values,
        index=getattr(values, "index", None),
        dtype="float64",
    )
    return series.clip(0, 100).round(2)

def _percentile(values,mask=None,neutral=50.0):
    series=pd.to_numeric(values,errors="coerce")
    result=pd.Series(neutral,index=series.index,dtype=float)
    valid=series.notna()
    if mask is not None:valid &= pd.Series(mask,index=series.index).fillna(False)
    if valid.sum()>=2:
        result.loc[valid]=series.loc[valid].rank(pct=True,method="average")*100
    elif valid.sum()==1:
        result.loc[valid]=neutral
    return result.round(2)

def _evidence_tier(features):
    priced=_num(features,"current_price").gt(0)
    observations=_num(features,"observation_count")
    span=_num(features,"history_span_days")
    sources=_num(features,"source_count")
    historical=priced & observations.ge(6) & span.ge(120)
    emerging=priced & ((observations.ge(2)) | (sources.ge(2))) & ~historical
    return pd.Series(
        np.select(
            [historical,emerging,priced],
            ["Historical","Emerging History","Current Price Only"],
            default="Insufficient",
        ),
        index=features.index,
    )

def _market_spread_percentile(current_prices,features):
    ids=features["investment_product_id"].str.replace("^SL-","",regex=True)
    cp=current_prices.copy()
    if cp.empty:return pd.Series(50.0,index=features.index)
    cp["investment_product_id"]="SL-"+cp["secret_lair_id"].astype(str)
    cp["market_price"]=pd.to_numeric(cp["market_price"],errors="coerce")
    cp["low_price"]=pd.to_numeric(cp["low_price"],errors="coerce")
    cp["market_low_spread_pct"]=np.where(
        cp["market_price"].gt(0),
        (cp["market_price"]-cp["low_price"])/cp["market_price"],
        np.nan,
    )
    spread=(
        cp.set_index("investment_product_id")["market_low_spread_pct"]
        .reindex(features["investment_product_id"])
        .reset_index(drop=True)
    )
    spread.index=features.index
    # Lower positive spread is preferable; negative values are treated as neutral/anomalous.
    clean=spread.where(spread.ge(0))
    pct=100-_percentile(clean,mask=clean.notna())
    return pct.clip(0,100).fillna(50).round(2)

def _availability(features):
    specs=[
        ("current_price",_num(features,"current_price").gt(0),"Fresh current market price",0.18),
        ("price_history",_num(features,"observation_count").ge(2),"At least two observations",0.22),
        ("long_history",_num(features,"history_span_days").ge(120),"At least 120 days of history",0.12),
        ("metadata",_num(features,"metadata_completeness").ge(60),"Metadata completeness at least 60%",0.15),
        ("msrp",_num(features,"msrp_usd").gt(0),"Original MSRP available",0.10),
        ("artist_ip",(_num(features,"artist_count").gt(0)|features.get("universes_beyond_flag",False)),"Artist or IP signal available",0.08),
        ("liquidity",_num(features,"liquidity_score").gt(0),"Market coverage supports a liquidity proxy",0.10),
        ("returns",features[[c for c in ["return_30d","return_90d","return_365d"] if c in features]].notna().any(axis=1) if any(c in features for c in ["return_30d","return_90d","return_365d"]) else pd.Series(False,index=features.index),"Observed return signal available",0.05),
    ]
    rows=[]
    for idx,row in features.iterrows():
        for code,mask,reason,weight in specs:
            available=bool(mask.loc[idx] if hasattr(mask,"loc") else mask)
            rows.append({
                "investment_product_id":row["investment_product_id"],
                "asset_class":row["asset_class"],
                "product_name":row["product_name"],
                "factor_code":code,
                "available":available,
                "availability_reason":reason if available else "Missing: "+reason,
                "importance_weight":weight,
            })
    return pd.DataFrame(rows)

def calibrate_secret_lair_intelligence(
    features,
    raw_scores,
    risk,
    confidence,
    coverage,
    current_prices,
):
    base=features[["investment_product_id","asset_class","product_name"]].copy()
    base["evidence_tier"]=_evidence_tier(features)
    priced=_num(features,"current_price").gt(0)

    # Cross-sectional signals allow current-price-only products to be ranked
    # without pretending that they have historical return evidence.
    price_pct=_percentile(_num(features,"current_price").replace(0,np.nan),mask=priced)
    scarcity_pct=_percentile(_num(raw_scores,"scarcity_score"),mask=pd.Series(True,index=features.index))
    metadata_pct=_percentile(_num(features,"metadata_completeness"),mask=pd.Series(True,index=features.index))
    liquidity_pct=_percentile(_num(features,"liquidity_score"),mask=priced)
    spread_pct=_market_spread_percentile(current_prices,features)

    raw=raw_scores.set_index("investment_product_id")
    raw_invest=raw["investment_score"].reindex(features["investment_product_id"]).fillna(0).reset_index(drop=True)
    raw_risk_adjusted=raw["risk_adjusted_score"].reindex(features["investment_product_id"]).fillna(0).reset_index(drop=True)
    conf=confidence.set_index("investment_product_id")["overall_confidence_score"].reindex(features["investment_product_id"]).fillna(0).reset_index(drop=True)
    risk_score=risk.set_index("investment_product_id")["overall_risk_score"].reindex(features["investment_product_id"]).fillna(100).reset_index(drop=True)

    relative=_clip(
        scarcity_pct*.30+
        metadata_pct*.20+
        liquidity_pct*.15+
        spread_pct*.15+
        (100-price_pct)*.10+
        _percentile(raw_invest)*.10
    )

    # Historical evidence retains the original model. Current-price-only assets
    # receive a conservative relative research score capped below Buy territory.
    historical=base["evidence_tier"].eq("Historical")
    emerging=base["evidence_tier"].eq("Emerging History")
    current_only=base["evidence_tier"].eq("Current Price Only")

    calibrated=pd.Series(0.0,index=base.index)
    calibrated.loc[historical]=(
        raw_invest.loc[historical]*.70+
        relative.loc[historical]*.30
    )
    calibrated.loc[emerging]=(
        raw_invest.loc[emerging]*.45+
        relative.loc[emerging]*.55
    ).clip(upper=72)
    calibrated.loc[current_only]=(
        32+relative.loc[current_only]*.28
    ).clip(upper=60)
    calibrated=_clip(calibrated)

    # Fresh current-price evidence earns a bounded confidence floor, but only
    # history can create High confidence.
    calibrated_conf=conf.astype(float).copy()
    calibrated_conf.loc[current_only]=np.maximum(
        calibrated_conf.loc[current_only],
        38+metadata_pct.loc[current_only]*.10+
        liquidity_pct.loc[current_only]*.07
    ).clip(upper=55)
    calibrated_conf.loc[emerging]=np.maximum(
        calibrated_conf.loc[emerging],
        50+metadata_pct.loc[emerging]*.10
    ).clip(upper=68)
    calibrated_conf.loc[historical]=np.maximum(
        calibrated_conf.loc[historical],60
    ).clip(upper=100)
    calibrated_conf=_clip(calibrated_conf)

    calibrated_ra=_clip(calibrated-(risk_score-50)*.25)
    base["calibrated_investment_score"]=calibrated
    base["calibrated_risk_adjusted_score"]=calibrated_ra
    base["relative_opportunity_percentile"]=relative
    base["calibrated_confidence_score"]=calibrated_conf
    base["price_percentile"]=price_pct
    base["market_spread_score"]=spread_pct
    base["calibration_status"]=np.select(
        [historical,emerging,current_only],
        ["History Backed","Provisional History","Cross-Sectional Only"],
        default="Blocked",
    )

    rec=base.copy()
    rec["recommendation_score"]=_clip(
        rec["calibrated_risk_adjusted_score"]*.72+
        rec["calibrated_confidence_score"]*.28
    )
    sufficient_history=historical
    rec["recommendation"]=np.select(
        [
            base["evidence_tier"].eq("Insufficient"),
            current_only & rec["recommendation_score"].ge(52),
            current_only,
            emerging & rec["recommendation_score"].ge(58),
            emerging,
            sufficient_history & rec["recommendation_score"].ge(78),
            sufficient_history & rec["recommendation_score"].ge(66),
            sufficient_history & rec["recommendation_score"].ge(54),
            sufficient_history & rec["recommendation_score"].ge(42),
        ],
        [
            "Insufficient Data",
            "Watch",
            "Hold",
            "Watch",
            "Hold",
            "Strong Buy",
            "Buy",
            "Watch",
            "Hold",
        ],
        default="Avoid",
    )
    rec["actionability"]=np.select(
        [
            rec["recommendation"].isin(["Strong Buy","Buy"]),
            rec["recommendation"].eq("Watch"),
            rec["recommendation"].eq("Hold"),
        ],
        ["Actionable","Research Candidate","Monitor"],
        default="Blocked",
    )
    rec["recommendation_basis"]=np.select(
        [historical,emerging,current_only],
        [
            "Historical price evidence and calibrated factors",
            "Limited history; provisional recommendation",
            "Fresh current price and cross-sectional ranking only",
        ],
        default="Insufficient price evidence",
    )
    rec=rec[[
        "investment_product_id","asset_class","product_name","recommendation",
        "recommendation_score","evidence_tier","recommendation_basis",
        "actionability","calibrated_investment_score",
        "calibrated_risk_adjusted_score","calibrated_confidence_score",
        "relative_opportunity_percentile",
    ]]

    availability=_availability(features)
    distribution=base.assign(priced=priced).groupby("evidence_tier",dropna=False).agg(
        product_count=("investment_product_id","count"),
        priced_count=("priced","sum"),
        mean_score=("calibrated_investment_score","mean"),
        median_score=("calibrated_investment_score","median"),
        minimum_score=("calibrated_investment_score","min"),
        maximum_score=("calibrated_investment_score","max"),
        mean_confidence=("calibrated_confidence_score","mean"),
    ).reset_index().round(2)

    counts=base["evidence_tier"].value_counts()
    recommendations=rec["recommendation"].value_counts()
    score_spread=float(base["calibrated_investment_score"].max()-base["calibrated_investment_score"].min()) if len(base) else 0
    summary=pd.DataFrame([{
        "snapshot_date":datetime.now(timezone.utc).date().isoformat(),
        "product_count":len(base),
        "priced_count":int(priced.sum()),
        "historical_count":int(counts.get("Historical",0)),
        "current_price_only_count":int(counts.get("Current Price Only",0)),
        "insufficient_count":int(counts.get("Insufficient",0)),
        "provisional_watch_count":int(recommendations.get("Watch",0)),
        "provisional_hold_count":int(recommendations.get("Hold",0)),
        "actionable_buy_count":int(recommendations.get("Buy",0)+recommendations.get("Strong Buy",0)),
        "score_spread":round(score_spread,2),
        "calibration_status":"PROVISIONAL_CURRENT_PRICE" if int(counts.get("Historical",0))==0 else "HISTORY_ENABLED",
    }])

    return CalibrationResult(
        datasets={
            "secret_lair_calibrated_scores":base,
            "secret_lair_calibrated_recommendations":rec,
            "secret_lair_factor_availability":availability,
            "secret_lair_score_distribution":distribution,
            "secret_lair_calibration_summary":summary,
        },
        calibrated_scores=base,
        calibrated_recommendations=rec,
    )
