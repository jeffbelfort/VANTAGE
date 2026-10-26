"""Explicit investor books and fixed-NAV redemption liabilities. No fictional cash credits."""
from decimal import Decimal as D,ROUND_DOWN
from .integrity import amt

class FundSystemMixin:
 def migrate_fund_system(self):
  w=self.state
  if w.get('fund_system_version',0)>=1:return
  for n in w['npcs']:
   assets={'npc:'+n['id']+':cash':D(n['wealth'])}
   for f in w['funds']:
    units=D(f['units']);owned=D(f['investors'].get(n['id'],'0'))
    if owned and units:assets['npc:'+n['id']+':investment:'+f['id']]=(max(D(0),D(self.metrics(f['id'])['equity']))*owned/units).quantize(D('.01'))
   assets['npc:'+n['id']+':equity']=-sum(assets.values(),D(0));self.post('Investor subledger opening baseline '+n['id'],assets)
   n.setdefault('horizon_days',30 if n['risk']<.4 else 7);n.setdefault('liquidity_need',.02 if n['risk']<.4 else .05);n.setdefault('withdrawal_sensitivity',1-n['risk']);n.setdefault('last_observation',w['tick'])
  w['redemptions']=[];w['fund_system_version']=1
  self.audit('fund_system_v1',{'policy':'Prospective investor cash/claim subledgers; pre-existing holdings fair-value baseline; no historic player balances changed'})

 def npc_subscription_book(self,n,f,amount):
  if not self.state.get('fund_system_version'):return
  self.post('Investor cash settlement '+n['id']+' to '+f['id'],{'npc:'+n['id']+':cash':-amount,'npc:'+n['id']+':investment:'+f['id']:amount})

 def npc_claim_release(self,n,f,units,amount,payable=None):
  owned=D(f['investors'][n['id']]);key='npc:'+n['id']+':investment:'+f['id'];basis=(self.balance(key)*units/owned).quantize(D('.01'))
  destination='npc:'+n['id']+(':receivable:'+payable if payable else ':cash')
  self.post('Investor claim conversion '+n['id']+' / '+f['id'],{destination:amount,key:-basis,'npc:'+n['id']+':pnl':basis-amount})

 def redemption_request(self,p):
  from .engine import uid,positive
  self.migrate_fund_system();f=next(f for f in self.state['funds'] if f['id']==p['fund']);investor=p['investor'];units=D(str(p['units']))
  if not units.is_finite() or units<=0 or units>D(f['investors'].get(investor,'0')):raise ValueError('Invalid or unavailable redemption units')
  if self.is_frozen(f['id']):raise ValueError(self.restriction_message(f['id'],'Redemption'))
  if investor not in ['personal']+[n['id'] for n in self.state['npcs']]:raise ValueError('Investor cannot receive redemptions through this facility')
  nav=D(self.metrics(f['id'])['equity']);total=D(f['units']);amount=(nav*units/total).quantize(D('.01'),rounding=ROUND_DOWN) if total else D(0)
  if amount<=0:raise ValueError('No positive actual NAV is available; reported value is not redeemable')
  request=dict(id=uid(),fund=f['id'],investor=investor,units=str(units),amount=amt(amount),paid='0.00',remaining=amt(amount),status='PENDING',time=self.state['time'],requested_tick=self.state['tick'],eligible_tick=max(self.state['tick']+int(f.get('terms',{}).get('notice_hours',0)),f['lock_until']),fee='0.00',valuation='Fixed actual NAV at acceptance; cash rounded down to cents; becomes a creditor obligation',settlements=[])
  self.post('Redemption accepted '+request['id']+' / '+investor,{'equity:'+f['id']:amount,'debt:'+f['id']+':redemption:'+request['id']:-amount})
  if investor=='personal':
   key='investment:personal:'+f['id'];basis=(self.balance(key)*units/D(f['investors']['personal'])).quantize(D('.01'))
   self.post('Personal redemption receivable '+request['id'],{'receivable:personal:'+f['id']:amount,key:-basis,'pnl:personal':basis-amount})
  else:self.npc_claim_release(next(n for n in self.state['npcs'] if n['id']==investor),f,units,amount,request['id'])
  f['units']=str(total-units);f['investors'][investor]=str(D(f['investors'][investor])-units);self.state['redemptions'].append(request)
  self.audit('redemption_request',request.copy());self.settle_redemptions(f['id']);return self.redemption_receipt(request)

 def redemption_receipt(self,r):
  return {**r,'destination_account':'personal' if r['investor']=='personal' else 'investor:'+r['investor'],'personal_cash':amt(self.cash()),'personal_net_assets':self.metrics()['equity'],'fund_nav':self.metrics(r['fund'])['equity']}

 def settle_redemptions(self,fund=None):
  for r in self.state.get('redemptions',[]):
   if r['status']=='SETTLED' or (fund and r['fund']!=fund) or self.state['tick']<r['eligible_tick']:continue
   f=next(f for f in self.state['funds'] if f['id']==r['fund'])
   if self.is_frozen(f['id']) or f.get('suspended'):r['status']='SUSPENDED';continue
   day=self.state['tick']//24
   if f.get('gate_day')!=day:
    f['gate_day']=day;f['gate_paid']='0.00';f['gate_base']=amt(max(D(0),D(self.metrics(f['id'])['equity']))+sum((D(q['remaining']) for q in self.state.get('redemptions',[]) if q['fund']==f['id']),D(0)))
   gate=max(D(0),D(f['gate_base'])*D(str(f.get('gate_daily_pct',100)))/100-D(f['gate_paid']))
   liquid=max(D(0),self.available_cash(f['id'])-D(f['gate_base'])*D(str(f.get('terms',{}).get('side_pocket_pct',0)))/100)
   amount=min(D(r['remaining']),liquid,gate).quantize(D('.01'))
   if amount<=0:
    r['status']='GATED' if gate<=0 else 'AWAITING LIQUIDITY';continue
   lines={'cash:'+f['id']:-amount,'debt:'+f['id']+':redemption:'+r['id']:amount}
   if r['investor']=='personal':lines.update({'cash:personal':amount,'receivable:personal:'+f['id']:-amount})
   else:
    prefix='npc:'+r['investor'];lines.update({prefix+':cash':amount,prefix+':receivable:'+r['id']:-amount});n=next(n for n in self.state['npcs'] if n['id']==r['investor']);n['wealth']=amt(D(n['wealth'])+amount)
   self.post('Redemption cash settlement '+r['id']+' to '+r['investor'],lines)
   r['paid']=amt(D(r['paid'])+amount);r['remaining']=amt(D(r['remaining'])-amount);r['status']='SETTLED' if D(r['remaining'])==0 else 'PARTIAL'
   r['settlements'].append(dict(time=self.state['time'],amount=amt(amount),destination=r['investor']));f['gate_paid']=amt(D(f['gate_paid'])+amount)
   recipient='Personal account' if r['investor']=='personal' else next((n['name'] for n in self.state['npcs'] if n['id']==r['investor']),r['investor'])
   status='Paid in full' if r['status']=='SETTLED' else 'Partly paid'
   self.message('Fund Operations','Investor payment: '+status,f"{f['name']} paid £{amount:,.2f} to {recipient}. Total paid on this request: £{D(r['paid']):,.2f}. Left to pay: £{D(r['remaining']):,.2f}. Receipt {r['id']}.")

 def fund_policy(self,p):
  f=next(f for f in self.state['funds'] if f['id']==p['fund'])
  if 'gate_daily_pct' in p:
   gate=D(str(p['gate_daily_pct']))
   if not gate.is_finite() or not 0<=gate<=100:raise ValueError('Daily gate must be 0–100%')
   f['gate_daily_pct']=float(gate)
  if 'suspended' in p:f['suspended']=bool(p['suspended'])
  if 'auto_liquidate' in p:f['auto_liquidate']=bool(p['auto_liquidate'])
  if 'promised_apr' in p:
   rate=D(str(p['promised_apr']))
   if not rate.is_finite() or not 0<=rate<=100:raise ValueError('Promise must be 0–100% annual')
   f['promised_apr']=str(rate);f.setdefault('promise_residuals',{})
  if p.get('liquidate'):
   f['liquidating']=True;f['suspended']=False
   for o in self.state['orders']:
    if o['account']==f['id'] and o['status'] in ('OPEN','PARTIAL'):o['status']='CANCELLED'
  self.audit('fund_policy',dict(p));return f

 def fund_obligations_tick(self):
  self.settle_redemptions()
  for f in self.state['funds']:
   pending=sum((D(r['remaining']) for r in self.state.get('redemptions',[]) if r['fund']==f['id']),D(0));f['pending_redemptions']=amt(pending)
   fm=self.metrics(f['id']);f['solvency']='INSOLVENT' if D(fm['equity'])<0 else 'LIQUIDATING' if f.get('liquidating') else 'ACTIVE' if D(f['units'])>0 else 'EMPTY'
   if self.is_frozen(f['id']):continue
   if f.get('liquidating') or (pending>self.available_cash(f['id']) and f.get('auto_liquidate',False)):
    for pos in list(self.state['positions'].values()):
     if pos['account']!=f['id']:continue
     if any(o['account']==f['id'] and o['symbol']==pos['symbol'] and o['status'] in ('OPEN','PARTIAL') for o in self.state['orders']):continue
     try:self.order({'account':f['id'],'symbol':pos['symbol'],'side':'sell' if D(pos['qty'])>0 else 'buy','qty':str(abs(D(pos['qty']))),'margin':True})
     except ValueError as exc:self.message('Fund Liquidity','Liquidation instruction constrained',f['name']+': '+str(exc)+'. The creditor obligation remains outstanding.')
    self.settle_redemptions(f['id'])

 def promised_returns(self):
  from .engine import uid
  for f in self.state['funds']:
   rate=D(f.get('promised_apr','0'));total=D(f['units'])
   if rate<=0 or total<=0:continue
   for investor,owned in f['investors'].items():
    if investor not in ['personal']+[n['id'] for n in self.state['npcs']]:continue
    basis=self.balance('investment:personal:'+f['id']) if investor=='personal' else self.balance('npc:'+investor+':investment:'+f['id']);residuals=f.setdefault('promise_residuals',{});raw=basis*rate/D(36500)+D(residuals.get(investor,'0'));amount=raw.quantize(D('.01'));residuals[investor]=str(raw-amount)
    if amount<=0:continue
    id=uid();r=dict(id=id,fund=f['id'],investor=investor,units='0',amount=amt(amount),paid='0.00',remaining=amt(amount),status='PENDING',time=self.state['time'],requested_tick=self.state['tick'],eligible_tick=self.state['tick'],fee='0.00',kind='CONTRACTUAL RETURN',settlements=[])
    recipient='receivable:personal:'+f['id'] if investor=='personal' else 'npc:'+investor+':receivable:'+id;income='pnl:personal' if investor=='personal' else 'npc:'+investor+':pnl'
    self.post('Contractual promised return '+id,{'expense:promises:'+f['id']:amount,'debt:'+f['id']+':redemption:'+id:-amount,recipient:amount,income:-amount});self.state['redemptions'].append(r)

 def investor_behaviour(self):
  return self.grounded_investor_behaviour()
