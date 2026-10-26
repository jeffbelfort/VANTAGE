"""Approved corporate actions over the existing entity/claim/journal model."""
import copy
from decimal import Decimal as D
from .integrity import amt

COMPANIES=('company','holding','credit_fund')

class CorporateLifecycleMixin:
 def successor_account(self,account):
  seen=set()
  while account not in seen:
   seen.add(account);successor=self.state.get('entities',{}).get(account,{}).get('successor')
   if not successor:return account
   account=successor
  raise ValueError('Invalid successor cycle')

 def realised_total(self,account):
  return super().realised_total(account)+sum((super(CorporateLifecycleMixin,self).realised_total(id) for id in self.state.get('entities',{}).get(account,{}).get('predecessors',[])),D(0))

 def ownership_cycle(self,target,buyer):
  pending=[buyer];seen=set()
  while pending:
   id=pending.pop()
   if id==target:return True
   if id in seen:continue
   seen.add(id);fund=next((f for f in self.state['funds'] if f['id']==id),None);owners=(fund or {}).get('investors',self.state['entities'].get(id,{}).get('owners',{}));issuer=next((i for i in self.state.get('issuers',{}).values() if i['account']==id),None)
   if issuer:owners={h['account']:h['registered_shares'] for h in self.public_ownership(issuer['symbol'])['shareholders']}
   pending.extend(o for o,q in owners.items() if D(q)>0)
  return False

 def lifecycle_requirements(self,entities,amounts=None,shareholders=(),liquidator=None,ai_dividend=False):
  result=[]
  for id in dict.fromkeys(entities):
   e=self.state['entities'][id]
   result.append({'key':'govern:'+id,'entity':id,'role':'liquidator' if id==liquidator else 'govern_ai' if ai_dividend and id.startswith('corporate_owner_') and not e.get('controlled') else 'govern'})
   if id!=liquidator and e['kind']!='personal' and (e.get('controls',0)>0 or D((amounts or {}).get(id,0))>D(e['payment_limit'])):result.append({'key':'board:'+id,'entity':id,'role':'board'})
  for id in dict.fromkeys(shareholders):
   if ai_dividend and id.startswith('corporate_owner_') and not self.state['entities'][id].get('controlled'):
    result.append({'key':'shareholder:'+id,'entity':id,'role':'shareholder_ai'});continue
   if id not in self.state['entities'] or not self.state['entities'][id].get('controlled'):raise ValueError('Unanimous shareholder consent unavailable from this external shareholder')
   result.append({'key':'shareholder:'+id,'entity':id,'role':'shareholder'})
  return result

 def lifecycle_preview(self,p):
  kind=p['kind'];w=self.state;target=p['entity'];e=w['entities'].get(target)
  if not e or e['kind'] not in COMPANIES or self.is_fund(target):raise ValueError('Select an ordinary company, holding company or credit company; fund units and deposit banks have separate legal models')
  if e['status']!='ACTIVE' or self.is_frozen(target):raise ValueError('Target status or active restrictions prohibit this corporate action')
  m=self.metrics(target);terms=copy.deepcopy(p);terms.pop('id',None);amount=D(str(p.get('amount',0)));details={};participants=[target];shareholders=[];payments={};liquidator=None
  if not amount.is_finite() or amount<0 or amount!=amount.quantize(D('.01')):raise ValueError('Amount must be nonnegative whole pennies')
  if kind=='sale':
   seller=p['seller'];buyer=p['buyer'];pct=D(str(p.get('percent',100)));units=D(e['units']);owned=D(e['owners'].get(seller,0))
   if not pct.is_finite() or not 0<pct<=100 or units<=0:raise ValueError('Invalid ownership percentage')
   quantity=units if pct==100 else (units*pct/100).quantize(D('.000001'))
   if quantity<=0 or quantity>owned or buyer==seller:raise ValueError('Seller does not own the requested company interest')
   if self.ownership_cycle(target,buyer):raise ValueError('Acquisition would create an ownership cycle')
   for id in (seller,buyer):
    party=w['entities'].get(id)
    if not party or not party.get('controlled'):raise ValueError('A funded, controlled counterparty is required')
    if self.is_fund(id) and not party['mandate']['related_parties']:raise ValueError('Fund investment mandate does not authorise related-company equity')
   admin=next((a for a in w.get('administrations',[]) if a['entity']==seller and a['status']!='DISSOLVED'),None)
   if admin:liquidator=seller
   elif self.is_frozen(seller):raise ValueError('Seller is restricted')
   if self.is_frozen(buyer) or self.available_cash(buyer)<amount:raise ValueError('Buyer is restricted or lacks unrestricted purchase funds')
   if amount<=0:raise ValueError('A negotiated positive cash price is required')
   fair=max(D(0),D(m['equity']))*quantity/units
   if admin and amount<fair*D('.95'):raise ValueError('Administrator cannot approve a disposal below 95% of marked equity value')
   terms.update(quantity=str(quantity),percent=str(pct));participants+=[seller,buyer];payments[buyer]=amount
   details={'marked_equity_value':amt(fair),'negotiated_price':amt(amount),'interest_percent':str(pct),'seller':seller,'buyer':buyer,'debt_remains_with':target,'administrator_disposal':bool(admin),'valuation_basis':'Proportionate marked net assets after all recorded liabilities; no invented goodwill'}
  elif kind=='swap':
   c=next(c for c in w['claims_book'] if c['id']==p['claim'])
   if c['debtor']!=target or c['kind']!='INTERCOMPANY' or c['status'] not in ('ACTIVE','OVERDUE') or not 0<amount<=D(c['balance']):raise ValueError('Only outstanding ordinary commercial intercompany debt may convert; restitution and penalties retain their terms')
   creditor=c['creditor'];valuation=D(str(p.get('valuation',max(D(1),D(m['equity'])))))
   if not valuation.is_finite() or valuation<=0 or D(e['units'])<=0:raise ValueError('An agreed positive pre-money share valuation is required')
   if self.is_frozen(creditor) or self.ownership_cycle(target,creditor):raise ValueError('Creditor restriction or ownership cycle prevents conversion')
   ce=w['entities'].get(creditor,{})
   if self.is_fund(creditor) and not ce['mandate']['related_parties']:raise ValueError('Creditor fund mandate does not permit this equity investment')
   issued=(amount*D(e['units'])/valuation).quantize(D('.000001'))
   if issued<=0:raise ValueError('Conversion is below share-unit precision')
   participants.append(creditor);shareholders=list(e['owners']);terms.update(valuation=str(valuation),issued=str(issued))
   details={'claim':c['id'],'converted_face':amt(amount),'creditor_carrying_value':amt(amount*(1-D(c['allowance'])/D(c['balance']))),'agreed_pre_money_equity':amt(valuation),'new_units':str(issued),'creditor_post_percent':amt((D(e['owners'].get(creditor,0))+issued)/(D(e['units'])+issued)*100),'existing_shareholder_dilution_percent':amt(issued/(D(e['units'])+issued)*100)}
  elif kind in ('dividend','capital_return'):
   if amount<=0 or self.available_cash(target)<amount or D(m['equity'])<amount:raise ValueError('Distribution exceeds unrestricted cash or solvent net assets')
   if not e['owners'] or D(e['units'])<=0:raise ValueError('No eligible shareholder register')
   earned=-self.balance('pnl:'+target)-sum((D(v) for k,v in w['balances'].items() if k.startswith('expense:') and k.endswith(':'+target)),D(0))
   prior=sum((D(r['terms']['amount']) for r in w.get('corporate_actions',[]) if r['kind']=='dividend' and r['terms']['entity'] in [target]+e.get('predecessors',[]) and r['status']=='COMPLETED'),D(0))
   capacity=max(D(0),earned-prior) if kind=='dividend' else max(D(0),-self.balance('equity:'+target))
   if amount>capacity:raise ValueError('Distribution exceeds recorded retained realised profits' if kind=='dividend' else 'Capital return exceeds recorded paid-in capital')
   due=sum((D(c['balance']) for c in w['claims_book'] if c['debtor']==target and c['due']<=w['tick']),D(0))
   due+=sum((D(s['unpaid']) for s in w.get('employees',[]) if s['entity']==target),D(0))
   if self.available_cash(target)-amount<due:raise ValueError('Distribution would leave due creditor or employee obligations unfunded')
   shareholders=list(e['owners']);participants+=shareholders;payments[target]=amount
   details={'amount':amt(amount),'distributable_capacity':amt(capacity),'remaining_cash':amt(self.cash(target)-amount),'shareholders':copy.deepcopy(e['owners']),'not_a_debt_repayment':True}
  elif kind=='liquidation':
   if any(v['entity']==target and not v.get('claims_converted') and any(D(row['balance'])>0 for row in v['investors'].values()) for v in w.get('investment_programmes',[])):raise ValueError('Begin programme creditor recovery in Financial Crime before voluntary liquidation; investor liabilities must first become registered claims')
   shareholders=list(e['owners']);details={'mode':'VOLUNTARY LIQUIDATION','assets':amt(D(m['equity'])+D(m['debt'])+(D(m['equity_gross'])-D(m['market']))/2),'liabilities':amt(D(m['debt'])+(D(m['equity_gross'])-D(m['market']))/2),'equity':m['equity'],'creditor_claims':[c['id'] for c in w['claims_book'] if c['debtor']==target and D(c['balance'])>0],'process':'Existing administrator realisation and creditor priorities. Shortfalls remain enforceable; unresolved cases prevent dissolution.'}
  elif kind=='merger':
   if target in w.get('private_businesses',{}):raise ValueError('Private operating-business successor integration is not yet supported; retain the operating legal entity or sell its shares')
   survivor=p['survivor'];parent=w['entities'].get(survivor,{})
   if parent.get('kind') not in COMPANIES or (len([o for o,q in e.get('owners',{}).items() if D(q)>0])!=1 or D(e.get('owners',{}).get(survivor,0))!=D(e['units'])):raise ValueError('Merger currently requires a wholly owned subsidiary merging into its ordinary corporate parent')
   if self.is_frozen(survivor) or parent.get('status')!='ACTIVE':raise ValueError('Successor is restricted or inactive')
   if any(o['account']==target and o.get('forced') and o['status'] in ('OPEN','PARTIAL') for o in w['orders']):raise ValueError('Resolve forced risk/administrator executions before merger')
   source_symbols={p['symbol'] for p in w['positions'].values() if p['account']==target}
   if any(p['account']==survivor and p['symbol'] in source_symbols for p in w['positions'].values()) or any(s in w['options'] for s in source_symbols):raise ValueError('Close overlapping positions and derivative positions before legal merger; no artificial netting is performed')
   if any(v['entity']==target and v['status'] not in ('RECOVERED',) for v in w.get('investment_programmes',[])):raise ValueError('Resolve investment-programme creditors before merger')
   if any(v['owner']==target and v['status']=='SCHEDULED' for v in w.get('social_events',[])):raise ValueError('Complete or cancel scheduled asset activities before merger')
   plans=[w.get('operating_plans',{}).get(id,{}) for id in (target,survivor)];combined_budget=sum((D(plan.get(key,0)) for plan in plans for key in ('research','technology','salary','monthly_payroll')),D(0));payments[survivor]=combined_budget
   if any(c['debtor']==target and c['kind']=='RECOVERY' and D(c['balance'])>0 for c in w['claims_book']):raise ValueError('Outstanding restitution requires its authorised recovery process before merger; a sale can retain the debtor identity')
   bankloans=[l for l in w['loans'] if l['account']==target and D(l['balance'])>0]
   if bankloans and (D(self.metrics(survivor)['equity'])+min(D(0),D(m['equity']))<0 or any(l['status']=='DEFAULT' for l in bankloans)):raise ValueError('Lenders decline assumption by an insolvent successor or of defaulted facilities')
   participants.append(survivor);shareholders=[survivor];details={'source':target,'successor':survivor,'source_assets':amt(D(m['equity'])+D(m['debt'])+(D(m['equity_gross'])-D(m['market']))/2),'source_liabilities':amt(D(m['debt'])+(D(m['equity_gross'])-D(m['market']))/2),'successor_equity_before':self.metrics(survivor)['equity'],'combined_monthly_department_commitment':amt(combined_budget),'orders_to_cancel':[o['id'] for o in w['orders'] if o['account']==target and o['status'] in ('OPEN','PARTIAL')],'bank_facilities_assumed':[l['id'] for l in bankloans],'case_refs_preserved':[c['id'] for c in w.get('legal_cases',[]) if c['entity']==target],'employee_effect':'Employees and salary obligations transfer; trading delegation resets to advisory and unexecuted work mandates cancel. Parent governance remains authoritative.','history':'Original entity ID retained as MERGED with successor reference; journal and transactions remain intact'}
  else:raise ValueError('Unknown corporate lifecycle action')
  for id in dict.fromkeys(participants):
   if id not in w['entities']:raise ValueError('Unsupported counterparty')
   if id!=liquidator and self.is_frozen(id):raise ValueError('An involved account is restricted')
  approvals=self.lifecycle_requirements(participants,payments,shareholders,liquidator,ai_dividend=kind=='dividend' and target in w.get('private_businesses',{}))
  return {'kind':kind,'terms':terms,'financials':{k:m[k] for k in ('cash','available_cash','equity','debt','investment','receivables')},'details':details,'requirements':approvals,'restriction':self.restriction_summary(target),'ownership_before':copy.deepcopy(e['owners']),'valid_until_tick':w['tick']+168}

 def lifecycle_propose(self,p):
  from .engine import uid
  preview=self.lifecycle_preview(p);self.authority(p['entity'],'govern')
  # A liquidating shareholder may request an administrator disposal, never private spending.
  r=dict(id=uid(),kind=p['kind'],terms=preview['terms'],preview=preview,status='PENDING',approvals={},initiator='player',time=self.state['time'],expires=self.state['tick']+168,revisions=[])
  self.state.setdefault('corporate_actions',[]).append(r);self.audit('corporate_action_proposed',copy.deepcopy(r));return r

 def lifecycle_record(self,id):
  return next(r for r in self.state.get('corporate_actions',[]) if r['id']==id)

 def lifecycle_approve(self,p):
  r=self.lifecycle_record(p['id'])
  if r['status']!='PENDING' or self.state['tick']>r['expires']:raise ValueError('Action is no longer pending or has expired')
  preview=self.lifecycle_preview(r['terms'])
  if preview['ownership_before']!=r['preview']['ownership_before']:raise ValueError('Ownership changed; create a new proposal')
  requirements=preview['requirements'];keys=[p['requirement']] if p.get('requirement') else [q['key'] for q in requirements]
  for key in keys:
   req=next(q for q in requirements if q['key']==key);id=req['entity'];e=self.state['entities'][id];role=req['role'];reviewer=p.get('reviewer') if len(keys)==1 else None
   if role=='board':
    eligible=[d for d in e['directors'] if d!=r['initiator'] and 'govern' in e['signatories'].get(d,[])]
    reviewer=reviewer or ('board' if 'board' in eligible else next(iter(eligible),''))
    if reviewer not in eligible:raise ValueError('Independent board approval required for '+e['name']+'; appoint an authorised director or fund governance controls')
   elif role in ('shareholder_ai','govern_ai'):reviewer='ai_board'
   elif role=='liquidator':
    if not any(a['entity']==id and a['status']!='DISSOLVED' for a in self.state.get('administrations',[])):raise ValueError('Administrator no longer appointed')
    reviewer='player';self.authority(id,'disclose',reviewer)
   else:reviewer=reviewer or 'player'
   if role!='liquidator':self.authority(id,'govern',reviewer)
   r['approvals'][key]={'time':self.state['time'],'reviewer':reviewer,'role':role}
  self.audit('corporate_action_approvals',{'id':r['id'],'approvals':copy.deepcopy(r['approvals'])});return r

 def lifecycle_cancel(self,p):
  r=self.lifecycle_record(p['id'])
  if r['status']!='PENDING':raise ValueError('Only pending actions may be withdrawn')
  self.authority(r['terms']['entity'],'govern');r['status']='CANCELLED';self.audit('corporate_action_cancelled',{'id':r['id']});return r

 def lifecycle_counteroffer(self,p):
  r=self.lifecycle_record(p['id'])
  if r['kind']!='sale' or r['status']!='PENDING':raise ValueError('Only pending acquisitions can be renegotiated')
  default=r['terms']['buyer'] if self.is_frozen(r['terms']['seller']) else r['terms']['seller'];party=p.get('party',default)
  if party not in (r['terms']['seller'],r['terms']['buyer']):raise ValueError('Counteroffer must come from a transaction party')
  self.authority(party,'govern');terms=dict(r['terms'],amount=p['amount']);preview=self.lifecycle_preview(terms)
  r['revisions'].append({'time':self.state['time'],'previous_price':r['terms']['amount'],'party':party});r.update(terms=preview['terms'],preview=preview,approvals={},expires=self.state['tick']+168);self.audit('corporate_counteroffer',copy.deepcopy(r));return r

 def lifecycle_execute(self,p):
  r=self.lifecycle_record(p['id'])
  if r['status']!='PENDING' or self.state['tick']>r['expires']:raise ValueError('Action already completed or expired')
  preview=self.lifecycle_preview(r['terms'])
  if preview['ownership_before']!=r['preview']['ownership_before']:raise ValueError('Ownership changed since preview; obtain a fresh proposal')
  for req in preview['requirements']:
   approval=r['approvals'].get(req['key'])
   if not approval:raise ValueError('Missing approval: '+req['key'])
   if req['role']=='liquidator':self.authority(req['entity'],'disclose')
   else:
    self.authority(req['entity'],'govern',approval['reviewer'])
    if req['role']=='board' and (approval['reviewer']==r['initiator'] or approval['reviewer'] not in self.state['entities'][req['entity']]['directors']):raise ValueError('Board authority changed')
  t=r['terms'];kind=r['kind'];e=self.state['entities'][t['entity']]
  if kind=='sale':self.lifecycle_sale(t,r['id'])
  elif kind=='swap':self.lifecycle_swap(t)
  elif kind in ('dividend','capital_return'):self.lifecycle_distribution(t,kind)
  elif kind=='merger':self.lifecycle_merge(t)
  elif kind=='liquidation':self.lifecycle_liquidation(t)
  r.update(status='COMPLETED',completed=self.state['time'],final_preview=preview);self.audit('corporate_action_completed',copy.deepcopy(r));return r

 def lifecycle_parent(self,e):
  positive=[(D(q),id) for id,q in e['owners'].items() if D(q)>0];e['parent']=max(positive)[1] if positive else None

 def lifecycle_sale(self,t,reference,actor='player'):
  target=t['entity'];seller=t['seller'];buyer=t['buyer'];e=self.state['entities'][target];q=D(t['quantity']);owned=D(e['owners'][seller]);price=D(str(t['amount']));basis=(self.balance('holding:'+seller+':'+target)*q/owned).quantize(D('.01'))
  self.authority(buyer,'payment',actor)
  self.post('Corporate share acquisition '+target,{'cash:'+buyer:-price,'holding:'+buyer+':'+target:price,'cash:'+seller:price,'holding:'+seller+':'+target:-basis,'pnl:'+seller:basis-price})
  e['owners'][seller]=str(owned-q)
  if D(e['owners'][seller])==0:e['owners'].pop(seller)
  e['owners'][buyer]=str(D(e['owners'].get(buyer,0))+q);self.lifecycle_parent(e)
  from .engine import uid
  fair=self.corporate_interest_value(target,self.metrics(target))*q/D(e['units']);reasons=['Share consideration materially exceeds supported equity value'] if price>=100000 and price>fair*D('1.25') else []
  self.state['related_transactions'].append(dict(id=uid(),source=buyer,destination=seller,kind='share_acquisition',amount=amt(price),fair_value=amt(fair),classification='QUESTIONABLE GOVERNANCE' if reasons else 'LEGITIMATE',reasons=reasons,actor=actor,status='SETTLED',time=self.state['time'],tick=self.state['tick'],corporate_action=reference,disclosed=True,terms={'entity':target,'quantity':str(q)},settlements=[{'time':self.state['time'],'amount':amt(price)}]))

 def lifecycle_swap(self,t):
  c=next(c for c in self.state['claims_book'] if c['id']==t['claim']);a=D(str(t['amount']));allowance=(D(c['allowance'])*a/D(c['balance'])).quantize(D('.01'));debtor=c['debtor'];creditor=c['creditor'];e=self.state['entities'][debtor];issued=D(t['issued'])
  self.post('Creditor-approved debt for equity '+c['id'],{'debt:'+debtor+':claim_'+c['id']:a,'equity:'+debtor:-a,'claim:'+creditor+':'+c['id']:-a,'allowance:'+creditor+':'+c['id']:allowance,'holding:'+creditor+':'+debtor:a-allowance})
  c['balance']=amt(D(c['balance'])-a);c['allowance']=amt(D(c['allowance'])-allowance);c.setdefault('conversions',[]).append({'time':self.state['time'],'amount':amt(a),'units':str(issued),'valuation':t['valuation']})
  e['units']=str(D(e['units'])+issued);e['owners'][creditor]=str(D(e['owners'].get(creditor,0))+issued);self.lifecycle_parent(e)
  if D(c['balance'])==0:
   c['status']='CONVERTED'
   if c.get('secured'):self.release_pledge({'id':c['secured']})

 def lifecycle_distribution(self,t,kind):
  id=t['entity'];e=self.state['entities'][id];amount=D(str(t['amount']));owners=[(o,D(q)) for o,q in e['owners'].items() if D(q)>0];total=sum((q for _,q in owners),D(0));remaining=amount;lines={'cash:'+id:-amount,'equity:'+id:amount};paid=[]
  self.authority(id,'payment')
  for index,(owner,units) in enumerate(owners):
   share=remaining if index==len(owners)-1 else (amount*units/total).quantize(D('.01'),rounding='ROUND_DOWN');remaining-=share;lines['cash:'+owner]=share
   basis=min(share,self.balance('holding:'+owner+':'+id)) if kind=='capital_return' else D(0)
   if basis:lines['holding:'+owner+':'+id]=-basis
   lines['pnl:'+owner]=basis-share;paid.append({'owner':owner,'cash':amt(share),'basis_returned':amt(basis)})
  self.post('Pro-rata '+kind+' '+id,lines);self.state.setdefault('corporate_distributions',[]).append({'entity':id,'kind':kind,'time':self.state['time'],'amount':amt(amount),'payments':paid})

 def lifecycle_cancel_work(self,entity,reason):
  for collection in ('employee_tasks','staff_recommendations'):
   for row in self.state.get(collection,[]):
    if row.get('entity')==entity and row.get('status') in ('QUEUED','AWAITING APPROVAL','PENDING','ASSIGNED'):
     row['status']='CANCELLED';row['result']=reason;row['reason']=reason
  for row in self.state.get('scheduled_instructions',[]):
   if row.get('status')=='QUEUED' and row.get('payload',{}).get('source')==entity:
    row['status']='CANCELLED';row['reason']=reason

 def lifecycle_liquidation(self,t):
  id=t['entity'];w=self.state;self.lifecycle_cancel_work(id,'Voluntary liquidation suspends ordinary mandates')
  for employee in list(w.get('employees',[])):
   if employee['entity']==id and employee['status']=='EMPLOYED':
    self.accrue_employee(employee);notice=(D(employee['salary'])*D(employee['contract']['notice_hours'])/720).quantize(D('.01'))
    if notice:self.post('Liquidation contractual notice '+employee['id'],{'expense:payroll:'+id:notice,'debt:'+id+':payroll_'+employee['id']:-notice});employee['unpaid']=amt(D(employee['unpaid'])+notice)
    self.employee_departure(employee,'DISMISSED','Voluntary liquidation; earned and notice wages remain creditor claims')
  for event in w.get('social_events',[]):
   if event['owner']==id and event['status']=='SCHEDULED':self.refund_activity(event,'Voluntary liquidation')
  for office in w.get('offices',[]):
   if office['entity']==id and office['status']=='ACTIVE':
    if office['mode']=='lease':
     rou=self.balance('rou:'+id+':'+office['id'])
     if rou:self.post('Liquidation office right-of-use impairment',{'rou:'+id+':'+office['id']:-rou,'expense:office_rent:'+id:rou})
     office['status']='TERMINATED';office['unpaid_rent']=amt(-self.balance('debt:'+id+':lease_'+office['id']))
    else:office['status']='VACATED'
  admin=self.appoint_administrator({'entity':id});admin.update(mode='VOLUNTARY LIQUIDATION',phase='REALISATION',claims_registered=[c['id'] for c in w['claims_book'] if c['debtor']==id and D(c['balance'])>0]);w['entities'][id]['liquidation']=True
  if id in w.get('operating_plans',{}):w['entities'][id]['liquidation_operating_plan']=w['operating_plans'].pop(id)
  self.list_administrator_assets(admin)

 def lifecycle_merge(self,t):
  w=self.state;src=t['entity'];dst=t['survivor'];source=w['entities'][src];target=w['entities'][dst];lines={};self.lifecycle_cancel_work(src,'Legal merger: obtain a new successor mandate')
  def add(key,v):lines[key]=lines.get(key,D(0))+v
  for employee in w.get('employees',[]):
   if employee['entity']==src and employee['status']=='EMPLOYED':self.accrue_employee(employee)
  # Accrue real coupon entitlements before transferring the legal holder.
  for position in list(w.get('treasury_positions',{}).values()):
   if position['account']==src:self.treasury_accrue(w['treasury_securities'][position['security']])
  for key,value in list(w['balances'].items()):
   tokens=key.split(':')
   if src not in tokens:continue
   # Every account token is a legal account ID; journal rows are never rewritten.
   new=':'.join(dst if token==src else token for token in tokens);v=D(value)
   if new!=key:add(key,-v);add(new,v)
  basis=self.balance('holding:'+dst+':'+src);source_capital=-self.balance('equity:'+src)
  # Parent's share investment is cancelled against merger equity reserves.
  if basis:
   add('holding:'+dst+':'+src,-basis)
   # If generic token remap moved this key, undo that remap first.
   new='holding:'+dst+':'+dst;add('holding:'+dst+':'+src,basis);add(new,-basis);add('equity:'+dst,basis)
  # A subsidiary merger is not a new shareholder contribution or withdrawal.
  # Keep parent paid-in capital unchanged and recognise the basis difference in equity reserves.
  reserve=basis-source_capital
  if reserve:add('equity:'+dst,-reserve);add('capital_reserve:'+dst,reserve)
  # Coupon and reserve creditor IDs are embedded in liability suffixes.
  for key,value in list(w['balances'].items()):
   for prefix in ('debt:us_treasury:coupon_','debt:federal_reserve:reserve_'):
    if key.startswith(prefix+src+('_' if prefix.endswith('coupon_') else '')) and (prefix.endswith('coupon_') or key==prefix+src):
     new=prefix+dst+key[len(prefix+src):];add(key,-D(value));add(new,D(value))
  self.post('Universal succession merger '+src+' → '+dst,lines)
  for pos in list(w['positions'].values()):
   if pos['account']==src:w['positions'].pop(src+':'+pos['symbol']);pos['origin_account']=src;pos['account']=dst;w['positions'][dst+':'+pos['symbol']]=pos
  for position in list(w.get('treasury_positions',{}).values()):
   if position['account']!=src:continue
   security=position['security'];w['treasury_positions'].pop(src+':'+security);successor=w['treasury_positions'].setdefault(dst+':'+security,dict(account=dst,security=security,face='0.00'));successor['face']=amt(D(successor['face'])+D(position['face']))
  for pledge in w.get('treasury_pledges',[]):
   if pledge['account']==src:pledge['account']=dst
  for facility in w.get('fed',{}).get('facilities',[]):
   if facility['borrower']==src:facility['borrower']=dst
  for order in w['orders']:
   if order['account']==src and order['status'] in ('OPEN','PARTIAL'):order['status']='CANCELLED';order['cancel_reason']='Legal merger; resubmit under successor mandate'
  for collection,field in [('loans','account'),('claims_book','creditor'),('claims_book','debtor'),('pledges','owner'),('pledges','beneficiary'),('owned_assets','owner'),('offices','entity'),('property_contracts','owner'),('legal_cases','entity'),('employees','entity')]:
   for record in w.get(collection,[]):
    if record.get(field)==src:record.setdefault('origin_'+field,src);record[field]=dst
  for c in w['claims_book']:
   if c['creditor']==dst and c['debtor']==dst and D(c['balance'])>0:
    a=D(c['balance']);allowance=D(c['allowance']);self.post('Merger internal debt cancellation '+c['id'],{'claim:'+dst+':'+c['id']:-a,'debt:'+dst+':claim_'+c['id']:a,'allowance:'+dst+':'+c['id']:allowance,'pnl:'+dst:-allowance});c['balance']='0.00';c['allowance']='0.00';c['status']='MERGED INTERNAL'
    if c.get('secured'):self.release_pledge({'id':c['secured']})
  for employee in w.get('employees',[]):
   if employee.get('origin_entity')==src:
    employee['delegation']['trade']=False
    if employee.get('department_policy'):employee['department_policy']['level']=1
  for child in w['entities'].values():
   if D(child.get('owners',{}).get(src,0))>0:
    child['owners'][dst]=str(D(child['owners'].get(dst,0))+D(child['owners'].pop(src)));self.lifecycle_parent(child)
  if src in w.get('operating_plans',{}):
   plan=w['operating_plans'].pop(src);source['merged_operating_plan']=copy.deepcopy(plan)
   combined=copy.deepcopy(w['operating_plans'].get(dst,plan))
   if dst in w['operating_plans']:
    for key in ('research','technology','salary'):combined[key]=amt(D(combined.get(key,0))+D(plan.get(key,0)))
   combined['entity']=dst;w['operating_plans'][dst]=combined;self.sync_staff_plan(dst)
  target.setdefault('predecessors',[]).extend([src]+source.get('predecessors',[]));source.update(status='MERGED',successor=dst,owners={},units='0',parent=None);self._realised_cache={}

 def administration_tick(self):
  for admin in self.state.get('administrations',[]):
   if admin.get('mode')=='VOLUNTARY LIQUIDATION' and admin['status']!='DISSOLVED':self.list_administrator_assets(admin)
  super().administration_tick()
  for admin in self.state.get('administrations',[]):
   if admin.get('mode')!='VOLUNTARY LIQUIDATION':continue
   admin['phase']='DISSOLVED' if admin['status']=='DISSOLVED' else 'INSOLVENCY RECOVERY' if admin['status']=='UNRESOLVED SHORTFALL' else 'REALISATION / DISTRIBUTION'
   admin['final_account']={'time':self.state['time'],'cash':amt(self.cash(admin['entity'])),'remaining_liabilities':self.metrics(admin['entity'])['debt'],'distributed':amt(sum((D(d['amount']) for d in admin['distributions']),D(0)))}
