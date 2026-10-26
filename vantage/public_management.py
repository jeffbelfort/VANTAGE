"""Listed-issuer adapter for existing corporate, workforce and operating controls."""
import copy
from datetime import datetime,timedelta
from decimal import Decimal as D
from .integrity import amt
from .public_tenders import PublicTenderMixin

class PublicManagementMixin(PublicTenderMixin):
 def fund_control_principals(self,account,seen=None):
  seen=set(seen or ())
  if account in seen:return []
  seen.add(account);w=self.state;e=w['entities'].get(account,{});fund=next((f for f in w['funds'] if f['id']==account),None);result={account} if fund else set();issuer=next((i for i in w.get('issuers',{}).values() if i['account']==account),None)
  if issuer:
   view=self.public_ownership(issuer['symbol']);units=D(view['voting_total']);owners={h['account']:h['voting_shares'] for h in view['shareholders']}
  else:units=D((fund or e).get('units',0));owners=(fund or e).get('investors',e.get('owners',{}))
  votes={}
  if units:
   for owner,quantity in owners.items():
    if D(quantity)<=0:continue
    for principal in self.fund_control_principals(owner,seen):votes[principal]=votes.get(principal,D(0))+D(quantity)/units
  result.update(f for f,share in votes.items() if share>D(str(w.get('private_businesses',{}).get(account,{}).get('voting_threshold','.5'))))
  return sorted(result)

 def fund_allows_corporate_control(self,account):
  mandate=self.state['entities'][account]['mandate']
  return bool(mandate.get('allow_corporate_control',mandate.get('related_parties',False)))

 def require_fund_control_permission(self,account):
  for fund in self.fund_control_principals(account):
   if not self.fund_allows_corporate_control(fund):raise ValueError('Fund mandate prohibits corporate control investments for '+self.state['entities'][fund]['name']+'; enable Corporate control investments in Institutions')

 def validate_fund_control_purchase(self,account,symbol,new_quantity,total=None,include_pending=False):
  if symbol not in self.state.get('share_register',{}) or new_quantity<=0:return
  issuer=self.state['issuers'][symbol]
  if account==issuer['account']:return # treasury shares never confer votes
  restricted=[f for f in self.fund_control_principals(account) if not self.fund_allows_corporate_control(f)]
  if not restricted:return
  lent={};pending={}
  for loan in self.state.get('stock_loans',[]):
   if loan['symbol']==symbol:lent[loan['lender']]=lent.get(loan['lender'],D(0))+D(loan['quantity'])
  if include_pending:
   from .pretrade import pending as working
   for order in working(self,None,symbol):
    if order['side']=='buy' and order['account']!=account:pending[order['account']]=pending.get(order['account'],D(0))+D(order['remaining'])
  positions={p['account']:D(p['qty']) for p in self.state['positions'].values() if p['symbol']==symbol};treasury=max(D(0),positions.get(issuer['account'],D(0)));voting_total=(D(issuer['model_shares']) if total is None else total)-treasury
  for principal in restricted:
   votes=max(D(0),new_quantity-lent.get(account,D(0)))
   for holder in set(positions)|set(pending):
    if holder not in (account,issuer['account']) and principal in self.fund_control_principals(holder):votes+=max(D(0),positions.get(holder,D(0))+pending.get(holder,D(0))-lent.get(holder,D(0)))
   if votes>voting_total/2:self.require_fund_control_permission(principal)

 def player_control_set(self,views):
  w=self.state;controlled={'personal'}|{e['id'] for e in w['entities'].values() if e.get('controlled') and e['kind']!='issuer' and (not e.get('owners') or any(f['id']==e['id'] for f in w['funds']))}
  while True:
   previous=len(controlled)
   for e in w['entities'].values():
    if e['kind']=='issuer' or e['id'] in controlled:continue
    units=D(e.get('units',0))
    if units and sum((D(q) for a,q in e.get('owners',{}).items() if a in controlled),D(0))/units>D(str(w.get('private_businesses',{}).get(e['id'],{}).get('voting_threshold','.5'))):controlled.add(e['id'])
   for symbol,view in views.items():
    if view['reconciled'] and sum((D(h['voting_shares']) for h in view['shareholders'] if h['account'] in controlled),D(0))>D(view['voting_total'])/2:controlled.add(view['issuer'])
   if len(controlled)==previous:return controlled

 def player_controls_entity(self,account,seen=None):
  if account=='personal':return True
  seen=set(seen or ())
  if account in seen:return False
  seen.add(account);w=self.state;e=w['entities'].get(account,{})
  issuer=next((i for i in w.get('issuers',{}).values() if i['account']==account),None)
  if issuer:
   view=self.public_ownership(issuer['symbol'])
   return view['reconciled'] and sum((D(h['voting_shares']) for h in view['shareholders'] if self.player_controls_entity(h['account'],seen)),D(0))>D(view['voting_total'])/2
  if any(f['id']==account for f in w.get('funds',[])):return bool(e.get('controlled')) # management authority, not beneficial ownership
  units=D(e.get('units',0));owners=e.get('owners',{})
  if units and owners:
   threshold=D(str(w.get('private_businesses',{}).get(account,{}).get('voting_threshold','.5')))
   return sum((D(q) for owner,q in owners.items() if self.player_controls_entity(owner,seen)),D(0))/units>threshold
  return bool(e.get('controlled'))

 def public_distributable(self,issuer):
  account=issuer['account'];profit=-self.balance('pnl:'+account)-sum((D(v) for k,v in self.ledger_items(account) if k.startswith('expense:') and k.endswith(':'+account)),D(0))-D(issuer.get('dividends_paid_gbp',0))
  return max(D(0),min(profit,self.available_cash(account),D(self.metrics(account)['equity'])))

 def public_share_realised(self,symbol,accounts):
  total=D(0);cache=getattr(self,'_public_share_results',{});self._public_share_results=cache
  for account in accounts:
   key=(self.state['id'],account,symbol);head=self.db.execute("select rowid,id from executions where world=? and json_extract(data,'$.account')=? order by rowid desc limit 1",(self.state['id'],account)).fetchone();head=tuple(head) if head else None
   if key not in cache or cache[key][0]!=head:
    value=sum((D(r[0] or 0) for r in self.db.execute("select json_extract(data,'$.realised') from executions where world=? and json_extract(data,'$.account')=? and json_extract(data,'$.symbol')=?",(self.state['id'],account,symbol))),D(0));cache[key]=(head,value)
   total+=cache[key][1]
  return amt(total)

 def public_management_rows(self):
  rows=[];w=self.state;views={s:self.public_ownership(s) for s in w.get('issuers',{})};controls=self.player_control_set(views)
  for symbol,issuer in w.get('issuers',{}).items():
   id=issuer['account'];view=views[symbol];controlled=id in controls;held=[h for h in view['shareholders'] if h['account'] in controls]
   former=bool(issuer.get('ever_player_controlled')) or any(b['issuer']==id and b['status']=='COMPLETED' and D(b.get('filled',0))>D(view['voting_total'])/2 for b in w.get('public_tenders',[]))
   if not controlled and not held and not former:continue
   ins=self.instrument(symbol);m=self.metrics(id);owners={h['account']:h['registered_shares'] for h in view['shareholders']};history=[]
   for h in issuer.get('operating_history',[]):
    history.append(dict(h,time=(datetime.fromisoformat(w['time'])-timedelta(hours=w['tick']-h['tick'])).isoformat()))
   votes=sum((D(h['voting_shares']) for h in held),D(0));controller=max(held,key=lambda h:D(h['voting_shares']))['account'] if held else None;cost=sum((D(w['positions'][h['account']+':'+symbol]['cost']) for h in held),D(0));quantity=sum((D(h['shares']) for h in held),D(0));value=quantity*D(ins['price'])*self.fx_rate(ins['currency'])
   holder_accounts={h['account'] for h in held}|{b['buyer'] for b in w.get('public_tenders',[]) if b['issuer']==id and b['status']=='COMPLETED' and b['buyer'] in controls};realised=self.public_share_realised(symbol,holder_accounts);received=sum((D(d['entitlements'].get(a,0)) for d in w.get('public_dividends',[]) if d['symbol']==symbol for a in holder_accounts),D(0))
   rows.append(dict(holding_realised=realised,dividends_received=amt(received),id=id,name=ins['name'],symbol=symbol,public=True,sector=issuer['sector'],location=ins.get('country','US'),availability='LISTED',status=w['entities'][id]['status'],controlled=controlled,classification='Controlled' if controlled else 'Minority' if quantity else 'Formerly controlled',owners=owners,units=view['outstanding'],controller=controller,voting_percent=str(votes/max(D(1),D(view['voting_total']))*100),management_authorized=controlled and bool(issuer.get('board_resolution')) and w['entities'][id]['status']=='ACTIVE' and not self.is_frozen(id),cash=m['cash'],liabilities=m['debt'],book_equity=m['equity'],equity_value=amt(D(view['outstanding'])*D(ins['price'])*self.fx_rate(ins['currency'])),annual_revenue=amt(D(issuer['revenue_daily'])*365),annualised_ebitda='0.00',employees=len(self.staff(id)),workforce=self.workforce_view(id),strategy=issuer.get('strategy','balanced'),direction=copy.deepcopy(issuer.get('direction')),daily_investment_budget=issuer.get('daily_investment_budget','0.00'),management_quality='Not separately modelled',history=history,last_result=history[-1] if history else None,engagements=[],holding_cost=amt(cost),holding_value=amt(value),holding_unrealised=amt(value-cost),dividends_paid=issuer.get('dividends_paid_gbp','0.00'),distributable=amt(self.public_distributable(issuer)),sale_orders=[dict(id=o['id'],qty=o['qty'],remaining=o['remaining'],filled=o['filled'],status=o['status']) for o in w['orders'] if o['symbol']==symbol and o['side']=='sell' and o['account'] in [h['account'] for h in held] and o['status'] in ('OPEN','PARTIAL','PAUSED')]))
  return rows

 def public_operating_manage(self,p):
  id=p['entity'];e=self.authority(id,'govern');issuer=next(i for i in self.state['issuers'].values() if i['account']==id)
  if self.is_frozen(id):raise ValueError('Restricted issuer cannot change policy')
  if p.get('management_quality') is not None:raise ValueError('Recruit named executives through Employees; no unmodelled executive quality purchase')
  if p.get('strategy'):
   strategy=p['strategy']
   if strategy not in ('balanced','growth','efficiency'):raise ValueError('Unknown operating strategy')
   issuer['strategy']=strategy;issuer['direction']=dict(strategy=strategy,set_tick=self.state['tick'],set_time=self.state['time'],set_by='Authorised board management',status='ACTIVE',effects='Growth deploys approved investment while retaining operating liquidity; Efficiency directs paid productivity investment; Balanced retains capacity.',observed='Awaiting daily operating cycle')
  if 'daily_investment_budget' in p:
   value=D(str(p['daily_investment_budget']))
   if not value.is_finite() or value<0 or value>D(e['payment_limit']):raise ValueError('Daily investment budget exceeds board payment authority')
   issuer['daily_investment_budget']=amt(value)
  self.audit('public_operating_policy',copy.deepcopy(p));return issuer

 def public_productive_investment(self,p):
  from .engine import positive
  id=p['entity'];e=self.authority(id,'payment');self.authority(id,'govern');issuer=next(i for i in self.state['issuers'].values() if i['account']==id);amount=positive(p['amount'])
  if self.is_frozen(id) or amount>self.available_cash(id) or amount>D(e['payment_limit']):raise ValueError('Investment exceeds unrestricted company cash or board payment authority')
  return self.public_investment_post(issuer,amount)

 def public_investment_post(self,issuer,amount):
  id=issuer['account'];supplier=self.ma_account('suppliers');self.post('Listed company productive investment '+id,{'cash:'+id:-amount,'productive:'+id:amount,'cash:'+supplier:amount,'pnl:'+supplier:-amount});field='productivity_investment' if issuer.get('strategy')=='efficiency' else 'capacity_investment';issuer[field]=amt(D(issuer.get(field,0))+amount);self.audit('public_productive_investment',dict(entity=id,amount=amt(amount),purpose=field));return issuer

 def public_pay_dividend(self,resolution):
  issuer=self.state['issuers'][resolution['symbol']];account=issuer['account'];amount=D(resolution['terms']['amount']);view=self.public_ownership(issuer['symbol'])
  if not issuer.get('board_resolution'):raise ValueError('Elect a board before distributing issuer profits')
  if not view['reconciled']:raise ValueError('Dividend voting register is unreconciled')
  holders=[h for h in view['shareholders'] if h['account']!=account and D(h['registered_shares'])>0];total=sum((D(h['registered_shares']) for h in holders),D(0))
  if total<=0:raise ValueError('No eligible dividend shares')
  if 'per_share' in resolution['terms']:
   amount=D(resolution['terms']['per_share'])*total
   if amount>D(resolution['terms']['amount']) or amount>self.public_distributable(issuer):raise ValueError('Share count or funding changed; propose a fresh dividend resolution')
  if amount>self.public_distributable(issuer):raise ValueError('Dividend exceeds retained realised profits, unrestricted cash or solvent equity')
  cents=int(amount*100);allocated={h['account']:int(D(cents)*D(h['registered_shares'])/total) for h in holders};remainder=cents-sum(allocated.values())
  for h in sorted(holders,key=lambda h:(-(D(cents)*D(h['registered_shares'])/total-allocated[h['account']]),h['account']))[:remainder]:allocated[h['account']]+=1
  record=dict(id=resolution['id'],symbol=issuer['symbol'],record_date=self.state['tick'],amount=amt(amount),per_share=str(amount/total),entitlements={a:amt(D(c)/100) for a,c in allocated.items()},status='PAID')
  if any(d['id']==record['id'] for d in self.state.get('public_dividends',[])):raise ValueError('Dividend already paid')
  lines={'cash:'+account:-amount,'equity:'+account:amount}
  for holder,c in allocated.items():
   paid=D(c)/100
   if paid:lines['cash:'+holder]=paid;lines['pnl:'+holder]=-paid
  self.post('Approved shareholder dividend '+issuer['symbol']+' / '+record['id'],lines)
  # On-loan title receives the issuer payment at its registered owner. The short
  # borrower owes the lender an equivalent contractual payment, not issuer cash.
  for loan in self.state.get('stock_loans',[]):
   if loan['symbol']!=issuer['symbol'] or D(loan['quantity'])<=0:continue
   due=(D(loan['quantity'])*amount/total).quantize(D('.01'))
   if not due:continue
   borrower=loan['borrower'];lender=loan['lender'];claim=self.create_claim(lender,borrower,due,'DIVIDEND_EQUIVALENT','Stock-loan dividend equivalent '+record['id'],months=0);self.post('Accrued stock-loan dividend equivalent '+record['id'],{'expense:dividend_equivalent:'+borrower:due,'debt:'+borrower+':claim_'+claim['id']:-due,'claim:'+lender+':'+claim['id']:due,'pnl:'+lender:-due});cash=min(due,self.available_cash(borrower))
   if cash:self.settle_claim_cash(claim,cash,'Stock-loan dividend equivalent settlement')
  self.state.setdefault('public_dividends',[]).append(record);issuer['dividends_paid_gbp']=amt(D(issuer.get('dividends_paid_gbp',0))+amount);resolution['distribution']=record['id'];self.market_event({'symbol':issuer['symbol'],'kind':'guidance','severity':-min(.5,float(amount/total/max(D('.01'),D(self.instrument(issuer['symbol'])['price'])*self.fx_rate(self.instrument(issuer['symbol'])['currency']))))});self.audit('public_dividend_paid',copy.deepcopy(record));return record
