"""Independent reference data. Never feeds fictional execution or overwrites simulation prices."""
from __future__ import annotations
import json,os,threading,time
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from urllib.request import Request,urlopen
from xml.etree import ElementTree as ET
ECB_URL='https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
MAX_BYTES=2*1024*1024

class ReferenceStore:
 def __init__(self,path):
  self.path=Path(path);self.lock=threading.RLock();self.last_attempt=0;self.error=None;self.cache={'quotes':[],'fetched':None,'provider':'ECB'}
  try:
   if self.path.is_file() and self.path.stat().st_size<=MAX_BYTES:self.cache=json.loads(self.path.read_text())
  except (OSError,ValueError):self.error='Reference cache could not be read; simulation remains available'
 @staticmethod
 def parse_ecb(payload):
  if isinstance(payload,str):payload=payload.encode()
  if len(payload)>MAX_BYTES or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():raise ValueError('Unsupported or oversized XML')
  try:root=ET.fromstring(payload)
  except ET.ParseError:raise ValueError('Invalid ECB XML')
  namespace='{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}'
  daily=root.find('.//'+namespace+'Cube[@time]')
  if daily is None:raise ValueError('ECB rate date is missing')
  day=datetime.strptime(daily.attrib['time'],'%Y-%m-%d').replace(tzinfo=timezone.utc)
  if day>datetime.now(timezone.utc)+timedelta(days=1):raise ValueError('Future reference date rejected')
  quotes=[]
  for row in daily:
   currency=row.attrib.get('currency','');rate=row.attrib.get('rate','')
   if len(currency)!=3 or not currency.isalpha() or not currency.isupper():raise ValueError('Invalid currency code')
   try:value=Decimal(rate)
   except Exception:raise ValueError('Invalid reference rate')
   if not value.is_finite() or value<=0:raise ValueError('Invalid reference rate')
   quotes.append(dict(instrument='EUR/'+currency,exchange='ECB reference fixing',currency=currency,price=str(value),timestamp=day.isoformat(),date_precision='DAY',source='European Central Bank',source_url=ECB_URL,status='REFERENCE ONLY',delay='Daily reference, not an executable quote',quality='HISTORICAL'))
  if not quotes or len({q['instrument'] for q in quotes})!=len(quotes):raise ValueError('Missing or duplicate ECB rates')
  return quotes
 def import_xml(self,payload,verified=False):
  quotes=self.parse_ecb(payload)
  for quote in quotes:
   quote['verification']='FETCHED FROM OFFICIAL ENDPOINT' if verified else 'USER IMPORT · ORIGIN UNVERIFIED'
   if not verified:quote['source']='User-supplied ECB-format XML (unverified origin)'
  with self.lock:
   self.cache={'quotes':quotes,'fetched':datetime.now(timezone.utc).isoformat(),'provider':'ECB'};self.error=None;self.save()
  return {'count':len(quotes),'source':'ECB','message':'Reference rates imported; simulated trading prices unchanged'}
 def save(self):
  self.path.parent.mkdir(parents=True,exist_ok=True);temporary=self.path.with_suffix('.tmp')
  with open(temporary,'w') as f:json.dump(self.cache,f);f.flush();os.fsync(f.fileno())
  os.replace(temporary,self.path)
 def refresh(self,opener=urlopen):
  with self.lock:
   if time.monotonic()-self.last_attempt<1800 and self.last_attempt:
    return {'cached':True,'message':'Provider cooldown: at most one attempt every 30 minutes'}
   self.last_attempt=time.monotonic()
   try:
    req=Request(ECB_URL,headers={'User-Agent':'VANTAGE-local/0.1 (reference data; no execution)'})
    with opener(req,timeout=5) as response:
     if not response.geturl().startswith('https://www.ecb.europa.eu/'):raise ValueError('Unexpected provider redirect')
     payload=response.read(MAX_BYTES+1)
    return self.import_xml(payload,verified=True)
   except Exception as exc:
    self.error=f'ECB unavailable: {type(exc).__name__}. Cached references retained; simulated markets remain available.'
    return {'available':False,'message':self.error}
 def snapshot(self):
  with self.lock:
   quotes=[]
   for q in self.cache.get('quotes',[]):
    q=dict(q)
    try:
     if datetime.now(timezone.utc)-datetime.fromisoformat(q['timestamp'])>timedelta(days=4):q['quality']='STALE'
    except (KeyError,ValueError):continue
    quotes.append(q)
   return {'provider':'ECB','quotes':quotes,'fetched':self.cache.get('fetched'),'error':self.error,'status':'AVAILABLE' if quotes else 'UNAVAILABLE','endpoint':ECB_URL,'note':'Daily official reference rates; never used as simulated trade prices.'}
