"""Additive living-world activities; all money goes through the existing journal."""
import random,json
from decimal import Decimal as D
from .integrity import amt

class LivingWorldMixin:
 def install_living_world(self):
  if self.state.get('living_world_version'):
   self.install_phase_two();return
  w=self.state
  w.update(living_world_version=1,insiders=[],intelligence=[],social_events=[],world_coverage={},personal_reputation=dict(prominence=0,credibility=50,prestige=0,controversy=0),social_relationships={})
  # Fixed fictional contacts, never an unbounded NPC generator.
  for i,symbol in enumerate(w.get('market_symbols',list(w['instruments']))[:8]):
   w['insiders'].append(dict(id='contact_'+str(i),name=['Morgan Vale','Robin Ash','Taylor Reed','Casey Ward'][i%4]+' '+str(i+1),symbol=symbol,role=['Finance director','Corporate adviser','Product executive','Board member'][i%4],access=40+i*7,reliability=55+i*5,willingness=0 if i==0 else 40+i*6,motivation='Career protection' if i==0 else 'Compensation',relationship=0,next_approach=0))
  w['corporate_calendar_due']=w['tick']+24
  self.audit('living_world_installed',{'historical_accounts_unchanged':True});self.install_phase_two()
 def world_article(self,key,title,paragraphs,publication,entities):
  w=self.state
  if key in w['world_coverage']:return
  w['world_coverage'][key]=w['tick']
  self.news(title,'\n\n'.join(paragraphs),'SOCIETY' if publication=='City After Hours' else 'FINANCIAL CRIME' if 'case:' in key else 'BUSINESS')
  w['news'][0].update(publication=publication,entities=entities,source=publication+' / fictional simulation desk')
 def insider_approach(self,p):
  from .engine import uid
  w=self.state;c=next((c for c in w['insiders'] if c['id']==p['contact']),None)
  if not c:raise ValueError('Unknown contact')
  owner=p.get('account','personal');entity=self.authority(owner,'payment');fee=D(str(p.get('amount',1000)))
  if not fee.is_finite() or not 1000<=fee<=100000 or fee!=fee.quantize(D('.01')):raise ValueError('Offer must be £1,000–£100,000')
  if self.is_frozen(owner) or fee>self.available_cash(owner) or fee>D(entity['payment_limit']):raise ValueError('Insufficient cash or payment authority')
  if w['tick']<c['next_approach']:raise ValueError('Contact unavailable for seven simulation days')
  c['next_approach']=w['tick']+168
  rng=random.Random(c['id']+str(w['tick'])+str(w['seed']))
  accepted=c['willingness']>0 and rng.randrange(100)<min(95,c['willingness']+int(fee/5000)+c['relationship'])
  tip=dict(execution_after=self.db.execute('select coalesce(max(rowid),0) from executions where world=?',(w['id'],)).fetchone()[0],prior_orders=[o['id'] for o in w['orders'] if o['account']==owner and o.get('tick')==w['tick']],id=uid(),contact=c['id'],account=owner,tick=w['tick'],time=w['time'],status='REFUSED',event=None,fee='0.00',assessment='Contact refused the approach.',case=None)
  if accepted:
   self.post('Confidential consultancy payment: '+c['name'],{'cash:'+owner:-fee,'expense:intelligence:'+owner:fee,'cash:'+c['id']:fee,'pnl:'+c['id']:-fee})
   tip['fee']=amt(fee);c['relationship']=min(30,c['relationship']+3)
   events=[e for e in w['events'] if e['symbol']==c['symbol'] and not e['published'] and e['publish_tick']>w['tick'] and e['kind'] in ('earnings','guidance','credit','acquisition','product')]
   if events and rng.randrange(100)<c['access']:
    event=min(events,key=lambda e:e['publish_tick']);correct=rng.randrange(100)<c['reliability'];direction=event['severity'] if correct else -event['severity']
    tip.update(status='CONFIDENTIAL',event=event['id'],symbol=event['symbol'],publish_tick=event['publish_tick'],assessment=('Improving' if direction>0 else 'Deteriorating')+' outlook indicated; magnitude and market reaction unknown. Source may be wrong.')
   else:tip.update(status='NO USEFUL INFORMATION',assessment='Payment made, but contact supplied no actionable scheduled information.')
  w['intelligence'].append(tip);self.audit('insider_approach',tip.copy());return tip
 def lifestyle_host(self,p):
  from .engine import uid
  w=self.state;a=next((a for a in w.get('owned_assets',[]) if a['id']==p['asset'] and a['status']=='OWNED'),None)
  if not a:raise ValueError('Owned asset required')
  self.lifestyle_authority(a['owner'])
  if a['category'] not in ('Yachts','Residential property','Aircraft','Vehicles','Art and collectibles','Collectibles','Watches and jewellery'):raise ValueError('Asset does not support private activities')
  if D(a['unpaid'])>0:raise ValueError('Settle asset operating arrears before hosting')
  if w['tick']<a.get('hosting_next',0):raise ValueError('Allow seven simulation days between activities')
  if any(c['asset']==a['id'] and c['status']=='ACTIVE' for c in w.get('property_contracts',[])):raise ValueError('Tenanted property is unavailable for hosting')
  guests=list(dict.fromkeys(p.get('guests',[])))
  if not 1<=len(guests)<=min(8,max(1,int(D(a['purchase_price'])/100000))):raise ValueError('Choose guests within the asset capacity (1–8)')
  npcs={n['id']:n for n in w['npcs']};employees={e['id']:e for e in w['employees'] if e['status']=='EMPLOYED' and e['entity'] in self.controlled_accounts()}
  if any(g not in npcs and g not in employees for g in guests):raise ValueError('Guest must be an existing investor or controlled employee')
  cost=max(D(250),D(a['monthly_cost'])*D('.1'))+D(250)*len(guests);owner=a['owner']
  if cost>self.available_cash(owner) or cost>D(self.authority(owner,'payment')['payment_limit']):raise ValueError('Activity exceeds available cash or authority')
  self.post('Private activity: '+a['name'],{'cash:'+owner:-cost,'expense:hosting:'+owner:cost,'cash:lifestyle_suppliers':cost,'pnl:lifestyle_suppliers':-cost})
  event=dict(id=uid(),asset=a['id'],owner=owner,guests=guests,cost=amt(cost),time=w['time'],tick=w['tick'],status='COMPLETED',outcomes=[])
  for guest in guests:
   relation=w['social_relationships'].setdefault(guest,{'meetings':0,'rapport':0});relation['meetings']+=1
   gain=max(0,5-relation['meetings']//3);relation['rapport']=min(40,relation['rapport']+gain)
   if guest in npcs:
    n=npcs[guest];n['trust']=min(100,n['trust']+min(2,gain));event['outcomes'].append(n['name']+': investor trust +'+str(min(2,gain)))
   else:
    e=employees[guest];distress=self.available_cash(e['entity'])<D(e['salary'])*2 or D(e['unpaid'])>D(e['salary']);e['morale']=max(0,min(100,e.get('morale',70)+(-8 if distress else 4)));event['outcomes'].append(e['name']+': morale '+str(e['morale']))
  a['hosting_next']=w['tick']+168;w['social_events'].append(event)
  rep=w['personal_reputation'];rep['prominence']=min(100,rep['prominence']+2);rep['prestige']=min(100,rep['prestige']+1)
  self.world_article('social:'+event['id'],a['name']+' hosts a private reception',[f"The owner of {a['name']} hosted {len(guests)} invited investors and associates. The activity cost £{cost:,.2f} in the local simulation.",f"The asset carries monthly operating commitments of £{D(a['monthly_cost']):,.2f}. Guests gained time with their host; attendance does not constitute an investment commitment."],'City After Hours',[owner,a['id']])
  self.audit('lifestyle_activity',event.copy());return event
 def staff_research_policy(self,p):
  e=next((e for e in self.state['employees'] if e['id']==p['employee'] and e['status']=='EMPLOYED'),None)
  if not e or e['role']!='analyst':raise ValueError('Active analyst required')
  self.employee_entity(e['entity']);symbol=p['symbol'];self.instrument(symbol)
  if symbol not in self.state['instruments'] or symbol in self.state['options']:raise ValueError('Underlying security required')
  e['research_policy']={'symbol':symbol,'enabled':bool(p.get('enabled',True)),'next':self.state['tick']+1};return e['research_policy']
 def living_world_tick(self):
  w=self.state
  if not w.get('living_world_version'):return
  self.phase_two_tick();self.programme_tick()
  # Maintain at most one pending event per covered issuer, without retroactive events.
  if w['tick']>=w['corporate_calendar_due']:
   w['corporate_calendar_due']=w['tick']+168
   for c in w['insiders']:
    if any(not e['published'] and e['symbol']==c['symbol'] for e in w['events']):continue
    rng=random.Random(str(w['seed'])+c['symbol']+str(w['tick']//168))
    self.market_event(dict(symbol=c['symbol'],kind=rng.choice(['earnings','earnings','guidance','acquisition','product']),severity=rng.uniform(-.12,.12),delay_hours=120+rng.randrange(49)))
  for e in w['employees']:
   policy=e.get('research_policy',{})
   if e['status']!='EMPLOYED' or not policy.get('enabled') or w['tick']<policy['next']:continue
   policy['next']=w['tick']+168
   if self.is_frozen(e['entity']):continue
   try:self.request_analysis({'entity':e['entity'],'analyst':e['id'],'symbol':policy['symbol']})
   except ValueError as exc:self.employee_log(e,'research_deferred',str(exc))
  # Surveillance waits for public disclosure AND matching recorded pre-event orders.
  for tip in w['intelligence']:
   if tip['status']!='CONFIDENTIAL' or tip.get('case') or tip.get('surveillance_reviewed'):continue
   event=next((v for v in w['events'] if v['id']==tip['event']),None)
   if not event or not event['published'] or w['tick']<event['publish_tick']+24:continue
   tip['surveillance_reviewed']=w['time']
   current={o['id']:o for o in w['orders'] if o['account']==tip['account']};orders={};executions=[]
   for row in self.db.execute("select data from executions where world=? and json_extract(data,'$.account')=? and rowid>?",(w['id'],tip['account'],tip.get('execution_after',0))):
    fill=json.loads(row[0]);symbol=fill['symbol']
    if not tip['time']<=fill['time']<event['publication_time'] or fill['order'] in tip.get('prior_orders',[]):continue
    if symbol!=tip['symbol'] and w['options'].get(symbol,{}).get('underlying')!=tip['symbol']:continue
    order=current.get(fill['order'])
    if not order:
     archived=self.db.execute('select data from order_archive where id=? and world=?',(fill['order'],w['id'])).fetchone();order=json.loads(archived[0]) if archived else None
    if not order or not tip['tick']<=order.get('tick',-1)<event['publish_tick']:continue
    orders[order['id']]=order;executions.append(fill)
   if not executions:continue
   reference=tip['id'];exposure=sum((D(f['consideration_gbp']) for f in executions),D(0));r=dict(id=reference,source=tip['account'],destination=tip['contact'],kind='insider_dealing',amount=amt(exposure),fair_value='0.00',classification='MISCONDUCT ALLEGATION',reasons=['Paid confidential access followed by pre-announcement executions; intent and causation require review'],actor='player',status='SETTLED',time=w['time'],tick=w['tick'],disclosed=False,settlements=[],observed=w['time'])
   w['related_transactions'].append(r)
   case=self.complaint({'entity':tip['account'],'reference':reference,'reason':'Exchange review: paid access and executed orders ahead of '+tip['symbol']+' disclosure'})
   case['evidence'].append(self.evidence('SURVEILLANCE',reference,'Event '+event['id']+'; orders '+', '.join(orders),tip['account'],tip['fee']));case['living_world_case']=True;case['reviewed_transactions'].append(reference);tip['case']=case['id']
   for e in self.staff(tip['account']):
    if e['role']=='compliance':self.employee_log(e,'concern_raised','Pre-announcement executions referred to case '+case['id'],reference)
  for case in w['legal_cases']:
   if case['stage'] not in ('FORMAL INVESTIGATION','ENFORCEMENT','CIVIL RECOVERY','PROSECUTION REFERRAL'):continue
   if case.get('living_world_case') and not case.get('legal_cost_assessed'):
    cost=D(5000 if any(e['role']=='legal' for e in self.staff(case['entity'])) else 10000);case['legal_cost_assessed']=amt(cost);case['legal_cost_unpaid']=amt(cost)
    self.post('External legal costs: '+case['id'],{'expense:legal:'+case['entity']:cost,'debt:'+case['entity']+':legal_'+case['id']:-cost})
   if D(case.get('legal_cost_unpaid','0'))>0 and not self.is_frozen(case['entity']):
    paid=min(D(case['legal_cost_unpaid']),max(D(0),self.available_cash(case['entity'])))
    if paid:
     self.post('Legal cost settlement: '+case['id'],{'cash:'+case['entity']:-paid,'debt:'+case['entity']+':legal_'+case['id']:paid,'cash:legal_suppliers':paid,'pnl:legal_suppliers':-paid});case['legal_cost_unpaid']=amt(D(case['legal_cost_unpaid'])-paid)
   key='case:'+case['id']+case['stage']
   if key not in w['world_coverage']:
    rep=w['personal_reputation'];rep['controversy']=min(100,rep['controversy']+5);rep['credibility']=max(0,rep['credibility']-3)
    for npc in w['npcs']:
     fund=next((f for f in w['funds'] if f['id']==case['entity']),None)
     if fund and npc['id'] in fund['investors']:npc['trust']=max(0,npc['trust']-2)
   self.world_article(key,w['entities'][case['entity']]['name']+': '+case['stage'].lower(),[f"The fictional Financial Conduct Office has reached {case['stage'].lower()} in case {case['id']}. The institution is {w['entities'][case['entity']]['name']}.",f"The authority has recorded {len(case['evidence'])} evidence references. A referral or allegation does not establish guilt; investor claims and the institution's actual ledger remain in force."],'The Financial Record',[case['entity']])
 def programme_create(self,p):
  from .engine import uid
  entity=p['entity'];e=self.authority(entity,'govern');rate=D(str(p.get('annual_return',30)))
  if e['kind'] in ('personal','fund') or self.is_frozen(entity):raise ValueError('Use a controlled unrestricted company, separate from fund investor assets')
  if not rate.is_finite() or not 0<=rate<=200:raise ValueError('Promised annual return must be 0–200 percent')
  programmes=self.state.setdefault('investment_programmes',[])
  if any(v['entity']==entity and v['status']=='OPEN' for v in programmes):raise ValueError('Company already operates a programme')
  v=dict(id=uid(),entity=entity,name=str(p.get('name','Fixed-return investment programme'))[:80],annual_return=str(rate),status='OPEN',created=self.state['time'],next_accrual=self.state['tick']+720,investors={},complaint=None)
  programmes.append(v);self.audit('programme_created',v.copy())
  self.world_article('programme:'+v['id'],e['name']+' markets a fixed-return programme',[f"{e['name']} has opened {v['name']}, promising {rate}% annually in the fictional economy.","Subscriptions are company liabilities, separate from equity and from genuine trading income. The promise does not ensure that assets will earn enough to pay investors."],'The Financial Record',[entity]);return v
 def programme_subscribe(self,p):
  v=next(v for v in self.state.get('investment_programmes',[]) if v['id']==p['programme']);self.authority(v['entity'],'govern')
  npc=next(n for n in self.state['npcs'] if n['id']==p['investor']);amount=D(str(p['amount']));w=self.state
  if not amount.is_finite() or amount<=0 or amount!=amount.quantize(D('.01')):raise ValueError('Positive whole-penny subscription required')
  if v['status']!='OPEN' or self.is_frozen(v['entity']) or v['complaint'] or npc['trust']<45:raise ValueError('Programme or investor unavailable')
  r=v['investors'].setdefault(npc['id'],dict(principal='0.00',balance='0.00',requested='0.00',paid='0.00',next_offer=0,arrears_since=None,last_accrual=w['tick']))
  if w['tick']<r['next_offer']:raise ValueError('Investor allocation reviewed only once per simulation week')
  if amount>min(D(npc['wealth'])*D('.1'),self.balance('npc:'+npc['id']+':cash')):raise ValueError('Investor allocation exceeds finite available cash or 10% suitability cap')
  self.programme_accrue(v,npc['id'],r)
  self.post('Investment programme subscription '+v['id'],{'npc:'+npc['id']+':cash':-amount,'npc:'+npc['id']+':programme:'+v['id']:amount,'cash:'+v['entity']:amount,'debt:'+v['entity']+':programme_'+v['id']:-amount})
  npc['wealth']=amt(D(npc['wealth'])-amount);r['principal']=amt(D(r['principal'])+amount);r['balance']=amt(D(r['balance'])+amount);r['next_offer']=w['tick']+168;self.audit('programme_subscription',dict(programme=v['id'],investor=npc['id'],amount=amt(amount)));return r
 def programme_redeem(self,p):
  v=next(v for v in self.state.get('investment_programmes',[]) if v['id']==p['programme']);self.authority(v['entity'],'govern');r=v['investors'][p['investor']]
  self.programme_accrue(v,p['investor'],r)
  r['requested']=r['balance'];return r
 def programme_tick(self):
  w=self.state
  for v in w.get('investment_programmes',[]):
   if v.get('claims_converted'):continue
   entity=v['entity']
   if w['tick']>=v['next_accrual']:
    v['next_accrual']+=720
    for investor,r in v['investors'].items():
     self.programme_accrue(v,investor,r)
   for investor,r in sorted(v['investors'].items(),key=lambda item:item[1].get('queue_sequence',10**12)):
    if w['tick']%168==0 and (w['macro']['stress']>=60 or v['complaint']):self.enqueue_programme_redemption(v,investor,r)
    amount=min(D(r['requested']),D(r['balance']),max(D(0),self.available_cash(entity)))
    if amount and not self.is_frozen(entity) and w['tick']>=v.get('withdrawals_suspended_until',0):
     self.post('Investment programme redemption '+v['id'],{'cash:'+entity:-amount,'debt:'+entity+':programme_'+v['id']:amount,'npc:'+investor+':cash':amount,'npc:'+investor+':programme:'+v['id']:-amount});r['balance']=amt(D(r['balance'])-amount);r['requested']=amt(D(r['requested'])-amount);r['paid']=amt(D(r['paid'])+amount);npc=next(n for n in w['npcs'] if n['id']==investor);npc['wealth']=amt(D(npc['wealth'])+amount);self.record_programme_payment(v,investor,r,amount)
    if D(r['requested'])>0:
     if r['arrears_since'] is None:r['arrears_since']=w['tick']
     if w['tick']-r['arrears_since']>=72 and not v['complaint']:
      amount=sum((D(x['balance']) for x in v['investors'].values()),D(0));reference=v['id'];w['related_transactions'].append(dict(id=reference,source=entity,destination=investor,kind='investment_programme',amount=amt(amount),fair_value='0.00',classification='MISCONDUCT ALLEGATION',reasons=['Unmet fixed-return programme redemptions; investigate marketing and use of proceeds'],actor='player',status='SETTLED',time=w['time'],tick=w['tick'],disclosed=True,settlements=[],observed=w['time']))
      case=self.complaint({'entity':entity,'reference':reference,'reason':'Unpaid investment programme redemption for more than 72 simulation hours'});case['living_world_case']=True;case['reviewed_transactions'].append(reference);v['complaint']=case['id']
    else:r['arrears_since']=None

 def programme_accrue(self,v,investor,r):
  if v.get('claims_converted'):return
  elapsed=self.state['tick']-r.get('last_accrual',self.state['tick']);r['last_accrual']=self.state['tick']
  interest=(D(r['balance'])*D(v['annual_return'])*D(elapsed)/864000).quantize(D('.01'))
  if interest:
   entity=v['entity'];self.post('Promised programme return accrued '+v['id'],{'expense:programme:'+entity:interest,'debt:'+entity+':programme_'+v['id']:-interest,'npc:'+investor+':programme:'+v['id']:interest,'npc:'+investor+':programme_income':-interest});r['balance']=amt(D(r['balance'])+interest)
