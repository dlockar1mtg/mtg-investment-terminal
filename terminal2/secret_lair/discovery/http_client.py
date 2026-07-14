import gzip,hashlib,json,time
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
@dataclass(frozen=True)
class FetchResult: content:bytes; content_type:str; from_cache:bool; status_code:int; fetched_at_utc:str; cache_path:str
class CachedHttpClient:
    def __init__(self,cache_root): self.cache_root=Path(cache_root)
    def fetch(self,endpoint,timeout_seconds=30,max_retries=3,cache_ttl_hours=24.0):
        key=hashlib.sha256(endpoint.encode()).hexdigest(); payload=self.cache_root/f'{key}.bin'; meta=self.cache_root/f'{key}.json'
        if payload.exists() and meta.exists():
            try:
                m=json.loads(meta.read_text()); dt=datetime.fromisoformat(m['fetched_at_utc']); age=(datetime.now(timezone.utc)-dt).total_seconds()/3600
                if age<=cache_ttl_hours:return FetchResult(payload.read_bytes(),m['content_type'],True,int(m['status_code']),m['fetched_at_utc'],str(payload))
            except Exception:pass
        self.cache_root.mkdir(parents=True,exist_ok=True); err=None
        for i in range(max(1,max_retries)):
            try:
                req=Request(endpoint,headers={'User-Agent':'MTG-Investment-Terminal/2.7.1','Accept':'application/json, application/x-ndjson, text/html, */*','Accept-Encoding':'gzip'})
                with urlopen(req,timeout=timeout_seconds) as r:
                    data=r.read(); ctype=r.headers.get('Content-Type','application/octet-stream'); status=int(getattr(r,'status',200)); enc=r.headers.get('Content-Encoding','').lower()
                if enc=='gzip':data=gzip.decompress(data)
                stamp=datetime.now(timezone.utc).isoformat(); payload.write_bytes(data); meta.write_text(json.dumps({'content_type':ctype,'status_code':status,'fetched_at_utc':stamp}),encoding='utf-8')
                return FetchResult(data,ctype,False,status,stamp,str(payload))
            except Exception as exc:
                err=exc
                if i+1<max(1,max_retries):time.sleep(min(2**i,8))
        raise RuntimeError(f'Discovery fetch failed for {endpoint}: {err}')
