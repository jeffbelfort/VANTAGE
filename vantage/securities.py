"""Source-attributed, exchange-qualified securities and independent reference cache."""
import copy,hashlib,json,math,random,os,time
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone,timedelta
from urllib.request import Request,urlopen
from urllib.parse import quote
ASSETS=Path(__file__).resolve().parent.parent/'assets'

def catalogue():return json.loads((ASSETS/'securities.json').read_text())['records']
def find_security(symbol):
 matches=[r for r in catalogue() if symbol in (r['symbol'],r['security_id'])]
 if len(matches)!=1:raise ValueError('Unknown or ambiguous security; use exchange-qualified identifier')
 return matches[0]
def fx_snapshot():
 data=json.loads((ASSETS/'fx-reference-snapshot.json').read_text());gbp=D(data['currency_per_eur']['GBP'])
 return {c:dict(gbp_per_unit=str(gbp/D(rate)),reference=dict(data,date=data['date']),quality='MODEL FX',source='World starting snapshot; ECB baseline') for c,rate in data['currency_per_eur'].items()}

class EquityReferences:
 def __init__(self,path):
  self.path=Path(path);self.quotes={q['symbol']:q for q in json.loads((ASSETS/'verified-equity-references.json').read_text())['quotes']};self.error=None;self.attempts={}
  try:
   if self.path.is_file() and self.path.stat().st_size<16*1024*1024:self.quotes.update(json.loads(self.path.read_text()))
  except (OSError,ValueError):self.error='Equity reference cache unreadable; bundled snapshot retained'
 def save(self):
  self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
  encoded=json.dumps(self.quotes)
  if len(encoded.encode())>16*1024*1024:raise ValueError('Reference cache exceeds 16 MB; retain fewer historical series')
  with open(temp,'w') as f:f.write(encoded);f.flush();os.fsync(f.fileno())
  os.replace(temp,self.path)
 def refresh(self,symbol,opener=urlopen):
  security=find_security(symbol);symbol=security['symbol'];now=time.monotonic()
  if symbol in self.attempts and now-self.attempts[symbol]<900:return {'available':symbol in self.quotes,'message':'Reference refresh limited to one attempt per symbol every 15 minutes'}
  self.attempts[symbol]=now
  url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?interval=1d&range=3mo'
  try:
   request=Request(url,headers={'User-Agent':'VANTAGE-local-research/0.2'})
   with opener(request,timeout=8) as response:
    payload=response.read(2*1024*1024+1)
    if len(payload)>2*1024*1024:raise ValueError('Reference payload exceeds 2 MB')
   data=json.loads(payload);result=data['chart']['result'][0];meta=result['meta'];values=result['indicators']['quote'][0];bars=[];currency=meta['currency']
   scale=D('.01') if currency in ('GBp','GBX') else D(1);currency='GBP' if scale!=1 else currency
   if currency!=security['currency']:raise ValueError('Provider listing currency differs from catalogue; import requires review')
   for i,timestamp in enumerate(result['timestamp']):
    if any(values[k][i] is None for k in ('open','high','low','close')):continue
    bar={k:str(D(str(values[field][i]))*scale) for k,field in [('o','open'),('h','high'),('l','low'),('c','close')]};bar.update(v=int(values.get('volume',[0]*len(result['timestamp']))[i] or 0),timestamp=datetime.fromtimestamp(timestamp,timezone.utc).isoformat());
    points=[D(bar[k]) for k in ('o','h','l','c')]
    if any(not x.is_finite() or x<=0 for x in points) or D(bar['h'])<max(points) or D(bar['l'])>min(points) or bar['v']<0:raise ValueError('Invalid OHLCV bar')
    bars.append(bar)
   if not bars:raise ValueError('Provider supplied no complete OHLC bars')
   q=dict(symbol=symbol,price=bars[-1]['c'],currency=currency,timestamp=bars[-1]['timestamp'],date_precision='DAILY BAR',observed_at=datetime.now(timezone.utc).isoformat(),source='Yahoo Finance public chart endpoint',source_url=url,quality='HISTORICAL',ohlcv=bars[-1],history=bars,corporate_actions=result.get('events',{}),adjustment='OHLC per provider; adjusted closes retained separately when supplied',adjusted_closes=result['indicators'].get('adjclose'),verification='FETCHED FROM PROVIDER ENDPOINT')
   self.validate(q);self.quotes[symbol]=q;self.error=None;self.save();return {'available':True,'message':'Genuine reference cached. Existing execution prices remain unchanged.'}
  except Exception as exc:
   self.error=f'Reference unavailable ({type(exc).__name__}); cached data retained. No execution price was replaced.';return {'available':symbol in self.quotes,'message':self.error}
 @staticmethod
 def validate(q):
  price=D(str(q['price']))
  if not price.is_finite() or price<=0:raise ValueError('Invalid reference price')
  if not q.get('source_url') or not q.get('observed_at'):raise ValueError('Reference attribution and observation time required')
  if q.get('timestamp'):
   stamp=datetime.fromisoformat(q['timestamp'])
   if stamp.tzinfo is None or stamp>datetime.now(timezone.utc)+timedelta(days=1):raise ValueError('Invalid reference timestamp')
 def import_quote(self,p):
  security=find_security(p['symbol']);q=dict(p);q['symbol']=security['symbol']
  if q.get('currency')!=security['currency']:raise ValueError('Currency must match the listing; convert GBX to GBP explicitly')
  self.validate(q);q.update(verification='USER IMPORT — ORIGIN UNVERIFIED',quality='HISTORICAL',source='User-supplied reference: '+str(q.get('source','unverified')));self.quotes[q['symbol']]=q;self.save();return {'available':True}
 def snapshot(self):
  out=[]
  for q in self.quotes.values():
   q=copy.deepcopy(q);timestamp=q.get('timestamp')
   q['quality']='STALE' if timestamp and datetime.now(timezone.utc)-datetime.fromisoformat(timestamp)>timedelta(days=4) else 'HISTORICAL'
   if timestamp is None:q['date_precision']='PROVIDER TIMESTAMP UNAVAILABLE'
   q.pop('history',None);out.append(q)
  return {'quotes':out,'error':self.error,'notice':'Archived reference library. Execution prices are a separate persistent market.'}

def execution_security(security,reference,world):
 EquityReferences.validate(reference);symbol=security['symbol'];baseline=D(reference['price']);seed=int(hashlib.sha256((str(world['seed'])+security['security_id']).encode()).hexdigest()[:12],16);rng=random.Random(seed);vol=.25
 # This is explicitly model prehistory, never substituted for provider OHLC.
 values=[float(baseline)];hist=[]
 for i in range(100):values.append(values[-1]*math.exp(rng.gauss(0,vol/math.sqrt(8760))))
 scale=float(baseline)/values[-1]
 for i in range(100):
  o=values[i]*scale;c=values[i+1]*scale;hist.append(dict(t=world['tick']-100+i,o=round(o,4),h=round(max(o,c)*1.001,4),l=round(min(o,c)*.999,4),c=round(c,4),v=0,quality='MODEL'))
 sector='Unclassified';known_finance={'JPM','GS','MS','BAC','C','WFC','BLK','HSBA.L','BARC.L','LLOY.L','NWG.L','STAN.L','UBS','DB','BRK-B'};known_tech={'NVDA','AAPL','MSFT','GOOGL','GOOG','AMZN','META','TSLA','AMD','INTC','AVGO','PLTR','TSM','005930.KS','ASML','SAP'}
 if symbol in known_finance:sector='Financials'
 elif symbol in known_tech:sector='Technology'
 elif symbol in {'BP.L','SHEL.L','XOM','CVX'}:sector='Energy'
 elif symbol in {'RR.L','BA','LMT'}:sector='Industrials'
 elif symbol in {'AZN.L','AZN','JNJ','LLY','MRK'}:sector='Healthcare'
 ins=copy.deepcopy(security);ins.update(price=str(baseline),previous=str(baseline),vol=vol,sector=sector,sector_basis='Model risk grouping; reference industry unknown',source='VANTAGE execution market',quality='SIMULATED',delay='Independent market session',status='OPEN',timestamp=world['time'],tick_size='1' if security['currency']=='KRW' else '.0001' if security['currency']=='GBP' else '.01',liquidity=100000,borrow_available=2000000,model_daily_volume=20000000,liquidity_source='MODEL ASSUMPTION; not exchange depth',history=hist,reference=copy.deepcopy(reference),fundamentals=dict(revenue=None,profit=None,debt=None,shares=None),fundamentals_quality='UNAVAILABLE',expected_cashflows=1.0)
 return ins

class SecuritiesMixin:
 def install_real_securities(self,legacy=False):
  w=self.state
  if w.get('catalogue_version',0)>=1:return
  w['fx']=fx_snapshot();initial={}
  if not legacy:w['instruments']={}
  else:
   for ins in w['instruments'].values():ins['legacy']=True
  for security in catalogue():
   ref=self.equity_references.quotes.get(security['symbol'])
   if not ref:continue
   if security['currency'] not in w['fx']:continue
   if security['symbol'] in w['instruments']:continue
   w['instruments'][security['symbol']]=execution_security(security,ref,w);initial[security['security_id']]=copy.deepcopy(ref)
  w['catalogue_version']=1;w['market_starting_snapshot']=initial;w['market_starting_snapshot_hash']=hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest()
  if legacy:self.audit('real_security_catalogue_added',{'new_securities':len(initial),'legacy_positions_preserved':True,'reference_dates_independent_of_simulation_clock':True})
 def activate_security(self,p):
  security=find_security(p['symbol']);symbol=security['symbol']
  if symbol in self.state['instruments']:return {'symbol':symbol,'unchanged':True}
  ref=self.equity_references.quotes.get(symbol)
  if not ref:raise ValueError('No genuine reference cached for '+symbol+'. Refresh or import a sourced reference in Markets first.')
  self.fx_rate(security['currency']);self.state['instruments'][symbol]=execution_security(security,ref,self.state);self.audit('security_activated',{'symbol':symbol,'reference':ref});return {'symbol':symbol}
