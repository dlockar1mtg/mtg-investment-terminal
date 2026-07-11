from terminal2.features.lifecycle import lifecycle_report
from terminal2.config import EXPORT_DIR

if __name__ == "__main__":
    data = lifecycle_report()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = EXPORT_DIR / "lifecycle_report.csv"
    data.to_csv(output, index=False)
    print(data.groupby(["product_type", "lifecycle_stage"]).size().to_string())
    print(f"\nCreated: {output}")
