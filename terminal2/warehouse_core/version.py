from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import csv
@dataclass(frozen=True)
class VersionRecord:
    terminal_version:str; schema_version:str; recorded_at_utc:str; note:str=""
class VersionManager:
    def __init__(self,config): self.config=config; self.version_file=config.manifests_root/'version_log.csv'
    def append(self,note=""):
        self.config.manifests_root.mkdir(parents=True,exist_ok=True); r=VersionRecord(self.config.version,self.config.schema_version,datetime.now(timezone.utc).isoformat(),note); e=self.version_file.exists()
        with self.version_file.open('a',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=asdict(r).keys()); (not e) and w.writeheader(); w.writerow(asdict(r))
        return r
