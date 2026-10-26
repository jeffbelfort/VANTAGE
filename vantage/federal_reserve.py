"""Autonomous simulated US monetary policy and finite-counterparty Treasury market.
USD securities, GBP authoritative journal. No equity positions stand in for bonds.
Officials, release calendar and macro calibration are explicitly fictional models.
"""
import calendar,copy,math
from datetime import datetime,timedelta
from decimal import Decimal as D
from collections import Counter
from .integrity import amt

FED='federal_reserve';GOV='us_treasury';PERIOD=365*12
MATURITIES=(('BILL',91/365),('2Y',2),('5Y',5),('10Y',10),('30Y',30))
DISTRICTS=['Boston','New York','Philadelphia','Cleveland','Richmond','Atlanta','Chicago','St Louis','Minneapolis','Kansas City','Dallas','San Francisco']
GROUPS=[['Philadelphia','Richmond','Boston'],['Cleveland','Chicago'],['Dallas','Atlanta','St Louis'],['Minneapolis','Kansas City','San Francisco']]

def clamp(x,lo,hi):return max(lo,min(hi,x))
def bond_price(security,tick,yield_pct):
 remaining=max(0,security['maturity_tick']-tick)/8760
 if remaining<=0:return 100.,0.
 y=yield_pct/100
 if not security['coupon']:return 100/(1+y*remaining),0.
 coupon=security['coupon']/2;elapsed=max(0,tick-security['issue_tick']);accrued=coupon*((elapsed%PERIOD)/PERIOD)
 times=[t for t in security['coupons'] if t>tick];price=sum(coupon/(1+y/2)**((t-tick)/PERIOD) for t in times)+100/(1+y/2)**(remaining*2)
 return price,accrued

class FederalReserveMixin:
 def install_fed(self):
  w=self.state
  if w.get('fed'):return w['fed']
  now=datetime.fromisoformat(w['time']);rate=float(w['macro']['rate']);m=w['macro'];members=[]
  for n,name in enumerate(['Alex Morgan','Eleanor Vale','Samuel Ellis','Maya Reed','Victor Chen','Amara Brooks','Daniel Hart']):members.append(dict(id='governor_'+str(n),name=name,office='Chair' if n==0 else 'Governor',institution='Board of Governors',inflation_weight=.75+n*.09,employment_weight=.9-n*.06,bias=(n-3)*.08))
  for n,district in enumerate(DISTRICTS):members.append(dict(id='president_'+str(n),name=district+' simulated president',office='Reserve Bank president',institution=district,inflation_weight=.8+(n%5)*.1,employment_weight=.5+(n%4)*.1,bias=((n%5)-2)*.1))
  for account,name,kind in [(FED,'Federal Reserve System','central_bank'),(GOV,'United States Treasury','sovereign')]:w['entities'][account]=dict(id=account,name=name,kind=kind,controlled=False,parent=None,status='ACTIVE',owners={},units='0',directors=[],signatories={},payment_limit='0',controls=0,mandate={'related_parties':False,'sectors':[]})
  observed=dict(headline=float(m['inflation']),core=max(-.5,float(m['inflation'])-.2),unemployment=(1-float(m.get('employment',.955)))*100,growth=float(m['growth']),output_gap=-.5,output=100.,spending=100.,investment=100.,wage_growth=3.2,expectations=2.4,stress=float(m['stress']),liquidity=100.,financial_conditions=0.)
  f=dict(version=1,created=w['time'],upper=rate,lower=max(0,rate-.25),members=members,observed=copy.deepcopy(observed),latent=copy.deepcopy(observed),calendar=[],calendar_year=now.year-1,history=[],meetings=[],releases=[],facilities=[],last_day=w['tick']//24,sandbox=False,forward_rate=rate,priced_expectation=0.,emergency_armed=True,parameters=dict(inflation_target=2.,neutral_real_rate=1.2,potential_growth=2.,natural_unemployment=4.5),source='Simulated officials and macro model; not real Federal Reserve data or an official release schedule')
  w.update(fed=f,treasury_securities={},treasury_positions={},treasury_trades=[],treasury_pledges=[])
  self.fed_calendar(now.year);self.fed_calendar(now.year+1);self.fed_curve();f['expectations']=self.fed_expectations()
  dealers=[p['account'] for p in w.get('participants',[]) if p['strategy'] in ('bank','investment_bank')]
  f['dealers']=dealers
  if dealers:
   dealer=dealers[0];cash=max(D(0),self.available_cash(dealer));reserve=min(cash*D('.03'),D('100000000000')*self.fx_rate('USD')).quantize(D('.01'));seed=min(cash*D('.15'),D('250000000000')*self.fx_rate('USD'))
   if reserve:
    self.post('Opening funded Federal Reserve account',{'cash:'+dealer:-reserve,'fed_reserve:'+dealer:reserve,'cash:'+FED:reserve,'debt:'+FED+':reserve_'+dealer:-reserve})
   for tenor,years in MATURITIES:
    security=self.treasury_new(tenor,years);face=int(seed/self.fx_rate('USD')/5/100)*100
    if face>=100:self.treasury_issue(dealer,security,D(face));buy=min(D(face)/5,(reserve/5/self.fx_rate('USD')/100).to_integral_value(rounding='ROUND_DOWN')*100)
    else:buy=D(0)
    if buy>=100:self.treasury_transfer(dealer,FED,security,buy,D(str(self.treasury_quote(security)['dirty_price'])),D(0),'Opening secondary-market Fed purchase')
  else:
   for tenor,years in MATURITIES:self.treasury_new(tenor,years)
  f['opening_reserves']=amt(sum((-D(v) for k,v in w['balances'].items() if k.startswith('debt:'+FED+':reserve_')),D(0)))
  f['history'].append(dict(time=w['time'],tick=w['tick'],**f['observed'],upper=f['upper'],curve=copy.deepcopy(f['curve'])))
  self.audit('federal_reserve_established',{'source':f['source'],'funded_dealers':dealers});return f

 def fed_calendar(self,year):
  f=self.state['fed']
  if year<=f['calendar_year']:return
  now=datetime.fromisoformat(self.state['time'])
  for month in range(1,13):
   events=[('CPI',14),('PCE',26),('Employment',1+(4-datetime(year,month,1).weekday())%7)]
   if month in (1,4,7,10):events.append(('GDP',28))
   if month in (1,3,4,6,7,9,10,12):events.append(('FOMC',15+(2-datetime(year,month,15).weekday())%7))
   for kind,day in events:
    date=datetime(year,month,min(day,calendar.monthrange(year,month)[1]),18 if kind=='FOMC' else 13,tzinfo=now.tzinfo)
    if date>now:f['calendar'].append(dict(id=kind+'-'+date.date().isoformat(),kind=kind,time=date.isoformat()))
  f['calendar'].sort(key=lambda x:x['time']);f['calendar_year']=year

 def fed_voters(self,year=None):
  year=year or datetime.fromisoformat(self.state['time']).year;rotation={group[(year-2026)%len(group)] for group in GROUPS}
  return [dict(member,voting=member['institution']=='Board of Governors' or member['institution']=='New York' or member['institution'] in rotation) for member in self.state['fed']['members']]

 def fed_desired_rate(self,data,member=None):
  f=self.state['fed'];p=f['parameters'];member=member or dict(inflation_weight=1.,employment_weight=.65,bias=0.)
  return clamp(p['neutral_real_rate']+data['core']+member['inflation_weight']*(data['core']-p['inflation_target'])+.35*data['output_gap']-member['employment_weight']*(data['unemployment']-p['natural_unemployment'])+member['bias']-.01*max(0,data.get('stress',0)-40),.25,15)

 def fed_expectations(self):
  f=self.state['fed'];o=f['observed'];desired=self.fed_desired_rate(o);signal=clamp((desired-f['upper'])*.35,-.5,.5);uncertainty=.15+abs(o['headline']-o['core'])*.1
  choices=(-.5,-.25,0.,.25,.5);weights=[math.exp(-.5*((change-signal)/uncertainty)**2) for change in choices];total=sum(weights)
  probabilities=[dict(change_bps=round(change*100),probability=weight/total) for change,weight in zip(choices,weights)];mean=sum(x['change_bps']*x['probability']/100 for x in probabilities)
  return dict(as_of=self.state['time'],probabilities=probabilities,expected_change=mean,basis='Model-implied from published inflation, employment and policy reaction; not observed futures prices')

 def fed_curve(self):
  f=self.state['fed'];o=f['observed'];expected=f.get('expectations',{}).get('expected_change',0.);long_rate=clamp(o['expectations']+f['parameters']['neutral_real_rate'],.1,12);reserves=sum((-D(v) for k,v in self.state['balances'].items() if k.startswith('debt:'+FED+':reserve_')),D(0));opening=D(f.get('opening_reserves','0'));qe=clamp(float((reserves-opening)/max(D(1),opening)),-1,3) if opening else 0
  curve=[]
  for _,years in MATURITIES:
   short=f['upper']-.05+expected*(1-math.exp(-years));blend=math.exp(-years/4);premium=.12*math.log1p(years)-.12*qe-.003*o['stress']*min(1,years/5)
   curve.append(dict(years=years,yield_pct=round(clamp(short*blend+long_rate*(1-blend)+premium,.01,15),5)))
  f['curve']=curve;return curve

 def treasury_yield(self,years):
  curve=self.state['fed']['curve']
  if years<=curve[0]['years']:return curve[0]['yield_pct']
  for a,b in zip(curve,curve[1:]):
   if years<=b['years']:return a['yield_pct']+(b['yield_pct']-a['yield_pct'])*(years-a['years'])/(b['years']-a['years'])
  return curve[-1]['yield_pct']

 def treasury_new(self,tenor,years):
  w=self.state;ident='UST-'+tenor+'-'+str(w['tick']);maturity=w['tick']+round(years*8760);coupon=0. if tenor=='BILL' else math.floor(self.treasury_yield(years)*8)/8
  security=dict(id=ident,name='US Treasury '+('13-week bill' if tenor=='BILL' else tenor+' note' if years<=10 else tenor+' bond'),tenor=tenor,years=years,issue_tick=w['tick'],maturity_tick=maturity,maturity=(datetime.fromisoformat(w['time'])+timedelta(hours=maturity-w['tick'])).isoformat(),coupon=coupon,coupons=list(range(w['tick']+PERIOD,maturity+1,PERIOD)) if coupon else [],coupon_index=0,outstanding='0.00',principal_book='0.00',issue_discount='0.00',amortised='0.00',status='ACTIVE',currency='USD',auction_remaining='100000000000.00')
  w['treasury_securities'][ident]=security;return security

 def treasury_quote(self,security):
  tick=self.state['tick'];years=max(0,security['maturity_tick']-tick)/8760;y=self.treasury_yield(years);dirty,accrued=bond_price(security,tick,y)
  if security['coupon_index']<len(security['coupons']) and security['coupons'][security['coupon_index']]<=tick:dirty+=security['coupon']/2;accrued=security['coupon']/2
  up=bond_price(security,tick,y+.01)[0];down=bond_price(security,tick,max(-.5,y-.01))[0];duration=(down-up)/(.0002*dirty) if years>0 else 0
  return dict(id=security['id'],name=security['name'],currency='USD',maturity=security['maturity'],coupon=security['coupon'],yield_pct=y,clean_price=dirty-accrued,dirty_price=dirty,accrued_per_100=accrued,modified_duration=duration,status=security['status'],outstanding=security['outstanding'],price_basis='Per $100 face; semiannual coupon yield, ACT/365 investment yield for bills')

 def treasury_value(self,account):
  if not self.state.get('fed'):return D(0)
  return sum(((D(p['face'])/100*D(str(self.treasury_quote(self.state['treasury_securities'][p['security']])['dirty_price']))*self.fx_rate('USD')).quantize(D('.01')) for p in self.state['treasury_positions'].values() if p['account']==account),D(0))

 def treasury_basis(self,account):
  return sum((D(v) for k,v in self.ledger_items(account) if k.startswith(('treasury:'+account+':','bond_interest:'+account+':'))),D(0))

 def treasury_accrue(self,security):
  w=self.state
  if not security['coupon'] or security['status']!='ACTIVE':return
  q=self.treasury_quote(security);fx=self.fx_rate('USD');last=security['issue_tick'] if security['coupon_index']==0 else security['coupons'][security['coupon_index']-1];accrued=security['coupon']/2*clamp((w['tick']-last)/PERIOD,0,1)
  for p in list(w['treasury_positions'].values()):
   if p['security']!=security['id']:continue
   key='bond_interest:'+p['account']+':'+security['id'];target=(D(p['face'])/100*D(str(accrued))*fx).quantize(D('.01'));delta=target-self.balance(key)
   if delta:self.post('Earned Treasury coupon '+security['id'],{key:delta,'pnl:'+p['account']:-delta,'expense:treasury_interest:'+GOV:delta,'debt:'+GOV+':coupon_'+p['account']+'_'+security['id']:-delta})

 def treasury_issue(self,buyer,security,face):
  if face>D(security['auction_remaining']):raise ValueError('Treasury auction capacity exhausted')
  quote=self.treasury_quote(security);fx=self.fx_rate('USD');principal=(face*fx).quantize(D('.01'));cost=(face/100*D(str(quote['dirty_price']))*fx).quantize(D('.01'));interest=(face/100*D(str(quote['accrued_per_100']))*fx).quantize(D('.01'));clean=cost-interest
  if self.available_cash(buyer)<cost:raise ValueError('Insufficient funded cash for Treasury auction')
  # Face principal liability and an explicit deferred issue discount/premium.
  discount=principal-clean
  self.post('Funded Treasury auction '+security['id'],{'cash:'+buyer:-cost,'treasury:'+buyer+':'+security['id']:clean,'bond_interest:'+buyer+':'+security['id']:interest,'cash:'+GOV:cost,'debt:'+GOV+':principal_'+security['id']:-principal,'treasury_discount:'+GOV+':'+security['id']:discount,'debt:'+GOV+':coupon_'+buyer+'_'+security['id']:-interest})
  key=buyer+':'+security['id'];p=self.state['treasury_positions'].setdefault(key,dict(account=buyer,security=security['id'],face='0.00'));p['face']=amt(D(p['face'])+face);security['outstanding']=amt(D(security['outstanding'])+face);security['principal_book']=amt(D(security['principal_book'])+principal);security['issue_discount']=amt(D(security['issue_discount'])+discount);security['auction_remaining']=amt(D(security['auction_remaining'])-face);security.setdefault('discount_lots',[]).append(dict(amount=amt(discount),tick=self.state['tick'],amortised='0.00'))

 def treasury_transfer(self,seller,buyer,security,face,price,fee,description='Treasury secondary execution',reserves=False):
  if seller==buyer:raise ValueError('Treasury self-trading is not permitted')
  self.treasury_accrue(security);w=self.state;key=seller+':'+security['id'];pos=w['treasury_positions'].get(key)
  locked=sum((D(p['face']) for p in w['treasury_pledges'] if p['account']==seller and p['security']==security['id'] and p['status']=='ACTIVE'),D(0))
  if not pos or face>D(pos['face'])-locked:raise ValueError('Insufficient unpledged Treasury face value')
  fx=self.fx_rate('USD');gross=(face/100*price*fx).quantize(D('.01'));ratio=face/D(pos['face']);basis=(self.balance('treasury:'+seller+':'+security['id'])*ratio).quantize(D('.01'));interest=(self.balance('bond_interest:'+seller+':'+security['id'])*ratio).quantize(D('.01'));realised=gross-interest-basis
  if not reserves and self.available_cash(buyer)<gross+fee:raise ValueError('Insufficient cash after current order commitments')
  lines={'treasury:'+seller+':'+security['id']:-basis,'bond_interest:'+seller+':'+security['id']:-interest,'pnl:'+seller:-realised,'treasury:'+buyer+':'+security['id']:gross-interest,'bond_interest:'+buyer+':'+security['id']:interest,'debt:'+GOV+':coupon_'+seller+'_'+security['id']:interest,'debt:'+GOV+':coupon_'+buyer+'_'+security['id']:-interest}
  if reserves:
   if buyer==FED:lines.update({'fed_reserve:'+seller:gross,'debt:'+FED+':reserve_'+seller:-gross})
   elif seller==FED:
    if self.balance('fed_reserve:'+buyer)<gross:raise ValueError('Insufficient bank reserve balances for QT')
    lines.update({'fed_reserve:'+buyer:-gross,'debt:'+FED+':reserve_'+buyer:gross})
   else:raise ValueError('Reserve settlement requires the central bank')
  else:lines.update({'cash:'+buyer:-gross-fee,'cash:'+seller:gross,'expense:fees:'+buyer:fee,'cash:treasury_clearing':fee,'pnl:treasury_clearing':-fee})
  self.post(description+' '+security['id'],lines);pos['face']=amt(D(pos['face'])-face)
  if D(pos['face'])==0:del w['treasury_positions'][key]
  target=w['treasury_positions'].setdefault(buyer+':'+security['id'],dict(account=buyer,security=security['id'],face='0.00'));target['face']=amt(D(target['face'])+face)
  return gross,realised

 def treasury_order(self,p,internal=False):
  from .engine import positive,uid
  if not self.state.get('fed'):raise ValueError('Federal Reserve / Treasury market is not initialised')
  account=self.account(p)
  if not internal:self.authority(account,'trade',p.get('actor','player'))
  security=self.state['treasury_securities'].get(p.get('security'))
  if not security or security['status']!='ACTIVE' or security['maturity_tick']<=self.state['tick']:raise ValueError('Select an active Treasury security')
  face=positive(p['face']);side=p.get('side','buy')
  if p.get('margin'):raise ValueError('Treasury margin and short borrowing are unsupported')
  if face%100 or side not in ('buy','sell'):raise ValueError('Use buy or sell and whole $100 face increments')
  if self.is_frozen(account):raise ValueError('Account is restricted')
  q=self.treasury_quote(security);spread=D(str((2+.3*q['modified_duration']+.05*self.state['fed']['observed']['stress'])/10000));price=D(str(q['dirty_price']))*(1+spread if side=='buy' else 1-spread);fx=self.fx_rate('USD');gross=(face/100*price*fx).quantize(D('.01'));fee=max(D(1),(gross*D('.0005')).quantize(D('.01')))
  employee=None
  actor=p.get('actor','player');employee_id=p.get('employee') or (actor if actor.startswith('staff_') else None)
  if employee_id:
   if actor.startswith('staff_') and actor!=employee_id:raise ValueError('Employee attribution must match the delegated actor')
   employee=next((e for e in self.staff(account) if e['id']==employee_id and e['role'] in ('trader','portfolio_manager')),None);team=self.state.get('auto_teams',{}).get(account,{})
   if not employee or not team.get('enabled') or team.get('strategy')!='income' or not employee['delegation']['trade']:raise ValueError('Treasury delegation requires an active Income team')
   policy=self.team_policy(employee)
   if policy.get('universe')!='market' or policy.get('countries') and 'US' not in policy['countries'] or policy.get('sectors'):raise ValueError('Treasuries are outside the selected employee security mandate')
   held=D(self.state['treasury_positions'].get(account+':'+security['id'],{}).get('face','0'));nav=max(D(0),D(self.metrics(account)['equity']));reserve=max(D(policy['cash_reserve']),nav*D(policy.get('cash_target_pct','0'))/100)
   if side=='buy' and (self.available_cash(account)-gross-fee<reserve or (held+face)/100*D(str(q['dirty_price']))*fx>min(D(policy['capital_limit']),nav*D(policy.get('max_position_pct','100'))/100)):raise ValueError('Treasury allocation or chosen cash reserve exceeded')
   own_remaining=D(employee['delegation']['daily'])-(D(employee.get('fill_spent','0')) if employee.get('fill_day')==self.state['tick']//24 else D(0))
   remaining=D(team['daily_limit'])-self.team_daily_spend(account)-self.team_pending_turnover(account)
   if gross+fee>min(remaining,own_remaining,D(employee['delegation']['per_order'])):raise ValueError('Treasury order exceeds shared delegated capital')
  dealers=[a for a in self.state['fed']['dealers'] if a!=account]
  if side=='buy':
   if gross+fee>self.available_cash(account):raise ValueError('Insufficient available cash for Treasury price, accrued interest and fee')
   dealer=next((a for a in dealers if D(self.state['treasury_positions'].get(a+':'+security['id'],{}).get('face','0'))>=face),None)
   if dealer:self.treasury_transfer(dealer,account,security,face,price,fee)
   else:
    if face>D(security['auction_remaining']):raise ValueError('Insufficient Treasury inventory and auction allocation')
    self.treasury_issue(account,security,face);price=D(str(q['dirty_price']));gross=(face/100*price*fx).quantize(D('.01'));fee=max(D(1),(gross*D('.0005')).quantize(D('.01')))
    if fee:self.post('Treasury auction execution fee',{'cash:'+account:-fee,'expense:fees:'+account:fee,'cash:treasury_clearing':fee,'pnl:treasury_clearing':-fee})
    gross=(face/100*D(str(q['dirty_price']))*fx).quantize(D('.01'))
   realised=D(0)
  else:
   position=self.state['treasury_positions'].get(account+':'+security['id']);locked=sum((D(v['face']) for v in self.state['treasury_pledges'] if v['account']==account and v['security']==security['id'] and v['status']=='ACTIVE'),D(0))
   if not position or face>D(position['face'])-locked:raise ValueError('Insufficient unpledged Treasury holdings; Treasury short sales are unsupported')
   dealer=next((a for a in dealers if self.available_cash(a)>=gross),None)
   if not dealer:raise ValueError('No funded Treasury dealer bid for that quantity; try a smaller face amount')
   gross,realised=self.treasury_transfer(account,dealer,security,face,price,D(0))
   self.post('Treasury sale execution fee',{'cash:'+account:-fee,'expense:fees:'+account:fee,'cash:treasury_clearing':fee,'pnl:treasury_clearing':-fee})
  if employee:
   day=self.state['tick']//24;employee['fill_spent']=amt((D(employee.get('fill_spent','0')) if employee.get('fill_day')==day else D(0))+gross+fee);employee['fill_day']=day
  row=dict(id=uid(),time=self.state['time'],tick=self.state['tick'],account=account,security=security['id'],side=side,face=amt(face),dirty_price=str(price),consideration_gbp=amt(gross),fee=amt(fee),realised=amt(realised),employee=employee['id'] if employee else None,status='FILLED',counterparty=dealer or GOV)
  self.state['treasury_trades'].append(row);self.audit('treasury_execution',row);return row

 def treasury_fiscal_cash(self,amount):
  gap=max(D(0),amount-self.cash(GOV));tax=min(gap,max(D(0),self.available_cash('economy_households')))
  if tax:self.post('US Treasury fiscal debt-service receipts',{'cash:economy_households':-tax,'expense:sovereign_tax:economy_households':tax,'cash:'+GOV:tax,'pnl:'+GOV:-tax})
  return self.cash(GOV)>=amount

 def treasury_cashflows(self):
  w=self.state
  for security in list(w['treasury_securities'].values()):
   if security['status']=='MATURED':continue
   if w['tick']%24==0 or security['maturity_tick']<=w['tick']:
    target=(D(security['outstanding'])*self.fx_rate('USD')).quantize(D('.01'));difference=target-D(security['principal_book'])
    if difference:self.post('Treasury principal reporting-currency remeasurement',{'expense:treasury_fx:'+GOV:difference,'debt:'+GOV+':principal_'+security['id']:-difference});security['principal_book']=amt(target)
   for lot in (security.get('discount_lots',[]) if w['tick']%24==0 or security['maturity_tick']<=w['tick'] else []):
    fraction=clamp((w['tick']-lot['tick'])/max(1,security['maturity_tick']-lot['tick']),0,1);target=(D(lot['amount'])*D(str(fraction))).quantize(D('.01'));delta=target-D(lot['amortised'])
    if delta:self.post('Treasury issue-discount amortisation '+security['id'],{'expense:treasury_financing:'+GOV:delta,'treasury_discount:'+GOV+':'+security['id']:-delta});lot['amortised']=amt(target)
   if w['tick']%24==0:self.treasury_accrue(security)
   while security['coupon_index']<len(security['coupons']) and security['coupons'][security['coupon_index']]<=w['tick']:
    self.treasury_accrue(security);holders=[p for p in w['treasury_positions'].values() if p['security']==security['id']];due=sum(((D(p['face'])/100*D(str(security['coupon']/2))*self.fx_rate('USD')).quantize(D('.01')) for p in holders),D(0))
    if not self.treasury_fiscal_cash(due):security['status']='COUPON_ARREARS';break
    for pos in holders:
     account=pos['account'];amount=(D(pos['face'])/100*D(str(security['coupon']/2))*self.fx_rate('USD')).quantize(D('.01'));key='bond_interest:'+account+':'+security['id'];book=self.balance(key);difference=amount-book
     self.post('US Treasury semiannual coupon '+security['id'],{'cash:'+GOV:-amount,'debt:'+GOV+':coupon_'+account+'_'+security['id']:book,'expense:treasury_fx:'+GOV:difference,'cash:'+account:amount,key:-book,'pnl:'+account:-difference})
    security['coupon_index']+=1;security['status']='ACTIVE'
   if security['maturity_tick']<=w['tick'] and security['coupon_index']==len(security['coupons']):
    holders=[p for p in w['treasury_positions'].values() if p['security']==security['id']];face=D(security['outstanding']);due=(face*self.fx_rate('USD')).quantize(D('.01'))
    if not self.treasury_fiscal_cash(due):security['status']='MATURITY_ARREARS';continue
    principal=D(security['principal_book']);remaining=principal
    for i,pos in enumerate(holders):
     account=pos['account'];amount=(D(pos['face'])*self.fx_rate('USD')).quantize(D('.01'));book=self.balance('treasury:'+account+':'+security['id']);liability=remaining if i==len(holders)-1 else (principal*D(pos['face'])/face).quantize(D('.01'));remaining-=liability
     self.post('Treasury principal redemption '+security['id'],{'cash:'+GOV:-amount,'debt:'+GOV+':principal_'+security['id']:liability,'expense:treasury_fx:'+GOV:amount-liability,'cash:'+account:amount,'treasury:'+account+':'+security['id']:-book,'pnl:'+account:book-amount});del w['treasury_positions'][account+':'+security['id']]
     if account==FED and w['fed'].get('runoff'):self.fed_runoff(amount)
    security.update(status='MATURED',outstanding='0.00',principal_book='0.00')
    if security['tenor']=='BILL':self.treasury_new('BILL',91/365)

 def fed_macro_step(self,data,rate,days=1):
  d=copy.deepcopy(data);p=self.state['fed']['parameters']
  for _ in range(days):
   real_rate=rate-d['expectations'];target_conditions=real_rate-p['neutral_real_rate']+d['stress']/40-(d['liquidity']-100)/80;d['financial_conditions']+=(target_conditions-d['financial_conditions'])/30
   target_gap=clamp(-1.2*d['financial_conditions']+(d['spending']-100)/50,-8,6);target_growth=clamp(p['potential_growth']+.65*(target_gap-d['output_gap']),-8,8);d['growth']+=(target_growth-d['growth'])/30;d['output_gap']=clamp(d['output_gap']+(d['growth']-p['potential_growth'])/365,-10,8);d['output']*=math.exp(d['growth']/36500)
   target_unemployment=clamp(p['natural_unemployment']-.45*d['output_gap'],2,18);d['unemployment']+=(target_unemployment-d['unemployment'])/90
   target_wage=d['expectations']+1+.25*(p['natural_unemployment']-d['unemployment']);d['wage_growth']+=(target_wage-d['wage_growth'])/90
   d['core']=clamp(d['core']+(.25*(d['expectations']-d['core'])+.18*d['output_gap']+.08*(d['wage_growth']-3))/365,-1,15);d['expectations']=clamp(d['expectations']+(.7*d['core']+.3*p['inflation_target']-d['expectations'])/540,0,10)
   d['headline']+=(d['core']-d['headline'])/60;d['investment']+=(clamp(100-6*d['financial_conditions'],60,125)-d['investment'])/60;d['spending']+=(clamp(100+d['output_gap']*2,70,120)-d['spending'])/90
  return d

 def fed_publish_expectations(self,reason):
  f=self.state['fed'];previous=f.get('expectations',{}).get('expected_change',0);f['expectations']=self.fed_expectations();change=f['expectations']['expected_change']-previous
  if abs(change)>=.025:self.macro_change({'rate':self.state['macro']['rate']},reason,rate_information_delta=change*.5)
  self.fed_curve()

 def fed_meeting(self,event,emergency=False,override=None):
  f=self.state['fed'];o=f['observed'];before=f['upper'];expected=f.get('expectations',self.fed_expectations())['expected_change'];votes=[]
  for person in self.fed_voters():
   if not person['voting']:continue
   desired=self.fed_desired_rate(f['latent'],person);gap=(desired-before)*.3;step=.75 if o['core']>6 else .5 if emergency or abs(o['core']-2)>3 or o['unemployment']>8 else .25;choice=step if gap>.12 else -step if gap<-.12 else 0;target=clamp(before+choice,.25,15);votes.append(dict(member=person['id'],name=person['name'],institution=person['institution'],target=target,reason='Inflation mandate weighted '+str(round(person['inflation_weight'],2))+'; employment gap '+str(round(o['unemployment']-4.5,2))))
  counts=Counter(v['target'] for v in votes);best=max(counts.values());targets=[rate for rate,n in counts.items() if n==best];chair=votes[0]['target'];decision=min(targets,key=lambda target:(abs(target-chair),abs(target-before))) if override is None else override
  decision=round(clamp(decision,.25,15)*4)/4;surprise=decision-before-expected;f.update(upper=decision,lower=max(0,decision-.25),forward_rate=decision,policy_stance='Restrictive' if decision-o['expectations']>1.5 else 'Accommodative' if decision-o['expectations']<.5 else 'Neutral')
  title='Federal Reserve '+('holds rates' if decision==before else 'raises rates' if decision>before else 'cuts rates')
  self.macro_change({'rate':decision},title,rate_information_delta=surprise)
  row=dict(id=event['id'],time=event['time'],emergency=emergency,sandbox=override is not None,before=before,upper=decision,lower=f['lower'],votes=votes if override is None else [],dissent=sum(v['target']!=decision for v in votes) if override is None else None,expected_change=expected,surprise_bps=round(surprise*100,2),statement=title+'; headline inflation '+str(round(o['headline'],2))+'%, unemployment '+str(round(o['unemployment'],2))+'%. Decisions balance price stability, employment and observed financial conditions.',minutes='Members compared published data with current staff estimates. Differing inflation and employment preferences explain recorded dissents. Model uncertainty remains; no future market prices were used.',projections={k:f['latent'][k] for k in ('core','unemployment','growth')})
  month=datetime.fromisoformat(event['time']).month
  if month in (3,6,9,12):
   one=self.fed_macro_step(f['latent'],decision,365);two=self.fed_macro_step(f['latent'],decision,730);row['projections']={'one_year':{key:one[key] for key in ('core','unemployment','growth')},'two_years':{key:two[key] for key in ('core','unemployment','growth')},'basis':'Conditional staff model forecasts at constant policy; not known future outcomes'}
  else:row['staff_nowcast']=row.pop('projections')
  f['meetings'].append(row);f['latest']=row;f['expectations']=self.fed_expectations();self.fed_curve();self.news(title,row['statement']+' Policy surprise '+str(row['surprise_bps'])+' basis points versus prior model expectations.','MONETARY POLICY')
  if emergency:f['last_emergency']=self.state['tick'];f['last_emergency_stress']=o['stress'];f['emergency_armed']=False
  for employee in self.state['employees']:
   if employee['status']=='EMPLOYED' and employee['role'] in ('analyst','trader','portfolio_manager') and self.state.get('auto_teams',{}).get(employee['entity'],{}).get('enabled'):employee['next_department']=min(employee.get('next_department',self.state['tick']+1),self.state['tick']+1)
  self.fed_balance_operation('QE' if o['stress']>65 and decision<=1 else 'QT' if o['core']>2.5 else 'HOLD')
  return row

 def fed_balance_operation(self,kind):
  f=self.state['fed'];dealer=next(iter(f['dealers']),None)
  f['runoff']=kind=='QT'
  if not dealer or kind=='HOLD':return
  seller,buyer=(dealer,FED) if kind=='QE' else (FED,dealer)
  for position in list(self.state['treasury_positions'].values()):
   if position['account']!=seller:continue
   security=self.state['treasury_securities'][position['security']]
   if security['status']!='ACTIVE':continue
   price=D(str(self.treasury_quote(security)['dirty_price']));capacity=D(position['face'])*D('.05')
   if kind=='QT':capacity=min(capacity,self.balance('fed_reserve:'+dealer)/self.fx_rate('USD')/price*100)
   face=(capacity/100).to_integral_value(rounding='ROUND_DOWN')*100
   if face<100:continue
   self.treasury_transfer(seller,buyer,security,face,price,D(0),'Federal Reserve '+kind,reserves=True)
   if kind=='QE':
    convert=(face/100*price*self.fx_rate('USD')*D('.25')).quantize(D('.01'))
    if convert:self.fed_reserve_transfer({'account':dealer,'kind':'withdraw','amount':str(convert)},internal=True)
   f['last_balance_operation']=dict(time=self.state['time'],kind=kind,face_usd=amt(face),security=security['id']);break

 def fed_tick(self):
  f=self.state.get('fed')
  if not f:return
  w=self.state;now=datetime.fromisoformat(w['time']);day=w['tick']//24
  if f['last_day']!=day:
   f['last_day']=day;d=f['latent'];d['stress']=float(w['macro'].get('stress',0))
   us=[issuer for symbol,issuer in w.get('issuers',{}).items() if self.instrument(symbol).get('market_country')=='US' and D(issuer.get('last_revenue','0'))>0];actual=sum((D(i['last_revenue']) for i in us),D(0));baseline=sum((D(i['revenue_daily']) for i in us),D(0))
   if baseline>0:d['spending']=clamp(d['spending']+(float(actual/baseline)*100-d['spending'])*.02,70,130)
   claims=[claim for claim in w.get('claims_book',[]) if D(claim['balance'])>0];credit_total=sum((D(c['balance']) for c in claims),D(0));defaults=sum((D(c['balance']) for c in claims if c['status'] in ('DEFAULT','OVERDUE')),D(0))
   if credit_total>0:d['stress']=max(d['stress'],min(100,float(defaults/credit_total)*100))
   reserves=sum((-D(v) for k,v in w['balances'].items() if k.startswith('debt:'+FED+':reserve_')),D(0));opening=D(f.get('opening_reserves','0'));d['liquidity']=clamp(100+10*float((reserves-opening)/max(D(1),opening)),60,130);f['latent']=self.fed_macro_step(d,f['upper']);f['observed'].update(financial_conditions=f['latent']['financial_conditions'],liquidity=d['liquidity']);w['macro']['demand']=f['latent']['spending'];self.fed_curve();self.fed_institutional_allocation();f['history'].append(dict(time=w['time'],tick=w['tick'],**f['observed'],upper=f['upper'],curve=copy.deepcopy(f['curve'])));f['history']=f['history'][-4000:]
  self.treasury_cashflows();self.fed_facility_tick()
  if now.year>=f['calendar_year']:self.fed_calendar(now.year+1)
  while f['calendar'] and f['calendar'][0]['time']<=w['time']:
   event=f['calendar'].pop(0)
   if event['kind']=='FOMC':self.fed_meeting(event);continue
   fields={'CPI':['headline'],'PCE':['core','expectations'],'Employment':['unemployment','wage_growth'],'GDP':['growth','output_gap','output','spending','investment']}[event['kind']];actual={key:f['latent'][key] for key in fields};previous={key:f['observed'][key] for key in fields};forecast={}
   for key in fields:
    past=[release['actual'][key] for release in f['releases'] if key in release['actual']];trend=(past[-1]-past[-2])*.5 if len(past)>1 else 0;forecast[key]=previous[key]+trend
   f['observed'].update(actual);row=dict(**event,previous=previous,expectation=forecast,expectation_basis='Damped trend of previously published releases',actual=actual);f['releases'].append(row);f['releases']=f['releases'][-600:]
   w['macro'].update(inflation=f['observed']['headline'],growth=f['observed']['growth'],employment=1-f['observed']['unemployment']/100)
   self.news('US '+event['kind']+' release',', '.join(key.replace('_',' ')+' '+str(round(value,2))+' (previous '+str(round(previous[key],2))+')' for key,value in actual.items()),'ECONOMIC DATA');self.fed_publish_expectations('Markets reassess policy after '+event['kind'])
  if f['observed']['stress']!=f['latent']['stress']:f['observed']['stress']=f['latent']['stress']
  if f['observed']['stress']<60:f['emergency_armed']=True
  material=f.get('emergency_armed',True) or f['observed']['stress']>=f.get('last_emergency_stress',0)+10
  if f['observed']['stress']>=80 and material and w['tick']-f.get('last_emergency',-8760)>=24:self.fed_meeting(dict(id='EMERGENCY-'+str(w['tick']),time=w['time']),emergency=True)

 def fed_scenario(self,p):
  f=self.state.get('fed')
  if not f:raise ValueError('Federal Reserve is not initialised')
  delta=float(p.get('delta_bps',0));months=int(p.get('months',24))
  if not math.isfinite(delta) or abs(delta)>300 or not 1<=months<=36:raise ValueError('Scenario supports ±300 basis points and 1–36 months')
  baseline=copy.deepcopy(f['observed']);scenario=copy.deepcopy(baseline);rows=[]
  for month in range(1,months+1):
   baseline=self.fed_macro_step(baseline,f['upper'],30);scenario=self.fed_macro_step(scenario,clamp(f['upper']+delta/100,.25,15),30);rows.append(dict(month=month,baseline={k:baseline[k] for k in ('core','unemployment','growth')},scenario={k:scenario[k] for k in ('core','unemployment','growth')},uncertainty_pp=.15*math.sqrt(month)))
  return dict(as_of=self.state['time'],delta_bps=delta,rows=rows,note='Read-only hypothetical path from published observations. Policy held constant; uncertainty bands are model ranges, not probabilities. No live state, orders or journal entries changed.')

 def fed_facility(self,p,internal=False):
  from .engine import positive,uid
  account=p['account'];entity=self.state['entities'].get(account,{})
  if not internal:
   self.authority(account,'payment');bank=next((b for b in self.state['banks'] if b.get('entity')==account),None)
   if entity.get('kind')!='bank' or not bank or bank.get('licence')!='AUTHORISED':raise ValueError('Emergency facility requires an authorised operating bank')
  if self.is_frozen(account) or D(self.metrics(account)['equity'])<=0:raise ValueError('Facility eligibility requires an unrestricted solvent bank')
  if self.state['fed']['observed']['stress']<65:raise ValueError('Emergency facility is inactive outside genuine financial stress')
  security=self.state['treasury_securities'].get(p.get('security'));face=positive(p['face']);amount=positive(p['amount'])
  if not security or security['status']!='ACTIVE':raise ValueError('Active Treasury collateral is required')
  if security['maturity_tick']<=self.state['tick']+720:raise ValueError('Treasury collateral must remain outstanding beyond the 30-day facility term')
  held=D(self.state['treasury_positions'].get(account+':'+security['id'],{}).get('face','0'));locked=sum((D(v['face']) for v in self.state['treasury_pledges'] if v['account']==account and v['security']==security['id'] and v['status']=='ACTIVE'),D(0));collateral=face/100*D(str(self.treasury_quote(security)['dirty_price']))*self.fx_rate('USD')
  if face%100 or face>held-locked or amount>collateral*D('.9'):raise ValueError('Facility exceeds actual unpledged collateral after a 10% haircut')
  cap=max(D('100000000')*self.fx_rate('USD'),D(self.state['fed'].get('opening_reserves','0'))*D('.25'));used=sum((D(c['balance']) for c in self.state['claims_book'] if c['kind']=='FED FACILITY'),D(0))
  if amount+used>cap:raise ValueError('Emergency facility funding limit reached')
  claim=self.create_claim(FED,account,amount,'FED FACILITY','Discount-window Treasury collateral',str(self.state['fed']['upper']+1),1);pledge=dict(id=uid(),account=account,security=security['id'],face=amt(face),claim=claim['id'],status='ACTIVE');self.state['treasury_pledges'].append(pledge)
  self.post('Collateralised Federal Reserve emergency loan',{'cash:'+account:amount,'debt:'+account+':claim_'+claim['id']:-amount,'claim:'+FED+':'+claim['id']:amount,'debt:'+FED+':currency':-amount});self.state['fed']['facilities'].append(dict(claim=claim['id'],borrower=account,pledge=pledge['id'],principal=amt(amount),burned='0.00',time=self.state['time']));return claim

 def fed_enforce_facilities(self,account=None):
  # Contractual in-kind foreclosure, not a fabricated exchange execution or cash fill.
  w=self.state
  if not w.get('fed'):return
  for facility in w['fed']['facilities']:
   if account and facility['borrower']!=account:continue
   claim=next(c for c in w['claims_book'] if c['id']==facility['claim']);pledge=next(p for p in w['treasury_pledges'] if p['id']==facility['pledge']);borrower=claim['debtor']
   default=claim['status'] in ('OVERDUE','DEFAULT') and claim['due']<=w['tick'];administration=w['entities'].get(borrower,{}).get('status')=='ADMINISTRATION'
   if not (default or administration) or pledge['status']!='ACTIVE' or D(claim['balance'])<=0:continue
   security=w['treasury_securities'][pledge['security']];position=w['treasury_positions'].get(borrower+':'+security['id'])
   if not position or security['status']!='ACTIVE':continue
   self.treasury_accrue(security);quote=self.treasury_quote(security);unit=D(str(quote['dirty_price']))/100*self.fx_rate('USD');face=min(D(pledge['face']),D(position['face']),(D(claim['balance'])/unit/100).to_integral_value(rounding='ROUND_DOWN')*100)
   if face<100:continue
   amount=(face*unit).quantize(D('.01'));ratio=face/D(position['face']);basis=(self.balance('treasury:'+borrower+':'+security['id'])*ratio).quantize(D('.01'));interest=(self.balance('bond_interest:'+borrower+':'+security['id'])*ratio).quantize(D('.01'));release=(D(claim['allowance'])*amount/D(claim['balance'])).quantize(D('.01'))
   self.post('Defaulted Fed facility: contractual Treasury collateral foreclosure '+claim['id'],{'treasury:'+borrower+':'+security['id']:-basis,'bond_interest:'+borrower+':'+security['id']:-interest,'debt:'+borrower+':claim_'+claim['id']:amount,'pnl:'+borrower:basis+interest-amount,'treasury:'+FED+':'+security['id']:amount-interest,'bond_interest:'+FED+':'+security['id']:interest,'claim:'+FED+':'+claim['id']:-amount,'allowance:'+FED+':'+claim['id']:release,'pnl:'+FED:-release,'debt:'+GOV+':coupon_'+borrower+'_'+security['id']:interest,'debt:'+GOV+':coupon_'+FED+'_'+security['id']:-interest})
   position['face']=amt(D(position['face'])-face)
   if D(position['face'])==0:del w['treasury_positions'][borrower+':'+security['id']]
   target=w['treasury_positions'].setdefault(FED+':'+security['id'],dict(account=FED,security=security['id'],face='0.00'));target['face']=amt(D(target['face'])+face);claim['balance']=amt(D(claim['balance'])-amount);claim['allowance']=amt(D(claim['allowance'])-release);claim['status']='REPAID' if D(claim['balance'])==0 else claim['status'];claim.setdefault('collateral_recoveries',[]).append(dict(time=w['time'],security=security['id'],face=amt(face),amount=amt(amount),basis='Published dirty model price; in-kind secured recovery, no cash or exchange volume'))
   remaining=max(D(0),D(pledge['face'])-face);needed=(D(claim['balance'])/unit/100).to_integral_value(rounding='ROUND_CEILING')*100 if D(claim['balance'])>0 else D(0);pledge['face']=amt(min(remaining,needed));pledge['status']='RELEASED' if not D(pledge['face']) else 'ACTIVE';self.audit('fed_collateral_enforcement',claim['collateral_recoveries'][-1])

 def fed_facility_tick(self):
  self.fed_enforce_facilities()
  for facility in self.state['fed']['facilities']:
   claim=next(c for c in self.state['claims_book'] if c['id']==facility['claim']);pledge=next(p for p in self.state['treasury_pledges'] if p['id']==facility['pledge'])
   if claim['status']=='REPAID':
    pledge['status']='RELEASED';burn=min(D(facility['principal'])-D(facility['burned']),self.cash(FED),max(D(0),-self.balance('debt:'+FED+':currency')))
    if burn>0:self.post('Retire repaid emergency currency',{'cash:'+FED:-burn,'debt:'+FED+':currency':burn});facility['burned']=amt(D(facility['burned'])+burn)

 def fed_public_view(self):
  f=self.state.get('fed')
  if not f:return None
  assets=self.metrics(FED);reserves=-sum((D(v) for k,v in self.state['balances'].items() if k.startswith('debt:'+FED+':reserve_')),D(0));quotes=[self.treasury_quote(s) for s in self.state['treasury_securities'].values() if s['status']!='MATURED']
  return dict(upper=f['upper'],lower=f['lower'],stance=f.get('policy_stance','Initial policy range'),members=self.fed_voters(),observed=copy.deepcopy(f['observed']),next_meeting=next((e for e in f['calendar'] if e['kind']=='FOMC'),None),calendar=copy.deepcopy(f['calendar'][:16]),expectations=copy.deepcopy(f.get('expectations',self.fed_expectations())),curve=copy.deepcopy(f['curve']),history=copy.deepcopy(f['history'][-730:]),meetings=copy.deepcopy(f['meetings']),releases=copy.deepcopy(f['releases'][-60:]),latest=copy.deepcopy(f.get('latest')),balance_sheet=dict(cash=assets['cash'],treasuries=assets.get('treasury_market','0'),loans=assets['receivables'],reserves=amt(reserves),currency=amt(-self.balance('debt:'+FED+':currency')),net_assets=assets['equity'],reporting_currency='GBP ledger equivalent; securities denominated USD'),securities=quotes,positions=copy.deepcopy(list(self.state['treasury_positions'].values())),trades=copy.deepcopy(self.state['treasury_trades'][-100:]),sandbox=f['sandbox'],source=f['source'],facilities=[dict(facility,balance=next(c['balance'] for c in self.state['claims_book'] if c['id']==facility['claim']),status=next(c['status'] for c in self.state['claims_book'] if c['id']==facility['claim'])) for facility in f['facilities']],last_balance_operation=copy.deepcopy(f.get('last_balance_operation')))

 def fed_control(self,p):
  f=self.state['fed'];kind=p['kind']
  if kind=='sandbox':
   if p.get('confirm')!='POLICY SANDBOX':raise ValueError('Explicit POLICY SANDBOX confirmation required')
   f['sandbox']=bool(p.get('enabled'));return {'sandbox':f['sandbox']}
  if kind=='override':
   if not f['sandbox']:raise ValueError('Policy overrides are disabled in normal gameplay')
   rate=float(p['upper'])
   if not math.isfinite(rate) or not .25<=rate<=15 or abs(rate*4-round(rate*4))>1e-8:raise ValueError('Use a target upper bound of 0.25–15%, in quarter-point steps')
   return self.fed_meeting(dict(id='SANDBOX-'+str(self.state['tick'])+'-'+str(len(f['meetings'])),time=self.state['time']),override=rate)
  raise ValueError('Unknown Federal Reserve control')

 def validate_treasuries(self):
  if not self.state.get('fed'):return
  for security in self.state['treasury_securities'].values():
   face=sum((D(p['face']) for p in self.state['treasury_positions'].values() if p['security']==security['id']),D(0))
   if face!=D(security['outstanding']):raise ValueError('Treasury face supply does not reconcile')
   if -self.balance('debt:'+GOV+':principal_'+security['id'])!=D(security['principal_book']):raise ValueError('Treasury principal liability does not reconcile')
  for key,value in self.state['balances'].items():
   if key.startswith('bond_interest:'):
    _,account,security=key.split(':',2)
    if D(value)!=-self.balance('debt:'+GOV+':coupon_'+account+'_'+security):raise ValueError('Earned coupon asset/liability does not reconcile')
   if key.startswith('fed_reserve:'):
    account=key.split(':',1)[1]
    if D(value)!=-self.balance('debt:'+FED+':reserve_'+account):raise ValueError('Federal Reserve balances do not reconcile')

 def fed_institutional_allocation(self):
  w=self.state;f=w['fed'];actors=[a for a in w.get('participants',[]) if a['strategy'] in ('pension','asset_manager','bank','investment_bank','corporate_treasury','credit_fund') and not a.get('mandate',{}).get('equity_only') and a.get('mandate',{}).get('allow_trade',True)]
  if not actors:return
  actor=actors[(w['tick']//24)%len(actors)];account=actor['account'];used=D(actor.get('turnover_used','0')) if actor.get('turnover_day')==w['tick']//24 else D(0);capacity=max(D(0),D(actor.get('opening_listed','0'))*D(actor.get('mandate',{}).get('annual_turnover','0'))/365-used);budget=min(max(D(0),self.available_cash(account))*D('.002'),D(self.metrics(account)['equity'])*D('.001'),capacity)
  if budget<100:return
  securities=[s for s in w['treasury_securities'].values() if s['status']=='ACTIVE' and s['maturity_tick']>w['tick']];target_years=10 if f.get('expectations',{}).get('expected_change',0)<-.1 else .25
  if not securities:return
  security=min(securities,key=lambda s:abs((s['maturity_tick']-w['tick'])/8760-target_years));q=self.treasury_quote(security)
  if q['yield_pct']<w['macro']['rate']-.5:return
  face=(budget/self.fx_rate('USD')/D(str(q['dirty_price']))).to_integral_value(rounding='ROUND_DOWN')*100
  try:
   result=self.treasury_order({'account':account,'security':security['id'],'side':'buy','face':str(face)},internal=True);actor['last_treasury_decision']=dict(time=w['time'],yield_pct=q['yield_pct'],reason='Funded liquidity allocation using published policy expectations and Treasury yields',execution=result['id']);actor['turnover_day']=w['tick']//24;actor['turnover_used']=amt(used+D(result['consideration_gbp']))
  except ValueError as error:actor['last_treasury_decision']=dict(time=w['time'],reason=str(error),status='No funded eligible Treasury execution')

 def team_treasury_income(self,employee):
  w=self.state;team=w.get('auto_teams',{}).get(employee['entity'],{})
  if not w.get('fed') or not team.get('enabled') or team.get('strategy')!='income' or not employee['delegation']['trade']:return
  policy=self.team_policy(employee)
  equity_commitment=D(0)
  for task in w['employee_tasks']:
   if task['entity']!=employee['entity'] or task['kind']!='order' or task['status'] not in ('QUEUED','AWAITING APPROVAL') or not task.get('recommendation') or task.get('instruction',{}).get('side','buy')!='buy':continue
   request=task['instruction'];ins=self.instrument(request['symbol']);notional=D(str(request['qty']))*D(ins['price'])*self.fx_rate(ins['currency']);equity_commitment+=notional*D('1.01')+max(D(1),notional*D('.0005'))
  if policy.get('universe')!='market' or policy.get('countries') and 'US' not in policy['countries'] or policy.get('sectors'):return
  equity=max(D(0),D(self.metrics(employee['entity'])['equity']));reserve=max(D(policy['cash_reserve']),equity*D(policy.get('cash_target_pct','0'))/100);budget=min(D(policy['capital_limit']),max(D(0),self.available_cash(employee['entity'])-reserve-equity_commitment),max(D(0),D(team['daily_limit'])-self.team_daily_spend(employee['entity'])-self.team_pending_turnover(employee['entity'])-equity_commitment))
  own_used=D(employee.get('fill_spent','0')) if employee.get('fill_day')==w['tick']//24 else D(0)
  budget=min(budget,D(employee['delegation']['per_order']),max(D(0),D(employee['delegation']['daily'])-own_used))
  if budget<100:team['activity']='Income team has no uncommitted cash or remaining delegated authority above its chosen reserve';return
  target=2 if team['mode']=='careful' else 5 if team['mode']=='balanced' else 10;securities=[s for s in w['treasury_securities'].values() if s['status']=='ACTIVE' and s['maturity_tick']>w['tick']]
  for security in sorted(securities,key=lambda s:abs((s['maturity_tick']-w['tick'])/8760-target)):
   held=D(w['treasury_positions'].get(employee['entity']+':'+security['id'],{}).get('face','0'));q=self.treasury_quote(security);unit=D(str(q['dirty_price']))/100*self.fx_rate('USD');room=max(D(0),min(D(policy['capital_limit']),equity*D(policy.get('max_position_pct','100'))/100)-held*unit);face=(min(budget,room)/unit/D('1.01')/100).to_integral_value(rounding='ROUND_DOWN')*100
   if face<100:continue
   result=self.treasury_order({'account':employee['entity'],'employee':employee['id'],'actor':employee['id'],'security':security['id'],'side':'buy','face':str(face)});team['activity']='Income team purchased '+amt(face)+' USD face of '+security['name']+' at '+str(round(q['yield_pct'],2))+'% model yield';self.employee_log(employee,'treasury_income',team['activity'],result['id']);return result

 def fed_runoff(self,amount):
  remaining=min(amount,self.cash(FED))
  for key,value in list(self.state['balances'].items()):
   if not key.startswith('fed_reserve:') or D(value)<=0:continue
   bank=key.split(':',1)[1];paid=min(remaining,D(value))
   if paid:self.post('Fed maturity runoff / reserve redemption',{'cash:'+FED:-paid,'debt:'+FED+':reserve_'+bank:paid,key:-paid,'cash:'+bank:paid});remaining-=paid
   if remaining<=0:break

 def fed_reserve_transfer(self,p,internal=False):
  from .engine import positive
  account=p['account'];amount=positive(p['amount']);kind=p['kind']
  if not internal:
   self.authority(account,'payment');bank=next((bank for bank in self.state['banks'] if bank.get('entity')==account),None)
   if not bank or bank.get('licence')!='AUTHORISED':raise ValueError('Reserve accounts are for authorised banks, not investment funds')
  if self.is_frozen(account):raise ValueError('Reserve account is restricted')
  if kind=='deposit':
   if self.available_cash(account)<amount:raise ValueError('Insufficient uncommitted bank cash for reserve deposit')
   self.post('Funded central bank reserve deposit',{'cash:'+account:-amount,'fed_reserve:'+account:amount,'cash:'+FED:amount,'debt:'+FED+':reserve_'+account:-amount})
  elif kind=='withdraw':
   if self.balance('fed_reserve:'+account)<amount:raise ValueError('Insufficient reserve claim; reserves cannot be invented')
   funded=min(amount,max(D(0),self.cash(FED)));issued=amount-funded;lines={'fed_reserve:'+account:-amount,'debt:'+FED+':reserve_'+account:amount,'cash:'+account:amount,'cash:'+FED:-funded,'debt:'+FED+':currency':-issued};self.post('Bank reserve conversion to spendable cash',lines)
  else:raise ValueError('Choose reserve deposit or withdrawal')
  return dict(account=account,reserves=amt(self.balance('fed_reserve:'+account)),cash=amt(self.cash(account)))

 def treasury_resolution_sale(self,account):
  if not self.state.get('fed'):return
  for position in list(self.state['treasury_positions'].values()):
   if position['account']!=account:continue
   security=self.state['treasury_securities'][position['security']]
   if security['status']!='ACTIVE':continue
   locked=sum((D(p['face']) for p in self.state['treasury_pledges'] if p['account']==account and p['security']==security['id'] and p['status']=='ACTIVE'),D(0));face=D(position['face'])-locked
   for dealer in self.state['fed']['dealers']:
    if dealer==account or face<100:continue
    price=D(str(self.treasury_quote(security)['dirty_price']))*D('.9995');capacity=(max(D(0),self.available_cash(dealer))/self.fx_rate('USD')/price).to_integral_value(rounding='ROUND_DOWN')*100;quantity=min(face,capacity)
    if quantity>=100:self.treasury_transfer(account,dealer,security,quantity,price,D(0),'Administrator funded Treasury disposal');face-=quantity
