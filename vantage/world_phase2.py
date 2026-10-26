"""Persistent executive operations, asset activities and creditor recovery.
Extends phase one; migration adds metadata and never restates existing books.
"""
import copy,json,random
from decimal import Decimal as D, ROUND_DOWN
from .integrity import amt
from .staff_autonomy import StaffAutonomyMixin

class WorldPhaseTwoMixin(StaffAutonomyMixin):
 def install_phase_two(self):
  w=self.state
  if w.get('living_world_phase2_version'):return
  w.update(living_world_phase2_version=1,staff_recommendations=[],internal_reviews=[],executive_notices={},story_threads={},asset_incidents=[],networking_opportunities=[],statement_audits=[])
  w['social_contacts']=[dict(id='soc_'+str(i),name=name,role=role,preference=preference,location=location) for i,(name,role,preference,location) in enumerate([('Evelyn Cross','Executive','private_meeting','London'),('Arun Hale','Business partner','investor_reception','Singapore'),('Frances Bell','Journalist','charity_gala','London'),('Leon Mercer','Lawyer','private_meeting','Geneva'),('Ada Brooks','Philanthropist','charity_gala','New York')])]
  for e in w['employees']:self.staff_defaults(e)
  for a in w.get('owned_assets',[]):a.setdefault('incident_review',w['tick']+720)
  for c in w['insiders']:
   c.setdefault('employment','EMPLOYED');c.setdefault('employer',c['symbol']);c.setdefault('employment_history',[]);c.setdefault('next_career_review',w['tick']+720);c.setdefault('base_access',c['access']);c.setdefault('interactions',[])
  self.audit('living_world_phase2_installed',{'balances_unchanged':True,'historical_journal_unchanged':True})
 def phase_two_tick(self):
  w=self.state
  if not w.get('living_world_phase2_version'):return
  if not w.get('microstructure_enabled'):self.publish_events()
  self.department_tick()
  for recommendation in w['staff_recommendations']:
   if recommendation['kind']!='trade' or recommendation['status'] not in ('PENDING','ASSIGNED'):continue
   task=next((t for t in w['employee_tasks'] if t['id']==recommendation.get('task')),None)
   if task and task['status']=='SUBMITTED':
    order=next((o for o in w['orders'] if o['id']==task['result']),None)
    if order:recommendation.update(status='EXECUTED' if D(order['filled'])>0 else 'NOT FILLED',order=order['id'],filled=order['filled'],remaining=order['remaining'],execution_status=order['status'])
    if order and task.get('target_quantity') is not None:
     held=D(w['positions'].get(recommendation['entity']+':'+order['symbol'],{}).get('qty','0'));target=D(str(task['target_quantity']));recommendation['target_reached']=held<=target if order['side']=='sell' else held>=target;recommendation['remaining_to_target']=str(max(D(0),held-target) if order['side']=='sell' else max(D(0),target-held))
   elif task and task['status']=='COMPLETED' and task.get('target_quantity') is not None:recommendation.update(status='COMPLETED',reason=task['result'],target_reached=True)
   elif task and task['status'] in ('FAILED','CANCELLED'):recommendation.update(status=task['status'],reason=task['result'])
   elif w['tick']-recommendation['tick']>168:
    recommendation['status']='EXPIRED'
    if task:task['status']='CANCELLED';task['result']='Underlying research recommendation expired'
  for event in list(w['social_events']):
   if event['status']=='SCHEDULED' and w['tick']>=event['due']:self.finish_activity(event)
  for c in w['insiders']:
   if w['tick']>=c['next_career_review']:
    c['next_career_review']=w['tick']+720;rng=random.Random(str(w['seed'])+c['id']+str(w['tick']//720))
    if c['employment']=='EMPLOYED' and (rng.random()<.12 or c.get('misconduct_discovered')):
     c['employment_history'].append(dict(tick=w['tick'],employer=c['symbol'],outcome='LEFT EMPLOYER'));c['employment']='LEFT EMPLOYER';c['access']=0
     self.executive_notice('contact-left:'+c['id'],c['name']+' has left their employer','Past tips remain on file; this contact no longer has access to future '+c['symbol']+' announcements.')
    elif c['employment']=='EMPLOYED':c['access']=max(10,min(95,c['base_access']+rng.randint(-15,10)))
   for tip in w['intelligence']:
    if tip['contact']==c['id'] and tip.get('case') and not c.get('misconduct_discovered'):
     c['misconduct_discovered']=tip['case'];c['willingness']=max(0,c['willingness']-40);c['access']=max(0,c['access']-30);c['next_career_review']=min(c['next_career_review'],w['tick']+168)
  for programme in w.get('investment_programmes',[]):
   if programme['status']=='WITHDRAWALS SUSPENDED' and w['tick']>=programme.get('withdrawals_suspended_until',0):programme['status']='SUSPENDED'
   if programme.get('claims_converted'):
    self.sync_programme_recovery(programme)
  for case in w['legal_cases']:
   if case['stage']=='CLOSED' and D(case.get('legal_cost_unpaid','0'))>0 and not self.is_frozen(case['entity']):
    paid=min(D(case['legal_cost_unpaid']),self.available_cash(case['entity']))
    if paid:self.post('Closed-case legal invoice settlement',{'cash:'+case['entity']:-paid,'debt:'+case['entity']+':legal_'+case['id']:paid,'cash:legal_suppliers':paid,'pnl:legal_suppliers':-paid});case['legal_cost_unpaid']=amt(D(case['legal_cost_unpaid'])-paid)
  if w['tick']%24==0:
   self.audit_statements();self.asset_incident_tick();self.media_followups()
  if w['tick']%168==0:self.refresh_networking()
 def insider_approach(self,p):
  c=next((c for c in self.state['insiders'] if c['id']==p['contact']),None)
  if c and c.get('employment')!='EMPLOYED':raise ValueError('Contact has left the issuer and has no current confidential access')
  result=super().insider_approach(p)
  if c:
   c['interactions'].append(dict(tick=self.state['tick'],tip=result['id'],status=result['status'],paid=result['fee']));c['interactions']=c['interactions'][-30:]
   if result['status']=='REFUSED' and c['willingness']>0:c['willingness']=max(0,c['willingness']-2)
  return result
 def enqueue_programme_redemption(self,v,investor,r):
  from .engine import uid
  if D(r['balance'])<=0:return None
  queue=v.setdefault('redemption_queue',[]);row=next((q for q in queue if q['investor']==investor and q['status'] in ('WAITING','PARTIAL')),None)
  if not row:
   v['queue_sequence']=v.get('queue_sequence',0)+1;row=dict(id=uid(),investor=investor,sequence=v['queue_sequence'],requested_tick=self.state['tick'],amount=r['balance'],paid='0.00',remaining=r['balance'],status='WAITING');queue.append(row)
  else:row['amount']=amt(D(row['paid'])+D(r['balance']));row['remaining']=r['balance']
  r['requested']=r['balance'];r['queue_sequence']=row['sequence'];return row
 def programme_redeem(self,p):
  v=next(v for v in self.state.get('investment_programmes',[]) if v['id']==p['programme']);self.authority(v['entity'],'disclose');r=v['investors'][p['investor']]
  if v.get('claims_converted'):return r
  if D(r['balance'])<=0:raise ValueError('Investor has no remaining programme balance')
  self.programme_accrue(v,p['investor'],r);self.enqueue_programme_redemption(v,p['investor'],r);return r
 def record_programme_payment(self,v,investor,r,amount):
  row=next((q for q in v.get('redemption_queue',[]) if q['investor']==investor and q['status'] in ('WAITING','PARTIAL')),None)
  if row:row.update(paid=amt(D(row['paid'])+amount),remaining=r['requested'],status='PAID' if D(r['requested'])==0 else 'PARTIAL')
 def programme_resolution(self,p):
  v=next(v for v in self.state.get('investment_programmes',[]) if v['id']==p['programme']);entity=v['entity'];self.authority(entity,'disclose');action=p['kind']
  if action=='suspend_withdrawals':
   if v.get('claims_converted') or self.state['tick']<v.get('suspension_review_after',0):raise ValueError('Withdrawal suspension cannot be renewed within seven simulation days or during insolvency')
   v['withdrawals_suspended_until']=self.state['tick']+72;v['suspension_review_after']=self.state['tick']+168;v['status']='WITHDRAWALS SUSPENDED';self.executive_notice('withdrawal-suspension:'+v['id']+':'+str(self.state['tick']),'Programme withdrawals suspended for 72 hours','Investor requests and liabilities remain recorded; complaint clocks continue.');return v
  if action=='suspend':
   if v.get('claims_converted'):raise ValueError('Programme is in insolvency recovery')
   v['status']='SUSPENDED';self.audit('programme_suspended',{'programme':v['id']});return v
  if action=='resume':
   self.authority(entity,'govern')
   if v.get('claims_converted') or v['complaint'] or self.is_frozen(entity) or any(D(r['requested'])>0 for r in v['investors'].values()):raise ValueError('Outstanding complaints, withdrawals or insolvency prevent reopening')
   v['status']='OPEN';return v
  if action!='liquidate':raise ValueError('Choose suspend, resume or liquidate')
  if v.get('claims_converted'):return v
  # One administration covers the legal company and ALL its programmes.
  programmes=[q for q in self.state.get('investment_programmes',[]) if q['entity']==entity and not q.get('claims_converted')]
  for programme in programmes:
   for investor,r in programme['investors'].items():
    self.programme_accrue(programme,investor,r);amount=D(r['balance'])
    if amount<=0:continue
    creditor='npc_'+investor;claim=self.create_claim(creditor,entity,amount,'PROGRAMME INVESTOR',programme['id'],0,1);claim['status']='DEFAULT';r['recovery_claim']=claim['id'];r['paid_before_recovery']=r['paid']
    self.post('Programme creditor claim recognised '+programme['id'],{'debt:'+entity+':programme_'+programme['id']:amount,'debt:'+entity+':claim_'+claim['id']:-amount,'npc:'+investor+':programme:'+programme['id']:-amount,'claim:'+creditor+':'+claim['id']:amount})
    r['requested']=r['balance']
   programme.update(claims_converted=True,status='INSOLVENT',insolvency_tick=self.state['tick'])
   for request in programme.get('redemption_queue',[]):
    if request['status'] in ('WAITING','PARTIAL'):request['status']='CREDITOR RECOVERY'
  for e in list(self.staff(entity)):
   self.accrue_employee(e);notice=(D(e['salary'])*D(e['contract']['notice_hours'])/720).quantize(D('.01'))
   self.post('Administration contractual notice pay: '+e['name'],{'expense:payroll:'+entity:notice,'debt:'+entity+':payroll_'+e['id']:-notice});e['unpaid']=amt(D(e['unpaid'])+notice);self.employee_departure(e,'DISMISSED','Company entered administration; earned and notice wages remain creditor obligations')
  for activity in self.state['social_events']:
   if activity['owner']==entity and activity['status']=='SCHEDULED':self.refund_activity(activity,'Company entered administration')
  for office in self.state.get('offices',[]):
   if office['entity']!=entity or office['status']!='ACTIVE':continue
   if office['mode']=='lease':
    rou=self.balance('rou:'+entity+':'+office['id'])
    if rou:self.post('Administration office right-of-use impairment',{'rou:'+entity+':'+office['id']:-rou,'expense:office_rent:'+entity:rou})
    office['status']='TERMINATED';office['unpaid_rent']=amt(-self.balance('debt:'+entity+':lease_'+office['id']))
   else:office['status']='VACATED'
  admin=self.appoint_administrator({'entity':entity,'_programme_authorised':True})
  self.list_administrator_assets(admin)
  self.world_article('programme-insolvency:'+v['id'],self.state['entities'][entity]['name']+' enters programme recovery',[f"The company has appointed an administrator for its investment programmes. Investor balances were converted into creditor claims; no cash was created or debt forgiven.",f"Recorded programme claims at appointment total £{sum((D(r['balance']) for q in programmes for r in q['investors'].values()),D(0)):,.2f}. Distributions depend on cash recovered from actual assets and the existing secured/unsecured priority rules."],'Ledger Watch',[entity])
  self.executive_notice('insolvency:'+entity,'Programme administration started','Investor claims, securities and savings will use the existing recovery engine. Unsold assets and unpaid claims remain on file.');return v
 def list_administrator_assets(self,admin):
  entity=admin['entity']
  for asset in self.state.get('owned_assets',[]):
   if asset['owner']!=entity or asset['status']=='SOLD':continue
   if any(c['asset']==asset['id'] and c['status']=='ACTIVE' for c in self.state.get('property_contracts',[])):continue
   if any(o.get('asset')==asset['id'] and o['status']=='ACTIVE' for o in self.state.get('offices',[])):continue
   if asset['status']=='OWNED':
    asset['status']='LISTED';asset['sale']=dict(listed=self.state['time'],due=self.state['tick']+asset['sale_hours'],quote=amt(D(asset['valuation'])*(1-D(asset['discount']))),status='FINDING BUYER')
   asset['sale']['administrator']=admin['id']
 def appoint_administrator(self,p):
  if p.get('_programme_authorised'):
   # Disclose authority is sufficient for a frozen debtor to seek administration.
   self.authority(p['entity'],'disclose')
   status=self.state['entities'][p['entity']]['status']
   if status=='DISSOLVED':raise ValueError('Dissolved company cannot appoint an administrator')
  return super().appoint_administrator(p)
 def settle_claim_cash(self,c,a,description):
  super().settle_claim_cash(c,a,description)
  if c['kind']=='PROGRAMME INVESTOR':
   v=next((v for v in self.state.get('investment_programmes',[]) if v['id']==c['reference']),None)
   if v:self.sync_programme_recovery(v)
 def sync_programme_recovery(self,v):
  for r in v['investors'].values():
   if not r.get('recovery_claim'):continue
   c=next(c for c in self.state['claims_book'] if c['id']==r['recovery_claim']);r['balance']=c['balance'];r['requested']=c['balance'];r['paid']=amt(D(r['paid_before_recovery'])+sum((D(p['amount']) for p in c['payments']),D(0)))
  admin=next((a for a in self.state['administrations'] if a['entity']==v['entity']),None)
  if all(D(r['balance'])==0 for r in v['investors'].values()):v['status']='RECOVERED'
  elif admin and admin['status']=='UNRESOLVED SHORTFALL':v['status']='UNRESOLVED SHORTFALL'
 def administration_tick(self):
  for admin in self.state.get('administrations',[]):
   if admin['status']!='DISSOLVED' and any(v['entity']==admin['entity'] and v.get('claims_converted') for v in self.state.get('investment_programmes',[])):self.list_administrator_assets(admin)
  super().administration_tick()
  for v in self.state.get('investment_programmes',[]):
   if v.get('claims_converted'):self.sync_programme_recovery(v)
 def validate_programme_case_recovery(self,case):
  programme=next((v for v in self.state.get('investment_programmes',[]) if v['id']==case.get('reference')),None)
  if programme and not programme.get('claims_converted') and any(D(r['balance'])>0 for r in programme['investors'].values()):raise ValueError('Recognise programme creditor claims through Begin creditor recovery before resolving the proceeding')
 def case_claim_in_scope(self,case,claim):
  return claim['id']==case.get('penalty') or (claim['kind']=='RECOVERY' and claim['reference'] in case['reviewed_transactions']) or (claim['kind']=='PROGRAMME INVESTOR' and claim['reference']==case.get('reference'))
 def phase2_statement(self,claim):
  if not self.state.get('living_world_phase2_version') or self.state.get('_legacy_fixture'):return
  claim['phase2_reporting']=True
  if abs(D(claim['gap']))>max(D(100),abs(D(claim['actual']))*D('.02')):
   audit=dict(statement=claim['id'],entity=claim['fund'],actual=claim['actual'],reported=claim['reported'],gap=claim['gap'],opened=self.state['tick'],status='PENDING REVIEW',case=None);self.state['statement_audits'].append(audit)
 def audit_statements(self):
  w=self.state
  for audit in w['statement_audits']:
   if audit['status']!='PENDING REVIEW' or w['tick']-audit['opened']<72:continue
   claim=next(c for c in w['claims'] if c['id']==audit['statement']);reference=claim['id']
   if claim['status']=='CORRECTED':audit['status']='CORRECTED BEFORE REFERRAL';continue
   w['related_transactions'].append(dict(id=reference,source=audit['entity'],destination='investors',kind='financial_misstatement',amount=amt(abs(D(audit['gap']))),fair_value=audit['actual'],classification='MISCONDUCT ALLEGATION',reasons=[f"Published NAV {audit['reported']} differs from contemporaneous ledger NAV {audit['actual']}"],actor='player',status='SETTLED',time=w['time'],tick=w['tick'],disclosed=True,settlements=[],observed=w['time']))
   case=self.complaint({'entity':audit['entity'],'reference':reference,'reason':'Audit found a material published NAV discrepancy'});case['evidence'].append(self.evidence('STATEMENT AUDIT',reference,'Actual '+audit['actual']+'; reported '+audit['reported'],audit['entity'],abs(D(audit['gap']))));case['reviewed_transactions'].append(reference);case['living_world_case']=True;audit.update(status='REFERRED',case=case['id']);claim['evidence']=35;claim['status']='INQUIRY'
   w['investigations'].append(dict(id=case['id'],claim=claim['id'],evidence=claim['evidence'],status=case['stage'],time=w['time'],legal_case=case['id']))
   for n in w['npcs']:
    fund=next(f for f in w['funds'] if f['id']==audit['entity'])
    if n['id'] in fund['investors']:n['trust']=max(0,n['trust']-5)
   self.executive_notice('audit:'+reference,'Audit detected a material statement discrepancy','The preserved contemporaneous figures differ by £'+amt(abs(D(audit['gap'])))+'. Correct the statement and respond to the evidence-backed case.')
 def statement_correct(self,p):
  claim=next(c for c in self.state['claims'] if c['id']==p['statement']);self.authority(claim['fund'],'disclose')
  if claim.get('correction'):return claim['correction']
  current=self.metrics(claim['fund'])['equity'];claim['correction']=dict(tick=self.state['tick'],time=self.state['time'],actual=current,original_reported=claim['reported']);claim['status']='CORRECTED';fund=next(f for f in self.state['funds'] if f['id']==claim['fund']);fund['reported']=current
  for audit in self.state['statement_audits']:
   if audit['statement']==claim['id'] and audit['case']:
    case=next(c for c in self.state['legal_cases'] if c['id']==audit['case']);case['mitigation']=True;case['evidence'].append(self.evidence('CORRECTED DISCLOSURE',claim['id'],'Original statement preserved; current NAV '+current,claim['fund']))
  self.audit('statement_corrected',{'statement':claim['id'],'actual':current});return claim['correction']
 def case_settlement(self,p):
  case=next(c for c in self.state['legal_cases'] if c['id']==p['case']);entity=case['entity'];self.authority(entity,'disclose')
  if case['stage'] not in ('FORMAL INVESTIGATION','ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL'):raise ValueError('No formal proceeding is available for settlement')
  if not case.get('cooperating') and not case.get('mitigation'):raise ValueError('Provide records or correct disclosures before requesting a settlement')
  current_penalty=next((c for c in self.state['claims_book'] if c['id']==case.get('penalty')),None)
  prior=case.get('settlement_offer');refresh=prior and not p.get('accept') and prior['status']=='OFFERED' and (self.state['tick']>prior['expires'] or current_penalty is not None and D(prior['amount'])!=D(current_penalty['balance']))
  if not prior or refresh:
   exposure=sum((D(r['amount']) for r in self.state['related_transactions'] if r['id'] in case['reviewed_transactions']),D(0));case['settlement_offer']=dict(amount=current_penalty['balance'] if current_penalty else amt(min(D(10000000),exposure*D('.05'))),expires=self.state['tick']+168,status='OFFERED')
  offer=case['settlement_offer']
  if p.get('accept'):
   self.validate_programme_case_recovery(case)
   if offer['status']!='OFFERED' or self.state['tick']>offer['expires']:raise ValueError('Settlement offer has expired or was already accepted')
   penalty=next((c for c in self.state['claims_book'] if c['id']==case.get('penalty')),None);amount=D(penalty['balance']) if penalty else D(offer['amount'])
   if amount!=D(offer['amount']):raise ValueError('Penalty assessment changed; request a refreshed offer before accepting')
   if amount>self.available_cash(entity):raise ValueError('Settlement requires actual debtor cash')
   if not penalty:
    penalty=self.create_claim('regulator',entity,amount,'ADMINISTRATIVE PENALTY',case['id']);case['penalty']=penalty['id'];self.post('Administrative settlement assessed',{'expense:penalty:'+entity:amount,'debt:'+entity+':claim_'+penalty['id']:-amount,'claim:regulator:'+penalty['id']:amount,'pnl:regulator':-amount})
   if amount:self.settle_claim_cash(penalty,amount,'Administrative settlement payment')
   offer['status']='ACCEPTED';case['mitigation']=True
   outstanding=sum((D(c['balance']) for c in self.state['claims_book'] if self.case_claim_in_scope(case,c)),D(0))
   case['stage']='CIVIL RECOVERY' if outstanding else 'CLOSED';case['outcome']='Administrative settlement; no criminal adjudication. Investor recovery obligations survive.'
   if not outstanding and not any(c['entity']==entity and c['id']!=case['id'] and c['stage'] in ('ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL') for c in self.state['legal_cases']):self.state['frozen_funds']=[a for a in self.state.get('frozen_funds',[]) if a!=entity]
   case['evidence'].append(self.evidence('SETTLEMENT',case['id'],'Accepted settlement paid from real cash',entity,amount))
  return offer
 def asset_profile(self,a):
  category=a['category'];price=D(a['purchase_price']);spec={'Yachts':('Marina',16,5,['party','investor_reception','holiday']),'Aircraft':('Business aviation terminal',8,2,['business_trip']),'Residential property':('London' if a['catalogue'] in ('apartment','penthouse') else 'English countryside',24 if price>=1000000 else 8,3 if price>=1000000 else 1,['private_meeting','investor_reception','party','charity_gala']),'Commercial property':('Regional business district',24,2,['private_meeting','investor_reception','charity_gala']),'Offices':(a.get('location','Business district'),min(100,a.get('capacity',25)),2,['private_meeting','investor_reception']),'Vehicles':('Motoring club',4,1,['showcase','private_meeting'])}.get(category,('Private collection room',2,0,['showcase','private_meeting']))
  return dict(location=spec[0],capacity=spec[1],staff_required=spec[2],activities=spec[3],prestige=min(100,int(price/100000)),visibility=min(100,20+int(price/1000000)),staffing=a.get('service_staffing','FULL'),security=a.get('service_security','STANDARD'))
 def asset_services(self,p):
  a=next(a for a in self.state['owned_assets'] if a['id']==p['asset'] and a['status']=='OWNED');self.lifestyle_authority(a['owner']);staffing=p.get('staffing','FULL');security=p.get('security','STANDARD')
  if staffing not in ('FULL','REDUCED') or security not in ('STANDARD','ENHANCED'):raise ValueError('Choose full/reduced staffing and standard/enhanced security')
  a.setdefault('base_monthly_cost',a['monthly_cost']);a['service_staffing']=staffing;a['service_security']=security;a['monthly_cost']=amt(D(a['base_monthly_cost'])*(D('.8') if staffing=='REDUCED' else D(1))+(D(a['base_monthly_cost'])*D('.1') if security=='ENHANCED' else D(0)))
  self.audit('asset_services',{'asset':a['id'],'staffing':staffing,'security':security,'monthly_cost':a['monthly_cost']});return self.asset_profile(a)
 def activity_quote(self,a,guests,purpose):
  base=max(D(250),D(a['monthly_cost'])*D('.1'))+D(250)*len(guests)
  if purpose=='charity_gala':base*=2
  if purpose=='business_trip':base=max(base,D(5000))
  return base.quantize(D('.01'))
 def lifestyle_host(self,p):
  event=self.lifestyle_schedule({**p,'delay_hours':0,'publicity':p.get('publicity','PUBLIC')});self.finish_activity(event);return event
 def lifestyle_schedule(self,p):
  from .engine import uid
  w=self.state;a=next((a for a in w['owned_assets'] if a['id']==p['asset'] and a['status']=='OWNED'),None)
  if not a:raise ValueError('Owned asset required')
  self.lifestyle_authority(a['owner']);profile=self.asset_profile(a);purpose=p.get('purpose',profile['activities'][0]);delay=int(p.get('delay_hours',24));guests=list(dict.fromkeys(p.get('guests',[])));publicity=p.get('publicity','PRIVATE')
  if purpose not in profile['activities'] or not 0<=delay<=720 or publicity not in ('PRIVATE','PUBLIC'):raise ValueError('Unsupported asset activity, publicity or scheduling delay')
  if not 1<=len(guests)<=profile['capacity']:raise ValueError('Attendee count exceeds asset capacity')
  if D(a['unpaid'])>0 or w['tick']<a.get('hosting_next',0) or any(c['asset']==a['id'] and c['status']=='ACTIVE' for c in w.get('property_contracts',[])):raise ValueError('Asset has arrears, a hosting cooldown or an active tenancy')
  if any(e['asset']==a['id'] and e['status']=='SCHEDULED' for e in w['social_events']):raise ValueError('Asset already has a scheduled activity')
  if any(i['asset']==a['id'] and i['status']=='OPEN' for i in w['asset_incidents']):raise ValueError('Resolve the asset incident before arranging an activity')
  people={n['id']:n for n in w['npcs']+w['social_contacts']+[e for e in w['employees'] if e['status']=='EMPLOYED' and e['entity'] in self.controlled_accounts()]}
  if any(g not in people for g in guests):raise ValueError('Attendees must be existing social contacts, investors or controlled employees')
  opportunity=None
  if purpose=='business_trip':
   opportunity=next((o for o in w['networking_opportunities'] if o['id']==p.get('opportunity') and o['status']=='OPEN'),None)
   if not opportunity or opportunity['due']<w['tick']+delay:raise ValueError('Choose an actual open networking event before its deadline')
  cost=D(str(p.get('budget',self.activity_quote(a,guests,purpose))));minimum=self.activity_quote(a,guests,purpose)
  if not cost.is_finite() or cost<minimum or cost>minimum*10 or cost!=cost.quantize(D('.01')):raise ValueError('Budget must be between the quoted minimum and ten times that amount, in whole pennies')
  if cost>self.available_cash(a['owner']) or cost>D(self.authority(a['owner'],'payment')['payment_limit']):raise ValueError('Activity exceeds cash or payment authority')
  event=dict(id=uid(),asset=a['id'],owner=a['owner'],guests=guests,purpose=purpose,location=opportunity['location'] if opportunity else profile['location'],cost=amt(cost),minimum=amt(minimum),publicity=publicity,status='SCHEDULED',time=w['time'],tick=w['tick'],due=w['tick']+delay,outcomes=[],opportunity=opportunity['id'] if opportunity else None)
  self.post('Activity budget reserved '+event['id'],{'cash:'+a['owner']:-cost,'escrow:'+a['owner']+':'+event['id']:cost,'cash:activity_escrow':cost,'debt:activity_escrow:'+event['id']:-cost});w['social_events'].append(event);self.executive_notice('activity-scheduled:'+event['id'],'Lifestyle activity scheduled',purpose+' at '+event['location']+'; £'+amt(cost)+' reserved until hour '+str(event['due']));return event
 def lifestyle_cancel(self,p):
  event=next(e for e in self.state['social_events'] if e['id']==p['event']);self.authority(event['owner'],'payment')
  if event['status']!='SCHEDULED':raise ValueError('Only scheduled activities can be cancelled')
  self.refund_activity(event,'Cancelled by host');return event
 def refund_activity(self,event,reason):
  cost=D(event['cost']);self.post('Activity budget refunded '+event['id'],{'escrow:'+event['owner']+':'+event['id']:-cost,'cash:'+event['owner']:cost,'cash:activity_escrow':-cost,'debt:activity_escrow:'+event['id']:cost});event.update(status='CANCELLED',reason=reason)
 def finish_activity(self,event):
  if event['status']!='SCHEDULED':return
  w=self.state;a=next(a for a in w['owned_assets'] if a['id']==event['asset']);owner=event['owner']
  if a['status']!='OWNED' or self.is_frozen(owner) or D(a['unpaid'])>0 or any(i['asset']==a['id'] and i['status']=='OPEN' for i in w['asset_incidents']):self.refund_activity(event,'Asset unavailable at scheduled time');return
  people={n['id']:n for n in w['npcs']+w['social_contacts']+[e for e in w['employees'] if e['status']=='EMPLOYED']};cost=D(event['cost']);donation=(cost*D('.6')).quantize(D('.01')) if event['purpose']=='charity_gala' else D(0);supplier=cost-donation
  lines={'escrow:'+owner+':'+event['id']:-cost,'cash:activity_escrow':-cost,'debt:activity_escrow:'+event['id']:cost,'expense:hosting:'+owner:cost,'cash:lifestyle_suppliers':supplier,'pnl:lifestyle_suppliers':-supplier}
  if donation:lines.update({'cash:charity_sector':donation,'pnl:charity_sector':-donation})
  self.post('Activity completed '+event['id'],lines);event.update(status='COMPLETED',completed_tick=w['tick'],completed_time=w['time'],donation=amt(donation));a['hosting_next']=w['tick']+168
  quality=min(20,int(cost/D(event['minimum'])*5))+(0 if a.get('service_staffing','FULL')=='FULL' else -10);rep=w['personal_reputation']
  for guest in event['guests']:
   if guest not in people:event['outcomes'].append(guest+' could not attend');continue
   person=people[guest];relation=w['social_relationships'].setdefault(guest,dict(meetings=0,rapport=0));relation.setdefault('memory',[]);relation['meetings']+=1
   suitability=8 if person.get('preference')==event['purpose'] or guest.startswith('lp') and event['purpose'] in ('investor_reception','private_meeting','showcase') else 0
   austerity=12 if person.get('risk',1)<.4 and event['purpose']=='party' else 0
   distress='entity' in person and (D(person.get('unpaid','0'))>D(person['salary']) or self.available_cash(person['entity'])<D(person['salary'])*2)
   prestige_fit=self.asset_profile(a)['prestige']//20 if person.get('risk',0)>.6 or person.get('role') in ('Executive','Business partner') else 0
   score=quality+suitability+prestige_fit+min(5,rep['credibility']//20)-rep['controversy']//5-austerity-(20 if distress else 0)-min(10,relation['meetings']//3)
   gain=max(-5,min(4,score//5));relation['rapport']=max(-40,min(60,relation['rapport']+gain));relation['memory'].append(dict(event=event['id'],tick=w['tick'],purpose=event['purpose'],change=gain));relation['memory']=relation['memory'][-20:]
   if 'trust' in person:person['trust']=max(0,min(100,person['trust']+max(-3,min(2,gain))))
   if 'morale' in person:person['morale']=max(0,min(100,person['morale']+gain*2))
   event['outcomes'].append(person['name']+': rapport '+f'{gain:+d}'+(' (payroll distress)' if distress else ''))
   if guest in {n['id'] for n in w['npcs']} and gain>0 and relation['rapport']>=8:
    event.setdefault('business_requests',[]).append(dict(investor=guest,kind='INVESTOR MEETING',available_wealth=person['wealth']));self.executive_notice('meeting:'+guest+':'+str(w['tick']//720),person['name']+' requests a business meeting','A positive reception led to a meeting request. Any allocation still uses actual NAV, suitability and finite investor cash.')
  if event['opportunity']:
   opportunity=next(o for o in w['networking_opportunities'] if o['id']==event['opportunity']);opportunity['status']='ATTENDED';opportunity['activity']=event['id']
  if event['publicity']=='PUBLIC':
   rep['prominence']=min(100,rep['prominence']+max(1,self.asset_profile(a)['visibility']//10));rep['prestige']=min(100,rep['prestige']+max(1,self.asset_profile(a)['prestige']//25))
   self.world_article('social:'+event['id'],a['name']+' hosts '+event['purpose'].replace('_',' '),[f"The owner hosted {len(event['guests'])} invited associates at {event['location']}. The recorded activity budget was £{cost:,.2f}.",f"The asset carries operating commitments of £{D(a['monthly_cost']):,.2f} per month. "+(f"The gala transferred £{donation:,.2f} to the simulated charity sector." if donation else 'Attendance does not constitute an investment commitment.')],'City After Hours',[owner,a['id']])
  self.audit('lifestyle_activity',event.copy())
 def refresh_networking(self):
  from .engine import uid
  w=self.state
  eligible=w['personal_reputation']['prominence']>=5 or any(a['status']!='SOLD' and D(a['valuation'])>=1000000 for a in w['owned_assets']) or any(r['rapport']>=8 for r in w['social_relationships'].values())
  for o in w['networking_opportunities']:
   if o['status']=='OPEN' and o['due']<w['tick']:o['status']='EXPIRED'
  if not eligible or len([o for o in w['networking_opportunities'] if o['status']=='OPEN'])>=3:return
  contact=w['social_contacts'][(w['tick']//168)%len(w['social_contacts'])];o=dict(id=uid(),host=contact['id'],name=contact['name']+' business forum',location=contact['location'],due=w['tick']+120,status='OPEN',public=True)
  w['networking_opportunities'].append(o);self.executive_notice('networking:'+o['id'],'Business forum invitation',o['name']+' in '+o['location']+'. An aircraft business trip can attend before hour '+str(o['due'])+'.')
 def asset_incident_tick(self):
  from .engine import uid
  w=self.state
  for a in w['owned_assets']:
   if a['status']=='SOLD' or w['tick']<a.get('incident_review',a['acquired_tick']+1440):continue
   a['incident_review']=w['tick']+720
   if any(i['asset']==a['id'] and i['status']=='OPEN' for i in w['asset_incidents']):continue
   rng=random.Random(a['id']+str(w['tick']//720));chance=.35 if a.get('service_staffing')=='REDUCED' else .08
   security_incident=a['category'] in ('Residential property','Vehicles','Art and collectibles','Collectibles','Watches and jewellery')
   if security_incident and a.get('service_security')=='ENHANCED':chance*=.6
   if rng.random()>=chance:continue
   cost=max(D(100),D(a['monthly_cost'])*D('.5')).quantize(D('.01'));row=dict(id=uid(),asset=a['id'],owner=a['owner'],cost=amt(cost),status='OPEN',tick=w['tick'],kind='Security and service inspection required' if security_incident else 'Maintenance inspection required')
   self.post('Asset maintenance incident '+a['name'],{'expense:lifestyle:'+a['owner']:cost,'debt:'+a['owner']+':lifestyle_'+a['id']:-cost});a['unpaid']=amt(D(a['unpaid'])+cost);w['asset_incidents'].append(row);self.executive_notice('incident:'+row['id'],'Asset maintenance needs a decision',a['name']+' requires an inspection; the £'+amt(cost)+' invoice is recorded. Settle operating arrears before signing off repairs.')
 def asset_repair(self,p):
  incident=next(i for i in self.state['asset_incidents'] if i['id']==p['incident']);a=next(a for a in self.state['owned_assets'] if a['id']==incident['asset']);self.lifestyle_authority(a['owner'])
  if incident['status']!='OPEN':return incident
  if D(a['unpaid'])>0:raise ValueError('Operating and maintenance invoices must settle before repair sign-off; advance time with sufficient cash')
  incident.update(status='REPAIRED',resolved_tick=self.state['tick']);return incident
 def world_article(self,key,title,paragraphs,publication,entities):
  if key in self.state['world_coverage']:return
  super().world_article(key,title,paragraphs,publication,entities)
  if self.state.get('living_world_phase2_version'):self.link_story(self.state['news'][0],('case:'+key.split(':')[1]) if key.startswith(('case:','case-analysis:')) else ('entity:'+str(entities[0]) if entities else key))
 def link_story(self,article,thread):
  if not self.state.get('living_world_phase2_version'):return
  story=self.state['story_threads'].setdefault(thread,dict(id=thread,articles=[],entities=article.get('entities',[])))
  if any(a['id']==article['id'] for a in story['articles']):return
  article['thread']=thread;article['related_articles']=[a['id'] for a in story['articles'][-3:]];story['articles'].append({k:copy.deepcopy(article[k]) for k in ('id','time','title','publication') if k in article});story['articles']=story['articles'][-40:]
 def media_followups(self):
  w=self.state
  for case in w['legal_cases']:
   for linked in w['investigations']:
    if linked.get('legal_case')==case['id']:linked['status']=case['stage'];linked['evidence']=max(linked['evidence'],case['score'])
   formal=case['stage'] in ('FORMAL INVESTIGATION','ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL')
   prior_public=any(k.startswith('case:'+case['id']) for k in w['world_coverage'])
   if formal and w['tick']-case.get('stage_tick',case['opened'])>=24:
    self.world_article('case-analysis:'+case['id'],"Document trail in "+w['entities'][case['entity']]['name']+' inquiry',[f"The public proceeding is at {case['stage'].lower()}. Its recorded concern is: {case['concern']}.",f"The authority has preserved {len(case['evidence'])} evidence references. Legal invoices assessed so far total £{D(case.get('legal_cost_assessed','0')):,.2f}. Evidence of an accounting discrepancy is distinct from proof of criminal intent; no conviction is inferred."],'Ledger Watch',[case['entity']])
   if case['stage']=='CLOSED' and prior_public:
    self.world_article('case:'+case['id']+':closed',w['entities'][case['entity']]['name']+' proceeding closes',[case.get('outcome','The authority closed the recorded proceeding.'),f"Case {case['id']} remains on the historical record. Actual payments, penalties and unpaid creditor claims remain in the authoritative books."],'The Financial Record',[case['entity']])
  published=[e for e in w['events'] if e['published']]
  if w['tick']%168==0 and published:
   event=published[-1];ins=self.instrument(event['symbol']);self.world_article('industry:'+event['id'],ins.get('sector','Industry')+': '+event['symbol']+' disclosure in context',[f"The published {event['kind']} update revised model expectations by {event['severity']*100:+.1f}%. The disclosure occurred at {event['publication_time']}.",f"The latest simulated execution mark is {ins['currency']} {ins['price']}. This industry brief uses public event data; it conveys no pending corporate information or recommendation to buy."],'Sector Brief',[event['symbol']])
 def corporate_update(self,p):
  entity=p['entity'];self.authority(entity,'disclose');w=self.state;week=w['tick']//168;key='corporate-update:'+entity+':'+str(week)
  if key in w['world_coverage']:raise ValueError('A corporate update has already been published this simulation week')
  metrics=self.metrics(entity);self.world_article(key,w['entities'][entity]['name']+' publishes an operating update',[f"The institution voluntarily disclosed net assets of £{D(metrics['equity']):,.2f}, realised trading results of £{D(metrics['realised']):,.2f} and unrealised marks of £{D(metrics['unrealised']):,.2f}.",f"Recorded financing and other liabilities total £{D(metrics['debt']):,.2f}; available cash is £{D(metrics['available_cash']):,.2f}. These figures are taken from the local ledger at {w['time']} and are not a promise of future returns."],'Boardroom Review',[entity]);return metrics
