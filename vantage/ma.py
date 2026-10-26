"""Finite private-business economy and negotiated acquisitions on existing ledgers.
Model forecasts are explicitly separate from actual posted operating history.
"""
import copy,hashlib
from decimal import Decimal as D
from .integrity import amt

INDUSTRIES={
 'technology':('.24','8'), 'manufacturing':('.14','6'), 'retail':('.08','5'),
 'telecommunications':('.22','7'), 'healthcare':('.19','8'), 'energy':('.16','5'),
 'logistics':('.12','6'), 'property':('.28','8'), 'consumer goods':('.13','6'),
 'professional services':('.20','6'), 'financial services':('.23','7'), 'hospitality':('.11','5')}
STRATEGIES={'balanced':('1','1'),'growth':('1.08','1.12'),'efficiency':('.96','.90')}

from .company_operations import CompanyOperationsMixin

class MAMixin(CompanyOperationsMixin):
 def ma_generate(self,migration=False):
  w=self.state
  if w.get('private_businesses'):raise ValueError('Corporate economy already exists')
  if w['tick']!=0 and not migration:raise ValueError('Use the explicit audited M&A migration for an existing world')
  reserved={'private_'+str(i) for i in range(48)}|{'corporate_owner_'+str(i) for i in range(8)}|{'corporate_lender'}
  if reserved.intersection(w['entities']) or any(reserved.intersection(k.split(':')[1:]) for k in w['balances']):raise ValueError('M&A account identifiers already exist; refusing to overwrite')
  if migration:w['ma_economy_accounts']={'households':'ma_migration_households','suppliers':'ma_migration_suppliers'}
  w.update(private_businesses={},ma_offers=[],ma_history=[],ma_facilities=[])
  def entity(id,name,kind,owners=None,capital=0):
   w['entities'][id]=dict(id=id,name=name,kind=kind,controlled=False,parent=next(iter(owners or {}),None),status='ACTIVE',owners=owners or {},units='1000000' if owners else '0',directors=['ai_board'],signatories={'ai_board':['govern','payment','disclose']},payment_limit=amt(capital),controls=1,mandate={'related_parties':True,'sectors':[]})
  for i in range(8):
   id='corporate_owner_'+str(i);entity(id,['Northstar Private Capital','Atlas Industrial Group','Cedar Family Enterprises','Meridian Growth Partners','Pioneer Regional Holdings','Harbour Investment Group','Summit Strategic Capital','Independent Founders Trust'][i],'holding');cash=D(5000000000)*(i+1);self.post('Independent corporate owner opening capital',{'cash:'+id:cash,'equity:'+id:-cash})
   distribution=cash*D('.02');self.post('Corporate-owner opening household capital distribution',{'cash:'+id:-distribution,'equity:'+id:distribution,'cash:'+self.ma_account('households'):distribution,'equity:'+self.ma_account('households'):-distribution})
   w['entities'][id]['payment_limit']=amt(cash*D('.1'))
  entity('corporate_lender','Corporate Acquisition Credit Partners','holding');self.post('Acquisition lender opening capital',{'cash:corporate_lender':D(15000000000),'equity:corporate_lender':D(-15000000000)})
  locations=['United Kingdom','Germany','United States','France','Japan','Singapore'];prefix=['Alder','Beacon','Cobalt','Delta','Elm','Falcon','Granite','Hawthorn','Inver','Juniper','Keystone','Linden']
  for i in range(48):
   sector=list(INDUSTRIES)[i%12];id='private_'+str(i);owner='corporate_owner_'+str(i%8);margin,multiple=map(D,INDUSTRIES[sector]);scale=[D(1000000),D(18000000),D(150000000),D(1800000000)][i//12];variation=D(80+int(hashlib.sha256((str(w['seed'])+id).encode()).hexdigest()[:6],16)%41)/100;assets=(scale*variation).quantize(D('.01'));cash=(assets*D('.15')).quantize(D('.01'));productive=assets-cash;name=prefix[i%12]+' '+sector.title()+' '+['Local','Regional','National','International'][i//12]
   entity(id,name,'company',{owner:'1000000'},cash*D('.25'));self.post('Independent business opening equity '+name,{'cash:'+id:cash,'productive:'+id:productive,'equity:'+id:-assets,'holding:'+owner+':'+id:assets,'capital_reserve:'+owner:-assets})
   revenue=(assets*D('1.4')).quantize(D('.01'));employees=max(3,int(revenue/D(150000)));payroll=(revenue*D('.24')).quantize(D('.01'));materials=(revenue*(1-margin)-payroll).quantize(D('.01'));availability=['FOR_SALE','OPEN_TO_APPROACH','MINORITY_ONLY','NOT_FOR_SALE'][i%4]
   w['private_businesses'][id]=dict(entity=id,sector=sector,location=locations[i%6],availability=availability,annual_revenue=amt(revenue),annual_payroll=amt(payroll),annual_materials=amt(materials),employee_count=employees,management_quality=55+i%35,strategy='balanced',multiple=str(multiple),opening_productive=amt(productive),history=[],last_tick=w['tick'],growth='.02',integration_until=0,voting_threshold='.50',sale_attempts=0)
   if i%3==1:
    debt=(assets*D('.12')).quantize(D('.01'));claim=self.create_claim('corporate_lender',id,debt,'COMMERCIAL','opening-business-capex',rate='4.5',months=120)
    self.post('Funded independent business equipment loan '+id,{'cash:corporate_lender':-debt,'claim:corporate_lender:'+claim['id']:debt,'productive:'+id:debt,'debt:'+id+':claim_'+claim['id']:-debt,'cash:'+self.ma_account('suppliers'):debt,'pnl:'+self.ma_account('suppliers'):-debt});w['private_businesses'][id]['opening_productive']=amt(productive+debt)
   self.state.setdefault('operating_businesses',{})[id]={'entity':id,'sector':sector,'corporate_model':True,'last_tick':w['tick'],'status':'OPERATING'}
  self.audit('independent_business_economy_created',{'companies':48,'owners':8,'method':'Balanced productive assets and separate owner capital, no player balances changed'})
 def ma_account(self,kind):
  return self.state.get('ma_economy_accounts',{}).get(kind,{'households':'economy_households','suppliers':'operating_suppliers'}[kind])
 def ma_migrate(self):
  w=self.state
  if w.get('private_businesses'):
   if len(w['private_businesses'])!=48:raise ValueError('Partial corporate economy detected; refusing duplicate allocation')
   return {'status':'ALREADY_INITIALISED','added':0,'total':48,'world':w['id']}
  if any(w.get(k) for k in ('ma_offers','ma_history','ma_facilities','ma_economy_accounts','ma_migration')):raise ValueError('Existing M&A records require inspection; migration cannot reset them')
  reserved={'ma_migration_households','ma_migration_suppliers'}
  if reserved.intersection(w['entities']) or any(reserved.intersection(k.split(':')[1:]) for k in w['balances']):raise ValueError('Migration counterparties already exist')
  before=copy.deepcopy(w);self.ma_generate(migration=True)
  self.ma_preservation(before,w)
  w['ma_migration']={'version':1,'tick':w['tick'],'time':w['time'],'companies':48,'method':'Existing generator, isolated new counterparties; no historical balance edits'}
  banks=copy.deepcopy(w['banks'])
  try:self.reconcile()
  finally:w['banks']=banks
  self.ma_preservation(before,w);self.audit('ma_existing_world_migration',copy.deepcopy(w['ma_migration']))
  return {'status':'MIGRATED','added':48,'total':48,'world':w['id'],'tick':w['tick'],'existing_state_preserved':True}
 @staticmethod
 def ma_preservation(before,after):
  for key,value in before.items():
   if key in ('entities','balances','operating_businesses'):
    if any(after.get(key,{}).get(k)!=v for k,v in value.items()):raise ValueError('Migration changed existing '+key)
   elif key=='claims_book':
    if after[key][:len(value)]!=value:raise ValueError('Migration changed historical creditor claims')
   elif key in ('private_businesses','ma_offers','ma_history','ma_facilities') and not value:continue
   elif after.get(key)!=value:raise ValueError('Migration changed existing state: '+key)
 def ma_model_earnings(self,id):
  b=self.state['private_businesses'][id];history=b['history'][-30:]
  if history:return max(D(0),sum((D(h['ebitda']) for h in history),D(0))/len(history)*365)
  return max(D(0),D(b['annual_revenue'])-D(b['annual_payroll'])-D(b['annual_materials']))
 def ma_valuation(self,id,metrics=None):
  m=metrics or self.metrics(id);b=self.state['private_businesses'][id];productive=self.productive_value(id);earnings=self.ma_model_earnings(id);ev=max(productive*D('.65'),earnings*D(b['multiple']));nonoperating=D(m['equity'])+D(m['debt'])-D(m['cash'])-productive;equity=max(D(0),ev+D(m['cash'])+nonoperating-D(m['debt']))
  if self.is_frozen(id):equity=min(equity,max(D(0),D(m['equity'])))
  return {'enterprise_value':amt(ev),'equity_value':amt(equity),'book_equity':m['equity'],'annualised_ebitda':amt(earnings),'multiple':b['multiple'],'basis':'Last up to30 posted days annualised' if b['history'] else 'Opening model earnings forecast, not realised historical income','currency':'GBP'}
 def corporate_interest_value(self,id,metrics):
  return D(self.ma_valuation(id,metrics)['equity_value']) if id in self.state.get('private_businesses',{}) else max(D(0),D(metrics['equity']))
 def ma_market(self,p=None):
  p=p or {};rows=[]
  for id,b in self.state.get('private_businesses',{}).items():
   e=self.state['entities'][id];m=self.metrics(id);v=self.ma_valuation(id,m);row=dict(id=id,name=e['name'],sector=b['sector'],location=b['location'],availability=b['availability'],status=e['status'],controlled=e['controlled'],owners=copy.deepcopy(e['owners']),units=e['units'],cash=m['cash'],liabilities=m['debt'],assets=amt(D(m['equity'])+D(m['debt'])),employees=self.workforce_view(id)['headcount'],annual_revenue=b['annual_revenue'],workforce=self.workforce_view(id),engagements=copy.deepcopy(b.get('engagements',[])) if e['controlled'] else [],strategy=b['strategy'],direction=copy.deepcopy(b.get('direction')) if e['controlled'] else None,daily_investment_budget=b.get('daily_investment_budget','0.00') if e['controlled'] else None,management_quality=b['management_quality'],last_result=b['history'][-1] if b['history'] else None,**v)
   if p.get('query') and str(p['query']).lower() not in (row['name']+' '+row['sector']+' '+row['location']).lower():continue
   if p.get('sector') and p['sector']!=b['sector']:continue
   if p.get('availability') and p['availability']!=b['availability']:continue
   if p.get('max_value') is not None and D(v['equity_value'])>D(str(p['max_value'])):continue
   rows.append(row)
  field=p.get('sort','equity_value');field=field if field in ('equity_value','annualised_ebitda','cash','name','location') else 'equity_value';rows.sort(key=lambda r:r[field] if field in ('name','location') else D(r[field]),reverse=p.get('direction','asc')=='desc');return rows
 def ma_profile(self,p):
  if self.state['entities'].get(p['entity'],{}).get('kind')=='issuer':
   row=next((r for r in self.public_management_rows() if r['id']==p['entity']),None)
   if not row:raise ValueError('Use the public issuer profile for an unowned listed company')
   row['access']='MANAGEMENT' if row['management_authorized'] else 'SHAREHOLDER SUMMARY';row['statement']=self.statement(p['entity'],limit=20) if row['management_authorized'] else {};return row
  id=p['entity'];access=self.state['entities'][id].get('controlled') or any(r['entity']==id and r.get('diligence') and r['status'] in ('DILIGENCE','SIGNED','CLOSED') and self.state['entities'].get(r['buyer'],{}).get('controlled') and r.get('ownership')==self.state['entities'][id]['owners'] for r in self.state.get('ma_offers',[]))
  return self._ma_profile(id,bool(access))
 def _ma_profile(self,id,access):
  row=next(r for r in self.ma_market({'query':self.state['entities'][id]['name']}) if r['id']==id);statement=self.statement(id,limit=20)
  if not access:
   statement.update(entries=[],income_sources={},cash_sources={})
  row.update(access='MANAGEMENT / DILIGENCE' if access else 'PUBLIC SUMMARY',history=copy.deepcopy(self.state['private_businesses'][id]['history']) if access else [],statement=statement,
   claims=[copy.deepcopy(c) for c in self.state['claims_book'] if c['debtor']==id or c['creditor']==id] if access else [],restriction=self.restriction_summary(id),
   information_note='Detailed obligations, delivery records and ledger entries require current management authority or paid diligence with unchanged selling ownership.')
  return row
 def ma_offer(self,p):
  from .engine import positive,uid
  buyer=p['buyer'];self.authority(buyer,'govern');return self._ma_offer(p,uid,positive)
 def _ma_offer(self,p,uid,positive,ai=False):
  w=self.state;buyer=p['buyer'];id=p['entity'];b=w.get('private_businesses',{}).get(id);e=w['entities'].get(id)
  if not b or not e or e['status']!='ACTIVE' or any(self.is_frozen(a) for a in (id,buyer)):raise ValueError('An active unrestricted private business and buyer are required')
  if self.is_fund(buyer) and not w['entities'][buyer]['mandate']['related_parties'] and not self.fund_allows_corporate_control(buyer):raise ValueError('Fund mandate does not permit corporate investments')
  seller=p.get('seller') or max(e['owners'],key=lambda o:D(e['owners'][o]));pct=D(str(p.get('percent',100)));amount=positive(p['amount']);debt=D(str(p.get('debt',0)))
  if not pct.is_finite() or not 0<pct<=100 or not debt.is_finite() or debt<0 or debt>=amount:raise ValueError('Invalid stake or acquisition debt')
  qty=(D(e['units'])*pct/100).quantize(D('.000001'))
  if (D(e['owners'].get(buyer,0))+qty)/D(e['units'])>D(b['voting_threshold']):self.require_fund_control_permission(buyer)
  if qty<=0 or qty>D(e['owners'].get(seller,0)) or buyer==seller or self.ownership_cycle(id,buyer):raise ValueError('Invalid seller interest or ownership cycle')
  if self.is_frozen(seller):raise ValueError('Seller is restricted')
  if w['entities'][seller].get('controlled') and not ai:self.authority(seller,'govern')
  if any(r['buyer']==buyer and r['entity']==id and r['status'] in ('ACCEPTED','COUNTERED','DILIGENCE','SIGNED') for r in w.get('ma_offers',[])):raise ValueError('Review or withdraw the existing live approach first')
  value=D(self.ma_valuation(id)['equity_value'])*pct/100;premium=D('1.05') if pct>50 else D('.95');floor=value*premium
  if b['availability']=='OPEN_TO_APPROACH':floor*=D('1.10')
  if b['availability']=='NOT_FOR_SALE':floor*=D('1.5')
  if b['availability']=='MINORITY_ONLY' and pct>49:status='REJECTED';reason='Owner will only sell a minority stake'
  elif amount<floor*D('.75'):status='REJECTED';reason='Offer is materially below the owner reservation valuation'
  elif amount<floor:status='COUNTERED';reason='Owner requires the recorded counterprice'
  else:status='ACCEPTED';reason='Owner conditionally accepts, subject to diligence, approvals and funds'
  r=dict(id=uid(),entity=id,buyer=buyer,seller=seller,percent=str(pct),quantity=str(qty),amount=amt(amount),debt=amt(debt),status=status,reason=reason,counterprice=amt(floor),created=w['tick'],expires=w['tick']+336,ownership=copy.deepcopy(e['owners']),approvals={},ai=ai,revisions=[],owner_consent={'owner':seller,'quantity':str(qty),'accepted':status=='ACCEPTED','basis':b['availability']},time=w['time']);w.setdefault('ma_offers',[]).append(r);b['sale_attempts']+=1;self.audit('acquisition_approach',copy.deepcopy(r));return r
 def ma_record(self,p):return next(r for r in self.state.get('ma_offers',[]) if r['id']==p['id'])
 def ma_live(self,r,statuses):
  if r['status'] not in statuses or self.state['tick']>r['expires']:raise ValueError('Offer is no longer eligible or has expired')
  if r['ownership']!=self.state['entities'][r['entity']]['owners']:raise ValueError('Ownership changed; submit a new approach')
  for id in (r['buyer'],r['seller'],r['entity']):
   if self.is_frozen(id):raise ValueError('An involved legal account is restricted')
 def ma_negotiate(self,p):
  from .engine import positive
  r=self.ma_record(p);self.ma_authority(r['buyer'],'govern');self.ma_live(r,('COUNTERED','ACCEPTED'));amount=positive(p.get('amount',r['counterprice']));r['revisions'].append({'time':self.state['time'],'amount':r['amount']});r['amount']=amt(amount);r['status']='ACCEPTED' if amount>=D(r['counterprice']) else 'REJECTED';r['owner_consent']['accepted']=r['status']=='ACCEPTED';r['approvals']={};self.audit('acquisition_negotiated',copy.deepcopy(r));return r
 def ma_authority(self,id,right):
  return self.authority(id,right,'ai_board' if getattr(self,'_ma_ai_context',None)==id else 'player')
 def ma_diligence(self,p):
  r=self.ma_record(p);self.ma_authority(r['buyer'],'govern');self.ma_authority(r['buyer'],'payment');self.ma_live(r,('ACCEPTED',));fee=min(D(200000),max(D(500),D(r['amount'])*D('.001')))
  if self.available_cash(r['buyer'])<fee or fee>D(self.state['entities'][r['buyer']]['payment_limit']):raise ValueError('Diligence exceeds unrestricted cash or delegated payment authority')
  self.post('Acquisition due diligence '+r['id'],{'cash:'+r['buyer']:-fee,'expense:due_diligence:'+r['buyer']:fee,'cash:'+self.ma_account('suppliers'):fee,'pnl:'+self.ma_account('suppliers'):-fee});r['diligence']=self._ma_profile(r['entity'],True);r['diligence_tick']=self.state['tick'];r['diligence_fee']=amt(fee);r['status']='DILIGENCE';return r
 def ma_approve(self,p):
  r=self.ma_record(p);self.ma_live(r,('DILIGENCE','SIGNED'));buyer=self.ma_authority(r['buyer'],'govern');self.ma_authority(r['buyer'],'payment');r['approvals']['buyer']={'actor':'ai_board' if getattr(self,'_ma_ai_context',None)==r['buyer'] else 'player','time':self.state['time']}
  for id in (r['buyer'],r['seller']):
   e=self.state['entities'][id]
   if not e.get('controlled'):continue
   self.authority(id,'govern')
   if e.get('controls',0)>0 or D(r['amount'])>D(e['payment_limit']):
    reviewer=next((a for a in e['directors'] if a!='player' and 'govern' in e['signatories'].get(a,[])),None)
    if not reviewer:raise ValueError('Independent board authority required for '+e['name']+'; configure governance controls or an authorised director')
    self.authority(id,'govern',reviewer);r['approvals'][id]={'actor':reviewer,'time':self.state['time']}
  r['status']='SIGNED';self.audit('acquisition_signed',copy.deepcopy(r));return r
 def ma_close(self,p):
  r=self.ma_record(p);self.ma_authority(r['buyer'],'govern');self.ma_authority(r['buyer'],'payment');self.ma_live(r,('SIGNED',))
  if self.state['tick']-r['diligence_tick']>168:raise ValueError('Diligence is stale; withdraw and obtain a fresh assessment')
  if not r['owner_consent']['accepted']:raise ValueError('Seller has not agreed')
  for id,approval in r['approvals'].items():
   account=r['buyer'] if id=='buyer' else id;self.authority(account,'govern',approval['actor'])
   if id!='buyer' and (approval['actor']=='player' or approval['actor'] not in self.state['entities'][account]['directors']):raise ValueError('Independent board authority changed after signing')
  for account in (r['buyer'],r['seller']):
   e=self.state['entities'][account]
   if e.get('controlled') and (e['controls']>0 or D(r['amount'])>D(e['payment_limit'])) and account not in r['approvals']:raise ValueError('Changed authority requires fresh board approval')
  for other in self.state['ma_offers']:
   if other['id']!=r['id'] and other['entity']==r['entity'] and other['seller']==r['seller'] and other['status'] in ('ACCEPTED','DILIGENCE','SIGNED') and self.state['tick']<=other['expires'] and self.ma_bid_funded(other) and D(other['amount'])/D(other['quantity'])>D(r['amount'])/D(r['quantity']):raise ValueError('Seller is considering a higher competing bid')
  amount=D(r['amount']);debt=D(r['debt']);buyer=r['buyer'];source=buyer
  if self.available_cash(buyer)<amount-debt:raise ValueError('Acquisition equity exceeds actual available cash')
  if debt:
   if D(r['percent'])!=100:raise ValueError('Acquisition-vehicle debt currently requires a100% stake')
   valuation=self.ma_valuation(r['entity']);ebitda=D(valuation['annualised_ebitda']);service=debt*(D('.09')+D('.2'))
   if debt>D(valuation['enterprise_value'])*D('.5') or ebitda<service*D('1.5') or self.available_cash('corporate_lender')<debt:raise ValueError('LBO declined: leverage, cash-flow coverage or finite lender capacity')
   vehicle=self.entity_create({'parent':buyer,'name':self.state['entities'][r['entity']]['name']+' Acquisition SPV','capital':amount-debt,'kind':'holding'});source=vehicle['id'];self.governance_controls({'entity':source,'level':1});claim=self.create_claim('corporate_lender',source,debt,'ACQUISITION',r['id'],rate=9,months=60);self.post('Acquisition senior facility '+r['id'],{'cash:corporate_lender':-debt,'claim:corporate_lender:'+claim['id']:debt,'cash:'+source:debt,'debt:'+source+':claim_'+claim['id']:-debt});self.state['ma_facilities'].append({'claim':claim['id'],'vehicle':source,'target':r['entity'],'original':amt(debt),'next_due':self.state['tick']+720,'missed':0,'status':'ACTIVE'});r['vehicle']=source
  self.lifecycle_sale({'entity':r['entity'],'buyer':source,'seller':r['seller'],'quantity':r['quantity'],'amount':r['amount']},r['id'],actor='ai_board' if getattr(self,'_ma_ai_context',None)==r['buyer'] else 'player');r.update(status='CLOSED',closed=self.state['time'],settled_buyer=source);self.ma_update_control(r['entity']);self.state['private_businesses'][r['entity']]['integration_until']=self.state['tick']+168
  for other in self.state['ma_offers']:
   if other['id']!=r['id'] and other['entity']==r['entity'] and other['status'] in ('ACCEPTED','COUNTERED','DILIGENCE','SIGNED'):other['status']='OUTBID'
  self.state['ma_history'].append(copy.deepcopy(r));self.audit('acquisition_closed',copy.deepcopy(r));return r
 def ma_bid_funded(self,r):
  if self.is_frozen(r['buyer']) or self.available_cash(r['buyer'])<D(r['amount'])-D(r['debt']):return False
  debt=D(r['debt'])
  if not debt:return True
  v=self.ma_valuation(r['entity']);return D(r['percent'])==100 and debt<=D(v['enterprise_value'])*D('.5') and D(v['annualised_ebitda'])>=debt*D('.29')*D('1.5') and self.available_cash('corporate_lender')>=debt
 def ma_withdraw(self,p):
  r=self.ma_record(p);self.authority(r['seller'] if p.get('seller') else r['buyer'],'govern')
  if r['status'] in ('CLOSED','WITHDRAWN'):raise ValueError('Offer already settled or withdrawn')
  r['status']='WITHDRAWN';return r
 def ma_update_control(self,id):
  e=self.state['entities'][id];b=self.state['private_businesses'][id];units=D(e['units']);votes=sum((D(q) for owner,q in e['owners'].items() if self.state['entities'].get(owner,{}).get('controlled')),D(0))/units;controlled=votes>D(b['voting_threshold']);e['controlled']=controlled
  e['parent']=next((owner for owner,q in e['owners'].items() if D(q)/units>D(b['voting_threshold'])),None)
  if controlled:e['signatories'].pop('ai_board',None);e['signatories']['player']=['govern','disclose'];e['signatories']['board']=['govern'];e['directors']=['player','board'];e['controls']=1
  else:e['signatories'].pop('player',None);e['signatories'].pop('board',None);e['signatories']['ai_board']=['govern','payment','disclose'];e['directors']=['ai_board']
 def ma_manage(self,p):
  if self.state['entities'].get(p['entity'],{}).get('kind')=='issuer':return self.public_operating_manage(p)
  id=p['entity'];e=self.authority(id,'govern');b=self.state['private_businesses'][id]
  if self.is_frozen(id):raise ValueError('Restricted company cannot change operating policies')
  if p.get('appoint_manager'):e['signatories']['player']=['govern','disclose','payment','trade']
  if p.get('strategy'):
   if p['strategy'] not in STRATEGIES:raise ValueError('Unknown operating strategy')
   b['strategy']=p['strategy']
   b['direction']=dict(strategy=p['strategy'],set_tick=self.state['tick'],set_time=self.state['time'],set_by='Player',status='ACTIVE',effects={'balanced':'Maintain current staffing and capacity; retain operating liquidity.','growth':'Prioritise capacity investment within the authorised daily budget.','efficiency':'Conserve cash; existing efficiency input-cost policy applies.'}[p['strategy']],observed='Awaiting next daily operating cycle')
  if 'daily_investment_budget' in p:
   budget=D(str(p['daily_investment_budget']))
   if not budget.is_finite() or budget<0 or budget>D(e['payment_limit']):raise ValueError('Daily investment budget exceeds payment authority')
   b['daily_investment_budget']=amt(budget)
  if p.get('management_quality') is not None:
   quality=int(p['management_quality'])
   if not 40<=quality<=95:raise ValueError('Management quality must be40–95')
   cost=D(b['annual_payroll'])*D('.01')
   self.authority(id,'payment')
   if self.available_cash(id)<cost or cost>D(e['payment_limit']):raise ValueError('Management recruitment exceeds cash or payment authority')
   self.post('Executive recruitment '+id,{'cash:'+id:-cost,'expense:recruitment:'+id:cost,'cash:'+self.ma_account('suppliers'):cost,'pnl:'+self.ma_account('suppliers'):-cost});b['management_quality']=quality
  self.audit('portfolio_operating_policy',copy.deepcopy(p));return b
 def ma_expand(self,p):
  if self.state['entities'].get(p['entity'],{}).get('kind')=='issuer':return self.public_productive_investment(p)
  from .engine import positive
  id=p['entity'];e=self.authority(id,'payment');self.authority(id,'govern');amount=positive(p['amount'])
  if id not in self.state.get('private_businesses',{}) or self.is_frozen(id):raise ValueError('An unrestricted portfolio business is required')
  if amount>self.available_cash(id) or amount>D(e['payment_limit']):raise ValueError('Expansion exceeds cash or delegated payment limit')
  self.post('Portfolio productive expansion '+id,{'cash:'+id:-amount,'productive:'+id:amount,'cash:'+self.ma_account('suppliers'):amount,'pnl:'+self.ma_account('suppliers'):-amount});self.audit('portfolio_expansion',{'entity':id,'amount':amt(amount)});return self.ma_valuation(id)
 def ma_dividend(self,p):
  from .engine import positive
  self.authority(p['entity'],'govern');self.authority(p['entity'],'payment')
  if p['entity'] not in self.state.get('private_businesses',{}):raise ValueError('Select a portfolio business')
  r=self.lifecycle_propose({'kind':'dividend','entity':p['entity'],'amount':amt(positive(p['amount']))});self.lifecycle_approve({'id':r['id']});return self.lifecycle_execute({'id':r['id']})
 def ma_exit(self,p):
  from .engine import uid,positive
  id=p['entity'];seller=p['seller'];self.authority(seller,'govern');e=self.state['entities'][id];pct=D(str(p.get('percent',100)));price=D(self.ma_valuation(id)['equity_value'])*pct/100*D('.95');buyers=[a for a in self.state['entities'].values() if a['id'].startswith('corporate_owner_') and a['id']!=seller and not self.is_frozen(a['id']) and self.available_cash(a['id'])>=price and not self.ownership_cycle(id,a['id'])]
  if not buyers:raise ValueError('No independently funded exit buyer at the current valuation')
  buyer=max(buyers,key=lambda a:self.available_cash(a['id']))['id'];r=self._ma_offer({'entity':id,'seller':seller,'buyer':buyer,'percent':str(pct),'amount':amt(price)},uid,positive,ai=True);r.update(status='EXIT_OFFER',owner_consent={'owner':seller,'quantity':r['quantity'],'accepted':False},exit_quote=True);return r
 def ma_exit_accept(self,p):
  r=self.ma_record(p);self.ma_live(r,('EXIT_OFFER',));self.authority(r['seller'],'govern');seller=self.state['entities'][r['seller']]
  if seller['controls'] or D(r['amount'])>D(seller['payment_limit']):
   actor=next((a for a in seller['directors'] if a!='player' and 'govern' in seller['signatories'].get(a,[])),None)
   if not actor:raise ValueError('Seller independent board approval required')
   self.authority(r['seller'],'govern',actor)
  if self.available_cash(r['buyer'])<D(r['amount']):raise ValueError('Exit buyer no longer has sufficient funds')
  self.lifecycle_sale({'entity':r['entity'],'buyer':r['buyer'],'seller':r['seller'],'quantity':r['quantity'],'amount':r['amount']},r['id'],actor='ai_board');r.update(status='CLOSED',closed=self.state['time'],settled_buyer=r['buyer']);self.ma_update_control(r['entity']);self.state['ma_history'].append(copy.deepcopy(r));self.audit('portfolio_exit',copy.deepcopy(r));return r
 def ma_company_tick(self):
  w=self.state
  self.public_offer_tick()
  if w['tick']%24:return
  for id,b in w.get('private_businesses',{}).items():
   if b['last_tick']==w['tick'] or self.is_frozen(id):continue
   delivered=self.company_delivery_tick(id,b)
   if w['entities'][id]['status']!='ACTIVE':continue
   b['last_tick']=w['tick']
   direction=b.get('direction')
   if direction:
    direction.update(last_review=w['time'],status='ACTIVE',observed='Operating policy applied; no automatic investment authorised')
    budget=D(b.get('daily_investment_budget','0'))
    if b['strategy']=='growth' and budget>0:
     reserve=D(b['annual_payroll'])/12+D(b['annual_materials'])/12;amount=min(budget,max(D(0),self.available_cash(id)-reserve),max(D(0),D(b['opening_productive'])*2-self.productive_value(id)))
     if amount>=1:
      try:
       self.company_operate({'entity':id,'kind':'equipment','amount':amt(amount)})
       direction['observed']='Purchased productive equipment for £'+amt(amount)+'; one month of operating costs retained'
      except ValueError as error:direction.update(status='BLOCKED',observed=str(error))
     else:direction.update(status='BLOCKED',observed='Operating cash reserve or productive capacity ceiling prevents investment')
   revfactor,costfactor=map(D,STRATEGIES[b['strategy']]);capacity=self.productive_value(id)/max(D(1),D(b['opening_productive']));capacity=min(D(2),max(D('.1'),capacity));demand=max(D('.25'),min(D('1.5'),D(str(w['macro'].get('demand',100)))/100*(1+D(str(w['macro'].get('growth',0)))/100-D(str(w['macro'].get('stress',0)))/250)));quality=D('.75')+D(b['management_quality'])/200;integration=D('.9') if w['tick']<b['integration_until'] else D(1);sales=(D(b['annual_revenue'])/365*capacity*revfactor*demand*quality*integration*D(self.workforce_view(id)['available'])/max(1,b['employee_count'])).quantize(D('.01'));revenue=min(max(D(0),self.cash(self.ma_account('households'))),sales);wages=(D(b['annual_payroll'])/365).quantize(D('.01'));materials=(D(b['annual_materials'])/365*capacity*costfactor).quantize(D('.01'));cost=wages+materials;depreciation=min(self.productive_value(id),(self.productive_value(id)/3650).quantize(D('.01')))
   self.post('Private business customer receipts '+id,{'cash:'+self.ma_account('households'):-revenue,'expense:consumption:'+self.ma_account('households'):revenue,'cash:'+id:revenue,'pnl:'+id:-revenue});self.post('Private business operating obligations '+id,{'expense:workforce:'+id:wages,'debt:'+id+':workforce':-wages,'expense:materials:'+id:materials,'debt:'+id+':materials':-materials,'expense:depreciation:'+id:depreciation,'productive:'+id:-depreciation})
   for name,amount,destination in [('workforce',wages,self.ma_account('households')),('materials',materials,self.ma_account('suppliers'))]:
    due=-self.balance('debt:'+id+':'+name);paid=min(max(D(0),self.available_cash(id)),due)
    if paid:self.post('Private business '+name+' payment '+id,{'cash:'+id:-paid,'debt:'+id+':'+name:paid,'cash:'+destination:paid,'pnl:'+destination:-paid})
   earnings=-self.balance('pnl:'+id)-sum((D(v) for k,v in self.state['balances'].items() if k.startswith('expense:') and k.endswith(':'+id)),D(0));net=earnings-D(b.get('accounted_earnings',0));b['accounted_earnings']=amt(earnings)
   b['history'].append({'time':w['time'],'tick':w['tick'],'revenue':amt(revenue+delivered),'service_revenue':amt(delivered),'payroll':amt(wages),'materials':amt(materials),'ebitda':amt(revenue+delivered-cost),'operating_profit':amt(revenue+delivered-cost-depreciation),'net_income':amt(net),'cumulative_net_income':amt(earnings),'cash':amt(self.cash(id))});b['history']=b['history'][-120:]
  self.ma_facility_tick();self.ma_ai_tick()
 def ma_facility_tick(self):
  for facility in self.state.get('ma_facilities',[]):
   c=next(c for c in self.state['claims_book'] if c['id']==facility['claim'])
   if D(c['balance'])<=0:facility['status']='REPAID';continue
   if self.state['tick']<facility['next_due']:continue
   due=min(D(c['balance']),D(facility['original'])/60+D(c['balance'])*D('.09')/12);paid=min(due,max(D(0),self.available_cash(facility['vehicle'])))
   target=facility['target'];e=self.state['entities'][target]
   # The signed100% LBO mandate permits only lawful retained-profit dividends.
   if paid<due and e.get('parent')==facility['vehicle'] and len(e['owners'])==1 and not self.is_frozen(target) and 'payment' in e['signatories'].get('player',[]):
    earned=-self.balance('pnl:'+target)-sum((D(v) for k,v in self.state['balances'].items() if k.startswith('expense:') and k.endswith(':'+target)),D(0));prior=sum((D(r['terms']['amount']) for r in self.state.get('corporate_actions',[]) if r['kind']=='dividend' and r['terms']['entity']==target and r['status']=='COMPLETED'),D(0));surplus=min(max(D(0),earned-prior),self.available_cash(target),due-paid)
    if surplus>0:
     # Validate before proposing, so a rejected distribution leaves no partial action.
     try:self.lifecycle_preview({'kind':'dividend','entity':target,'amount':amt(surplus)})
     except ValueError:pass
     else:self.ma_dividend({'entity':target,'amount':amt(surplus)});paid=min(due,max(D(0),self.available_cash(facility['vehicle'])))
   if paid and not self.is_frozen(facility['vehicle']):self.settle_claim_cash(c,paid,'Senior acquisition scheduled service')
   else:paid=D(0)
   coverage=self.ma_model_earnings(facility['target'])/(D(facility['original'])*D('.29'))
   if paid<due or coverage<D('1.2'):facility['missed']+=1;facility['status']='COVENANT_BREACH';facility['last_shortfall']=amt(due-paid)
   else:facility['status']='ACTIVE';facility['missed']=0
   if facility['missed']>=3:c['status']='OVERDUE';c['due']=self.state['tick'];facility['status']='DEFAULT'
   facility['next_due']+=720

 def ma_ai_tick(self):
  w=self.state
  if not w.get('private_businesses') or w['tick']%168:return
  from .engine import uid,positive
  candidates=[id for id,b in w['private_businesses'].items() if b['availability']=='FOR_SALE' and not w['entities'][id]['controlled'] and w['entities'][id]['status']=='ACTIVE' and not self.is_frozen(id)]
  if not candidates:return
  target=sorted(candidates)[(w['tick']//168)%len(candidates)];seller=max(w['entities'][target]['owners'],key=lambda o:D(w['entities'][target]['owners'][o]));price=(D(self.ma_valuation(target)['equity_value'])*D('1.06')).quantize(D('.01'));buyers=[id for id in w['entities'] if id.startswith('corporate_owner_') and id!=seller and not self.is_frozen(id) and self.available_cash(id)>price*D('1.01')]
  if not buyers or price<=0:return
  buyer=sorted(buyers)[(w['tick']//168)%len(buyers)];checkpoint=copy.deepcopy(w);self.db.execute('SAVEPOINT autonomous_acquisition')
  try:
   self._ma_ai_context=buyer;r=self._ma_offer({'entity':target,'buyer':buyer,'seller':seller,'amount':amt(price),'percent':100},uid,positive,ai=True)
   if r['status']=='ACCEPTED':
    self.ma_diligence({'id':r['id']});self.ma_approve({'id':r['id']});self.ma_close({'id':r['id']})
   self.db.execute('RELEASE autonomous_acquisition')
  except ValueError as error:
   self.db.execute('ROLLBACK TO autonomous_acquisition');self.db.execute('RELEASE autonomous_acquisition');w.clear();w.update(checkpoint);self.audit('autonomous_acquisition_deferred',{'entity':target,'reason':str(error)})
  finally:self._ma_ai_context=None
