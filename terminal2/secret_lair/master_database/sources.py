from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
import pandas as pd
from .config import OFFICIAL_URLS,SCRYFALL_BULK_INDEX_URL,TCGCSV_BASE_URL,REQUEST_DELAY_SECONDS
from .normalize import canonical_name,infer_finish,infer_family,is_sealed_secret_lair,key,text

def _results(payload):
 if isinstance(payload,dict):
  value=payload.get("results") or payload.get("data") or []
  return value if isinstance(value,list) else []
 return payload if isinstance(payload,list) else []

def official_records(client,refresh=False):
 rows=[]
 for url in OFFICIAL_URLS:
  html=client.get_text(url,refresh=refresh)
  seen=set()
  for match in re.finditer(r'href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',html,re.I|re.S):
   href=match.group(1);label=re.sub(r"<[^>]+>"," ",match.group(2));label=text(label)
   if not label or not is_sealed_secret_lair(label):continue
   if href.startswith("/"):href="https://secretlair.wizards.com"+href
   token=(label,href)
   if token in seen:continue
   seen.add(token);rows.append({"source_name":"official_secret_lair","source_record_id":href,"source_product_name":label,"source_url":href,"group_name":"","published_on":"","market_price":None,"low_price":None,"tcgplayer_product_id":"","tcgcsv_group_id":"","tcgcsv_category_id":"","raw_json":""})
  for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.I|re.S):
   try:payload=json.loads(block)
   except Exception:continue
   items=payload if isinstance(payload,list) else [payload]
   for item in items:
    if not isinstance(item,dict):continue
    name=text(item.get("name"));href=text(item.get("url"))
    if name and is_sealed_secret_lair(name):rows.append({"source_name":"official_secret_lair","source_record_id":href or name,"source_product_name":name,"source_url":href or url,"group_name":"","published_on":"","market_price":None,"low_price":None,"tcgplayer_product_id":"","tcgcsv_group_id":"","tcgcsv_category_id":"","raw_json":json.dumps(item)})
 return pd.DataFrame(rows).drop_duplicates(["source_name","source_record_id"]) if rows else pd.DataFrame()

def _magic_category(client,refresh=False):
 cats=pd.DataFrame(_results(client.get_json(f"{TCGCSV_BASE_URL}/categories",refresh=refresh)))
 for _,row in cats.iterrows():
  label=key(" ".join(str(row.get(c,"")) for c in ("name","displayName","seoCategoryName")))
  if "magic" in label:
   return int(row.get("categoryId") or row.get("category_id"))
 raise RuntimeError("Unable to detect the TCGCSV Magic category.")

def tcgcsv_records(client,refresh=False,max_groups=None):
 category=_magic_category(client,refresh=refresh)
 groups=pd.DataFrame(_results(client.get_json(f"{TCGCSV_BASE_URL}/{category}/groups",refresh=refresh)))
 if max_groups:groups=groups.head(int(max_groups))
 rows=[]
 for _,group in groups.iterrows():
  gid=group.get("groupId") or group.get("group_id")
  if pd.isna(gid):continue
  gname=text(group.get("name"));published=text(group.get("publishedOn") or group.get("published_on"))
  try:
   products=pd.DataFrame(_results(client.get_json(f"{TCGCSV_BASE_URL}/{category}/{int(gid)}/products",refresh=refresh)))
  except Exception:continue
  if products.empty:continue
  matches=products[products.get("name",pd.Series(index=products.index,dtype=str)).map(is_sealed_secret_lair)]
  if matches.empty:continue
  try:prices=pd.DataFrame(_results(client.get_json(f"{TCGCSV_BASE_URL}/{category}/{int(gid)}/prices",refresh=refresh)))
  except Exception:prices=pd.DataFrame()
  for _,product in matches.iterrows():
   pid=product.get("productId") or product.get("product_id")
   pr=pd.DataFrame()
   if not prices.empty:
    col="productId" if "productId" in prices else "product_id" if "product_id" in prices else None
    if col:pr=prices[prices[col].astype(str)==str(pid)]
   price=pr.iloc[0] if not pr.empty else {}
   rows.append({"source_name":"tcgcsv","source_record_id":str(pid),"source_product_name":text(product.get("name")),"source_url":f"https://www.tcgplayer.com/product/{pid}","group_name":gname,"published_on":published,"market_price":price.get("marketPrice") if hasattr(price,"get") else None,"low_price":price.get("lowPrice") if hasattr(price,"get") else None,"tcgplayer_product_id":str(pid),"tcgcsv_group_id":str(int(gid)),"tcgcsv_category_id":str(category),"raw_json":json.dumps(product.to_dict(),default=str)})
  time.sleep(REQUEST_DELAY_SECONDS)
 return pd.DataFrame(rows)

def scryfall_cards(client,refresh=False):
 index=client.get_json(SCRYFALL_BULK_INDEX_URL,refresh=refresh)
 items=index.get("data",[]) if isinstance(index,dict) else []
 target=next((x for x in items if x.get("type")=="default_cards"),None)
 if not target:return pd.DataFrame()
 cards=client.download_json(target["download_uri"],refresh=refresh)
 rows=[]
 for card in cards:
  if str(card.get("set","")).lower()!="sld":continue
  rows.append({"scryfall_id":card.get("id"),"card_name":card.get("name"),"released_at":card.get("released_at"),"artist":card.get("artist"),"collector_number":card.get("collector_number"),"finishes":"|".join(card.get("finishes") or []),"tcgplayer_id":card.get("tcgplayer_id"),"oracle_id":card.get("oracle_id"),"promo_types":"|".join(card.get("promo_types") or []),"source_url":card.get("scryfall_uri")})
 return pd.DataFrame(rows)
