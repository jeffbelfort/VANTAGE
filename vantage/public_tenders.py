"""Cash-backed public tenders over the existing registered holdings.
No synthetic financing, squeeze-out or delisting. Nominee client pools issue
explicit simulated instructions; title and proceeds stay in their existing account.
"""
import copy
from decimal import Decimal as D
from .integrity import amt

class PublicTenderMixin:
 def public_tender_shareholders(self,bid,view=None):
  from .pretrade import pending
  w=self.state;view=view or self.public_ownership(bid['symbol']);ins=self.instrument(bid['symbol']);fx=self.fx_rate(ins['currency']);market=D(ins['price'])*fx;fair=D(ins.get('model_fundamental',ins['price']))*fx;committed={}
  for order in pending(self,None,bid['symbol']):
   if order['side']=='sell':committed[order['account']]=committed.get(order['account'],D(0))+D(order['remaining'])
  competing=max([D(b['price_gbp']) for b in w.get('public_tenders',[]) if b['symbol']==bid['symbol'] and b['id']!=bid['id'] and b['status']=='OPEN' and w['tick']<=b['expires']] or [D(0)])
  rows=[]
  for h in view['shareholders']:
   account=h['account'];entity=w['entities'].get(account,{});actor=next((a for a in w['participants'] if a['account']==account),None);nominee=entity.get('kind')=='custody';strategic=entity.get('kind')=='strategic_owner';instruction=bid.get('negotiations',{}).get(account,{})
   other=self.public_tender_committed(account,bid['symbol'],bid['id']);reserved=committed.get(account,D(0))+other;available=max(D(0),D(h['registered_shares'])-reserved)
   premium=D('1.50') if strategic else D('1.20') if nominee else D('1.15') if actor and actor.get('strategy') in ('value','pension') else D('1.08')
   cash_target=D(str((actor or {}).get('opening_listed',0)))*D(str((actor or {}).get('mandate',{}).get('cash_ratio',0)));need=max(D(0),cash_target-self.cash(account))/max(D(1),cash_target);premium-=min(D('.05'),need*D('.05'))
   ask=max(max(fair,market)*premium,competing).quantize(D('.01'),rounding='ROUND_CEILING');eligible=True;reason='Offer meets public valuation, strategy/control premium and liquidity needs'
   if account==bid['buyer'] or entity.get('controlled'):eligible=False;reason='Bidder or player-controlled holder; no independent shareholder consent inferred'
   elif self.is_frozen(account):eligible=False;reason='Holder is restricted'
   elif not actor or not (strategic or nominee or actor.get('mandate',{}).get('allow_trade')):eligible=False;reason='Investment mandate does not authorise disposal'
   elif nominee and not instruction.get('requested'):eligible=False;reason='Client instructions required: request the aggregated client pool response through this nominee'
   elif available<1:eligible=False;reason='No unencumbered title: shares are lent or committed to orders/other offers'
   status='ACCEPT' if eligible and D(bid['price_gbp'])>=ask else 'COUNTEROFFER' if eligible else 'UNAVAILABLE'
   if status=='COUNTEROFFER':reason='Requires the greater of public fair/market value plus strategy premium and competing funded offers'
   known=[w['entities'].get(r['owner'],{}).get('name',r['owner']) for r in h.get('ultimate_beneficiaries',[]) if r['status'] not in ('UNDISCLOSED NOMINEE','CYCLE')]
   beneficiaries='Undisclosed aggregate client pool; simulated client instructions, not custodian discretion' if nominee else ', '.join(dict.fromkeys(known)) or 'Recorded registered holder'
   rows.append(dict(account=account,held=h['shares'],lent=h['lent'],reserved=str(reserved),available=str(available),accepted=bid.get('acceptances',{}).get(account,'0'),offer_price=bid['price_gbp'],asking_price=amt(ask),status=status,reason=reason,nominee=nominee,beneficial_owners=beneficiaries,basis=dict(market_gbp=amt(market),fair_gbp=amt(fair),required_premium=str(premium-1),competing_gbp=amt(competing)),eligible=eligible))
  return rows

 def public_tender_committed(self,account,symbol,exclude=None):
  """Accepted title is reserved until withdrawal, expiry or settlement."""
  return sum((D(b.get('acceptances',{}).get(account,0)) for b in self.state.get('public_tenders',[]) if b['id']!=exclude and b['symbol']==symbol and b['status']=='OPEN' and self.state['tick']<=b['expires']),D(0))

 def public_tender(self,p):
  from .engine import uid,positive
  w=self.state;kind=p.get('kind','launch')
  bids=w.setdefault('public_tenders',[])
  if kind=='launch':
   symbol=p['symbol'];buyer=p['buyer'];view=self.public_ownership(symbol);entity=self.authority(buyer,'govern');self.authority(buyer,'trade');self.authority(buyer,'payment')
   if not view['reconciled']:raise ValueError('Reconciled registered ownership is required for a public offer')
   if self.ownership_cycle(view['issuer'],buyer):raise ValueError('An issuer or its subsidiary cannot acquire its own parent through this tender workflow')
   if buyer==view['issuer'] or self.is_frozen(buyer) or self.is_frozen(view['issuer']):raise ValueError('Offer parties are ineligible or restricted')
   if any(b['buyer']==buyer and b['symbol']==symbol and b['status']=='OPEN' for b in bids):raise ValueError('Review the existing offer first')
   ins=self.instrument(symbol);price=positive(p['price_gbp']);quantity=int(p['quantity']);minimum=int(p.get('minimum',quantity))
   if D(str(p['quantity']))!=quantity or D(str(p.get('minimum',quantity)))!=minimum:raise ValueError('Offer quantities must be whole shares')
   own=D(next((h['voting_shares'] for h in view['shareholders'] if h['account']==buyer),'0'))
   if not 1<=minimum<=quantity or quantity>D(view['voting_total'])-own:raise ValueError('Invalid offer quantity or minimum acceptance')
   self.require_fund_control_permission(buyer)
   short=D(w['positions'].get(buyer+':'+symbol,{}).get('qty',0))
   if short<0:raise ValueError('Cover the bidder short position before a corporate offer')
   consideration=(price*quantity).quantize(D('.01'));fee=max(D(500),consideration*D('.001')).quantize(D('.01'))
   available=self.available_cash(buyer)
   if consideration+fee>available:
    # Give the actual failed instruction's figures; rejected offers intentionally
    # leave no funded bid or financial mutation behind.
    low=0;high=int(D(view['voting_total'])-own)
    while low<high:
     middle=(low+high+1)//2;cost=(price*middle).quantize(D('.01'));charge=max(D(500),cost*D('.001')).quantize(D('.01'))
     if cost+charge<=available:low=middle
     else:high=middle-1
    raise ValueError(f"Public offer requires fully funded consideration and fees; financing is not generated. Buyer: {entity['name']} ({buyer}). Available cash £{available:,.2f}; {quantity:,} shares at £{price:,.2f} GBP require £{consideration:,.2f} consideration + £{fee:,.2f} fees = £{consideration+fee:,.2f}. Shortfall £{consideration+fee-available:,.2f}. Maximum affordable at this GBP price: {low:,} shares. USD market quotes must be converted to GBP before entering an offer.")
   if consideration+fee>D(entity['payment_limit']) and not entity['controls']:raise ValueError('Independent bidder board approval is required above delegated spending authority')
   board=None
   if consideration+fee>D(entity['payment_limit']):
    self.authority(buyer,'govern','board');board='board'
   id=uid();escrow='tender_'+id;suppliers=self.ma_account('suppliers')
   self.post('Funded public offer '+id,{'cash:'+buyer:-consideration-fee,'escrow:'+buyer+':'+id:consideration,'expense:takeover:'+buyer:fee,'cash:'+escrow:consideration,'debt:'+escrow+':offer':-consideration,'cash:'+suppliers:fee,'pnl:'+suppliers:-fee})
   bid=dict(id=id,symbol=symbol,buyer=buyer,issuer=view['issuer'],quantity=quantity,minimum=minimum,price_gbp=amt(price),reserved=amt(consideration),fee=amt(fee),escrow=escrow,
    status='OPEN',created=w['tick'],review_after=w['tick']+24,expires=w['tick']+168,acceptances={},review=None,financing='Cash already committed to segregated escrow',bidder_roots=self.ownership_roots(buyer),bidder_board=board)
   bids.append(bid);self.market_event({'symbol':symbol,'kind':'acquisition','severity':0});self.audit('public_tender_launched',copy.deepcopy(bid));return bid
  bid=next((b for b in bids if b['id']==p['id']),None)
  if not bid or bid['status']!='OPEN':raise ValueError('Offer is not open')
  buyer=bid['buyer'];self.authority(buyer,'govern');view=self.public_ownership(bid['symbol'])
  if kind=='withdraw':
   self.public_tender_refund(bid);bid['status']='WITHDRAWN'
  elif kind in ('amend','extend','negotiate'):
   if w['tick']>bid['expires']:raise ValueError('Offer has expired; its terms can no longer be amended or extended')
   if not view['reconciled'] or self.is_frozen(buyer) or self.is_frozen(bid['issuer']):raise ValueError('Ownership or regulatory restrictions block this offer action')
   if kind=='amend':
    price=positive(p['price_gbp']).quantize(D('.01'))
    if price<=D(bid['price_gbp']):raise ValueError('Amendment must increase the offer price')
    entity=self.authority(buyer,'payment');self.authority(buyer,'trade');total=(price*bid['quantity']).quantize(D('.01'));fee=max(D(500),total*D('.001')).quantize(D('.01'));extra=total-D(bid['reserved']);extra_fee=max(D(0),fee-D(bid['fee']))
    if self.cash(bid['escrow'])!=D(bid['reserved']):raise ValueError('Existing escrow does not reconcile with the offer commitment')
    if extra+extra_fee>self.available_cash(buyer):raise ValueError('Insufficient available cash for additional maximum consideration and incremental fees')
    if total+fee>D(entity['payment_limit']):
     if not entity['controls']:raise ValueError('Increase bidder payment authority or obtain independent board approval')
     self.authority(buyer,'govern','board')
    suppliers=self.ma_account('suppliers');self.post('Public offer price amendment '+bid['id'],{'cash:'+buyer:-extra-extra_fee,'escrow:'+buyer+':'+bid['id']:extra,'expense:takeover:'+buyer:extra_fee,'cash:'+bid['escrow']:extra,'debt:'+bid['escrow']+':offer':-extra,'cash:'+suppliers:extra_fee,'pnl:'+suppliers:-extra_fee})
    bid.setdefault('amendments',[]).append(dict(tick=w['tick'],old_price=bid['price_gbp'],price=amt(price),additional_escrow=amt(extra),additional_fee=amt(extra_fee)));bid.update(price_gbp=amt(price),reserved=amt(total),fee=amt(fee))
   elif kind=='extend':
    hours=int(p.get('hours',168))
    if hours!=D(str(p.get('hours',168))) or not 1<=hours<=168 or bid['expires']+hours>bid['created']+720:raise ValueError('Extend by 1–168 hours, up to 30 days from launch')
    bid['expires']+=hours;bid.setdefault('extensions',[]).append(dict(tick=w['tick'],hours=hours,expires=bid['expires']))
   else:
    account=p['shareholder'];row=next((r for r in self.public_tender_shareholders(bid,view) if r['account']==account),None)
    if not row:raise ValueError('Shareholder has no registered title in this issuer')
    if account==buyer or w['entities'].get(account,{}).get('controlled'):raise ValueError('Cannot infer independent acceptance from a controlled shareholder')
    bid.setdefault('negotiations',{})[account]=dict(requested=True,tick=w['tick'],price=bid['price_gbp'],basis='Deterministic response of the existing aggregated beneficial client pool' if row['nominee'] else 'Direct registered shareholder approach')
   if w['tick']>=bid['review_after']:self.public_tender({'kind':'review','id':bid['id']})
   if kind=='negotiate':bid.setdefault('negotiation_history',[]).append(dict(shareholder=p['shareholder'],**copy.deepcopy(bid['negotiations'][p['shareholder']])))
   self.audit('public_tender_'+kind,dict(id=bid['id'],tick=w['tick'],price=bid['price_gbp'],shareholder=p.get('shareholder')))
  elif kind=='review':
   self.require_fund_control_permission(buyer)
   if w['tick']<bid['review_after']:raise ValueError('Public review requires at least 24 simulation hours')
   if w['tick']>bid['expires']:raise ValueError('Offer expired; withdraw to release escrow')
   if not view['reconciled'] or self.is_frozen(buyer) or self.is_frozen(bid['issuer']):raise ValueError('Ownership or regulatory restrictions block review')
   cases=[c for c in w.get('legal_cases',[]) if c['entity'] in (buyer,bid['issuer']) and c['stage'] not in ('CLOSED','PRELIMINARY')]
   sector=self.instrument(bid['symbol']).get('sector','').lower()
   if cases or any(t in sector for t in ('defence','defense','financial','bank')):raise ValueError('Regulatory review is blocked: active proceedings or a sector requiring unsupported specialist approval')
   # Scenario-level ordinary-company review, explicitly not a model of every jurisdiction.
   bid['review']=dict(tick=w['tick'],status='CLEARED',basis='Simulation ordinary-sector review; no active formal proceedings or restricted-sector permissions')
   price=D(bid['price_gbp']);ins=self.instrument(bid['symbol']);fair=D(ins.get('model_fundamental',ins['price']))*self.fx_rate(ins['currency']);market=D(ins['price'])*self.fx_rate(ins['currency'])
   competing=max([D(b['price_gbp']) for b in bids if b['symbol']==bid['symbol'] and b['id']!=bid['id'] and b['status']=='OPEN' and w['tick']<=b['expires']] or [D(0)])
   remaining=D(bid['quantity']);acceptances={};decisions=self.public_tender_shareholders(bid,view)
   for row in sorted(decisions,key=lambda r:r['account']):
    if row['status']!='ACCEPT':continue
    account=row['account'];q=min(remaining,D(row['available'])).to_integral_value(rounding='ROUND_DOWN')
    if q>0:acceptances[account]=str(q);remaining-=q
   bid['acceptances']=acceptances
   bid['shareholder_decisions']=decisions
   for row in decisions:
    row['accepted']=acceptances.get(row['account'],'0')
    if row['account'] in bid.get('negotiations',{}):bid['negotiations'][row['account']].update(response=row['status'],asking_price=row['asking_price'],reason=row['reason'])
   bid['shareholder_review']=dict(tick=w['tick'],fair_value_gbp=str(fair),market_gbp=str(market),competing_price_gbp=str(competing),basis='Actual unencumbered title and public investment evidence; nominee pools respond only after an explicit client-instruction request')
  elif kind=='complete':
   self.authority(buyer,'payment');self.authority(buyer,'trade')
   if w['tick']>bid['expires']:raise ValueError('Offer expired; unspent escrow is returned by the offer lifecycle or can be withdrawn')
   if not bid['review']:raise ValueError('A regulatory and shareholder review is required before completion')
   # Revalidate consent and eligibility atomically with settlement. Requiring the
   # player to review and complete in one simulation hour races the running clock.
   self.public_tender({'kind':'review','id':bid['id']})
   if not view['reconciled'] or self.is_frozen(buyer) or self.is_frozen(bid['issuer']):raise ValueError('Ownership or restrictions prevent completion')
   if any(c['entity'] in (buyer,bid['issuer']) and c['stage'] not in ('CLOSED','PRELIMINARY') for c in w.get('legal_cases',[])):raise ValueError('Regulatory proceedings prevent completion')
   if any(b['id']!=bid['id'] and b['symbol']==bid['symbol'] and b['status']=='OPEN' and w['tick']<=b['expires'] and D(b['price_gbp'])>D(bid['price_gbp']) for b in bids):raise ValueError('A higher competing offer requires fresh shareholder consideration')
   quantity=sum((D(q) for q in bid['acceptances'].values()),D(0))
   if quantity<bid['minimum']:raise ValueError(f"Insufficient genuine shareholder acceptance: {quantity:,.0f} of {bid['minimum']:,} minimum shares; review again before expiry or withdraw")
   actual={h['account']:D(h['registered_shares']) for h in view['shareholders']}
   if any(q>actual.get(s,D(0)) or self.is_frozen(s) for s,q in ((s,D(q)) for s,q in bid['acceptances'].items())):raise ValueError('Tendered holdings are no longer available; review again')
   amount=(quantity*D(bid['price_gbp'])).quantize(D('.01'))
   entity=self.state['entities'][buyer]
   if amount>D(entity['payment_limit']):self.authority(buyer,'govern','board')
   if self.cash(bid['escrow'])<amount:raise ValueError('Committed offer funds are insufficient')
   key=buyer+':'+bid['symbol'];position=w['positions'].get(key,dict(account=buyer,symbol=bid['symbol'],qty='0',cost='0',borrowed='0'))
   if D(position['qty'])<0:raise ValueError('Bidder has opened a short position; completion blocked')
   for seller,q in bid['acceptances'].items():
    qty=D(q);skey=seller+':'+bid['symbol'];pos=w['positions'][skey];cost=(D(pos['cost'])*qty/D(pos['qty'])).quantize(D('.01'));paid=(qty*D(bid['price_gbp'])).quantize(D('.01'))
    self.post('Public tender shareholder settlement '+bid['id']+' / '+seller,{'cash:'+bid['escrow']:-paid,'debt:'+bid['escrow']+':offer':paid,'cash:'+seller:paid,'inventory:'+skey:-cost,'pnl:'+seller:cost-paid,'inventory:'+key:paid,'escrow:'+buyer+':'+bid['id']:-paid})
    pos['qty']=str(D(pos['qty'])-qty);pos['cost']=amt(D(pos['cost'])-cost)
    if D(pos['qty'])==0:w['positions'].pop(skey)
    position['qty']=str(D(position['qty'])+qty);position['cost']=amt(D(position['cost'])+paid)
   w['positions'][key]=position;bid['filled']=str(quantity);bid['settled']=amt(amount);self.public_tender_refund(bid);bid['status']='COMPLETED';bid['completed']=w['tick']
   self.audit('public_tender_settlement',copy.deepcopy(bid))
  else:raise ValueError('Unknown public offer instruction')
  return bid

 def public_tender_refund(self,bid):
  remaining=self.cash(bid['escrow'])
  if remaining:self.post('Public offer unspent commitment returned '+bid['id'],{'cash:'+bid['escrow']:-remaining,'debt:'+bid['escrow']+':offer':remaining,'cash:'+bid['buyer']:remaining,'escrow:'+bid['buyer']+':'+bid['id']:-remaining})

 def public_offer_tick(self):
  w=self.state
  for bid in w.get('public_tenders',[]):
   if bid['status']=='OPEN' and w['tick']>bid['expires']:
    self.public_tender_refund(bid);bid['status']='EXPIRED';self.audit('public_tender_expired',{'id':bid['id']})
  for resolution in w.get('public_resolutions',[]):
   if resolution['status']=='OPEN' and w['tick']>resolution['expires']:resolution['status']='EXPIRED'
