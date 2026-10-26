"""Institution-scoped employment, earned payroll and bounded autonomous work.
State is additive within the existing transactional worlds document; no historical
journal rows or legacy liabilities are rewritten.
"""
import copy, random
from decimal import Decimal as D
from .integrity import amt

ROLES = {
 'analyst': ('Investment analyst','Research','CFA; financial modelling','Equity research'),
 'portfolio_manager': ('Portfolio manager','Investments','CFA; portfolio construction','Asset allocation'),
 'trader': ('Trader','Trading','CISI; execution and market structure','Trade execution'),
 'risk': ('Risk manager','Risk','FRM; quantitative risk','Exposure and liquidity'),
 'compliance': ('Compliance officer','Compliance','ICA; financial regulation','Transaction review'),
 'relations': ('Investor relations','Investor relations','CISI; institutional client coverage','Investor reporting'),
 'operations': ('Operations and settlement','Operations','CISI investment operations','Settlement and reconciliation'),
 'accountant': ('Accountant','Finance','ACCA; financial reporting','Ledger reconciliation'),
 'executive': ('Executive and director','Executive','MBA; corporate governance','Management oversight'),
 'hr': ('Human resources officer','Human resources','CIPD; workforce planning','Staff retention'),
 'legal': ('Legal counsel','Legal','Solicitor; corporate law','Regulatory procedure'),
}
NAMES = ['Alex Morgan','Priya Shah','James Okafor','Sofia Bennett','Daniel Chen','Amelia Clarke','Noah Patel','Grace Williams','Oliver Hughes']

class EmployeeMixin:
 def install_employees(self):
  w=self.state
  if w.get('employee_version',0)>=1:return
  for key in ('employees','recruitment','employment_offers','employee_activity','employee_tasks','employee_reports'):w.setdefault(key,[])
  w['employee_version']=1
  # Preserve paid headcount as named employees at precisely the old monthly rate.
  # Existing aggregate debts remain in the ledger; only future payroll moves here.
  for entity,plan in w.get('operating_plans',{}).items():
   if entity=='personal':continue  # Preserve legacy personal supplier budgets, not institutional employment.
   existing=len(self.staff(entity))
   for i in range(existing,int(plan.get('staff',0))):
    employee=self.new_employee(entity,dict(name=NAMES[i%len(NAMES)]+(' '+str(i//len(NAMES)+1) if i>=len(NAMES) else ''),role='operations',experience=5,competence=65,reliability=85,specialisation='Legacy operating team',qualifications='Existing staff; qualifications not verified',background='Retained from existing funded operating plan'),D(4000))
    employee['contract']['origin']='Preserved legacy headcount'
   # Preserve the historical operating plan verbatim; subsequent player changes
   # recalculate its derived capacity/payroll through sync_staff_plan.
  self.audit('employee_system_installed',{'version':1,'legacy_payroll_debts_preserved':True,'employees':len(w['employees'])})
 def employee_entity(self,entity):
  e=self.authority(entity,'govern')
  if entity=='personal':raise ValueError('Employees must belong to an institution or company')
  if self.is_frozen(entity):raise ValueError('Restricted institution cannot change employment or delegate work')
  return e
 def staff(self,entity):return [e for e in self.state.get('employees',[]) if e['entity']==entity and e['status']=='EMPLOYED']
 def aggregate_monthly_payroll(self,entity):return D(self.state.get('private_businesses',{}).get(entity,{}).get('annual_payroll','0'))/12
 def employee_log(self,e,kind,detail,reference=None):
  from .engine import uid
  row=dict(id=uid(),employee=e['id'],entity=e['entity'],time=self.state['time'],tick=self.state['tick'],kind=kind,detail=detail,reference=reference)
  self.state['employee_activity'].append(row);e['performance_history'].append(row['id']);self.audit('employee_'+kind,row.copy());return row
 def new_employee(self,entity,candidate,salary):
  from .engine import uid
  w=self.state;role=candidate['role'];id='staff_'+uid()
  e={k:copy.deepcopy(candidate[k]) for k in ['name','role','experience','competence','reliability','specialisation','qualifications','background']}
  e.update(id=id,entity=entity,department=ROLES[role][1],status='EMPLOYED',salary=amt(salary),hired_tick=w['tick'],hired_time=w['time'],accrual_start=w['tick'],segment_accrued='0.00',payroll_next=w['tick']+720,unpaid='0.00',paid='0.00',workload=0,availability='Available',next_work=w['tick']+24,performance_history=[],manager=None,delegation={'trade':False,'per_order':'0.00','daily':'0.00'},contract={'notice_hours':168,'hours_per_day':8,'currency':'GBP','monthly_salary':amt(salary),'origin':'Accepted recruitment offer'},grade=1)
  w['employees'].append(e);self.employee_log(e,'hired','Employment contract started');return e
 def sync_staff_plan(self,entity):
  plan=self.state.get('operating_plans',{}).get(entity)
  if not plan:
   plan=dict(entity=entity,research='0.00',technology='0.00',salary='0.00',fee_rate='.0005',enabled=True)
   self.state['operating_plans'][entity]=plan
  people=self.staff(entity);plan['staff']=len(people);plan['monthly_payroll']=amt(sum((D(e['salary']) for e in people),D(0)));plan['order_capacity']=50+len(people)*10+int(D(plan['technology'])/1000)
 def recruit(self,p):
  from .engine import uid
  entity=p['entity'];self.employee_entity(entity);role=p['role']
  if role not in ROLES:raise ValueError('Unknown employment role')
  if sum(c['entity']==entity and c['role']==role and c['status']=='AVAILABLE' for c in self.state['recruitment'])>=3:raise ValueError('Review existing candidates for this role first')
  rng=random.Random(str(self.state['seed'])+entity+role+str(len(self.state['recruitment'])))
  candidates=[]
  quality=max([o['prestige'] for o in self.state.get('offices',[]) if o['entity']==entity and o['status']=='ACTIVE'] or [0])
  for i in range(3):
   skill=rng.randint(45,92);c=dict(id=uid(),entity=entity,name=NAMES[rng.randrange(len(NAMES))]+' '+str(len(self.state['recruitment'])+1),role=role,experience=rng.randint(2,20),competence=skill,reliability=rng.randint(65,98),specialisation=ROLES[role][3],qualifications=ROLES[role][2],background='Previously worked in '+ROLES[role][1].lower()+' at an independent financial firm',minimum_salary=amt(max(D(4000),D(4000)+max(0,skill-65)*100-max(0,quality-60)*10)),status='AVAILABLE',time=self.state['time'])
   self.state['recruitment'].append(c);candidates.append(c)
  self.audit('recruitment_search',{'entity':entity,'role':role,'candidates':[c['id'] for c in candidates]});return candidates
 def employment_offer(self,p):
  from .engine import uid
  c=next((c for c in self.state['recruitment'] if c['id']==p['candidate']),None)
  if not c:raise ValueError('Candidate not found')
  self.employee_entity(c['entity']);salary=D(str(p['salary']))
  if c['status']!='AVAILABLE':raise ValueError('Candidate is no longer available')
  if not salary.is_finite() or not 4000<=salary<=1000000:raise ValueError('Monthly salary must be between £4,000 and £1,000,000')
  authority=self.authority(c['entity'],'govern')
  if self.aggregate_monthly_payroll(c['entity'])+salary+sum((D(e['salary']) for e in self.staff(c['entity'])),D(0))>D(authority['payment_limit']):raise ValueError('Payroll commitment exceeds institution authority')
  accepted=salary>=D(c['minimum_salary']);offer=dict(id=uid(),candidate=c['id'],entity=c['entity'],salary=amt(salary),status='ACCEPTED' if accepted else 'DECLINED',reason='Salary meets candidate terms' if accepted else 'Salary below candidate minimum',time=self.state['time'],expires=self.state['tick']+168)
  self.state['employment_offers'].append(offer);self.audit('employment_offer',offer.copy());return offer
 def employee_hire(self,p):
  offer=next((o for o in self.state['employment_offers'] if o['id']==p['offer']),None)
  if not offer:raise ValueError('Offer not found')
  self.employee_entity(offer['entity']);c=next(c for c in self.state['recruitment'] if c['id']==offer['candidate'])
  if offer['status']!='ACCEPTED' or c['status']!='AVAILABLE' or offer['expires']<self.state['tick']:raise ValueError('Offer is unavailable or expired')
  if self.available_cash(offer['entity'])<D(offer['salary']):raise ValueError('Hold at least one month of unrestricted salary funding before hiring')
  if self.aggregate_monthly_payroll(offer['entity'])+sum((D(e['salary']) for e in self.staff(offer['entity'])),D(offer['salary']))>D(self.authority(offer['entity'],'govern')['payment_limit']):raise ValueError('Payroll commitment exceeds institution authority')
  if len(self.staff(offer['entity']))>=self.office_capacity(offer['entity']):raise ValueError('Office capacity reached; lease or purchase more premises before hiring')
  e=self.new_employee(offer['entity'],c,D(offer['salary']));c['status']='HIRED';offer['status']='HIRED';self.sync_staff_plan(e['entity']);return e
 def accrue_employee(self,e):
  elapsed=self.state['tick']-e['accrual_start'];target=(D(e['salary'])*D(elapsed)/720).quantize(D('.01'));amount=target-D(e['segment_accrued'])
  if amount>0:
   self.post('Earned employee payroll: '+e['name'],{'expense:payroll:'+e['entity']:amount,'debt:'+e['entity']+':payroll_'+e['id']:-amount});e['segment_accrued']=amt(target);e['unpaid']=amt(D(e['unpaid'])+amount)
 def pay_employee(self,e):
  amount=min(D(e['unpaid']),max(D(0),self.available_cash(e['entity'])))
  if amount and not self.is_frozen(e['entity']):
   self.post('Employee salary settlement: '+e['name'],{'cash:'+e['entity']:-amount,'debt:'+e['entity']+':payroll_'+e['id']:amount,'cash:'+e['id']:amount,'pnl:'+e['id']:-amount});e['unpaid']=amt(D(e['unpaid'])-amount);e['paid']=amt(D(e['paid'])+amount);self.employee_log(e,'payroll','Paid £'+amt(amount))
  return {'paid':e['paid'],'unpaid':e['unpaid']}
 def employee_change(self,p):
  e=next((e for e in self.state['employees'] if e['id']==p['employee']),None)
  if not e:raise ValueError('Employee not found')
  self.employee_entity(e['entity']);kind=p['kind']
  if kind=='pay':
   if e['status']=='EMPLOYED':self.accrue_employee(e)
   return self.pay_employee(e)
  if e['status']!='EMPLOYED':raise ValueError('Employee has left the institution')
  if kind in ('salary','promote'):
   salary=D(str(p.get('salary',e['salary'])))
   if not salary.is_finite() or not 4000<=salary<=1000000:raise ValueError('Invalid monthly salary')
   if self.aggregate_monthly_payroll(e['entity'])+salary+sum((D(x['salary']) for x in self.staff(e['entity']) if x['id']!=e['id']),D(0))>D(self.authority(e['entity'],'govern')['payment_limit']):raise ValueError('Payroll commitment exceeds institution authority')
   self.accrue_employee(e);e['accrual_start']=self.state['tick'];e['segment_accrued']='0.00';e['salary']=amt(salary);e['contract']['monthly_salary']=amt(salary)
   if kind=='promote':e['grade']+=1
  elif kind=='delegate':
   per=D(str(p.get('per_order',0)));daily=D(str(p.get('daily',0)));enabled=bool(p.get('trade'))
   if e['role'] not in ('trader','portfolio_manager') or not per.is_finite() or not daily.is_finite() or not 0<=per<=daily<=self.staff_trading_limit(e['entity']):raise ValueError('Invalid trading delegation or role')
   e['delegation']={'trade':enabled,'per_order':amt(per),'daily':amt(daily)}
   self.state['entities'][e['entity']]['signatories'][e['id']]=['trade'] if enabled else []
  elif kind=='manager':
   manager=next((x for x in self.staff(e['entity']) if x['id']==p.get('manager')),None)
   if not p.get('manager'):
    e['manager']=None;self.employee_log(e,'manager','Reports directly to player');return e
   if not manager or manager['id']==e['id']:raise ValueError('Manager must be a different employee in this institution')
   seen={e['id']};current=manager
   while current:
    if current['id'] in seen:raise ValueError('Circular reporting relationships are prohibited')
    seen.add(current['id']);current=next((x for x in self.staff(e['entity']) if x['id']==current.get('manager')),None)
   e['manager']=manager['id']
  elif kind in ('dismiss','resign'):
   self.accrue_employee(e)
   if kind=='dismiss':
    notice=(D(e['salary'])*D(e['contract']['notice_hours'])/720).quantize(D('.01'));self.post('Contractual notice pay: '+e['name'],{'expense:payroll:'+e['entity']:notice,'debt:'+e['entity']+':payroll_'+e['id']:-notice});e['unpaid']=amt(D(e['unpaid'])+notice)
   self.employee_departure(e,'DISMISSED' if kind=='dismiss' else 'RESIGNED','Player recorded '+kind);self.pay_employee(e)
  else:raise ValueError('Unknown employment instruction')
  self.sync_staff_plan(e['entity']);self.employee_log(e,kind,'Employment record updated');return e
 def employee_departure(self,e,status,reason):
  e['status']=status;e['left_time']=self.state['time'];e['availability']='Left institution';e['delegation']['trade']=False;self.state['entities'][e['entity']]['signatories'].pop(e['id'],None)
  for order in self.state['orders']:
   if order.get('employee')==e['id'] and order['status'] in ('OPEN','PARTIAL'):order['status']='CANCELLED';order['reason']='Employee employment ended'
  for t in self.state['employee_tasks']:
   if t['employee']==e['id'] and t['status'] in ('QUEUED','AWAITING APPROVAL'):t['status']='CANCELLED';t['result']='Employee left; no order executed'
  for x in self.staff(e['entity']):
   if x['manager']==e['id']:x['manager']=None
  self.sync_staff_plan(e['entity']);self.employee_log(e,'departure',reason)
 def employee_task(self,p):
  from .engine import uid
  e=next((e for e in self.state['employees'] if e['id']==p['employee']),None)
  if not e or e['status']!='EMPLOYED':raise ValueError('Active employee required')
  self.employee_entity(e['entity'])
  if sum(t['employee']==e['id'] and t['status'] in ('QUEUED','AWAITING APPROVAL') for t in self.state['employee_tasks'])>=3:raise ValueError('Employee workload is full')
  kind=p['kind'];instruction={}
  if kind=='order':
   if e['role'] not in ('trader','portfolio_manager'):raise ValueError('Only traders and portfolio managers receive order instructions')
   symbol=str(p['symbol']);self.instrument(symbol);qty=int(p['qty']);side=p.get('side','buy')
   if not 1<=qty<=1000000000 or side not in ('buy','sell'):raise ValueError('Invalid order quantity or side')
   instruction={'symbol':symbol,'qty':qty,'side':side,'type':'market','account':e['entity'],'margin':False}
  elif kind!='review':raise ValueError('Unknown employee task')
  task=dict(id=uid(),employee=e['id'],entity=e['entity'],kind=kind,instruction=instruction,status='QUEUED',due=self.state['tick']+1,time=self.state['time'],approved=False,result=None)
  self.state['employee_tasks'].append(task);self.employee_log(e,'assigned',kind,task['id']);return task
 def employee_approve(self,p):
  task=next((t for t in self.state['employee_tasks'] if t['id']==p['task']),None)
  if not task or task['status']!='AWAITING APPROVAL':raise ValueError('Task is not awaiting approval')
  self.employee_entity(task['entity']);task['approved']=True;task['status']='QUEUED';task['due']=self.state['tick']+1;self.audit('employee_order_approved',{'entity':task['entity'],'task':task['id'],'instruction':task['instruction']});return task
 def employee_review(self,e):
  from .engine import uid
  m=self.metrics(e['entity']);kind=e['role'];evidence={};summary='';rng=random.Random(e['id']+str(self.state['tick']));reliable=rng.randrange(100)<e['reliability'];quality=rng.randrange(100)<e['competence'];uncertainty='Employee assessment; may omit risks and must be reviewed.'
  if kind in ('risk','portfolio_manager'):
   evidence={k:m[k] for k in ['gross','equity','available_cash','leverage','concentration','var95','realised','unrealised','profit','fees']};summary='Exposure and liquidity review. '+('Attention: low cash or elevated leverage.' if D(m['available_cash'])<D(10000) or m['leverage']>1 else 'No threshold breach identified.')
  elif kind=='compliance':
   rows=[t for t in self.state.get('related_transactions',[]) if t['source']==e['entity']];flagged=[t['id'] for t in rows if t['classification']!='LEGITIMATE'];evidence={'transactions_reviewed':[t['id'] for t in rows],'flagged':flagged if quality else flagged[:1],'cases':[c['id'] for c in self.state.get('legal_cases',[]) if c['entity']==e['entity'] and c['stage']!='CLOSED']};summary='Internal review of recorded transactions; flags are allegations requiring investigation.'
  elif kind in ('operations','accountant'):
   self.reconcile();evidence={'reconciled':True,'cash':m['available_cash'],'unusual_expenses':{k:v for k,v in self.state['balances'].items() if k.startswith('expense:') and k.endswith(':'+e['entity']) and any(part in k for part in ('intelligence','hosting','programme','penalty','legal'))},'liabilities':{k:v for k,v in self.state['balances'].items() if k.startswith('debt:'+e['entity']+':') and D(v)!=0},'remaining_withdrawals':[r['id'] for r in self.state.get('redemptions',[]) if r['fund']==e['entity'] and D(r['remaining'])>0]};summary='Ledger reconciled. Outstanding claims remain payable; no liabilities were waived.'
  elif kind=='hr':
   people=self.staff(e['entity']);evidence={'headcount':len(people),'capacity':self.office_capacity(e['entity']),'payroll':sum(float(x['salary']) for x in people),'at_risk':[x['id'] for x in people if x.get('morale',70)<40 or D(x['unpaid'])>D(x['salary'])],'salary_reviews':[x['id'] for x in people if D(x['salary'])<max(D(4000),D(4000)+max(0,x['competence']-65)*100)]};summary='Workforce review: '+str(len(evidence['at_risk']))+' retention risks and '+str(len(evidence['salary_reviews']))+' salaries below current recruitment benchmarks. Pay changes require approval.'
  elif kind=='legal':
   evidence={'cases':[{'id':c['id'],'stage':c['stage'],'deadline':c['deadline'],'overdue':self.state['tick']>c['deadline']} for c in self.state['legal_cases'] if c['entity']==e['entity'] and c['stage']!='CLOSED']};summary='Reviewed regulatory procedure and outstanding response deadlines. Provide records, contest or disclose through Oversight; an allegation is not a conviction.'
  elif kind=='relations':
   fund=next((f for f in self.state['funds'] if f['id']==e['entity']),None);evidence={'equity':m['equity'],'available_cash':m['available_cash'],'investors':list(fund['investors']) if fund else [],'pending_withdrawals':[r['id'] for r in self.state.get('redemptions',[]) if r['fund']==e['entity'] and D(r['remaining'])>0]};summary='Prepared investor enquiry briefing using actual NAV and outstanding withdrawals. New fundraising requires player approval.'
  elif kind=='analyst':
   symbols=[p['symbol'] for p in self.state['positions'].values() if p['account']==e['entity']] or list(self.state['instruments'])[:1];symbol=symbols[0];ins=self.instrument(symbol);evidence={'symbol':symbol,'price':ins['price'],'fundamentals':copy.deepcopy(ins.get('fundamentals',{})),'macro':copy.deepcopy(self.state['macro'])};summary='Security evidence briefing for '+symbol+'. Commission a full valuation and investment opinion from the Trading desk.'
  elif kind=='trader':evidence={'open_orders':[o['id'] for o in self.state['orders'] if o['account']==e['entity'] and o['status'] in ('OPEN','PARTIAL')]};summary='Reviewed execution queue. Trades require assigned instructions and approval or explicit delegation.'
  else:evidence={'equity':m['equity'],'payroll':self.state['operating_plans'].get(e['entity'],{}).get('monthly_payroll','0.00')};summary='Prepared institutional management and remuneration briefing; no corporate decisions were executed.'
  if not reliable:summary='Review delayed: employee missed this reporting deadline.';evidence={}
  elif not quality:summary+=' Limited review: low confidence; obtain a second opinion.'
  report=dict(id=uid(),employee=e['id'],entity=e['entity'],role=kind,time=self.state['time'],tick=self.state['tick'],summary=summary,evidence=evidence,confidence=min(e['competence'],80) if quality else 30,uncertainty=uncertainty,status='PUBLISHED' if reliable else 'DELAYED')
  if reliable and quality and kind=='compliance' and e.get('integrity',75)>=60:
   for reference in evidence.get('flagged',[]):
    if any(c.get('reference')==reference for c in self.state['legal_cases']):continue
    row=next(r for r in rows if r['id']==reference)
    if row['status']!='SETTLED' or not row['reasons']:continue
    if not self.compliance_referral(e,row,report):continue
    case=self.complaint({'entity':e['entity'],'reference':reference,'reason':'Internal compliance referred a recorded discrepancy: '+'; '.join(row['reasons'])});case['evidence'].append(self.evidence('INTERNAL COMPLIANCE',report['id'],'Recorded transaction '+reference,e['entity'],row['amount']));self.employee_log(e,'concern_raised','Referred '+reference+' to '+case['id'],report['id']);break
  self.state['employee_reports'].append(report);self.employee_log(e,'review',summary,report['id']);return report
 def employee_order_limit(self,p,ins):
  actor=p.get('actor','player')
  if not actor.startswith('staff_'):return None
  e=next((e for e in self.staff(p.get('account','personal')) if e['id']==actor),None)
  if not e or e['role'] not in ('trader','portfolio_manager'):raise ValueError('Employee is not a trader for this institution')
  d=e['delegation'];amount=D(str(p['qty']))*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency'])
  if p.get('margin') or p.get('type','market')!='market':raise ValueError('Employee delegation permits only unleveraged immediate market orders')
  day=self.state['tick']//24;used=D(e.get('day_committed','0')) if e.get('trading_day')==day else D(0)
  if not d['trade'] or amount>D(d['per_order']) or used+amount>D(d['daily']):raise ValueError('Employee trading delegation limit exceeded')
  cap=min(D(d['per_order']),D(d['daily'])-used)
  p['_employee_cap']=amt(cap);p['tif']='IOC'
  e['trading_day']=day;e['day_committed']=amt(used+cap)
  return e
 def employee_tick(self):
  w=self.state
  if not w.get('employee_version'):return
  for e in w['employees']:
   if e['status']!='EMPLOYED':continue
   if w['tick']>=e['next_work']:
    e['next_work']=w['tick']+24;self.accrue_employee(e)
    e.setdefault('morale',70);e.setdefault('integrity',60+e['competence']//4)
    overdue=max(D(0),D(e['unpaid'])-D(e['salary']))
    e['morale']=max(0,min(100,e['morale']+(-4 if overdue else 1)))
    if not self.is_frozen(e['entity']):self.employee_review(e)
    if D(e['unpaid'])>D(e['salary'])*2:
     self.employee_departure(e,'RESIGNED','Resigned after more than two months of unpaid salary');continue
   if w['tick']>=e['payroll_next']:
    self.accrue_employee(e);self.pay_employee(e);e['payroll_next']+=720
   tasks=[t for t in w['employee_tasks'] if t['employee']==e['id'] and t['status']=='QUEUED' and t['due']<=w['tick']]
   e['workload']=sum(t['employee']==e['id'] and t['status'] in ('QUEUED','AWAITING APPROVAL') for t in w['employee_tasks']);e['availability']='Busy' if e['workload'] else 'Available'
   for task in tasks[:1]:
    if task['kind']=='order' and task.get('target_quantity') is not None:
     held=D(w['positions'].get(e['entity']+':'+task['instruction']['symbol'],{}).get('qty','0'));target=D(str(task['target_quantity']));satisfied=held<=target if task['instruction'].get('side','buy')=='sell' else held>=target
     if satisfied:
      task.update(status='COMPLETED',result='Absolute position target already satisfied; no duplicate order');continue
    day=w['tick']//24
    if e.get('work_day')!=day:e['work_day']=day;e['work_done']=0
    if e['work_done']>=e['contract']['hours_per_day']:continue
    e['work_done']+=1
    task['attempts']=task.get('attempts',0)+1
    if task['attempts']<=2 and random.Random(e['id']+task.get('time','')+task['kind']+str(task.get('instruction',{}).get('symbol',''))+str(task['attempts'])).randrange(100)>=min(e['competence']+15,e['reliability']):
     task['due']=w['tick']+1;self.employee_log(e,'work_delayed','Instruction delayed by employee workload or reliability',task['id']);continue
    if self.is_frozen(e['entity']):task['status']='FAILED';task['result']='Institution is restricted';self.employee_log(e,'task_failed',task['result'],task['id']);continue
    if task['kind']=='review':task['result']=self.employee_review(e)['id'];task['status']='COMPLETED'
    elif task['kind']=='analysis':task['result']=self.complete_analysis(e,task)['id'];task['status']='COMPLETED'
    else:
     instruction=task['instruction'];ins=self.instrument(instruction['symbol']);notional=D(str(instruction['qty']))*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency']);d=e['delegation'];day=w['tick']//24
     if e.get('trading_day')!=day:e['trading_day']=day;e['day_committed']='0.00'
     delegated=d['trade'] and notional<=D(d['per_order']) and D(e.get('day_committed','0'))+notional<=D(d['daily'])
     if not task['approved'] and not delegated:task['status']='AWAITING APPROVAL';task['result']='Player approval required for this instruction';self.employee_log(e,'approval_requested',task['result'],task['id']);continue
     # Use a savepoint: failed executions cannot leave partially committed money/orders.
     original=copy.deepcopy(w);self.db.execute('SAVEPOINT employee_order')
     try:
      request={**instruction,'actor':'player' if task['approved'] else e['id'],'employee':e['id'],'_staff_task':task['id'],'tif':'IOC'}
      request=self.prepare_team_submission(request,e,task)
      order=self.order(request);task=next(t for t in w['employee_tasks'] if t['id']==task['id']);e=next(x for x in w['employees'] if x['id']==e['id']);self.db.execute('RELEASE employee_order');task['result']=order.get('reason',order['id']) if order['status']=='REJECTED' else order['id'];task['status']='FAILED' if order['status']=='REJECTED' else 'SUBMITTED'
     except (ValueError,KeyError) as exc:
      self.db.execute('ROLLBACK TO employee_order');self.db.execute('RELEASE employee_order');w.clear();w.update(original);task=next(t for t in w['employee_tasks'] if t['id']==task['id']);e=next(x for x in w['employees'] if x['id']==e['id']);task['status']='FAILED';task['result']=str(exc)
    self.employee_log(e,'task_'+task['status'].lower(),str(task['result']),task['id'])
    if task['status']=='FAILED':return  # State was restored; resume other work on the next clock hour.
