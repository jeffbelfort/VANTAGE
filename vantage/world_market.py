"""Default institutional economy: finite issued securities and segregated portfolios.
Calibration is an offline fictional scenario, independent of player wealth.
"""
import hashlib,math
from decimal import Decimal as D
from .integrity import amt

# ID, label, strategy, share of public float, cash/listed assets, outside/listed,
# annual gross turnover mandate, review interval, client-owned, lendable fraction.
MANDATES=[
 ('mm0','Arden Global Dealer','market_maker','.0008','.8','0','20',1,False,'.25'),
 ('mm1','Beacon Securities','liquidity_provider','.0006','1.2','0','25',1,False,'.25'),
 ('global_mm','Meridian Institutional Markets','market_maker','.001','1','0','30',1,False,'.3'),
 ('bankdesk','Harbour Investment Bank Desk','bank','.0005','1.5','0','8',12,False,'.15'),
 ('investment_bank','Bridgewater Brokerage Desk','investment_bank','.0004','1.2','0','10',12,False,'.15'),
 ('asset','Horizon Global Asset Management','asset_manager','.12','.015','.15','.15',24,True,'.08'),
 ('index','Broad Market Index Portfolios','asset_manager','.10','.008','.05','.05',48,True,'.12'),
 ('active_asset','Continental Active Funds','asset_manager','.025','.04','.4','.5',12,True,'.08'),
 ('pension','Civic Retirement Trust','pension','.018','.025','1.2','.12',48,True,'.10'),
 ('global_pension','National Retirement System','pension','.025','.02','.8','.10',48,True,'.10'),
 ('sovereign','Sovereign Future Generations','value','.02','.04','.8','.12',48,True,'.05'),
 ('insurance','Long Horizon Insurance Portfolio','value','.008','.05','2','.15',24,True,'.04'),
 ('hedge','Cairn Global Strategies','hedge_fund','.0012','.15','.1','3',4,True,'.05'),
 ('momentum','Vector Institutional Partners','momentum','.0002','.2','0','4',6,True,'.03'),
 ('credit','Stratum Corporate Credit','credit_fund','.001','.1','4','.3',24,True,'.02'),
 ('private','Longview Private Capital','value','.0005','.08','7','.1',48,True,'0'),
 ('midfund','Regional Opportunities Fund','value','.00002','.08','.2','.8',12,True,'.05'),
 ('smallfund','Emerging Managers Portfolio','value','.0000002','.15','0','1',12,True,'0'),
 ('microfund','Specialist Small Partnership','momentum','.00000005','.25','0','2',6,True,'0'),
 ('prop','Vertex Proprietary Trading','proprietary','.000001','.5','0','8',3,False,'.05'),
 ('retail','Household Direct Investors','retail','.04','.08','.1','.4',24,False,'.03')]

class WorldMarketMixin:
 def generate_institutional_world(self):
  w=self.state
  if w.get('institutional_world_initialized'):raise ValueError('World capitalisation is creation-only and cannot be replayed')
  if w['tick']!=0 or w['participants']:raise ValueError('Institutional generation requires a new empty market')
  w['outside_assets']={};w['outside_backing']={};w['institutional_funds']=[];w['share_register']={};w['institutional_world_initialized']=True
  symbols=w['market_symbols'];allocations={id:{} for id,*_ in MANDATES};locked={};custody={};listed_values={id:D(0) for id,*_ in MANDATES};total_market=D(0)
  for sym in symbols:
   ins=w['instruments'][sym];profile=self.market_profile(sym);ins['institutional_profile']=profile;ins['model_daily_volume']=profile['adv'];free=D(profile['free_float']);seed=int(hashlib.sha256(sym.encode()).hexdigest()[:8],16);ratio=D(65+seed%26)/100;outstanding=(free/ratio).to_integral_value(rounding='ROUND_UP');locked[sym]=outstanding-free;assigned=D(0);unit=D(ins['price'])*self.fx_rate(ins['currency']);total_market+=outstanding*unit
   for id,_,strategy,weight,*rest in MANDATES:
    # Sector preferences differ without changing the finite total share supply.
    preference=D('.85')+D(int(hashlib.sha256((id+':'+ins['sector']).encode()).hexdigest()[:4],16)%31)/100
    qty=(free*D(weight)*preference).to_integral_value(rounding='ROUND_DOWN');allocations[id][sym]=qty;assigned+=qty;listed_values[id]+=qty*unit
   if assigned>free:raise ValueError('Institutional allocation exceeds public float')
   custody[sym]=free-assigned;w['share_register'][sym]={'outstanding':str(outstanding),'authorised':str((outstanding*D('1.25')).to_integral_value(rounding='ROUND_DOWN')),'free_float':str(free),'strategic_shares':str(outstanding-free),'treasury':'0','source':profile['source']};ins['borrow_available']=0;ins['model_fundamental']=ins['price'];ins.setdefault('flow_history',[])
  self.post('Model prime-broker opening risk capital',{'cash:prime':total_market*D('.001'),'equity:prime':-total_market*D('.001')})
  self.post('Model household opening liquidity reserve',{'cash:economy_households':total_market*D('.01'),'equity:economy_households':-total_market*D('.01')})
  def entity(id,name,kind):
   w['entities'][id]={'id':id,'name':name,'kind':kind,'controlled':False,'parent':None,'status':'ACTIVE','owners':{},'units':'0','directors':['model_board'],'signatories':{},'payment_limit':'0','controls':2,'mandate':{'related_parties':False,'sectors':[]}}
  def stocks(account,name,quantities,client,cash,outside):
   lines={'cash:'+account:cash};value=cash
   for sym,qty in quantities.items():
    if qty<=0:continue
    ins=w['instruments'][sym];cost=(qty*D(ins['price'])*self.fx_rate(ins['currency'])).quantize(D('.01'));lines['inventory:'+account+':'+sym]=cost;value+=cost;w['positions'][account+':'+sym]={'account':account,'symbol':sym,'qty':amt(qty),'cost':amt(cost),'borrowed':'0.00','opening_allocation':True}
   if outside:
    lines['outside:'+account+':fixed_income_private']=outside;value+=outside;w['outside_assets'][account]={'carrying_value':amt(outside),'class':'Nonlisted fixed income / private productive assets','liquidity':'Not exchange cash; no automatic redemption','backing':'outside_economy'}
   lines['equity:'+account]=-value;self.post('Opening portfolio capitalisation: '+name,lines)
   if client:
    owner='beneficiaries_'+account;entity(owner,name+' clients','beneficiary_pool');w['entities'][account]['owners']={owner:amt(value)};w['entities'][account]['units']=amt(value);self.post('Client beneficial units: '+name,{'investment:'+owner+':'+account:value,'equity:'+owner:-value})
   return value
  for id,name,strategy,weight,cash_ratio,outside_ratio,turnover,interval,client,lend in MANDATES:
   account='agent_'+id;entity(account,name,'institutional_fund' if client else 'dealer' if strategy in ('market_maker','liquidity_provider','bank','investment_bank') else 'proprietary_pool');listed=listed_values[id];cash=(listed*D(cash_ratio)).quantize(D('.01'));outside=(listed*D(outside_ratio)).quantize(D('.01'));nav=stocks(account,name,allocations[id],client,cash,outside)
   operator=None
   if client:
    operator='manager_'+id;entity(operator,name+' management company','asset_manager');operating=min(D(50000000),max(D(50000),nav*D('.00002'))).quantize(D('.01'));self.post('Manager operating capital: '+name,{'cash:'+operator:operating,'equity:'+operator:-operating})
    w['institutional_funds'].append({'account':account,'manager':operator,'name':name,'beneficial_owner':list(w['entities'][account]['owners'])[0],'opening_units':amt(nav),'mandate':strategy,'opening_nav':amt(nav)})
   actor=dict(id=id,account=account,name=name,strategy=strategy,interval=interval,next_tick=interval,risk_budget=.35,information_delay=2,known_events=[],beliefs={},last_decision=None,manager=operator,client_owned=client,mandate={'annual_turnover':turnover,'lend_fraction':lend,'cash_ratio':cash_ratio,'allow_trade':True,'equity_only':outside==0},target_quantities={s:str(q) for s,q in allocations[id].items()},opening_nav=amt(nav),opening_listed=amt(listed))
   w['participants'].append(actor)
  for id,name,quantities,kind in [('strategic','Founders and strategic locked owners',locked,'strategic_owner'),('custody','Independent custody nominees',custody,'custody')]:
   account='agent_'+id;entity(account,name,kind);stocks(account,name,quantities,False,D(0),D(0));w['participants'].append(dict(id=id,account=account,name=name,strategy=kind,interval=10**9,next_tick=10**9,risk_budget=0,information_delay=0,known_events=[],beliefs={},last_decision=None,mandate={'allow_trade':False,'annual_turnover':'0','lend_fraction':'0'}))
  outside_total=sum((D(v['carrying_value']) for v in w['outside_assets'].values()),D(0));self.post('Nonlisted portfolio underlying opening backing',{'productive:outside_economy':outside_total,'debt:outside_economy:portfolio_claims':-outside_total});w['outside_backing']={'productive_assets':amt(outside_total),'portfolio_claims':amt(outside_total),'cash_available':'0.00','source':'Fictional fixed-income/private productive economy; illiquid, not duplicate listed shares'}
  for sym in symbols:
   ins=w['instruments'][sym];reg=w['share_register'][sym];capital=(D(reg['outstanding'])*D(ins['price'])*self.fx_rate(ins['currency'])*D('.03')).quantize(D('.01'));account='issuer_'+sym.replace('.','_').replace('-','_');entity(account,ins['name']+' model treasury','issuer');self.post('Issuer operating cash capitalisation '+sym,{'cash:'+account:capital,'equity:'+account:-capital});marketcap=capital/D('.03');revenue=(marketcap*D('.035')/D('.2')/365).quantize(D('.01'))
   w['issuers'][sym]={'symbol':sym,'account':account,'revenue_daily':amt(revenue),'cost_ratio':'.8','opening_earnings_multiple':str(marketcap/(revenue*365*D('.2'))),'model_shares':int(D(reg['outstanding'])),'last_revenue':'0.00','last_cost':'0.00','last_profit':'0.00','cumulative_revenue':'0.00','cumulative_profit':'0.00','status':'OPERATING','sector':ins['sector'],'source':'FICTIONAL issuer calibrated to model equity supply; not real financial reports'}
  self.refresh_institutional_borrow();self.audit('institutional_world_generated',{'version':2,'participants':len(w['participants']),'issuers':len(symbols),'market_capitalisation_gbp':amt(total_market),'method':'Finite ownership allocations of a single issued share register; no dependence on player funds or orders'})
  self.replenish_books();w['liquidity_quote_version']=1
 def outside_value(self,account):return sum((D(v) for k,v in self.ledger_items(account) if k.startswith('outside:'+account+':')),D(0))
 def market_reference(self,ins):
  return D(ins.get('model_fundamental',ins['price']))*D(str(math.exp(float(ins.get('market_information_log',0)))))

 def update_market_information(self,common,sectors,rng):
  # Public information, not executions: marks/volume change only at settlement.
  w=self.state
  if w.get('market_generation_version')!=2 or not self.session_open():return
  variance=.94*float(w.get('market_information_variance',1))+.06*common*common;w['market_information_variance']=variance
  regime=max(.6,min(1.7,math.sqrt(variance)))*(1+float(w['macro'].get('stress',0))/120)
  for symbol in w['market_symbols']:
   ins=w['instruments'][symbol]
   if ins['status']!='OPEN':continue
   if 'information_vol_scale' not in ins:ins['information_vol_scale']=.8+int(hashlib.sha256(symbol.encode()).hexdigest()[:4],16)%401/1000
   shock=.6*common+.4*sectors.get(ins['sector'],0)+math.sqrt(.48)*rng.gauss(0,1)
   innovation=float(ins.get('vol',.25))*ins['information_vol_scale']*.75*regime/math.sqrt(8760)*shock
   ins['market_information_log']=max(-.2,min(.2,.997*float(ins.get('market_information_log',0))+innovation));ins['information_tick']=w['tick']

 def refresh_institutional_borrow(self):
  w=self.state
  if w.get('market_generation_version')!=2:return
  for sym in w['market_symbols']:
   cap=D(0)
   for actor in w['participants']:
    held=max(D(0),D(w['positions'].get(actor['account']+':'+sym,{}).get('qty',0)));cap+=(held*D(actor.get('mandate',{}).get('lend_fraction',0))).to_integral_value(rounding='ROUND_DOWN')
   w['instruments'][sym]['borrow_available']=int(cap)
 def institutional_investor_openings(self):
  w=self.state
  for i,(name,aum,cash_fraction) in enumerate([('Regional Fund of Funds',500000000,'.08'),('Global Pension Allocator',350000000000,'.025'),('Sovereign External Mandates',800000000000,'.015'),('Insurance Alternatives',180000000000,'.04'),('Institutional Endowment',25000000000,'.05'),('Family Investment Partnership',40000000,'.1')]):
   id='allocator_'+str(i);cash=(D(aum)*D(cash_fraction)).quantize(D('.01'));outside=D(aum)-cash;n=dict(id=id,name=name,wealth=amt(cash),trust=75,risk=.35+i*.06,horizon_days=90+i*30,liquidity_need=.005,withdrawal_sensitivity=.2,units={},outside_assets=amt(outside),opening_aum=str(aum));w['npcs'].append(n);self.post('Allocator opening portfolio '+name,{'npc:'+id+':cash':cash,'npc:'+id+':outside':outside,'npc:'+id+':equity':-D(aum)})
   self.post('Allocator nonlisted backing '+name,{'productive:outside_economy':outside,'debt:outside_economy:portfolio_claims':-outside})
  w['outside_backing'].update(productive_assets=amt(self.balance('productive:outside_economy')),portfolio_claims=amt(-self.balance('debt:outside_economy:portfolio_claims')))
 def institutional_views(self,metrics=None):
  rows=[]
  for actor in self.state.get('participants',[]):
   if not actor.get('mandate'):continue
   m=(metrics or {}).get(actor['account']) or self.metrics(actor['account']);client=actor.get('client_owned',False);custody=actor['strategy']=='custody'
   rows.append(dict(id=actor['id'],name=actor['name'],strategy=actor['strategy'],account=actor['account'],manager=actor.get('manager'),client_owned=client,aum=m['equity'] if client else None,custody_assets=m['equity'] if custody else None,proprietary_risk_capital=m['equity'] if not client and not custody else None,cash=m['cash'],available_cash=m['available_cash'],listed_assets=m['market'],outside_assets=amt(self.outside_value(actor['account'])),liabilities=m['debt'],annual_turnover=actor['mandate'].get('annual_turnover'),last_decision=actor.get('last_decision')))
  return rows
 def institutional_decision(self,actor,sym,rng):
  if not actor.get('mandate'):return False
  mandate=actor['mandate']
  if not mandate.get('allow_trade') or self.is_frozen(actor['account']) or not self.session_open() or self.instrument(sym)['status']!='OPEN':return True
  w=self.state;account=actor['account'];ins=self.instrument(sym);px=D(ins['price']);fx=self.fx_rate(ins['currency']);held=D(w['positions'].get(account+':'+sym,{}).get('qty',0));target=D(actor['target_quantities'].get(sym,0));fundamental=self.market_reference(ins);signal=D(str(actor.get('beliefs',{}).get(sym,0)))
  # Opening holdings are not every investor's permanent desired portfolio.
  # Different funded mandates review bounded valuation/allocation views on
  # different horizons. These affect orders only, never prices or volume.
  key=int(hashlib.sha256((str(w['seed'])+actor['id']+sym).encode()).hexdigest()[:12],16);turnover=D(mandate['annual_turnover']);horizon=max(48,min(720,720/math.sqrt(max(.01,float(turnover)))));prior=D(key%2001-1000)/100000;rotation=D(str(math.sin(w['tick']*2*math.pi/horizon+(key//2001%6284)/1000)))*D('.015');macro=w['macro'];exposure=D((key//13)%201-100)/100;economic=(D(str(macro.get('growth',0)))/100-D(str(macro.get('rate',0)))/200-D(str(macro.get('stress',0)))/1000)*exposure*D('.2');cash_target=D(actor['opening_listed'])*D(mandate.get('cash_ratio',0));cash_tilt=max(D('-.015'),min(D('.015'),(self.cash(account)-cash_target)/max(D(1),D(actor['opening_listed']))));view=max(D('-.04'),min(D('.04'),prior+rotation+economic+cash_tilt));desired=target*max(D('.5'),min(D('1.5'),fundamental/px+signal+view));difference=desired-held
  day=w['tick']//24;used=D(actor.get('turnover_used',0)) if actor.get('turnover_day')==day else D(0);budget=max(D(0),D(actor['opening_listed'])*D(mandate['annual_turnover'])/365-used);clip=min(abs(difference),self.profile_hour_volume(sym)*D('.1'),budget/max(1,getattr(self,'_institutional_review_slots',1))/max(D('.01'),px*fx));qty=int(clip)
  if qty<1:return True
  side='buy' if difference>0 else 'sell'
  if side=='sell':qty=min(qty,max(0,int(held)))
  else:qty=min(qty,int(self.available_cash(account)/(px*fx*D('1.002'))))
  if qty<=0:return True
  try:order=self.order({'account':account,'symbol':sym,'side':side,'qty':qty,'tif':'IOC','margin':False})
  except ValueError as exc:
   actor['last_decision']={'time':w['time'],'symbol':sym,'status':'RISK CONSTRAINED','reason':str(exc)};return True
  actor['last_decision']={'time':w['time'],'symbol':sym,'side':side,'qty':qty,'filled':order['filled'],'status':order['status'],'allocation_view':str(view),'basis':'Public fundamentals, bounded mandate allocation review and liquidity needs; actual cash and shared daily turnover budget'};return True
 def institutional_capacity(self,order,price,requested):
  actor=next((a for a in self.state.get('participants',[]) if a['account']==order['account'] and a.get('mandate')),None)
  if not actor:return requested
  mandate=actor['mandate']
  if not mandate.get('allow_trade'):return D(0)
  if actor['strategy'] in ('market_maker','liquidity_provider'):return requested
  used=D(actor.get('turnover_used',0)) if actor.get('turnover_day')==self.state['tick']//24 else D(0);budget=max(D(0),D(actor['opening_listed'])*D(mandate['annual_turnover'])/365-used)
  return min(requested,(budget/(price*self.fx_rate(self.instrument(order['symbol'])['currency']))).to_integral_value(rounding='ROUND_DOWN'))
 def validate_institutional_supply(self):
  w=self.state
  if w.get('market_generation_version')!=2:return
  totals={}
  for pos in w['positions'].values():totals[pos['symbol']]=totals.get(pos['symbol'],D(0))+D(pos['qty'])
  for sym,issuer in w['issuers'].items():
   if totals.get(sym,D(0))!=D(issuer['model_shares']):raise ValueError('Issued share ownership does not reconcile: '+sym)
  outside=sum((D(v) for k,v in w['balances'].items() if k.startswith('outside:') or k.startswith('npc:') and k.endswith(':outside')),D(0))
  if outside!=-self.balance('debt:outside_economy:portfolio_claims') or outside!=self.balance('productive:outside_economy'):raise ValueError('Nonlisted institutional backing does not reconcile')
  for f in w['institutional_funds']:
   e=w['entities'][f['account']]
   if sum((D(q) for q in e['owners'].values()),D(0))!=D(e['units']):raise ValueError('Institutional beneficial units do not reconcile')
 def investor_aum(self,n):
  total=D(n['wealth'])+self.balance('npc:'+n['id']+':outside')
  for f in self.state['funds']:
   if D(f['units'])>0:total+=max(D(0),D(self.metrics(f['id'])['equity']))*D(f['investors'].get(n['id'],0))/D(f['units'])
  total+=sum((D(v) for k,v in self.state['balances'].items() if k.startswith(('npc:'+n['id']+':programme:','npc:'+n['id']+':receivable:'))),D(0))
  return amt(total)
 def institutional_cycle(self):
  w=self.state
  if w.get('market_generation_version')!=2 or w['tick']%24:return
  for actor in w['participants']:
   if not actor.get('manager'):continue
   account=actor['account'];fee=(D(actor['opening_nav'])*D('.001')/365).quantize(D('.01'));paid=min(fee,self.available_cash(account))
   if paid:self.post('Institutional management expense '+actor['name'],{'cash:'+account:-paid,'expense:management:'+account:paid,'cash:'+actor['manager']:paid,'pnl:'+actor['manager']:-paid})
