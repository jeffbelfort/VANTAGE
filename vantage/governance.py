"""Institutional control, classified related-party payments and enforceable claims.
All money remains in real local accounts. Intent and evidence are separate fields.
"""
from decimal import Decimal as D
from .integrity import amt

KINDS=('loan','service','consulting','reimbursement','distribution','equity','asset_purchase','collateral','appropriation')
class GovernanceMixin:
 def install_governance(self):
  w=self.state
  if w.get('governance_version',0)>=1:return
  w.update(governance_version=1,entities={},related_transactions=[],claims_book=[],pledges=[],correspondence=[],disclosures=[])
  self.sync_entities();self.audit('governance_initialized',{'policy':'Metadata only; historical balances and evidence unchanged'})
 def sync_entities(self):
  w=self.state
  if not w.get('governance_version'):return
  defs=[('personal','Personal account','personal',True,None)]+[(f['id'],f['name'],'fund',True,None) for f in w['funds']]+[(a['account'],a['name'],a['strategy'],False,None) for a in w.get('participants',[])]
  for id,name,kind,control,parent in defs:
   w['entities'].setdefault(id,dict(id=id,name=name,kind=kind,controlled=control,parent=parent,status='ACTIVE',signatories={'player':['trade','payment','disclose','govern']} if control else {},directors=['player'] if control else [],payment_limit='1000000.00',controls=0,mandate={'related_parties':kind!='fund','sectors':[]},owners={},units='0'))
 def controlled_accounts(self):return ['personal']+[f['id'] for f in self.state['funds']]+[e['id'] for e in self.state.get('entities',{}).values() if e['kind'] in ('company','holding','credit_fund','bank','issuer') and e['controlled']]
 def authority(self,account,right,actor='player'):
  self.sync_entities();entity=self.state.get('entities',{}).get(account)
  if actor.startswith('staff_'):
   employee=next((e for e in self.state.get('employees',[]) if e['id']==actor),None)
   if not employee or employee['entity']!=account or employee['status']!='EMPLOYED':raise ValueError('Employee authority is limited to their current employing institution')
  issuer=next((i for i in self.state.get('issuers',{}).values() if i['account']==account),None)
  if issuer and actor in ('player','board','public_player_board'):
   if not self.player_controls_entity(account):raise ValueError('Current voting ownership does not confer corporate management control')
   if not issuer.get('board_resolution'):raise ValueError('Elect a board through Public shareholder governance before managing this issuer')
   if actor=='board' and right!='govern':raise ValueError('Board approval is limited to governance')
  elif actor=='player' and entity and entity.get('parent') and not self.player_controls_entity(account):raise ValueError('Ownership-derived management control has been lost')
  elif not entity or right not in entity['signatories'].get(actor,[]):raise ValueError('Signatory lacks '+right+' authority for this account')
  if entity['status'] in ('DISSOLVED','ADMINISTRATION','MERGED') and right!='disclose':raise ValueError('Entity is under administration, dissolved or merged; inspect its legal successor')
  return entity
 def entity_create(self,p):
  from .engine import uid,positive
  parent=p.get('parent','personal');self.authority(parent,'govern');seed=positive(p.get('capital',1000));name=str(p['name']).strip()[:90];kind=p.get('kind','company')
  if not name or kind not in ('company','holding','credit_fund','bank'):raise ValueError('Choose a valid institution name and type')
  if self.is_frozen(parent):raise ValueError(self.restriction_message(parent,'Subsidiary funding'))
  if self.available_cash(parent)<seed:raise ValueError('Parent funding is insufficient')
  if self.state['entities'][parent]['kind']=='issuer':
   source=self.authority(parent,'payment')
   if seed>D(source['payment_limit']):raise ValueError('Subsidiary funding exceeds board payment authority')
  if self.is_fund(parent) and not self.state['entities'][parent]['mandate']['related_parties']:raise ValueError('Fund mandate prohibits a related-party capital investment')
  id='co_'+uid();e=dict(id=id,name=name,kind=kind,controlled=True,parent=parent,status='ACTIVE',owners={parent:str(seed)},units=str(seed),directors=['player'],signatories={'player':['trade','payment','disclose','govern']},payment_limit='1000000.00',controls=0,mandate={'related_parties':True,'sectors':[]})
  self.state['entities'][id]=e;self.post('Capital investment '+parent+' → '+name,{'cash:'+parent:-seed,'holding:'+parent+':'+id:seed,'cash:'+id:seed,'equity:'+id:-seed});self.audit('entity_created',e.copy());return e
 def entity_policy(self,p):
  e=self.authority(p['entity'],'govern')
  if 'payment_limit' in p:
   value=D(str(p['payment_limit']))
   if not value.is_finite() or value<0:raise ValueError('Invalid payment authority limit')
   e['payment_limit']=amt(value)
  if 'related_parties' in p:e['mandate']['related_parties']=bool(p['related_parties'])
  if 'allow_corporate_control' in p:
   if not self.is_fund(e['id']) or not isinstance(p['allow_corporate_control'],bool):raise ValueError('Corporate-control permission requires a fund and an Enabled/Disabled value')
   e['mandate']['allow_corporate_control']=p['allow_corporate_control']
   self.news('Fund mandate amended',e['name']+': corporate control investments '+('enabled' if p['allow_corporate_control'] else 'disabled')+'. Existing investor units, redemption rights and assets remain unchanged.','FUND MANDATE')
  if 'sectors' in p:e['mandate']['sectors']=list(p['sectors'])
  if 'delegate' in p:
   rights=p.get('rights',[])
   if not set(rights)<=set(['trade','payment','disclose','govern']):raise ValueError('Unknown delegated right')
   e['signatories'][str(p['delegate'])[:60]]=rights
  self.audit('authority_or_mandate_updated',dict(p));return e
 def related_instruction(self,p):
  from .engine import uid,positive
  self.install_governance();src=p['source'];dst=p['destination'];kind=p['kind'];amount=positive(p['amount']);actor=p.get('actor','player');entity=self.authority(src,'payment',actor)
  if dst not in self.accounts() or src==dst or kind not in KINDS:raise ValueError('Invalid transaction parties or classification')
  if kind=='equity':
   target=self.state['entities'].get(dst)
   if not target or self.is_fund(dst) or target.get('parent')!=src:raise ValueError('Capital injection requires an existing direct subsidiary; cyclic ownership prohibited')
  if self.is_frozen(src) or self.is_frozen(dst):raise ValueError(self.restriction_message(src if self.is_frozen(src) else dst,'Transfer'))
  if self.state['entities'].get(dst,{}).get('status') in ('DISSOLVED','ADMINISTRATION'):raise ValueError('Recipient cannot accept normal transactions')
  if kind in ('loan','asset_purchase') and not self.state['entities'].get(dst,{}).get('controlled'):raise ValueError('Counterparty has not delegated bilateral transaction authority')
  fair=D(str(p.get('fair_value',amount)))
  if kind=='asset_purchase':
   instrument=self.instrument(p['symbol'])
   if p['symbol'] not in self.state['instruments']:raise ValueError('Bilateral asset workflow supports owned securities, not derivative contracts')
   fair=(D(str(p.get('qty',0)))*D(instrument['price'])*self.fx_rate(instrument['currency'])).quantize(D('.01'))
  if not fair.is_finite() or fair<0:raise ValueError('Invalid independently estimated service/asset value')
  reasons=[]
  if kind=='appropriation':
   if entity['kind']=='personal' or not entity.get('controlled'):raise ValueError('Appropriation requires a controlled institutional source')
   if not self.state['entities'].get(dst,{}).get('controlled') or self.state['entities'][dst]['kind'] not in ('personal','company','holding','credit_fund','bank'):raise ValueError('Recipient must be personal or a controlled company')
   reasons.append('Unauthorised appropriation of institutional property; restitution not yet adjudicated')
  if self.is_fund(src) and not entity['mandate']['related_parties']:reasons.append('Undisclosed related-party activity outside fund mandate')
  if amount>fair*D('1.25') and kind in ('service','consulting','reimbursement','asset_purchase'):reasons.append('Payment materially exceeds declared economic value')
  owners=entity.get('owners',{})
  if kind=='distribution' and (self.is_fund(src) or D(owners.get(dst,'0'))!=D(entity.get('units','0')) or not owners):reasons.append('Distribution lacks full beneficial ownership; use pro-rata fund redemption')
  if kind=='distribution' and amount>max(D(0),D(self.metrics(src)['equity'])):reasons.append('Distribution exceeds distributable net assets')
  bypass=p.get('mode')=='override'
  if reasons and not bypass:raise ValueError('; '.join(reasons)+'. Restricted instruction requires an explicit recorded governance override.')
  if bypass and entity['controls']>=2:raise ValueError('Dual-authorisation controls block this override')
  r=dict(id=uid(),source=src,destination=dst,kind=kind,amount=amt(amount),fair_value=amt(fair),classification='MISCONDUCT ALLEGATION' if reasons and bypass else 'QUESTIONABLE GOVERNANCE' if self.is_fund(src) and not p.get('disclosed',False) else 'LEGITIMATE',reasons=reasons,actor=actor,status='PENDING',time=self.state['time'],tick=self.state['tick'],terms=dict(rate=str(p.get('rate',0)),months=int(p.get('months',12)),symbol=p.get('symbol'),qty=str(p.get('qty',0))),disclosed=bool(p.get('disclosed',False)),settlements=[])
  if kind=='loan':
   rate=D(r['terms']['rate'])
   if not rate.is_finite() or not 0<=rate<=100 or not 1<=r['terms']['months']<=360:raise ValueError('Invalid loan terms')
  self.state['related_transactions'].append(r)
  if r['disclosed']:self.state['disclosures'].append({'time':r['time'],'transaction':r['id'],'source':src,'counterparty':dst,'conflict':'Affiliated counterparty'})
  self.audit('related_instruction',r.copy())
  if amount>D(entity['payment_limit']) and not bypass:r['status']='AWAITING BOARD'
  else:self.settle_related(r)
  return r
 def approve_related(self,p):
  r=next(r for r in self.state['related_transactions'] if r['id']==p['id']);source=self.authority(r['source'],'govern');personal=source['kind']=='personal' and not source.get('controls',0) and 'board' not in source['directors'];reviewer='player' if personal else p.get('reviewer','board')
  if not personal:
   if reviewer==r['actor']:raise ValueError('Payment initiator cannot provide the independent approval')
   board=self.authority(r['source'],'govern',reviewer)
   if reviewer not in board['directors']:raise ValueError('Approver is not an appointed director')
  self.authority(r['source'],'payment',r['actor'])
  if r['status'] not in ('AWAITING BOARD','INSUFFICIENT FUNDS'):raise ValueError('Instruction does not await approval/settlement')
  if r['classification']!='LEGITIMATE':raise ValueError('Independent board cannot approve the recorded breach')
  r['personal_approval' if personal else 'board_approval']={'time':self.state['time'],'signatory':reviewer,'initiator':r['actor'],'source':'Personal account holder authorisation' if personal else 'Independent rule-based board review of mandate, valuation and authority'};self.audit('personal_transfer_authorised' if personal else 'board_resolution',{'transaction':r['id']});self.settle_related(r);return r
 def create_claim(self,creditor,debtor,amount,kind,reference,rate='0',months=12,secured=None):
  from .engine import uid
  id=uid();r=dict(id=id,creditor=creditor,debtor=debtor,original=amt(amount),balance=amt(amount),allowance='0.00',kind=kind,reference=reference,rate=str(rate),due=self.state['tick']+int(months)*720,created=self.state['tick'],status='ACTIVE',secured=secured,residual='0',payments=[])
  r['secured']=next((q['id'] for q in self.state.get('pledges',[]) if q['owner']==debtor and q['beneficiary']==creditor and q['status']=='ACTIVE'),secured);self.state['claims_book'].append(r);return r
 def settle_related(self,r):
  from .engine import positive
  if r['status']=='SETTLED':return
  if r['status'] not in ('PENDING','AWAITING BOARD','INSUFFICIENT FUNDS','RESTRICTED'):raise ValueError('Instruction is not eligible for settlement')
  if r['status']=='AWAITING BOARD' and not (r.get('board_approval') or r.get('personal_approval')):raise ValueError('Instruction requires authorisation before settlement')
  src=r['source'];dst=r['destination'];a=D(r['amount']);kind=r['kind'];e=self.state['entities'][src]
  if self.is_frozen(src) or self.is_frozen(dst):r['status']='RESTRICTED';return
  if self.available_cash(src)<a:r['status']='INSUFFICIENT FUNDS';return
  if kind=='collateral':
   id=r['id'];self.state['pledges'].append(dict(id=id,owner=src,beneficiary=dst,amount=amt(a),status='ACTIVE',symbol=r['terms'].get('symbol')));self.post('Cash collateral ring-fenced '+id,{'memo:pledge:'+src+':'+id:a,'memo:contra:'+src+':'+id:-a});r['status']='SETTLED';return
  lines={'cash:'+src:-a,'cash:'+dst:a}
  if kind=='appropriation':
   lines.update({'expense:appropriation:'+src:a,'pnl:'+dst:-a})
  elif r['classification']=='MISCONDUCT ALLEGATION' or kind=='loan':
   claim=self.create_claim(src,dst,a,'RECOVERY' if r['classification']!='LEGITIMATE' else 'INTERCOMPANY',r['id'],r['terms']['rate'] if kind=='loan' else '0',r['terms']['months']);r['claim']=claim['id'];lines.update({'claim:'+src+':'+claim['id']:a,'debt:'+dst+':claim_'+claim['id']:-a})
  elif kind in ('service','consulting','reimbursement'):lines.update({'expense:'+kind+':'+src:a,'pnl:'+dst:-a})
  elif kind=='distribution':lines.update({'equity:'+src:a,'pnl:'+dst:-a})
  elif kind=='equity':
   target=self.state['entities'].get(dst)
   if not target or self.is_fund(dst) or target.get('parent')!=src:raise ValueError('Capital injection requires an existing direct subsidiary; cyclic ownership prohibited')
   units=D(target['units']);nav=D(self.metrics(dst)['equity']);issued=a*units/nav if units>0 and nav>0 else a;target['units']=str(units+issued);target['owners'][src]=str(D(target['owners'].get(src,0))+issued);lines.update({'holding:'+src+':'+dst:a,'equity:'+dst:-a})
  elif kind=='asset_purchase':
   sym=r['terms']['symbol'];qty=positive(r['terms']['qty']);ins=self.instrument(sym);key=dst+':'+sym;pos=self.state['positions'].get(key)
   if not pos or qty>D(pos['qty']) or qty!=int(qty):raise ValueError('Asset seller does not own transferable shares')
   basis=(D(pos['cost'])*qty/D(pos['qty'])).quantize(D('.01'));newkey=src+':'+sym;buyer=self.state['positions'].get(newkey,{'qty':'0','cost':'0'})
   if D(buyer['qty'])<0:raise ValueError('OTC asset purchase cannot net against a borrowed position')
   pos['qty']=amt(D(pos['qty'])-qty);pos['cost']=amt(D(pos['cost'])-basis)
   if D(pos['qty'])==0:self.state['positions'].pop(key)
   self.state['positions'][newkey]=dict(account=src,symbol=sym,qty=amt(D(buyer['qty'])+qty),cost=amt(D(buyer['cost'])+a),borrowed='0.00');lines.update({'inventory:'+src+':'+sym:a,'inventory:'+dst+':'+sym:-basis,'pnl:'+dst:basis-a})
  self.post('Related-party '+kind+' '+r['id']+' / '+r['classification'],lines);r['status']='SETTLED';r['settlements'].append({'time':self.state['time'],'amount':amt(a)});self.audit('related_settlement',r.copy())
  if kind=='appropriation':
   r['evidence_record']=self.evidence('TRANSACTION RECORD',r['id'],'Recorded unauthorised appropriation; not yet regulator-discovered',src,a)
   r['source_nav_before']=amt(D(self.metrics(src)['equity'])+a)
 def repay_claim(self,p):
  from .engine import positive
  claim=next(c for c in self.state['claims_book'] if c['id']==p['id']);src=claim['debtor'];dst=claim['creditor'];self.authority(src,'payment',p.get('actor','player'));a=min(positive(p['amount']),D(claim['balance']))
  if self.is_frozen(src) or self.available_cash(src)<a:raise ValueError('Repayment source is restricted or illiquid')
  self.settle_claim_cash(claim,a,'Voluntary claim repayment');return claim
 def settle_claim_cash(self,c,a,description):
  before=D(c['balance']);release=(D(c['allowance'])*a/before).quantize(D('.01')) if before else D(0);lines={'cash:'+c['debtor']:-a,'cash:'+c['creditor']:a,'claim:'+c['creditor']+':'+c['id']:-a,'debt:'+c['debtor']+':claim_'+c['id']:a}
  if release:lines.update({'allowance:'+c['creditor']+':'+c['id']:release,'pnl:'+c['creditor']:-release})
  self.post(description+' '+c['id'],lines);c['balance']=amt(before-a);c['allowance']=amt(D(c['allowance'])-release);c['payments'].append({'time':self.state['time'],'amount':amt(a)});c['status']='REPAID' if D(c['balance'])==0 else c['status']
  if c['status']=='REPAID' and c.get('secured') and self.state.get('resolution_version'):self.release_pledge({'id':c['secured']})
 def impairment(self,p):
  c=next(c for c in self.state['claims_book'] if c['id']==p['id']);self.authority(c['creditor'],'govern');rate=D(str(p['fraction']))
  if not rate.is_finite() or not 0<=rate<=1:raise ValueError('Impairment must be0–1')
  target=(D(c['balance'])*rate).quantize(D('.01'));change=target-D(c['allowance']);self.post('Documented claim impairment '+c['id'],{'expense:impairment:'+c['creditor']:change,'allowance:'+c['creditor']+':'+c['id']:-change});c['allowance']=amt(target);self.audit('claim_valuation',dict(p));return c
 def governance_tick(self):
  self.corporate_tick()
  for c in self.state.get('claims_book',[]):
   if c['status'] not in ('ACTIVE','OVERDUE'):continue
   if D(c['rate'])>0:
    raw=D(c['balance'])*D(c['rate'])/D(100*365*24)+D(c['residual']);a=raw.quantize(D('.01'));c['residual']=str(raw-a)
    if a:self.post(('Federal Reserve facility interest ' if c['kind']=='FED FACILITY' else 'Intercompany credit interest ')+c['id'],{'claim:'+c['creditor']+':'+c['id']:a,'pnl:'+c['creditor']:-a,'expense:related_interest:'+c['debtor']:a,'debt:'+c['debtor']+':claim_'+c['id']:-a});c['balance']=amt(D(c['balance'])+a)
   if self.state['tick']>=c['due']:
    if self.available_cash(c['debtor'])>=D(c['balance']) and not self.is_frozen(c['debtor']):self.settle_claim_cash(c,D(c['balance']),'Maturing credit settlement')
    else:c['status']='OVERDUE'
 def fund_terms(self,p):
  f=next(f for f in self.state['funds'] if f['id']==p['fund']);self.authority(f['id'],'govern');terms=f.setdefault('terms',{'minimum':'1.00','subscription_open':True,'notice_hours':0,'eligible':[n['id'] for n in self.state['npcs']],'share_class':'STANDARD','side_pocket_pct':0})
  for k in ('minimum','notice_hours','side_pocket_pct'):
   if k in p:
    value=D(str(p[k]));maximum=D(100) if k=='side_pocket_pct' else D(8760) if k=='notice_hours' else D('1e15')
    if not value.is_finite() or not 0<=value<=maximum:raise ValueError('Fund term outside allowed range')
    terms[k]=str(value) if k=='minimum' else int(value)
  if 'subscription_open' in p:terms['subscription_open']=bool(p['subscription_open'])
  if 'eligible' in p:terms['eligible']=[id for id in p['eligible'] if any(n['id']==id for n in self.state['npcs'])]
  if 'share_class' in p:terms['share_class']=str(p['share_class'])[:40]
  self.audit('fund_terms',{'fund':f['id'],**terms});return terms
 def verified_statement(self,p):
  f=next(f for f in self.state['funds'] if f['id']==p['fund']);self.authority(f['id'],'disclose');actual=self.metrics(f['id'])['equity'];f['verified']={'time':self.state['time'],'nav':actual,'method':'Independent ledger reconstruction','difference':self.statement(f['id'])['difference']};self.audit('independent_nav_verification',{'fund':f['id'],**f['verified']});return f['verified']
 def investor_response(self,p):
  from .engine import uid
  f=next(f for f in self.state['funds'] if f['id']==p['fund']);self.authority(f['id'],'disclose');n=next(n for n in self.state['npcs'] if n['id']==p['investor']);kind=p['response']
  if kind not in ('verified_statement','liquidity_update','disclose_conflict'):raise ValueError('Choose a structured response')
  event={'id':uid(),'time':self.state['time'],'fund':f['id'],'investor':n['id'],'kind':kind,'nav':self.metrics(f['id'])['equity'],'cash':amt(self.available_cash(f['id'])),'pending':amt(sum((D(r['remaining']) for r in self.state.get('redemptions',[]) if r['fund']==f['id']),D(0)))}
  if any(m['fund']==f['id'] and m['investor']==n['id'] and m['kind']==kind and m.get('tick')==self.state['tick']//24 for m in self.state['correspondence']):raise ValueError('This response has already been sent this market day')
  event['tick']=self.state['tick']//24;self.state['correspondence'].append(event);n['trust']=min(100,n['trust']+(1 if kind!='disclose_conflict' else 2));self.message(n['name'],'Response: '+kind.replace('_',' '),f"{f['name']}: verified actual NAV £{D(event['nav']):,.2f}, available cash £{D(event['cash']):,.2f}, outstanding withdrawals £{D(event['pending']):,.2f}. Correspondence {event['id']}.");self.audit('investor_correspondence',event);return event
