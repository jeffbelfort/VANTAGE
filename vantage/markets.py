"""Read-only market discovery projections and strictly non-financial UI preferences."""
import math,statistics,json
from collections import defaultdict,Counter
from datetime import datetime,timedelta
from functools import lru_cache
from pathlib import Path

REGIONS=['United States','United Kingdom','Europe','Asia-Pacific','Other supported markets']
EUROPE={'DE','FR','NL','CH','IE','ES','IT','SE','NO','DK','FI','BE','AT','PT','PL'}
APAC={'KR','JP','CN','HK','TW','SG','AU','NZ','IN'}
NUMERIC_FILTERS={'min_price_gbp':'price_gbp','max_price_gbp':'price_gbp','min_change_1d':'change_1d','max_change_1d':'change_1d','min_change_1w':'change_1w','max_change_1w':'change_1w','min_market_cap_gbp':'market_cap_gbp','max_market_cap_gbp':'market_cap_gbp','min_volume':'volume_1d','min_liquidity':'liquidity','min_volatility':'volatility','max_volatility':'volatility','min_yield':'dividend_yield','max_pe':'pe'}
TEXT_FILTERS={'query','region','country','exchange','sector','industry','universe','list','news','recommendation','sort','direction'}
SORT_FIELDS={'symbol','name','price_gbp','change_1d','change_1w','volume_1d','liquidity','volatility','market_cap_gbp','pe','dividend_yield','news_count','revision','recent'}

def number(value):
 try:
  n=float(value)
  return n if math.isfinite(n) else None
 except (TypeError,ValueError):return None
@lru_cache(maxsize=1)
def classifications():return json.loads((Path(__file__).resolve().parent.parent/'assets/market-classifications.json').read_text())['records']
def classification(record,instrument=None):
 mapped=classifications().get(record['symbol'],{});instrument=instrument or {}
 return {'sector':record.get('sector') or mapped.get('sector') or ('Unclassified' if instrument.get('sector_basis') else instrument.get('sector')) or 'Unclassified',
 'industry':record.get('industry') or mapped.get('industry') or 'Unclassified',
 'basis':('Catalogue metadata' if record.get('industry') else mapped.get('basis','Classification unavailable')),'issuer_source':mapped.get('issuer_source')}
def region(country):return 'United States' if country=='US' else 'United Kingdom' if country=='GB' else 'Europe' if country in EUROPE else 'Asia-Pacific' if country in APAC else 'Other supported markets'
def recorded_history(instrument,tick):
 return sorted([b for b in instrument.get('history',[]) if number(b.get('c')) is not None and number(b.get('t')) is not None and b['t']<=tick],key=lambda b:b['t'])
def observed_history(instrument,tick):return [b for b in recorded_history(instrument,tick) if b['t']>=0 and b.get('quality')!='MODEL']
def change(instrument,tick,hours):
 price=number(instrument.get('price'));history=observed_history(instrument,tick);cutoff=tick-hours
 if not price or cutoff<0:return None
 old=[b for b in history if b['t']<=cutoff]
 base=number(old[-1]['c']) if old else number(history[0].get('o')) if history and history[0]['t']==cutoff+1 else None
 return (price/base-1)*100 if base and base>0 else None

def project_market(world,catalogue,volumes=None,trade_stats=None):
 """No state mutation, security activation, reference refresh or future information."""
 tick=world['tick'];volumes=volumes or {};trade_stats=trade_stats or {};identities={r['symbol']:r for r in catalogue}
 for symbol,i in world['instruments'].items():identities.setdefault(symbol,{'symbol':symbol,'name':i['name'],'exchange':i.get('exchange','Local simulation'),'currency':i.get('currency','GBP'),'market_country':i.get('market_country')})
 events=defaultdict(list)
 for event in world.get('events',[]):
  if event.get('published') and event.get('publish_tick',tick+1)<=tick:events[event['symbol']].append(event)
 news=defaultdict(list)
 for item in world.get('news',[]):
  if item.get('symbol') and item.get('time','')<=world['time']:news[item['symbol']].append(item)
 reports=defaultdict(dict)
 for report in world.get('stock_research',[]):
  if report.get('tick',tick+1)>tick:continue
  reports[report['symbol']][report['entity']]={'recommendation':report['recommendation'],'analyst_name':report['analyst_name'],'tick':report['tick'],'stale':bool(report.get('stale'))}
 rows=[]
 for symbol,identity in identities.items():
  ins=world['instruments'].get(symbol);active=ins is not None;ins=ins or {};country=identity.get('market_country') or identity.get('country');c=classification(identity,ins);price=number(ins.get('price'));fx=number(world.get('fx',{}).get(identity.get('currency'),{}).get('gbp_per_unit'));fx=1 if identity.get('currency')=='GBP' else fx
  f=ins.get('fundamentals',{});shares=number(f.get('shares'));profit=number(f.get('profit'));dividend=number(f.get('annual_dividend_per_share'));eps=profit/shares if profit is not None and shares and shares>0 else None;pe=price/eps if price and eps and eps>0 else None
  history=observed_history(ins,tick);returns=[math.log(float(b['c'])/float(a['c'])) for a,b in zip(history,history[1:]) if float(a['c'])>0 and float(b['c'])>0 and b['t']==a['t']+1];vol=statistics.pstdev(returns[-168:])*math.sqrt(8760)*100 if len(returns)>=2 else None
  recent=[e for e in events[symbol] if tick-e['publish_tick']<=168];revisions=[e for e in events[symbol] if e['kind'] in ('earnings','guidance')];latest_revision=max(recent,key=lambda e:e['publish_tick'],default=None)
  revision_recent=[e for e in recent if e['kind'] in ('earnings','guidance')];latest_revision=max(revision_recent,key=lambda e:e['publish_tick'],default=None)
  levels=ins.get('depth',[]);liquidity=sum((number(r.get('bid_qty',r.get('qty',0))) or 0)+(number(r.get('ask_qty',r.get('qty',0))) or 0) for r in levels) if active else None
  rows.append({'symbol':symbol,'name':identity.get('name',ins.get('name',symbol)),'security_id':identity.get('security_id'),'exchange':identity.get('exchange'),'country':country,'region':region(country),'currency':identity.get('currency',ins.get('currency','GBP')),
   'sector':c['sector'],'industry':c['industry'],'classification_basis':c['basis'],'issuer_source':c['issuer_source'],'active':active,'status':ins.get('status','CATALOGUE ONLY'),'price':price,'price_gbp':price*fx if price is not None and fx else None,'change_1d':change(ins,tick,24) if active else None,'change_1w':change(ins,tick,168) if active else None,
   'market_cap_gbp':price*shares*fx if price is not None and shares is not None and shares>0 and fx else None,'pe':pe,'dividend_yield':dividend/price*100 if dividend is not None and price else None,'fundamentals_quality':ins.get('fundamentals_quality','Unavailable'),
   'best_bid':number(next((r['bid'] for r in levels if r.get('bid') is not None),None)),'best_ask':number(next((r['ask'] for r in levels if r.get('ask') is not None),None)),'last_trade_24h':trade_stats.get(symbol,{}).get('last_trade'),'trades_24h':trade_stats.get(symbol,{}).get('trades',0) if active else None,
   'volume_1d':volumes.get(symbol,0) if active else None,'liquidity':liquidity,'volatility':vol,'model_volatility':number(ins.get('vol')),'execution_model':'Matched book' if active and world.get('microstructure_enabled') and symbol in world.get('market_symbols',[]) else 'Bounded model' if active else 'Reference required',
   'news_positive':any(e['severity']>0 for e in recent),'news_negative':any(e['severity']<0 for e in recent),'news_count':len(recent),'revision':latest_revision['severity'] if latest_revision else None,'revisions':revisions,'news':news[symbol][:10],'research':reports[symbol],
   'options_available':active and ins.get('status')=='OPEN','history_hours':(history[-1]['t']-history[0]['t']+1) if history else 0})
 return {'rows':rows,'regions':[{'name':r,'active':sum(x['active'] and x['region']==r for x in rows),'catalogue':sum(x['region']==r for x in rows)} for r in REGIONS],
 'facets':{key:sorted({r[key] for r in rows if r[key]}) for key in ['country','exchange','sector','industry']},'as_of':world['time'],'tick':tick,'volume_basis':'Recorded execution quantity over 24 simulation hours; paired matched-book legs counted once. Model candle volumes are excluded.','history_limit':'Only retained simulation history is available; no reference feed or long-range candles are fabricated.'}

def normalize_filters(values):
 if not isinstance(values,dict):raise ValueError('Market filters must be an object')
 if set(values)-TEXT_FILTERS-set(NUMERIC_FILTERS):raise ValueError('Unknown market filter')
 result={}
 for k,v in values.items():
  if v is None or v=='':continue
  if k in NUMERIC_FILTERS:
   if number(v) is None:raise ValueError('Market range must be finite: '+k)
   result[k]=str(v)
  else:
   if not isinstance(v,str) or len(v)>160:raise ValueError('Invalid market filter: '+k)
   result[k]=v
 if result.get('sort','symbol') not in SORT_FIELDS:raise ValueError('Unsupported market sort')
 if result.get('direction','asc') not in ('asc','desc'):raise ValueError('Unsupported sort direction')
 return result

def screen_rows(rows,filters,account='',watchlist=(),recent=()):
 f=normalize_filters(filters);q=f.get('query','').strip().casefold();result=[]
 for row in rows:
  if q and not all(t in (row['symbol']+' '+row['name']).casefold() for t in q.split()):continue
  if any(f.get(k) and f[k]!=row.get(k) for k in ('region','country','exchange','sector','industry')):continue
  if f.get('universe','active')=='active' and not row['active']:continue
  if f.get('universe')=='catalogue' and row['active']:continue
  kind=f.get('list','all')
  if kind=='watchlist' and row['symbol'] not in watchlist:continue
  if kind=='recent' and row['symbol'] not in recent:continue
  if kind=='gainers' and not (row['change_1d'] is not None and row['change_1d']>0):continue
  if kind=='losers' and not (row['change_1d'] is not None and row['change_1d']<0):continue
  if kind=='active' and not (row['volume_1d'] is not None and row['volume_1d']>0):continue
  if kind=='volatile' and row['volatility'] is None:continue
  if kind=='news' and not row['news_count']:continue
  if kind=='revision_up' and not (row['revision'] is not None and row['revision']>0):continue
  if kind=='revision_down' and not (row['revision'] is not None and row['revision']<0):continue
  if f.get('news')=='positive' and not row['news_positive']:continue
  if f.get('news')=='negative' and not row['news_negative']:continue
  research=row['research'].get(account)
  if f.get('recommendation') and (not research or research['stale'] or research['recommendation']!=f['recommendation']):continue
  if any(row[field] is None or (row[field]<float(f[key]) if key.startswith('min_') else row[field]>float(f[key])) for key,field in NUMERIC_FILTERS.items() if key in f):continue
  result.append(row)
 key=f.get('sort','symbol');direction=-1 if f.get('direction')=='desc' else 1
 from functools import cmp_to_key
 def compare(a,b):
  x=(recent.index(a['symbol']) if a['symbol'] in recent else None) if key=='recent' else a.get(key);y=(recent.index(b['symbol']) if b['symbol'] in recent else None) if key=='recent' else b.get(key)
  if x is None or y is None:return (x is None)-(y is None) or (a['symbol']>b['symbol'])-(a['symbol']<b['symbol'])
  return direction*((x>y)-(x<y)) or (a['symbol']>b['symbol'])-(a['symbol']<b['symbol'])
 return sorted(result,key=cmp_to_key(compare))

def execution_stats(db,world):
 end=datetime.fromisoformat(world['time']);start=(end-timedelta(hours=24)).isoformat()
 # Old bounded-model executions remain single legs after coverage expands.
 rows=db.execute("select data from executions where world=? and json_extract(data,'$.time')>? and json_extract(data,'$.time')<=?",(world['id'],start,world['time']))
 totals={}
 for (encoded,) in rows:
  fill=json.loads(encoded);symbol=fill['symbol']
  paired=fill.get('paired')
  if paired is None:
   since=world.get('matched_since',{}).get(symbol)
   paired=world.get('microstructure_enabled') and symbol in world.get('market_symbols',[]) and (since is None or fill['time']>since)
  divisor=2 if paired else 1
  item=totals.setdefault(symbol,{'volume':0,'trades':0,'last_trade':fill['time']})
  item['volume']+=float(fill['qty'])/divisor;item['trades']+=1/divisor;item['last_trade']=max(item['last_trade'],fill['time'])
 return totals

def execution_volumes(db,world):return {symbol:stats['volume'] for symbol,stats in execution_stats(db,world).items()}
