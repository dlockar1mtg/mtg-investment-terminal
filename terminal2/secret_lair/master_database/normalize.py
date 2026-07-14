from __future__ import annotations
import hashlib,re

def text(value):return re.sub(r"\s+"," ",str(value or "")).strip()
def key(value):return re.sub(r"[^a-z0-9]+"," ",text(value).lower()).strip()
def stable_id(prefix,value):return f"{prefix}-{hashlib.sha1(key(value).encode()).hexdigest()[:14].upper()}"
def infer_finish(name):
 n=key(name)
 if "non foil" in n or "nonfoil" in n:return "nonfoil"
 if "foil" in n:return "foil"
 return "unknown"
def infer_family(name):
 n=key(name)
 if "commander deck" in n:return "commander deck"
 if "festival in a box" in n:return "festival in a box"
 if "bundle" in n:return "bundle"
 return "drop"
def canonical_name(name):
 n=text(name)
 n=re.sub(r"^secret lair(?: drop series)?[:\-]?\s*","",n,flags=re.I)
 n=re.sub(r"\s*\((?:foil|non-foil|nonfoil)\)\s*$","",n,flags=re.I)
 return text(n)
def variant_name(name):
 finish=infer_finish(name)
 if finish=="foil":return "Foil Edition"
 if finish=="nonfoil":return "Nonfoil Edition"
 return "Standard Edition"
def is_sealed_secret_lair(name):
 n=key(name)
 include=("secret lair" in n or any(x in n for x in ("foil edition","non foil edition","nonfoil edition","festival in a box")))
 exclude=any(x in n for x in ("single card","oversized","display commander","playmat","sleeves","deck box","token","booster"))
 return include and not exclude
