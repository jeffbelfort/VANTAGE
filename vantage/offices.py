"""Institutional premises and leases with funded liabilities and right-of-use assets."""
from decimal import Decimal as D
from .integrity import amt
OFFICES=[
 {'id':'regional','name':'Regional serviced office','location':'Manchester','capacity':25,'prestige':45,'equipment':60,'price':'450000','rent':'2500','utilities':'350','equipment_cost':'250','maintenance':'400'},
 {'id':'city','name':'City trading floor','location':'London','capacity':100,'prestige':80,'equipment':85,'price':'5500000','rent':'35000','utilities':'3500','equipment_cost':'2500','maintenance':'4500'},
 {'id':'headquarters','name':'Financial headquarters','location':'London','capacity':500,'prestige':95,'equipment':95,'price':'45000000','rent':'240000','utilities':'20000','equipment_cost':'15000','maintenance':'30000'},
]
class OfficeMixin:
 def install_offices(self):
  if self.state.get('office_version'):return
  self.state.setdefault('offices',[]);self.state.setdefault('remote_capacity',{});self.state['office_version']=1
  for entity in self.controlled_accounts():self.state['remote_capacity'].setdefault(entity,max(10,len(self.staff(entity))))
  self.audit('offices_installed',{'version':1,'existing_staff_retained':True,'remote_capacity':10})
 def office_capacity(self,entity):return self.state.get('remote_capacity',{}).get(entity,10)+sum(o['capacity'] for o in self.state.get('offices',[]) if o['entity']==entity and o['status']=='ACTIVE')
 def office_start(self,p):
  from .engine import uid
  entity=p['entity'];authority=self.employee_entity(entity);item=next((o for o in OFFICES if o['id']==p['catalogue']),None);mode=p['mode']
  if not item or mode not in ('lease','purchase'):raise ValueError('Choose valid premises and lease or purchase')
  term=int(p.get('months',12))
  if not 1<=term<=120:raise ValueError('Lease term must be 1–120 simulation months')
  price=D(item['price']);rent=D(item['rent']);commitment=rent*term if mode=='lease' else price
  if commitment>D(authority['payment_limit']):raise ValueError('Property commitment exceeds institution authority')
  required=rent if mode=='lease' else price
  if required>self.available_cash(entity):raise ValueError('Insufficient unrestricted cash for premises')
  o={**item,'id':'office_'+uid(),'catalogue':item['id'],'entity':entity,'mode':mode,'status':'ACTIVE','started':self.state['time'],'tick':self.state['tick'],'next_due':self.state['tick']+720,'term_months':term,'months_elapsed':0,'unpaid_rent':'0.00','unpaid_operations':'0.00','paid':'0.00','asset':None}
  if mode=='lease':
   self.post('Office lease signed: '+o['name'],{'rou:'+entity+':'+o['id']:commitment,'debt:'+entity+':lease_'+o['id']:-commitment})
  else:
   asset={**item,'id':'asset_'+uid(),'catalogue':'office_'+item['id'],'category':'Offices','name':item['name'],'price':item['price'],'annual_change':'0.01','monthly_cost':item['maintenance'],'sale_hours':1440,'discount':'0.05','owner':entity,'purchase_price':amt(price),'valuation':amt(price),'acquired':self.state['time'],'acquired_tick':self.state['tick'],'cost_next':self.state['tick']+720,'status':'OWNED','unpaid':'0.00','running_paid':'0.00','sale':None,'realised':None}
   self.post('Office building purchased: '+o['name'],{'cash:'+entity:-price,'asset:'+entity+':'+asset['id']:price,'cash:lifestyle_market':price,'pnl:lifestyle_market':-price});self.state['owned_assets'].append(asset);o['asset']=asset['id']
  self.state['offices'].append(o);self.audit('office_started',o.copy());return o
 def office_end(self,p):
  o=next((o for o in self.state['offices'] if o['id']==p['office']),None)
  if not o or o['status']!='ACTIVE':raise ValueError('Active office required')
  entity=o['entity'];self.employee_entity(entity)
  if len(self.staff(entity))>self.office_capacity(entity)-o['capacity']:raise ValueError('Relocate or reduce headcount before removing occupied capacity')
  if o['mode']=='lease':
   balance=-self.balance('debt:'+entity+':lease_'+o['id']);rou=self.balance('rou:'+entity+':'+o['id'])
   if self.available_cash(entity)<balance:raise ValueError('Early termination requires payment of all remaining contractual rent')
   if balance:self.post('Office lease termination payment: '+o['name'],{'cash:'+entity:-balance,'debt:'+entity+':lease_'+o['id']:balance,'cash:property_suppliers':balance,'pnl:property_suppliers':-balance})
   if rou:self.post('Remaining office right-of-use written off: '+o['name'],{'rou:'+entity+':'+o['id']:-rou,'expense:office_rent:'+entity:rou})
   o['unpaid_rent']='0.00'
  o['status']='TERMINATED' if o['mode']=='lease' else 'VACATED';o['ended']=self.state['time'];self.audit('office_ended',{'office':o['id'],'entity':entity,'remaining_lease_paid':True});return o
 def office_relocate(self,p):
  old=next((o for o in self.state['offices'] if o['id']==p['office']),None)
  if not old:raise ValueError('Office not found')
  new=self.office_start({**p,'entity':old['entity']});self.office_end({'office':old['id']});return new
 def office_sell(self,p):
  o=next((o for o in self.state['offices'] if o['id']==p['office']),None)
  if not o or not o['asset']:raise ValueError('Owned office required')
  self.employee_entity(o['entity'])
  if o['status']=='ACTIVE':self.office_end({'office':o['id']})
  a=next(a for a in self.state['owned_assets'] if a['id']==o['asset'])
  if a['status']!='OWNED':raise ValueError('Office is already listed or sold')
  if any(c['asset']==a['id'] and c['status']=='ACTIVE' for c in self.state.get('property_contracts',[])):raise ValueError('End the rental contract before selling the building')
  a['sale']={'listed':self.state['time'],'due':self.state['tick']+a['sale_hours'],'quote':amt(D(a['valuation'])*(1-D(a['discount']))),'status':'FINDING BUYER'};a['status']='LISTED';self.audit('office_sale_listed',{'office':o['id'],'asset':a['id'],'entity':o['entity']});return a
 def office_tick(self):
  for o in self.state.get('offices',[]):
   entity=o['entity'];id=o['id']
   if o['status']=='ACTIVE' and self.state['tick']>=o['next_due']:
    o['next_due']+=720;o['months_elapsed']+=1;cost=D(o['utilities'])+D(o['equipment_cost']);self.post('Office utilities and equipment: '+o['name'],{'expense:office_operations:'+entity:cost,'debt:'+entity+':office_'+id:-cost});o['unpaid_operations']=amt(D(o['unpaid_operations'])+cost)
    if o['mode']=='lease':
     rent=D(o['rent']);self.post('Monthly office right-of-use consumption: '+o['name'],{'expense:office_rent:'+entity:rent,'rou:'+entity+':'+id:-rent});o['unpaid_rent']=amt(D(o['unpaid_rent'])+rent)
     if o['months_elapsed']>=o['term_months']:o['status']='EXPIRED';self.audit('office_lease_expired',{'office':id,'entity':entity,'unpaid_rent_preserved':True})
   if self.is_frozen(entity):continue
   for field,key in [('unpaid_rent','lease_'),('unpaid_operations','office_')]:
    amount=min(D(o[field]),max(D(0),self.available_cash(entity)))
    if amount:self.post('Office obligation settlement: '+o['name'],{'cash:'+entity:-amount,'debt:'+entity+':'+key+id:amount,'cash:property_suppliers':amount,'pnl:property_suppliers':-amount});o[field]=amt(D(o[field])-amount);o['paid']=amt(D(o['paid'])+amount)
 def office_rou(self,entity):return sum((D(v) for k,v in self.ledger_items(entity) if k.startswith('rou:'+entity+':')),D(0))
