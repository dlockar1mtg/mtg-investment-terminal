from pathlib import Path
import tempfile,unittest
import pandas as pd
from terminal2.secret_lair.promotion.contracts import PROMOTION_CONTRACTS
from terminal2.secret_lair.promotion.exports import publish_promotion_datasets
from terminal2.warehouse_core import Warehouse,get_warehouse_config

class T(unittest.TestCase):
    def test_publish(self):
        datasets={
            name:pd.DataFrame(columns=contract.required_columns)
            for name,contract in PROMOTION_CONTRACTS.items()
        }
        datasets["secret_lair_promotion_summary"]=pd.DataFrame([{
            "snapshot_date":"2026-07-14","master_product_count":0,
            "eligible_product_count":0,"rejected_product_count":0,
            "review_remaining_count":0,"eligible_price_count":0,
            "production_registry_count":0,"production_price_count":0,
            "apply_ready":False,"last_apply_status":"Never Applied"
        }])
        datasets["secret_lair_registry_health"]=pd.DataFrame([{
            "snapshot_date":"2026-07-14","registry_product_count":0,
            "unique_registry_id_count":0,"duplicate_registry_id_count":0,
            "valid_finish_count":0,"invalid_finish_count":0,
            "priced_product_count":0,"orphan_price_count":0,
            "current_price_coverage":0.0,"integrity_status":"PASS"
        }])
        with tempfile.TemporaryDirectory() as temp:
            published=publish_promotion_datasets(
                datasets,
                warehouse=Warehouse(config=get_warehouse_config(Path(temp)))
            )
            self.assertEqual(len(published),7)
if __name__=="__main__":unittest.main()
