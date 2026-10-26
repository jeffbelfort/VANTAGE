"""Player banks use the existing savings, underwriting and loan-servicing engine."""
from decimal import Decimal as D
from .integrity import amt

class PlayerBankingMixin:
 def player_bank(self,entity):
  return next((b for b in self.state['banks'] if b.get('entity')==entity),None)
 def bank_rules(self,p):
  self.authority('personal','govern');capital=D(str(p['minimum_capital']))
  if not capital.is_finite() or not D('10000')<=capital<=D('1000000000'):raise ValueError('Simulation minimum capital must be £10,000–£1 billion')
  self.state['banking_rules']={'minimum_capital':amt(capital)};self.audit('simulation_bank_capital_rule',self.state['banking_rules'].copy());return self.state['banking_rules']
 def refresh_player_banks(self):
  for b in self.state.get('banks',[]):
   if not b.get('entity'):continue
   entity=b['entity'];b['cash']=amt(self.cash(entity));b['loans']=amt(self.balance('credit_asset:'+entity+':bank_loans'));b['allowance']=amt(-self.balance('allowance:'+entity+':bank_loans'));b['deposits']=amt(-self.balance('debt:'+entity+':customer_deposits'))
   metrics=self.metrics(entity);b['equity']=metrics['equity']
   b['other_assets']=amt(D(metrics['equity'])+D(metrics['debt'])-D(b['cash'])-D(b['loans'])+D(b['allowance']));b['other_liabilities']=amt(D(metrics['debt'])-D(b['deposits']))
 def bank_licence(self,p):
  entity=p['entity'];e=self.authority(entity,'govern')
  if e['kind']!='bank' or not e['controlled']:raise ValueError('Select a controlled bank entity')
  if self.is_frozen(entity):raise ValueError('Restricted entity cannot obtain a licence')
  b=self.player_bank(entity)
  if not b:
   b=dict(id=entity,entity=entity,name=e['name'],cash=amt(self.cash(entity)),loans='0.00',allowance='0.00',deposits='0.00',equity=amt(self.cash(entity)),status='DISTRESSED',licence='UNLICENSED',spread=3.,deposit_rate=2.,lending_rate=8.,reserve_ratio=.10,max_loan='10000.00',lending_enabled=True,customers={},interest_income='0.00',interest_expense='0.00',reputation=60,opened=0,closed=0)
   self.state['banks'].append(b)
  self.refresh_player_banks();minimum=D(self.state.get('banking_rules',{}).get('minimum_capital','100000'));assets=D(b['cash'])+D(b['loans'])-D(b['allowance'])+D(b.get('other_assets','0'));ratio=D(b['equity'])/max(D(1),assets)
  if D(b['equity'])<minimum or ratio<D('.08') or self.available_cash(entity)<D(b['deposits'])*D(str(b['reserve_ratio'])):
   b['licence']='UNLICENSED' if b['licence']=='UNLICENSED' else 'INTERVENTION';b['status']='DISTRESSED';self.audit('bank_licence_review',{'entity':entity,'outcome':b['licence'],'capital':b['equity'],'minimum':str(minimum)});return {'status':b['licence'],'reason':'Insufficient operating capital, capital ratio or liquid reserves','required_capital':amt(minimum)}
  b['licence']='AUTHORISED';b['status']='ACTIVE';self.audit('bank_authorised',{'entity':entity,'capital':b['equity'],'minimum':str(minimum)});return {'status':'AUTHORISED'}
 def bank_policy(self,p):
  self.authority(p['entity'],'govern');b=self.player_bank(p['entity'])
  if not b:raise ValueError('Apply for bank authorisation first')
  for field,low,high in [('deposit_rate',0,20),('lending_rate',.01,50),('reserve_ratio',.1,1),('max_loan',1,100000000)]:
   if field in p:
    value=D(str(p[field]))
    if not value.is_finite() or not D(str(low))<=value<=D(str(high)):raise ValueError('Invalid '+field)
    b[field]=amt(value) if field=='max_loan' else float(value)
  if 'lending_enabled' in p:b['lending_enabled']=bool(p['lending_enabled'])
  self.audit('bank_products_updated',dict(p));return b
 def bank_customer_transfer(self,p):
  account=self.account(p);self.authority(account,'payment');b=self.player_bank(p['bank'])
  if not b:raise ValueError('Select a player-owned operating bank')
  return self.bank_customer_cash(b,account,p['amount'],p.get('direction','deposit'),p.get('product','savings'))
 def bank_customer_cash(self,b,account,amount,direction='deposit',product='savings'):
  if account==b['entity'] or product not in ('current','savings'):raise ValueError('Invalid customer or product')
  customer=b['customers'].get(account);held=self.balance('savings:'+account+':'+b['id'])
  if customer and customer['product']!=product and held:raise ValueError('Withdraw the existing product balance before switching products')
  if direction=='deposit' and b['licence']!='AUTHORISED':raise ValueError('Bank is not authorised to accept deposits')
  result=self.savings_transfer({'account':account,'bank':b['id'],'amount':amount,'direction':direction})
  customer=b['customers'][account];customer['product']=product
  closed=self.balance('savings:'+account+':'+b['id'])==0
  if closed and customer['status']!='CLOSED':b['closed']+=1
  customer['status']='CLOSED' if closed else 'ACTIVE'
  self.audit('bank_customer_cash',{'bank':b['id'],'account':account,'product':product,'direction':direction,'amount':amt(amount)})
  return result
 def player_bank_tick(self):
  self.refresh_player_banks();w=self.state
  for b in list(w['banks']):
   if not b.get('entity'):continue
   event='player_bank:'+b['id']+':'+str(w['tick'])
   if self.db.execute('select 1 from scheduled_events where world=? and event=?',(w['id'],event)).fetchone():continue
   self.db.execute('insert into scheduled_events values(?,?,?)',(w['id'],event,w['time']))
   if b['licence']=='UNLICENSED':continue
   assets=D(b['cash'])+D(b['loans'])-D(b['allowance'])+D(b.get('other_assets','0'));capital=D(b['equity']);minimum=D(w.get('banking_rules',{}).get('minimum_capital','100000'))
   if capital<minimum or capital/max(D(1),assets)<D('.08') or self.available_cash(b['entity'])<D(b['deposits'])*D(str(b['reserve_ratio'])) or self.is_frozen(b['entity']):
    if b['licence']!='INTERVENTION':
     b['licence']='INTERVENTION';b['status']='DISTRESSED';b['reputation']=max(0,b['reputation']-10);self.audit('bank_intervention',{'entity':b['entity'],'capital':b['equity'],'cash':b['cash'],'deposits':b['deposits']});self.message('Bank supervision',b['name']+' placed under intervention','New deposits and lending suspended. Claims and deposits remain outstanding. Restore capital/liquidity and reapply; no public bailout is assumed.')
    continue
   # One real customer decision per bank per simulation day; finite cash, no endowments.
   if w['tick']%24:continue
   candidates=['npc_'+n['id'] for n in w['npcs']]+[e['id'] for e in w['entities'].values() if e['kind']=='issuer' and e['status']=='ACTIVE']
   if not candidates:continue
   candidates=sorted(candidates,key=lambda account:__import__('hashlib').sha256((b['id']+'|'+account).encode()).hexdigest())
   account=candidates[(w['tick']//24)%len(candidates)]
   if self.is_frozen(account):continue
   plan=self.bank_customer_plan(account,b);profile=plan['profile']
   customer=b['customers'].get(account);balance=self.balance('savings:'+account+':'+b['id']);competitors=[float(x.get('deposit_rate',max(0,w['macro']['rate']-1))) for x in w['banks'] if x['id']!=b['id'] and x.get('status')!='DISTRESSED'];best=max(competitors,default=0)
   if balance>0 and (float(b['deposit_rate'])+profile['rate_tolerance']<best or b['reputation']<40 or plan['cash_need']>0):
    amount=min(balance,max(D(1),min(balance*D('.25'),plan['cash_need']) if plan['cash_need']>0 else balance*D(str(.05+profile['risk_appetite']*.2))).quantize(D('.01')),D(b['cash']))
    if amount>0:self.bank_customer_cash(b,account,str(amount),'withdraw',customer['product'])
    continue
   if balance==0 and (b['reputation']<40 or float(b['deposit_rate'])+profile['rate_tolerance']<best and plan['loan_need']<=0):continue
   available=self.available_cash(account);amount=plan['deposit']
   if amount>=D(100):
    self.bank_customer_cash(b,account,str(amount),product=customer['product'] if customer else 'savings' if (w['tick']//24)%3 else 'current');customer=b['customers'][account]
   # A borrower need not first have surplus cash to open a savings account.
   # Registration records the application; it does not create a deposit or capital.
   if not customer and plan['loan_need']>0 and b['lending_enabled']:
    customer=dict(account=account,product='current',opened=w['time'],status='APPLICANT',loan_applied=False);b['customers'][account]=customer
   if customer and customer['loan_applied'] and w['tick']-customer.get('last_loan_tick',w['tick'])>=720 and all(l['status']=='REPAID' for l in w['loans'] if l['bank']==b['id'] and l['account']==account):customer['loan_applied']=False
   if customer and plan['loan_need']>0 and balance<=0 and b['lending_enabled'] and not customer['loan_applied'] and float(b['lending_rate'])<=float(w['macro']['rate'])+8:
    customer['loan_applied']=True;customer['last_loan_tick']=w['tick']
    # A small financed consumption/working-capital purchase, subject to existing underwriting.
    principal=min(plan['loan_need'],D(b['max_loan']),max(D(100),self.balance('savings:'+account+':'+b['id'])*D('.75')),max(D(0),D(b['cash'])*D('.04')),max(D(0),D(b['equity'])*D('.20')))
    if principal<100:continue
    result=self.originate_loan({'account':account,'bank':b['id'],'amount':str(principal),'months':12})
    if result.get('approved'):
     customer['status']='BORROWER'
     paid=D(result['loan']['principal']);self.post('Bank customer financed purchase',{'cash:'+account:-paid,'expense:financed_purchase:'+account:paid,'cash:economy_suppliers':paid,'pnl:economy_suppliers':-paid});self.audit('bank_customer_loan',{'bank':b['id'],'account':account,'loan':result['loan']['id'],'purpose':plan['reason'],'customer_identity':profile['id']})
 def player_bank_views(self):
  self.refresh_player_banks();views={}
  for entity in self.state['entities'].values():
   if entity['kind']!='bank' or not entity['controlled']:continue
   b=self.player_bank(entity['id']);minimum=self.state.get('banking_rules',{}).get('minimum_capital','100000')
   if not b:views[entity['id']]={'entity':entity['id'],'licence':'UNLICENSED','required_capital':minimum,'cash':amt(self.cash(entity['id']))};continue
   loans=[l for l in self.state['loans'] if l['bank']==b['id']];assets=D(b['cash'])+D(b['loans'])-D(b['allowance'])+D(b.get('other_assets','0'));income=D(b['interest_income']);expense=D(b['interest_expense'])
   views[entity['id']]={**b,'required_capital':minimum,'available_liquidity':amt(max(D(0),self.available_cash(entity['id'])-D(b['deposits'])*D(str(b['reserve_ratio'])))),'capital_ratio':float(D(b['equity'])/max(D(1),assets)),'accounts':sum(self.balance('savings:'+a+':'+b['id'])>0 for a in self.accounts()),'net_interest_income':amt(income-expense),'net_interest_margin':float((income-expense)/max(D(1),D(b['loans']))),'profit':amt(-self.balance('pnl:'+entity['id'])-sum((D(v) for k,v in self.state['balances'].items() if k.startswith('expense:') and k.endswith(':'+entity['id'])),D(0))),'loan_count':len(loans),'defaults':sum(l['status']=='DEFAULT' for l in loans),'loans_detail':loans,'customer_accounts':[{**c,'identity':self.customer_profile(a).copy(),'available_cash':amt(self.cash(a)),'balance':amt(self.balance('savings:'+a+':'+b['id']))} for a,c in b['customers'].items()]}
  return views
