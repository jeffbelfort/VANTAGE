"""Causal institutional schedules, executable-depth diagnostics and lean projections."""
import copy,json
from decimal import Decimal as D
from .integrity import amt

class InstitutionalMixin:
 def realised_total(self,account):
  # Executions are append-only. Validate the tail identity as well as rowid,
  # so savepoint rollback and rowid reuse cannot leak tentative performance.
  version=self.db.execute('pragma data_version').fetchone()[0];key=(self.state['id'],account)
  if getattr(self,'_realised_data_version',None)!=version:self._realised_cache={};self._realised_data_version=version
  cache=self._realised_cache;head=self.db.execute("select rowid,id from executions where world=? and json_extract(data,'$.account')=? order by rowid desc limit 1",key).fetchone();head=tuple(head) if head else (0,None);old=cache.get(key)
  if old and old[0]==head:return old[1]
  last,total=(old[0][0],old[1]) if old else (0,D(0))
  tail=self.db.execute('select id from executions where rowid=? and world=?',(last,self.state['id'])).fetchone() if old and last and head!=old[0] else None
  if not old or head[0]<=old[0][0] or last and (not tail or tail[0]!=old[0][1]):last=0;total=D(0)
  for row in self.db.execute("select json_extract(data,'$.realised') from executions where world=? and json_extract(data,'$.account')=? and rowid>?",(*key,last)):total+=D(row[0] or '0')
  cache[key]=(head,total);return total
 def configure_execution(self,o,p):
  mode=str(p.get('execution_algo','TWAP' if p.get('execution_hours') else 'MARKET')).upper()
  if mode not in ('MARKET','TWAP','VWAP','POV','ICEBERG'):raise ValueError('Unsupported execution algorithm')
  if mode in ('TWAP','VWAP','POV'):
   if o['account']=='personal' or o['symbol'] not in self.state.get('market_symbols',[]) or o['tif']!='GTC' or o['type'] not in ('market','limit'):raise ValueError('Scheduled execution requires an institutional matched-stock GTC market/limit order')
   hours=int(p.get('execution_hours',24))
   if not 2<=hours<=744:raise ValueError('Execution horizon must be 2–744 simulation hours')
   schedule=dict(kind=mode,hours=hours,start_tick=self.state['tick'])
   ins=self.instrument(o['symbol'])
   if mode=='VWAP':
    # Learn a historical intraday shape; never inspect future bars or events.
    past=[b for b in ins.get('history',[]) if b['t']<self.state['tick'] and b.get('v',0)>0];shape=[sum(int(b['v']) for b in past if b['t']%24==i) for i in range(24)]
    schedule['weights']=[max(1,shape[(self.state['tick']+i)%24]) for i in range(hours)];schedule['basis']='Retained past observed volume by simulation hour; flat fallback'
   if mode=='POV':
    rate=D(str(p.get('participation',.1)))
    if not rate.is_finite() or not 0<rate<=D('.5'):raise ValueError('Participation rate must be above zero and at most 50%')
    schedule.update(rate=str(rate),volume_start=ins.get('executed_volume','0'),basis='Actual matched volume since submission, excluding this parent')
   o['execution_schedule']=schedule
  if mode=='ICEBERG' or p.get('display_qty') is not None:
   if o['symbol'] not in self.state.get('market_symbols',[]) or o['type']!='limit' or o['tif']!='GTC':raise ValueError('Iceberg requires a matched-stock GTC limit order')
   display=D(str(p.get('display_qty',0)))
   if not display.is_finite() or display!=int(display) or not 1<=display<=D(o['qty']):raise ValueError('Displayed quantity must be whole shares within parent quantity')
   o['display_qty']=str(display)
 def scheduled_release(self,o):
  remaining=D(o['remaining']);schedule=o.get('execution_schedule');released=D(o['qty'])
  if schedule:
   elapsed=max(0,self.state['tick']-schedule['start_tick']);steps=min(schedule['hours'],o['execution_policy']['active_steps'] if o.get('execution_policy',{}).get('clock')=='ACTIVE' else elapsed+1)
   if schedule['kind']=='POV':
    volume=max(D(0),D(self.instrument(o['symbol']).get('executed_volume','0'))-D(schedule['volume_start'])-D(o['filled']));rate=D(schedule['rate']);released=min(released,(volume*rate/(1-rate)).to_integral_value(rounding='ROUND_DOWN'))
   elif schedule['kind']=='VWAP':released=min(released,D(o['qty'])*sum((D(v) for v in schedule['weights'][:steps]),D(0))//sum((D(v) for v in schedule['weights']),D(0)))
   else:released=min(released,D(o['qty'])*steps//schedule['hours'])
   remaining=min(remaining,max(D(0),released-D(o['filled'])))
  return self.policy_release(o,min(remaining,D(o.get('display_qty',remaining))))
 def risk_quantity(self,o,price,requested,held,metrics=None):
  ins=self.instrument(o['symbol']);unit=price*self.fx_rate(ins['currency']);m=metrics or self.metrics(o['account']);policy=self.state.get('account_limits',{}).get(o['account'],{});equity=max(D(0),D(m['liquid_equity'])-1);mark=D(ins['price'])*self.fx_rate(ins['currency']);other=max(D(0),D(m['gross'])-abs(held*mark));ceiling=min(max(D(0),equity*D(policy.get('max_leverage',2))-other),equity*D(policy.get('single_name_pct',200))/100)*D('.999')/max(D('.0001'),unit)
  reducing=max(D(0),-held if o['side']=='buy' else held);room=max(D(0),ceiling-held if o['side']=='buy' else ceiling+held);quantity=min(requested,max(reducing,room).to_integral_value(rounding='ROUND_DOWN'))
  if quantity<requested:o['reason']='Remaining quantity constrained by margin / gross-exposure headroom'
  return quantity
 def explicit_risk_preflight(self,o):
  policy=self.state.get('account_limits',{}).get(o['account'])
  if not policy:return
  ins=self.instrument(o['symbol']);unit=D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency']);held=D(self.state['positions'].get(o['account']+':'+o['symbol'],{}).get('qty','0'));new=held+(D(o['qty']) if o['side']=='buy' else -D(o['qty']))
  if abs(new)<=abs(held) and new*held>=0:return
  m=self.metrics(o['account']);equity=max(D(0),D(m['liquid_equity'])-1);gross=D(m['gross'])-abs(held*unit)+abs(new*unit);lev=D(policy['max_leverage']);single=D(policy['single_name_pct'])
  reason=None
  if gross>equity*lev:reason=f"Desk gross-exposure limit: requested £{gross:,.2f} exceeds explicit {lev}× liquid equity; maximum approximately {max(0,int((equity*lev-D(m['gross'])+abs(held*unit))/unit))} total units at this price."
  elif abs(new*unit)>equity*single/100:reason=f"Single-name concentration limit: maximum approximately {max(0,int(equity*single/100/unit))} total units at this price."
  if reason:o.update(status='REJECTED',reason=reason)
 def replenish_value_bids(self):
  # Natural institutional demand at reservation prices, funded by existing cash.
  w=self.state;symbols=w['market_symbols'];count=max(1,len(symbols))
  for actor in w['participants']:
   if actor['strategy'] not in ('pension','asset_manager','value','bank') or self.is_frozen(actor['account']):continue
   account=actor['account'];cash=self.available_cash(account);m=self.metrics(account);equity=max(D(0),D(m['liquid_equity']));room=max(D(0),equity*D('1.5')-D(m['gross']));budget=min(cash*D('.15'),room)/count
   if budget<=0:continue
   target=equity*D(str(actor['risk_budget']))/D(str(max(1,len(symbols)/2)))
   for symbol in symbols:
    ins=w['instruments'][symbol]
    if ins['status']!='OPEN':continue
    center=D(ins.get('liquidity_center',ins['price']));fundamental=self.market_reference(ins);px=min(center*D('.992'),fundamental*D('.98'))
    if px<center*D('.95'):continue
    px=self.quote_price(ins,px);unit=px*self.fx_rate(ins['currency']);held=max(D(0),D(w['positions'].get(account+':'+symbol,{}).get('qty','0')));capacity,_=self.liquidity_profile(ins);qty=int(min(capacity*D('.5'),budget/(unit*D('1.002')),max(D(0),target-held*unit)/unit))
    if qty>0:self.append_liquidity_quote(account,symbol,'buy',px,qty,inventory=True)
 def order_diagnostics(self,o,metrics=None):
  ins=self.instrument(o['symbol']);buy=o['side']=='buy';matched=o['symbol'] in self.state.get('market_symbols',[]) and self.state.get('microstructure_enabled');rows=self.book_depth(o['symbol'],limit=1000,orders=[r for r in self.state['orders'] if r['account']!=o['account'] and r['symbol']==o['symbol']]) if matched else []
  bids=sum((D(r['bid_qty']) for r in rows),D(0));asks=sum((D(r['ask_qty']) for r in rows),D(0));remaining=D(o['remaining']);release=self.released_order_qty(o);borrow=max(D(0),D(ins.get('borrow_available',0))-sum((max(D(0),-D(p['qty'])) for p in self.state['positions'].values() if p['symbol']==o['symbol']),D(0)));held=D(self.state['positions'].get(o['account']+':'+o['symbol'],{}).get('qty','0'));available=asks if buy else bids
  quote_cost=D(0);qty=D(0);limit=self.execution_limit(o)
  for row in rows:
   price=row['ask'] if buy else row['bid'];amount=D(row['ask_qty'] if buy else row['bid_qty'])
   if price is None:continue
   price=D(price)
   if limit is not None and (price>limit if buy else price<limit):continue
   take=min(amount,max(D(0),min(remaining,release)-qty));qty+=take;quote_cost+=take*price*self.fx_rate(ins['currency'])
  funded_put=o['symbol'] in self.state['options'] and self.state['options'][o['symbol']]['kind']=='put' and self.state.get('microstructure_enabled')
  put_quote=self.put_quote(o['symbol']) if funded_put else None
  if not matched:
   stored=self.state['options'].get(o['symbol'],self.state['instruments'].get(o['symbol'],{}));used=D(stored.get('liquidity_used','0')) if stored.get('liquidity_tick')==self.state['tick'] else D(0);available=put_quote['available'] if put_quote else max(D(0),D(ins['liquidity'])-used);qty=min(remaining,available);quote_cost=qty*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency'])
  status='Partially filled' if D(o['filled'])>0 else 'Awaiting liquidity';reason=o.get('reason','')
  if o['status'] not in ('OPEN','PARTIAL'):status=o['status']
  elif not self.session_open():status='Awaiting market open'
  elif not buy and not o.get('margin') and remaining>max(D(0),held):status='Insufficient holdings';reason='Insufficient shares — use Sell Short with margin enabled'
  elif self.state['paused'] and self.state.get('microstructure_enabled') and not self._advancing:status='Simulation paused'
  elif self.is_frozen(o['account']):status='Account restricted'
  elif release<=0:status='Algorithmic execution scheduled'
  elif not buy and not o.get('margin') and remaining>max(D(0),held):status='Insufficient holdings';reason='Insufficient shares — use Sell Short with margin enabled'
  elif ins['status']!='OPEN':status='Trading halt'
  elif not buy and remaining>max(D(0),held) and borrow<=0:status='Insufficient borrow'
  elif limit is not None and qty==0 and available>0:status='Price / slippage limit prevents execution' if o.get('execution_policy') else 'Price limit prevents execution'
  elif reason and any(word in reason.lower() for word in ('margin','collateral','exposure','cash limit','concentration')):status='Insufficient margin / risk headroom'
  elif available==0:status='Awaiting liquidity'
  if o['status'] in ('OPEN','PARTIAL') and not o.get('forced'):
   from .pretrade import validate
   try:validate(self,o,o['account'],ins,remaining,exclude=o['id'])
   except ValueError as exc:
    reason=str(exc);lower=reason.lower()
    status='Insufficient holdings' if 'shares' in lower or 'existing long' in lower else 'No eligible short to cover' if 'cover' in lower else 'Stock borrow unavailable' if 'borrow' in lower else 'Insufficient buying power' if 'buying power' in lower else 'Insufficient margin / financing' if any(t in lower for t in ('margin','collateral','exposure','concentration','financing')) else 'Trading halt' if 'not open' in lower or 'halt' in lower else 'Market closed' if 'market closed' in lower else 'Order blocked'
    qty=D(0);quote_cost=D(0)
  last=self.db.execute("select data from executions where world=? and json_extract(data,'$.order')=? order by rowid desc limit 1",(self.state['id'],o['id'])).fetchone()
  m=metrics if metrics is not None else self.metrics(o['account']);schedule=o.get('execution_schedule');vwap=D(o.get('executed_notional','0'))/D(o['filled']) if D(o['filled']) and o.get('executed_notional') else None
  elapsed=max(1,o.get('execution_policy',{}).get('active_steps',self.state['tick']-(schedule or {}).get('start_tick',self.state['tick'])+1));pace=D(o['filled'])/elapsed;arrival=o.get('arrival_price') or o.get('execution_policy',{}).get('arrival');slippage=(vwap/D(arrival)-1)*10000*(1 if buy else -1) if vwap and arrival else None
  return dict(actual_market_volume=str(ins.get('executed_volume',0)),average_execution_native=str(vwap) if vwap else None,execution_pace_shares_per_hour=str(pace),estimated_remaining_hours_at_observed_pace=str(remaining/pace) if pace>0 else None,completion_estimate_basis='Past actual fills only; future liquidity and limits can change or prevent completion',realised_slippage_bps=str(slippage) if slippage is not None else None,execution_fees_gbp=o.get('execution_fees_gbp'),currency=ins['currency'],limit_native=str(limit) if limit is not None else None,best_bid=rows[0]['bid'] if rows else None,best_ask=rows[0]['ask'] if rows else None,model_profile=self.market_profile(o['symbol']) if matched else None,execution_policy=copy.deepcopy(o.get('execution_policy')),schedule_target=str(min(D(o['qty']),D(o['filled'])+release)),window_ended=bool(schedule and (o.get('execution_policy',{}).get('active_steps',self.state['tick']-schedule['start_tick']+1)>schedule['hours'])),remaining_as_model_adv=str(remaining/D(self.market_profile(o['symbol'])['adv'])) if matched else None,requested_notional_gbp=amt(remaining*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency'])),spread=str(D(rows[0]['ask'])-D(rows[0]['bid'])) if rows and rows[0]['ask'] and rows[0]['bid'] else None,status=status,reason=reason,bid_depth=str(bids),ask_depth=str(asks),remaining=o['remaining'],released=str(release),estimated_executable=str(qty),estimated_consideration_gbp=amt(quote_cost),estimate_basis='Displayed liquidity only; fees, self-orders, competing instructions and final risk checks may reduce execution',borrow_remaining=str(borrow),available_cash=m['available_cash'],gross_headroom=amt(max(D(0),D(m['liquid_equity'])*D(self.state.get('account_limits',{}).get(o['account'],{}).get('max_leverage',2))-D(m['gross']))),last_execution=json.loads(last[0]) if last else None,option_quote={k:str(v) for k,v in put_quote.items() if k!='makers'} if put_quote else None,next_execution_tick=self.state['tick']+1 if schedule and o['status'] in ('OPEN','PARTIAL') else None,vwap=str(vwap) if vwap is not None else None)
 def trading_snapshot(self):
  with self.lock:
   if not self.state:return self.snapshot()
   w=self.state;keys=('id','name','time','tick','paused','speed','orders','fills','positions','balances','entities','funds','options','history','employees','employee_tasks','npcs','account_limits','credit','macro','news','market_generation_version','institutional_funds','block_quotes','treasury_positions')
   view=copy.deepcopy({k:w[k] for k in keys if k in w});view['metrics']={a:self.metrics(a) for a in self.accounts()};view['option_quotes']={s:self.option_view(s) for s in w['options']};view['session_open']=self.session_open();view['restrictions']={a:self.restriction_summary(a) for a in self.controlled_accounts()};view['institutional_economy']=self.institutional_views(view['metrics'])
   for pos in view['positions'].values():
    ins=self.instrument(pos['symbol']);pos.update(price=ins['price'],currency=ins['currency'],value=amt(D(pos['qty'])*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency'])));pos['pnl']=amt(D(pos['value'])-D(pos['cost']))
   view['treasury_quotes']={key:self.treasury_quote(security) for key,security in w.get('treasury_securities',{}).items()}
   view['market_marks']={s:{k:copy.deepcopy(ins[k]) for k in ('price','previous','status','timestamp','history') if k in ins} for s,ins in w['instruments'].items()}
   books=self.depth_map()
   for s,mark in view['market_marks'].items():mark.update(depth=books.get(s,[]),chart_tick=w['tick'],chart_time=w['time'])
   view['order_diagnostics']={o['id']:self.order_diagnostics(o,view['metrics'][o['account']]) for o in w['orders'] if o['status'] in ('OPEN','PARTIAL') and o['account'] in self.controlled_accounts()}
   return dict(world=view,_partial=True,_view='trading')
 def depth_map(self):
  # One order traversal for all security ladders; per-symbol book_depth remains exact.
  groups={}
  for o in self.state['orders']:
   if o['status'] in ('OPEN','PARTIAL') and o['type'] in ('limit','stop_limit') and (o['type']=='limit' or o.get('triggered')):groups.setdefault(o['symbol'],[]).append(o)
  return {s:self.book_depth(s,orders=rows) for s,rows in groups.items()}
