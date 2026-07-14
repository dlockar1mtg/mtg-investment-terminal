from __future__ import annotations
import hashlib,json,time
from pathlib import Path
import requests
from .config import CACHE_ROOT,REQUEST_TIMEOUT
class CachedHttpClient:
 def __init__(self,cache_root=CACHE_ROOT):self.cache_root=Path(cache_root)
 def _path(self,url,suffix):
  return self.cache_root/f"{hashlib.sha256(url.encode()).hexdigest()}.{suffix}"
 def get_text(self,url,refresh=False):
  p=self._path(url,"txt");p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists() and not refresh:return p.read_text(encoding="utf-8")
  r=requests.get(url,timeout=REQUEST_TIMEOUT,headers={"User-Agent":"MTGInvestmentTerminal/2.9.7","Accept":"text/html,application/json"});r.raise_for_status();p.write_text(r.text,encoding="utf-8");return r.text
 def get_json(self,url,refresh=False):
  p=self._path(url,"json");p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists() and not refresh:return json.loads(p.read_text(encoding="utf-8"))
  r=requests.get(url,timeout=REQUEST_TIMEOUT,headers={"User-Agent":"MTGInvestmentTerminal/2.9.7","Accept":"application/json"});r.raise_for_status();p.write_text(r.text,encoding="utf-8");return r.json()
 def download_json(self,url,refresh=False):return self.get_json(url,refresh=refresh)
