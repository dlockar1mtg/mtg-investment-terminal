import json,re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin
import pandas as pd
from terminal2.secret_lair.identifiers import normalize_text,slug
COLUMNS=('source_name','source_record_id','drop_name','variant_name','finish','product_family','release_date','sale_start_date','sale_end_date','msrp_usd','currency','franchise','ip_category','universes_beyond','artist_names','card_count','superdrop_name','event_type','availability_model','status','official_url','source_quality','discovered_at_utc','source_payload_type')
@dataclass(frozen=True)
class ParsedDiscovery: catalog:pd.DataFrame; raw_record_count:int
def parse_discovery_payload(parser_name,source_name,endpoint,content,fetched_at_utc,source_quality,query):
    parsers={'official_html':_html,'normalized_json':_normalized,'scryfall_cards':_scryfall,'mtgjson_sets':_mtgjson}
    try:f,n=parsers[parser_name](endpoint,content,query)
    except KeyError as exc:raise ValueError(f'Unsupported discovery parser: {parser_name}') from exc
    for c in COLUMNS:
        if c not in f.columns:f[c]=pd.NA
    f=f[list(COLUMNS)]; f['source_name']=source_name; f['source_quality']=float(source_quality); f['discovered_at_utc']=fetched_at_utc; f['source_payload_type']=parser_name
    for c in ('source_record_id','drop_name','variant_name','finish','product_family','franchise','ip_category','artist_names','superdrop_name','event_type','availability_model','status','official_url'):f[c]=f[c].fillna('').map(normalize_text)
    f['finish']=f['finish'].str.lower().replace({'non-foil':'nonfoil','non foil':'nonfoil'}); f['product_family']=f['product_family'].str.lower(); f['universes_beyond']=f['universes_beyond'].fillna(False).astype(bool); f['msrp_usd']=pd.to_numeric(f['msrp_usd'],errors='coerce'); f['card_count']=pd.to_numeric(f['card_count'],errors='coerce').astype('Int64')
    for c in ('release_date','sale_start_date','sale_end_date'):
        d=pd.to_datetime(f[c],errors='coerce'); f[c]=d.dt.date.astype('string').fillna('')
    f=f[f['source_record_id'].astype(str).str.strip().ne('')].drop_duplicates('source_record_id')
    return ParsedDiscovery(f.reset_index(drop=True),n)
def _html(endpoint,content,q):
    text=content.decode('utf-8',errors='replace'); pat=re.compile(r'href="(?P<href>[^"]*/product/(?P<id>\d+)/(?P<slug>[^"?#]+)[^"]*)"[^>]*>(?P<label>.*?)</a>',re.I|re.S); rows=[]; seen=set()
    for m in pat.finditer(text):
        if m['id'] in seen:continue
        seen.add(m['id']); label=normalize_text(re.sub(r'<[^>]+>',' ',unescape(m['label']))) or normalize_text(m['slug'].replace('-',' ')); finish='nonfoil' if 'nonfoil' in label.lower() or 'non-foil' in label.lower() else 'foil' if 'foil' in label.lower() else 'unknown'; ub=' x ' in label.lower()
        rows.append({'source_record_id':m['id'],'drop_name':label,'variant_name':'Foil Edition' if finish=='foil' else 'Nonfoil Edition' if finish=='nonfoil' else 'Standard Edition','finish':finish,'product_family':'bundle' if 'bundle' in label.lower() else 'drop','currency':q.get('currency','USD'),'franchise':label.split(' x ',1)[1] if ' x ' in label else 'Magic','ip_category':'Universes Beyond' if ub else 'Magic','universes_beyond':ub,'event_type':'standalone','availability_model':'unknown','status':q.get('status','unknown'),'official_url':urljoin(endpoint,m['href'])})
    return pd.DataFrame(rows),len(rows)
def _normalized(endpoint,content,q):
    obj=json.loads(content.decode()); records=obj if isinstance(obj,list) else obj.get(q.get('records_key','products'),obj.get('catalog',obj.get('items',obj.get('data',[])))) if isinstance(obj,dict) else []; mp=q.get('mapping',{}); rows=[]
    for r in records:
        if not isinstance(r,dict):continue
        v=lambda c,d='':r.get(mp.get(c,c),d)
        rows.append({'source_record_id':v('source_record_id'),'drop_name':v('drop_name'),'variant_name':v('variant_name','Standard Edition'),'finish':v('finish','unknown'),'product_family':v('product_family','drop'),'release_date':v('release_date'),'sale_start_date':v('sale_start_date'),'sale_end_date':v('sale_end_date'),'msrp_usd':v('msrp_usd'),'currency':v('currency','USD'),'franchise':v('franchise','Magic'),'ip_category':v('ip_category','Magic'),'universes_beyond':v('universes_beyond',False),'artist_names':v('artist_names'),'card_count':v('card_count'),'superdrop_name':v('superdrop_name'),'event_type':v('event_type','standalone'),'availability_model':v('availability_model','unknown'),'status':v('status','unknown'),'official_url':v('official_url')})
    return pd.DataFrame(rows),len(records)
def _scryfall(endpoint,content,q):
    text=content.decode(); cards=json.loads(text) if text.lstrip().startswith('[') else [json.loads(x) for x in text.splitlines() if x.strip()]; groups={}
    for c in cards:
        code=str(c.get('set','')).lower(); name=normalize_text(c.get('set_name')); typ=str(c.get('set_type','')).lower()
        if not(code=='sld' or code.startswith('sl') or 'secret lair' in name.lower() or typ=='memorabilia' and 'secret lair' in name.lower()):continue
        g=groups.setdefault(code or slug(name),{'name':name,'date':c.get('released_at',''),'artists':set(),'count':0}); a=normalize_text(c.get('artist')); g['artists'].add(a) if a else None; g['count']+=1
    rows=[{'source_record_id':k,'drop_name':g['name'] or k,'variant_name':'Card Metadata Set','finish':'unknown','product_family':'drop','release_date':g['date'],'currency':'USD','franchise':'Magic','ip_category':'Magic','universes_beyond':False,'artist_names':'|'.join(sorted(g['artists'])),'card_count':g['count'],'event_type':'metadata','availability_model':'unknown','status':'released'} for k,g in groups.items()]
    return pd.DataFrame(rows),len(cards)
def _mtgjson(endpoint,content,q):
    obj=json.loads(content.decode()); data=obj.get('data',obj) if isinstance(obj,dict) else {}; sets=data if isinstance(data,list) else list(data.values()) if isinstance(data,dict) else []; rows=[]
    for s in sets:
        if not isinstance(s,dict):continue
        code=normalize_text(s.get('code') or s.get('key')).lower(); name=normalize_text(s.get('name')); typ=normalize_text(s.get('type')).lower()
        if not(code=='sld' or code.startswith('sl') or 'secret lair' in name.lower() or typ=='memorabilia' and 'secret lair' in name.lower()):continue
        cards=s.get('cards') or []; artists=sorted({normalize_text(c.get('artist')) for c in cards if isinstance(c,dict) and normalize_text(c.get('artist'))}); rows.append({'source_record_id':code or slug(name),'drop_name':name,'variant_name':'Card Metadata Set','finish':'unknown','product_family':'drop','release_date':s.get('releaseDate') or s.get('release_date') or '','currency':'USD','franchise':'Magic','ip_category':'Magic','universes_beyond':False,'artist_names':'|'.join(artists),'card_count':len(cards),'event_type':'metadata','availability_model':'unknown','status':'released'})
    return pd.DataFrame(rows),len(sets)
