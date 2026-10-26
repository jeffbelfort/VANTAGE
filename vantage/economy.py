"""Modeled issuers, finite household demand and explicit institutional credit networks.
These financials are simulation parameters, never genuine issuer financial reports.
"""
from decimal import Decimal as D
import hashlib,math
from .integrity import amt

class EconomyMixin:
 def install_economy(self):
  w=self.state
  if w.get('economy_version'):return
  w.update(economy_version=1,issuers={},credit_offers=[],economic_history=[],network_events=[])
  w['economy_active']=bool(w.get('microstructure_enabled'));w['paused']=True
  if not w['economy_active']:return
  if w.get('market_generation_version')==2:
   self.generate_institutional_world();w['macro'].update(employment=.94,demand=100.,confidence=65.,recession_risk=.1);return
  extra=[s for s in ['GS','MS','BAC','WFC','C','XOM','CVX','AMD','AVGO','META','AMZN','LMT','BA','AZN.L','SHEL.L','BP.L'] if s in w['instruments'] and s not in w['market_symbols']]
  w['market_symbols']+=extra;self.post('Household sector opening model endowment',{'cash:economy_households':D('100000000000'),'equity:economy_households':-D('100000000000')})
  for id,name,strategy,capital,interval in [('global_mm','Meridian Global Liquidity','market_maker',2000000000,1),('credit','Stratum Credit Partners','credit_fund',500000000,24),('investment_bank','Bridgewater Securities Treasury','investment_bank',1000000000,12),('corporate_cash','Industrial Treasury Pool','corporate_treasury',250000000,24)]:
   account='agent_'+id;actor=dict(id=id,account=account,name=name,strategy=strategy,interval=interval,next_tick=w['tick']+1,risk_budget=.3,information_delay=1 if strategy!='market_maker' else 0,known_events=[],beliefs={},last_decision=None);w['participants'].append(actor);lines={'cash:'+account:D(capital)};equity=D(capital)
   if strategy=='market_maker':
    for sym in w['market_symbols']:
     ins=w['instruments'][sym];qty=D(max(100,int(D('2500000')/(D(ins['price'])*self.fx_rate(ins['currency'])))));cost=(qty*D(ins['price'])*self.fx_rate(ins['currency'])).quantize(D('.01'));lines['inventory:'+account+':'+sym]=cost;equity+=cost;w['positions'][account+':'+sym]=dict(account=account,symbol=sym,qty=amt(qty),cost=amt(cost),borrowed='0.00')
   lines['equity:'+account]=-equity;self.post('Institution opening capital '+name,lines)
  self.sync_entities()
  for sym in w['market_symbols']:
   ins=w['instruments'][sym];ins.setdefault('model_fundamental',ins['price']);ins.setdefault('flow_history',[]);ins.setdefault('public_short_interest','0');ins.setdefault('public_borrow_utilization',0);ins.setdefault('borrow_fee_apr',3);ins['borrow_available']=max(int(ins.get('borrow_available',0)),int(sum((max(D(0),D(p['qty'])) for p in w['positions'].values() if p['symbol']==sym),D(0))*D('2.5')))
   id='issuer_'+sym.replace('.','_').replace('-','_');seed=int(hashlib.sha256(sym.encode()).hexdigest()[:6],16);capital=D(50000000+seed%150000000);revenue=D(100000+seed%300000)
   issuer=dict(symbol=sym,account=id,revenue_daily=amt(revenue),cost_ratio=str(D('.65')+D(seed%20)/100),model_shares=max(1000000,sum(int(D(p['qty'])) for p in w['positions'].values() if p['symbol']==sym)*5),last_revenue='0.00',last_cost='0.00',last_profit='0.00',cumulative_revenue='0.00',cumulative_profit='0.00',status='OPERATING',sector=ins['sector'],source='MODEL ISSUER FINANCIALS; NOT ACTUAL COMPANY DATA')
   w['issuers'][sym]=issuer;w['entities'][id]=dict(id=id,name=ins['name']+' / model treasury',kind='issuer',controlled=False,parent=None,status='ACTIVE',owners={},units='0',directors=['model_board'],signatories={},payment_limit='0',controls=2,mandate={'related_parties':False,'sectors':[]});self.post('Model issuer opening capital '+sym,{'cash:'+id:capital,'equity:'+id:-capital})
  # Seed a small transparent network entirely among new institutions/issuers.
  self.make_network_claim('agent_investment_bank','agent_credit',D('100000000'),'5.5',24,'Opening signed institutional credit facility')
  for issuer in list(w['issuers'].values())[:6]:self.make_network_claim('agent_credit',issuer['account'],D('5000000'),'7',12,'Opening working-capital agreement')
  w['macro'].update(employment=.94,demand=100.,confidence=65.,recession_risk=.1);self.replenish_books();self.audit('economic_network_initialized',{'matched_symbols':len(w['market_symbols']),'new_institutions':4,'issuer_financials':'Explicit model, not real reported figures','existing_prices_preserved':True})
 def make_network_claim(self,lender,borrower,amount,rate,months,description):
  claim=self.create_claim(lender,borrower,amount,'INSTITUTIONAL CREDIT',description,rate,months);self.post(description,{'cash:'+lender:-amount,'claim:'+lender+':'+claim['id']:amount,'cash:'+borrower:amount,'debt:'+borrower+':claim_'+claim['id']:-amount});return claim
 def network_credit(self,p):
  from .engine import positive
  src=p['source'];dst=p['destination'];entity=self.authority(src,'payment');a=positive(p['amount']);rate=D(str(p.get('rate',7)));months=int(p.get('months',12))
  if dst not in self.accounts() or src==dst or not rate.is_finite() or not 0<=rate<=100 or not 1<=months<=360:raise ValueError('Invalid credit terms or counterparty')
  if self.is_frozen(src) or self.is_frozen(dst) or self.available_cash(src)<a:raise ValueError('Credit source or counterparty restricted/illiquid')
  if a>D(entity['payment_limit']):raise ValueError('Credit exceeds board-delegated payment limit')
  if a>D(self.metrics(src)['equity'])*D('.4'):raise ValueError('Single-counterparty credit exceeds40% of lender equity')
  borrower=self.metrics(dst)
  if D(borrower['equity'])<=0 or D(borrower['debt'])+a>D(borrower['equity'])*2 or rate>D(str(self.state['macro']['rate']))+10:raise ValueError('Counterparty rejects unsustainable funding terms')
  c=self.make_network_claim(src,dst,a,str(rate),months,'Signed institutional credit placement');self.audit('credit_offer_accepted',{'id':c['id'],'source':src,'destination':dst,'amount':str(a)});return c
 def issuer_earnings_observation(self,issuer):
  history=issuer.get('operating_history',[])[-30:];base=max(D(1),D(issuer['revenue_daily']))
  return sum((D(row['net_income']) for row in history),D(0))/(base*len(history)) if history else D(issuer['last_profit'])/base

 def issuer_reporting_day(self,issuer):
  # Fictional monthly reporting calendar; deterministic by issuer, not all at once.
  if 'earnings_reporting_day' not in issuer:issuer['earnings_reporting_day']=int(hashlib.sha256(issuer['symbol'].encode()).hexdigest()[:8],16)%30
  return issuer['earnings_reporting_day']

 def issuer_event(self,p):
  from .engine import positive
  issuer=self.state['issuers'][p['symbol']];account=issuer['account'];kind=p['kind']
  if kind=='dividend':
   if issuer['symbol'] in self.state.get('share_register',{}):raise ValueError('Listed dividends require an approved public shareholder resolution')
   per=positive(p['per_share']);holders=[pos for pos in self.state['positions'].values() if pos['symbol']==issuer['symbol']];required=(D(issuer['model_shares'])*per).quantize(D('.01'))
   if self.available_cash(account)<required:raise ValueError('Model issuer treasury cannot fund this distribution')
   for pos in holders:
    a=(D(pos['qty'])*per).quantize(D('.01'));self.post('Model issuer cash dividend '+issuer['symbol'],{'cash:'+account:-a,'equity:'+account:a,'cash:'+pos['account']:a,'pnl:'+pos['account']:-a})
   external=max(D(0),D(issuer['model_shares'])-sum((D(pos['qty']) for pos in holders),D(0)));a=(external*per).quantize(D('.01'))
   if a:self.post('Model external shareholder distribution '+issuer['symbol'],{'cash:'+account:-a,'equity:'+account:a,'cash:external_shareholders':a,'pnl:external_shareholders':-a})
   severity=-min(.1,float(per/max(D('.01'),D(self.state['instruments'][issuer['symbol']]['price'])*self.fx_rate(self.state['instruments'][issuer['symbol']]['currency']))));self.market_event({'symbol':issuer['symbol'],'kind':'guidance','severity':severity})
  elif kind=='liability_shock':
   a=positive(p['amount']);claim=self.create_claim('external_legal',account,a,'JUDGMENT','Modeled corporate liability shock');self.post('Model corporate judgment '+issuer['symbol'],{'expense:legal:'+account:a,'debt:'+account+':claim_'+claim['id']:-a,'claim:external_legal:'+claim['id']:a,'pnl:external_legal':-a});paid=min(a,self.available_cash(account))
   if paid:self.settle_claim_cash(claim,paid,'Model issuer judgment settlement')
   issuer['status']='DISTRESSED';self.market_event({'symbol':issuer['symbol'],'kind':'credit','severity':-.3})
  elif kind=='earnings':
   actual=self.issuer_earnings_observation(issuer);expected=D(issuer.get('earnings_expected_margin',str(actual)));opening=D(1)-D(issuer['cost_ratio']);old_index=max(D('.05'),1+expected-opening);new_index=max(D('.05'),1+actual-opening);surprise=max(D('-.2'),min(D('.2'),new_index/old_index-1))
   event=self.market_event({'symbol':issuer['symbol'],'kind':'earnings','severity':float(surprise)})
   event['earnings_evidence']=dict(actual_margin=str(actual),expected_margin=str(expected),observed_days=len(issuer.get('operating_history',[])[-30:]),basis='Trailing posted net income versus the prior disclosed run-rate; not a recurring discount against an assumed 20% margin')
   issuer['earnings_expected_margin']=str(actual);issuer['last_earnings_tick']=self.state['tick']
  elif kind=='buyback':
   quantity=int(p['qty']);entity=self.authority(account,'govern');self.authority(account,'payment')
   if D(str(p['qty']))!=quantity or not 0<quantity<issuer['model_shares']:raise ValueError('Repurchase a positive whole-share quantity below all issued capital')
   ins=self.instrument(issuer['symbol']);limit=positive(p.get('max_price',str(D(ins['price'])*D('1.01'))));notional=D(quantity)*limit*self.fx_rate(ins['currency']);budget=notional+max(D(1),(notional*D('.0005')).quantize(D('.01')))
   spending_ceiling=min(self.available_cash(account),D(entity['payment_limit']),max(D(0),D(self.metrics(account)['equity'])))
   if budget>spending_ceiling:raise ValueError('Repurchase exceeds unrestricted cash, solvent equity or board spending authority')
   # A price-limited IOC enforces the approved spend even if execution is thin.
   before_cash=self.cash(account);self._issuer_buyback_account=account
   try:order=self.order({'account':account,'symbol':issuer['symbol'],'qty':quantity,'side':'buy','type':'limit','limit':str(limit),'tif':'IOC'})
   finally:self._issuer_buyback_account=None
   if before_cash-self.cash(account)>spending_ceiling:raise ValueError('Actual repurchase fees exceed board spending authority or solvent resources')
   issuer['last_buyback']=order['id'];key=account+':'+issuer['symbol'];position=self.state['positions'].get(key)
   if position and D(order['filled'])>0:
    retired=int(D(order['filled']));cost=(D(position['cost'])*retired/D(position['qty'])).quantize(D('.01'));self.post('Model treasury shares retired '+issuer['symbol'],{'inventory:'+key:-cost,'equity:'+account:cost});position['qty']=str(D(position['qty'])-retired);position['cost']=amt(D(position['cost'])-cost)
    if not D(position['qty']):self.state['positions'].pop(key)
    issuer['model_shares']-=retired;register=self.state.get('share_register',{}).get(issuer['symbol'])
    if register:register['outstanding']=str(issuer['model_shares']);register['free_float']=str(max(D(0),D(register['free_float'])-retired));register['treasury']=str(D(position['qty']))
  else:raise ValueError('Unknown model issuer operation')
  self.audit('model_issuer_event',dict(p));return issuer
 def economy_policy(self,p):
  macro=self.state['macro']
  for key in ('demand','employment','confidence'):
   if key in p:
    value=float(p[key]);low,high=(0,1) if key=='employment' else (20,200) if key=='demand' else (0,100)
    if not math.isfinite(value) or not low<=value<=high:raise ValueError('Economic input outside model range')
    macro[key]=value
  self.audit('economic_assumptions',dict(p));return macro
 def economic_cycle(self):
  if self.state.get('fed'):
   f=self.state['fed'];o=f['observed'];self.state['macro'].update(rate=f['upper'],growth=o['growth'],inflation=o['headline'],employment=1-o['unemployment']/100,demand=f['latent']['spending']);self.state['economic_history'].append(dict(time=self.state['time'],**self.state['macro']));self.state['economic_history']=self.state['economic_history'][-500:];return
  m=self.state['macro'];prior=dict(m);stress=float(m['stress']);demand=m.get('demand',100);confidence=m.get('confidence',65);employment=m.get('employment',.94)
  growth=max(-8,min(8,1.8+.025*(demand-100)+.012*(confidence-65)-.3*(m['rate']-4)-.035*stress));inflation=max(-2,min(15,m['inflation']+.025*(demand-100)/10+.02*(growth-2)));employment=max(.7,min(.99,employment+.0008*(growth-2)));rate=max(0,min(20,m['rate']+(.25 if inflation>3 else -.25 if inflation<1.5 else 0)));demand=max(40,min(160,demand+.12*(confidence-65)/10+.08*(employment-.94)*100-.06*(rate-4)))
  m.update(growth=round(growth,3),inflation=round(inflation,3),employment=round(employment,5),rate=round(rate,2),demand=round(demand,3),recession_risk=round(max(0,min(1,.15-growth*.04+stress*.006)),3))
  severity=max(-.1,min(.1,-(rate-prior['rate'])*.025+(growth-prior['growth'])*.003))
  for sym in self.state['market_symbols']:
   if abs(severity)>.0001:self.market_event({'symbol':sym,'kind':'policy','severity':severity})
  self.state['economic_history'].append({'time':self.state['time'],**m});self.state['economic_history']=self.state['economic_history'][-500:]
 def economy_tick(self):
  w=self.state
  if not w.get('economy_active'):return
  # Defined circuit breakers, never a hidden source of liquidity.
  for sym in w['market_symbols']:
   ins=w['instruments'][sym]
   if ins.get('halt_until') and w['tick']>=ins['halt_until']:ins['status']='OPEN';ins.pop('halt_until')
   if ins['status']=='OPEN' and abs(D(ins['price'])/D(ins['previous'])-1)>D('.12'):
    ins['status']='HALTED';ins['halt_until']=w['tick']+3;self.news('Execution circuit breaker: '+sym,'Local price movement exceeded12% in one market hour; three-hour cooling period.','MARKET OPERATIONS')
  if w['tick']%24==0:
   m=w['macro']
   for issuer in w['issuers'].values():
    if issuer['status']=='DEFAULT' or self.state['entities'][issuer['account']]['status'] in ('ADMINISTRATION','DISSOLVED'):continue
    if issuer.get('last_result_tick')==w['tick']:continue
    if 'earnings_expected_margin' not in issuer:
     # Existing saves: use already-public observations, never manufacture a past
     # forecast or reverse historical transactions. New issuers use opening costs.
     issuer['earnings_expected_margin']=str(self.issuer_earnings_observation(issuer) if issuer.get('operating_history') else D(1)-D(issuer['cost_ratio']))
    # Board-approved policies spend actual issuer cash; they remain corporate
    # mandates after the shareholder changes, rather than depending on player UI.
    budget=D(issuer.get('daily_investment_budget',0));strategy=issuer.get('strategy','balanced');spent=D(0)
    if issuer.get('board_resolution') and strategy in ('growth','efficiency') and not self.is_frozen(issuer['account']):
     reserve=D(issuer['revenue_daily'])*D(issuer['cost_ratio'])*30+sum((D(e['salary']) for e in self.staff(issuer['account'])),D(0));spent=min(budget,D(w['entities'][issuer['account']]['payment_limit']),max(D(0),self.available_cash(issuer['account'])-reserve)).quantize(D('.01'))
     if spent:self.public_investment_post(issuer,spent)
    if issuer.get('direction'):issuer['direction'].update(observed='Daily authorised productive investment £'+amt(spent),last_review=w['time'])
    productivity=min(D('.2'),D(issuer.get('productivity_investment',0))/max(D(1),D(issuer['revenue_daily'])*D(issuer['cost_ratio'])*365)*D('.2'))
    demand=D(str(m.get('demand',100)))/100;confidence=D(str(.75+m.get('confidence',65)/260));revenue=min(self.balance('cash:economy_households'),(D(issuer['revenue_daily'])*demand*confidence*(1+D(issuer.get('capacity_investment',0))/max(D(1),D(issuer['revenue_daily'])*365))).quantize(D('.01')));cost=(D(issuer['revenue_daily'])*D(issuer['cost_ratio'])*(1+D(issuer.get('capacity_investment',0))/max(D(1),D(issuer['revenue_daily'])*365))*(1+D(str(m['inflation']))/1200)*(1-productivity)).quantize(D('.01'));cost=min(cost,self.cash(issuer['account'])+revenue);wages=(cost*D('.7')).quantize(D('.01'));supplier=cost-wages;profit=revenue-cost
    self.post('Model issuer operating cycle '+issuer['symbol'],{'cash:economy_households':wages-revenue,'expense:consumption:economy_households':revenue,'pnl:economy_households':-wages,'cash:'+issuer['account']:profit,'pnl:'+issuer['account']:-revenue,'expense:operations:'+issuer['account']:cost,'cash:economy_suppliers':supplier,'pnl:economy_suppliers':-supplier})
    total_net=-self.balance('pnl:'+issuer['account'])-sum((D(v) for k,v in self.ledger_items(issuer['account']) if k.startswith('expense:') and k.endswith(':'+issuer['account'])),D(0))
    net=total_net-D(issuer.get('accounted_net',issuer['cumulative_profit']));issuer['accounted_net']=amt(total_net)
    issuer.update(last_result_tick=w['tick'],last_revenue=amt(revenue),last_cost=amt(cost),last_profit=amt(net),cumulative_revenue=amt(D(issuer['cumulative_revenue'])+revenue),cumulative_profit=amt(total_net))
    issuer.setdefault('operating_history',[]).append(dict(tick=w['tick'],revenue=amt(revenue),net_income=amt(net),cash=amt(self.cash(issuer['account'])),payroll=amt(wages),materials=amt(supplier),operating_cost=amt(cost),investment=amt(spent)))
    issuer['operating_history']=issuer['operating_history'][-120:]
    if w['tick']>=720 and (w['tick']//24)%30==self.issuer_reporting_day(issuer) and issuer.get('last_earnings_tick')!=w['tick']:self.issuer_event({'symbol':issuer['symbol'],'kind':'earnings'})
   if w['tick']%168==0:self.economic_cycle()
  debtors={key.split(':',2)[1] for key,value in w['balances'].items() if key.startswith('debt:') and D(value)<0}
  for entity in list(w['entities'].values()):
   if entity['id'] not in debtors or entity['kind'] in ('central_bank','sovereign'):continue
   if entity['kind'] not in ('issuer','credit_fund','investment_bank') or entity['status']!='ACTIVE':continue
   m=self.metrics(entity['id'])
   if D(m['equity'])<0 and D(m['debt'])>0:
    # Court/system appointment follows recorded insolvency, not player control.
    from .engine import uid
    admin={'id':uid(),'entity':entity['id'],'status':'ADMINISTRATION','time':w['time'],'distributions':[],'shortfall':m['debt']};w['administrations'].append(admin);entity['status']='ADMINISTRATION'
    for c in w['claims_book']:
     if c['debtor']==entity['id']:c['status']='DEFAULT'
    for issuer in w['issuers'].values():
     if issuer['account']==entity['id']:issuer['status']='DEFAULT'
    w['network_events'].append({'time':w['time'],'entity':entity['id'],'type':'INSOLVENCY','debt':m['debt'],'exposure_claims':[c['id'] for c in w['claims_book'] if c['debtor']==entity['id']]});self.news('Model institution enters administration',entity['name']+' has recorded negative equity and creditor obligations. Actual exposure holders face recoveries and losses.','CREDIT CONTAGION')
  for bank in w['banks']:
   ratio=D(bank['equity'])/max(D(1),D(bank['cash'])+D(bank['loans'])-D(bank.get('allowance','0')))
   if ratio<D('.08') or D(bank['cash'])<D(bank['deposits'])*D('.02'):bank['status']='DISTRESSED'
