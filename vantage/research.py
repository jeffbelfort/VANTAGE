"""Commissioned, time-consuming research based on current disclosed model evidence."""
import copy,math,random,statistics
from decimal import Decimal as D
from .integrity import amt
from .execution import depth

class ResearchMixin:
 def install_research(self):
  if self.state.get('stock_research_version'):return
  self.state.setdefault('stock_research',[]);self.state['stock_research_version']=1
  self.audit('stock_research_installed',{'version':1,'historical_reports_unchanged':True})
 def research_fundamentals(self,symbol,include_debt=True):
  ins=self.instrument(symbol);f=copy.deepcopy(ins.get('fundamentals',{}));source=ins.get('fundamentals_quality','SIMULATED')
  if f.get('profit') is not None and f.get('shares') is not None:return f,source
  issuer=self.state.get('issuers',{}).get(symbol)
  if not issuer or D(issuer.get('last_revenue','0'))<=0:return f,source
  # The public issuer profile already exposes these posted model results. These
  # are annualised observations, never real-company reference data or forecasts.
  fx=self.fx_rate(ins['currency']);register=self.state.get('share_register',{}).get(symbol,{});debt=None
  if include_debt:debt=sum((-D(value) for key,value in self.state['balances'].items() if key.startswith('debt:'+issuer['account']+':') and D(value)<0),D(0))
  f.update(revenue=str(D(issuer['last_revenue'])*365/fx),profit=str(D(issuer['last_profit'])*365/fx),shares=str(register.get('outstanding',issuer['model_shares'])),debt=str(debt/fx) if debt is not None else None)
  return f,'SIMULATED ISSUER: latest posted operating day annualised; not real reported financials'

 def observed_equity_trend(self,symbol):
  ins=self.instrument(symbol);tick=self.state['tick'];bars=[bar for bar in ins.get('history',[]) if 0<=bar.get('t',-1)<=tick and float(bar['c'])>0][-120:];closes=[float(bar['c']) for bar in bars];price=float(ins['price']);returns=[math.log(b/a) for a,b in zip(closes,closes[1:])];sigma=statistics.pstdev(returns) if len(returns)>1 else 0.;long=price/closes[0]-1 if closes else 0.;average=statistics.fmean(closes[-24:]) if closes else price;fast=price/average-1 if average else 0.;noise=sigma*math.sqrt(max(1,len(returns)));strength=math.log1p(long)/max(.0001,noise);enough=len(closes)>=9;volume=sum(float(bar.get('v',0)) for bar in bars[-24:])
  return dict(observations=len(closes),return_fraction=long,above_recent_average=fast,trend_strength=strength,observed_hourly_volatility=sigma,volume=volume,information_tick=tick,enough_history=enough,source='Only recorded simulation prices at or before the decision; opening reference candles excluded')

 def request_analysis(self,p):
  entity=p['entity'];self.employee_entity(entity);symbol=self.instrument(p['symbol'])['symbol']
  if symbol not in self.state['instruments']:raise ValueError('Commission research on an underlying security, not an option contract')
  analysts=[e for e in self.staff(entity) if e['role']=='analyst' and (not p.get('analyst') or e['id']==p['analyst'])]
  if not analysts:raise ValueError('Hire an investment analyst at this institution before requesting analysis')
  load=lambda e:sum(t['employee']==e['id'] and t['status'] in ('QUEUED','AWAITING APPROVAL') for t in self.state['employee_tasks'])
  e=min(analysts,key=lambda e:(load(e),-e['competence']))
  if load(e)>=3:raise ValueError('Analyst workload is full')
  if any(t['employee']==e['id'] and t['kind']=='analysis' and t['instruction'].get('symbol')==symbol and t['status']=='QUEUED' for t in self.state['employee_tasks']):raise ValueError('This analyst is already researching that security')
  cost=D(250)
  if cost>D(self.authority(entity,'govern')['payment_limit']):raise ValueError('Research cost exceeds delegated institution authority')
  if self.available_cash(entity)<cost:raise ValueError('Research requires £250 unrestricted operating cash')
  self.post('Commissioned security research: '+symbol,{'expense:research:'+entity:cost,'cash:'+entity:-cost,'cash:research_suppliers':cost,'pnl:research_suppliers':-cost})
  from .engine import uid
  task=dict(id=uid(),employee=e['id'],entity=entity,kind='analysis',instruction={'symbol':symbol},status='QUEUED',due=self.state['tick']+max(4,12-e['competence']//15),time=self.state['time'],approved=False,result=None,cost=amt(cost))
  self.state['employee_tasks'].append(task);self.employee_log(e,'research_commissioned','Research '+symbol+'; £250 operating expenditure',task['id']);return task
 def complete_analysis(self,e,task):
  from .engine import uid
  w=self.state;ins=self.instrument(task['instruction']['symbol']);price=D(ins['price']);f,fundamentals_source=self.research_fundamentals(ins['symbol']);macro=copy.deepcopy(w['macro']);bars=copy.deepcopy([b for b in ins.get('history',[]) if b.get('t',w['tick'])<=w['tick']][-168:]);closes=[float(b['c']) for b in bars if float(b['c'])>0]
  if w.get('fed'):macro['us_monetary_policy']=dict(target_range=[w['fed']['lower'],w['fed']['upper']],yield_curve=copy.deepcopy(w['fed']['curve']),expected_change=w['fed'].get('expectations',{}).get('expected_change',0))
  changes=[math.log(b/a) for a,b in zip(closes,closes[1:])];vol=statistics.pstdev(changes)*math.sqrt(252*8) if len(changes)>1 else None
  known=lambda key:f.get(key) is not None and math.isfinite(float(f[key]))
  revenue=D(str(f['revenue'])) if known('revenue') else None;profit=D(str(f['profit'])) if known('profit') else None;debt=D(str(f['debt'])) if known('debt') else None;shares=D(str(f['shares'])) if known('shares') else None
  expected_profit=profit*D(ins.get('public_earnings_factor','1')) if profit is not None else None
  eps=expected_profit/shares if profit is not None and shares and shares>0 else None;pe=price/eps if eps and eps>0 else None;margin=profit/revenue if profit is not None and revenue and revenue>0 else None;debt_revenue=debt/revenue if debt is not None and revenue and revenue>0 else None
  rng=random.Random(e['id']+str(w['tick'])+ins['symbol']);bias=(rng.random()-.5)*(1-e['competence']/120);multiple=max(5,min(30,18+float(macro.get('growth',0))-float(macro.get('rate',0))*.7-float(macro.get('stress',0))*.04))
  if fundamentals_source.startswith('SIMULATED ISSUER'):
   issuer=w['issuers'][ins['symbol']];base=float(issuer.get('opening_earnings_multiple',18));multiple=max(5,min(60,base+float(macro.get('growth',0))-float(macro.get('rate',0))*.7-float(macro.get('stress',0))*.04))
  reasons=[];uncertainties=['Model estimates are fallible; prices and liquidity may change.','No future news or scheduled events were used.'];risks=[];bull=[];bear=[]
  if fundamentals_source.startswith('SIMULATED ISSUER'):uncertainties.append('Annualised latest-day model results are not a full-year earnings history; margins can change. The valuation multiple starts from the fictional economy’s disclosed opening earnings-yield calibration, adjusted for current macro conditions and analyst judgement.')
  if eps and eps>0:
   centre=eps*D(str(multiple*(1+bias)));basis='Earnings valuation: disclosed profit adjusted by published model revisions × assumed earnings multiple';reasons.append(f"EPS {eps:.4f}; assumed earnings multiple {multiple:.2f}, adjusted for analyst judgement.");confidence=min(90,e['competence']);width=D('.20')+D(str((100-e['competence'])/200))
  else:
   centre=D(str(statistics.median(closes))) if closes else price;centre*=D(str(1+float(macro.get('growth',0))/1000+bias*.1));basis='Market-history scenario range; independent intrinsic value unavailable';confidence=min(35,e['competence']);width=D('.35');uncertainties.append('Profit/share data do not support an independent earnings valuation.');reasons.append('Price-history scenario only; insufficient fundamentals for a high-confidence Buy opinion.')
  low=max(D('.01'),centre*(1-width));high=max(low,centre*(1+width));upside=centre/price-1
  recommendation='Buy' if eps and eps>0 and upside>D('.15') and confidence>=60 else 'Avoid' if (profit is not None and profit<0) or (debt_revenue is not None and debt_revenue>3) or (eps and eps>0 and upside<D('-.20')) else 'Hold'
  if revenue is None:uncertainties.append('Revenue unavailable.')
  if debt is None:uncertainties.append('Debt unavailable; balance-sheet strength cannot be fully assessed.')
  elif debt_revenue is not None and debt_revenue>1:risks.append('Debt exceeds annual revenue; refinancing sensitivity.');bear.append('Refinancing costs could erode profits.')
  if profit is not None and profit<0:risks.append('The company currently reports a loss.')
  if float(macro.get('rate',0))>4:risks.append('Elevated interest rates pressure financing and valuation multiples.')
  if vol is not None and vol>.4:risks.append('High observed price volatility increases downside uncertainty.')
  if profit is not None and profit>0:bull.append('Sustained earnings could support valuation if the assumed multiple holds.')
  if float(macro.get('growth',0))>0:bull.append('Positive model economic growth may support demand; this is an assumption.')
  bear.append('A lower earnings multiple or weaker growth would reduce the estimated range.');risks.append('Liquidity can disappear before an order executes.')
  levels=self.book_depth(ins['symbol']) if ins['symbol'] in w.get('market_symbols',[]) else depth(ins,w['tick'])
  evidence=dict(observed_trend=self.observed_equity_trend(ins['symbol']),public_earnings_factor=ins.get('public_earnings_factor','1'),expected_model_profit=str(expected_profit) if expected_profit is not None else None,fundamentals=f,fundamentals_quality=fundamentals_source,price=str(price),currency=ins['currency'],sector=ins.get('sector'),macro=macro,price_history=bars,observed_volatility=vol,market_depth=copy.deepcopy(levels),ratios={'eps':str(eps) if eps is not None else None,'pe':str(pe) if pe is not None else None,'profit_margin':str(margin) if margin is not None else None,'debt_to_revenue':str(debt_revenue) if debt_revenue is not None else None})
  report=dict(id=uid(),entity=e['entity'],analyst=e['id'],analyst_name=e['name'],symbol=ins['symbol'],time=w['time'],tick=w['tick'],recommendation=recommendation,fair_low=amt(low),fair_high=amt(high),fair_centre=amt(centre),currency=ins['currency'],confidence=confidence,valuation_basis=basis,assumptions={'earnings_multiple':multiple,'analyst_adjustment':bias,'range_width':str(width)},reasoning=reasons,bullish_catalysts=bull,bearish_catalysts=bear,risks=risks,uncertainties=uncertainties,evidence=evidence,task=task['id'],assessment_due=w['tick']+168,outcome=None)
  w['stock_research'].append(report);self.employee_log(e,'analysis_published',ins['symbol']+': '+recommendation,report['id']);return report
 def research_tick(self):
  for report in self.state.get('stock_research',[]):
   if report['outcome'] is not None or self.state['tick']<report['assessment_due']:continue
   price=D(self.instrument(report['symbol'])['price']);start=D(report['evidence']['price']);movement=price/start-1;prediction=report['recommendation'];correct=movement>0 if prediction=='Buy' else movement<0 if prediction=='Avoid' else abs(movement)<=D('.1')
   report['outcome']={'time':self.state['time'],'tick':self.state['tick'],'price':str(price),'price_return':str(movement),'direction_correct':bool(correct),'method':'Seven simulation days of price change; excludes dividends, fees and risk adjustment; not a guarantee of future accuracy'}
   employee=next((e for e in self.state['employees'] if e['id']==report['analyst']),None)
   if employee:
    score=employee.setdefault('research_performance',{'assessed':0,'direction_correct':0});score['assessed']+=1;score['direction_correct']+=int(correct);self.employee_log(employee,'research_assessed',report['symbol']+' assessed using subsequently observed market price',report['id'])
 def research_views(self):
  rows=copy.deepcopy(self.state.get('stock_research',[]))
  for r in rows:
   movement=abs(D(self.instrument(r['symbol'])['price'])/D(r['evidence']['price'])-1);r['age_hours']=self.state['tick']-r['tick'];r['stale']=r['evidence'].get('public_earnings_factor','1')!=self.instrument(r['symbol']).get('public_earnings_factor','1') or r['age_hours']>=168 or movement>=D('.1') or r['evidence']['macro']!=self.state['macro'];r['staleness_reason']='Older than seven simulation days, price moved at least 10%, or macro conditions changed' if r['stale'] else 'Within freshness thresholds; estimates remain uncertain'
  return rows
