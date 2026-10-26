"""Funded capital calls, operating businesses and read-only group accounts."""
import copy
from decimal import Decimal as D
from .integrity import amt

SECTORS={'services':('.004','.65',2),'manufacturing':('.003','.75',5),'technology':('.0035','.6',3)}
class EmpireFinanceMixin:
 def pe_commit(self,p):
  from .engine import positive,uid
  f=next(f for f in self.state['funds'] if f['id']==p['fund']);self.authority(f['id'],'disclose');n=next(n for n in self.state['npcs'] if n['id']==p['investor']);amount=positive(p['amount'])
  if f.get('fund_type')!='private_equity' or self.is_frozen(f['id']):raise ValueError('Unrestricted private equity fund required')
  commitments=self.state.setdefault('capital_commitments',[]);prior=sum((D(r['committed']) for r in commitments if r['investor']==n['id']),D(0))
  if prior+amount>D(self.investor_aum(n))*D('.25'):raise ValueError('Commitment exceeds allocator mandate of 25% of actual investor assets')
  r={'id':uid(),'fund':f['id'],'investor':n['id'],'committed':amt(amount),'paid':'0.00','time':self.state['time']};commitments.append(r);self.audit('pe_commitment',copy.deepcopy(r));return r
 def pe_call(self,p):
  from .engine import positive,uid
  fund=p['fund'];self.authority(fund,'govern')
  if self.is_frozen(fund):raise ValueError('Restricted fund cannot call capital')
  if any(c['fund']==fund and c['status']=='PARTIAL' for c in self.state.get('capital_calls',[])):raise ValueError('Process the existing unpaid capital call first')
  rows=[r for r in self.state.get('capital_commitments',[]) if r['fund']==fund and D(r['paid'])<D(r['committed'])];available=sum((D(r['committed'])-D(r['paid']) for r in rows),D(0));amount=positive(p['amount'])
  if amount>available:raise ValueError('Call exceeds uncalled commitments')
  allocations=[];left=amount
  for i,r in enumerate(rows):
   due=left if i==len(rows)-1 else (amount*(D(r['committed'])-D(r['paid']))/available).quantize(D('.01'),rounding='ROUND_DOWN');left-=due;allocations.append({'commitment':r['id'],'due':amt(due),'paid':'0.00'})
  call={'id':uid(),'fund':fund,'amount':amt(amount),'allocations':allocations,'status':'PARTIAL','time':self.state['time']};self.state.setdefault('capital_calls',[]).append(call);return self.pe_call_process({'id':call['id']})
 def pe_call_process(self,p):
  call=next(c for c in self.state.get('capital_calls',[]) if c['id']==p['id']);self.authority(call['fund'],'govern')
  if call['status']=='PAID':raise ValueError('Capital call already settled')
  if self.is_frozen(call['fund']):raise ValueError('Fund is restricted')
  for allocation in call['allocations']:
   r=next(r for r in self.state['capital_commitments'] if r['id']==allocation['commitment']);n=next(n for n in self.state['npcs'] if n['id']==r['investor']);due=D(allocation['due'])-D(allocation['paid']);pay=min(due,D(n['wealth'])).quantize(D('.01'),rounding='ROUND_DOWN')
   if pay<=0:continue
   try:
    self._capital_call_context=(call['fund'],n['id']);self.subscribe({'fund':call['fund'],'investor':n['id'],'amount':pay})
   finally:self._capital_call_context=None
   r['paid']=amt(D(r['paid'])+pay);allocation['paid']=amt(D(allocation['paid'])+pay)
  call['status']='PAID' if all(D(a['paid'])==D(a['due']) for a in call['allocations']) else 'PARTIAL';self.audit('pe_capital_call',copy.deepcopy(call));return call
 def productive_value(self,account):return self.balance('productive:'+account)
 def business_start(self,p):
  from .engine import positive
  id=p['entity'];e=self.authority(id,'govern');self.authority(id,'payment');capital=positive(p['capital']);sector=p.get('sector','services')
  if e['kind']!='company' or self.is_fund(id) or self.is_frozen(id) or sector not in SECTORS:raise ValueError('Unrestricted operating company and a supported sector required')
  if capital>self.available_cash(id) or capital>D(e['payment_limit']):raise ValueError('Productive investment exceeds unrestricted cash or payment mandate')
  self.post('Productive business capital expenditure '+id,{'cash:'+id:-capital,'productive:'+id:capital,'cash:operating_suppliers':capital,'pnl:operating_suppliers':-capital})
  model=self.state.setdefault('operating_businesses',{}).setdefault(id,{'entity':id,'sector':sector,'revenue':'0.00','costs':'0.00','status':'OPERATING','last_tick':self.state['tick']});model['sector']=sector;self.audit('productive_investment',{'entity':id,'capital':amt(capital),'sector':sector});return model
 def operating_business_tick(self):
  if self.state['tick']%24:return
  for id,model in self.state.get('operating_businesses',{}).items():
   if model.get('corporate_model'):continue
   if model['last_tick']==self.state['tick'] or self.is_frozen(id):continue
   model['last_tick']=self.state['tick'];capacity=self.productive_value(id)
   if capacity<=0:continue
   yield_rate,cost_ratio,required=SECTORS[model['sector']];staff=self.staff(id);coverage=min(D(1),D(len(staff))/(D(required)*max(D(1),capacity/D(250000))));quality=D(str(sum(e.get('competence',60) for e in staff)/max(1,len(staff))))/100;demand=D(str(self.state['macro'].get('demand',100)))/100;revenue=min(self.cash('economy_households'),capacity*D(yield_rate)*coverage*(D('.5')+quality/2)*demand).quantize(D('.01'));cost=(capacity*D(yield_rate)*D(cost_ratio)*max(D('.15'),coverage)).quantize(D('.01'));depreciation=min(capacity,(capacity/D(3650)).quantize(D('.01')))
   self.post('Operating company customer revenue '+id,{'cash:economy_households':-revenue,'expense:consumption:economy_households':revenue,'cash:'+id:revenue,'pnl:'+id:-revenue})
   self.post('Operating company materials and depreciation '+id,{'expense:business:'+id:cost,'debt:'+id+':business':-cost,'productive:'+id:-depreciation,'expense:depreciation:'+id:depreciation})
   paid=min(cost,self.available_cash(id))
   if paid:self.post('Operating company supplier settlement '+id,{'cash:'+id:-paid,'debt:'+id+':business':paid,'cash:operating_suppliers':paid,'pnl:operating_suppliers':-paid})
   model['revenue']=amt(D(model['revenue'])+revenue);model['costs']=amt(D(model['costs'])+cost);model['last_revenue']=amt(revenue);model['staff_coverage']=str(coverage)
 def consolidated_statement(self,p):
  root=p['entity'];self.authority(root,'disclose');w=self.state;members=[root];ownership={};investment_entity=self.is_fund(root)
  if not investment_entity:
   for parent in members:
    for e in w['entities'].values():
     units=D(e.get('units',0));share=D(e.get('owners',{}).get(parent,0))/units if units else D(0);threshold=D(str(e.get('reporting_control_threshold','.5')))
     if share>threshold and e['id'] not in members and not self.is_fund(e['id']) and e['status']!='MERGED':members.append(e['id']);ownership[e['id']]=share
  metrics={id:self.metrics(id) for id in members};assets=sum((D(m['equity'])+D(m['debt'])+(D(m['equity_gross'])-D(m['market']))/2 for m in metrics.values()),D(0));liabilities=sum((D(m['debt'])+(D(m['equity_gross'])-D(m['market']))/2 for m in metrics.values()),D(0));investments=D(0)
  for parent in members:
   for child in members:
    e=w['entities'][child];units=D(e.get('units',0));owned=D(e.get('owners',{}).get(parent,0))
    if units and owned:investments+=self.corporate_interest_value(child,metrics[child])*owned/units
  assets-=investments;claim_assets=D(0);claim_debts=D(0)
  for c in w['claims_book']:
   if c['creditor'] not in members or c['debtor'] not in members:continue
   debtor=c['debtor'];tangible=self.cash(debtor)+sum((D(v) for k,v in w['balances'].items() if k.startswith('savings:'+debtor+':')),D(0))+D(metrics[debtor]['market']);obligations=D(metrics[debtor]['debt']);other=sum((D(v) for k,v in w['balances'].items() if k.startswith(('claim:'+debtor+':','allowance:'+debtor+':','holding:'+debtor+':','investment:'+debtor+':'))),D(0));troubled=c['status'] in ('DEFAULT','OVERDUE') or w['entities'][debtor]['status'] in ('ADMINISTRATION','DISSOLVED') or tangible+other<obligations;recovery=min(D(1),max(D(0),tangible)/obligations) if obligations>0 and troubled else D(1);carrying=min(max(D(0),D(c['balance'])-D(c['allowance'])),D(c['balance'])*recovery);claim_assets+=carrying;claim_debts+=D(c['balance'])
  public_interests=[]
  for parent in members:
   for symbol,issuer in w.get('issuers',{}).items():
    position=w['positions'].get(parent+':'+symbol)
    if not position or D(position['qty'])<=0:continue
    public_interests.append(dict(holder=parent,issuer=issuer['account'],symbol=symbol,shares=position['qty'],market_value=amt(D(position['qty'])*D(self.instrument(symbol)['price'])*self.fx_rate(self.instrument(symbol)['currency'])),
     controlled=w['entities'][issuer['account']].get('controlled',False),treatment='Market investment retained; public issuer operations are not consolidated'))
  assets-=claim_assets;liabilities-=claim_debts;nci=sum(((1-ownership[id])*D(metrics[id]['equity']) for id in ownership),D(0));equity=assets-liabilities
  return {'entity':root,'time':w['time'],'method':'Investment entity: portfolio holdings at fair value, no client asset consolidation' if investment_entity else 'Controlled-group marked accounts; standalone legal liabilities remain enforceable','members':members,'public_interests_at_fair_value':public_interests,'assets':amt(assets),'liabilities':amt(liabilities),'equity':amt(equity),'non_controlling_interests':amt(nci),'attributable_group_equity':amt(equity-nci),'eliminations':{'equity_investments':amt(investments),'intercompany_claim_assets':amt(claim_assets),'intercompany_claim_debts':amt(claim_debts)},'root_available_cash':metrics[root]['available_cash'],'cash_by_legal_entity':{id:metrics[id]['cash'] for id in members},'restrictions':{id:self.restriction_summary(id) for id in members},'note':'Reporting elimination is not settlement or a parent guarantee. Group cash is not freely transferable. This is model group reporting, not statutory GAAP accounts or a goodwill/tax model. Public interests remain market investments; controlled listed-issuer operations are not consolidated.'}
 def administration_tick(self):
  for admin in self.state.get('administrations',[]):
   id=admin['entity'];basis=self.productive_value(id)
   if admin['status']=='DISSOLVED' or basis<=0:continue
   proceeds=min(basis*D('.5'),self.cash('operating_suppliers')).quantize(D('.01'));retired=min(basis,proceeds*2)
   if proceeds:self.post('Administrator productive asset realisation '+id,{'cash:operating_suppliers':-proceeds,'productive:operating_suppliers':proceeds,'cash:'+id:proceeds,'productive:'+id:-retired,'expense:realisation:'+id:retired-proceeds});admin.setdefault('productive_sales',[]).append({'time':self.state['time'],'cash':amt(proceeds),'book_disposed':amt(retired)})
  super().administration_tick()
