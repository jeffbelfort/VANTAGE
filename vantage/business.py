"""Operating decisions, fundraising, financing, scheduling and risk/scenarios."""
import copy,math
from decimal import Decimal as D
from datetime import datetime,timedelta
from .integrity import amt
from .execution import depth as model_depth

class BusinessMixin:
 def install_business(self):
  w=self.state
  if w.get('business_version'):return
  w.update(business_version=1,operating_plans={},fundraising_rounds=[],scheduled_instructions=[],session_calendar={'mode':'CONTINUOUS','open_hour':8,'close_hour':16,'closed_dates':[]},research_reports=[])
  w['paused']=True
  if w.get('market_generation_version')==2:
   self.institutional_investor_openings();self.audit('institutional_allocators_created',{'count':6,'cash_is_not_aum':True});return
  for i in range(4,12):
   id='lp'+str(i);n=dict(id=id,name=['Calder Family Office','Moorland Charitable Trust','North Quay Partners','Ellis Private Capital','Cedar Insurance Pool','Fenwick Foundation','Harbour Pension Reserve','Larch Wealth Partnership'][i-4],wealth=amt(1000000*(i-2)),trust=55+i,risk=.2+(i%4)*.15,horizon_days=30+(i%3)*30,liquidity_need=.02,withdrawal_sensitivity=.7,units={})
   w['npcs'].append(n);self.post('New investor opening endowment '+n['name'],{'npc:'+id+':cash':D(n['wealth']),'npc:'+id+':equity':-D(n['wealth'])})
  self.audit('business_programme_initialized',{'new_prospects':8,'existing_investors_unchanged':True,'calendar':'Configurable local simulation session, not an official exchange calendar'})
 def fund_class(self,p):
  """Independently funded class vehicle; no shared portfolio or equalisation claims."""
  self.authority(p['fund'],'govern');umbrella=next(f for f in self.state['funds'] if f['id']==p['fund'])
  if self.is_frozen(umbrella['id']):raise ValueError('Restricted mandates cannot establish new classes')
  if p.get('confirm')!='AUTHORIZE':raise ValueError('Explicit class funding and fee authorisation required')
  label=str(p.get('label','Institutional')).strip()[:40]
  if not label:raise ValueError('Share class name is required')
  if any(f.get('umbrella')==umbrella['id'] and f.get('class_label')==label for f in self.state['funds']):raise ValueError('Class name already exists in this umbrella')
  f=self.fund({'name':umbrella['name']+' / '+label,'amount':p['amount']})
  f.update(umbrella=umbrella['id'],class_label=label,class_structure='SEGREGATED VEHICLE',terms=copy.deepcopy(umbrella.get('terms',{})))
  f['terms']['share_class']=label
  self.compensation({'fund':f['id'],'management':p.get('management',0),'performance':p.get('performance',0),'monthly_salary':0,'confirm':'AUTHORIZE'})
  self.audit('segregated_class_established',{'umbrella':umbrella['id'],'class':f['id'],'seed_source':'personal','seed':str(p['amount']),'structure':'Independent cash, holdings, units, fees and liabilities; no pooled equalisation'})
  return f
 def operating_plan(self,p):
  entity=p['entity'];authority=self.authority(entity,'govern');staff=int(p.get('staff',0));research=D(str(p.get('research',0)));technology=D(str(p.get('technology',0)));salary=D(str(p.get('salary',0)))
  if not 0<=staff<=10000 or any(not v.is_finite() or not 0<=v<=D('1e9') for v in [research,technology,salary]):raise ValueError('Operating budget outside allowed range')
  if self.state.get('employee_version') and entity!='personal':staff=len(self.staff(entity))
  plan=dict(entity=entity,staff=staff,research=amt(research),technology=amt(technology),salary=amt(salary),monthly_payroll=amt(D(staff)*D(4000)),order_capacity=50+staff*10+int(technology/1000),fee_rate=str(max(D('.0002'),D('.0005')-min(D('.0003'),technology/D('1000000000')))),enabled=True)
  if self.state.get('employee_version') and entity!='personal':plan['monthly_payroll']=amt(sum((D(e['salary']) for e in self.staff(entity)),D(0)))
  if D(plan['monthly_payroll'])+research+technology+salary>D(authority['payment_limit']):raise ValueError('Operating commitment exceeds board-delegated authority')
  upfront=research+technology
  if self.is_frozen(entity) or self.available_cash(entity)<upfront:raise ValueError('Operating procurement lacks unrestricted funds')
  if upfront:self.post('Operating research and technology procurement',{'expense:business_setup:'+entity:upfront,'cash:'+entity:-upfront,'cash:operating_suppliers':upfront,'pnl:operating_suppliers':-upfront})
  self.state['operating_plans'][entity]=plan;self.audit('operating_plan',plan.copy());return plan
 def fundraising(self,p):
  from .engine import uid,positive
  fund=next(f for f in self.state['funds'] if f['id']==p['fund']);self.authority(fund['id'],'disclose');target=positive(p.get('target',1000000))
  if self.is_frozen(fund['id']):raise ValueError('Restricted funds cannot solicit new capital')
  if any(r['fund']==fund['id'] and self.state['tick']-r['tick']<168 for r in self.state['fundraising_rounds']):raise ValueError('Fundraising round cooling period is seven market days')
  m=self.metrics(fund['id']);verified=fund.get('verified');verified_recent=verified and (datetime.fromisoformat(self.state['time'])-datetime.fromisoformat(verified['time'])).total_seconds()<=30*86400;return_ratio=float((D(verified['nav'])-D(m['contributed']))/max(D(1),D(m['contributed']))) if verified_recent else float((D(fund['reported'])-D(m['contributed']))/max(D(1),D(m['contributed'])));regulatory=any(c['entity']==fund['id'] and c['stage'] not in ('CLOSED','PRELIMINARY') for c in self.state.get('legal_cases',[])) or any(c['fund']==fund['id'] and c['status'] in ('INQUIRY','ENFORCEMENT') for c in self.state['claims']);illiquid=bool(fund.get('suspended')) or float(fund.get('gate_daily_pct',100))<25
  round=dict(id=uid(),fund=fund['id'],tick=self.state['tick'],target=amt(target),raised='0.00',decisions=[],time=self.state['time'])
  for n in sorted(self.state['npcs'],key=lambda n:n['id']):
   if D(round['raised'])>=target:break
   score=n['trust']*.4+self.state['reputation']*.2+(20 if verified_recent else 0)+max(-30,min(20,return_ratio*100))-float(fund.get('management',0))*3-(25 if regulatory else 0)-(15 if illiquid else 0)-(float(m['drawdown'])*40 if verified_recent else 0)+float(self.state['macro'].get('confidence',65)-65)*.1
   amount=min(target-D(round['raised']),D(n['wealth'])*D('.05')).quantize(D('.01'));reason='Risk/return, fee or trust assessment below mandate'
   if score>=55 and amount>=D(fund.get('terms',{}).get('minimum','1')):
    try:
     self.subscribe({'fund':fund['id'],'investor':n['id'],'amount':amount});round['raised']=amt(D(round['raised'])+amount);reason='Accepted after suitability and liquidity checks';accepted=True
    except ValueError as exc:reason=str(exc);accepted=False
   else:accepted=False
   round['decisions'].append({'investor':n['id'],'score':round_float(score),'accepted':accepted,'amount':amt(amount) if accepted else '0.00','reason':reason})
  self.state['fundraising_rounds'].append(round);self.message('Capital Formation','Fundraising round completed',f"{fund['name']}: £{D(round['raised']):,.2f} raised from actual investor cash against £{target:,.2f} target. Decisions reference track record, verification, fees and restrictions.");self.audit('fundraising_round',round.copy());return round
 def financing(self,p):
  from .engine import positive
  kind=p['kind'];source=p['source'];symbol=p['symbol'];issuer=self.state['issuers'][symbol];borrower=issuer['account'];e=self.authority(source,'payment');amount=positive(p.get('amount',1))
  if self.is_frozen(source) or self.is_frozen(borrower):raise ValueError('Financing party is restricted')
  if kind in ('bond','secured_loan'):
   claim=self.network_credit({'source':source,'destination':borrower,'amount':amount,'rate':p.get('rate',7),'months':int(p.get('months',36))});claim['kind']='CORPORATE BOND' if kind=='bond' else 'SECURED CORPORATE CREDIT'
   if kind=='secured_loan':
    collateral=min(D(claim['balance']),self.cash(borrower));from .engine import uid
    id=uid();self.state['pledges'].append(dict(id=id,owner=borrower,beneficiary=source,amount=amt(collateral),status='ACTIVE'));claim['secured']=id;self.post('Corporate cash collateral pledged '+id,{'memo:pledge:'+borrower+':'+id:collateral,'memo:contra:'+borrower+':'+id:-collateral})
   return claim
  if kind=='equity':
   qty=int(p['qty']);ins=self.instrument(symbol);price=D(ins['price'])*self.fx_rate(ins['currency']);amount=(price*qty).quantize(D('.01'))
   register=self.state.get('share_register',{}).get(symbol)
   if register and D(issuer['model_shares'])+qty>D(register['authorised']):raise ValueError('Primary placement exceeds the model board-authorised share capital')
   self.validate_fund_control_purchase(source,symbol,D(self.state['positions'].get(source+':'+symbol,{}).get('qty',0))+qty,D(issuer['model_shares'])+qty)
   if qty<=0 or amount>self.available_cash(source) or amount>D(e['payment_limit']):raise ValueError('Placement exceeds available cash or board authority')
   entity=self.authority(source,'trade');sectors=entity['mandate'].get('sectors',[])
   if sectors and ins['sector'] not in sectors:raise ValueError('Placement is outside the investment mandate')
   limits=self.state.get('account_limits',{}).get(source,{});m=self.metrics(source)
   if D(m['gross'])+amount>D(m['liquid_equity'])*D(limits.get('max_leverage','2')):raise ValueError('Placement exceeds desk gross-exposure mandate')
   pos=self.state['positions'].get(source+':'+symbol,{'qty':'0','cost':'0'})
   if D(pos['qty'])<0:raise ValueError('Primary issuance cannot cover a borrowed position through this workflow')
   self.post('Model issuer primary equity placement '+symbol,{'cash:'+source:-amount,'inventory:'+source+':'+symbol:amount,'cash:'+borrower:amount,'equity:'+borrower:-amount});self.state['positions'][source+':'+symbol]=dict(account=source,symbol=symbol,qty=amt(D(pos['qty'])+qty),cost=amt(D(pos['cost'])+amount),borrowed='0');issuer['model_shares']+=qty
   if register:register['outstanding']=str(issuer['model_shares']);register['free_float']=str(D(register['free_float'])+qty)
   self.audit('public_equity_issued',{'symbol':symbol,'subscriber':source,'quantity':qty,'amount':amt(amount),'outstanding':issuer['model_shares']})
   self.market_event({'symbol':symbol,'kind':'guidance','severity':0});return {'kind':kind,'amount':amt(amount),'shares':qty}
  if kind=='refinance':
   old=next(c for c in self.state['claims_book'] if c['id']==p['claim'] and c['debtor']==borrower);a=D(old['balance']);m=self.metrics(borrower)
   if self.available_cash(source)<a or a>D(e['payment_limit']) or D(m['equity'])<=0:raise ValueError('Refinancing lacks authorised funds or borrower solvency')
   rate=D(str(p.get('rate',7)));months=int(p.get('months',12))
   if not rate.is_finite() or not 0<=rate<=100 or not 1<=months<=360:raise ValueError('Invalid refinancing terms')
   new=self.make_network_claim(source,borrower,a,str(rate),months,'Signed corporate refinancing');self.settle_claim_cash(old,a,'Retired refinanced obligation');self.audit('corporate_refinancing',{'old':old['id'],'new':new['id']});return new
  raise ValueError('Unsupported financing form')
 def restructure(self,p):
  c=next(c for c in self.state['claims_book'] if c['id']==p['id']);self.authority(c['creditor'],'govern')
  if self.is_frozen(c['creditor']):raise ValueError('Creditor assets are restricted')
  if c['kind']=='RECOVERY':raise ValueError('Recovery obligations require an actual repayment or administrator settlement, not an ordinary waiver')
  haircut=D(str(p.get('haircut',0)));rate=D(str(p.get('rate',c['rate'])));months=int(p.get('months',12))
  if not haircut.is_finite() or not 0<=haircut<=1 or not rate.is_finite() or not 0<=rate<=100 or not 1<=months<=360:raise ValueError('Invalid negotiated restructuring')
  if haircut>0 and self.is_fund(c['creditor']) and self.state['entities'].get(c['debtor'],{}).get('controlled'):raise ValueError('Fiduciary claims on controlled recipients cannot be waived through this workflow')
  amount=(D(c['balance'])*haircut).quantize(D('.01'));released=min(D(c['allowance']),amount)
  if amount:
   self.post('Creditor-approved debt restructuring '+c['id'],{'claim:'+c['creditor']+':'+c['id']:-amount,'allowance:'+c['creditor']+':'+c['id']:released,'expense:credit_loss:'+c['creditor']:amount-released,'debt:'+c['debtor']+':claim_'+c['id']:amount,'pnl:'+c['debtor']:-amount});c['balance']=amt(D(c['balance'])-amount);c['allowance']=amt(D(c['allowance'])-released)
  c['rate']=str(rate);c['due']=self.state['tick']+months*720;c['status']='REPAID' if D(c['balance'])==0 else 'ACTIVE';c.setdefault('restructurings',[]).append({'time':self.state['time'],'haircut':amt(amount),'rate':str(rate),'new_due':c['due']});self.audit('negotiated_restructuring',dict(p))
  if c['status']=='REPAID' and c.get('secured'):self.release_pledge({'id':c['secured']})
  return c
 def schedule_instruction(self,p):
  from .engine import uid
  action=p['action'];payload=copy.deepcopy(p['payload']);delay=int(p.get('delay',24));interval=int(p.get('interval',0));count=int(p.get('count',1))
  if action not in ('related','market_event','verify_nav','investor_response') or not 1<=delay<=8760 or not 1<=count<=1000 or (count>1 and interval<24):raise ValueError('Unsupported scheduled instruction or interval')
  if action=='related':self.authority(payload['source'],'payment',payload.get('actor','player'))
  job=dict(id=uid(),action=action,payload=payload,due=self.state['tick']+delay,interval=interval,remaining=count,status='QUEUED',receipts=[]);self.state['scheduled_instructions'].append(job);self.audit('instruction_scheduled',job.copy());return job
 def session_policy(self,p):
  mode=p.get('mode','CONTINUOUS');opening=int(p.get('open_hour',8));closing=int(p.get('close_hour',16));dates=list(p.get('closed_dates',[]))
  if mode not in ('CONTINUOUS','CUSTOM') or not 0<=opening<closing<=24:raise ValueError('Invalid configured session')
  dates=[datetime.strptime(day,'%Y-%m-%d').date().isoformat() for day in dates]
  self.state['session_calendar']={'mode':mode,'open_hour':opening,'close_hour':closing,'closed_dates':dates};self.audit('custom_session_policy',self.state['session_calendar']);return self.state['session_calendar']
 def session_open(self):
  policy=self.state.get('session_calendar',{});now=datetime.fromisoformat(self.state['time'])
  return policy.get('mode','CONTINUOUS')=='CONTINUOUS' or (now.weekday()<5 and now.date().isoformat() not in policy['closed_dates'] and policy['open_hour']<=now.hour<policy['close_hour'])
 def risk_report(self,p):
  from .engine import option_value,money
  account=self.account(p);self.authority(account,'disclose');shock=D(str(p.get('shock',-.2)));fxshock=D(str(p.get('fx_shock',0)))
  if not shock.is_finite() or not fxshock.is_finite() or not D('-.95')<=shock<=2 or not D('-.95')<=fxshock<=2:raise ValueError('Stress outside permitted range')
  rows=[];total=D(0);illiquid=D(0)
  for pos in self.state['positions'].values():
   if pos['account']!=account:continue
   ins=self.instrument(pos['symbol']);fx=self.fx_rate(ins.get('currency','GBP'));newfx=fx*(1+fxshock) if ins.get('currency')!='GBP' else fx;price=D(ins['price']);stressed=price*(1+shock)
   if pos['symbol'] in self.state['options']:
    o=self.state['options'][pos['symbol']];under=self.state['instruments'][o['underlying']];years=max(0,(datetime.fromisoformat(o['expiry'])-datetime.fromisoformat(self.state['time'])).total_seconds()/31536000);stressed=D(str(option_value(float(D(under['price'])*(1+shock)),float(o['strike']),years,under['vol'],self.state['macro']['rate']/100,o['kind'])['price']))
   mult=D(ins.get('multiplier',1));value=money(D(pos['qty'])*price*mult*fx);pnl=money(D(pos['qty'])*stressed*mult*newfx-value);total+=pnl;depth=self.book_depth(pos['symbol']) if pos['symbol'] in self.state.get('market_symbols',[]) else model_depth(ins,self.state['tick'])
   capacity=sum((D(r.get('bid_qty' if D(pos['qty'])>0 else 'ask_qty',r['qty'])) for r in depth),D(0));unmatched=max(D(0),abs(D(pos['qty']))-capacity);illiquid+=money(unmatched*price*mult*fx);rows.append({'symbol':pos['symbol'],'value':amt(value),'stress_pnl':amt(pnl),'unmatched_units':str(unmatched)})
  return {'account':account,'shock':str(shock),'fx_shock':str(fxshock),'stress_pnl':amt(total),'stressed_equity':amt(D(self.metrics(account)['equity'])+total),'liquidity_exposure':amt(illiquid),'positions':rows,'method':'Equity/FX shock; options repriced theoretically; excludes non-traded credit and entity-holding stress'}
 def business_tick(self):
  w=self.state
  for id in [j['id'] for j in w.get('scheduled_instructions',[])]:
   job=next(j for j in self.state['scheduled_instructions'] if j['id']==id)
   if job['status']!='QUEUED' or job['due']>w['tick']:continue
   key='instruction:'+job['id']+':'+str(job['due'])
   if self.db.execute('select 1 from scheduled_events where world=? and event=?',(w['id'],key)).fetchone():continue
   original=copy.deepcopy(self.state);id=job['id'];self.db.execute('SAVEPOINT scheduled_instruction')
   try:
    handlers={'related':self.related_instruction,'market_event':self.market_event,'verify_nav':self.verified_statement,'investor_response':self.investor_response};result=handlers[job['action']](job['payload']);self.db.execute('RELEASE scheduled_instruction');status='EXECUTED';reason=str(result.get('id',result.get('status','completed')))
   except (ValueError,KeyError) as exc:
    self.db.execute('ROLLBACK TO scheduled_instruction');self.db.execute('RELEASE scheduled_instruction');self.state.clear();self.state.update(original);job=next(j for j in self.state['scheduled_instructions'] if j['id']==id);status='FAILED';reason=str(exc)
   self.db.execute('insert into scheduled_events values(?,?,?)',(w['id'],key,w['time']));job['receipts'].append({'time':w['time'],'status':status,'reference':reason});job['remaining']-=1;job['status']='QUEUED' if status=='EXECUTED' and job['remaining']>0 else status
   if job['status']=='QUEUED':job['due']+=job['interval']
  if w['tick']%720==0:
   for account,plan in w.get('operating_plans',{}).items():
    total=(D(plan['monthly_payroll']) if account=='personal' or not w.get('employee_version') else D(0))+D(plan['research'])+D(plan['technology'])+D(plan['salary']);self.post('Monthly operating departments '+account,{'expense:business:'+account:total,'debt:'+account+':business':-total});paid=min(total,self.available_cash(account))
    if paid<total:plan['enabled']=False
    if paid and not self.is_frozen(account):self.post('Operating department settlement',{'cash:'+account:-paid,'debt:'+account+':business':paid,'cash:operating_suppliers':paid,'pnl:operating_suppliers':-paid})
    if D(plan['research'])>0:w['research_reports'].append({'time':w['time'],'entity':account,'outlook':w['macro'].copy(),'method':'Recorded model research, not external investment advice'})
 def create_scenario(self,p):
  name=p['scenario'];presets={'small_fund':('Professional Trader','500000'),'investment_bank':('Investment Bank Trader','20000000000'),'pension':('Investment Firm Founder','10000000'),'leveraged':('Professional Trader','500000'),'redemption_run':('Professional Trader','500000'),'investigation':('Professional Trader','500000'),'credit_shock':('Professional Trader','500000'),'short_squeeze':('Professional Trader','500000')}
  if name not in presets:raise ValueError('Unknown scenario')
  career,capital=presets[name];result=self.create({'name':p.get('name',name.replace('_',' ').title()),'career':career,'capital':capital,'seed':int(p.get('seed',42))});self.state['paused']=False
  if name in ('small_fund','redemption_run'):
   f=self.fund({'amount':100000,'name':'Scenario investment mandate'});f['lock_until']=0;self.subscribe({'fund':f['id'],'investor':'lp0','amount':100000})
   if name=='redemption_run':
    self.subscribe({'fund':f['id'],'investor':'lp1','amount':100000});self.order({'account':f['id'],'symbol':'NVDA','qty':1000});self.fund_policy({'fund':f['id'],'auto_liquidate':True});self.redemption_request({'fund':f['id'],'investor':'lp0','units':100000});self.redemption_request({'fund':f['id'],'investor':'lp1','units':100000})
  if name=='pension':self.state.setdefault('account_limits',{})['book']={'max_leverage':'1','single_name_pct':'25'}
  if name=='leveraged':self.order({'account':'personal','symbol':'NVDA','qty':4000,'margin':True})
  if name=='investigation':
   c=self.entity_create({'name':'Scenario services company','capital':100000});r=self.related_instruction({'source':c['id'],'destination':'personal','kind':'service','amount':10000,'fair_value':0,'mode':'override','disclosed':True});case=self.complaint({'entity':c['id'],'reference':r['id'],'reason':'Disputed affiliated expenditure'});self.respond_case({'id':case['id'],'response':'provide_records'})
  if name=='credit_shock':
   issuer=self.state['issuers']['NVDA'];self.issuer_event({'symbol':'NVDA','kind':'liability_shock','amount':str(self.cash(issuer['account'])*2)})
  if name=='short_squeeze':
   self.order({'account':'personal','symbol':'NVDA','side':'sell','qty':5000,'margin':True});self.market_event({'symbol':'NVDA','kind':'earnings','severity':-.08});self.market_event({'symbol':'NVDA','kind':'correction','severity':.5,'delay_hours':24})
  self.state['paused']=True;self.audit('scenario_initialized',{'scenario':name,'seed':self.state['seed'],'balanced':self.reconcile()['balanced']});return result

def round_float(value):return round(float(value),3)
