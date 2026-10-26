"""Evidence-driven oversight, finite recoveries and non-destructive administration."""
from decimal import Decimal as D
import json,random,math
from .integrity import amt

class ResolutionMixin:
 def install_resolution(self):
  if self.state.get('resolution_version'):return
  self.state['paused']=True;self.state.update(resolution_version=1,legal_cases=[],evidence_records=[],administrations=[])
  self.audit('resolution_initialized',{'policy':'No historical allegations, fines or cash adjustments generated on migration'})
 def evidence(self,kind,reference,description,entity,amount='0'):
  from .engine import uid
  record={'id':uid(),'kind':kind,'reference':reference,'description':description,'entity':entity,'amount':amt(amount),'time':self.state['time']}
  self.db.execute('insert into evidence_records values(?,?,?)',(record['id'],self.state['id'],json.dumps(record)));self.state['evidence_records'].append(record);return record['id']
 def governance_controls(self,p):
  e=self.authority(p['entity'],'govern');level=int(p['level'])
  if level not in (0,1,2,3):raise ValueError('Control level must be0–3')
  e['controls']=level
  if level:
   e['signatories']['board']=['govern'];e['signatories']['compliance']=['disclose']
   if 'board' not in e['directors']:e['directors'].append('board')
  else:
   e['signatories'].pop('board',None);e['signatories'].pop('compliance',None);e['directors']=[d for d in e['directors'] if d!='board']
  e['compliance_monthly']=amt(D(500)*level);self.audit('governance_controls',{'entity':e['id'],'level':level,'monthly_cost':e['compliance_monthly']});return e
 def complaint(self,p):
  from .engine import uid
  origin=p['entity'];entity=self.successor_account(origin)
  if entity not in self.state['entities']:raise ValueError('Unknown institution')
  reason=str(p.get('reason','Investor complaint'))[:500];record=self.evidence('COMPLAINT',p.get('reference'),reason,entity)
  case=dict(id=uid(),origin_entity=origin,pacing_version=1,opened_time=self.state['time'],reference=p.get('reference'),concern=reason,stage_tick=self.state['tick'],entity=entity,stage='PRELIMINARY',evidence=[record],score=5,opened=self.state['tick'],deadline=self.state['tick']+72,requests=[],responses=[],penalty=None,reviewed_transactions=[])
  for transaction in self.state.get('related_transactions',[]):
   if transaction['id']==p.get('reference') and self.successor_account(transaction['source'])==entity:transaction['observed']=self.state['time']
  case['ownership_context']=self.ownership_context(entity)
  self.state['legal_cases'].append(case);self.message('Financial Conduct Office','Preliminary enquiry',reason+' Case '+case['id']+'. An allegation is not an adjudicated finding.');return case
 def respond_case(self,p):
  case=next(c for c in self.state['legal_cases'] if c['id']==p['id']);self.authority(case['entity'],'disclose');choice=p['response']
  if choice not in ('provide_records','contest','voluntary_disclosure'):raise ValueError('Unknown regulatory response')
  if any(r['tick']==self.state['tick'] and r['response']==choice for r in case['responses']):raise ValueError('Response already recorded this hour')
  case['responses'].append({'tick':self.state['tick'],'response':choice,'time':self.state['time']});case['evidence'].append(self.evidence('RESPONSE',case['id'],choice.replace('_',' '),case['entity']));case['deadline']=self.state['tick']+72
  if choice=='provide_records':case['cooperating']=True
  if choice=='voluntary_disclosure':case['mitigation']=True
  self.audit('regulatory_response',{'case':case['id'],'response':choice});return case
 def regulatory_daily(self):
  w=self.state
  for i,r in enumerate(w.get('related_transactions',[])):
   if r['status']!='SETTLED' or not r['reasons'] or r.get('observed'):continue
   e=w['entities'][r['source']];rng=random.Random(w['seed']+w['tick']*17+i*113)
   magnitude=float(D(r['amount'])/max(D(1),D(r.get('source_nav_before',self.metrics(r['source'])['equity']))));conspicuous=magnitude>=.1 and D(r['amount'])>=100000
   if 'next_detection_review' not in r:
    schedule=random.Random(w['seed']+int(r.get('tick',0))*17+i*113);r['next_detection_review']=int(r.get('tick',w['tick']))+(24 if conspicuous else (3+schedule.randrange(15))*24)
   if w['tick']<r['next_detection_review']:continue
   r['next_detection_review']=w['tick']+7*24
   suspicious=sum(x['source']==r['source'] and bool(x['reasons']) and x['status']=='SETTLED' for x in w['related_transactions'])
   prior_findings=sum(c['entity']==self.successor_account(r['source']) and c['stage'] in ('FORMAL INVESTIGATION','ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL') for c in w.get('legal_cases',[]))
   chance=min(.9,.025+.04*e['controls']+min(.4,magnitude*.8)+min(.05,math.log1p(float(D(r['amount'])/10000))*.01)+min(.12,suspicious*.015)+min(.2,prior_findings*.04)+(.2 if conspicuous else 0))
   if rng.random()>chance:continue
   r['observed']=w['time'];case=self.complaint({'entity':r['source'],'reason':'Transaction review found an authority/valuation discrepancy','reference':r['id']});ev=self.evidence('TRANSACTION',r['id'],'; '.join(r['reasons']),r['source'],r['amount']);case['evidence'].append(ev);case['score']=25;case['reviewed_transactions'].append(r['id'])
  for case in w.get('legal_cases',[]):
   if case['stage']=='CLOSED':continue
   entity=case['entity'];observable=[r for r in w.get('related_transactions',[]) if self.successor_account(r['source'])==entity and r['reasons'] and r['status']=='SETTLED']
   for r in observable:
    if r['id'] not in case['reviewed_transactions'] and (r.get('observed') or r['id']==case.get('reference') or case.get('cooperating') or (not case.get('pacing_version') and r['disclosed'])):
     case['reviewed_transactions'].append(r['id']);case['evidence'].append(self.evidence('AUTHORISATION REVIEW',r['id'],'Recorded mandate compared with actual transfer',entity,r['amount']));case['score']+=15
   proven=[r for r in observable if r['id'] in case['reviewed_transactions']]
   if not proven:
    if w['tick']-case['opened']>=7*24:case['stage']='CLOSED';case['outcome']='No corroborated material discrepancy'
    continue
   case['score']+=5 if case.get('cooperating') else 8
   if w['tick']>case['deadline'] and not case.get('cooperating'):case['score']+=5
   prior=case['stage']
   if case.get('pacing_version'):
    elapsed=w['tick']-case.get('stage_tick',case['opened'])
    if prior=='PRELIMINARY' and elapsed>=72:case['stage']='INFORMATION REQUEST'
    elif prior=='INFORMATION REQUEST' and elapsed>=120 and case['score']>=40:case['stage']='FORMAL INVESTIGATION'
    elif prior=='FORMAL INVESTIGATION' and elapsed>=240 and case['score']>=70:case['stage']='ENFORCEMENT'
    elif prior=='ENFORCEMENT' and elapsed>=336 and case['score']>=100:case['stage']='CIVIL RECOVERY' if case.get('mitigation') else 'PROSECUTION REFERRAL'
    if prior!=case['stage']:case['stage_tick']=w['tick']
   else:
    # Preserve the historical case state/rules; never downgrade existing enforcement.
    if case['score']<40:case['stage']='INFORMATION REQUEST'
    elif case['score']<70:case['stage']='FORMAL INVESTIGATION'
    elif case['score']<100:case['stage']='ENFORCEMENT'
    elif case.get('mitigation'):case['stage']='CIVIL RECOVERY'
    else:case['stage']='PROSECUTION REFERRAL'
   if case['stage'] in ('ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL'):
    for transaction in proven:
     if transaction['kind']=='appropriation':self.impose_restitution(transaction,case)
    if entity not in w.setdefault('frozen_funds',[]):w['frozen_funds'].append(entity)
    if not case['penalty']:
     amount=min(D('10000000'),sum((D(r['amount']) for r in proven),D(0))*D('.1')).quantize(D('.01'));claim=self.create_claim('regulator',entity,amount,'ADMINISTRATIVE PENALTY',case['id']);case['penalty']=claim['id'];self.post('Administrative penalty '+case['id'],{'expense:penalty:'+entity:amount,'debt:'+entity+':claim_'+claim['id']:-amount,'claim:regulator:'+claim['id']:amount,'pnl:regulator':-amount})
    for fund in w['funds']:
     if fund['id']==entity:
      for npc in w['npcs']:
       if npc['id'] in fund['investors']:npc['trust']=max(0,npc['trust']-3)
   if prior!=case['stage']:
    case['requests'].append({'time':w['time'],'stage':case['stage'],'deadline_tick':case['deadline']});self.message('Financial Conduct Office',case['stage'],f"Case {case['id']}: {entity}. Evidence references {', '.join(case['evidence'])}. Documented regulatory action; prosecution referral is not a conviction.")
    if case['stage'] in ('FORMAL INVESTIGATION','ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL'):self.news('Institutional oversight: '+case['stage'].lower(),'A local authority is reviewing documented transactions and creditor claims.','REGULATORY')
  if w['tick']%720==0:
   for e in w['entities'].values():
    cost=D(e.get('compliance_monthly','0'))
    if cost<=0:continue
    self.post('Compliance and audit operating cost '+e['id'],{'expense:compliance:'+e['id']:cost,'debt:'+e['id']+':compliance':-cost});paid=min(cost,self.available_cash(e['id']))
    if paid and not self.is_frozen(e['id']):self.post('Compliance provider settlement',{'cash:'+e['id']:-paid,'debt:'+e['id']+':compliance':paid,'cash:external_auditor':paid,'pnl:external_auditor':-paid})
 def appoint_administrator(self,p):
  from .engine import uid
  entity=p['entity'];self.authority(entity,'govern')
  if self.state['entities'][entity]['kind']=='personal':raise ValueError('Corporate administration cannot dissolve personal property')
  existing=next((a for a in self.state['administrations'] if a['entity']==entity),None)
  if existing:return existing
  record=dict(id=uid(),entity=entity,status='ADMINISTRATION',time=self.state['time'],distributions=[],shortfall='0.00');self.state['administrations'].append(record);self.state['entities'][entity]['status']='ADMINISTRATION'
  for o in self.state['orders']:
   if o['account']==entity and o['status'] in ('OPEN','PARTIAL'):o['status']='CANCELLED'
  for c in self.state['claims_book']:
   if c['debtor']==entity and D(c['balance'])>0:c['status']='DEFAULT'
  for loan in self.state['loans']:
   if loan['account']==entity and D(loan['balance'])>0:loan['status']='DEFAULT'
  self.audit('administrator_appointed',record.copy());return record
 def release_pledge(self,p):
  pledge=next(x for x in self.state['pledges'] if x['id']==p['id'])
  if pledge['status']!='ACTIVE':return pledge
  if any(c.get('secured')==pledge['id'] and D(c['balance'])>0 for c in self.state['claims_book']):raise ValueError('Collateral secures an outstanding obligation')
  a=D(pledge['amount']);self.post('Collateral release '+pledge['id'],{'memo:pledge:'+pledge['owner']+':'+pledge['id']:-a,'memo:contra:'+pledge['owner']+':'+pledge['id']:a});pledge['status']='RELEASED';return pledge
 def administrator_payment(self,entity,creditor,a):
  kind,obj=creditor
  if kind=='claim':self.settle_claim_cash(obj,a,'Administrator recovery')
  elif kind=='bank':self.repay_credit({'id':obj['id'],'amount':a})
  elif kind=='redemption':
   lines={'cash:'+entity:-a,'debt:'+entity+':redemption:'+obj['id']:a};who=obj['investor']
   if who=='personal':lines.update({'cash:personal':a,'receivable:personal:'+entity:-a})
   else:lines.update({'npc:'+who+':cash':a,'npc:'+who+':receivable:'+obj['id']:-a});n=next(n for n in self.state['npcs'] if n['id']==who);n['wealth']=amt(D(n['wealth'])+a)
   self.post('Administrator redemption recovery '+obj['id'],lines);obj['paid']=amt(D(obj['paid'])+a);obj['remaining']=amt(D(obj['remaining'])-a);obj['status']='SETTLED' if D(obj['remaining'])==0 else 'PARTIAL';obj['settlements'].append({'time':self.state['time'],'amount':amt(a),'destination':who})
  elif kind in ('office_rent','office_operations'):
   rent=kind=='office_rent';field='unpaid_rent' if rent else 'unpaid_operations';key='debt:'+entity+':'+('lease_' if rent else 'office_')+obj['id'];self.post('Administrator premises creditor recovery',{'cash:'+entity:-a,key:a,'cash:property_suppliers':a,'pnl:property_suppliers':-a});obj[field]=amt(D(obj[field])-a);obj['paid']=amt(D(obj['paid'])+a)
  elif kind=='legal':
   self.post('Administrator legal creditor recovery',{'cash:'+entity:-a,'debt:'+entity+':legal_'+obj['id']:a,'cash:legal_suppliers':a,'pnl:legal_suppliers':-a});obj['legal_cost_unpaid']=amt(D(obj['legal_cost_unpaid'])-a)
  elif kind=='payroll':
   self.post('Administrator employee wage recovery',{'cash:'+entity:-a,'debt:'+entity+':payroll_'+obj['id']:a,'cash:'+obj['id']:a,'pnl:'+obj['id']:-a});obj['unpaid']=amt(D(obj['unpaid'])-a);obj['paid']=amt(D(obj['paid'])+a)
  elif kind=='lifestyle':
   self.post('Administrator asset operating recovery',{'cash:'+entity:-a,'debt:'+entity+':lifestyle_'+obj['id']:a,'cash:lifestyle_suppliers':a,'pnl:lifestyle_suppliers':-a});obj['unpaid']=amt(D(obj['unpaid'])-a);obj['running_paid']=amt(D(obj['running_paid'])+a)
  elif kind=='margin':self.post('Administrator prime funding recovery',{'cash:'+entity:-a,'debt:'+entity+':margin':a,'cash:prime':a,'prime:loan:'+entity:-a})
  elif kind=='manager':
   recipient=next((f.get('manager','personal') for f in self.state['funds'] if f['id']==entity),'personal');self.post('Administrator manager-fee recovery',{'cash:'+entity:-a,'debt:'+entity+':manager_fees':a,'cash:'+recipient:a,'receivable:'+recipient+':'+entity:-a})
  elif kind in ('aggregate_payroll','materials'):
   destination=self.ma_account('households' if kind=='aggregate_payroll' else 'suppliers');self.post('Administrator private-business creditor recovery',{'cash:'+entity:-a,obj:a,'cash:'+destination:a,'pnl:'+destination:-a})
  else:self.post('Administrator operating creditor recovery',{'cash:'+entity:-a,obj:a,'cash:external_creditors':a,'pnl:external_creditors':-a})
 def administration_tick(self):
  from .engine import uid
  for admin in self.state.get('administrations',[]):
   if admin['status']=='DISSOLVED':continue
   entity=admin['entity']
   self.fed_enforce_facilities(entity)
   self.treasury_resolution_sale(entity)
   for pos in list(self.state['positions'].values()):
    if pos['account']!=entity:continue
    if any(o['account']==entity and o.get('forced') and o['status'] in ('OPEN','PARTIAL') for o in self.state['orders']):continue
    o=dict(id=uid(),account=entity,symbol=pos['symbol'],qty=amt(abs(D(pos['qty']))),remaining=amt(abs(D(pos['qty']))),filled='0.00',side='sell' if D(pos['qty'])>0 else 'buy',type='market',status='OPEN',margin=True,time=self.state['time'],forced=True);self.state['orders'].append(o);self.process_order(o,True)
   # Realise bank deposits into cash when withdrawals are actually available.
   for bank in self.state['banks']:
    deposit=self.balance('savings:'+entity+':'+bank['id']);paid=min(deposit,D(bank['cash']))
    if paid and bank.get('status')!='DISTRESSED':
     self.post('Administrator deposit recovery',{'cash:'+entity:paid,'savings:'+entity+':'+bank['id']:-paid});bank['cash']=amt(D(bank['cash'])-paid);bank['deposits']=amt(D(bank['deposits'])-paid);self.bank_sync(bank,'Administrator withdrawal')
   creditors=[]
   for c in self.state['claims_book']:
    if c['debtor']==entity and D(c['balance'])>0:
     secured=D(0)
     if c.get('secured'):secured=min(D(c['balance']),D(next(q['amount'] for q in self.state['pledges'] if q['id']==c['secured'])))
     if secured:creditors.append((0,'claim',c,secured))
     if D(c['balance'])>secured:creditors.append((1,'claim',c,D(c['balance'])-secured))
   for l in self.state['loans']:
    if l['account']==entity and D(l['balance'])>0:creditors.append((1,'bank',l,D(l['balance'])))
   for r in self.state.get('redemptions',[]):
    if r['fund']==entity and D(r['remaining'])>0:creditors.append((1,'redemption',r,D(r['remaining'])))
   for suffix,kind in [('margin','margin'),('manager_fees','manager'),('operations','other'),('compliance','other'),('business','other'),('workforce','aggregate_payroll'),('materials','materials')]:
    key='debt:'+entity+':'+suffix;owed=-self.balance(key)
    if owed>0:creditors.append((0 if suffix=='margin' else 1,kind,key if kind in ('other','aggregate_payroll','materials') else None,owed))
   for employee in self.state.get('employees',[]):
    if employee['entity']==entity and D(employee['unpaid'])>0:creditors.append((1,'payroll',employee,D(employee['unpaid'])))
   for asset in self.state.get('owned_assets',[]):
    if asset['owner']==entity and D(asset['unpaid'])>0:creditors.append((1,'lifestyle',asset,D(asset['unpaid'])))
   for case in self.state['legal_cases']:
    if case['entity']==entity and D(case.get('legal_cost_unpaid','0'))>0:creditors.append((1,'legal',case,D(case['legal_cost_unpaid'])))
   for office in self.state.get('offices',[]):
    if office['entity']!=entity:continue
    if office['mode']=='lease' and D(office['unpaid_rent'])>0:creditors.append((1,'office_rent',office,D(office['unpaid_rent'])))
    if D(office['unpaid_operations'])>0:creditors.append((1,'office_operations',office,D(office['unpaid_operations'])))
   for priority in (0,1):
    rows=[r for r in creditors if r[0]==priority];total=sum((r[3] for r in rows),D(0))
    if priority==0:
     for _,kind,c,owed in rows:
      if kind=='claim' and c.get('secured'):
       pledge=next(p for p in self.state['pledges'] if p['id']==c['secured']);pledge['status']='ENFORCEMENT'
    budget=min(self.available_cash(entity),total);left=budget
    for i,(_,kind,obj,owed) in enumerate(rows):
     a=min(owed,left if i==len(rows)-1 else (budget*owed/total).quantize(D('.01'),rounding='ROUND_DOWN'));left-=a
     if a<=0:continue
     self.administrator_payment(entity,(kind,obj),a);admin['distributions'].append({'time':self.state['time'],'priority':priority,'kind':kind,'amount':amt(a)})
   remaining=D(self.metrics(entity)['debt']);admin['shortfall']=amt(remaining)
   has_assets=self.treasury_value(entity)>0 or self.productive_value(entity)>0 or any(D(e.get('units',0))>0 and D(e.get('owners',{}).get(entity,0))>0 for e in self.state['entities'].values()) or any(p['account']==entity for p in self.state['positions'].values()) or any(a['owner']==entity and a['status']!='SOLD' for a in self.state.get('owned_assets',[])) or D(self.metrics(entity)['receivables'])>0 or D(self.metrics(entity)['savings'])>0 or D(self.metrics(entity)['receivables'])>0 or D(self.metrics(entity)['investment'])>0 or any(c['creditor']==entity and D(c['balance'])>0 for c in self.state['claims_book'])
   if remaining>0 and not has_assets and self.cash(entity)==0:
    admin['status']='UNRESOLVED SHORTFALL'
    for c in self.state['claims_book']:
     if c['debtor']==entity and D(c['balance'])>0:
      change=D(c['balance'])-D(c['allowance'])
      if change:self.post('Administration expected-credit-loss provision',{'expense:impairment:'+c['creditor']:change,'allowance:'+c['creditor']+':'+c['id']:-change});c['allowance']=c['balance']
    for loan in self.state['loans']:
     if loan['account']!=entity or D(loan['balance'])<=0:continue
     bank=next(b for b in self.state['banks'] if b['id']==loan['bank']);change=D(loan['balance'])-D(loan.get('allowance','0'));loan['allowance']=loan['balance'];bank['allowance']=amt(D(bank.get('allowance','0'))+change);bank['equity']=amt(D(bank['equity'])-change);self.bank_sync(bank,'Administration lender expected loss')
   elif remaining==0 and not has_assets and not any(c['entity']==entity and c['stage']!='CLOSED' for c in self.state.get('legal_cases',[])):
    self.distribute_residual(entity);admin['status']='DISSOLVED';self.state['entities'][entity]['status']='DISSOLVED'
 def distribute_residual(self,entity):
  f=next((f for f in self.state['funds'] if f['id']==entity),None);e=self.state['entities'][entity];owners=f['investors'] if f else e['owners'];total=sum((D(u) for u in owners.values()),D(0));cash=self.cash(entity);left=cash
  for i,(owner,u) in enumerate(list(owners.items())):
   if D(u)<=0:continue
   a=min(left,(cash*D(u)/total).quantize(D('.01')));left-=a;lines={'cash:'+entity:-a,'equity:'+entity:a}
   if owner in self.accounts():
    key=('investment:' if f else 'holding:')+owner+':'+entity;basis=self.balance(key);lines.update({'cash:'+owner:a,key:-basis,'pnl:'+owner:basis-a})
   elif any(n['id']==owner for n in self.state['npcs']):
    n=next(n for n in self.state['npcs'] if n['id']==owner);key='npc:'+owner+':investment:'+entity;basis=self.balance(key);lines.update({'npc:'+owner+':cash':a,key:-basis,'npc:'+owner+':pnl':basis-a});n['wealth']=amt(D(n['wealth'])+a)
   else:lines.update({'cash:external_owners':a,'pnl:external_owners':-a})
   self.post('Residual shareholder distribution '+entity,lines);owners[owner]='0.00'
  if left>0:self.post('Rounding residual to external ownership',{'cash:'+entity:-left,'equity:'+entity:left,'cash:external_owners':left,'pnl:external_owners':-left})
  if f:f['units']='0.00'
  else:e['units']='0.00'

 def impose_restitution(self,r,case):
  if r.get('claim'):return next(c for c in self.state['claims_book'] if c['id']==r['claim'])
  a=D(r['amount']);src=self.successor_account(r['source']);dst=self.successor_account(r['destination']);claim=self.create_claim(src,dst,a,'RECOVERY',r['id']);r['claim']=claim['id']
  self.post('Restitution obligation imposed '+r['id'],{'claim:'+src+':'+claim['id']:a,'pnl:'+src:-a,'expense:restitution:'+dst:a,'debt:'+dst+':claim_'+claim['id']:-a})
  case['evidence'].append(self.evidence('RESTITUTION ORDER',r['id'],'Separate obligation recognised after original appropriation loss',r['source'],a));self.audit('restitution_imposed',{'transaction':r['id'],'claim':claim['id'],'case':case['id']});return claim
 def restriction_summary(self,account):
  cases=[c for c in self.state.get('legal_cases',[]) if c['entity']==account and c['stage'] in ('ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL')]
  legacy=[c for c in self.state.get('investigations',[]) if not c.get('legal_case') and c.get('status')=='ENFORCEMENT' and any(q['id']==c['claim'] and q['fund']==account for q in self.state['claims'])]
  refs=[c['id'] for c in cases+legacy];claims=[q for q in self.state.get('claims_book',[]) if any(self.case_claim_in_scope(c,q) for c in cases)]
  return {'account':account,'frozen':self.is_frozen(account),'case_refs':refs,'scope':'Named account: trading, transfers and withdrawals prohibited; authorised recovery permitted','outstanding':amt(sum((D(q['balance']) for q in claims),D(0))),'condition':'Settle case-linked recovery claims and penalties; record cooperation; review cannot override another case or administration','legacy':bool(legacy)}
 def restriction_message(self,account,action='Transaction'):
  r=self.restriction_summary(account);refs=', '.join(r['case_refs']) or 'administration or recorded global/account restriction'
  return f"{action} prohibited: {self.state.get('entities',{}).get(account,{}).get('name',account)} is frozen; case {refs}. See Oversight & Resolution for recovery and review."
 def review_restrictions(self,p):
  c=next(c for c in self.state['legal_cases'] if c['id']==p['id']);self.authority(c['entity'],'disclose')
  if c['stage'] not in ('ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL','CLOSED'):raise ValueError('Case is not at restriction review stage')
  self.validate_programme_case_recovery(c)
  relevant=[q for q in self.state['claims_book'] if self.case_claim_in_scope(c,q)]
  outstanding=sum((D(q['balance']) for q in relevant),D(0))
  if outstanding>0:raise ValueError(f'Review refused: £{outstanding:,.2f} of case-linked penalties/recovery remains unpaid')
  if not c.get('cooperating') and not c.get('mitigation'):raise ValueError('Review requires preserved records or voluntary disclosure/cooperation')
  if not c.get('penalty') or not any(q['id']==c['penalty'] for q in relevant):raise ValueError('Restriction review requires a verified enforcement penalty/resolution record')
  c['stage']='CLOSED';c['outcome']='Closed with findings after obligation checks and regulatory review';c['evidence'].append(self.evidence('RESTRICTION REVIEW',c['id'],'Obligations satisfied; original records and findings preserved',c['entity']))
  other=self.restriction_summary(c['entity'])
  if not other['case_refs'] and self.state.get('entities',{}).get(c['entity'],{}).get('status') not in ('ADMINISTRATION','DISSOLVED'):
   self.state['frozen_funds']=[a for a in self.state.get('frozen_funds',[]) if a!=c['entity']]
  self.audit('restriction_review',{'case':c['id'],'frozen':self.is_frozen(c['entity'])});return {'approved':not self.is_frozen(c['entity']),'status':'REVIEWED','case':c['id']}
 def case_recovery(self,p):
  from .engine import positive
  case=next(c for c in self.state['legal_cases'] if c['id']==p['case']);claim=next(c for c in self.state['claims_book'] if c['id']==p['claim']);self.authority(claim['debtor'],'disclose')
  self.validate_programme_case_recovery(case)
  if case['stage'] not in ('ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL'):raise ValueError('Proceeding has not authorised recovery settlements')
  if not (self.case_claim_in_scope(case,claim)):raise ValueError('Claim is not part of this proceeding')
  a=min(positive(p['amount']),D(claim['balance']))
  if a>self.available_cash(claim['debtor']):raise ValueError('Recovery cannot exceed actual available debtor cash')
  self.settle_claim_cash(claim,a,'Court-authorised voluntary settlement');case['recovered']=amt(D(case.get('recovered','0'))+a);case['mitigation']=True;case['evidence'].append(self.evidence('ACTUAL RECOVERY',claim['id'],'Cash transferred from debtor and corresponding obligation reduced',case['entity'],a))
  relevant=[c for c in self.state['claims_book'] if self.case_claim_in_scope(case,c)]
  if relevant and all(D(c['balance'])==0 for c in relevant):
   case['stage']='CLOSED';case['outcome']='Closed with findings after actual recovery and penalty settlement';entity=case['entity'];other=any(c['entity']==entity and c['id']!=case['id'] and c['stage'] in ('ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL') for c in self.state['legal_cases']);legacy=any(c['fund']==entity and c['status']=='ENFORCEMENT' for c in self.state['claims'])
   if not other and not legacy and entity in self.state.get('frozen_funds',[]):self.state['frozen_funds'].remove(entity)
  self.audit('case_recovery',{'case':case['id'],'claim':claim['id'],'amount':amt(a)});return case
