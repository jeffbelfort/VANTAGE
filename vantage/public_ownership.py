"""Public issuer identity, finite registered votes and attributable stock lending.
Positions remain the sole economic register. Loans distinguish lenders' economic
claims from voting title; no duplicate equity or private ownership units are made.
Legacy shorts without lender evidence quarantine voting for that security.
"""
import copy
from decimal import Decimal as D
from .integrity import amt

from .public_management import PublicManagementMixin

class PublicOwnershipMixin(PublicManagementMixin):
 def install_public_ownership(self):
  w=self.state
  if w.get('public_ownership_version'):return
  w['public_ownership_version']=1;w['stock_loans']=[];w['public_resolutions']=[];w['ownership_disclosures']=[]
  unresolved={}
  for p in w['positions'].values():
   if p['symbol'] in w.get('issuers',{}) and D(p['qty'])<0:unresolved[p['account']+':'+p['symbol']]=str(-D(p['qty']))
  w['legacy_stock_borrow']=unresolved
  w['public_ownership_baseline']={}
  for symbol,issuer in w.get('issuers',{}).items():
   positions=[p for p in w['positions'].values() if p['symbol']==symbol];reg=w.get('share_register',{}).get(symbol,{})
   w['public_ownership_baseline'][symbol]=dict(issuer=issuer['account'],tick=w['tick'],issued=str(issuer['model_shares']),registered_header=reg.get('outstanding'),
    net_positions=str(sum((D(p['qty']) for p in positions),D(0))),source='Observed existing records; no ownership or financial balancing entries created')
  self.audit('public_ownership_installed',{'version':1,'positions_unchanged':True,'shares_unchanged':True,'legacy_unattributed_shorts':copy.deepcopy(unresolved),
   'class_policy':'Single ordinary one-vote model class where issued supply reconciles. No claim about real issuer share classes.',
   'nominees':'Existing custody pools retained; underlying client identities remain unknown.',
   'legacy_supply':'Missing or inconsistent issued supply blocks voting; no balancing shareholders created.'})

 def ownership_roots(self,account,path=None,weight=D(1)):
  path=list(path or [])
  if account in path:return [dict(owner=account,weight=str(weight),path=path+[account],status='CYCLE')]
  path=path+[account];e=self.state.get('entities',{}).get(account,{})
  f=next((f for f in self.state.get('funds',[]) if f['id']==account),None)
  owners=(f or {}).get('investors',e.get('owners',{}));units=D((f or e).get('units',0))
  listed=next((i for i in self.state.get('issuers',{}).values() if i['account']==account),None)
  if listed:
   symbol=listed['symbol'];units=D(str(listed['model_shares']));owners={}
   for position in self.state['positions'].values():
    if position['symbol']!=symbol or D(position['qty'])<=0:continue
    lent=sum((D(l['quantity']) for l in self.state.get('stock_loans',[]) if l['symbol']==symbol and l['lender']==position['account']),D(0))
    owners[position['account']]=max(D(0),D(position['qty'])-lent)
  if not owners or units<=0:return [dict(owner=account,weight=str(weight),path=path,status='UNDISCLOSED NOMINEE' if e.get('kind')=='custody' else 'KNOWN POOL' if e.get('kind')=='beneficiary_pool' else 'TERMINAL')]
  result=[]
  for owner,qty in owners.items():result.extend(self.ownership_roots(owner,path,weight*D(qty)/units))
  return result

 def public_ownership(self,symbol):
  w=self.state;issuer=w.get('issuers',{}).get(symbol)
  if not issuer:raise ValueError('Security has no corporate issuer record')
  outstanding=D(str(issuer.get('model_shares',0)));reg=w.get('share_register',{}).get(symbol,{})
  positions=[p for p in w['positions'].values() if p['symbol']==symbol];net=sum((D(p['qty']) for p in positions),D(0))
  legacy=sum((D(q) for k,q in w.get('legacy_stock_borrow',{}).items() if k.rsplit(':',1)[-1]==symbol),D(0))
  lent={};borrowed=D(0)
  for loan in w.get('stock_loans',[]):
   if loan['symbol']!=symbol or D(loan['quantity'])<=0:continue
   lent[loan['lender']]=lent.get(loan['lender'],D(0))+D(loan['quantity']);borrowed+=D(loan['quantity'])
  shorts=sum((max(D(0),-D(p['qty'])) for p in positions),D(0))
  reconciled=bool(reg) and D(str(reg.get('outstanding',0)))==outstanding and net==outstanding and outstanding>0 and legacy==0 and borrowed==shorts
  treasury_account=issuer['account'];treasury=max(D(0),D(w['positions'].get(treasury_account+':'+symbol,{}).get('qty',0))-lent.get(treasury_account,D(0)))
  voting_total=outstanding-treasury;holders=[]
  for p in positions:
   qty=D(p['qty'])
   if qty<=0:continue
   registered=qty-lent.get(p['account'],D(0))
   if registered<0:reconciled=False
   holders.append(dict(account=p['account'],shares=str(qty),lent=str(lent.get(p['account'],0)),registered_shares=str(max(D(0),registered)),
    voting_shares=str(max(D(0),registered)) if reconciled and p['account']!=treasury_account else '0',
    economic_percent=str(qty/outstanding*100) if outstanding else None,
    ultimate_beneficiaries=self.ownership_roots(p['account'])))
  if not reconciled:
   for h in holders:h['voting_shares']='0'
  for h in holders:h['control_percent']=str(D(h['voting_shares'])/voting_total*100) if reconciled and voting_total>0 else None
  return dict(symbol=symbol,issuer=treasury_account,outstanding=str(outstanding),treasury=str(treasury),public_float=reg.get('free_float'),
   classes=[dict(id='MODEL_ORDINARY',outstanding=str(outstanding),votes_per_share='1',source='Explicit simulation convention; real-world classes not inferred')],
   reconciled=reconciled,net_economic_shares=str(net),unattributed_legacy_borrow=str(legacy),voting_total=str(voting_total),shareholders=holders,
   status='RECONCILED' if reconciled else 'LEGACY / UNRECONCILED — voting and public control disabled')

 def stock_lending_sources(self,symbol,borrower=None):
  w=self.state;lent={};sales={}
  for loan in w.get('stock_loans',[]):
   if loan['symbol']==symbol:lent[loan['lender']]=lent.get(loan['lender'],D(0))+D(loan['quantity'])
  from .pretrade import pending
  for order in pending(self,None,symbol):
   if order['symbol']==symbol and order['side']=='sell' and order['status'] in ('OPEN','PARTIAL','PAUSED'):sales[order['account']]=sales.get(order['account'],D(0))+D(order['remaining'])
  sources=[]
  for actor in w['participants']:
   lender=actor['account']
   if lender==borrower or self.is_frozen(lender):continue
   held=max(D(0),D(w['positions'].get(lender+':'+symbol,{}).get('qty',0)));committed=lent.get(lender,D(0))
   capacity=max(D(0),min((held*D(actor.get('mandate',{}).get('lend_fraction',0))).to_integral_value(rounding='ROUND_DOWN')-committed,held-committed-sales.get(lender,D(0))-self.public_tender_committed(lender,symbol)))
   if capacity:sources.append((lender,capacity))
  return sources

 def public_stock_transfer(self,account,symbol,old,new):
  """Called inside paired settlement. Lending title follows actual short creation."""
  w=self.state
  if not w.get('public_ownership_version') or symbol not in w.get('share_register',{}):return
  from .engine import OrderRejected,uid
  if new>old:
   try:self.validate_fund_control_purchase(account,symbol,new)
   except ValueError as exc:raise OrderRejected(str(exc)) from exc
  delta=max(D(0),-new)-max(D(0),-old)
  # An owner cannot sell title already on loan; recall requires borrower return.
  lent=sum((D(l['quantity']) for l in w['stock_loans'] if l['symbol']==symbol and l['lender']==account),D(0))
  if max(D(0),new)<lent:raise OrderRejected('Shares are on loan; borrower must return title before disposal')
  if new<old and max(D(0),new)<lent+self.public_tender_committed(account,symbol):raise OrderRejected('Shares are committed to an open public offer; withdraw or review the offer before disposal')
  if delta>0:
   allocations=[];remaining=delta
   for lender,capacity in self.stock_lending_sources(symbol,account):
    q=min(remaining,capacity)
    if q:allocations.append(dict(id=uid(),symbol=symbol,lender=lender,borrower=account,quantity=str(q),original_quantity=str(q),returned='0',opened=w['tick'],basis='Existing consenting institutional lending mandate'));remaining-=q
    if remaining<=0:break
   if remaining>0:raise OrderRejected('No attributable consenting stock lender has sufficient unencumbered shares')
   w['stock_loans'].extend(allocations)
  elif delta<0:
   remaining=-delta;legacy_key=account+':'+symbol;legacy=D(w['legacy_stock_borrow'].get(legacy_key,0));release=min(legacy,remaining)
   if release:w['legacy_stock_borrow'][legacy_key]=str(legacy-release);remaining-=release
   for loan in w['stock_loans']:
    if loan['borrower']!=account or loan['symbol']!=symbol:continue
    release=min(remaining,D(loan['quantity']));loan['quantity']=str(D(loan['quantity'])-release);loan['returned']=str(D(loan.get('returned',0))+release);remaining-=release
    if D(loan['quantity'])==0:loan['closed']=w['tick']
    if remaining<=0:break
   if remaining>0:raise OrderRejected('Stock borrow return does not reconcile')

 def public_control_refresh(self):
  if not self.state.get('public_ownership_version'):return
  w=self.state;views={s:self.public_ownership(s) for s in w.get('issuers',{})};control_set=self.player_control_set(views)
  for entity in w['entities'].values():
   if entity['kind'] in ('company','holding','credit_fund','bank') and entity.get('owners'):entity['controlled']=entity['id'] in control_set
  for symbol,issuer in w.get('issuers',{}).items():
   view=views[symbol];e=w['entities'][issuer['account']]
   votes=sum((D(h['voting_shares']) for h in view['shareholders'] if w['entities'].get(h['account'],{}).get('controlled')),D(0))
   # Portfolio control is distinct from board authority and from personal economics.
   controlled=issuer['account'] in control_set;e['controlled']=controlled;e['listed_symbol']=symbol
   if controlled:issuer['ever_player_controlled']=True
   majority=next((h['account'] for h in view['shareholders'] if D(h['voting_shares'])>D(view['voting_total'])/2),None)
   e['parent']=majority
   if not controlled:
    e['signatories'].pop('player',None) # appointments and executed governance history survive control loss
   disclosure_holders={h['account']:h for h in view['shareholders']}
   for previous in w['ownership_disclosures']:
    if previous['symbol']==symbol:disclosure_holders.setdefault(previous['account'],{'account':previous['account'],'control_percent':'0'})
   for h in disclosure_holders.values():
    if not w['entities'].get(h['account'],{}).get('controlled'):continue
    pct=D(h['control_percent'] or 0);thresholds=[n for n in (5,10,25,50) if pct>=n]
    previous=next((d for d in reversed(w['ownership_disclosures']) if d['symbol']==symbol and d['account']==h['account']),None)
    if thresholds!=(previous or {}).get('thresholds',[]):
     r=dict(symbol=symbol,account=h['account'],tick=w['tick'],percent=str(pct),thresholds=thresholds,policy='Simulation significant-interest monitoring; not jurisdiction-specific legal advice')
     w['ownership_disclosures'].append(r);self.audit('public_shareholding_disclosure',r.copy())

 def public_resolution(self,p):
  from .engine import uid
  w=self.state;symbol=p['symbol'];view=self.public_ownership(symbol);account=p['account'];self.authority(account,'govern')
  if not view['reconciled']:raise ValueError('Voting register is unreconciled; no public governance authority can be exercised')
  if self.is_frozen(account) or self.is_frozen(view['issuer']):raise ValueError('Restrictions block public governance')
  if w['entities'][view['issuer']]['status']!='ACTIVE':raise ValueError('Issuer is not active')
  holding=next((h for h in view['shareholders'] if h['account']==account),None)
  if not holding or D(holding['voting_shares'])<=0:raise ValueError('Eligible registered shares are required; derivatives confer no votes')
  kind=p.get('kind','propose')
  if kind=='propose':
   if any(r['symbol']==symbol and r['status']=='OPEN' for r in w['public_resolutions']):raise ValueError('Review the existing public resolution first')
   action=p.get('action','board')
   if action not in ('board','operating_budget','dividend'):raise ValueError('Supported public resolutions: board, operating budget or dividend')
   terms={}
   if action in ('operating_budget','dividend'):
    per=D(str(p['per_share'])) if action=='dividend' and 'per_share' in p else None
    if per is not None and (not per.is_finite() or per<=0 or per!=per.quantize(D('.01'))):raise ValueError('Dividend per share must be positive whole pennies in GBP')
    amount=per*D(view['voting_total']) if per is not None else D(str(p.get('amount',0)))
    if not amount.is_finite() or amount<=0 or amount!=amount.quantize(D('.01')):raise ValueError('A positive penny-denominated budget is required')
    terms={'amount':amt(amount)}
    if per is not None:terms['per_share']=amt(per)
   r=dict(id=uid(),symbol=symbol,proposer=account,action=action,terms=terms,status='OPEN',created=w['tick'],expires=w['tick']+168,
    record_date=w['tick'],eligible={h['account']:h['voting_shares'] for h in view['shareholders'] if D(h['voting_shares'])>0},voting_total=view['voting_total'],ballots={})
   w['public_resolutions'].append(r)
  else:
   r=next((r for r in w['public_resolutions'] if r['id']==p.get('id') and r['symbol']==symbol),None)
   if not r or r['status']!='OPEN' or w['tick']>r['expires']:raise ValueError('Resolution is closed or expired')
   if kind=='vote':
    if D(r['eligible'].get(account,0))<=0:raise ValueError('Account had no eligible votes on the record date')
    choice=p.get('choice','FOR')
    if choice not in ('FOR','AGAINST','ABSTAIN'):raise ValueError('Invalid ballot')
    r['ballots'][account]=choice
   elif kind=='execute':
    yes=sum((D(r['eligible'][a]) for a,c in r['ballots'].items() if c=='FOR'),D(0))
    if yes<=D(r['voting_total'])/2:raise ValueError('Affirmative majority of all eligible voting shares is required')
    # Recheck current votes as well: no stale resolution grants control after a disposal.
    current=sum((D(h['voting_shares']) for h in view['shareholders'] if r['ballots'].get(h['account'])=='FOR'),D(0))
    if current<=D(view['voting_total'])/2:raise ValueError('Supporting holders no longer have majority voting control')
    issuer=w['issuers'][symbol];entity=w['entities'][view['issuer']]
    if r['action']=='board':
     entity['directors']=['public_player_board','model_independent_board'];entity['signatories']['public_player_board']=['govern','disclose'];issuer['board_resolution']=r['id'];entity['payment_limit']=entity['payment_limit'] if D(entity['payment_limit'])>0 else '1000000.00'
    elif r['action']=='dividend':self.public_pay_dividend(r)
    else:
     if not issuer.get('board_resolution'):raise ValueError('Elect a board before directing operating investment')
     amount=D(r['terms']['amount'])
     if self.available_cash(view['issuer'])<amount:raise ValueError('Issuer has insufficient unrestricted funding')
     supplier=self.ma_account('suppliers');self.post('Public board approved productive investment '+r['id'],{'cash:'+view['issuer']:-amount,'productive:'+view['issuer']:amount,'cash:'+supplier:amount,'pnl:'+supplier:-amount})
     issuer['capacity_investment']=amt(D(issuer.get('capacity_investment',0))+amount)
    r['status']='EXECUTED';r['executed']=w['tick']
   else:raise ValueError('Unknown public resolution instruction')
  self.audit('public_resolution',copy.deepcopy(r));return r

 def validate_public_lending(self):
  w=self.state
  if not w.get('public_ownership_version'):return
  for symbol in w.get('share_register',{}):
   if symbol not in w.get('issuers',{}):continue
   loans=[l for l in w['stock_loans'] if l['symbol']==symbol]
   for loan in loans:
    if D(loan['quantity'])<0 or loan['lender']==loan['borrower']:raise ValueError('Invalid attributed stock loan')
   borrowers={l['borrower'] for l in loans}|{k.rsplit(':',1)[0] for k in w['legacy_stock_borrow'] if k.rsplit(':',1)[-1]==symbol}
   borrowers|={p['account'] for p in w['positions'].values() if p['symbol']==symbol and D(p['qty'])<0}
   for borrower in borrowers:
    actual=max(D(0),-D(w['positions'].get(borrower+':'+symbol,{}).get('qty',0)))
    recorded=sum((D(l['quantity']) for l in loans if l['borrower']==borrower),D(0))+D(w['legacy_stock_borrow'].get(borrower+':'+symbol,0))
    if actual!=recorded:raise ValueError('Attributed stock borrowing does not reconcile: '+symbol)
   for lender in {l['lender'] for l in loans}:
    lent=sum((D(l['quantity']) for l in loans if l['lender']==lender),D(0));held=max(D(0),D(w['positions'].get(lender+':'+symbol,{}).get('qty',0)))
    if lent>held:raise ValueError('Stock lender disposed of encumbered title')

 def ownership_context(self,entity):
  roots=self.ownership_roots(entity);terminals={r['owner'] for r in roots if r['status'] not in ('CYCLE','UNDISCLOSED NOMINEE')}
  related=[]
  for id in self.state.get('entities',{}):
   if id==entity:continue
   other=self.ownership_roots(id)
   if any(r['owner'] in terminals and r['status'] not in ('CYCLE','UNDISCLOSED NOMINEE') for r in other):related.append(id)
  return dict(entity=entity,ultimate_ownership=roots,related_entities=related,managed_by_player=self.state['entities'].get(entity,{}).get('controlled',False),
   note='Recorded ownership context, not evidence of wrongdoing. Discretionary fund management and beneficial client ownership remain distinct; undisclosed nominees are not resolved by inference.')
