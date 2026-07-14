from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition
@dataclass(frozen=True)
class MasterDatabaseContract:
 name:str;description:str;primary_key:tuple[str,...];required_columns:tuple[str,...];snapshot:bool=True
 def definition(self):
  return DatasetDefinition(name=self.name,category="secret_lair",module="terminal2.secret_lair.master_database",description=self.description,primary_key=self.primary_key,expected_columns=self.required_columns,required=True,snapshot=self.snapshot,version="1")
C=MasterDatabaseContract
MASTER_DATABASE_CONTRACTS={
 "master_secret_lair_products":C("master_secret_lair_products","Canonical sealed Secret Lair product catalog.",( "secret_lair_id",),("secret_lair_id","product_name","drop_name","variant_name","finish","product_family","release_date","msrp_usd","official_url","source_confidence")),
 "master_secret_lair_prices_current":C("master_secret_lair_prices_current","Latest product-level market prices.",( "secret_lair_id","source_name"),("secret_lair_id","source_name","observation_date","market_price","low_price","tcgplayer_product_id","tcgcsv_group_id")),
 "master_secret_lair_price_history":C("master_secret_lair_price_history","Persistent observed Secret Lair price history.",( "observation_date","secret_lair_id","source_name"),("observation_date","secret_lair_id","source_name","market_price","low_price","source_record_id"),False),
 "master_secret_lair_source_records":C("master_secret_lair_source_records","Raw normalized product evidence and provenance.",( "source_name","source_record_id"),("source_name","source_record_id","source_product_name","source_url","canonical_name","match_status","secret_lair_id"),False),
 "master_secret_lair_card_metadata":C("master_secret_lair_card_metadata","Scryfall Secret Lair card metadata for enrichment.",( "scryfall_id",),("scryfall_id","card_name","released_at","artist","collector_number","finishes","tcgplayer_id")),
 "master_secret_lair_product_map":C("master_secret_lair_product_map","Stable product identifiers for current and historical pricing.",( "secret_lair_id","tcgplayer_product_id"),("secret_lair_id","tcgplayer_product_id","tcgcsv_category_id","tcgcsv_group_id","product_name","match_confidence")),
 "master_secret_lair_review_queue":C("master_secret_lair_review_queue","Uncertain, duplicate, or incomplete products requiring review.",( "review_id",),("review_id","review_type","severity","source_name","source_record_id","product_name","message")),
 "master_secret_lair_summary":C("master_secret_lair_summary","Executive build and readiness summary.",( "snapshot_date",),("snapshot_date","source_product_count","canonical_product_count","current_price_count","historical_observation_count","review_count","registry_ready_count")),
}
def get_master_database_contract(name):
 try:return MASTER_DATABASE_CONTRACTS[name]
 except KeyError as exc:raise KeyError(f"Unknown master database contract: {name}") from exc
