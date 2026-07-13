from pathlib import Path
import tempfile, unittest
import pandas as pd
from terminal2.warehouse_core import DashboardPublisher,DatasetDefinition,Warehouse,get_warehouse_config
class DashboardPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.warehouse=Warehouse(config=get_warehouse_config(Path(self.temp.name))); self.publisher=DashboardPublisher(self.warehouse)
    def tearDown(self): self.temp.cleanup()
    def test_publish(self):
        df=pd.DataFrame({'investment_product_id':['a','b'],'score':[90.,80.]}); definition=DatasetDefinition(name='investment_rankings',category='rankings',module='test',primary_key=('investment_product_id',),expected_columns=('investment_product_id','score'))
        result=self.publisher.publish(df,definition); self.assertTrue(Path(result.current_path).exists()); self.assertTrue(Path(result.snapshot_path).exists()); self.assertEqual(result.row_count,2)
    def test_duplicate_key_rejected(self):
        df=pd.DataFrame({'investment_product_id':['a','a']}); definition=DatasetDefinition(name='duplicate_test',category='admin',module='test',primary_key=('investment_product_id',))
        with self.assertRaises(ValueError): self.publisher.publish(df,definition)
    def test_missing_column_rejected(self):
        df=pd.DataFrame({'id':['a']}); definition=DatasetDefinition(name='schema_test',category='admin',module='test',expected_columns=('id','missing'))
        with self.assertRaises(ValueError): self.publisher.publish(df,definition)
if __name__=='__main__': unittest.main()
