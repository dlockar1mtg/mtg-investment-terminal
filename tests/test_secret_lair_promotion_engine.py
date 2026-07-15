from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import pandas as pd
from terminal2.secret_lair.promotion import engine

class T(unittest.TestCase):
    def products(self):
        return pd.DataFrame([
            {
                "secret_lair_id":"SL-1","product_name":"Good — Foil",
                "drop_name":"Good","variant_name":"Foil Edition","finish":"foil",
                "product_family":"drop","source_confidence":95,
                "source_name":"tcgcsv","source_record_id":"1",
            },
            {
                "secret_lair_id":"SL-2","product_name":"Unknown",
                "drop_name":"Unknown","variant_name":"Standard","finish":"unknown",
                "product_family":"drop","source_confidence":75,
                "source_name":"tcgcsv","source_record_id":"2",
            },
        ])
    def test_plan_filters_invalid_finish(self):
        products=self.products()
        history=pd.DataFrame([{
            "observation_date":"2026-07-14","secret_lair_id":"SL-1",
            "source_name":"tcgcsv","market_price":100,
            "low_price":90,"source_record_id":"1"
        }])
        with patch.object(engine,"_read") as read:
            def fake(path,columns=()):
                s=str(path)
                if s.endswith("master_secret_lair_products.csv"):return products.copy()
                if s.endswith("master_secret_lair_price_history.csv"):return history.copy()
                return pd.DataFrame(columns=list(columns))
            read.side_effect=fake
            plan=engine.build_secret_lair_promotion_plan()
        self.assertEqual(len(plan.registry_frame),1)
        self.assertEqual(plan.registry_frame.iloc[0]["secret_lair_id"],"SL-1")
        self.assertTrue(plan.apply_ready)
    def test_apply_creates_production_files(self):
        products=self.products().iloc[[0]].copy()
        history=pd.DataFrame([{
            "observation_date":"2026-07-14","secret_lair_id":"SL-1",
            "source_name":"tcgcsv","market_price":100,
            "low_price":90,"source_record_id":"1"
        }])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            registry=root/"registry.csv";prices=root/"prices.csv"
            log=root/"log.csv";backups=root/"backups"
            with patch.object(engine,"MASTER_PRODUCTS_PATH",root/"master_secret_lair_products.csv"),\
                 patch.object(engine,"MASTER_HISTORY_PATH",root/"master_secret_lair_price_history.csv"),\
                 patch.object(engine,"REGISTRY_PATH",registry),\
                 patch.object(engine,"PRICE_PATH",prices),\
                 patch.object(engine,"PROMOTION_LOG_PATH",log),\
                 patch.object(engine,"BACKUP_ROOT",backups),\
                 patch.object(engine,"_review_path",return_value=root/"review.csv"),\
                 patch.object(engine,"_current_master_prices_path",return_value=root/"current.csv"):
                products.to_csv(root/"master_secret_lair_products.csv",index=False)
                history.to_csv(root/"master_secret_lair_price_history.csv",index=False)
                result=engine.apply_secret_lair_promotion()
            self.assertTrue(result.applied)
            self.assertTrue(registry.exists())
            self.assertTrue(prices.exists())
if __name__=="__main__":unittest.main()
