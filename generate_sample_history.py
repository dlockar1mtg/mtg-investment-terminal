from pathlib import Path
import numpy as np
import pandas as pd

from config import PRODUCT_MASTER_FILE, HISTORICAL_IMPORT_FILE


def main(days=365, seed=42):
    rng = np.random.default_rng(seed)

    master = pd.read_csv(PRODUCT_MASTER_FILE, dtype=str)
    approved = master[master["approval_status"].astype(str).str.lower() == "approved"].copy()

    if approved.empty:
        print("No approved product master rows found. Run python run.py first.")
        return

    today = pd.Timestamp.utcnow().normalize()
    dates = pd.date_range(end=today, periods=days, freq="D")

    rows = []
    for _, row in approved.iterrows():
        # If no current price is in master, use broad default and let run.py update later.
        base_price = 400.0
        notes = str(row.get("notes", ""))
        if "market_price=" in notes:
            try:
                base_price = float(notes.split("market_price=")[-1].split(";")[0])
            except Exception:
                pass

        # modest random drift/volatility for testing only
        drift = rng.normal(0.00035, 0.00015)
        vol = rng.uniform(0.008, 0.018)
        prices = [base_price / np.exp(drift * days)]
        for _ in range(1, len(dates)):
            prices.append(prices[-1] * np.exp(rng.normal(drift, vol)))

        # scale final price roughly toward base
        scale = base_price / prices[-1] if prices[-1] else 1
        prices = [max(1, p * scale) for p in prices]

        for d, p in zip(dates, prices):
            rows.append({
                "observation_date": d.date().isoformat(),
                "investment_product_id": row["investment_product_id"],
                "tcgplayer_product_id": row["approved_tcgplayer_product_id"],
                "box_name": row["box_name"],
                "set_name": row["set_name"],
                "current_price": round(float(p), 2),
                "low_price": round(float(p) * 0.95, 2),
                "price_source": "synthetic_sample_history",
                "price_data_quality": 25,
                "source_note": "Synthetic sample history for testing metrics only. Replace with real historical prices.",
            })

    out = pd.DataFrame(rows)
    Path(HISTORICAL_IMPORT_FILE).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(HISTORICAL_IMPORT_FILE, index=False)
    print(f"Sample historical import created: {HISTORICAL_IMPORT_FILE}")
    print(f"Rows: {len(out)}")
    print("Next run: python import_historical_prices.py")


if __name__ == "__main__":
    main()
