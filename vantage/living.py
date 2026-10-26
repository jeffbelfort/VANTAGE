"""Finite-capital rule-based participants, resting orders and public event propagation.
No inference service. Simulation decisions depend only on past/current local information.
"""
import copy,hashlib,random,math
from decimal import Decimal as D
from datetime import datetime,timedelta
from .integrity import amt

PROFILES=[('mm0','Arden Securities','market_maker',1000000000,1),('mm1','Beacon Liquidity','liquidity_provider',1000000000,1),('retail','Household Investment Pool','retail',5000000,6),('momentum','Vector Trend Partners','momentum',250000000,3),('value','Longview Capital','value',500000000,12),('hedge','Cairn Strategies','hedge_fund',500000000,4),('pension','Civic Retirement Trust','pension',2000000000,48),('bankdesk','Harbour Treasury','bank',1000000000,24),('prop','Vertex Trading','proprietary',200000000,2),('short','Northstar Research Fund','short_seller',250000000,3),('asset','Horizon Asset Management','asset_manager',1000000000,24),('arb','Concord Relative Value','relative_value',200000000,6),('squeeze','Summit Tactical Capital','contrarian',200000000,2)]

class LivingMarketMixin:
 def install_living_market(self):
  w=self.state
  if w.get('market_system_version',0)>=1:return
  w['market_system_version']=1;w['paused']=True;w['events']=[];w['participants']=[];w['market_activity']=[];w['alerts']=[]
  w['microstructure_enabled']=not (w.get('_legacy_fixture') or w.get('_static_market'));w['market_symbols']=[s for s in ['NVDA','JPM','AAPL','MSFT','GOOGL','HSBA.L','TSM','RR.L'] if s in w['instruments']]
  if not w['microstructure_enabled']:return
  if w.get('market_generation_version')==2:
   w['market_symbols']=[];self.ensure_exchange_coverage();return
  prime_loans=sum((-D(v) for k,v in w['balances'].items() if k.startswith('debt:') and k.endswith(':margin')),D(0));lines={'cash:prime':D('10000000000'),'equity:prime':-D('10000000000')-prime_loans}
  for k,v in list(w['balances'].items()):
   if k.startswith('debt:') and k.endswith(':margin'):lines['prime:loan:'+k.split(':')[1]]=-D(v)
  self.post('Prime broker opening capital and legacy loan baseline',lines)
  for id,name,strategy,capital,interval in PROFILES:
   account='agent_'+id;actor=dict(id=id,account=account,name=name,strategy=strategy,interval=interval,next_tick=w['tick']+1,risk_budget=.15 if strategy in ('pension','bank') else .4,information_delay=0 if strategy in ('market_maker','liquidity_provider','hedge_fund') else 2 if strategy in ('short_seller','value') else 5,known_events=[],beliefs={},last_decision=None)
   lines={'cash:'+account:D(capital)};equity=D(capital)
   if strategy in ('market_maker','liquidity_provider'):
    for sym in w['market_symbols']:
     ins=w['instruments'][sym];inventory_budget=D(5000000)*D(str(.6+(int(hashlib.sha256(sym.encode()).hexdigest()[:4],16)%100)/100));qty=D(max(100,int(inventory_budget/(D(ins['price'])*self.fx_rate(ins['currency'])))));cost=(qty*D(ins['price'])*self.fx_rate(ins['currency'])).quantize(D('.01'));lines['inventory:'+account+':'+sym]=cost;equity+=cost;w['positions'][account+':'+sym]=dict(account=account,symbol=sym,qty=amt(qty),cost=amt(cost),borrowed='0.00')
   lines['equity:'+account]=-equity;self.post('Participant opening endowment '+name,lines);w['participants'].append(actor)
  for sym in w['market_symbols']:
   ins=w['instruments'][sym];ins['borrow_available']=int(sum((D(p['qty']) for p in w['positions'].values() if p['symbol']==sym and p['account'].startswith('agent_mm')),D(0))*D('2.5'));ins['liquidity_source']='Finite model cash and inventory; not exchange depth';ins['public_short_interest']='0';ins['borrow_fee_apr']=3.;ins['model_fundamental']=ins['price'];ins['flow_history']=[]
  self.replenish_books();w['liquidity_quote_version']=1;self.audit('living_market_initialized',{'participants':len(w['participants']),'coverage':w['market_symbols'],'capital':'Opening model endowments; no player balances modified'})

 def book_depth(self,symbol,limit=10,orders=None):
  bids={};asks={}
  for o in (self.state['orders'] if orders is None else orders):
   if o.get('block_reference') or o['symbol']!=symbol or o['status'] not in ('OPEN','PARTIAL') or o['type'] not in ('limit','stop_limit') or (o['type']=='stop_limit' and not o.get('triggered')):continue
   visible=self.released_order_qty(o)
   if visible<=0:continue
   levels=bids if o['side']=='buy' else asks;levels[o['limit']]=levels.get(o['limit'],D(0))+visible
  b=sorted(bids,key=D,reverse=True)[:limit];a=sorted(asks,key=D)[:limit];out=[];bc=D(0);ac=D(0)
  for i in range(max(len(b),len(a))):
   bid=b[i] if i<len(b) else None;ask=a[i] if i<len(a) else None;bq=bids.get(bid,D(0));aq=asks.get(ask,D(0));bc+=bq;ac+=aq
   out.append(dict(bid=bid,ask=ask,bid_qty=str(bq),ask_qty=str(aq),bid_cumulative=str(bc),ask_cumulative=str(ac),qty=str(min(bq,aq))))
  return out

 def match_order(self,o,forced=False):
  cache=getattr(self,'_snapshot_metrics_cache',None);ledger=getattr(self,'_projection_ledger',None)
  self._snapshot_metrics_cache={};self._projection_ledger={}
  try:return self._match_order_atomic(o,forced)
  finally:
   if cache is not None:cache.clear()
   self._snapshot_metrics_cache=cache;self._projection_ledger={} if ledger is not None else None

 def _match_order_atomic(self,o,forced=False):
  if o.get('tif')!='FOK':return self._match_order(o,forced)
  before=copy.deepcopy(self.state);self.db.execute('SAVEPOINT fok_instruction')
  try:
   self._match_order(o,forced)
   if o['status']=='FILLED':self.db.execute('RELEASE fok_instruction');return
   self.db.execute('ROLLBACK TO fok_instruction');self.db.execute('RELEASE fok_instruction');self.state.clear();self.state.update(before)
   if getattr(self,'_snapshot_metrics_cache',None) is not None:self._snapshot_metrics_cache.clear();self._projection_ledger={}
   original=next(x for x in self.state['orders'] if x['id']==o['id']);o.clear();o.update(original);o['status']='CANCELLED';o['reason']='Fill-or-kill: insufficient depth or risk capacity';self.state['orders']=[o if x['id']==o['id'] else x for x in self.state['orders']]
  except Exception:
   self.db.execute('ROLLBACK TO fok_instruction');self.db.execute('RELEASE fok_instruction');raise

 def released_order_qty(self,order):
  return self.scheduled_release(order)

 def _liquid_qty(self,order,price,requested):
  requested=self.institutional_capacity(order,price,min(requested,self.released_order_qty(order)))
  if requested<=0:return D(0)
  account=order['account'];sym=order['symbol'];fx=self.fx_rate(self.instrument(sym)['currency']);unit=price*fx;held=D(self.state['positions'].get(account+':'+sym,{}).get('qty','0'))
  lent=sum((D(l['quantity']) for l in self.state.get('stock_loans',[]) if l['symbol']==sym and l['lender']==account),D(0))
  if order['side']=='sell' and lent>0:return min(requested,max(D(0),held-lent))
  if order['side']=='sell' and 0<=requested<=held:return requested
  metrics=self.metrics(account);requested=self.risk_quantity(order,price,requested,held,metrics)
  if order['side']=='sell':
   if not order.get('margin'):
    if requested>max(D(0),held):order['reason']='Insufficient shares — use Sell Short with margin enabled'
    return min(requested,max(D(0),held))
   short=sum((max(D(0),-D(p['qty'])) for p in self.state['positions'].values() if p['symbol']==sym),D(0))
   return min(requested,max(D(0),held)+max(D(0),D(self.instrument(sym).get('borrow_available',0))-short))
  if order.get('margin'):return requested
  cash=D(metrics['available_cash'])
  if not order.get('maker_quote'):
   from .pretrade import order_cash
   cash+=order_cash(self,order)
  elif order['type']=='limit':cash+=D(order['remaining'])*D(order['limit'])*fx
  rate=D(self.state.get('operating_plans',{}).get(account,{}).get('fee_rate','.0005'));budget=max(D(0),min(cash-1,cash/(1+rate)))
  return min(requested,D(int(budget/unit)))

 def _match_order(self,o,forced=False):
  from .engine import OrderRejected,uid
  buy=o['side']=='buy';limit=self.execution_limit(o)
  available=self.released_order_qty(o)
  if available<=0:return
  candidates=[r for r in self.state['orders'] if r['symbol']==o['symbol'] and r['account']!=o['account'] and r['side']!=o['side'] and r['status'] in ('OPEN','PARTIAL') and r['type'] in ('limit','stop_limit') and (r['type']=='limit' or r.get('triggered')) and (r.get('block_reference')==o.get('block_reference') if o.get('block_reference') else not r.get('block_reference'))]
  candidates.sort(key=lambda r:(D(r['limit']) if buy else -D(r['limit']),r.get('sequence',0)))
  if o.get('tif')=='FOK':
   eligible=sum((self.released_order_qty(r) for r in candidates if limit is None or (buy and D(r['limit'])<=limit) or (not buy and D(r['limit'])>=limit)),D(0))
   if eligible<D(o['remaining']):o['status']='CANCELLED';o['reason']='Fill-or-kill: displayed depth insufficient';return
  filled=D(0)
  available=self.released_order_qty(o)
  if available<=0:return
  for candidate in candidates:
   resting=candidate
   if resting is None or resting['status'] not in ('OPEN','PARTIAL'):continue
   price=D(resting['limit'])
   if limit is not None and ((buy and price>limit) or (not buy and price<limit)):break
   qty=min(D(o['remaining']),D(resting['remaining']),available-filled)
   if not forced:qty=self._liquid_qty(o,price,qty)
   qty=self._liquid_qty(resting,price,qty)
   if o.get('reduce_only') or forced:
    held=D(self.state['positions'].get(o['account']+':'+o['symbol'],{}).get('qty','0'))
    if held==0 or (buy and held>0) or (not buy and held<0):o['status']='CANCELLED';break
    qty=min(qty,abs(held))
   if resting.get('reduce_only'):
    held=D(self.state['positions'].get(resting['account']+':'+resting['symbol'],{}).get('qty','0'))
    if held==0 or (resting['side']=='buy' and held>0) or (resting['side']=='sell' and held<0):resting['status']='CANCELLED';continue
    qty=min(qty,abs(held))
   if qty<=0:continue
   initiator_filled=False
   old_state={k:(dict(self.state[k]) if k in ('balances','positions') else list(self.state[k]) if k=='fills' else copy.deepcopy(self.state.get(k,[] if k=='stock_loans' else {}))) for k in ('balances','positions','fills','employees','npcs','stock_loans','legacy_stock_borrow')}
   o_before=copy.deepcopy(o);r_before=copy.deepcopy(resting);self.db.execute('SAVEPOINT paired_execution')
   try:
    self.fill(o,qty,price,forced);initiator_filled=True;self.fill(resting,qty,price,False);self.db.execute('RELEASE paired_execution')
   except OrderRejected as exc:
    self.db.execute('ROLLBACK TO paired_execution');self.db.execute('RELEASE paired_execution')
    # Restore object dictionaries in place because caller retains o/resting references.
    self.state.update(old_state)
    if getattr(self,'_snapshot_metrics_cache',None) is not None:self._snapshot_metrics_cache.clear();self._projection_ledger={}
    o.clear();o.update(o_before);resting.clear();resting.update(r_before)
    if initiator_filled:
     resting['status']='CANCELLED';resting['reason']='Unexecutable counterparty quote: '+str(exc);continue
    o['reason']=str(exc)
    if o.get('tif','GTC')=='GTC':o['status']='PARTIAL' if D(o['filled']) else 'OPEN'
    else:o['status']='REJECTED' if D(o['filled'])==0 else 'CANCELLED'
    return
   for item in [o,resting]:
    item['remaining']=amt(D(item['remaining'])-qty);item['filled']=amt(D(item['filled'])+qty);item['status']='FILLED' if D(item['remaining'])==0 else 'PARTIAL'
    if item.get('oco'):
     for sibling in self.state['orders']:
      if sibling['id']==item['oco'] and sibling['status'] in ('OPEN','PARTIAL'):
       sibling['remaining']=amt(max(D(0),D(sibling['remaining'])-qty))
       if D(sibling['remaining'])==0:sibling['status']='CANCELLED'
   instrument=self.state['instruments'][o['symbol']];instrument['executed_volume']=str(D(instrument.get('executed_volume','0'))+qty)
   filled+=qty;self.mark(o['symbol'],price);ins=self.state['instruments'][o['symbol']];ins['history'][-1]['v']+=int(qty);ins['flow_history'].append(dict(tick=self.state['tick'],qty=int(qty)*(1 if buy else -1),price=str(price)));ins['flow_history']=ins['flow_history'][-120:]
   self.state['market_activity'].insert(0,dict(time=self.state['time'],symbol=o['symbol'],qty=str(qty),price=str(price),aggressor=o['side'],participant_class=next((a['strategy'] for a in self.state['participants'] if a['account']==o['account']),'player'),source='LOCAL EXECUTION'))
   self.state['market_activity']=self.state['market_activity'][:250]
   if D(o['remaining'])==0 or filled>=available:break
  if o.get('tif') in ('IOC','FOK') and o['status'] in ('OPEN','PARTIAL'):o['status']='CANCELLED';o['reason']='Unfilled immediate quantity cancelled'
  if o['type']=='bracket' and filled:
   children=[]
   for type,level in [('limit',o['take']),('stop',o['loss'])]:
    self.state['order_sequence']+=1;children.append({**o,'id':uid(),'sequence':self.state['order_sequence'],'side':'sell' if buy else 'buy','intent':'sell_long' if buy else 'buy_to_cover','margin':not buy,'credit_reserved':'0.00','type':type,'qty':amt(filled),'remaining':amt(filled),'filled':'0.00','status':'OPEN','limit':level,'stop':level,'triggered':False,'oco':None,'reduce_only':True,'tif':'GTC'})
   children[0]['oco']=children[1]['id'];children[1]['oco']=children[0]['id'];self.state['orders'].extend(children)

 def repair_market_liquidity(self):
  if not self.state.get('microstructure_enabled') or self.state.get('liquidity_quote_version',0)>=1:return False
  self.replenish_books();self.state['liquidity_quote_version']=1
  self.audit('liquidity_quote_recovery',{'version':1,'funding':'Existing maker cash, collateral and finite borrow pool','player_cash_positions_and_orders_unchanged':True})
  return True

 def liquidity_profile(self,ins):
  """Explicit model capacity, not a claim about actual exchange ADV."""
  if ins.get('institutional_profile'):
   profile=ins['institutional_profile'];tier_factor={'illiquid':D('.2'),'thin':D('.4'),'normal':D(1),'liquid':D('1.5'),'deep':D(2)}.get(ins.get('liquidity_tier','normal'),D(1));vol=max(D('.05'),D(str(ins.get('vol',.25))));return D(profile['adv'])*D(profile['depth_fraction'])*tier_factor/(1+vol*2),vol
  daily=max(D(0),D(str(ins.get('model_daily_volume',D(ins.get('liquidity',100000))*20))))
  tier=str(ins.get('liquidity_tier','normal')).lower()
  tier_factor={'illiquid':D('.2'),'thin':D('.4'),'normal':D(1),'liquid':D('1.5'),'deep':D(2)}.get(tier,D(1))
  vol=max(D('.05'),D(str(ins.get('vol',.25))))
  recent=sum((abs(D(str(f['qty']))) for f in ins.get('flow_history',[]) if self.state['tick']-f['tick']<=24),D(0))
  # Observed activity can raise displayed capacity modestly; it never creates
  # stock borrow, cash, or another participant's inventory.
  activity=min(D('1.5'),D(1)+recent/max(D(1),daily))
  volume=daily*tier_factor
  hourly=volume/D(24)
  session=self.state.get('session_calendar',{});session_factor=D(1)
  if session.get('mode')=='CUSTOM':
   hour=datetime.fromisoformat(self.state['time']).hour;session_factor=D('1.35') if hour in (session['open_hour'],session['close_hour']-1) else D('.8')
  capacity=hourly*D('.25')*activity*session_factor/(1+vol*2)
  return capacity,vol

 def replenish_books(self):
  cache=getattr(self,'_snapshot_metrics_cache',None);ledger=getattr(self,'_projection_ledger',None)
  self._snapshot_metrics_cache={};self._projection_ledger={}
  try:return self._replenish_books()
  finally:
   if cache is not None:cache.clear()
   self._snapshot_metrics_cache=cache;self._projection_ledger={} if ledger is not None else None

 def _replenish_books(self):
  w=self.state
  if not w.get('microstructure_enabled'):return
  for o in w['orders']:
   if o.get('maker_quote') and o['status'] in ('OPEN','PARTIAL'):o['status']='CANCELLED'
  self.archive_closed_orders()
  reserved_borrow={};reserved_long={}
  for o in w['orders']:
   if o['status'] not in ('OPEN','PARTIAL') or o['side']!='sell':continue
   key=(o['account'],o['symbol'])
   reserved_long[key]=reserved_long.get(key,D(0))+D(o['remaining'])
   if o.get('margin'):reserved_borrow[key]=reserved_borrow.get(key,D(0))+D(o['remaining'])
  borrow_used={};shorts={}
  for position in w['positions'].values():
   if D(position['qty'])<0:shorts[position['symbol']]=shorts.get(position['symbol'],D(0))-D(position['qty'])
  for sym in w['market_symbols']:
   short=shorts.get(sym,D(0))
   committed=sum((max(D(0),amount-max(D(0),D(w['positions'].get(account+':'+sym,{}).get('qty','0')))) for (account,symbol),amount in reserved_borrow.items() if symbol==sym),D(0))
   borrow_used[sym]=short+committed
  makers=[a for a in w['participants'] if a['strategy'] in ('market_maker','liquidity_provider') and not self.is_frozen(a['account'])]
  profiles={sym:self.liquidity_profile(w['instruments'][sym]) for sym in w['market_symbols']}
  # A price/volume/volatility weighted allocation replaces the old equal
  # per-name exposure ceiling and sequential 2%-of-remaining-cash depletion.
  weights={sym:max(D('.1'),min(D(4),(max(D(1),profiles[sym][0])*D(w['instruments'][sym]['price'])*self.fx_rate(w['instruments'][sym]['currency'])/D('30000000')).sqrt())) for sym in w['market_symbols']}
  if w.get('market_generation_version')==2:
   active={o['symbol'] for o in w['orders'] if o['status'] in ('OPEN','PARTIAL') and not o['account'].startswith('agent_')}
   weights={sym:value*(D(8) if sym in active else D(1)) for sym,value in weights.items()}
  total_weight=sum(weights.values(),D(0)) or D(1)
  for actor in makers:
   account=actor['account'];cash=max(D(0),self.available_cash(account));metrics=self.metrics(account);equity=max(D(0),D(metrics['liquid_equity']));gross_room=max(D(0),equity*D('1.8')-D(metrics['gross']))
   if equity<=0:continue
   for sym in w['market_symbols']:
    ins=w['instruments'][sym]
    if ins['status']!='OPEN':continue
    px=D(ins['price']);fx=self.fx_rate(ins['currency']);held=D(w['positions'].get(account+':'+sym,{}).get('qty','0'));capacity,vol=profiles[sym];share=weights[sym]/total_weight
    # Do not compound the worst swept ladder price into the next entire book.
    # Start at the saved mark, then move a separate quote anchor once per hour
    # from actual signed executions relative to modeled daily turnover.
    if 'liquidity_anchor' not in ins:
     ins['liquidity_anchor']=str(px);ins['liquidity_anchor_tick']=w['tick']
    if ins['liquidity_anchor_tick']<w['tick']:
     net=sum((D(str(x['qty'])) for x in ins.get('flow_history',[]) if ins['liquidity_anchor_tick']<=x['tick']<w['tick']),D(0))
     daily=max(D(1),D(str(ins.get('model_daily_volume',D(ins.get('liquidity',100000))*20))))
     move=min(D('.02'),vol*D('.25')*(abs(net)/daily).sqrt())
     next_anchor=D(ins['liquidity_anchor'])*(1+(move if net>0 else -move if net<0 else D(0)))
     if ins.get('institutional_profile'):
      fundamental=self.market_reference(ins);prior=D(ins['liquidity_anchor']);adjusted=next_anchor*D('.94')+fundamental*D('.06')
      # The old ±3% clamp around the FUNDAMENTAL could move the entire book
      # 20% in one update. Bound the existing hourly anchor adjustment instead.
      next_anchor=max(prior*D('.98'),min(prior*D('1.02'),adjusted))
     ins['liquidity_anchor']=str(next_anchor)
     ins['liquidity_anchor_tick']=w['tick']
    anchor=D(ins['liquidity_anchor']);fundamental=self.market_reference(ins)
    center=max(anchor*D('.99'),min(anchor*D('1.01'),anchor*D('.85')+fundamental*D('.15')))
    # All makers observe the same pressure, avoiding mutually crossed maker
    # quotes merely because individual inventories differ.
    net_inventory=sum((D(w['positions'].get(a['account']+':'+sym,{}).get('qty','0')) for a in makers),D(0))
    borrow=max(D(1),D(ins.get('borrow_available',0)))
    flow=sum((D(str(x['qty'])) for x in ins.get('flow_history',[]) if w['tick']-x['tick']<=20),D(0))
    pressure=max(D('-.02'),min(D('.02'),-net_inventory/borrow*D('.012')+flow/max(D(1),capacity*4)*D('.004')))
    center*=1+pressure
    ins['liquidity_center']=str(center)
    spread=(D(ins['institutional_profile']['spread_bps'])/20000 if ins.get('institutional_profile') else D('.0004'))+vol*D('.001')+D(str(w['macro']['stress']))*D('.00002');tick=D(ins.get('tick_size','.01'))
    step=max(D('.0008'),vol*D('.006'))
    offsets=[D(0),D(1),D(3),D(8)] if ins.get('institutional_profile') else [D(0),D(2),D(10),D(32)]
    bid_prices=[max(tick,(center*(1-spread-step*x)).quantize(tick)) for x in offsets]
    ask_prices=[max(b+tick,(center*(1+spread+step*x)).quantize(tick)) for b,x in zip(bid_prices,offsets)]
    # Reserve each quote at its worst ladder price. Covers consume cash but
    # do not need fresh gross-exposure headroom. Long sales need no borrow.
    bid_unit=max(bid_prices)*fx;ask_unit=max(ask_prices)*fx
    bid_cash=cash*share*D('.45');collateral_cash=cash*share*D('.45')
    bid_room=gross_room*share*D('.5')+max(D(0),-held)*bid_unit
    bid_total=max(0,int(min(capacity,bid_cash/(bid_unit*D('1.002')),bid_room/bid_unit)))
    long=max(D(0),held-reserved_long.get((account,sym),D(0)))
    free_borrow=max(D(0),D(ins.get('borrow_available',0))-borrow_used[sym])
    short_capacity=min(free_borrow,collateral_cash/(ask_unit*D('1.6')),gross_room*share*D('.5')/ask_unit)
    ask_total=max(0,int(min(capacity,long+short_capacity)))
    borrowed=max(D(0),D(ask_total)-long);borrow_used[sym]+=borrowed
    bid_left=bid_total;ask_left=ask_total
    # More size sits further from touch: sweeping institutional orders pay
    # nonlinear impact, not the same near-touch price for every share.
    remaining_weight=10
    for level,(bid,ask) in enumerate(zip(bid_prices,ask_prices)):
     weight=level+1
     bq=bid_left*weight//remaining_weight;aq=ask_left*weight//remaining_weight
     bid_left-=bq;ask_left-=aq;remaining_weight-=weight
     for side,price,qty in [('buy',bid,bq),('sell',ask,aq)]:
      if qty<1:continue
      self.append_liquidity_quote(account,sym,side,price,qty,side=='sell' and borrowed>0)
  self.replenish_inventory_offers(reserved_long);self.replenish_value_bids()

 def append_liquidity_quote(self,account,sym,side,price,qty,margin=False,inventory=False):
  from .engine import uid
  tendered=self.public_tender_committed(account,sym)
  if side=='sell' and tendered:
   from .pretrade import pending
   held=D(self.state['positions'].get(account+':'+sym,{}).get('qty',0));lent=sum((D(l['quantity']) for l in self.state.get('stock_loans',[]) if l['lender']==account and l['symbol']==sym),D(0));offered=sum((D(o['remaining']) for o in pending(self,account,sym) if o['side']=='sell'),D(0));qty=min(qty,max(D(0),held-lent-tendered-offered))
   if qty<=0:return
  w=self.state;ins=w['instruments'][sym];w['order_sequence']=w.get('order_sequence',0)+1
  w['orders'].append(dict(id=uid(),sequence=w['order_sequence'],account=account,symbol=sym,side=side,type='limit',qty=amt(qty),remaining=amt(qty),filled='0.00',status='OPEN',time=w['time'],margin=margin,limit=str(price),stop=str(price),trail='5',anchor=ins['price'],triggered=False,oco=None,tif='GTC',maker_quote=True,inventory_quote=inventory))
  return w['orders'][-1]

 def replenish_inventory_offers(self,reserved_long):
  """Voluntary, price-limited portfolio offers from actual NPC longs.

  These are NPC decisions, not new shares or forced liquidation. Quotes may
  remain unfilled and are subject to normal paired settlement and risk checks.
  """
  w=self.state
  bids={}
  for o in w['orders']:
   if o['status'] in ('OPEN','PARTIAL') and o['side']=='buy' and o['type']=='limit':bids[o['symbol']]=max(bids.get(o['symbol'],D(0)),D(o['limit']))
  for actor in w['participants']:
   if actor['strategy'] in ('market_maker','liquidity_provider') or not actor.get('mandate',{}).get('allow_trade',True) or self.is_frozen(actor['account']):continue
   account=actor['account'];equity=max(D(0),D(self.metrics(account)['liquid_equity']))
   target=equity*D(str(actor['risk_budget']))/D(str(max(1,len(w['market_symbols'])/2)))
   for pos in list(w['positions'].values()):
    sym=pos['symbol']
    if pos['account']!=account or sym not in w['market_symbols']:continue
    ins=w['instruments'][sym]
    if ins['status']!='OPEN':continue
    px=D(ins['price']);fx=self.fx_rate(ins['currency']);held=max(D(0),D(pos['qty'])-reserved_long.get((account,sym),D(0)))
    excess=max(D(0),held-target/(px*fx))
    capacity,vol=self.liquidity_profile(ins)
    qty=int(min(held,excess*D('.25'),capacity))
    signal=max(D(0),D(str(actor.get('beliefs',{}).get(sym,0))))
    tick=D(ins.get('tick_size','.01'));premium=D('.001')+vol*D('.006')+signal*D('.02')
    center=D(ins.get('liquidity_center',px))
    if qty>0:
     price=max(bids.get(sym,D(0))+tick,(center*(1+premium)).quantize(tick))
     self.append_liquidity_quote(account,sym,'sell',price,qty,inventory=True)
    # A holder below target may still accept a premium for a small part of
    # its portfolio. This deeper reservation price makes large demand pay
    # to attract natural sellers without confiscating or manufacturing stock.
    opportunistic=int(min(max(D(0),held-qty),min(held,max(D(0),held-excess))*D('.05'),max(D(0),capacity-qty)))
    if opportunistic>0:
     premium=max(D('.01'),vol*D('.06'))+signal*D('.1')
     price=max(bids.get(sym,D(0))+tick,(center*(1+premium)).quantize(tick))
     self.append_liquidity_quote(account,sym,'sell',price,opportunistic,inventory=True)

 def market_event(self,p):
  from .engine import uid
  kind=p.get('kind','earnings');sym=p.get('symbol',self.state['market_symbols'][0]);severity=float(p.get('severity',-.08));delay=int(p.get('delay_hours',0))
  if sym not in self.state['instruments'] or not math.isfinite(severity) or not -.5<=severity<=.5 or not 0<=delay<=720:raise ValueError('Invalid event security, severity or delay')
  if kind not in ('earnings','guidance','credit','policy','rumour','correction','liquidity','acquisition','product'):raise ValueError('Unsupported structured event type')
  event=dict(id=uid(),kind=kind,symbol=sym,severity=severity,credibility=.55 if kind=='rumour' else 1.,created_tick=self.state['tick'],publish_tick=self.state['tick']+delay,publication_time=(datetime.fromisoformat(self.state['time'])+timedelta(hours=delay)).isoformat(),duration_hours=72,affected_entities=[sym],published=False,parent=p.get('parent'),source='VANTAGE / LOCAL MARKET EVENT',consequences=[])
  self.state['events'].append(event);self.publish_events();return event

 def publish_events(self):
  templates={'acquisition':('Acquisition outlook','Published acquisition information affects investor expectations; settlement requires a separate funded corporate transaction.'),'product':('Product development','A published product outcome changes expected future earnings.'),'earnings':('Earnings revision','Cash-flow expectations revised following a local earnings scenario.'),'guidance':('Guidance update','Forward expectations have changed; participants assess the revision against current prices.'),'credit':('Credit conditions deteriorate','A counterparty-specific credit scenario changes risk appetite and financing expectations.'),'policy':('Policy outlook revised','Participants reassess duration and financing costs.'),'rumour':('Unconfirmed market report','Information remains uncertain; credibility and discovery delays vary.'),'correction':('Report clarification','New information revises the preceding market assessment.'),'liquidity':('Liquidity conditions change','Available balance-sheet capacity and withdrawal pressure affect trading conditions.')}
  for event in self.state.get('events',[]):
   if event['published'] or event['publish_tick']>self.state['tick']:continue
   event['published']=True;title,body=templates[event['kind']];ins=self.state['instruments'][event['symbol']];factor=D(str(1+event['severity']*event['credibility']));ins['model_fundamental']=str(D(ins.get('model_fundamental',ins['price']))*factor)
   if event['kind'] in ('earnings','guidance','acquisition','product'):ins['public_earnings_factor']=str(D(ins.get('public_earnings_factor','1'))*factor)
   self.news('Market scenario: '+event['symbol']+' / '+title,body+' This is an internal simulation event, not a genuine company announcement.','MARKET EVENT');item=self.state['news'][0];item.update(event_id=event['id'],symbol=event['symbol'],severity=event['severity'],credibility=event['credibility'],kind=event['kind'],source=event['source'],publication_time=event['publication_time'])
   event['consequences'].append(dict(time=self.state['time'],type='PUBLISHED',price=ins['price']))
   if self.state.get('living_world_version'):
    item.update(publication='The Financial Record',body=body+f"\n\n{event['symbol']} publishes a {event['kind']} revision of {event['severity']*100:+.1f}% to model expectations. The observed execution mark at disclosure is {ins['currency']} {ins['price']}.\n\nThe model fundamental is now {ins['model_fundamental']}. Funded market participants discover public information at different speeds; execution prices, volatility and derivative values remain determined by the existing market and pricing engines. This is a fictional scenario, not a genuine issuer announcement.")
    self.link_story(item,'issuer:'+event['symbol'])

 def ensure_exchange_coverage(self):
  """Extend matched trading using existing maker capital and documented borrow.

  Never endow inventory or change player orders, positions or reference prices.
  Options retain their separate contract execution/settlement model.
  """
  w=self.state
  if not w.get('microstructure_enabled'):return
  symbols=w['market_symbols']
  for sym,ins in w['instruments'].items():
   if sym in symbols or sym in w.get('options',{}) or ins.get('legacy'):continue
   try:
    price=D(ins['price']);self.fx_rate(ins['currency'])
   except (KeyError,ValueError,TypeError,ArithmeticError):continue
   if not price.is_finite() or price<=0:continue
   w.setdefault('matched_since',{}).setdefault(sym,w['time'])
   symbols.append(sym)
   ins.setdefault('model_fundamental',ins['price'])
   ins.setdefault('flow_history',[])
   ins.setdefault('public_short_interest','0')
   ins.setdefault('public_borrow_utilization',0)
   ins.setdefault('borrow_fee_apr',3.)

 def agents_tick(self):
  w=self.state
  if not w.get('microstructure_enabled'):return
  self.ensure_exchange_coverage()
  self.publish_events();self.replenish_books()
  if not self.session_open():return
  for queued in sorted(list(w['orders']),key=lambda o:o.get('sequence',0)):
   if not queued.get('maker_quote') and queued['status'] in ('OPEN','PARTIAL'):self.process_order(queued,bool(queued.get('forced')))
  for actor in w['participants']:
   if actor['strategy'] in ('market_maker','liquidity_provider') or actor['next_tick']>w['tick']:continue
   actor['next_tick']=w['tick']+actor['interval'];rng=random.Random(w['seed']+w['tick']*100003+int(hashlib.sha256(actor['id'].encode()).hexdigest()[:8],16))
   beliefs={}
   known=set(actor['known_events'])
   for event in w['events']:
    if event['published'] and event['publish_tick']+actor['information_delay']<=w['tick']:
     if event['id'] not in known:
      actor['known_events'].append(event['id']);event['consequences'].append(dict(time=w['time'],type='DISCOVERED',participant_class=actor['strategy']))
     age=w['tick']-event['publish_tick'];duration=max(1,event.get('duration_hours',72))
     if age<duration:
      beliefs[event['symbol']]=beliefs.get(event['symbol'],0)+event['severity']*event['credibility']*(1-age/duration)
   # Event flow is temporary information, not an ever-growing permanent mandate.
   # Rebuild it from saved events so existing careers recover without a migration.
   actor['beliefs']={sym:max(-.5,min(.5,signal)) for sym,signal in beliefs.items()}
   # A portfolio review covers several securities rather than spending almost
   # every decision retrying a single inaccessible book. Intervals stay intact.
   # Scale research breadth with exchange size; a shuffled cycle prevents
   # permanently neglected names while retaining strategy/risk decisions.
   breadth=min(len(w['market_symbols']),max(3,math.ceil(math.sqrt(len(w['market_symbols'])))))
   if w.get('market_generation_version')==2 and actor['interval']<=6:breadth=min(len(w['market_symbols']),max(breadth,min(48,math.ceil(len(w['market_symbols'])/4))))
   pending=[s for s in actor.get('review_queue',[]) if s in w['market_symbols']]
   symbols=[]
   while len(symbols)<breadth:
    if not pending:
     pending=list(w['market_symbols']);rng.shuffle(pending)
    sym=pending.pop()
    if sym not in symbols:symbols.append(sym)
   actor['review_queue']=pending
   if actor['beliefs'] and rng.random()<.75:
    focus=max(actor['beliefs'],key=lambda s:abs(actor['beliefs'][s]))
    if focus not in symbols:symbols[0]=focus
   try:
    for index,sym in enumerate(symbols):
     self._institutional_review_slots=len(symbols)-index;self.agent_decision(actor,sym,rng)
   finally:self._institutional_review_slots=1
  self.finish_agents_tick()

 def agent_decision(self,actor,sym,rng):
   if self.institutional_decision(actor,sym,rng):return
   w=self.state;ins=w['instruments'][sym]
   if ins['status']!='OPEN':return
   px=D(ins['price']);signal=actor['beliefs'].get(sym,0);history=ins['history'];momentum=float(px)/max(.00001,history[-min(5,len(history))]['c'])-1;strategy=actor['strategy'];short_util=float(ins.get('public_borrow_utilization',0))
   score=signal*.7+momentum*.3
   if strategy=='momentum':score=momentum*4+signal*.3
   elif strategy in ('value','pension','asset_manager'):score=float(D(ins['reference']['price'])/D(ins.get('model_share_factor',1))*D(str(max(.1,1+signal)))/px-1)+(.005 if strategy!='value' else 0)
   elif strategy=='short_seller':score=min(-.003,signal) if signal<-.015 and short_util<.85 else .002
   elif strategy=='contrarian':score=.025 if short_util>.1 and momentum<0 and rng.random()<.7 else signal*.7
   elif strategy=='relative_value':score=-momentum*.6+signal*.2
   elif strategy=='bank':score=-.03 if w['macro']['stress']>40 else signal*.15
   elif strategy=='retail':score=signal*.4+rng.gauss(0,.007)
   else:score+=rng.gauss(0,.003)
   account=actor['account'];metrics=self.metrics(account);held=D(w['positions'].get(account+':'+sym,{}).get('qty','0'));max_notional=max(D(0),D(metrics['equity']))*D(str(actor['risk_budget']))/D(str(max(1,len(w['market_symbols'])/2)));fx=self.fx_rate(ins['currency']);capacity=max(0,int(max_notional/(px*fx)))
   # Existing inventory is part of the decision: trim overweight longs and
   # cover shorts instead of leaving the finite maker borrow pool locked up.
   weight=held*px*fx/max(D(1),max_notional)
   score-=float(weight)*.02
   if weight>1:score=min(score,-float(weight-1)*.02)
   side='buy' if score>0 else 'sell'
   if abs(score)<.001:return
   qty=max(1,min(max(1,capacity//10),int(capacity*min(.2,abs(score)*2))))
   if side=='buy' and weight>=1:return
   if side=='sell' and strategy in ('pension','asset_manager','retail','bank','value'):
    qty=min(qty,max(0,int(held)))
    if qty<=0:return
   if held<0 and (w['tick']-actor.get('short_open_tick',w['tick'])>=24 or short_util>.85):side='buy';qty=min(qty,max(1,int(abs(held))))
   try:
    order=self.order({'account':account,'symbol':sym,'side':side,'qty':qty,'margin':strategy not in ('pension','asset_manager','retail','bank','value'),'tif':'IOC'})
    actor['last_decision']=dict(time=w['time'],symbol=sym,signal=round(score,6),side=side,qty=qty,status=order['status']);actor.setdefault('short_open_tick',w['tick'])
   except ValueError as exc:actor['last_decision']=dict(time=w['time'],symbol=sym,status='RISK CONSTRAINED',reason=str(exc))
 def finish_agents_tick(self):
  w=self.state;shorts={}
  for position in w['positions'].values():
   if D(position['qty'])<0:shorts[position['symbol']]=shorts.get(position['symbol'],D(0))-D(position['qty'])
  for sym in w['market_symbols']:
   ins=w['instruments'][sym];short=shorts.get(sym,D(0));available=D(ins.get('borrow_available',2000000));util=min(1,float(short/max(D(1),available)))
   ins['public_short_interest']=str(int(short)//1000*1000);ins['public_borrow_utilization']=round(util,2);ins['borrow_fee_apr']=round(3+util*30,2)
  for event in w.get('events',[]):
   if event['published'] and 0<=w['tick']-event['publish_tick']<=event['duration_hours']:
    ins=w['instruments'][event['symbol']];flows=[x for x in ins.get('flow_history',[]) if x['tick']==w['tick']];event['consequences'].append(dict(time=w['time'],type='PUBLIC MARKET',price=ins['price'],buy_volume=sum(max(0,x['qty']) for x in flows),sell_volume=-sum(min(0,x['qty']) for x in flows),estimated_short_interest=ins.get('public_short_interest','0'),borrow_utilization=ins.get('public_borrow_utilization',0)))
    if len(event['consequences'])>120:event['consequences']=[event['consequences'][0]]+event['consequences'][-119:]
  if w['tick']%24==0:
   rng=random.Random(w['seed']+w['tick']*7);self.market_event({'kind':rng.choice(['earnings','guidance','rumour']),'symbol':rng.choice(w['market_symbols']),'severity':round(rng.gauss(0,.035),4)})
  for alert in w.get('alerts',[]):
   if alert['status']=='ARMED':
    px=D(w['instruments'][alert['symbol']]['price']);hit=px>=D(alert['price']) if alert['direction']=='above' else px<=D(alert['price'])
    if hit:alert['status']='TRIGGERED';alert['time']=w['time'];self.message('Market Alert',alert['symbol']+' price threshold reached',f"Execution mark {px} crossed {alert['direction']} {alert['price']}.")
  self.archive_closed_orders()

 def archive_closed_orders(self):
  # Preserve historical instructions in SQLite, including replaced quotes.
  w=self.state
  if not self.db.in_transaction:return
  if len(w['orders'])>3000:
   keep=[]
   for order in w['orders']:
    if order.get('maker_quote') and order['status']=='CANCELLED' and D(order['filled'])==0:continue
    if order['status'] in ('OPEN','PARTIAL','PAUSED') or len(keep)<1000:keep.append(order)
    else:self.db.execute('insert or replace into order_archive values(?,?,?)',(order['id'],w['id'],__import__('json').dumps(order)))
   w['orders']=keep

 def bank_credit_event(self,p):
  loan=next((l for l in self.state['loans'] if l['id']==p['loan']),None)
  if not loan:raise ValueError('Unknown borrower facility')
  recovery=D(str(p.get('recovery_fraction','.5')))
  if not recovery.is_finite() or not 0<=recovery<=1:raise ValueError('Recovery fraction must be 0–1')
  bank=next(b for b in self.state['banks'] if b['id']==loan['bank']);target=(D(loan['balance'])*(1-recovery)).quantize(D('.01'));delta=target-D(loan.get('allowance','0'));loan['allowance']=amt(target);loan['status']='DEFAULT';bank['allowance']=amt(D(bank.get('allowance','0'))+delta);bank['equity']=amt(D(bank['equity'])-delta);self.bank_sync(bank,'Counterparty credit impairment '+loan['id'])
  ratio=D(bank['equity'])/max(D(1),D(bank['cash'])+D(bank['loans'])-D(bank['allowance']))
  if ratio<D('.08'):bank['status']='DISTRESSED'
  self.state['credit']=max(300,self.state['credit']-60);self.audit('credit_event',{'loan':loan['id'],'expected_loss':amt(target),'recovery_fraction':str(recovery)})
  self.news('Credit event: '+bank['name'],f"A defaulted facility causes £{delta:,.2f} additional expected credit loss. Borrower debt remains outstanding; capital constraints affect new lending.",'CREDIT')
  return {'loan':loan['id'],'expected_loss':amt(target),'bank_equity':bank['equity'],'borrower_debt_unchanged':loan['balance']}
