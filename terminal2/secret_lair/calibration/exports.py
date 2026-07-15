from terminal2.warehouse_core import DashboardPublisher,Warehouse
from .contracts import get_calibration_contract
from .engine import calibrate_secret_lair_intelligence

def publish_calibration_datasets(datasets,warehouse=None):
    publisher=DashboardPublisher(warehouse or Warehouse())
    return publisher.publish_many(
        [(frame,get_calibration_contract(name).definition()) for name,frame in datasets.items()],
        message="Terminal 2.9.9 Secret Lair intelligence calibration",
    )

def publish_secret_lair_calibration(
    features,raw_scores,risk,confidence,coverage,current_prices,warehouse=None
):
    result=calibrate_secret_lair_intelligence(
        features,raw_scores,risk,confidence,coverage,current_prices
    )
    published=publish_calibration_datasets(result.datasets,warehouse)
    summary=result.datasets["secret_lair_calibration_summary"].iloc[0]
    return result,{
        "datasets":len(published),
        "products":int(summary["product_count"]),
        "priced_products":int(summary["priced_count"]),
        "historical_products":int(summary["historical_count"]),
        "provisional_watch":int(summary["provisional_watch_count"]),
        "provisional_hold":int(summary["provisional_hold_count"]),
        "actionable_buys":int(summary["actionable_buy_count"]),
        "score_spread":float(summary["score_spread"]),
        "status":str(summary["calibration_status"]),
    }
