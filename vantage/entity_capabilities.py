"""Canonical fund membership and funded entity capabilities; no authority bypass."""
import copy
from decimal import Decimal as D
from .integrity import amt

class EntityCapabilitiesMixin:
 def is_fund(self,account):return any(f['id']==account for f in self.state.get('funds',[]))
 def fund_register(self,p):
  id=p['entity'];e=self.authority(id,'govern')
  if self.is_fund(id):raise ValueError('Entity already has an investor-unit register')
  if e['kind']!='credit_fund' or e['status']!='ACTIVE' or self.is_frozen(id):raise ValueError('Only an unrestricted active credit company can adopt investor units')
  nav=D(self.metrics(id)['equity']);units=D(e['units'])
  if nav<=0 or units<=0:raise ValueError('Positive NAV and an existing shareholder register are required')
  owners=copy.deepcopy(e['owners']);lines={}
  for owner in owners:self.authority(owner,'govern')
  if e['controls']>=2:self.authority(id,'govern','board')
  for owner in owners:
   basis=self.balance('holding:'+owner+':'+id)
   if basis:lines['holding:'+owner+':'+id]=-basis;lines['investment:'+owner+':'+id]=basis
  if lines:self.post('Credit fund investor-unit adoption '+id,lines)
  f=dict(id=id,name=e['name'],fund_type='credit_fund',units=str(units),highwater=str(nav/units),reported=amt(nav),management=0,performance=0,compensation_authorized=False,investors=owners,lock_until=self.state['tick'],manager=e.get('parent') or 'personal')
  self.state['funds'].append(f);e['previous_share_register']={'owners':owners,'units':str(units)};e['owners']={};e['units']='0';self.audit('credit_fund_unit_registration',{'entity':id,'owners_preserved':owners,'positions_and_claims_preserved':True});return f
 def fund_contribute(self,p):
  from .engine import positive
  f=next(f for f in self.state['funds'] if f['id']==p['fund']);owner=p.get('owner','personal');e=self.authority(owner,'payment');self.authority(f['id'],'govern');amount=positive(p['amount'])
  if self.is_frozen(owner) or self.is_frozen(f['id']) or owner==f['id']:raise ValueError('Restricted or self-subscription prohibited')
  if amount>D(e['payment_limit']) or amount>self.available_cash(owner):raise ValueError('Subscription exceeds existing payment authority or unrestricted cash')
  if self.is_fund(owner) and not e['mandate']['related_parties']:raise ValueError('Owner fund mandate does not permit fund-of-funds subscriptions')
  nav=D(self.metrics(f['id'])['equity']);units=D(f['units'])
  if nav<=0 or units<=0:raise ValueError('Fund has no positive subscription NAV')
  # A fund cannot subscribe into a company/fund that beneficially owns it.
  pending=[owner];seen=set()
  while pending:
   account=pending.pop()
   if account==f['id']:raise ValueError('Fund subscription would create cyclic ownership')
   if account in seen:continue
   seen.add(account);ff=next((v for v in self.state['funds'] if v['id']==account),None);pending.extend((ff or {}).get('investors',self.state['entities'].get(account,{}).get('owners',{})))
  issued=(amount*units/nav).quantize(D('.00000001'),rounding='ROUND_DOWN')
  if issued<=0:raise ValueError('Subscription below unit precision')
  self.post('Owner fund-unit subscription '+f['id'],{'cash:'+owner:-amount,'investment:'+owner+':'+f['id']:amount,'cash:'+f['id']:amount,'equity:'+f['id']:-amount});f['units']=str(units+issued);f['investors'][owner]=str(D(f['investors'].get(owner,0))+issued);self.audit('owner_fund_subscription',{'fund':f['id'],'owner':owner,'amount':amt(amount),'units':str(issued)});return {'fund':f['id'],'owner':owner,'units':str(issued)}
 def entity_capabilities(self):
  result={}
  for id,e in self.state.get('entities',{}).items():
   if not e.get('controlled'):continue
   fund=next((f for f in self.state['funds'] if f['id']==id),None);enabled=not self.is_frozen(id) and e['status']=='ACTIVE'
   result[id]={'fund_type':(fund or {}).get('fund_type','investment_fund' if fund else None),'investor_units':bool(fund),'fundraising':bool(fund) and enabled,'adopt_credit_fund_units':not fund and e['kind']=='credit_fund' and enabled,'company_investment':enabled and (not fund or e['mandate']['related_parties']),'operating_budget':enabled,'loans':enabled,'restrictions':self.restriction_summary(id),'note':'Capabilities never replace signatory authority, mandate, cash, board or creditor checks.'}
  return result
