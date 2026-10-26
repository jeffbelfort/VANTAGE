"""Additive operating records; legacy aggregate workforce remains authoritative.
All purchases and deliveries use the existing journal and funded counterparties.
"""
import copy
from decimal import Decimal as D
from .integrity import amt

SECTOR_OPERATIONS = {
 'professional services': {'offering':'Consulting engagement','department':'Consulting','days':10,'staff':2,'equipment':False},
 'technology': {'offering':'Enterprise software implementation','department':'Engineering','days':20,'staff':3,'equipment':False},
 'healthcare': {'offering':'Clinical service programme','department':'Clinical services','days':14,'staff':3,'equipment':True},
}

from .public_ownership import PublicOwnershipMixin

class CompanyOperationsMixin(PublicOwnershipMixin):
 def workforce_view(self,entity):
  b=self.state.get('private_businesses',{}).get(entity,{});people=self.staff(entity)
  aggregate=int(b.get('employee_count',0));named=len(people)
  annual=D(b.get('annual_payroll','0'));monthly=sum((D(e['salary']) for e in people),D(0))
  contracts=b.get('engagements',[]);assigned=sum(int(c['staff']) for c in contracts if c['status']=='ACTIVE')
  department=SECTOR_OPERATIONS.get(b.get('sector'),{}).get('department','Operations')
  return dict(entity=entity,aggregate_headcount=aggregate,named_headcount=named,headcount=aggregate+named,
   annual_aggregate_payroll=amt(annual),monthly_payroll=amt(annual/12+monthly),
   unpaid=amt(max(D(0),-self.balance('debt:'+entity+':workforce'))+sum((D(e['unpaid']) for e in people),D(0))),
   assigned=assigned,available=max(0,aggregate-assigned),departments=[dict(name=department,headcount=aggregate,assigned=assigned)],
   note='Issuer baseline wage expense is aggregate; no historical individual headcount is inferred. Named staff have separate earned payroll.' if self.state['entities'].get(entity,{}).get('kind')=='issuer' else 'Existing workforce is an aggregate team, not invented individual employment records. Named institutional staff have separate earned payroll.')

 def commercial_budget(self,customer):
  business=self.state.get('private_businesses',{}).get(customer)
  issuer=next((i for i in self.state.get('issuers',{}).values() if i['account']==customer),None)
  revenue=D(business['annual_revenue']) if business else D(issuer['revenue_daily'])*365 if issuer else D(0)
  used=D(0)
  for other in self.state.get('private_businesses',{}).values():
   for c in other.get('engagements',[]):
    if c['client']!=customer or c.get('started',-8760)<self.state['tick']-8760:continue
    if c['status']=='ACTIVE':used+=D(c['fee'])
    elif c['status'] in ('COMPLETED','BREACHED'):used+=D(c['earned'])
  return max(D(0),revenue*D('.05')-used)

 def company_operate(self,p):
  if self.state['entities'].get(p['entity'],{}).get('kind')=='issuer':
   if p['kind']=='equipment':return self.public_productive_investment(p)
   raise ValueError('Use named Employees recruitment for listed issuers; aggregate commercial contracts are not modelled')
  from .engine import positive,uid
  id=p['entity'];e=self.authority(id,'govern');b=self.state.get('private_businesses',{}).get(id)
  if not b or e['status']!='ACTIVE' or self.is_frozen(id):raise ValueError('An active unrestricted operating company is required')
  kind=p['kind'];suppliers=self.ma_account('suppliers')
  if kind=='hire':
   count=int(p.get('count',1))
   if D(str(p.get('count',1)))!=count:raise ValueError('Recruitment headcount must be a whole number')
   if not 1<=count<=100:raise ValueError('Recruit between 1 and 100 aggregate operating staff')
   if not b['employee_count']:raise ValueError('No existing role salary benchmark; use named recruitment')
   annual=D(b['annual_payroll'])/b['employee_count'];fee=(annual*D('.08')*count).quantize(D('.01'))
   self.authority(id,'payment')
   if fee>self.available_cash(id) or fee>D(e['payment_limit']) or (D(b['annual_payroll'])+annual*count)/12+sum((D(person['salary']) for person in self.staff(id)),D(0))>D(e['payment_limit']):raise ValueError('Recruitment exceeds company funding or monthly payroll authority')
   self.post('Operating team recruitment '+id,{'cash:'+id:-fee,'expense:recruitment:'+id:fee,'cash:'+suppliers:fee,'pnl:'+suppliers:-fee})
   b['employee_count']+=count;b['annual_payroll']=amt(D(b['annual_payroll'])+annual*count)
  elif kind=='equipment':
   self.ma_expand(p)
   # Actual purchased productive assets; clinical capacity is an explicit new capability.
   b['service_equipment']=amt(D(b.get('service_equipment','0'))+D(str(p['amount'])))
  elif kind=='proposal':
   spec=SECTOR_OPERATIONS.get(b['sector'])
   if not spec:raise ValueError('Negotiated service engagements are not implemented for this sector')
   contracts=b.setdefault('engagements',[])
   if any(c['status']=='PROPOSED' for c in contracts):raise ValueError('Decide the existing proposal first')
   if len([c for c in contracts if c['status']=='ACTIVE'])>=8:raise ValueError('Commercial pipeline is full')
   cost=D(b['annual_payroll'])/max(1,b['employee_count'])/365*spec['staff']*spec['days']
   fee=(cost*D('1.6')).quantize(D('.01'))
   candidates=[]
   for target,other in self.state.get('private_businesses',{}).items():
    if target!=id:candidates.append((target,D(other['annual_revenue'])))
   for issuer in self.state.get('issuers',{}).values():
    candidates.append((issuer['account'],D(issuer['revenue_daily'])*365))
   eligible=[]
   for target,revenue in candidates:
    if p.get('customer') and target!=p['customer']:continue
    if self.is_frozen(target) or self.state['entities'][target]['status']!='ACTIVE':continue
    # Counterparty procurement is finite and reflects its existing business scale.
    if self.available_cash(target)>=fee and fee<=self.commercial_budget(target):eligible.append(target)
   if not eligible:raise ValueError('No eligible funded operating customer with sufficient procurement budget')
   client=eligible[0]
   if self.available_cash(client)<fee:raise ValueError('Customer sector lacks funds for another engagement')
   contracts.append(dict(id=uid(),name=spec['offering'],status='PROPOSED',staff=spec['staff'],days=spec['days'],completed=0,
    fee=amt(fee),earned='0.00',client=client,created=self.state['tick'],expires=self.state['tick']+168))
  elif kind in ('accept','decline'):
   c=next((c for c in b.get('engagements',[]) if c['id']==p['contract']),None)
   if not c or c['status']!='PROPOSED':raise ValueError('Choose an outstanding customer proposal')
   if kind=='decline':c['status']='DECLINED'
   else:
    if self.state['tick']>c['expires']:raise ValueError('Customer proposal expired')
    if self.workforce_view(id)['available']<c['staff']:raise ValueError('Insufficient unassigned operating staff')
    if SECTOR_OPERATIONS[b['sector']]['equipment'] and D(b.get('service_equipment',0))<D(10000):raise ValueError('Programme requires at least £10,000 of newly procured clinical equipment')
    fee=D(c['fee']);client=c['client']
    if self.state['entities'].get(client,{}).get('controlled'):
     customer_authority=self.authority(client,'payment')
     if fee>D(customer_authority['payment_limit']):raise ValueError('Customer procurement exceeds delegated spending authority')
    if fee>self.commercial_budget(client):raise ValueError('Customer procurement budget is no longer available')
    if self.is_frozen(client) or self.state['entities'][client]['status']!='ACTIVE':raise ValueError('Customer can no longer enter the contract')
    if self.available_cash(client)<fee:raise ValueError('Customer funding no longer available')
    # Advance is a liability until earned; segregated funded escrow prevents double spending.
    escrow='engagement_'+c['id'];c['escrow']=escrow
    self.post('Funded service advance '+c['id'],{'cash:'+client:-fee,'escrow:'+client+':'+c['id']:fee,'cash:'+escrow:fee,'debt:'+escrow+':advance':-fee})
    c.update(status='ACTIVE',started=self.state['tick'],deadline=self.state['tick']+(c['days']+7)*24)
  else:raise ValueError('Unknown operating instruction')
  detail=copy.deepcopy(p)
  if kind in ('proposal','accept'):
   customer=(contracts[-1] if kind=='proposal' else c)['client'];detail.update(customer=customer,supplier_roots=self.ownership_roots(id),customer_roots=self.ownership_roots(customer))
  self.audit('company_operation',detail);return self.workforce_view(id)

 def company_delivery_tick(self,id,b):
  w=self.state;delivered=D(0)
  for c in b.get('engagements',[]):
   if c['status']=='PROPOSED' and w['tick']>c['expires']:c['status']='EXPIRED'
   if c['status']!='ACTIVE' or w['tick']<=c['started']:continue
   escrow=c['escrow']
   if w['tick']>c['deadline'] or w['entities'][id]['status']!='ACTIVE':
    remaining=self.cash(escrow)
    if remaining:self.post('Unfulfilled service advance refund '+c['id'],{'cash:'+escrow:-remaining,'debt:'+escrow+':advance':remaining,'cash:'+c['client']:remaining,'escrow:'+c['client']+':'+c['id']:-remaining})
    c['status']='BREACHED';continue
   # Unpaid operating wages constrain delivery; no unlimited parallel engagements.
   if -self.balance('debt:'+id+':workforce')>D(b['annual_payroll'])/12:continue
   c['completed']+=1;target=(D(c['fee'])*c['completed']/c['days']).quantize(D('.01'));earned=target-D(c['earned'])
   self.post('Earned service delivery '+c['id'],{'cash:'+escrow:-earned,'debt:'+escrow+':advance':earned,'cash:'+id:earned,'pnl:'+id:-earned,'expense:services:'+c['client']:earned,'escrow:'+c['client']+':'+c['id']:-earned})
   delivered+=earned;c['earned']=amt(target)
   if c['completed']>=c['days']:c['status']='COMPLETED'
  return delivered

 def public_company_registry(self):
  rows=[]
  for symbol,issuer in self.state.get('issuers',{}).items():
   ins=self.state['instruments'].get(symbol,{})
   if not ins:continue
   view=self.public_ownership(symbol);account=issuer['account'];outstanding=D(view['outstanding'])
   rows.append(dict(id=account,symbol=symbol,name=ins['name'],sector=issuer.get('sector',ins.get('sector')),outstanding=view['outstanding'],
    price=ins['price'],currency=ins['currency'],market_cap_gbp=amt(outstanding*D(ins['price'])*self.fx_rate(ins['currency'])),
    cash=amt(self.cash(account)),liabilities=self.metrics(account)['debt'],cumulative_revenue=issuer.get('cumulative_revenue'),cumulative_profit=issuer.get('cumulative_profit'),
    shareholders=view['shareholders'],ownership=view,controlled=self.state['entities'][account].get('controlled',False),source=issuer.get('source','Legacy model issuer'),
    limitation=view['status']+'. Model ordinary voting shares; underlying nominee clients may be undisclosed. Public resolutions require recorded votes. Cash-backed public tenders are available. Nominee clients can issue aggregated tender instructions. Specialist sector approvals and take-private settlement are not implemented.'))
  return rows
