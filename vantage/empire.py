"""Corporate Empire Phase A: auditable investor reviews and persistent customer identity."""
import hashlib,json,copy
from decimal import Decimal as D
from .integrity import amt

class EmpireMixin:
 def install_empire_a(self):
  w=self.state
  if w.get('empire_a_version',0)>=1:return False
  if len({n['id'] for n in w['npcs']})!=len(w['npcs']):raise ValueError('Duplicate investor owner IDs; identity migration refused')
  profiles={};owners=['personal']+['npc_'+n['id'] for n in w['npcs']]+list(w['entities'])
  for account in dict.fromkeys(owners):
   n=next((n for n in w['npcs'] if account=='npc_'+n['id']),None);entity=w['entities'].get(account,{});name=n['name'] if n else entity.get('name',account)
   institution=any(word in name.lower() for word in ('pension','endowment','partners','capital','trust','office','insurance','foundation','reserve','partnership','pool'))
   kind='corporate' if institution or entity.get('kind') not in (None,'personal') else 'individual'
   seed=int(hashlib.sha256((w['id']+'|'+account).encode()).hexdigest()[:12],16);risk=float(n['risk']) if n else .2+(seed%50)/100
   profiles[account]={'id':'customer_'+hashlib.sha256((w['id']+'|'+account).encode()).hexdigest()[:16],'owner_account':account,'name':name,'kind':kind,'source':'Preserved investor/entity registry','risk_appetite':risk,'age_at_registration':25+seed%51 if kind=='individual' else None,'occupation':'Private investor' if n else 'Player' if account=='personal' else None,'industry':next((i['sector'] for i in w['instruments'].values() if w.get('issuers',{}).get(i['symbol'],{}).get('account')==account),'Institutional investment' if institution else entity.get('kind')),'representatives':list(entity.get('directors',[])),'income':None,'income_basis':'No invented salary or external income; cash flows remain ledger-based','liquidity_reserve':amt(max(D(100),self.cash(account)*D(str(.02+(seed%9)/100)))),'deposit_fraction':.005+(seed%16)/1000,'rate_tolerance':.5+(seed%16)/10,'spending_cycle_days':14+seed%30,'cycle_offset':seed%14}
  for owner,profile in w.get('customer_identities',{}).items():profiles[owner]=profile
  if len({p['id'] for p in profiles.values()})!=len(profiles):raise ValueError('Duplicate existing customer identity IDs; migration refused')
  w['customer_identities']=profiles;w.setdefault('investor_decisions',[]);w['empire_a_version']=1
  self.audit('empire_a_metadata_migration',{'version':1,'identities':len(profiles),'policy':'Owner IDs, financial balances, contracts and history unchanged; no customer endowments'})
  return True
 def customer_profile(self,account):
  self.install_empire_a()
  profile=self.state['customer_identities'].get(account)
  if profile:return profile
  # Entities formed after the migration acquire metadata from their actual legal record.
  entity=self.state['entities'].get(account)
  if not entity:raise ValueError('Unknown customer owner')
  seed=int(hashlib.sha256(account.encode()).hexdigest()[:8],16)
  profile={'id':'customer_'+hashlib.sha256((self.state['id']+'|'+account).encode()).hexdigest()[:16],'owner_account':account,'name':entity['name'],'kind':'corporate','industry':entity['kind'],'representatives':list(entity['directors']),'source':'Existing legal entity','income':None,'risk_appetite':.2,'liquidity_reserve':'1000.00','deposit_fraction':.005+(seed%16)/1000,'rate_tolerance':.5+(seed%16)/10,'spending_cycle_days':30,'cycle_offset':seed%14}
  self.state['customer_identities'][account]=profile;return profile
 def bank_customer_plan(self,account,bank):
  p=self.customer_profile(account);available=self.available_cash(account);reserve=D(p['liquidity_reserve']);days=p['spending_cycle_days']
  due=sum((D(l['payment']) for l in self.state['loans'] if l['account']==account and l['status']!='REPAID' and l['next_due']<=self.state['tick']+24*days),D(0))
  if p['kind']=='corporate':
   issuer=next((i for i in self.state.get('issuers',{}).values() if i['account']==account),None)
   if issuer:reserve=max(reserve,D(issuer['revenue_daily'])*D(issuer['cost_ratio'])*7)
   reason='Treasury liquidity and scheduled debt service'
  else:reason='Household liquidity reserve and scheduled debt service'
  need=max(D(0),reserve+due-available)
  return {'profile':p,'cash_need':need,'deposit':min(D(10000),max(D(0),available-reserve-due)*D(str(p['deposit_fraction']))).quantize(D('.01')),'loan_need':need,'reason':reason}
 def grounded_investor_behaviour(self):
  if self.state.get('_legacy_fixture'):return
  w=self.state
  for f in w['funds']:
   fm=self.metrics(f['id']);nav=D(fm['equity']);total=D(f['units']);per_unit=nav/total if total else D(0);reviews=f.setdefault('investor_reviews',{})
   for n in w['npcs']:
    owned=D(f['investors'].get(n['id'],'0'))
    if owned<=0:continue
    previous=reviews.get(n['id']);horizon=24*max(1,int(n.get('horizon_days',30)))
    if previous and w['tick']-previous['tick']<horizon:continue
    pending=[r for r in w.get('redemptions',[]) if r['fund']==f['id'] and r['investor']==n['id'] and D(r['remaining'])>0]
    risk=float(n['risk']);reasons=[];fraction=D(0);observed=float(per_unit/D(previous['nav_per_unit'])-1) if previous and D(previous['nav_per_unit'])>0 else None
    if observed is not None and observed<-(.03+.12*risk):reasons.append('Investment loss exceeds mandate tolerance');fraction=max(fraction,D(str(min(.35,-observed))))
    if float(fm['drawdown'])>.08+.25*risk:reasons.append('Drawdown exceeds investor risk tolerance');fraction=max(fraction,D('.1'))
    if float(fm['volatility'])>.1+.45*risk:reasons.append('Portfolio volatility exceeds risk appetite');fraction=max(fraction,D('.1'))
    largest=max((value for _,value in fm['concentration']),default=0)/max(1,float(nav))
    if largest>.2+.6*risk:reasons.append('Single-name concentration exceeds investor mandate');fraction=max(fraction,D('.1'))
    if any(c['fund']==f['id'] and c['status'] in ('INQUIRY','ENFORCEMENT') for c in w['claims']):reasons.append('Recorded reporting inquiry');fraction=max(fraction,D('.1'))
    if n['trust']<40:reasons.append('Low recorded investor confidence');fraction=max(fraction,D('.05'))
    if float(f.get('performance',0))>20+40*risk:reasons.append('Performance participation exceeds investor fee tolerance');fraction=max(fraction,D('.05'))
    if float(f.get('management',0))>4+2*risk:reasons.append('Management fee burden exceeds mandate tolerance');fraction=max(fraction,D('.05'))
    profile=self.customer_profile('npc_'+n['id']);cash_need=max(D(0),D(profile['liquidity_reserve'])-D(n['wealth']))
    if cash_need>0 and per_unit>0:reasons.append('Actual liquid cash below investor reserve');fraction=max(fraction,min(D('.35'),cash_need/(owned*per_unit)))
    if pending:
     overdue=[r for r in pending if w['tick']>=r['eligible_tick']+24]
     reasons=['Existing unpaid redemption; additional requests suppressed' if overdue else 'Contractual notice/lockup pending; additional requests suppressed'];fraction=D(0)
     if overdue:
      n['trust']=max(0,n['trust']-4);self.message(n['name'],'Outstanding redemption complaint',f["name"]+': accepted payment remains outstanding after eligibility. Receipt '+overdue[0]['id'])
      if not f.get('liquidity_notice'):
       f['liquidity_notice']=w['tick'];self.news('Fund withdrawal pressure: '+f['name'],'Accepted eligible redemption liabilities remain unpaid; the recorded creditor claims are unchanged.','FUND LIQUIDITY')
    if not previous and not reasons:reasons=['Initial observation; establish actual unit-NAV baseline']
    if not reasons:reasons=['Performance, risk, liquidity and fee mandate remain acceptable']
    decision={'time':w['time'],'tick':w['tick'],'fund':f['id'],'investor':n['id'],'action':'HOLD','reasons':reasons,'observed_return':observed,'nav_per_unit':str(per_unit)}
    if fraction>0:
     units=min(owned,(owned*min(D('.35'),fraction)).quantize(D('.00000001')))
     if units>0:
      try:
       receipt=self.redemption_request({'fund':f['id'],'investor':n['id'],'units':str(units)});decision.update(action='REDEEM',reference=receipt['id'],units=str(units),amount=receipt['amount'])
      except ValueError as exc:decision.update(action='BLOCKED',reason=str(exc))
    reviews[n['id']]={'tick':w['tick'],'nav_per_unit':str(per_unit)};w['investor_decisions'].append(decision);w['investor_decisions']=w['investor_decisions'][-300:];self.audit('investor_review',decision)
 def investor_relations_views(self):
  """Incremental projection of preserved cash-flow evidence; unknown commitments stay unknown."""
  w=self.state;version=self.db.execute('pragma data_version').fetchone()[0];cache=getattr(self,'_investor_flow_cache',None)
  tail=self.db.execute('select max(rowid) from journal').fetchone()[0] or 0
  if not cache or cache['world']!=w['id'] or cache['db'] is not self.db or cache['version']!=version or cache['last']>tail:cache={'world':w['id'],'db':self.db,'version':version,'last':0,'flows':{},'fees':{}}
  if self.db.in_transaction:cache={**cache,'flows':copy.deepcopy(cache['flows']),'fees':copy.deepcopy(cache['fees'])}
  for rowid,desc,encoded in self.db.execute("select rowid,description,lines from journal not indexed where world=? and rowid>? and (description like 'Investor %' or description like 'Personal %' or description like 'Redemption cash settlement %' or description like 'Accrued % fee' or description='Fund seed transfer' or description='Manager fee settlement') order by rowid",(w['id'],cache['last'])):
   lines=json.loads(encoded)
   for f in w['funds']:
    fid=f['id'];fees=cache['fees'].setdefault(fid,{'management':D(0),'performance':D(0),'salary':D(0),'paid':D(0)})
    for kind in ('management','performance','salary'):fees[kind]+=D(lines.get('expense:'+kind+':'+fid,'0'))
    if desc=='Manager fee settlement':fees['paid']+=D(lines.get('debt:'+fid+':manager_fees','0'))
    if desc.startswith('Accrued ') or desc=='Manager fee settlement':continue
    for investor in ['personal']+[n['id'] for n in w['npcs']]:
     flow=cache['flows'].setdefault((fid,investor),{'subscribed':D(0),'opening_basis':D(0),'redeemed':D(0)})
     invkey='investment:personal:'+fid if investor=='personal' else 'npc:'+investor+':investment:'+fid;cashkey='cash:personal' if investor=='personal' else 'npc:'+investor+':cash';basis=D(lines.get(invkey,'0'))
     if basis>0:
      if desc.startswith('Investor subledger opening baseline'):flow['opening_basis']+=basis
      else:flow['subscribed']+=basis
     redemption=desc.startswith(('Investor claim conversion ','Redemption cash settlement ')) or desc=='Personal fund redemption'
     # Settlement identifiers link payments to a specific fund; immediate releases identify it in the description.
     belongs_fund=(' / '+fid) in desc or any(r['fund']==fid and r['id'] in desc for r in w.get('redemptions',[])) or (desc=='Personal fund redemption' and invkey in lines)
     if redemption and belongs_fund:flow['redeemed']+=max(D(0),D(lines.get(cashkey,'0')))
   cache['last']=rowid
  cache['last']=tail
  if not self.db.in_transaction:self._investor_flow_cache=cache
  result={}
  for f in w['funds']:
   fid=f['id'];total=D(f['units']);nav=D(self.metrics(fid)['equity']);rows=[]
   for investor,units in f['investors'].items():
    n=next((n for n in w['npcs'] if n['id']==investor),None);flow=cache['flows'].get((fid,investor),{'subscribed':D(0),'opening_basis':D(0),'redeemed':D(0)});owned=D(units);value=max(D(0),nav)*owned/total if total else D(0);requests=[r for r in w.get('redemptions',[]) if r['fund']==fid and r['investor']==investor];pending=sum((D(r['remaining']) for r in requests),D(0));basis=flow['subscribed']+flow['opening_basis'];decision=next((d for d in reversed(w.get('investor_decisions',[])) if d['fund']==fid and d['investor']==investor),None)
    rows.append({'investor':investor,'name':n['name'] if n else {'personal':'Personal seed investor','sponsor':'Institutional sponsor','admin':'Administrative capital'}.get(investor,investor),'commitment':n.get('commitments',{}).get(fid) if n else None,'recorded_subscriptions':amt(flow['subscribed']),'opening_basis':amt(flow['opening_basis']),'basis_complete':flow['opening_basis']==0 and basis>0,'units':str(owned),'ownership':float(owned/total) if total else 0,'value':amt(value),'redemptions_paid':amt(flow['redeemed']),'redemptions_due':amt(pending),'net_performance':amt(value+pending+flow['redeemed']-basis) if basis else None,'risk_appetite':n.get('risk') if n else None,'lock_until':f['lock_until'],'notice_hours':f.get('terms',{}).get('notice_hours',0),'last_decision':decision,'redemption_history':requests[-20:],'redemption_count':len(requests)})
   fees=cache['fees'].get(fid,{});result[fid]={'investors':rows,'fees':{k:amt(v) for k,v in fees.items()},'contract':{'management_apr':f['management'],'performance_pct':f['performance'],'monthly_salary':f.get('monthly_salary','0'),'highwater':f['highwater'],'authorised':f.get('compensation_authorized',False),'frequency':'Management accrues daily (365-day basis); performance crystallises daily above net unit HWM; salary every 720 hours'},'evidence':'Preserved journal and redemption records. Commitments not previously recorded are unavailable. Opening migration bases are not represented as original subscriptions.'}
  return result
