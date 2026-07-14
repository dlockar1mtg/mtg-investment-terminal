from __future__ import annotations
from dataclasses import dataclass
from terminal2.warehouse_core import DatasetDefinition

@dataclass(frozen=True)
class AcquisitionContract:
    name: str
    description: str
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    snapshot: bool = True
    version: str = "1"
    def definition(self) -> DatasetDefinition:
        return DatasetDefinition(
            name=self.name, category="secret_lair", module="terminal2.secret_lair.acquisition",
            description=self.description, primary_key=self.primary_key,
            expected_columns=self.required_columns, required=True,
            snapshot=self.snapshot, version=self.version,
        )

ACQUISITION_CONTRACTS = {
 "secret_lair_acquisition_sources": AcquisitionContract(
   "secret_lair_acquisition_sources", "Configured acquisition sources and connector health.",
   ("source_name",), ("source_name","connector_type","location","enabled","priority","source_quality","status"), False),
 "secret_lair_acquisition_catalog": AcquisitionContract(
   "secret_lair_acquisition_catalog", "Canonical normalized catalog records collected from enabled sources.",
   ("source_name","source_record_id"), ("source_name","source_record_id","drop_name","variant_name","finish","acquired_at_utc")),
 "secret_lair_acquisition_prices": AcquisitionContract(
   "secret_lair_acquisition_prices", "Canonical normalized source price observations collected during acquisition.",
   ("source_name","source_record_id","observation_date"), ("source_name","source_record_id","observation_date","market_price","acquired_at_utc")),
 "secret_lair_acquisition_conflicts": AcquisitionContract(
   "secret_lair_acquisition_conflicts", "Cross-source identity and metadata conflicts requiring review.",
   ("conflict_id",), ("conflict_id","conflict_type","source_name","source_record_id","field_name","message"), False),
 "secret_lair_acquisition_coverage": AcquisitionContract(
   "secret_lair_acquisition_coverage", "Per-source acquisition completeness and usability metrics.",
   ("source_name",), ("source_name","catalog_rows","price_rows","usable_catalog_rows","usable_price_rows","completeness_score","status")),
 "secret_lair_acquisition_run_log": AcquisitionContract(
   "secret_lair_acquisition_run_log", "One row per acquisition run and source connector execution.",
   ("run_id","source_name"), ("run_id","source_name","started_at_utc","completed_at_utc","status","catalog_rows","price_rows"), False),
 "secret_lair_acquisition_summary": AcquisitionContract(
   "secret_lair_acquisition_summary", "Executive source-acquisition readiness summary.",
   ("snapshot_date",), ("snapshot_date","enabled_sources","successful_sources","catalog_rows","price_rows","conflict_rows","backfill_ready")),
}

def get_acquisition_contract(name: str) -> AcquisitionContract:
    try: return ACQUISITION_CONTRACTS[name]
    except KeyError as exc: raise KeyError(f"Unknown Secret Lair acquisition contract: {name}") from exc
