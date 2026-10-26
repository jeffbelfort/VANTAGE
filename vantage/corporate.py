"""Corporate management projections and creditor-approved commercial amendments.

Uses existing entities, claims, signatories, restrictions and journal settlement.
No replacement investigation, transfer or insolvency engine.
"""
import copy
from decimal import Decimal as D
from .integrity import amt

class CorporateMixin:
 def ownership_path(self,account,seen=None):
  seen=set(seen or ())
  if account in seen:return {'personal_percent':None,'cycle':True}
  if account=='personal':return {'personal_percent':'100.00','cycle':False}
  seen.add(account);e=self.state['entities'].get(account,{})
  fund=next((f for f in self.state['funds'] if f['id']==account),None)
  owners=fund.get('investors',{}) if fund else e.get('owners',{});units=D((fund or e).get('units','0'))
  issuer=next((i for i in self.state.get('issuers',{}).values() if i['account']==account),None)
  if issuer:
   view=self.public_ownership(issuer['symbol']);owners={h['account']:h['registered_shares'] for h in view['shareholders']};units=D(view['outstanding'])
  total=D(0)
  if units>0:
   for owner,quantity in owners.items():
    if owner not in self.state['entities']:continue
    path=self.ownership_path(owner,seen)
    if path['cycle']:return path
    total+=D(quantity)/units*D(path['personal_percent'])
  return {'personal_percent':amt(total),'cycle':False}

 def corporate_views(self,metrics=None):
  metrics=metrics or {};result={};w=self.state
  for id,e in w['entities'].items():
   if not e.get('controlled'):continue
   m=metrics.get(id) or self.metrics(id);claims=[c for c in w['claims_book'] if c['debtor']==id and D(c['balance'])>0]
   receivables=[c for c in w['claims_book'] if c['creditor']==id and D(c['balance'])>0]
   overdue=sum((D(c['balance']) for c in claims if c['due']<=w['tick']),D(0));equity=D(m['equity']);debt=D(m['debt'])
   # Net short positions are liabilities, never negative gross assets.
   short=D(0)
   for p in w['positions'].values():
    if p['account']==id and D(p['qty'])<0:
     ins=self.instrument(p['symbol']);short-=D(p['qty'])*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins.get('currency','GBP'))
   liabilities=debt+short;fund=next((f for f in w['funds'] if f['id']==id),None)
   owners=(fund or {}).get('investors',e.get('owners',{}));units=D((fund or e).get('units','0'))
   restriction=self.restriction_summary(id)
   result[id]={'id':id,'financials':dict(m,total_assets=amt(equity+liabilities),total_liabilities=amt(liabilities),short_position_liabilities=amt(short),claim_payables=amt(sum((D(c['balance']) for c in claims),D(0))),claim_receivables_face=amt(sum((D(c['balance']) for c in receivables),D(0))),recovery_payables=amt(sum((D(c['balance']) for c in claims if c['kind']=='RECOVERY'),D(0))),overdue_claims=amt(overdue)),
    'owners':[{'id':owner,'percent':amt(D(q)/units*100) if units else None} for owner,q in owners.items()],
    'beneficial':self.ownership_path(id),'relationship':'Managed institutional capital' if e['kind']=='fund' or id=='book' else 'Direct equity ownership',
    'condition':e['status'] if e['status']!='ACTIVE' else 'INSOLVENT' if equity<0 else 'DISTRESSED' if overdue>max(D(0),D(m['available_cash'])) else 'OPERATING',
    'restriction':restriction,'cases':[c['id'] for c in w.get('legal_cases',[]) if c['entity']==id],
    'actions':{'payments':not restriction['frozen'] and e['status']=='ACTIVE','administration':e['kind']!='personal' and e['status']=='ACTIVE'},
    'note':'Standalone marked assets and liabilities; never sum parent and subsidiary assets as consolidated wealth.'}
   recommendations=[];cash=D(m['available_cash']);business=w.get('private_businesses',{}).get(id)
   if overdue>cash:recommendations.append(dict(title='Creditor payments exceed available cash',reason='Overdue claims total £'+amt(overdue)+'.',action='Review Debt & Creditors; arrange authorised funding or repayment terms.'))
   if business:
    monthly=(D(business['annual_payroll'])+D(business['annual_materials']))/12
    if cash<monthly:recommendations.append(dict(title='Operating liquidity below one month of costs',reason='One month of aggregate payroll and materials is £'+amt(monthly)+'.',action='Review company funding before expanding; parent cash is separate.'))
    if business.get('history') and D(business['history'][-1]['ebitda'])<0:recommendations.append(dict(title='Latest operating day made a loss',reason='Revenue did not cover payroll and materials.',action='Review capacity, contracts and operating strategy; cost reduction may sacrifice growth.'))
   if equity>0 and cash>equity*D('.7'):recommendations.append(dict(title='Large cash allocation',reason='More than 70% of standalone net assets is available cash.',action='Review investment opportunities or retain liquidity deliberately; returns are not guaranteed.'))
   if fund and any(r['fund']==id and D(r['remaining'])>0 for r in w.get('redemptions',[])):recommendations.append(dict(title='Investor redemptions outstanding',reason='Recorded withdrawal requests require liquidity.',action='Review investor requests and liquidate investments only through normal execution.'))
   result[id]['recommendations']=recommendations
   result[id]['management_entity']=fund.get('manager','personal') if fund else None
   issuer=next((i for i in w.get('issuers',{}).values() if i['account']==id),None)
   if issuer:
    public=self.public_ownership(issuer['symbol']);result[id]['owners']=[{'id':h['account'],'percent':h['economic_percent'],'voting_percent':h['control_percent']} for h in public['shareholders']]
    result[id]['relationship']='Controlled listed issuer · shareholder governance';result[id]['public_ownership']=public
    result[id]['actions']['payments']=self.player_controls_entity(id) and bool(issuer.get('board_resolution'));result[id]['note']+=' Listed shares remain market investments in existing group reporting; public-company consolidation is not yet implemented.'
  return result

 def corporate_proposal(self,p):
  from .engine import uid
  c=next(c for c in self.state['claims_book'] if c['id']==p['claim']);self.authority(c['debtor'],'govern')
  if c['kind']!='INTERCOMPANY' or c['status'] not in ('ACTIVE','OVERDUE') or D(c['balance'])<=0:raise ValueError('Only outstanding ordinary intercompany credit can be negotiated; recovery and regulatory claims retain their terms')
  if self.is_frozen(c['debtor']) or self.is_frozen(c['creditor']):raise ValueError('Restricted parties cannot negotiate private debt amendments')
  months=int(p.get('months',12));rate=D(str(p.get('rate',c['rate'])));upfront=D(str(p.get('upfront',0)))
  if not 1<=months<=360 or not rate.is_finite() or not 0<=rate<=100 or not upfront.is_finite() or not 0<=upfront<=D(c['balance']) or upfront!=upfront.quantize(D('.01')):raise ValueError('Invalid credit amendment terms')
  proposals=self.state.setdefault('corporate_proposals',[])
  if any(r['claim']==c['id'] and r['status']=='PENDING' for r in proposals):raise ValueError('This claim already has a pending proposal')
  r=dict(id=uid(),claim=c['id'],debtor=c['debtor'],creditor=c['creditor'],months=months,rate=str(rate),upfront=amt(upfront),status='PENDING',time=self.state['time'],tick=self.state['tick'],expires=self.state['tick']+168)
  proposals.append(r);self.audit('credit_amendment_proposed',r.copy());return r

 def corporate_decision(self,p):
  r=next(r for r in self.state.get('corporate_proposals',[]) if r['id']==p['id'])
  if r['status']!='PENDING':raise ValueError('Proposal already decided')
  self.authority(r['creditor'],'govern');self.authority(r['debtor'],'govern')
  if self.is_frozen(r['creditor']) or self.is_frozen(r['debtor']):raise ValueError('Restrictions block private restructuring')
  c=next(c for c in self.state['claims_book'] if c['id']==r['claim'])
  if c['kind']!='INTERCOMPANY' or c['status'] not in ('ACTIVE','OVERDUE') or D(c['balance'])<=0:raise ValueError('Claim is no longer eligible')
  if self.state['tick']>r['expires']:r['status']='EXPIRED'
  elif not p.get('accept'):r['status']='REJECTED'
  else:
   upfront=D(r['upfront']);balance=D(c['balance'])
   viable=D(self.metrics(c['debtor'])['equity'])>=0 or upfront>=balance*D('.25')
   if not viable:r['status']='REJECTED';r['reason']='Negative debtor equity requires at least 25% upfront recovery'
   elif upfront>balance or upfront>self.available_cash(c['debtor']):raise ValueError('Upfront payment no longer affordable or exceeds outstanding balance')
   else:
    r['previous']={'due':c['due'],'rate':c['rate'],'balance':c['balance']}
    if upfront:self.repay_claim({'id':c['id'],'amount':upfront})
    c['due']=self.state['tick']+r['months']*720;c['rate']=r['rate']
    if D(c['balance'])>0:c['status']='ACTIVE'
    r['status']='ACCEPTED'
  r['decided']=self.state['time'];self.audit('credit_amendment_decided',copy.deepcopy(r));return r

 def corporate_tick(self):
  for action in self.state.get('corporate_actions',[]):
   if action['status']=='PENDING' and self.state['tick']>action['expires']:
    action['status']='EXPIRED';self.audit('corporate_action_expired',{'id':action['id']})
  for r in self.state.get('corporate_proposals',[]):
   if r['status']=='PENDING' and self.state['tick']>r['expires']:
    r['status']='EXPIRED';r['decided']=self.state['time'];self.audit('credit_amendment_expired',{'id':r['id'],'claim':r['claim']})

 def corporate_officer(self,p):
  e=self.authority(p['entity'],'govern')
  if self.is_frozen(e['id']):raise ValueError('Restrictions prohibit management changes')
  employee=next((s for s in self.state['employees'] if s['id']==p['employee'] and s['entity']==e['id'] and s['status']=='EMPLOYED'),None)
  if not employee:raise ValueError('Choose an employed officer of this company')
  role=p.get('role','CEO')
  if role not in ('CEO','DIRECTOR','REMOVE'):raise ValueError('Unknown officer action')
  grants=e.setdefault('officer_grants',{});rights=e['signatories'].setdefault(employee['id'],[]);added=grants.setdefault(employee['id'],[])
  if role=='CEO':e['ceo']=employee['id']
  elif role=='DIRECTOR':
   if employee['id'] not in e['directors']:e['directors'].append(employee['id'])
  else:
   e['directors']=[d for d in e['directors'] if d!=employee['id']]
   if e.get('ceo')==employee['id']:e.pop('ceo')
   for right in added:
    if right in rights:rights.remove(right)
   grants.pop(employee['id'],None)
  if role!='REMOVE':
   for right in (['disclose','govern'] if role=='DIRECTOR' else ['disclose']):
    if right not in rights:rights.append(right);added.append(right)
  # No payment/trading rights are granted; employee work still requires departmental mandates.
  self.audit('corporate_officer',dict(p));return e
