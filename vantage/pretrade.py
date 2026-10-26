"""Read-only order admission and commitments over existing holdings/cash/loans.
Reservations are derived from working instructions under Engine's transaction lock;
no cash, shares or loan records are created until actual settlement.
"""
from decimal import Decimal as D
from .integrity import amt
WORKING=('OPEN','PARTIAL','PAUSED')

def order_cash(engine,o,quantity=None):
 q=D(o['remaining']) if quantity is None else max(D(0),D(quantity));ins=engine.instrument(o['symbol'])
 price=D(o['limit']) if o['type'] in ('limit','stop_limit') else D(ins['price']);unit=price*D(ins.get('multiplier',1))*engine.fx_rate(ins['currency']);fee=max(D(1),(q*unit*D('.0005')).quantize(D('.01'))) if q else D(0)
 intent=o.get('intent')
 if intent=='buy_to_cover':return D(0)
 if o['side']=='buy':return q*unit*(D('.5') if o.get('margin') else D(1))+fee
 if o.get('margin'):
  held=max(D(0),D(engine.state['positions'].get(o['account']+':'+o['symbol'],{}).get('qty',0)))
  q=q if intent=='sell_short' else max(D(0),q-held)
  return q*unit*D('.5')+fee if q else D(0)
 return D(0)

def pending(engine,account=None,symbol=None,exclude=None):
 active={o['id']:o for o in engine.state['orders'] if o['status'] in WORKING}
 banned={exclude};own=active.get(exclude)
 if own and own.get('oco') in active and active[own['oco']].get('oco')==exclude:banned.add(own['oco'])
 result=[];seen=set()
 for o in active.values():
  if o['id'] in banned or o['id'] in seen or account is not None and o['account']!=account or symbol is not None and o['symbol']!=symbol:continue
  peer=active.get(o.get('oco'))
  if peer and peer.get('oco')==o['id'] and peer['account']==o['account'] and peer['symbol']==o['symbol'] and peer['side']==o['side']:
   seen.add(peer['id']);result.append(max((o,peer),key=lambda r:D(r['remaining'])))
  else:result.append(o)
 return result

def validate(engine,p,account,ins,qty,exclude=None):
 side=p.get('side','buy');margin=bool(p.get('margin',False));intent=p.get('intent');symbol=ins['symbol'];held=D(engine.state['positions'].get(account+':'+symbol,{}).get('qty',0));orders=pending(engine,account,symbol,exclude)
 if side not in ('buy','sell'):raise ValueError('Invalid order side')
 if intent not in (None,'buy_long','sell_long','sell_short','buy_to_cover'):raise ValueError('Unknown order intent')
 if intent and side!=('sell' if intent in ('sell_short','sell_long') else 'buy'):raise ValueError('Order side conflicts with explicit intent')
 if intent is None:
  intent='buy_to_cover' if side=='buy' and held<0 else 'buy_long' if side=='buy' else 'sell_short' if margin and held<=0 else 'sell_long'
 if intent=='sell_short' and not margin:raise ValueError('Sell Short requires margin and stock borrowing enabled')
 if intent=='sell_long':margin=False
 if intent=='buy_to_cover':margin=True
 if engine.is_frozen(account):raise ValueError(engine.restriction_message(account,'Trading'))
 entity=engine.state.get('entities',{}).get(account,{})
 if entity.get('status','ACTIVE')!='ACTIVE':raise ValueError('Account is not active for trading')
 if ins['status']!='OPEN':raise ValueError('Trading halt / security not open')
 if not engine.session_open() and p.get('tif','GTC') in ('IOC','FOK'):raise ValueError('Market closed — immediate orders cannot be submitted')
 lent=sum((D(l['quantity']) for l in engine.state.get('stock_loans',[]) if l['lender']==account and l['symbol']==symbol),D(0))
 sales=sum((D(o['remaining']) for o in orders if o['side']=='sell' and not o.get('margin')),D(0));available=max(D(0),held-lent-sales-engine.public_tender_committed(account,symbol))
 if side=='sell' and not margin and qty>available:raise ValueError('Insufficient shares — use Sell Short with margin enabled. Available uncommitted shares: '+str(available))
 if intent=='sell_short' and held>0:raise ValueError('Sell existing long holdings before opening a separate short; this account uses net positions')
 if intent=='buy_long' and held<0:raise ValueError('Use Buy to Cover to close the existing short first')
 covers=sum((D(o['remaining']) for o in orders if o['side']=='buy' and (o.get('intent')=='buy_to_cover' or held<0)),D(0))
 if intent=='buy_to_cover' and (held>=0 or qty>max(D(0),-held-covers)):raise ValueError('Buy to Cover exceeds the uncommitted existing short position')
 new=held+(qty if side=='buy' else -qty)
 if side=='buy':engine.validate_fund_control_purchase(account,symbol,new+sum((D(o['remaining']) for o in orders if o['side']=='buy'),D(0)),include_pending=True)
 if new<0 and D(ins.get('multiplier',1))!=1:raise ValueError('Short option writing is not supported by this order workflow')
 short_need=max(D(0),-new)-max(D(0),-held)
 if short_need>0:
  if not margin:raise ValueError('Insufficient shares — use Sell Short with margin enabled')
  committed={}
  for o in pending(engine,None,symbol,exclude):
   if o['symbol']==symbol and o['side']=='sell' and o.get('margin') and o['status'] in WORKING and o['id']!=exclude:committed[o['account']]=committed.get(o['account'],D(0))+D(o['remaining'])
  reserved=sum((max(D(0),q-max(D(0),D(engine.state['positions'].get(a+':'+symbol,{}).get('qty',0)))) for a,q in committed.items()),D(0))
  if engine.state.get('public_ownership_version') and symbol in engine.state.get('share_register',{}):supply=sum((q for _,q in engine.stock_lending_sources(symbol,account)),D(0))
  else:supply=max(D(0),D(ins.get('borrow_available',0))-sum((max(D(0),-D(pos['qty'])) for pos in engine.state['positions'].values() if pos['symbol']==symbol),D(0)))
  if short_need>max(D(0),supply-reserved):raise ValueError('Stock borrow unavailable: insufficient consenting uncommitted lender inventory')
 price=D(p.get('limit',ins['price'])) if p.get('type','market') in ('limit','stop_limit') else D(ins['price']);unit=price*D(ins.get('multiplier',1))*engine.fx_rate(ins['currency']);fee=max(D(1),(qty*unit*D('.0005')).quantize(D('.01')))
 m=engine.metrics(account);cash=engine.cash(account)-D(m['restricted_cash'])
 excluded=next((o for o in engine.state['orders'] if o['id']==exclude),None)
 if excluded:cash+=order_cash(engine,excluded)
 if side=='buy' and held>=0 and not margin and qty*unit+fee>cash:raise ValueError('Insufficient buying power after working-order reservations')
 if short_need>0 and short_need*unit*D('.5')+fee>cash:raise ValueError('Insufficient margin: 50% initial short collateral plus fees is required')
 credit=D(0)
 if side=='buy' and margin and held>=0:
  if qty*unit*D('.5')+fee>cash:raise ValueError('Insufficient margin after working-order collateral reservations')
  committed_credit=sum((D(o.get('credit_reserved',0))*D(o['remaining'])/D(o['qty']) for o in engine.state['orders'] if o['status'] in WORKING and o['id']!=exclude),D(0))
  credit=max(D(0),qty*unit+fee-cash)
  if credit>max(D(0),engine.cash('prime')-committed_credit):raise ValueError('Prime broker has insufficient uncommitted financing liquidity')
 if intent=='buy_to_cover':
  release=engine.put_collateral(account,symbol,held,D(engine.state['positions'][account+':'+symbol]['cost']),D(ins['price'])*engine.fx_rate(ins['currency']))*qty/abs(held)
  if engine.cash(account)-D(m['restricted_cash'])+release+ (order_cash(engine,excluded) if excluded else D(0))<qty*unit+fee:raise ValueError('Insufficient cash and released collateral to cover at the current price')
 if abs(new)>abs(held):
  policy=engine.state.get('account_limits',{}).get(account,{});equity=max(D(0),D(m['liquid_equity'])-fee);gross=D(m['gross'])-abs(held*D(ins['price'])*D(ins.get('multiplier',1))*engine.fx_rate(ins['currency']))+abs(new*unit)
  exposure=sum((D(o['remaining'])*D(engine.instrument(o['symbol'])['price'])*D(engine.instrument(o['symbol']).get('multiplier',1))*engine.fx_rate(engine.instrument(o['symbol'])['currency']) for o in pending(engine,account,exclude=exclude) if not o.get('maker_quote') and (o['side']=='buy' and o.get('intent')!='buy_to_cover' or o.get('intent')=='sell_short')),D(0))
  if gross+exposure>equity*D(policy.get('max_leverage',2)):raise ValueError('Insufficient margin / desk gross-exposure headroom including working orders')
  if abs(new*unit)>equity*D(policy.get('single_name_pct',200))/100:raise ValueError('Single-name concentration limit exceeded')
 return dict(credit_reserved=amt(credit),intent=intent,margin=margin,reduce_only=intent=='buy_to_cover' or bool(p.get('reduce_only')))
