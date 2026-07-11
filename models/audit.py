import pandas as pd

def create_projection_audit(df):
    rows = []
    for _, r in df.iterrows():
        notes = []

        if r["projection_confidence"] < 65:
            notes.append("Lower confidence due to new/thin data, volatility, or supply uncertainty.")
        if r.get("supply_dump_risk", 0) >= 70:
            notes.append("Elevated supply-dump risk may pressure prices.")
        if r.get("chase_concentration_risk", 0) >= 70:
            notes.append("High chase concentration: value may depend heavily on a small number of cards.")
        if r.get("ip_score", 0) >= 85:
            notes.append("Strong IP/franchise collectibility supports long-term sealed demand.")
        if r.get("demand_score", 0) >= 85:
            notes.append("High player/collector demand supports appreciation case.")
        if r.get("value_score", 0) < 45:
            notes.append("Current price appears elevated relative to estimated floor/fair value.")

        rows.append({
            "box_name": r["box_name"],
            "investment_score": r["investment_score"],
            "risk_adjusted_score": r["risk_adjusted_score"],
            "projection_confidence": r["projection_confidence"],
            "bear_cagr": r["bear_cagr"],
            "base_cagr": r["base_cagr"],
            "bull_cagr": r["bull_cagr"],
            "bear_5yr": r["bear_5yr"],
            "base_5yr": r["base_5yr"],
            "bull_5yr": r["bull_5yr"],
            "audit_notes": " ".join(notes) if notes else "Projection based on balanced quality, risk, and cohort assumptions.",
        })
    return pd.DataFrame(rows)
