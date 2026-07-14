import json
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
@dataclass(frozen=True)
class DiscoveryPayload: source_name:str; endpoint:str; content:bytes; content_type:str; from_cache:bool; records_received:int; fetched_at_utc:str
class HttpConnector:
    def load(self,s,client):
        r=client.fetch(str(s['endpoint']),int(s['timeout_seconds']),int(s['max_retries']),float(s['cache_ttl_hours']))
        return DiscoveryPayload(str(s['source_name']),str(s['endpoint']),r.content,r.content_type,r.from_cache,_count(r.content,r.content_type),r.fetched_at_utc)
class LocalConnector:
    def load(self,s,client):
        p=Path(str(s['endpoint'])).expanduser(); p=p if p.is_absolute() else Path.cwd()/p; data=p.read_bytes(); c=_ctype(p)
        return DiscoveryPayload(str(s['source_name']),str(p),data,c,False,_count(data,c),datetime.now(timezone.utc).isoformat())
def _ctype(p):
    return 'application/x-ndjson' if p.suffix.lower() in {'.jsonl','.ndjson'} else 'application/json' if p.suffix.lower()=='.json' else 'text/html' if p.suffix.lower() in {'.html','.htm'} else 'application/octet-stream'
def _count(data,ctype):
    try:
        text=data.decode(); low=ctype.lower()
        if 'ndjson' in low:return sum(bool(x.strip()) for x in text.splitlines())
        if 'json' in low:
            obj=json.loads(text)
            if isinstance(obj,list):return len(obj)
            if isinstance(obj,dict):
                for k in ('data','products','items','catalog'):
                    if isinstance(obj.get(k),list):return len(obj[k])
            return 1
        return len(text.splitlines())
    except Exception:return 0
def get_discovery_connector(kind):
    if kind.startswith('http'):return HttpConnector()
    if kind.startswith('local'):return LocalConnector()
    raise ValueError(f'Unsupported discovery connector: {kind}')
