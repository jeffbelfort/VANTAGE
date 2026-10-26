"""Account statements, prospective migrations and explicit compensation rules."""
import json
from decimal import Decimal as D
from datetime import datetime,timezone
from pathlib import Path

def amt(v):return format(D(str(v)).quantize(D('.01')),'f')
def belongs(key,account):
 if key=='pnl:'+account or key=='equity:'+account:return True
 if key.startswith('expense:'):return key.endswith(':'+account)
 return any(key.startswith(prefix+account+':') or key==prefix+account for prefix in ('escrow:','cash:','inventory:','savings:','investment:','receivable:','debt:','credit_asset:','treasury:','bond_interest:','fed_reserve:','treasury_discount:','cashfx:','claim:','allowance:','holding:'))

class IntegrityMixin:
 def bank_sync(self,bank,description):
  if bank.get('entity'):
   entity=bank['entity'];lines={}
   for field,key,sign in [('cash','cash:'+entity,1),('loans','credit_asset:'+entity+':bank_loans',1),('deposits','debt:'+entity+':customer_deposits',-1),('allowance','allowance:'+entity+':bank_loans',-1)]:
    delta=D(bank.get(field,'0'))*sign-self.balance(key)
    if delta:lines[key]=delta
   residual=-sum(lines.values(),D(0))
   if residual<0:lines['pnl:'+entity]=residual
   elif residual>0:lines['expense:'+('bank_interest' if description=='Bank savings interest' else 'bank_credit_loss')+':'+entity]=residual
   if lines:self.post(description,lines)
   if description.startswith('Lender interest '):bank['interest_income']=amt(D(bank['interest_income'])-min(D(0),residual))
   if description=='Bank savings interest':bank['interest_expense']=amt(D(bank['interest_expense'])+max(D(0),residual))
   return
  # A separate balanced subledger for each lender. Deposit and equity balances are credits.
  lines={}
  for field,sign in [('cash',1),('loans',1),('deposits',-1),('equity',-1),('allowance',-1)]:
   key='bank:'+bank['id']+':'+field;target=D(bank.get(field,'0'))*sign;delta=target-self.balance(key)
   if delta:lines[key]=delta
  if lines:self.post(description,lines)

 def migrate_financial_state(self):
  w=self.state
  if not w or w.get('financial_version',0)>=2:return False
  old={k:v for k,v in w['balances'].items()}
  for fund in w['funds']:
   if not fund.get('compensation_authorized'):
    fund['legacy_compensation']={'management':fund['management'],'performance':fund['performance'],'disabled_at':w['time']}
    fund['management']=0;fund['performance']=0;fund['compensation_authorized']=False
  for i,order in enumerate(reversed(w['orders'])):order.setdefault('sequence',i+1)
  w['order_sequence']=len(w['orders']);w['financial_version']=2;w['paused']=True
  for bank in w['banks']:self.bank_sync(bank,'Bank subledger migration baseline')
  for fill in w['fills']:self.db.execute('insert or ignore into executions values(?,?,?)',(fill['id'],w['id'],json.dumps(fill)))
  self.audit('financial_migration_v2',{'policy':'Unconfigured compensation disabled prospectively; prior balances and journal preserved','previous_balances':old,'version':2})
  self.message('Financial Control','Financial integrity upgrade','Historical balances and entries are preserved. Unauthorised preset management/performance compensation is disabled for future periods. Review Financial Statements for the complete NAV bridge. Historical fee transfers have not been reversed. Markets are paused for review.')
  self.persist();return True

 def compensation(self,p):
  fund=next(f for f in self.state['funds'] if f['id']==p['fund'])
  if self.is_frozen(fund['id']):raise ValueError('Restricted institutions cannot authorise new compensation')
  if p.get('confirm')!='AUTHORIZE':raise ValueError('Explicit compensation authorization required')
  management=D(str(p.get('management',0)));performance=D(str(p.get('performance',0)));salary=D(str(p.get('monthly_salary',0)))
  if not management.is_finite() or not performance.is_finite() or not salary.is_finite() or not 0<=management<=5 or not 0<=performance<=50 or not 0<=salary<=D('10000000'):raise ValueError('Invalid compensation policy: management 0–5%, performance 0–50%, monthly salary 0–£10m')
  fund.update(management=float(management),performance=float(performance),monthly_salary=amt(salary),compensation_authorized=True,compensation_authorized_at=self.state['time'])
  self.audit('compensation_authorization',{'fund':fund['id'],'management':str(management),'performance':str(performance),'monthly_salary':amt(salary)})
  self.message('Financial Control','Compensation policy authorised',f"{fund['name']}: {management}% annual management, {performance}% above high-water NAV, £{salary:,.2f} monthly salary. Payables and actual settlements appear in Financial Statements.")
  return {'authorized':True}

 def available_cash(self,account='personal'):
  return max(D(0),self.cash(account)-self.restricted_cash(account))
 def restricted_cash(self,account='personal'):
  reserve=D(0)
  for pos in self.state['positions'].values():
   if pos['account']!=account or D(pos['qty'])>=0:continue
   ins=self.instrument(pos['symbol']);liability=abs(D(pos['qty'])*D(ins['price'])*D(ins.get('multiplier',1)))*self.fx_rate(ins.get('currency','GBP'))
   reserve+=self.put_collateral(account,pos['symbol'],D(pos['qty']),D(pos['cost']),liability/abs(D(pos['qty'])))
  if self.state.get('microstructure_enabled'):
   for order in self.state['orders']:
    if order['account']==account and order['symbol'] in self.state.get('market_symbols',[]) and order['status'] in ('OPEN','PARTIAL') and order['type']=='limit' and order['side']=='buy' and not order.get('margin') and not order.get('reduce_only') and order.get('maker_quote'):
     ins=self.instrument(order['symbol']);reserve+=D(order['remaining'])*D(order['limit'])*self.fx_rate(ins['currency'])
  from .pretrade import order_cash
  reserve+=sum((order_cash(self,o) for o in self.state['orders'] if o['account']==account and o['status'] in ('OPEN','PARTIAL','PAUSED') and not o.get('maker_quote')),D(0))
  reserve+=sum((D(p['amount']) for p in self.state.get('pledges',[]) if p['owner']==account and p['status']=='ACTIVE'),D(0))
  return reserve.quantize(D('.01'))

 def statement_journal(self,account):
  """Incrementally project the append-only journal; never store derived financial data."""
  world=self.state['id'];accounts=tuple(sorted(set(self.controlled_accounts())|{account}))
  version=self.db.execute('pragma data_version').fetchone()[0]
  cache=getattr(self,'_statement_cache',None)
  # Transactional requests may subsequently roll back: use a private projection.
  transactional=self.db.in_transaction
  tail=self.db.execute('select rowid,id from journal not indexed where world=? order by rowid desc limit 1',(world,)).fetchone()
  if cache and (not tail or cache['last']>tail[0] or (cache['last']==tail[0] and cache.get('last_id')!=tail[1])):cache=None
  if transactional or not cache or cache['world']!=world or cache['accounts']!=accounts or cache['version']!=version or cache.get('connection') is not self.db:
   cache=dict(world=world,accounts=accounts,version=version,connection=self.db,last=0,items={a:[[],D(0),{},{}] for a in accounts})
  for rowid,id,time,desc,encoded in self.db.execute('select rowid,id,time,description,lines from journal not indexed where world=? and rowid>? order by rowid',(world,cache['last'])):
   lines=json.loads(encoded);owners=set()
   for key in lines:
    parts=key.split(':');owner=parts[-1] if parts[0]=='expense' else parts[1] if len(parts)>1 else None
    if owner in cache['items'] and belongs(key,owner):owners.add(owner)
   for owner in owners:
    rows,running,incomes,cashes=cache['items'][owner];cash=D(lines.get('cash:'+owner,'0'));running+=cash
    rows.append(dict(id=id,time=time,description=desc,lines=lines,cash_change=amt(cash),running_cash=amt(running)))
    if cash:cashes[desc]=cashes.get(desc,D(0))+cash
    gain=-D(lines.get('pnl:'+owner,'0'))
    if gain:incomes[desc]=incomes.get(desc,D(0))+gain
    cache['items'][owner][1]=running
   cache['last']=rowid;cache['last_id']=id
  if not transactional:self._statement_cache=cache
  return cache['items'][account]

 def statement(self,account='personal',offset=0,limit=100):
  if account not in self.accounts():raise ValueError('Unknown financial account')
  metrics=self.metrics(account);b=self.state['balances'];contribution=-self.balance('equity:'+account)
  income=-self.balance('pnl:'+account);expenses={k:D(v) for k,v in b.items() if k.startswith('expense:') and k.endswith(':'+account)}
  total_expense=sum(expenses.values(),D(0));inventory=sum((D(v) for k,v in b.items() if k.startswith('inventory:'+account+':')),D(0))
  investment_basis=sum((D(v) for k,v in b.items() if k.startswith(('investment:'+account+':','holding:'+account+':'))),D(0));receivable_face=sum((D(v) for k,v in b.items() if k.startswith(('escrow:'+account+':','receivable:'+account+':','claim:'+account+':','allowance:'+account+':','credit_asset:'+account+':'))),D(0))
  valuation=D(metrics['market'])-inventory+D(metrics['investment'])-investment_basis+D(metrics['receivables'])-receivable_face+D(metrics.get('fx_unrealised','0'))
  valuation+=D(metrics.get('treasury_market','0'))-self.treasury_basis(account)
  valuation+=D(metrics.get('owned_assets','0'))-sum((D(v) for k,v in b.items() if k.startswith('asset:'+account+':')),D(0))
  capital_reserves=-self.balance('capital_reserve:'+account)
  explained=contribution+income-total_expense+valuation+capital_reserves
  rows,running,income_sources,cash_sources=self.statement_journal(account)
  trades=self.realised_total(account)
  return dict(account=account,metrics=metrics,capital=amt(contribution),**({'capital_reserves':amt(capital_reserves)} if capital_reserves else {}),income=amt(income),trading_realised=amt(trades),expenses={k:amt(v) for k,v in expenses.items()},total_expenses=amt(total_expense),valuation=amt(valuation),explained_equity=amt(explained),reported_equity=metrics['equity'],difference=amt(D(metrics['equity'])-explained),balanced=explained==D(metrics['equity']),income_sources={k:amt(v) for k,v in income_sources.items()},cash_sources={k:amt(v) for k,v in cash_sources.items()},total_entries=len(rows),entries=list(reversed(rows))[max(0,int(offset)):max(0,int(offset))+min(500,max(1,int(limit)))])
