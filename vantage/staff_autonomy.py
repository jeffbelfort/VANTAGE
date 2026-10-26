"""Department operations on the existing employee, research and exchange systems."""
import copy, json, random
from decimal import Decimal as D, ROUND_DOWN, InvalidOperation
from .integrity import amt

def mandate_number(value,key):
 from .presentation import label
 try:
  number=D(str(value).strip())
 except (InvalidOperation,ValueError,TypeError):
  raise ValueError(label(key)+': enter a number without commas, currency symbols or abbreviations (for example 1000000).') from None
 if not number.is_finite():raise ValueError(label(key)+': enter a finite number.')
 return number

AUTHORITY_LEVELS = {1:'Advisory only',2:'Limited delegation',3:'Operational delegation',4:'Executive delegation'}

class StaffAutonomyMixin:
 def staff_defaults(self,e):
  rng=random.Random(e['id'])
  for key,value in dict(loyalty=rng.randint(45,85),ambition=rng.randint(40,90),integrity=rng.randint(45,95),morale=70,stress=0,next_department=self.state['tick']+24).items():e.setdefault(key,value)
  e.setdefault('department_policy',dict(level=1,weekly_budget='0.00',capital_limit='0.00',cash_reserve='0.00',symbols=[],revision=0,recruitment_role='analyst',salary_limit='0.00',headcount_target=0))
  return e
 def new_employee(self,entity,candidate,salary):
  employee=super().new_employee(entity,candidate,salary)
  for key in ('integrity','loyalty','ambition'):
   if key in candidate:employee[key]=candidate[key]
  return self.staff_defaults(employee)
 def executive_notice(self,key,title,body,sender='Executive office'):
  notices=self.state.setdefault('executive_notices',{})
  if key in notices:return
  notices[key]=self.state['tick'];self.message(sender,title,body)
 def recruit(self,p):
  candidates=super().recruit(p)
  for candidate in candidates:
   rng=random.Random(candidate['id'])
   for key,low,high in (('integrity',45,95),('loyalty',45,85),('ambition',40,90)):candidate.setdefault(key,rng.randint(low,high))
  return candidates
 def employee_departure(self,e,status,reason):
  super().employee_departure(e,status,reason)
  for row in self.state.get('staff_recommendations',[]):
   if row['employee']==e['id'] and row['status'] in ('PENDING','ASSIGNED'):row.update(status='CANCELLED',reason='Employee employment ended')
  for task in self.state['employee_tasks']:
   if task.get('mandate_owner')==e['id'] and task['status'] in ('QUEUED','AWAITING APPROVAL'):task.update(status='CANCELLED',result='Manager mandate ended with employment')
 def staff_policy(self,p):
  e=next((x for x in self.state['employees'] if x['id']==p['employee'] and x['status']=='EMPLOYED'),None)
  if not e:raise ValueError('Active employee required')
  entity=self.employee_entity(e['entity']);self.staff_defaults(e);old=e['department_policy'];level=int(p.get('level',old['level']))
  if level not in AUTHORITY_LEVELS:raise ValueError('Choose authority level 1–4')
  policy=copy.deepcopy(old)
  for key in ('weekly_budget','capital_limit','cash_reserve','salary_limit'):
   value=mandate_number(p.get(key,old[key]),key)
   ceiling=self.staff_trading_limit(e['entity']) if key in ('capital_limit','cash_reserve') else D(entity['payment_limit'])
   if not value.is_finite() or not 0<=value<=ceiling:raise ValueError(key.replace('_',' ').capitalize()+': enter an amount from £0 to £'+amt(ceiling)+' (applicable company payment authority or delegated portfolio authority).')
   policy[key]=amt(value)
  symbols=list(dict.fromkeys(p.get('symbols',old['symbols'])))
  if len(symbols)>160 or any(s not in self.state['instruments'] or s in self.state['options'] for s in symbols):raise ValueError('Choose at most 160 listed underlying securities')
  from .employees import ROLES
  role=p.get('recruitment_role',old['recruitment_role']);target=int(p.get('headcount_target',old['headcount_target']))
  if role not in ROLES or not 0<=target<=self.office_capacity(e['entity']):raise ValueError('Recruitment role or headcount target exceeds office capacity')
  scope=p.get('universe',old.get('universe','selected'))
  strategy=p.get('strategy',old.get('strategy','blended'))
  if scope not in ('selected','market') or strategy not in ('value','growth','momentum','quality','income','blended'):raise ValueError('Choose a supported universe and investment strategy')
  policy.update(universe=scope,strategy=strategy)
  for key,default,low,high in [('max_position_pct',100,1,100),('max_sector_pct',100,1,100),('cash_target_pct',0,0,100),('max_spread_bps',100,1,10000),('min_volume',0,0,1e15)]:
   value=mandate_number(p.get(key,old.get(key,default)),key)
   if not value.is_finite() or not low<=value<=high:raise ValueError('Invalid '+key.replace('_',' '))
   policy[key]=str(value)
  for key in ('sectors','countries'):
   values=p.get(key,old.get(key,[]))
   if not isinstance(values,list) or len(values)>160 or any(not isinstance(v,str) or len(v)>80 for v in values):raise ValueError('Invalid market filters')
   policy[key]=list(dict.fromkeys(values))
  policy.update(level=level,symbols=symbols,revision=old['revision']+1,recruitment_role=role,headcount_target=target)
  if e['role'] in ('trader','portfolio_manager'):
   per=mandate_number(p.get('per_order',e['delegation']['per_order']),'per_order');daily=mandate_number(p.get('daily',e['delegation']['daily']),'daily')
   if level>1 and (policy['capital_limit']=='0.00' or (scope=='selected' and not symbols)):raise ValueError('Delegated trading requires capital and a selected or market-wide universe')
   self.employee_change(dict(employee=e['id'],kind='delegate',trade=level>1,per_order=str(per),daily=str(daily)))
  e['department_policy']=policy;e['next_department']=self.state['tick']+1
  self.employee_log(e,'department_policy',AUTHORITY_LEVELS[level]+'; weekly operating budget £'+policy['weekly_budget']);return policy
 def department_spend(self,e,amount,description):
  amount=D(amount);policy=e['department_policy'];week=self.state['tick']//168
  used=D(e.get('department_spent','0')) if e.get('department_week')==week else D(0)
  if policy['level']<2 or used+amount>D(policy['weekly_budget']) or amount>self.available_cash(e['entity']) or self.is_frozen(e['entity']):raise ValueError('Department expenditure exceeds delegated weekly budget or available cash')
  self.post(description,{'cash:'+e['entity']:-amount,'expense:department:'+e['entity']:amount,'cash:department_suppliers':amount,'pnl:department_suppliers':-amount})
  e['department_week']=week;e['department_spent']=amt(used+amount)
 def staff_recommendation(self,e,kind,key,summary,evidence,payload=None):
  from .engine import uid
  rows=self.state['staff_recommendations']
  existing=next((r for r in rows if r['key']==key and r['status'] in ('PENDING','ASSIGNED')),None)
  if existing:return existing
  row=dict(id=uid(),employee=e['id'],entity=e['entity'],kind=kind,key=key,summary=summary,evidence=copy.deepcopy(evidence),payload=copy.deepcopy(payload or {}),status='PENDING',tick=self.state['tick'],time=self.state['time'])
  rows.append(row);self.executive_notice('recommendation:'+row['id'],summary,'Recommendation '+row['id']+' from '+e['name']+'. Review it in Executive Office.',e['department']);return row
 def staff_decision(self,p):
  row=next(r for r in self.state['staff_recommendations'] if r['id']==p['recommendation']);self.employee_entity(row['entity'])
  pending_task=next((t for t in self.state['employee_tasks'] if t['id']==row.get('task') and t['status']=='AWAITING APPROVAL'),None)
  if row['status']!='PENDING' and not (row['status']=='ASSIGNED' and pending_task):raise ValueError('Recommendation already decided')
  e=next(x for x in self.state['employees'] if x['id']==row['employee'])
  if e['status']!='EMPLOYED':raise ValueError('Recommendation author has left; obtain a fresh recommendation')
  choice=p['decision']
  if choice=='reject':
   row['status']='REJECTED'
   if pending_task:pending_task['status']='CANCELLED';pending_task['result']='Player rejected department recommendation'
   if row['kind'] in ('salary','promotion'):e['morale']=max(0,e['morale']-8);e['loyalty']=max(0,e['loyalty']-5);e['stress']=min(100,e['stress']+8)
  elif choice=='accept':
   if row['kind']=='trade':
    if pending_task:
     report=next((r for r in self.state['stock_research'] if r['id']==row['evidence'].get('research')),None)
     if not self.current_research(report):raise ValueError('Research recommendation is stale')
     self.employee_approve({'task':pending_task['id']})
    else:self.assign_recommendation(row,approved=True)
   elif row['kind'] in ('salary','promotion'):
    salary=D(row['payload']['salary'])
    if self.available_cash(e['entity'])<salary:raise ValueError('Hold a month of the proposed salary before approving')
    self.employee_change(dict(employee=e['id'],kind='promote' if row['kind']=='promotion' else 'salary',salary=str(salary)));e['morale']=min(100,e['morale']+15);e['loyalty']=min(100,e['loyalty']+10);e['stress']=max(0,e['stress']-15);row['status']='COMPLETED'
   elif row['kind']=='fundraise':
    row['result']=self.fundraising(row['payload']);row['status']='COMPLETED'
   elif row['kind']=='recruit':
    row['result']=[c['id'] for c in self.recruit({'entity':row['entity'],'role':row['payload']['role']})];row['status']='COMPLETED'
   else:row['status']='ACKNOWLEDGED'
  else:raise ValueError('Choose accept or reject')
  row['decided_tick']=self.state['tick'];self.audit('staff_decision',dict(recommendation=row['id'],decision=choice));return row
 def current_research(self,report):
  if not report or not 0<=self.state['tick']-report['tick']<=168:return False
  ins=self.instrument(report['symbol']);evidence=report['evidence']
  if abs(D(str(evidence.get('macro',{}).get('rate',self.state['macro']['rate'])))-D(str(self.state['macro']['rate'])))>=D('.25'):return False
  return evidence['fundamentals']==self.research_fundamentals(report['symbol'])[0] and evidence.get('public_earnings_factor','1')==ins.get('public_earnings_factor','1') and abs(D(ins['price'])/D(evidence['price'])-1)<=D('.1')
 def assign_recommendation(self,row,approved=False):
  if row['status']!='PENDING':raise ValueError('Only a pending recommendation may create an execution task')
  report=next((r for r in self.state['stock_research'] if r['id']==row['evidence'].get('research')),None)
  if not self.current_research(report):raise ValueError('Research recommendation is stale; public fundamentals or prices changed')
  e=next(x for x in self.state['employees'] if x['id']==row['employee']);policy=e['department_policy']
  if e['status']!='EMPLOYED':raise ValueError('Recommendation author no longer employed')
  symbol=row['payload']['symbol'];ins=self.instrument(symbol)
  if abs(D(ins['price'])/D(report['evidence']['price'])-1)>D('.1'):raise ValueError('Price changed materially; obtain fresh research')
  if not approved and (policy['level']<2 or not e['delegation']['trade']):raise ValueError('Autonomous trading is not authorised')
  # A trader can execute for a manager only within BOTH employees' mandates.
  traders=[x for x in self.staff(e['entity']) if x['role']=='trader' and x.get('department_policy',{}).get('level',1)>1 and x['delegation']['trade'] and self.mandate_allows(x['department_policy'],symbol)]
  executor=(e if e['role']=='trader' else min(traders,key=lambda person:sum(t['employee']==person['id'] and t['status'] in ('QUEUED','AWAITING APPROVAL') for t in self.state['employee_tasks']))) if traders and not approved else e
  task=self.employee_task(dict(employee=executor['id'],kind='order',**row['payload']))
  task.update(approved=approved,recommendation=row['id'],mandate_owner=e['id'],policy_revision=policy['revision'],executor_revision=executor['department_policy']['revision'],target_quantity=row['evidence'].get('target_quantity'))
  row.update(status='ASSIGNED',task=task['id'],executor=executor['id']);self.employee_log(e,'recommendation_assigned',symbol+' assigned to '+executor['name'],task['id']);return task
 def employee_task(self,p):
  e=next((e for e in self.state['employees'] if e['id']==p['employee']),None);tip=None
  if p.get('intelligence'):
   if not e:raise ValueError('Active employee required')
   self.employee_entity(e['entity']);tip=next((t for t in self.state['intelligence'] if t['id']==p['intelligence'] and t['account']==e['entity'] and t['status']=='CONFIDENTIAL'),None)
   if not tip or p.get('symbol')!=tip['symbol'] and self.state['options'].get(p.get('symbol'),{}).get('underlying')!=tip['symbol']:raise ValueError('Confidential basis must reference actual intelligence for this employer and security')
  task=super().employee_task(p)
  if tip:
   task['intelligence']=tip['id']
   if e.get('integrity',75)>=70 and self.state['tick']<tip['publish_tick']:
    task.update(status='REFUSED',result='Employee refused an explicitly confidential pre-announcement instruction');self.employee_log(e,'instruction_refused',task['result'],task['id']);self.executive_notice('refusal:'+task['id'],e['name']+' refused an improper instruction','The employee was given an actual confidential tip as the basis for a trade. No order was submitted.',e['department'])
  return task
 def employee_order_limit(self,p,ins):
  actor=p.get('actor','player');entity=p.get('account','personal');team=self.state.get('auto_teams',{}).get(entity,{})
  if team.get('enabled') and actor in team['members']:
   person=next((e for e in self.staff(entity) if e['id']==actor),None);day=self.state['tick']//24
   if person and person['role']=='trader':
    pending=sum((max(D(0),D(o.get('employee_cap','0'))-D(o.get('employee_executed','0'))) for o in self.state['orders'] if o.get('employee')==actor and o['status'] in ('OPEN','PARTIAL','PAUSED')),D(0))
    person['trading_day']=day;person['day_committed']=amt((D(person.get('fill_spent','0')) if person.get('fill_day')==day else D(0))+pending)
  employee=super().employee_order_limit(p,ins)
  if not employee:return employee
  task=next((t for t in self.state['employee_tasks'] if t['id']==p.get('_staff_task') and t.get('recommendation')),None)
  if task:
   recommendation=next(r for r in self.state['staff_recommendations'] if r['id']==task['recommendation']);report=next((r for r in self.state['stock_research'] if r['id']==recommendation['evidence'].get('research')),None)
   if not self.current_research(report):raise ValueError('Department research is stale; no autonomous execution')
  executor_policy=self.team_policy(employee)
  if not task and executor_policy.get('level',1)<=1:return employee
  owner=next(x for x in self.state['employees'] if x['id']==task['mandate_owner']) if task else employee;policy=self.team_policy(owner);symbol=ins['symbol']
  if owner['status']!='EMPLOYED' or policy['level']<2 or (task and (policy['revision']!=task['policy_revision'] or executor_policy['revision']!=task['executor_revision'])) or executor_policy['level']<2:raise ValueError('Department mandate was revoked or changed')
  if owner['entity']!=employee['entity'] or not self.mandate_allows(policy,symbol) or not self.mandate_allows(executor_policy,symbol):raise ValueError('Instruction is outside department security mandates')
  if symbol in self.state['options'] or p.get('margin'):raise ValueError('Autonomous mandates permit only unleveraged underlying trades')
  if any(o['account']==owner['entity'] and o['symbol']==symbol and o['status'] in ('OPEN','PARTIAL') for o in self.state['orders']):raise ValueError('Existing working order must finish before autonomous adjustment')
  held=D(self.state['positions'].get(owner['entity']+':'+symbol,{}).get('qty','0'));qty=D(str(p['qty']));px=D(ins['price'])*self.fx_rate(ins['currency'])
  if p.get('side','buy')=='sell' and qty>max(D(0),held):raise ValueError('Mandates cannot create short positions')
  equity=max(D(0),D(self.metrics(owner['entity'])['equity']))
  if self.manual_choice_applies(owner['entity'],symbol):
   justified_reduction=p.get('side')=='sell' and (held*px>min(D(policy['capital_limit']),equity*D(policy.get('max_position_pct','100'))/100) or self.team_sector_exposure(owner['entity']).get(ins.get('sector'),D(0))>equity*D(policy.get('max_sector_pct','100'))/100 or self.team_redemptions(owner['entity'])>self.available_cash(owner['entity']))
   if not justified_reduction:raise ValueError('Manual portfolio choice retained; new public evidence or a genuine mandate/liquidity breach is required')
  reserve=max(D(policy['cash_reserve']),D(executor_policy['cash_reserve']),equity*max(D(policy.get('cash_target_pct','0')),D(executor_policy.get('cash_target_pct','0')))/100)
  if p.get('side','buy')=='buy':
   sector=ins.get('sector');exposure=sum((abs(D(pos['qty']))*D(self.instrument(pos['symbol'])['price'])*D(self.instrument(pos['symbol']).get('multiplier',1))*self.fx_rate(self.instrument(pos['symbol'])['currency']) for pos in self.state['positions'].values() if pos['account']==owner['entity'] and self.instrument(pos['symbol']).get('sector')==sector),D(0))
   if exposure+qty*px>equity*min(D(policy.get('max_sector_pct','100')),D(executor_policy.get('max_sector_pct','100')))/100:raise ValueError('Sector concentration mandate exceeded')
   if (held+qty)*px>equity*min(D(policy.get('max_position_pct','100')),D(executor_policy.get('max_position_pct','100')))/100:raise ValueError('Position concentration mandate exceeded')
  limit=min(D(policy['capital_limit']),D(executor_policy['capital_limit']))
  if p.get('side','buy')=='buy' and ((held+qty)*px>limit or self.available_cash(owner['entity'])-qty*px<reserve):raise ValueError('Capital mandate or cash reserve exceeded')
  cap=D(p['_employee_cap'])
  if owner['id']!=employee['id']:
   day=self.state['tick']//24;used=D(owner.get('day_committed','0')) if owner.get('trading_day')==day else D(0)
   if not owner['delegation']['trade']:raise ValueError('Manager trading authority revoked')
   cap=min(cap,D(owner['delegation']['per_order']),D(owner['delegation']['daily'])-used)
   if qty*px>cap:raise ValueError('Manager aggregate daily authority exceeded')
   owner['trading_day']=day;owner['day_committed']=amt(used+cap)
  if p.get('side','buy')=='buy':cap=min(cap,max(D(0),self.available_cash(owner['entity'])-reserve),max(D(0),limit-held*px))
  team=self.state.get('auto_teams',{}).get(employee['entity'],{})
  if team.get('enabled') and employee['id'] in team['members']:
   used=self.team_daily_spend(employee['entity'])+self.team_pending_turnover(employee['entity']);remaining=max(D(0),D(team.get('daily_limit',team.get('portfolio_authority','0')))-used)
   if qty*px>remaining:raise ValueError('Shared team daily trading limit exceeded')
   cap=min(cap,remaining)
  p['_employee_cap']=amt(cap);return employee
 def compliance_referral(self,e,row,report):
  from .engine import uid
  cases=self.state['internal_reviews'];review=next((r for r in cases if r['entity']==e['entity'] and r['reference']==row['id']),None)
  if not review:
   review=dict(id=uid(),entity=e['entity'],employee=e['id'],reference=row['id'],opened=self.state['tick'],status='REVIEWING',evidence=[report['id']],reasons=copy.deepcopy(row['reasons']));cases.append(review)
   self.executive_notice('internal:'+review['id'],'Compliance opened an internal review','Recorded transaction '+row['id']+' is being compared with its mandate.',e['name']);return False
  if self.state['tick']-review['opened']<24:return False
  if report['id'] not in review['evidence']:review['evidence'].append(report['id'])
  review['status']='REFERRED';return True
 def department_tick(self):
  w=self.state
  for e in sorted(list(w['employees']),key=lambda person:{'analyst':0,'risk':1,'portfolio_manager':3,'trader':4}.get(person['role'],2)):
   if e['status']!='EMPLOYED':continue
   self.staff_defaults(e)
   if w['tick']<e['next_department']:continue
   e['next_department']=w['tick']+24;policy=e['department_policy'];entity=e['entity']
   active=[t for t in w['employee_tasks'] if t['employee']==e['id'] and t['status'] in ('QUEUED','AWAITING APPROVAL')]
   e['stress']=max(0,min(100,e['stress']+(5 if len(active)>=3 else -2)+(4 if D(e['unpaid'])>D(e['salary']) else 0)))
   if e['morale']<20 and e['stress']>70 and e['loyalty']<50:
    e.setdefault('retention_since',w['tick'])
    if w['tick']-e['retention_since']>=168:
     self.accrue_employee(e);self.employee_departure(e,'RESIGNED','Sustained low morale, high stress and low loyalty after an unresolved retention warning');self.executive_notice('resigned:'+e['id'],e['name']+' resigned','Earned wages remain payable.');continue
    self.executive_notice('retention:'+e['id'],e['name']+' is considering resignation','Low morale and sustained workload stress require management attention.')
   else:e.pop('retention_since',None)
   if self.is_frozen(entity):continue
   week=w['tick']//168
   if e.get('request_week')!=week:
    benchmark=max(D(4000),D(4000)+max(0,e['competence']-65)*100)
    recent=any(r['employee']==e['id'] and r['kind'] in ('salary','promotion') and (r['status']=='PENDING' or w['tick']-r['tick']<720) for r in w['staff_recommendations'])
    if not recent and D(e['salary'])<benchmark and w['tick']-e['hired_tick']>=168:
     self.staff_recommendation(e,'salary','salary:'+e['id'],e['name']+' requests a salary review',{'salary':e['salary'],'recruitment_benchmark':amt(benchmark),'ambition':e['ambition']},{'salary':amt(benchmark)})
    elif not recent and e['ambition']>=75 and w['tick']-e['hired_tick']>=720 and len(e['performance_history'])>=10:
     self.staff_recommendation(e,'promotion','promotion:'+e['id'],e['name']+' requests promotion',{'grade':e['grade'],'completed_work':len(e['performance_history'])},{'salary':amt(D(e['salary'])*D('1.05'))})
    e['request_week']=week
   try:
    if e['role']=='analyst':
     if w.get('auto_teams',{}).get(entity,{}).get('enabled'):self.portfolio_screen(e)
     else:self.department_research(e,active)
    elif e['role']=='portfolio_manager':
     if self.team_treasury_income(e):continue
     self.portfolio_screen(e)
     self.department_portfolio(e)
    elif e['role']=='relations' and e.get('relations_week')!=week:
     fund=next((f for f in w['funds'] if f['id']==entity),None)
     if fund:
      withdrawals=[r for r in w.get('redemptions',[]) if r['fund']==entity and D(r['remaining'])>0]
      if withdrawals:self.staff_recommendation(e,'liquidity','redemptions:'+entity,'Investor relations flags unpaid withdrawals',{'withdrawals':[r['id'] for r in withdrawals],'amount':amt(sum((D(r['remaining']) for r in withdrawals),D(0)))})
      requests=[request for activity in w['social_events'] if activity['status']=='COMPLETED' for request in activity.get('business_requests',[]) if w['tick']-activity.get('completed_tick',activity['tick'])<=168]
      if requests and not withdrawals and not any(r['fund']==entity and w['tick']-r['tick']<168 for r in w['fundraising_rounds']):
       target=min(sum((D(r['available_wealth'])*D('.1') for r in requests),D(0)),D(policy['capital_limit']) or D(100000))
       if target>0:
        recommendation=self.staff_recommendation(e,'fundraise','fundraise:'+entity+':'+str(week),'Investor relations proposes a funded allocation round',{'meeting_requests':requests,'actual_nav':self.metrics(entity)['equity']},{'fund':entity,'target':amt(target)})
        if policy['level']>=4 and D(policy['capital_limit'])>=target and recommendation['status']=='PENDING':recommendation['result']=self.fundraising(recommendation['payload']);recommendation['status']='COMPLETED'
      if policy['level']>=2 and D(self.metrics(entity)['equity'])>0:
       self.department_spend(e,D(250),'Authorised investor update');statement=self.report({'fund':entity,'reported':self.metrics(entity)['equity']});self.employee_log(e,'investor_update','Actual NAV distributed to existing investors',statement['id']);e['relations_week']=week
    elif e['role'] in ('accountant','operations','executive'):
     obligations=self.obligation_view(entity);cash=self.available_cash(entity)
     if D(obligations['due_week'])>cash:self.staff_recommendation(e,'liquidity','cash:'+entity,'Finance flags a seven-day liquidity shortfall',{'cash':amt(cash),**obligations})
    elif e['role']=='hr':self.department_hr(e)
    elif e['role']=='legal':
     for case in w['legal_cases']:
      if case['entity']!=entity or case['stage']=='CLOSED':continue
      if not case.get('cooperating'):
       if policy['level']>=3 and not any(r['response']=='provide_records' for r in case['responses']):
        self.department_spend(e,D(500),'Authorised regulatory document preparation');self.respond_case({'id':case['id'],'response':'provide_records'});self.employee_log(e,'legal_response','Records supplied under operational authority',case['id'])
       else:self.staff_recommendation(e,'legal','legal:'+case['id'],'Legal counsel recommends providing case records',{'case':case['id'],'deadline':case['deadline'],'stage':case['stage']})
    elif e['role']=='trader':
     self.portfolio_screen(e)
     if policy.get('universe')=='market':self.department_portfolio(e)
     self.team_treasury_income(e)
     for task in w['employee_tasks']:
      if task['employee']!=e['id'] or task['status']!='SUBMITTED':continue
      order=next((o for o in w['orders'] if o['id']==task['result']),None)
      if order and D(order['remaining'])>0:self.executive_notice('execution:'+order['id'],'Trader reports an incomplete execution',f"{order['symbol']}: {order['filled']} filled of {order['qty']}; {order['status']}. No replacement order is assumed.",e['name'])
   except ValueError as exc:
    if w.get('auto_teams',{}).get(entity,{}).get('enabled'):w['auto_teams'][entity]['activity']='Needs attention: '+str(exc)
    self.executive_notice('department-blocked:'+e['id']+':'+str(week),'Department work needs attention',e['name']+': '+str(exc))
 def department_research(self,e,active):
  if len(active)>=3 or e.get('research_policy',{}).get('enabled'):return
  w=self.state;symbols=e['department_policy']['symbols'] or [p['symbol'] for p in w['positions'].values() if p['account']==e['entity'] and p['symbol'] in w['instruments']] or w.get('watchlist',[])[:1] or list(w['instruments'])[:1]
  for symbol in symbols[:8]:
   if symbol not in w['instruments'] or symbol in w['options']:continue
   reports=[r for r in w['stock_research'] if r['entity']==e['entity'] and r['symbol']==symbol];last=reports[-1] if reports else None
   if last and w['tick']-last['tick']<168 and last['evidence']['fundamentals']==self.instrument(symbol).get('fundamentals',{}) and last['evidence'].get('public_earnings_factor','1')==self.instrument(symbol).get('public_earnings_factor','1'):continue
   if any(t['kind']=='analysis' and t['instruction'].get('symbol')==symbol for t in active):continue
   from .engine import uid
   task=dict(id=uid(),employee=e['id'],entity=e['entity'],kind='analysis',instruction={'symbol':symbol},status='QUEUED',due=w['tick']+max(4,12-e['competence']//15),time=w['time'],approved=False,result=None,cost='0.00',origin='SALARIED DEPARTMENT RESEARCH');w['employee_tasks'].append(task);self.employee_log(e,'internal_research',symbol+' assigned within salaried work',task['id']);break
 def department_portfolio(self,e):
  w=self.state;policy=self.team_policy(e);entity=e['entity'];seen=e.setdefault('research_seen',[])
  team=w.get('auto_teams',{}).get(entity,{})
  if team.get('enabled'):team['activity']='Reviewing shared research; no justified adjustment yet'
  reports=[r for r in w['stock_research'] if r['entity']==entity and r['id'] not in seen and w['tick']-r['tick']<=168 and self.current_research(r)]
  if team.get('enabled') and not reports:team['activity']='No recorded dividend-paying equities qualify for the Income mandate; retaining cash' if policy.get('strategy')=='income' else 'Waiting for fresh analyst research or a material change'
  for report in reports[-8:]:
   symbol=report['symbol']
   if not self.mandate_allows(policy,symbol):continue
   seen.append(report['id']);seen[:]=seen[-64:]
   for prior in w['staff_recommendations']:
    if prior['entity']!=entity or prior['kind']!='trade' or prior['payload'].get('symbol')!=symbol or prior['status'] not in ('PENDING','ASSIGNED') or prior['evidence'].get('research')==report['id']:continue
    task=next((t for t in w['employee_tasks'] if t['id']==prior.get('task')),None)
    if task and task['status']=='SUBMITTED':continue
    prior['status']='SUPERSEDED'
    if task and task['status'] in ('QUEUED','AWAITING APPROVAL'):task.update(status='CANCELLED',result='New research superseded this recommendation')
   actual_profit=report['evidence']['fundamentals'].get('profit')
   deterioration=report['recommendation']=='Avoid' and actual_profit is not None and D(str(actual_profit))<0
   team=w.get('auto_teams',{}).get(entity,{});ins=self.instrument(symbol);held=D(w['positions'].get(entity+':'+symbol,{}).get('qty','0'));price=D(ins['price'])*self.fx_rate(ins['currency']);equity=max(D(0),D(self.metrics(entity)['equity']));withdrawals=self.team_redemptions(entity) if team.get('enabled') else D(0);shortfall=max(D(0),withdrawals-self.available_cash(entity));excess=max(D(0),held*price-min(D(policy['capital_limit']),equity*D(policy.get('max_position_pct','100'))/100));sector_excess=max(D(0),self.team_sector_exposure(entity).get(ins.get('sector'),D(0))-equity*D(policy.get('max_sector_pct','100'))/100);reduction=min(max(D(0),held*price),max(shortfall,excess,sector_excess)) if team.get('enabled') else D(0)
   if self.manual_choice_applies(entity,symbol) and reduction<=0:
    if team.get('enabled'):team['activity']='Respecting the manual position in '+symbol+' until material information or mandate requirements change'
    continue
   opinion=report['recommendation'];decision_basis='Shared analyst valuation';forecast=None
   if team.get('enabled') and (opinion=='Hold' or policy.get('strategy')=='growth') and report['confidence']>=50 and actual_profit is not None and D(str(actual_profit))>0 and policy.get('strategy','blended')!='value':
    f=report['evidence']['fundamentals'];shares=D(str(f.get('shares') or 0));growth=D(str(w['macro'].get('growth',0)))/100;strategy=policy.get('strategy','blended');bars=[bar for bar in ins.get('history',[]) if 0<=bar.get('t',-1)<=w['tick']][-120:];momentum=D(ins['price'])/D(str(bars[0]['c']))-1 if bars else D(0)
    levels=report['evidence'].get('market_depth',[]);level=levels[0] if levels else {};friction=(D(str(level['ask']))-D(str(level['bid'])))/D(ins['price'])+D('.001') if level.get('ask') and level.get('bid') else D('.003')
    earnings_yield=D(str(report['evidence'].get('expected_model_profit') or actual_profit))/(shares*D(ins['price'])) if shares>0 else D(0);inflation=D(str(w['macro'].get('inflation',0)))/100;expected=earnings_yield+growth+inflation;required=D(str(w['macro'].get('rate',0)))/100+{'careful':D('.03'),'balanced':D('.015'),'adventurous':D('.005')}[team['mode']]
    eligible=(strategy!='momentum' or momentum>0) and (strategy!='growth' or growth>0) and (strategy!='quality' or D(str(f.get('revenue') or 0))>0 and D(str(actual_profit))/D(str(f['revenue']))>=D('.1')) and strategy!='income'
    forecast=dict(expected_long_run_return=str(expected),required_return=str(required),estimated_trading_friction=str(friction),real_growth=str(growth),inflation=str(inflation),assumption='Nominal long-run scenario: earnings yield plus real GDP growth and inflation, assuming partial pricing-power pass-through. Margins may compress; this is not a promised payout or future price')
    if eligible and expected>required+friction:
     opinion='Buy';decision_basis='Trader accepts earnings yield and public growth scenario above the chosen risk-appetite hurdle, despite an analyst Hold'
   # Strategy evidence and intrinsic valuation are different investment theses.
   # Momentum may disagree with a valuation Avoid, but never with execution rules.
   strategy=policy.get('strategy','blended');strategy_evidence=None;independent_signal=False
   if strategy=='momentum':
    trend=report['evidence'].get('observed_trend') or self.observed_equity_trend(symbol);levels=report['evidence'].get('market_depth',[]);level=levels[0] if levels else {};friction=float((D(str(level['ask']))-D(str(level['bid'])))/D(report['evidence']['price']))+.001 if level.get('ask') and level.get('bid') else .003
    entry=trend['enough_history'] and trend['return_fraction']>2*friction and trend['above_recent_average']>friction and trend['trend_strength']>.5 and trend['volume']>0
    exit_signal=trend['enough_history'] and trend['return_fraction']<-2*friction and trend['above_recent_average']<-friction and trend['trend_strength']<-.5
    opinion='Avoid' if held>0 and exit_signal else 'Buy' if entry else 'Hold';independent_signal=entry or exit_signal;decision_basis='Recorded multi-horizon equity trend and liquidity; earnings valuation remains a separate advisory opinion';strategy_evidence=dict(**trend,estimated_round_trip_friction=2*friction,entry=entry,exit=exit_signal)
   elif strategy=='growth':
    # A growth thesis is not a trailing-price/cost or value-multiple stop-loss.
    known=actual_profit is not None
    exit_signal=known and (D(str(actual_profit))<0 or forecast is not None and D(forecast['expected_long_run_return'])<D(forecast['required_return'])-D(forecast['estimated_trading_friction']))
    if held>0 and exit_signal:opinion='Avoid';independent_signal=True
    elif opinion=='Avoid':opinion='Hold'
    decision_basis='Growth earnings/public-growth return scenario versus financing and transaction costs; valuation Avoid alone is advisory';strategy_evidence=dict(exit=bool(exit_signal),scenario=forecast,profit_known=known)
   elif strategy=='quality':
    financials=report['evidence']['fundamentals'];revenue=D(str(financials.get('revenue') or 0));margin=D(str(actual_profit or 0))/revenue if revenue>0 and actual_profit is not None else None;exit_signal=margin is not None and margin<D('.1')
    if held>0 and exit_signal:opinion='Avoid';independent_signal=True
    elif opinion=='Avoid':opinion='Hold'
    decision_basis='Observed earnings margin against the Quality entry requirement; valuation Avoid alone is advisory';strategy_evidence=dict(exit=bool(exit_signal),profit_margin=str(margin) if margin is not None else None,quality_margin_requirement='.1')
   elif strategy=='income':
    dividend=D(str(report['evidence']['fundamentals'].get('annual_dividend_per_share') or 0));shares=D(str(report['evidence']['fundamentals'].get('shares') or 0));profit=D(str(actual_profit or 0));income_yield=dividend/D(ins['price']);bond_yield=D(str(self.treasury_yield(5) if w.get('fed') else w['macro']['rate']))/100
    covered=shares>0 and profit/shares>=dividend and dividend>0
    independent_signal=covered and income_yield>bond_yield+D('.005');opinion='Buy' if independent_signal else 'Avoid' if held>0 and report['evidence']['fundamentals'].get('annual_dividend_per_share') is not None and (dividend<=0 or not covered) else 'Hold';decision_basis='Recorded dividend yield and earnings coverage compared with eligible Treasury income';strategy_evidence=dict(dividend_per_share=str(dividend),dividend_yield=str(income_yield),treasury_yield=str(bond_yield),earnings_cover=covered)
   if ((report['confidence']<50 and not deterioration and not independent_signal) or opinion=='Hold') and reduction<=0:
    if team.get('enabled'):team['activity']='No trade: current research is Hold or insufficiently confident; comparing other securities'
    continue
   if opinion=='Avoid' and held<=0 and reduction<=0:
    if team.get('enabled'):team['activity']='Research avoids '+symbol+'; long-only traders are comparing other opportunities'
    continue
   if any(o['account']==entity and o['symbol']==symbol and o['status'] in ('OPEN','PARTIAL') for o in w['orders']):continue
   if any(r['entity']==entity and r['kind']=='trade' and r['payload'].get('symbol')==symbol and (r['status']=='PENDING' or r['status']=='ASSIGNED' and any(t['id']==r.get('task') and t['status'] in ('QUEUED','AWAITING APPROVAL') for t in w['employee_tasks'])) for r in w['staff_recommendations']):continue
   ins=self.instrument(symbol);price=D(ins['price'])*self.fx_rate(ins['currency']);held=D(w['positions'].get(entity+':'+symbol,{}).get('qty','0'));capital=D(policy['capital_limit']) or min(D(100000),self.available_cash(entity)*D('.1'));equity=max(D(0),D(self.metrics(entity)['equity']));capital=min(capital,equity*D(policy.get('max_position_pct','100'))/100);reserve=max(D(policy['cash_reserve']),equity*D(policy.get('cash_target_pct','0'))/100);side='sell' if opinion=='Avoid' or reduction>0 else 'buy'
   budget=min(capital,max(D(0),self.available_cash(entity)-reserve),D(e['delegation']['per_order']) if e['delegation']['trade'] else D(10000))
   if team.get('enabled') and side=='buy':budget=min(budget,max(D(0),equity*D(policy.get('max_sector_pct','100'))/100-self.team_sector_exposure(entity).get(ins.get('sector'),D(0))),max(D(0),D(team.get('daily_limit','0'))-self.team_daily_spend(entity)))
   sale_budget=D(e['delegation']['per_order']) if e['delegation']['trade'] else D(10000)
   target_quantity=0 if side=='sell' and opinion=='Avoid' else max(0,int((held-reduction/price).to_integral_value(rounding=ROUND_DOWN))) if reduction>0 else None
   qty=min(max(0,int(held)-target_quantity),max(0,int(sale_budget/(price*D('1.01'))))) if side=='sell' else int(max(D(0),min(budget,capital-held*price))/(price*D('1.01')))
   target_basis='Exit the failed investment thesis' if side=='sell' and opinion=='Avoid' else 'Meet current cash, position or sector constraint' if reduction>0 else 'Strategy allocation within actual funding'
   # Avoid cost-dominated discretionary top-ups; hard constraints and exits
   # remain enforceable even at a loss or for a small residual position.
   depth=report['evidence'].get('market_depth',[]);level=depth[0] if depth else {};spread=(D(str(level['ask']))-D(str(level['bid'])))/D(ins['price']) if level.get('ask') and level.get('bid') else D('.003')
   estimated_round_trip_cost=max(D(2),D(qty)*price*D('.001'))+D(qty)*price*max(D(0),spread)
   if side=='buy' and held>0 and D(qty)*price<=max(D(held)*price*(max(D(0),spread)+D('.001')),estimated_round_trip_cost):
    if team.get('enabled'):team['activity']='Existing position retained: proposed rebalance is too small relative to execution costs'
    continue
   advice=w.get('auto_teams',{}).get(entity,{}).get('risk_review');sector_share=self.team_sector_exposure(entity).get(ins.get('sector'),D(0))/equity if equity else D(0);edge=D(report['fair_centre'])/D(ins['price'])-1;advice_used=bool(advice and w['tick']-advice['tick']<=48 and side=='buy' and sector_share>D('.4') and edge<D('.25') and team.get('mode')!='adventurous')
   if advice_used:qty=int(D(qty)*D('.95'))
   if qty<1:
    if team.get('enabled'):team['activity']='No order: cash reserves, shared turnover or position/sector allocation is already committed'
    continue
   if side=='buy':target_quantity=int(held)+qty
   if team.get('enabled'):team['activity']='Submitting '+side+' '+str(qty)+' '+symbol+' using current research'
   row=self.staff_recommendation(e,'trade','trade:'+entity+':'+symbol,'Portfolio adjustment: '+side+' '+str(qty)+' '+symbol,{'research':report['id'],'strategy':policy.get('strategy','blended'),'mandate':copy.deepcopy(policy),'rationale':(['Reduce exposure to meet liquidity or concentration requirements'] if reduction>0 else [])+copy.deepcopy(report['reasoning']),'risks':copy.deepcopy(report['risks']),'proposal_risk':dict(advisory=True,sector_share_pct=str(sector_share*100),proposed_notional=amt(D(qty)*price),expected_valuation_edge=str(edge),size_adjustment='5% smaller; trader retains discretion' if advice_used else 'No reduction',basis='Current exposure and public valuation; volatility alone does not restrict trading') if advice else None,'risk_advice_applied':advice_used,'team_risk_review':copy.deepcopy(w.get('auto_teams',{}).get(entity,{}).get('risk_review')),'information_tick':report['tick'],'recommendation':opinion,'analyst_recommendation':report['recommendation'],'decision_basis':decision_basis,'return_scenario':forecast,'strategy_evidence':strategy_evidence,'target_quantity':target_quantity,'target_basis':target_basis,'estimated_round_trip_cost_gbp':amt(estimated_round_trip_cost),'price':ins['price'],'held':str(held),'realised':self.metrics(entity)['realised'],'unrealised':self.metrics(entity)['unrealised']},{'symbol':symbol,'side':side,'qty':qty})
   if policy['level']>1 and e['delegation']['trade']:self.assign_recommendation(row)
 def department_hr(self,e):
  policy=e['department_policy'];entity=e['entity'];people=self.staff(entity);target=policy['headcount_target']
  if target<=len(people):return
  role=policy['recruitment_role'];key='recruit:'+entity+':'+role
  if policy['level']<3:
   self.staff_recommendation(e,'recruit',key,'HR recommends recruiting '+role,{'headcount':len(people),'target':target,'capacity':self.office_capacity(entity)},{'role':role});return
  candidates=[c for c in self.state['recruitment'] if c['entity']==entity and c['role']==role and c['status']=='AVAILABLE']
  if not candidates:candidates=self.recruit({'entity':entity,'role':role});self.employee_log(e,'recruitment_search','Candidates located for '+role)
  if policy['level']>=4:
   candidate=min(candidates,key=lambda c:D(c['minimum_salary']));salary=D(candidate['minimum_salary'])
   if salary>D(policy['salary_limit']) or salary>self.available_cash(entity):return
   if e.get('hire_week')==self.state['tick']//168:return
   offer=self.employment_offer({'candidate':candidate['id'],'salary':str(salary)});hire=self.employee_hire({'offer':offer['id']});e['hire_week']=self.state['tick']//168;self.employee_log(e,'recruited','Hired '+hire['name']+' within explicit salary/headcount authority',hire['id'])
 def obligation_view(self,entity):
  w=self.state;debts={k:amt(-D(v)) for k,v in w['balances'].items() if k.startswith('debt:'+entity+':') and D(v)<0};upcoming=[]
  for e in self.staff(entity):
   if e['payroll_next']<=w['tick']+168:upcoming.append(dict(kind='PAYROLL',reference=e['id'],due=e['payroll_next'],amount=amt(max(D(e['salary']),D(e['unpaid'])))))
  for asset in w.get('owned_assets',[]):
   if asset['owner']==entity and asset['status']!='SOLD' and asset['cost_next']<=w['tick']+168:upcoming.append(dict(kind='ASSET OPERATIONS',reference=asset['id'],due=asset['cost_next'],amount=asset['monthly_cost']))
  for employee in w['employees']:
   if employee['entity']==entity and employee['status']!='EMPLOYED' and D(employee['unpaid'])>0:upcoming.append(dict(kind='EMPLOYEE CREDITOR',reference=employee['id'],due=w['tick'],amount=employee['unpaid']))
  for request in w.get('redemptions',[]):
   if request['fund']==entity and D(request['remaining'])>0 and request.get('eligible_tick',w['tick'])<=w['tick']+168:upcoming.append(dict(kind='FUND REDEMPTION',reference=request['id'],due=request.get('eligible_tick',w['tick']),amount=request['remaining']))
  for asset in w.get('owned_assets',[]):
   if asset['owner']==entity and D(asset['unpaid'])>0:upcoming.append(dict(kind='ASSET ARREARS',reference=asset['id'],due=w['tick'],amount=asset['unpaid']))
  for loan in w['loans']:
   if loan['account']==entity and D(loan['balance'])>0 and loan.get('next_due',w['tick']+999)<=w['tick']+168:upcoming.append(dict(kind='LOAN INSTALMENT',reference=loan['id'],due=loan['next_due'],amount=amt(min(D(loan['balance']),D(loan.get('payment',loan['balance']))))))
  for claim in w['claims_book']:
   if claim['debtor']==entity and D(claim['balance'])>0 and claim['due']<=w['tick']+168:upcoming.append(dict(kind='CREDITOR CLAIM',reference=claim['id'],due=claim['due'],amount=claim['balance']))
  for programme in w.get('investment_programmes',[]):
   if programme['entity']==entity and not programme.get('claims_converted'):
    for investor,row in programme['investors'].items():
     if D(row['requested'])>0:upcoming.append(dict(kind='PROGRAMME WITHDRAWAL',reference=programme['id']+':'+investor,due=w['tick'],amount=row['requested']))
  for key,value in debts.items():
   if ':legal_' in key or key.endswith((':operations',':business',':compliance')):upcoming.append(dict(kind='OPERATING ARREARS',reference=key,due=w['tick'],amount=value))
  return dict(recorded_debts=debts,upcoming=upcoming,due_week=amt(sum((D(x['amount']) for x in upcoming),D(0))))
 def executive_view(self):
  w=self.state;accounts=self.controlled_accounts();latest={}
  for r in w['employee_reports']:
   if r['entity'] in accounts:latest[(r['entity'],r['employee'])]=r
  return dict(investor_requests=[dict(activity=a['id'],**r) for a in w['social_events'] if a['status']=='COMPLETED' for r in a.get('business_requests',[])][-30:]+[dict(kind='REDEMPTION',fund=r['fund'],investor=r['investor'],remaining=r['remaining'],reference=r['id']) for r in w.get('redemptions',[]) if D(r['remaining'])>0],recommendations=[r for r in w['staff_recommendations'] if r['entity'] in accounts and (r['status']=='PENDING' or r['status']=='ASSIGNED' and any(t['id']==r.get('task') and t['status']=='AWAITING APPROVAL' for t in w['employee_tasks']))],departments=[dict(employee=e['id'],name=e['name'],entity=e['entity'],role=e['role'],authority=e.get('department_policy',{}),morale=e.get('morale',70),stress=e.get('stress',0),loyalty=e.get('loyalty'),ambition=e.get('ambition'),integrity=e.get('integrity')) for e in w['employees'] if e['status']=='EMPLOYED' and e['entity'] in accounts],briefings=list(latest.values()),obligations={a:self.obligation_view(a) for a in accounts},cases=[c for c in w['legal_cases'] if c['entity'] in accounts and c['stage']!='CLOSED'],activities=[a for a in w['social_events'] if a['status']=='SCHEDULED'],internal_reviews=w['internal_reviews'][-30:],news=w['news'][:8])

 def mandate_allows(self,policy,symbol):
  ins=self.state['instruments'].get(symbol,{})
  if symbol not in self.state.get('market_symbols',[]) and policy.get('universe')=='market':return False
  return (policy.get('universe')=='market' or symbol in policy.get('symbols',[]) or ('universe' not in policy and not policy.get('symbols'))) and (not policy.get('sectors') or ins.get('sector') in policy['sectors']) and (not policy.get('countries') or ins.get('market_country',ins.get('country',ins.get('listing_country'))) in policy['countries'])

 def portfolio_screen(self,e):
  """Once per research cycle: rank public observations, then use existing research/tasks."""
  policy=e['department_policy'];w=self.state
  research_team=e['role']=='analyst' and w.get('auto_teams',{}).get(e['entity'],{}).get('enabled')
  if policy.get('universe')!='market' or policy['level']<2 or (not research_team and not e['delegation']['trade']):return
  analysts=[person for person in self.staff(e['entity']) if person['role']=='analyst' and person.get('department_policy',{}).get('universe')=='market' and person.get('department_policy',{}).get('level',1)>=2]
  if not research_team and w.get('auto_teams',{}).get(e['entity'],{}).get('enabled') and analysts:
   shared=[r for r in w['stock_research'] if r['entity']==e['entity'] and 0<=w['tick']-r['tick']<=48 and self.current_research(r)]
   e['last_screen']=dict(tick=w['tick'],time=w['time'],status='Using shared analyst research',selected=[r['symbol'] for r in shared][-3:])
   weak=next((r for r in reversed(shared) if r['analyst']!=e['id'] and r['confidence']<60 and e['competence']>=60 and e['competence']>r['confidence'] and r['evidence']['fundamentals'].get('profit') is not None),None)
   if weak and not any(r['analyst']==e['id'] and w['tick']-r['tick']<24 for r in shared):
    from .engine import uid
    second=self.complete_analysis(e,dict(id=uid(),instruction={'symbol':weak['symbol']}));second['peer_review_of']=weak['id'];second['origin']='Trader second opinion on low-confidence shared analyst research'
   return
  cache=getattr(self,'_opportunity_cache',None)
  if not cache or cache[0]!=w['tick'] or cache[1]!=w['id']:
   quotes={};features=[]
   for order in w['orders']:
    if order['status'] not in ('OPEN','PARTIAL') or order['type']!='limit':continue
    q=quotes.setdefault(order['symbol'],{'buy':[],'sell':[]});q[order['side']].append(float(order['limit']))
   for symbol in w.get('market_symbols',[]):
    ins=self.instrument(symbol)
    if ins.get('status')!='OPEN':continue
    price=float(ins['price']);f,source=self.research_fundamentals(symbol,include_debt=False);shares=float(f.get('shares') or 0);profit=float(f.get('profit') or 0)*float(ins.get('public_earnings_factor','1'));revenue=float(f.get('revenue') or 0)
    bars=[b for b in ins.get('history',[]) if 0<=b.get('t',-1)<=w['tick']][-120:];closes=[float(b['c']) for b in bars if float(b['c'])>0]
    trend=self.observed_equity_trend(symbol);momentum=trend['return_fraction'];quality=profit/revenue if revenue else 0;value=(profit/shares*18/price-1) if shares>0 and profit>0 else -.5
    volume=sum(float(b.get('v',0)) for b in bars[-24:]);q=quotes.get(symbol,{});bid=max(q.get('buy',[]) or [0]);ask=min(q.get('sell',[]) or [0]);spread=(ask-bid)/price*10000 if bid and ask else (float(ins.get('spread_bps',25)) if not w.get('microstructure_enabled') else 1e9)
    features.append(dict(symbol=symbol,trend_strength=trend['trend_strength'],above_average=trend['above_recent_average'],enough_history=trend['enough_history'],value=max(-1,min(1,value)),quality=max(-1,min(1,quality)),momentum=max(-1,min(1,momentum)),income=float(f.get('annual_dividend_per_share') or 0)/price,volume=volume,spread=spread,price=price))
   cache=(w['tick'],w['id'],features);self._opportunity_cache=cache
  weights={'value':(.8,.2,0),'growth':(.2,.4,.4),'quality':(.2,.7,.1),'momentum':(.2,.2,.6),'income':(.4,.5,.1),'blended':(.5,.3,.2)}[policy.get('strategy','blended')]
  ranked=[]
  live_policy=self.team_policy(e);equity=max(D(0),D(self.metrics(e['entity'])['equity']));sectors=self.team_sector_exposure(e['entity'])
  for row in cache[2]:
   if policy.get('strategy')=='income' and row['income']<=0:continue
   if not self.mandate_allows(policy,row['symbol']) or row['spread']>float(policy.get('max_spread_bps',100)) or row['volume']<float(policy.get('min_volume',0)):continue
   if w.get('auto_teams',{}).get(e['entity'],{}).get('enabled') and sectors.get(self.instrument(row['symbol']).get('sector'),D(0))>=equity*D(live_policy.get('max_sector_pct','100'))/100:continue
   score=sum(row[k]*weight for k,weight in zip(('value','quality','momentum'),weights))-row['spread']/10000
   if policy.get('strategy')=='income':score+=row['income']
   if policy.get('strategy')=='momentum':score=.6*row['momentum']+.3*max(-1,min(1,row['trend_strength']/3))+.1*row['above_average']-row['spread']/10000 if row['enough_history'] else -1
   row=dict(row);review=w.get('auto_teams',{}).get(e['entity'],{}).get('risk_review');sector=self.instrument(row['symbol']).get('sector');row['diversification_advice']=float(sectors.get(sector,D(0))/equity)*{'careful':.025,'balanced':.015,'adventurous':.005}.get(w.get('auto_teams',{}).get(e['entity'],{}).get('mode'),0) if equity and review and w['tick']-review['tick']<=48 else 0
   ranked.append((score,row))
  ranked.sort(key=lambda x:(-(x[0]-x[1].get('diversification_advice',0)),x[1]['symbol']))
  # Include held names for exit research, never just the strongest recent winner.
  held=[p['symbol'] for p in w['positions'].values() if p['account']==e['entity'] and self.mandate_allows(policy,p['symbol'])]
  offset=(w['tick']//24*2)%len(held) if held else 0
  rotated=held[offset:]+held[:offset]
  candidates=list(dict.fromkeys(rotated[:2]+[r['symbol'] for score,r in ranked if score>0 and r['symbol'] not in held]+rotated[2:]))
  if research_team:
   candidates=list(dict.fromkeys(candidates+[r['symbol'] for score,r in ranked]))
   fresh={r['symbol'] for r in w['stock_research'] if r['entity']==e['entity'] and w['tick']-r['tick']<24 and self.current_research(r)}
   candidates=[symbol for symbol in candidates if symbol not in fresh]
  # Two strongest/held candidates plus one rotating research candidate prevents
  # repeatedly publishing the same rejected valuation on only three securities.
  if research_team and len(candidates)>3:
   explore=candidates[2+(w['tick']//24)%max(1,len(candidates)-2)];candidates=list(dict.fromkeys(candidates[:2]+[explore]+candidates[2:]))
  choices=candidates[:3]
  if research_team and not choices:w.get('auto_teams',{}).get(e['entity'],{})['activity']='Research is current; no new evidence warrants another report'
  e['last_screen']=dict(tick=w['tick'],time=w['time'],eligible=len(ranked),strategy=policy.get('strategy','blended'),selected=choices,status='Researching' if choices else 'No justified opportunity',reason='Valuation, profitability, liquidity or allocation filters did not justify an investment' if not choices else 'Comparing public evidence',ranking=[dict(score=round(score,6),**row) for score,row in ranked[:8]])
  for symbol in choices:
   if any(r['entity']==e['entity'] and r['symbol']==symbol and w['tick']-r['tick']<24 and self.current_research(r) for r in w['stock_research']):continue
   from .engine import uid
   report=self.complete_analysis(e,dict(id=uid(),instruction={'symbol':symbol}));report['origin']='Portfolio mandate screening';report['screen']=copy.deepcopy(e['last_screen'])

 def auto_team(self,p):
  """One explicit mandate for the existing employees of one legal employer."""
  entity=p['entity'];authority=self.employee_entity(entity);people=self.staff(entity)
  if self.is_frozen(entity):raise ValueError('This employer is restricted')
  mode=p.get('mode','balanced');presets={'careful':(10,30,20),'balanced':(20,50,10),'adventurous':(40,80,2)}
  teams=self.state.setdefault('auto_teams',{})
  if mode=='pause':
   team=teams.get(entity)
   if not team:raise ValueError('No automatic team has been configured')
   if not team['enabled']:return team
   team['paused_policies']={person['id']:copy.deepcopy(person['department_policy']) for person in people if person['id'] in team['members']}
   team['paused_delegations']={person['id']:copy.deepcopy(person['delegation']) for person in people if person['id'] in team['members']}
   team.update(enabled=False,status='Paused')
   for person in people:
    if person['id'] not in team['members'] or person['role'] not in ('trader','portfolio_manager'):continue
    self.staff_policy({'employee':person['id'],'level':1,'per_order':0,'daily':0})
   for task in self.state['employee_tasks']:
    if task['entity']==entity and task.get('mandate_owner') in team['members'] and task['status'] in ('QUEUED','AWAITING APPROVAL'):task.update(status='CANCELLED',result='Automatic team paused')
   for row in self.state.get('staff_recommendations',[]):
    if row['entity']==entity and row['employee'] in team['members'] and row['kind']=='trade' and row['status'] in ('PENDING','ASSIGNED'):row.update(status='CANCELLED',reason='Automatic team paused')
   self.audit('auto_team_paused',{'entity':entity});return team
  if mode=='resume':
   team=teams.get(entity)
   if not team or team.get('enabled'):raise ValueError('A paused team is required')
   if not any(person['role'] in ('trader','portfolio_manager') and person['id'] in team['members'] for person in people):raise ValueError('No assigned investment staff remain employed')
   for person in people:
    saved=team.get('paused_policies',{}).get(person['id'])
    if saved:
     delegate=team.get('paused_delegations',{}).get(person['id'],{})
     self.staff_policy(dict(saved,employee=person['id'],per_order=delegate.get('per_order',0),daily=delegate.get('daily',0)))
   team.update(enabled=True,status='Running');team['revisions']={person['id']:person['department_policy']['revision'] for person in people if person['id'] in team['members']};self.team_risk_review(entity,force=True);self.audit('auto_team_resumed',{'entity':entity});return team
  if mode not in presets:raise ValueError('Choose careful, balanced or adventurous')
  traders=[e for e in people if e['role'] in ('trader','portfolio_manager')]
  if not traders:raise ValueError('Hire a trader or portfolio manager at this employer first')
  equity=max(D(0),D(self.metrics(entity)['equity']));limit=equity if authority['kind']=='fund' else D(authority['payment_limit'])
  if limit<1 or equity<1:raise ValueError('The employer needs positive net assets and payment authority')
  position,sector,cash=presets[mode];capital=min(limit,equity*position/100);payroll=sum((D(e['salary']) for e in people),D(0));reserve=min(limit,payroll*2)
  if capital<1:raise ValueError('Insufficient capital for an automatic trading mandate')
  strategy=p.get('strategy','blended')
  members=[e['id'] for e in people if e['role'] in ('analyst','risk','operations','accountant','portfolio_manager','trader')]
  existing=teams.get(entity,{})
  if existing.get('enabled') and existing.get('mode')==mode and existing.get('strategy')==strategy and existing.get('members')==members and all(existing.get('revisions',{}).get(person['id'])==person.get('department_policy',{}).get('revision') for person in people if person['id'] in members):return existing
  teams[entity]=dict(existing,enabled=False,portfolio_authority=amt(limit))
  for person in people:
   if person['role'] not in ('analyst','risk','operations','accountant','portfolio_manager','trader'):continue
   self.staff_policy(dict(employee=person['id'],level=3 if person in traders else 2,universe='market',symbols=[],strategy=strategy,weekly_budget=0,capital_limit=amt(capital),cash_reserve=amt(reserve),per_order=amt(capital),daily=amt(limit),max_position_pct=position,max_sector_pct=sector,cash_target_pct=cash,sectors=[],countries=[]))
  manager=max((e for e in traders if e['role']=='portfolio_manager'),key=lambda e:e['competence'],default=None)
  if manager:
   # Preserve valid existing reporting lines; never create a reporting cycle.
   for trader in traders:
    if trader['role']=='trader' and not trader.get('manager'):self.employee_change({'employee':trader['id'],'kind':'manager','manager':manager['id']})
  team=dict(enabled=True,status='Running',mode=mode,strategy=strategy,members=[e['id'] for e in people if e['role'] in ('analyst','risk','operations','accountant','portfolio_manager','trader')],set_time=self.state['time'],max_position_pct=str(position),max_sector_pct=str(sector),cash_target_pct=str(cash),note='Uses existing employer cash; long-only. Two months of named salaries retained within payment authority. No hiring or extra operating spend authorised.')
  fund=next((fund for fund in self.state['funds'] if fund['id']==entity),None);team['start_nav_per_unit']=str(equity/D(fund['units'])) if fund and D(fund['units'])>0 else None
  team['portfolio_authority']=amt(limit);team['daily_limit']=amt(limit);team['revisions']={person['id']:person['department_policy']['revision'] for person in people if person['id'] in members}
  teams[entity]=team;self.team_risk_review(entity,force=True);self.audit('auto_team_started',{'entity':entity,'mode':mode,'members':team['members']});return team

 def team_risk_review(self,entity,force=False):
  team=self.state.get('auto_teams',{}).get(entity)
  if not team or not team['enabled']:return
  day=self.state['tick']//24
  managers=[e for e in self.staff(entity) if e['role']=='risk' and e['id'] in team['members']]
  if not managers:
   team.pop('risk_review',None);team['review_day']=day;return
  if not force and team.get('review_day')==day and team.get('risk_review',{}).get('version')==2:return
  import math,statistics
  employee=max(managers,key=lambda e:e['competence']);m=self.metrics(entity);equity=max(D(0),D(m['equity']));sectors=self.team_sector_exposure(entity);positions=[];bids={}
  for order in self.state['orders']:
   if order['status'] in ('OPEN','PARTIAL') and order['type']=='limit' and order['side']=='buy':bids[order['symbol']]=bids.get(order['symbol'],D(0))+D(order['remaining'])
  for pos in self.state['positions'].values():
   if pos['account']!=entity:continue
   ins=self.instrument(pos['symbol']);closes=[float(bar['c']) for bar in ins.get('history',[]) if 0<=bar.get('t',-1)<=self.state['tick']][-49:];changes=[math.log(y/x) for x,y in zip(closes,closes[1:]) if x>0 and y>0]
   positions.append(dict(symbol=pos['symbol'],shares=pos['qty'],displayed_bid_shares=str(bids.get(pos['symbol'],D(0))),observed_annualised_volatility=statistics.pstdev(changes)*math.sqrt(8760) if len(changes)>1 else None))
  largest=max(sectors.values(),default=D(0));share=largest/equity*100 if equity else D(0)
  assessment=('Largest sector is '+amt(share)+'% of net assets; prefer other attractive sectors when evidence is comparable.' if share>40 else 'No dominant sector identified; continue selecting investments on their merits.')
  team['risk_review']=dict(version=2,advisory=True,employee=employee['id'],name=employee['name'],tick=self.state['tick'],time=self.state['time'],equity=m['equity'],available_cash=m['available_cash'],sector_exposure={str(k):amt(v) for k,v in sectors.items()},positions=positions,redemptions_due=amt(self.team_redemptions(entity)),strategy=team['strategy'],risk_appetite=team['mode'],assessment=assessment+' Volatility alone does not change your limits or cash target.')
  if wfed:=self.state.get('fed'):
   team['risk_review']['treasury_dv01_gbp']=amt(sum((D(position['face'])/100*D(str(self.treasury_quote(self.state['treasury_securities'][position['security']])['dirty_price']))*self.fx_rate('USD')*D(str(self.treasury_quote(self.state['treasury_securities'][position['security']])['modified_duration']))*D('.0001') for position in self.state['treasury_positions'].values() if position['account']==entity),D(0)))
  team['review_day']=day;self.employee_log(employee,'team_risk_review',team['risk_review']['assessment'])

 def team_policy(self,employee):
  policy=employee.get('department_policy',{});team=self.state.get('auto_teams',{}).get(employee['entity'])
  if not team or not team['enabled'] or employee['id'] not in team['members']:return policy
  self.team_risk_review(employee['entity']);review=team.get('risk_review')
  policy=copy.deepcopy(policy)
  policy['cash_reserve']=str(max(D(policy.get('cash_reserve','0')),self.team_redemptions(employee['entity'])))
  return policy

 def staff_trading_limit(self,entity):
  team=self.state.get('auto_teams',{}).get(entity,{})
  return D(team.get('portfolio_authority',self.state['entities'][entity]['payment_limit']))

 def team_sector_exposure(self,entity):
  sectors={}
  for position in self.state['positions'].values():
   if position['account']!=entity:continue
   ins=self.instrument(position['symbol']);sector=ins.get('sector');sectors[sector]=sectors.get(sector,D(0))+abs(D(position['qty']))*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency'])
  return sectors

 def team_redemptions(self,entity):
  return sum((D(row['remaining']) for row in self.state.get('redemptions',[]) if row['fund']==entity and row.get('eligible_tick',self.state['tick'])<=self.state['tick']+168),D(0))

 def team_daily_spend(self,entity):
  day=self.state['tick']//24
  return sum((D(person.get('fill_spent','0')) for person in self.state['employees'] if person['entity']==entity and person.get('fill_day')==day),D(0))

 def manual_choice_applies(self,entity,symbol):
  row=self.state.get('auto_teams',{}).get(entity,{}).get('manual_choices',{}).get(symbol)
  if not row:return False
  ins=self.instrument(symbol)
  current=self.research_fundamentals(symbol)[0]
  for key in ('profit','revenue','debt','shares'):
   old=row['fundamentals'].get(key);now=current.get(key)
   if (old is None)!=(now is None):return False
   if old is not None and abs(D(str(now))-D(str(old)))>max(D(1),abs(D(str(old)))*D('.05')):return False
  return row['public_earnings_factor']==ins.get('public_earnings_factor','1') and abs(D(ins['price'])/D(row.get('price',ins['price']))-1)<=D('.1') and abs(D(str(row.get('macro_rate',self.state['macro']['rate'])))-D(str(self.state['macro']['rate'])))<D('.5')

 def team_pending_turnover(self,entity):
  total=D(0)
  for order in self.state['orders']:
   if order['account']!=entity or not order.get('employee') or order['status'] not in ('OPEN','PARTIAL','PAUSED'):continue
   ins=self.instrument(order['symbol']);notional=D(order['remaining'])*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins['currency']);total+=notional+max(D(1),(notional*D('.0005')).quantize(D('.01')))
  return total

 def prepare_team_submission(self,request,employee,task):
  team=self.state.get('auto_teams',{}).get(employee['entity'],{})
  if not team.get('enabled') or not task.get('recommendation') or task.get('approved'):return request
  policy=self.team_policy(employee);symbol=request['symbol'];ins=self.instrument(symbol);price=D(ins['price'])*self.fx_rate(ins['currency']);equity=max(D(0),D(self.metrics(employee['entity'])['equity']));held=D(self.state['positions'].get(employee['entity']+':'+symbol,{}).get('qty','0'));day=self.state['tick']//24
  daily=D(employee['delegation']['daily'])-(D(employee.get('fill_spent','0')) if employee.get('fill_day')==day else D(0));budget=min(D(employee['delegation']['per_order']),max(D(0),daily),max(D(0),D(team['daily_limit'])-self.team_daily_spend(employee['entity'])-self.team_pending_turnover(employee['entity'])))
  if request['side']=='buy':
   reserve=max(D(policy['cash_reserve']),equity*D(policy.get('cash_target_pct','0'))/100);budget=min(budget,max(D(0),self.available_cash(employee['entity'])-reserve),max(D(0),min(D(policy['capital_limit']),equity*D(policy.get('max_position_pct','100'))/100)-held*price),max(D(0),equity*D(policy.get('max_sector_pct','100'))/100-self.team_sector_exposure(employee['entity']).get(ins.get('sector'),D(0))))
  qty=min(int(request['qty']),max(0,int((budget-D(1))/(price*D('1.01')))))
  if task.get('target_quantity') is not None:
   target=D(str(task['target_quantity']));remaining=max(D(0),held-target) if request['side']=='sell' else max(D(0),target-held);qty=min(qty,int(remaining))
  if request['side']=='sell':qty=min(qty,max(0,int(held)))
  if qty<1:raise ValueError('No remaining cash or authorised allocation for this proposed trade')
  if qty<int(request['qty']):
   row=next(r for r in self.state['staff_recommendations'] if r['id']==task['recommendation']);row['evidence']['execution_resize']=dict(proposed=request['qty'],submitted=qty,reason='Resized to current cash, position, sector and shared trading authority; not an advisory veto')
  return dict(request,qty=qty)
