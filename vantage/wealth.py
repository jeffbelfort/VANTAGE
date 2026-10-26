"""Owned lifestyle assets: cost basis, model valuations, running liabilities and funded resale."""
import json,copy
from pathlib import Path
from decimal import Decimal as D
from .integrity import amt
CATALOGUE=json.loads((Path(__file__).resolve().parent.parent/'assets/lifestyle-catalogue.json').read_text())

class WealthMixin:
 def install_wealth(self):
  if self.state.get('wealth_version'):return
  self.state.setdefault('owned_assets',[]);self.state['wealth_version']=1
  self.audit('wealth_installed',{'version':1,'historical_accounts_unchanged':True})
 def lifestyle_authority(self,owner):
  e=self.authority(owner,'payment')
  if self.is_frozen(owner):raise ValueError('Owner is restricted from asset transactions')
  if self.is_fund(owner):raise ValueError('Investor fund capital cannot purchase lifestyle assets; use a valid separately recorded transfer first')
  return e
 def asset_buy(self,p):
  from .engine import uid
  owner=p.get('owner','personal');entity=self.lifestyle_authority(owner)
  if p.get('payer',owner)!=owner:raise ValueError('The legal owner must pay from its own account')
  item=next((c for c in CATALOGUE if c['id']==p['catalogue']),None)
  if not item:raise ValueError('Unknown catalogue asset')
  price=D(item['price'])
  if price>D(entity['payment_limit']) or price>self.available_cash(owner):raise ValueError('Purchase exceeds unrestricted cash or payment authority')
  asset=copy.deepcopy(item);asset.update(id='asset_'+uid(),catalogue=item['id'],owner=owner,purchase_price=amt(price),valuation=amt(price),acquired=self.state['time'],acquired_tick=self.state['tick'],cost_next=self.state['tick']+720,status='OWNED',unpaid='0.00',running_paid='0.00',sale=None,realised=None)
  self.post('Purchase '+asset['name']+' for '+entity['name'],{'asset:'+owner+':'+asset['id']:price,'cash:'+owner:-price,'cash:lifestyle_market':price,'pnl:lifestyle_market':-price});self.state['owned_assets'].append(asset);self.audit('asset_purchased',asset.copy())
  if self.state.get('living_world_version') and price>=100000:
   rep=self.state['personal_reputation'];rep['prominence']=min(100,rep['prominence']+2);rep['prestige']=min(100,rep['prestige']+1)
   self.world_article('purchase:'+asset['id'],entity['name']+' acquires '+asset['name'],[f"The recorded buyer paid £{price:,.2f} for {asset['name']}. Legal ownership rests with {entity['name']}.",f"Monthly maintenance and insurance commitments are £{D(asset['monthly_cost']):,.2f}. The purchase converts cash into an owned asset; it does not represent trading income."],'City After Hours',[owner,asset['id']])
   for employee in self.state.get('employees',[]):
    if employee['status']=='EMPLOYED' and employee['entity'] in self.controlled_accounts() and D(employee['unpaid'])>D(employee['salary']):
     employee['morale']=max(0,employee.get('morale',70)-10);rep['controversy']=min(100,rep['controversy']+1);self.employee_log(employee,'spending_concern','Luxury spending while earned wages are overdue',asset['id'])
  return asset
 def asset_sale(self,p):
  a=next((a for a in self.state['owned_assets'] if a['id']==p['asset']),None)
  if not a:raise ValueError('Owned asset not found')
  self.lifestyle_authority(a['owner'])
  if a['catalogue'].startswith('office_'):raise ValueError('Sell office buildings through Property & offices so occupancy is checked')
  if a['status']!='OWNED':raise ValueError('Asset is already listed or sold')
  if any(c['asset']==a['id'] and c['status']=='ACTIVE' for c in self.state.get('property_contracts',[])):raise ValueError('End the rental contract before listing a tenanted property')
  proceeds=(D(a['valuation'])*(1-D(a['discount']))).quantize(D('.01'));a['sale']={'listed':self.state['time'],'due':self.state['tick']+a['sale_hours'],'quote':amt(proceeds),'status':'FINDING BUYER'};a['status']='LISTED';self.audit('asset_listed',{'asset':a['id'],'owner':a['owner'],'quoted_proceeds':amt(proceeds),'due':a['sale']['due']});return a
 def wealth_tick(self):
  for a in self.state.get('owned_assets',[]):
   owner=a['owner'];id=a['id']
   if a['status']!='SOLD' and self.state['tick']>=a['cost_next']:
    a['cost_next']+=720;a['valuation']=amt(max(D('.01'),D(a['valuation'])*(1+D(a['annual_change'])/12)));cost=D(a['monthly_cost'])
    if cost:self.post('Asset maintenance and insurance: '+a['name'],{'expense:lifestyle:'+owner:cost,'debt:'+owner+':lifestyle_'+id:-cost});a['unpaid']=amt(D(a['unpaid'])+cost)
   # Existing unpaid running costs survive a sale and can settle when funding returns.
   paid=min(D(a['unpaid']),max(D(0),self.available_cash(owner)))
   if paid and not self.is_frozen(owner):
    self.post('Asset running cost settlement: '+a['name'],{'cash:'+owner:-paid,'debt:'+owner+':lifestyle_'+id:paid,'cash:lifestyle_suppliers':paid,'pnl:lifestyle_suppliers':-paid});a['unpaid']=amt(D(a['unpaid'])-paid);a['running_paid']=amt(D(a['running_paid'])+paid)
   if a['status']!='LISTED' or self.state['tick']<a['sale']['due'] or (self.is_frozen(owner) and not any(admin['entity']==owner and admin['id']==a['sale'].get('administrator') for admin in self.state.get('administrations',[]))):continue
   proceeds=D(a['sale']['quote']);cash=self.cash('lifestyle_market')
   if cash<proceeds:a['sale']['status']='AWAITING BUYER FUNDING';continue
   cost=D(a['purchase_price']);self.post('Asset resale: '+a['name'],{'cash:'+owner:proceeds,'asset:'+owner+':'+id:-cost,'pnl:'+owner:cost-proceeds,'cash:lifestyle_market':-proceeds,'pnl:lifestyle_market':proceeds});a['status']='SOLD';a['realised']=amt(proceeds-cost);a['sold_time']=self.state['time'];a['sale']['status']='PAID';a['sale']['proceeds']=amt(proceeds);self.audit('asset_sold',{'asset':id,'owner':owner,'proceeds':amt(proceeds),'realised':a['realised']})
 def asset_value(self,owner):return sum((D(a['valuation']) for a in self.state.get('owned_assets',[]) if a['owner']==owner and a['status']!='SOLD'),D(0))

 def property_lease(self,p):
  """Let a property to the existing, finite-funded household sector."""
  from .engine import uid
  a=next((a for a in self.state.get('owned_assets',[]) if a['id']==p['asset']),None)
  if not a or a['status']!='OWNED' or a['category'] not in ('Residential property','Commercial property','Offices'):raise ValueError('An owned residential or commercial property is required')
  entity=self.authority(a['owner'],'govern')
  if self.is_frozen(a['owner']):raise ValueError('Owner is restricted from new rental contracts')
  if any(o.get('asset')==a['id'] and o['status']=='ACTIVE' for o in self.state.get('offices',[])):raise ValueError('Vacate an occupied office before letting it to a tenant')
  leases=self.state.setdefault('property_contracts',[])
  if any(c['asset']==a['id'] and c['status']=='ACTIVE' for c in leases):raise ValueError('Property already has an active tenant')
  rent=D(str(p['rent']));months=int(p.get('months',12));cap=D(a['valuation'])*D('.12')/12
  if not rent.is_finite() or not 0<rent<=cap or not 1<=months<=60:raise ValueError('Rent must be positive and within the model 12% annual asking-yield cap; lease term 1–60 months')
  if rent>D(entity['payment_limit']):raise ValueError('Monthly rent exceeds entity governance authority')
  tenant='economy_households';committed=sum((D(c['rent']) for c in leases if c['status']=='ACTIVE'),D(0))
  if self.available_cash(tenant)<(committed+rent)*6:raise ValueError('Existing tenant sector lacks six months of available funding; no tenant cash is created')
  contract=dict(id='rental_'+uid(),asset=a['id'],owner=a['owner'],tenant=tenant,tenant_name='Household tenant pool',rent=amt(rent),months=months,billed=0,next_due=self.state['tick']+720,status='ACTIVE',started=self.state['time'],claims=[],paid='0.00')
  leases.append(contract);self.audit('property_lease_signed',contract.copy());return contract
 def property_lease_end(self,p):
  c=next((c for c in self.state.get('property_contracts',[]) if c['id']==p['contract']),None)
  if not c or c['status']!='ACTIVE':raise ValueError('Active rental contract required')
  self.authority(c['owner'],'govern');fee=D(c['rent'])
  if self.is_frozen(c['owner']) or self.available_cash(c['owner'])<fee:raise ValueError('Early termination requires one month of rent from the legal owner')
  self.post('Property rental early termination',{'cash:'+c['owner']:-fee,'expense:property_termination:'+c['owner']:fee,'cash:'+c['tenant']:fee,'pnl:'+c['tenant']:-fee});c['status']='TERMINATED';c['ended']=self.state['time'];self.audit('property_lease_ended',{'contract':c['id'],'owner':c['owner'],'termination_payment':amt(fee),'existing_arrears_preserved':True});return c
 def property_tick(self):
  for c in self.state.get('property_contracts',[]):
   if c['status']=='ACTIVE' and self.state['tick']>=c['next_due']:
    c['next_due']+=720;c['billed']+=1;rent=D(c['rent']);claim=self.create_claim(c['owner'],c['tenant'],rent,'PROPERTY RENT',c['id'],0,1);c['claims'].append(claim['id']);self.post('Property rental income accrued',{'claim:'+c['owner']+':'+claim['id']:rent,'pnl:'+c['owner']:-rent,'expense:property_rent:'+c['tenant']:rent,'debt:'+c['tenant']+':claim_'+claim['id']:-rent})
    if c['billed']>=c['months']:c['status']='EXPIRED';self.audit('property_lease_expired',{'contract':c['id'],'unpaid_claims_preserved':True})
   for id in c['claims']:
    claim=next(x for x in self.state['claims_book'] if x['id']==id);pay=min(D(claim['balance']),self.available_cash(c['tenant']))
    if pay and not self.is_frozen(c['owner']) and not self.is_frozen(c['tenant']):self.settle_claim_cash(claim,pay,'Property rental payment');c['paid']=amt(D(c['paid'])+pay)
   c['paid']=amt(sum((D(payment['amount']) for claim in self.state['claims_book'] if claim['id'] in c['claims'] for payment in claim['payments']),D(0)))
