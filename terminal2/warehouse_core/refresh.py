from dataclasses import dataclass,asdict,replace
from datetime import datetime,timezone
import csv,os,socket,time,uuid
@dataclass(frozen=True)
class RefreshRun:
    refresh_id:str; terminal_version:str; schema_version:str; started_at_utc:str; finished_at_utc:str=""; duration_seconds:float=0.0; status:str="running"; datasets_published:int=0; warnings:int=0; errors:int=0; hostname:str=""; username:str=""; message:str=""
class RefreshManager:
    def __init__(self,config): self.config=config; self.log_file=config.logs_root/'refresh_log.csv'; self._run=None; self._started=None
    def start(self,message=""):
        if self._run and self._run.status=='running': raise RuntimeError('Refresh already active')
        n=datetime.now(timezone.utc); self._run=RefreshRun(n.strftime(self.config.refresh_id_format)+'-'+uuid.uuid4().hex[:8],self.config.version,self.config.schema_version,n.isoformat(),hostname=socket.gethostname(),username=os.getenv('USERNAME') or os.getenv('USER') or '',message=message); self._started=time.monotonic(); return self._run
    def finish(self,status='success',datasets_published=0,warnings=0,errors=0,message=''):
        if not self._run or self._started is None: raise RuntimeError('No active refresh')
        r=replace(self._run,finished_at_utc=datetime.now(timezone.utc).isoformat(),duration_seconds=round(time.monotonic()-self._started,3),status=status,datasets_published=int(datasets_published),warnings=int(warnings),errors=int(errors),message=message or self._run.message); self.config.logs_root.mkdir(parents=True,exist_ok=True); e=self.log_file.exists()
        with self.log_file.open('a',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=asdict(r).keys()); (not e) and w.writeheader(); w.writerow(asdict(r))
        self._run=r; return r
