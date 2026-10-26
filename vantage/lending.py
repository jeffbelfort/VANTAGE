"""Term credit with explicit underwriting and consistent prospective 30/360 contracts."""
from decimal import Decimal as D
from .integrity import amt

class LendingMixin:
 def credit_offer(self,p):
  acct=self.account(p);bank=next((b for b in self.state['banks'] if b['id']==p.get('bank','sterling')),None)
  if not bank:raise ValueError('Unknown bank')
  if bank.get('entity'):self.refresh_player_banks()
  principal=D(amt(p['amount']));months=int(p.get('months',12))
  if principal<=0 or not 1<=months<=360:raise ValueError('Positive principal and 1–360 month term required')
  if self.is_frozen(acct):raise ValueError(self.restriction_message(acct,'Financing'))
  metrics=self.metrics(acct);equity=D(metrics['equity']);debt=D(metrics['debt']);cash=self.available_cash(acct)
  outstanding=sum((D(l['balance']) for l in self.state['loans'] if l['account']==acct and l['status']!='REPAID'),D(0));leverage=(debt+principal)/max(D(1),equity)
  oldservice=sum((D(l['payment']) for l in self.state['loans'] if l['account']==acct and l['status']!='REPAID'),D(0))
  base=D(str(self.state['macro']['rate']));spread=D(str(bank['spread']));credit=D(max(0,750-self.state['credit']))/100
  risk=leverage*D('2')+D(str(self.state['macro']['stress']))/100+((D(bank['loans'])+principal)/max(D(1),D(bank['equity'])))*D('.05')
  rate=max(D('.01'),D(str(bank['lending_rate'])) if bank.get('entity') else base+spread+credit+risk).quantize(D('.0001'));monthly=rate/1200;payment=(principal*monthly/(1-(1+monthly)**(-months))).quantize(D('.01'))
  limit=max(D(1000),max(0,equity)*D('.6'));coverage=(cash+principal)/max(D(1),(oldservice+payment)*12)
  bank_assets=D(bank['cash'])+D(bank['loans'])-D(bank.get('allowance','0'))+D(bank.get('other_assets','0'));capital_ratio=D(bank['equity'])/max(D(1),bank_assets)
  lender_exposure=sum((D(l['balance']) for l in self.state['loans'] if l['account']==acct and l['bank']==bank['id']),D(0))+principal
  reasons=[]
  if bank.get('entity'):
   if bank['licence']!='AUTHORISED' or not bank['lending_enabled']:reasons.append('Player bank lending is not authorised or enabled')
   if acct==bank['entity']:reasons.append('A bank cannot lend to itself')
   if D(bank['equity'])<D(self.state.get('banking_rules',{}).get('minimum_capital','100000')):reasons.append('Bank minimum operating capital requirement')
   room=max(D(0),self.available_cash(bank['entity'])-D(bank['deposits'])*D(str(bank['reserve_ratio'])))
   if principal>min(D(bank['max_loan']),room):reasons.append('Loan exceeds product limit or unencumbered reserves')
  if bank.get('status')=='DISTRESSED' or capital_ratio<D('.08'):reasons.append('Lender capital constraint')
  if self.state['credit']<550:reasons.append('Credit quality below policy')
  if debt+principal>limit:reasons.append('Aggregate debt exceeds 60% of net assets')
  if principal>D(bank['cash'])*D('.05'):reasons.append('Facility exceeds 5% of lender liquidity')
  if lender_exposure>D(bank['equity'])*D('.25'):reasons.append('Single-borrower exposure exceeds 25% of lender equity')
  if coverage<D('1.25'):reasons.append('Available liquidity cannot cover 12 months of aggregate debt service at 1.25×')
  if any(l['status']=='DEFAULT' and l['account']==acct for l in self.state['loans']):reasons.append('Borrower has a defaulted obligation')
  return dict(approved=not reasons,reasons=reasons,limit=amt(max(0,limit-debt)),rate=float(rate),payment=amt(payment),coverage=str(coverage),aggregate_monthly_service=amt(oldservice+payment),existing_principal=amt(outstanding),lender_exposure=amt(lender_exposure),interest_convention='30/360 SIMPLE; 720 simulation hours per month',bank=bank,account=acct,principal=amt(principal),months=months)

 def originate_loan(self,p):
  from .engine import uid,positive
  positive(p['amount']);offer=self.credit_offer(p);bank=offer.pop('bank');acct=offer.pop('account')
  if not offer['approved']:
   self.message(bank['name'],'Credit application declined','; '.join(offer['reasons']));return offer
  principal=D(offer['principal']);loan=dict(id=uid(),account=acct,bank=bank['id'],principal=amt(principal),principal_outstanding=amt(principal),unpaid_interest='0.00',balance=amt(principal),rate=offer['rate'],months=offer['months'],payment=offer['payment'],next_due=self.state['tick']+720,originated_tick=self.state['tick'],installments=0,status='ACTIVE',missed=0,accrued='0.00',interest_residual='0',interest_convention='30/360 SIMPLE',underwriting={k:v for k,v in offer.items() if k not in ('principal','months')},payments=[])
  self.state['loans'].append(loan);bank['cash']=amt(D(bank['cash'])-principal);bank['loans']=amt(D(bank['loans'])+principal);self.bank_sync(bank,'Lender disbursement '+loan['id'])
  self.post('Loan disbursement',{'cash:'+acct:principal,'debt:'+acct+':'+loan['id']:-principal})
  self.message(bank['name'],'Facility approved',f"£{principal:,.2f}; {loan['rate']:.4f}% nominal APR, 30/360 simple interest. Payment £{D(loan['payment']):,.2f} every 720 simulation hours. Aggregate monthly service £{D(offer['aggregate_monthly_service']):,.2f}; 12-month liquidity coverage {D(offer['coverage']):.2f}×.")
  return {'approved':True,'loan':loan,'underwriting':offer}

 def repay_credit(self,p):
  from .engine import positive
  loan=next((l for l in self.state['loans'] if l['id']==p['id']),None)
  if not loan or loan['status']=='REPAID':raise ValueError('No active loan found')
  amount=min(positive(p['amount']),D(loan['balance']));acct=loan['account']
  if self.available_cash(acct)<amount:raise ValueError('Insufficient unrestricted cash to repay loan')
  before=D(loan['balance']);bank=next(b for b in self.state['banks'] if b['id']==loan['bank'])
  if 'principal_outstanding' not in loan:
   loan['unpaid_interest']=amt(max(0,before-D(loan['principal'])));loan['principal_outstanding']=amt(before-D(loan['unpaid_interest']))
  interest=min(amount,D(loan['unpaid_interest']));principal=amount-interest
  loan['unpaid_interest']=amt(D(loan['unpaid_interest'])-interest);loan['principal_outstanding']=amt(D(loan['principal_outstanding'])-principal)
  self.post('Loan repayment',{'cash:'+acct:-amount,'debt:'+acct+':'+loan['id']:amount});loan['balance']=amt(before-amount)
  bank['cash']=amt(D(bank['cash'])+amount);bank['loans']=amt(D(bank['loans'])-amount)
  allowance=D(loan.get('allowance','0'));release=(allowance*amount/before).quantize(D('.01')) if before else D(0)
  if release:loan['allowance']=amt(allowance-release);bank['allowance']=amt(D(bank.get('allowance','0'))-release);bank['equity']=amt(D(bank['equity'])+release)
  self.bank_sync(bank,'Lender repayment '+loan['id']);loan.setdefault('payments',[]).append(dict(time=self.state['time'],tick=self.state['tick'],amount=amt(amount),principal=amt(principal),interest=amt(interest)))
  if D(loan['balance'])==0:loan['status']='REPAID';self.state['credit']=min(850,self.state['credit']+5)
  return loan

 def service_loans(self):
  for loan in self.state['loans']:
   if loan['status']=='REPAID':continue
   lender=next(b for b in self.state['banks'] if b['id']==loan['bank'])
   if lender.get('entity'):
    if loan.get('player_accrual_tick')==self.state['tick']:continue
    loan['player_accrual_tick']=self.state['tick']
   bank=next(b for b in self.state['banks'] if b['id']==loan['bank']);acct=loan['account'];legacy=loan.get('interest_convention')!='30/360 SIMPLE'
   if loan['status']!='DEFAULT':
    base=D(loan['balance']) if legacy else D(loan['principal_outstanding']);denominator=D(100*365*24) if legacy else D(1200*720)
    raw=base*D(str(loan['rate']))/denominator+D(loan.get('interest_residual','0'));interest=raw.quantize(D('.01'));loan['interest_residual']=str(raw-interest)
    if interest:
     self.post('Loan interest accrual',{'expense:interest:'+acct:interest,'debt:'+acct+':'+loan['id']:-interest});loan['balance']=amt(D(loan['balance'])+interest);loan['accrued']=amt(D(loan['accrued'])+interest)
     if not legacy:loan['unpaid_interest']=amt(D(loan['unpaid_interest'])+interest)
     elif 'unpaid_interest' in loan:loan['unpaid_interest']=amt(D(loan['unpaid_interest'])+interest)
     bank['loans']=amt(D(bank['loans'])+interest);bank['equity']=amt(D(bank['equity'])+interest);self.bank_sync(bank,'Lender interest '+loan['id'])
   if self.state['tick']<loan['next_due']:continue
   event='loan-due:'+loan['id']+':'+str(loan['next_due'])
   if self.db.execute('select 1 from scheduled_events where world=? and event=?',(self.state['id'],event)).fetchone():continue
   self.db.execute('insert into scheduled_events values(?,?,?)',(self.state['id'],event,self.state['time']))
   loan['installments']=loan.get('installments',0)+1;payment=D(loan['balance']) if loan['installments']>=loan['months'] else min(D(loan['payment']),D(loan['balance']))
   if self.available_cash(acct)>=payment and not self.is_frozen(acct):self.repay_credit({'id':loan['id'],'amount':payment})
   else:
    loan['missed']+=1;self.state['credit']=max(300,self.state['credit']-30);self.message('Credit Operations','Scheduled payment missed',f"£{payment:,.2f} is due on {loan['id']}. Liability persists; restricted collateral is not spent.")
    if loan['missed']>=3 and loan['status']!='DEFAULT':
     loan['status']='DEFAULT';impairment=(D(loan['balance'])*D('.5')).quantize(D('.01'));loan['allowance']=amt(impairment);bank['allowance']=amt(D(bank.get('allowance','0'))+impairment);bank['equity']=amt(D(bank['equity'])-impairment);self.bank_sync(bank,'Credit impairment '+loan['id'])
     if D(bank['equity'])<=0:bank['status']='DISTRESSED'
     self.news('Credit default reduces lender capital',f"{bank['name']} recognised £{impairment:,.2f} expected credit loss on an overdue facility. Borrower obligations persist.",'CREDIT')
   loan['next_due']+=720
