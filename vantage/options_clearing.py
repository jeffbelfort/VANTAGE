"""Prospective cash-secured put liquidity from existing funded market makers.
Legacy contracts/positions retain their original settlement path; only newly
paired units are tracked here. No maker endowment or synthetic cash payout.
"""
import copy
from decimal import Decimal as D
from datetime import datetime
from .integrity import amt

class PutClearingMixin:
 def option_view(self,symbol):
  quote=self.instrument(symbol)
  if self.state.get('microstructure_enabled') and self.state['options'][symbol]['kind']=='put':
   funded=self.put_quote(symbol);quote.update(bid=funded['bid'],ask=funded['ask'],available_liquidity=str(funded['available']),liquidity_model=funded['model'],collateral_per_contract=funded['collateral_per_contract'])
  else:
   stored=self.state['options'][symbol];used=D(stored.get('liquidity_used','0')) if stored.get('liquidity_tick')==self.state['tick'] else D(0);quote['available_liquidity']=str(max(D(0),D(quote['liquidity'])-used));quote['liquidity_model']='Legacy theoretical OTC model; fixed hourly depth, no new institutional counterparty expansion'
  return quote
 def put_collateral(self,account,symbol,qty,cost,mark):
  option=self.state.get('options',{}).get(symbol)
  if qty<0 and option and option.get('kind')=='put':return -qty*D(option['strike'])*100*self.fx_rate(self.state['instruments'][option['underlying']]['currency'])
  return max(D(0),-cost)+abs(qty*mark)*D('.5') if qty<0 else D(0)
 def put_quote(self,symbol):
  option=self.state['options'][symbol];ins=self.instrument(symbol);under=self.state['instruments'][option['underlying']];fx=self.fx_rate(ins['currency']);premium=D(ins['price']);unit=D(option['strike'])*100*fx
  capacity,_=self.liquidity_profile(under);moneyness=abs(D(under['price'])/D(option['strike'])-1);days=max(0,(datetime.fromisoformat(option['expiry'])-datetime.fromisoformat(self.state['time'])).total_seconds()/86400)
  contracts=max(1,int(capacity/100/(1+moneyness*8)/(1+D(str(max(0,days-90)))/365)));used=D(option.get('put_used','0')) if option.get('put_tick')==self.state['tick'] else D(0)
  aggregate_used=D(under.get('put_liquidity_used','0')) if under.get('put_liquidity_tick')==self.state['tick'] else D(0)
  makers=[a['account'] for a in self.state.get('participants',[]) if a['strategy'] in ('market_maker','liquidity_provider') and not self.is_frozen(a['account'])]
  funded=sum((max(D(0),self.available_cash(a))*D('.05')/max(D(1),unit*D('1.01')) for a in makers),D(0));ask=self.quote_price(ins,max(premium*D('1.04'),D(2)/(100*fx)));bid=self.quote_price(ins,max(D('.01'),premium*D('.96')))
  return dict(bid=str(bid),ask=str(ask),available=max(D(0),min(D(contracts)-used,max(D(0),D(int(capacity/100))-aggregate_used),funded).to_integral_value(rounding='ROUND_DOWN')),makers=makers,collateral_per_contract=str(unit),model='Cash-secured puts; existing maker capital, 5% available-cash quote budget, underlying volume/moneyness/tenor')
 def process_secured_put(self,o):
  from .engine import OrderRejected,uid
  option=self.state['options'][o['symbol']];quote=self.put_quote(o['symbol']);buy=o['side']=='buy';price=D(quote['ask'] if buy else quote['bid']);wanted=min(D(o['remaining']),quote['available']);held=D(self.state['positions'].get(o['account']+':'+o['symbol'],{}).get('qty','0'))
  if buy and held<0:
   o['reason']='Cash-secured writing obligations remain reserved until expiry; secondary writer novation is not enabled';return
  if o['type'] in ('limit','stop_limit') and (price>D(o['limit']) if buy else price<D(o['limit'])):
   o['reason']='Price limit prevents execution against funded put quote'
   if o.get('tif') in ('IOC','FOK'):o['status']='CANCELLED'
   return
  tranches=self.state.setdefault('secured_puts',[])
  if not buy:wanted=min(wanted,max(D(0),held),sum((D(t['qty']) for t in tranches if t['buyer']==o['account'] and t['symbol']==o['symbol'] and t['status']=='OPEN'),D(0)))
  fx=self.fx_rate(self.instrument(o['symbol'])['currency'])
  if buy and not o.get('margin'):wanted=min(wanted,max(D(0),((self.available_cash(o['account'])-1)/(price*100*fx*D('1.001'))).to_integral_value(rounding='ROUND_DOWN')))
  if o.get('tif')=='FOK' and wanted<D(o['remaining']):o.update(status='CANCELLED',reason='FOK: funded option depth or premium affordability insufficient');return
  total=D(0)
  # Whole instruction savepoint for FOK; paired fills have their own savepoint.
  before=copy.deepcopy(self.state) if o.get('tif')=='FOK' else None
  if before is not None:self.db.execute('SAVEPOINT put_fok')
  try:
   sources=quote['makers'] if buy else list(dict.fromkeys(t['writer'] for t in tranches if t['buyer']==o['account'] and t['symbol']==o['symbol'] and t['status']=='OPEN'))
   for writer in sources:
    if writer==o['account']:continue
    remaining=wanted-total
    if remaining<=0:break
    if buy and D(self.state['positions'].get(writer+':'+o['symbol'],{}).get('qty','0'))>0:continue
    if buy:amount=min(remaining,(self.available_cash(writer)*D('.05')/(D(quote['collateral_per_contract'])*D('1.01'))).to_integral_value(rounding='ROUND_DOWN'))
    else:amount=min(remaining,sum((D(t['qty']) for t in tranches if t['writer']==writer and t['buyer']==o['account'] and t['symbol']==o['symbol'] and t['status']=='OPEN'),D(0)))
    if amount<=0:continue
    saved={k:copy.deepcopy(self.state.get(k)) for k in ('balances','positions','fills','employees','npcs','secured_puts')};original=copy.deepcopy(o);self.db.execute('SAVEPOINT put_pair')
    other=dict(id='put_quote_'+uid(),account=writer,symbol=o['symbol'],side='sell' if buy else 'buy',type='market',margin=False,_put_writer=True,_option_paired=True,remaining=str(amount),filled='0.00',qty=str(amount));o['_option_paired']=True
    try:
     self.fill(o,amount,price);self.fill(other,amount,price)
     if buy:tranches.append(dict(id=uid(),symbol=o['symbol'],buyer=o['account'],writer=writer,qty=str(amount),status='OPEN',tick=self.state['tick']))
     else:
      left=amount
      for t in tranches:
       if t['writer']!=writer or t['buyer']!=o['account'] or t['symbol']!=o['symbol'] or t['status']!='OPEN':continue
       take=min(left,D(t['qty']));t['qty']=str(D(t['qty'])-take);left-=take
       if D(t['qty'])==0:t['status']='CLOSED'
       if left==0:break
     self.db.execute('RELEASE put_pair')
    except OrderRejected as exc:
     self.db.execute('ROLLBACK TO put_pair');self.db.execute('RELEASE put_pair');self.state.update(saved);o.clear();o.update(original);tranches=self.state['secured_puts'];o['reason']=str(exc);continue
    total+=amount;o['filled']=amt(D(o['filled'])+amount);o['remaining']=amt(D(o['remaining'])-amount)
   if before is not None and D(o['remaining'])>0:
    self.db.execute('ROLLBACK TO put_fok');self.db.execute('RELEASE put_fok');self.state.clear();self.state.update(before);stored=next(x for x in self.state['orders'] if x['id']==o['id']);o.clear();o.update(stored);o.update(status='CANCELLED',reason='FOK: funded counterparties could not complete instruction');self.state['orders']=[o if x['id']==o['id'] else x for x in self.state['orders']];return
   if before is not None:self.db.execute('RELEASE put_fok')
  except Exception:
   if before is not None:self.db.execute('ROLLBACK TO put_fok');self.db.execute('RELEASE put_fok')
   raise
  if total:
   under=self.state['instruments'][option['underlying']];under['put_liquidity_used']=str((D(under.get('put_liquidity_used','0')) if under.get('put_liquidity_tick')==self.state['tick'] else D(0))+total);under['put_liquidity_tick']=self.state['tick']
   option['put_tick']=self.state['tick'];option['put_used']=str(D(option.get('put_used','0'))+total if option.get('put_usage_tick')==self.state['tick'] else total);option['put_usage_tick']=self.state['tick']
  o['status']='FILLED' if D(o['remaining'])==0 else 'CANCELLED' if o.get('tif') in ('IOC','FOK') else 'PARTIAL' if D(o['filled']) else 'OPEN'
  if D(o['remaining'])>0:o.setdefault('reason','Awaiting funded put liquidity / premium capacity; next simulation hour')
 def settle_secured_puts(self):
  for t in self.state.get('secured_puts',[]):
   if t['status']!='OPEN':continue
   option=self.state['options'][t['symbol']]
   if datetime.fromisoformat(option['expiry'])>datetime.fromisoformat(self.state['time']):continue
   symbol=t['symbol'];qty=D(t['qty']);ins=self.instrument(symbol);fx=self.fx_rate(ins['currency']);face=(qty*D(ins['price'])*100*fx).quantize(D('.01'));writer=t['writer'];buyer=t['buyer'];reserve=qty*D(option['strike'])*100*fx;cash=max(D(0),self.cash(writer)-max(D(0),self.restricted_cash(writer)-reserve));paid=min(face,cash);unpaid=face-paid
   claim=self.create_claim(buyer,writer,unpaid,'OPTION SETTLEMENT',t['id'],0,0) if unpaid else None
   for account,signed,payout in ((buyer,qty,face),(writer,-qty,-face)):
    key=account+':'+symbol;pos=self.state['positions'][key];basis=(D(pos['cost'])*abs(signed)/abs(D(pos['qty']))).quantize(D('.01'));direction=D(1) if signed>0 else D(-1);lines={'cash:'+account:paid*direction,'inventory:'+account+':'+symbol:-basis,'pnl:'+account:basis-payout}
    if unpaid:lines[('claim:'+buyer+':'+claim['id']) if signed>0 else ('debt:'+writer+':claim_'+claim['id'])]=unpaid*direction
    self.post('Funded put settlement '+symbol,lines);newqty=D(pos['qty'])-signed
    if newqty:pos.update(qty=amt(newqty),cost=amt(D(pos['cost'])-basis),borrowed=amt(max(D(0),-newqty)))
    else:del self.state['positions'][key]
   t.update(status='SETTLED',paid=amt(paid),unpaid=amt(unpaid),claim=claim['id'] if claim else None,time=self.state['time'])
