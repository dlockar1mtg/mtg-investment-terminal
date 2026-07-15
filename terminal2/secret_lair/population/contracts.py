from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition
@dataclass(frozen=True)
class PopulationContract:
 name:str;description:str;primary_key:tuple[str,...];required_columns:tuple[str,...];snapshot:bool=True
 def definition(self):return DatasetDefinition(name=self.name,category="secret_lair",module="terminal2.secret_lair.population",description=self.description,primary_key=self.primary_key,expected_columns=self.required_columns,required=True,snapshot=self.snapshot,version="1")
POPULATION_CONTRACTS={
"secret_lair_population_candidates":PopulationContract("secret_lair_population_candidates","Canonical population candidates and guarded acceptance status.",( "source_name","source_record_id"),("source_name","source_record_id","secret_lair_id","drop_name","variant_name","finish","population_status","match_confidence","ready_for_registry")),
"secret_lair_population_duplicates":PopulationContract("secret_lair_population_duplicates","Potential duplicate source records grouped by canonical identity.",( "duplicate_id",),("duplicate_id","canonical_identity","source_name","source_record_id","duplicate_group_size","duplicate_status"),False),
"secret_lair_population_conflicts":PopulationContract("secret_lair_population_conflicts","Population conflicts that block unattended registry application.",( "conflict_id",),("conflict_id","source_name","source_record_id","conflict_type","message","blocking"),False),
"secret_lair_population_review_queue":PopulationContract("secret_lair_population_review_queue","Human-review queue with recommended resolution actions.",( "review_id",),("review_id","source_name","source_record_id","drop_name","variant_name","finish","review_reason","recommended_action","priority"),False),
"secret_lair_population_source_coverage":PopulationContract("secret_lair_population_source_coverage","Per-source catalog, match, registry, and price readiness.",( "source_name",),("source_name","catalog_rows","accepted_rows","review_rows","duplicate_rows","priced_records","completeness_score","source_status")),
"secret_lair_population_price_readiness":PopulationContract("secret_lair_population_price_readiness","Per-asset current-price, history, scoring, forecasting, and calibration readiness.",( "secret_lair_id",),("secret_lair_id","drop_name","variant_name","current_price_available","price_observation_count","distinct_price_months","source_count","history_span_days","ready_for_scoring","ready_for_forecasting","ready_for_calibration")),
"secret_lair_population_summary":PopulationContract("secret_lair_population_summary","Executive population and readiness summary.",( "snapshot_date",),("snapshot_date","catalog_rows","accepted_rows","review_rows","duplicate_rows","conflict_rows","registry_assets","priced_assets","scoring_ready_assets","forecast_ready_assets","calibration_ready_assets","apply_ready")),
}
def get_population_contract(name):
 try:return POPULATION_CONTRACTS[name]
 except KeyError as exc:raise KeyError(f"Unknown population contract: {name}") from exc
