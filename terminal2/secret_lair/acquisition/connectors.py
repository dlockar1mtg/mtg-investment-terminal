from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

@dataclass(frozen=True)
class ConnectorResult:
    catalog: pd.DataFrame
    prices: pd.DataFrame
    raw_rows: int

class SourceConnector:
    def load(self, location: Path) -> ConnectorResult: raise NotImplementedError

class CsvConnector(SourceConnector):
    def load(self, location: Path) -> ConnectorResult:
        frame=pd.read_csv(location,dtype=str).fillna("")
        kind=frame.get("record_type",pd.Series(["catalog"]*len(frame))).astype(str).str.lower()
        return ConnectorResult(frame.loc[kind.ne("price")].copy(),frame.loc[kind.eq("price")].copy(),len(frame))

class JsonConnector(SourceConnector):
    def load(self, location: Path) -> ConnectorResult:
        payload=json.loads(location.read_text(encoding="utf-8"))
        if isinstance(payload,list): catalog=pd.DataFrame(payload); prices=pd.DataFrame()
        elif isinstance(payload,dict):
            catalog=pd.DataFrame(payload.get("catalog",[])); prices=pd.DataFrame(payload.get("prices",[]))
        else: raise ValueError("JSON source must contain an object or list.")
        return ConnectorResult(catalog.fillna(""),prices.fillna(""),len(catalog)+len(prices))

class DirectoryConnector(SourceConnector):
    def load(self, location: Path) -> ConnectorResult:
        catalogs=[]; prices=[]; raw=0
        for path in sorted(location.glob("*")):
            if path.suffix.lower() not in {".csv",".json"}: continue
            connector=JsonConnector() if path.suffix.lower()==".json" else CsvConnector()
            result=connector.load(path); catalogs.append(result.catalog); prices.append(result.prices); raw+=result.raw_rows
        return ConnectorResult(pd.concat(catalogs,ignore_index=True) if catalogs else pd.DataFrame(),pd.concat(prices,ignore_index=True) if prices else pd.DataFrame(),raw)

def get_connector(connector_type: str) -> SourceConnector:
    types={"csv":CsvConnector,"json":JsonConnector,"directory":DirectoryConnector}
    try: return types[connector_type]()
    except KeyError as exc: raise ValueError(f"Unsupported connector type: {connector_type}") from exc
