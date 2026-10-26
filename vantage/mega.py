"""Institutional execution controls and stock-specific model profiles.
These are explicit fictional scenario assumptions, not live market statistics.
"""
import copy,hashlib,math
from decimal import Decimal as D, InvalidOperation
from datetime import datetime,timedelta
from .integrity import amt

# ADV, free float, full quoted spread bps; fictional calibration, not real company data.
CALIBRATION={'NVDA':(80000000,20000000000,4),'MSFT':(35000000,7000000000,5),'AAPL':(60000000,15000000000,5),'AMZN':(50000000,9000000000,6),'GOOGL':(30000000,11000000000,6),'JPM':(12000000,2800000000,7),'WELL':(8000000,600000000,12),'LMT':(1500000,250000000,15),'RR.L':(80000000,8000000000,10),'HSBA.L':(35000000,17000000000,8)}

class MegaMarketMixin:
 def market_profile(self,symbol):
  ins=self.instrument(symbol)
  if ins.get('institutional_profile'):return ins['institutional_profile']
  seed=int(hashlib.sha256(symbol.encode()).hexdigest()[:8],16);adv,float_shares,spread=CALIBRATION.get(symbol,(1000000+seed%6000000,100000000+seed%900000000,10+seed%20))
  tier=ins.get('liquidity_tier','normal');factor={'illiquid':D('.1'),'thin':D('.3'),'deep':D(2),'liquid':D('1.4')}.get(tier,D(1))
  return {'adv':int(D(adv)*factor),'free_float':float_shares,'spread_bps':spread,'depth_fraction':'.06','block_daily_fraction':'.5','impact_coefficient':'.025','curve':[1.6 if h in (8,9,19,20) else .7 if h in (1,2,3,4,5) else 1.0 for h in range(24)],'source':'VANTAGE FICTIONAL calibration v1; not real exchange statistics'}
 def profile_hour_volume(self,symbol):
  profile=self.market_profile(symbol);calendar=self.state.get('session_calendar',{});hour=datetime.fromisoformat(self.state['time']).hour;curve=profile['curve']
  active=list(range(int(calendar['open_hour']),int(calendar['close_hour']))) if calendar.get('mode')=='CUSTOM' else list(range(24))
  return D(profile['adv'])*D(str(curve[hour]))/sum((D(str(curve[h])) for h in active),D(0)) if hour in active else D(0)
 def execution_limit(self,o):
  limit=D(o['limit']) if o['type'] in ('limit','stop_limit') else None;guard=o.get('execution_policy',{}).get('slippage_bps')
  if guard is not None:
   cap=D(o['execution_policy']['arrival'])*(1+D(guard)/10000*(1 if o['side']=='buy' else -1));limit=cap if limit is None else min(limit,cap) if o['side']=='buy' else max(limit,cap)
  return limit
 def execution_policy(self,o,p):
  if not (self.state.get('market_generation_version')==2 and o.get('execution_schedule')) and not any(k in p for k in ('execution_clock','urgency','after_window','max_participation','max_slippage_bps','max_impact_bps')):return
  if not o.get('execution_schedule'):raise ValueError('Execution policy controls require TWAP, VWAP or POV')
  urgency=p.get('urgency','NORMAL');clock=p.get('execution_clock','ACTIVE');after=p.get('after_window','CARRY')
  if urgency not in ('PATIENT','NORMAL','URGENT') or clock not in ('ACTIVE','CALENDAR') or after not in ('CARRY','PAUSE','CANCEL'):raise ValueError('Invalid execution policy')
  rate=D(str(p.get('max_participation',{'PATIENT':.1,'NORMAL':.25,'URGENT':.5}[urgency])))
  if not rate.is_finite() or not 0<rate<=1:raise ValueError('Maximum modeled participation must be above zero and at most 100%')
  policy=dict(urgency=urgency,clock=clock,after=after,participation=str(rate),arrival=self.instrument(o['symbol'])['price'],active_steps=1 if self.session_open() else 0,clock_tick=self.state['tick'])
  for field,key in [('max_slippage_bps','slippage_bps'),('max_impact_bps','impact_bps')]:
   if p.get(field) not in (None,''):
    value=D(str(p[field]))
    if not value.is_finite() or not 0<=value<=5000:raise ValueError('Execution cost guard must be 0–5000 basis points')
    policy[key]=str(value)
  o['execution_policy']=policy
  if o['execution_schedule']['kind']=='VWAP' and clock=='ACTIVE':
   calendar=self.state.get('session_calendar',{});when=datetime.fromisoformat(self.state['time']);weights=[];profile=self.market_profile(o['symbol'])
   for _ in range(24*365):
    opened=calendar.get('mode')!='CUSTOM' or when.weekday()<5 and when.date().isoformat() not in calendar.get('closed_dates',[]) and calendar['open_hour']<=when.hour<calendar['close_hour']
    if opened:weights.append(D(str(profile['curve'][when.hour])))
    if len(weights)>=o['execution_schedule']['hours']:break
    when+=timedelta(hours=1)
   if len(weights)<o['execution_schedule']['hours']:raise ValueError('Execution calendar has insufficient open hours')
   o['execution_schedule']['weights']=[str(v) for v in weights];o['execution_schedule']['basis']='Published deterministic model intraday volume curve; active hours only, no future realised volume'
 def advance_execution_clocks(self):
  for o in self.state['orders']:
   if o['status'] not in ('OPEN','PARTIAL') or not o.get('execution_policy'):continue
   policy=o['execution_policy']
   if policy['clock_tick']==self.state['tick']:continue
   policy['clock_tick']=self.state['tick']
   if self.session_open():policy['active_steps']+=1
   elapsed=policy['active_steps'] if policy['clock']=='ACTIVE' else self.state['tick']-o['execution_schedule']['start_tick']+1
   if elapsed>o['execution_schedule']['hours'] and policy['after']!='CARRY':o['status']='PAUSED' if policy['after']=='PAUSE' else 'CANCELLED';o['reason']='Execution window ended; '+policy['after'].lower()+' policy applied'
 def policy_release(self,o,remaining):
  policy=o.get('execution_policy')
  if not policy:return remaining
  used=D(o.get('policy_hour_filled',0)) if o.get('policy_fill_tick')==self.state['tick'] else D(0);hour=self.profile_hour_volume(o['symbol']);cap=hour*D(policy['participation'])
  if policy.get('impact_bps') is not None:
   profile=self.market_profile(o['symbol']);vol=max(D('.05'),D(str(self.instrument(o['symbol'])['vol'])));coefficient=vol*D(profile['impact_coefficient'])*10000;cap=min(cap,D(profile['adv'])*(D(policy['impact_bps'])/coefficient)**2)
  return min(remaining,max(D(0),cap.to_integral_value(rounding='ROUND_DOWN')-used))
 def execution_resume(self,p):
  o=next(o for o in self.state['orders'] if o['id']==p['id']);self.authority(o['account'],'trade')
  if o['status']!='PAUSED' or self.is_frozen(o['account']):raise ValueError('Only an unrestricted paused execution can resume')
  o['status']='PARTIAL' if D(o['filled']) else 'OPEN';o['execution_policy']['after']='CARRY';o['reason']='Resumed with carry-forward policy';return o
 def block_quote(self,p):
  from .engine import uid
  account=p['account'];symbol=self.instrument(p['symbol'])['symbol'];side=p.get('side','buy')
  try:requested=D(str(p.get('qty','')))
  except (InvalidOperation,ValueError):raise ValueError('Enter a valid positive whole-share block quantity') from None
  self.authority(account,'trade')
  if account=='personal' and side!='sell':raise ValueError('Personal block quotes support Sell owned shares; select an institution for block purchases or use the exchange buy ticket')
  if self.is_frozen(account):raise ValueError('Block account is restricted')
  if symbol not in self.state['market_symbols']:raise ValueError('Block quotes require a listed matched-stock instrument')
  if not self.session_open():raise ValueError('Market closed: request a block quote during an open session')
  if self.instrument(symbol)['status']!='OPEN':raise ValueError('Trading halt: this security is not open for block quotes')
  if side not in ('buy','sell') or not requested.is_finite() or requested<=0 or requested!=int(requested) or requested>D('1e15'):raise ValueError('Invalid block side or whole-share quantity')
  if side=='sell' and requested>self.block_available_owned(account,symbol):raise ValueError('Insufficient uncommitted owned shares for block sale; cancel other commitments or reduce quantity')
  ins=self.instrument(symbol);profile=self.market_profile(symbol);day=self.state['tick']//24;used=D(self.state.get('block_volume',{}).get(str(day)+':'+symbol,0));quota=max(D(0),D(profile['adv'])*D(profile['block_daily_fraction'])-used);left=min(requested,quota);offers=[]
  depth=self.book_depth(symbol);bid=next((D(r['bid']) for r in depth if r['bid'] is not None),None);ask=next((D(r['ask']) for r in depth if r['ask'] is not None),None);mid=(bid+ask)/2 if bid is not None and ask is not None else D(ins['price'])
  base=self.market_reference(ins)*D('.6')+mid*D('.4');concession=min(D('.03'),D(profile['spread_bps'])/10000+D(str(ins['vol']))*D('.025')*(requested/D(profile['adv'])).sqrt());price=self.quote_price(ins,base*(1+concession if side=='buy' else 1-concession));unit=price*self.fx_rate(ins['currency'])
  for actor in sorted(self.state['participants'],key=lambda a:a['account']):
   if left<=0:break
   other=actor['account']
   if other==account or self.is_frozen(other):continue
   if actor.get('mandate') and not actor['mandate'].get('allow_trade'):continue
   held=max(D(0),D(self.state['positions'].get(other+':'+symbol,{}).get('qty',0)))
   if side=='buy':capacity=min(self.block_available_owned(other,symbol,replace_maker=True),held*D('.25'))
   else:
    metrics=self.metrics(other);room=max(D(0),D(metrics['liquid_equity'])*D('1.8')-D(metrics['gross']));capacity=min(D(metrics['available_cash'])*D('.1'),room*D('.1'))/(unit*D('1.002'))
   candidate={'account':other,'symbol':symbol,'side':'sell' if side=='buy' else 'buy'}
   qty=min(left,self.institutional_capacity(candidate,price,capacity).to_integral_value(rounding='ROUND_DOWN'))
   if qty>0:offers.append({'account':other,'qty':str(qty),'price':str(price)});left-=qty
  offered=sum((D(o['qty']) for o in offers),D(0));cost=offered*unit
  if side=='buy' and cost*D('1.002')>self.available_cash(account):raise ValueError('Requested block exceeds actual unrestricted cash including fee allowance')
  if offered:
   from .pretrade import validate
   validate(self,{'side':side,'type':'limit','limit':str(price),'tif':'IOC'},account,ins,offered)
  q={'id':uid(),'account':account,'symbol':symbol,'side':side,'requested':str(requested),'offered':str(offered),'price':str(price),'currency':ins['currency'],'estimated_consideration_gbp':amt(cost),'concession_bps':str(concession*10000),'offers':offers,'tick':self.state['tick'],'day':day,'mark':ins['price'],'status':'OPEN' if offered>0 else 'NO_LIQUIDITY','basis':'Finite existing long inventory or actual available cash; preview reserves nothing. Block volume capped at 50% model ADV per simulation day.'}
  q['market_context']={'bid':str(bid) if bid is not None else None,'ask':str(ask) if ask is not None else None,'reference':str(self.market_reference(ins)),'midpoint':str(mid)};q['reason']='Eligible funded counterparties quoted actual available resources' if offered else 'No eligible funded block liquidity remains at this price and daily turnover capacity; no cash or shares reserved'
  quotes=self.state.setdefault('block_quotes',[]);quotes.append(q);self.state['block_quotes']=quotes[-100:];self.audit('block_rfq',copy.deepcopy(q));return q

 def block_available_owned(self,account,symbol,replace_maker=False):
  from .pretrade import pending
  held=D(self.state['positions'].get(account+':'+symbol,{}).get('qty',0));lent=sum((D(l['quantity']) for l in self.state.get('stock_loans',[]) if l['lender']==account and l['symbol']==symbol),D(0));reserved=sum((D(o['remaining']) for o in pending(self,account,symbol) if o['side']=='sell' and not (replace_maker and o.get('maker_quote'))),D(0))
  return max(D(0),held-lent-reserved-self.public_tender_committed(account,symbol))
 def block_accept(self,p):
  q=next(q for q in self.state.get('block_quotes',[]) if q['id']==p['id']);account=q['account'];self.authority(account,'trade')
  if q['status']!='OPEN' or q['tick']!=self.state['tick'] or q['mark']!=self.instrument(q['symbol'])['price']:raise ValueError('Block quote expired, changed or already used; request a fresh RFQ')
  if self.is_frozen(account) or not self.session_open() or self.instrument(q['symbol'])['status']!='OPEN':raise ValueError('Block participant restricted, market closed or security halted')
  profile=self.market_profile(q['symbol']);key=str(q['day'])+':'+q['symbol'];quota=D(profile['adv'])*D(profile['block_daily_fraction'])-D(self.state.get('block_volume',{}).get(key,0))
  if D(q['offered'])>quota:raise ValueError('Other block executions consumed the daily capacity; request a new quote')
  private=[];cash_before=self.cash(account)
  try:
   for offer in q['offers']:
    if self.is_frozen(offer['account']):continue
    for old in self.state['orders']:
     if old['account']==offer['account'] and old['symbol']==q['symbol'] and old.get('maker_quote') and old['status'] in ('OPEN','PARTIAL'):old['status']='CANCELLED'
    quantity=D(offer['qty'])
    if q['side']=='buy':quantity=min(quantity,self.block_available_owned(offer['account'],q['symbol'],replace_maker=True))
    if quantity<=0:continue
    order=self.append_liquidity_quote(offer['account'],q['symbol'],'sell' if q['side']=='buy' else 'buy',D(offer['price']),quantity)
    if order is not None:order['block_reference']=q['id'];private.append(order)
   self._block_context=q['id'];parent=self.order({'account':account,'symbol':q['symbol'],'side':q['side'],'qty':q['offered'],'type':'limit','limit':q['price'],'tif':'IOC','margin':False});filled=D(parent['filled'])
  finally:
   self._block_context=None
   for order in private:
    if order['status'] in ('OPEN','PARTIAL'):order['status']='CANCELLED'
  q.update(status='EXECUTED' if filled else 'NO_FILL',order=parent['id'],filled=str(filled),unfilled_request=str(D(q['requested'])-filled))
  q.update(actual_cash_change_gbp=amt(self.cash(account)-cash_before),actual_fees_gbp=parent.get('execution_fees_gbp','0.00'),reason=('Actual matched block execution; only filled shares settled' if filled else parent.get('reason','No executable liquidity remained at the quote price; request a fresh quote')))
  volumes=self.state.setdefault('block_volume',{});volumes[key]=str(D(volumes.get(key,0))+filled);self.state['block_volume']={k:v for k,v in volumes.items() if int(k.split(':',1)[0])>=q['day']-2};self.audit('block_execution',copy.deepcopy(q));return q
