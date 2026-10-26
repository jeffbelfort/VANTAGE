import unittest,tempfile,copy,json
from pathlib import Path
from decimal import Decimal as D
from vantage.engine import Engine
class PlayerBankTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'runtime');self.e=Engine(Path(self.tmp.name)/'test.sqlite');self.e.execute('create',{'_legacy_fixture':True,'career':'Professional Trader'});self.parent=self.e.execute('entity_create',{'name':'Holdings','capital':300000})['id'];self.bank=self.e.execute('entity_create',{'name':'Bank','kind':'bank','parent':self.parent,'capital':10000})['id'];self.e.execute('bank_licence',{'entity':self.bank})
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def licensed(self):
  self.e.execute('related',{'source':self.parent,'destination':self.bank,'kind':'equity','amount':100000});self.assertEqual(self.e.execute('bank_licence',{'entity':self.bank})['status'],'AUTHORISED');return self.e.player_bank(self.bank)
 def test_borrowed_cash_is_not_licensing_capital(self):
  self.e.execute('related',{'source':self.parent,'destination':self.bank,'kind':'loan','amount':100000});self.assertEqual(self.e.execute('bank_licence',{'entity':self.bank})['status'],'UNLICENSED');self.assertEqual(self.e.player_bank(self.bank)['equity'],'10000.00');self.e.reconcile()
 def test_unlicensed_or_self_deposits_rejected(self):
  with self.assertRaises(ValueError):self.e.execute('bank_customer_transfer',{'account':'personal','bank':self.bank,'amount':100,'product':'savings'})
  self.licensed()
  with self.assertRaises(ValueError):self.e.execute('savings',{'account':self.bank,'bank':self.bank,'amount':100})
  self.e.reconcile()
 def test_customer_deposit_identity_and_retry(self):
  self.licensed();before=self.e.metrics(self.bank)['equity'];cash=self.e.cash();p={'account':'personal','bank':self.bank,'amount':1000,'product':'current'};self.e.execute('bank_customer_transfer',p,'deposit-key');self.e.execute('bank_customer_transfer',p,'deposit-key');self.assertEqual(self.e.cash(),cash-1000);self.assertEqual(self.e.metrics(self.bank)['equity'],before);self.assertEqual(self.e.player_bank(self.bank)['opened'],1);self.e.execute('bank_customer_transfer',dict(p,direction='withdraw'));self.assertEqual(self.e.cash(),cash);self.assertEqual(self.e.player_bank(self.bank)['closed'],1);self.e.reconcile()
 def test_npc_wealth_and_existing_fund_subscription_stay_consistent(self):
  b=self.licensed();n=self.e.state['npcs'][0];before=D(n['wealth']);alias='npc_'+n['id']
  with self.e.db:self.e.bank_customer_cash(b,alias,1000)
  self.assertEqual(D(n['wealth']),before-1000);fund=self.e.execute('fund',{'amount':1000});self.e.execute('subscribe',{'fund':fund['id'],'investor':n['id'],'amount':1000});self.assertEqual(D(n['wealth']),before-2000);self.e.refresh_player_banks();self.e.reconcile()
 def test_accrual_is_once_per_player_bank_tick(self):
  b=self.licensed();self.e.execute('bank_policy',{'entity':self.bank,'deposit_rate':5});self.e.execute('bank_customer_transfer',{'account':'personal','bank':self.bank,'amount':10000});loan=self.e.execute('loan',{'account':'personal','bank':self.bank,'amount':1000})['loan'];self.e.state['tick']+=1
  with self.e.db:self.e.savings_accrual();self.e.service_loans()
  amounts=(b['deposits'],b['loans'],b['cash'],b['interest_income'],b['interest_expense'],loan['balance'])
  with self.e.db:self.e.savings_accrual();self.e.service_loans()
  self.assertEqual(amounts,(b['deposits'],b['loans'],b['cash'],b['interest_income'],b['interest_expense'],loan['balance']));self.e.refresh_player_banks();self.e.reconcile();self.assertTrue(self.e.statement(self.bank)['balanced'])
 def test_loan_limits_and_rates(self):
  self.licensed();self.e.execute('bank_policy',{'entity':self.bank,'lending_rate':12,'max_loan':2000});offer=self.e.credit_offer({'account':'personal','bank':self.bank,'amount':1000});self.assertTrue(offer['approved']);self.assertEqual(offer['rate'],12);self.assertFalse(self.e.credit_offer({'account':'personal','bank':self.bank,'amount':3000})['approved']);self.assertFalse(self.e.credit_offer({'account':self.bank,'bank':self.bank,'amount':100})['approved'])
 def test_actual_clock_autonomy_and_replay(self):
  b=self.licensed();self.e.execute('bank_policy',{'entity':self.bank,'deposit_rate':5});self.e.execute('advance',{'hours':24});self.assertTrue(b['customers']);self.assertGreater(D(b['deposits']),0);self.assertTrue(all(self.e.bank_customer_plan(account,b)['loan_need']==0 for account in b['customers']));self.assertFalse(any(l['bank']==self.bank for l in self.e.state['loans']));before=copy.deepcopy(self.e.state['balances'])
  with self.e.db:self.e.player_bank_tick()
  self.assertEqual(self.e.state['balances'],before);self.e.refresh_player_banks();self.e.reconcile()
 def test_intervention_and_recapitalisation(self):
  b=self.licensed();self.e.execute('bank_customer_transfer',{'account':'personal','bank':self.bank,'amount':10000});spent=self.e.cash(self.bank)
  with self.e.db:self.e.post('Test actual bank loss',{'cash:'+self.bank:-spent,'expense:loss:'+self.bank:spent,'cash:economy_suppliers':spent,'pnl:economy_suppliers':-spent});self.e.state['tick']+=1;self.e.player_bank_tick()
  self.assertEqual(b['licence'],'INTERVENTION');self.assertEqual(b['deposits'],'10000.00');self.assertFalse(self.e.credit_offer({'account':'personal','bank':self.bank,'amount':100})['approved']);self.e.execute('related',{'source':self.parent,'destination':self.bank,'kind':'equity','amount':150000});self.assertEqual(self.e.execute('bank_licence',{'entity':self.bank})['status'],'AUTHORISED');self.e.reconcile()
 def test_rates_and_rules_cannot_be_invalid(self):
  self.licensed()
  for p in [{'deposit_rate':-1},{'lending_rate':'NaN'},{'reserve_ratio':.01},{'max_loan':0}]:
   with self.assertRaises(ValueError):self.e.execute('bank_policy',dict(entity=self.bank,**p))
  with self.assertRaises(ValueError):self.e.execute('bank_rules',{'minimum_capital':0})
 def test_competition_causes_real_withdrawals(self):
  b=self.licensed();candidates=['npc_'+n['id'] for n in self.e.state['npcs']]+[e['id'] for e in self.e.state['entities'].values() if e['kind']=='issuer' and e['status']=='ACTIVE'];candidates=sorted(candidates,key=lambda account:__import__('hashlib').sha256((b['id']+'|'+account).encode()).hexdigest());account=candidates[1%len(candidates)]
  with self.e.db:self.e.bank_customer_cash(b,account,1000)
  self.e.execute('bank_policy',{'entity':self.bank,'deposit_rate':0});cash=self.e.cash(account);self.e.state['tick']=24
  with self.e.db:self.e.player_bank_tick()
  remaining=self.e.balance('savings:'+account+':'+self.bank);withdrawn=D(1000)-remaining;self.assertGreater(withdrawn,0);self.assertLessEqual(withdrawn,1000);self.assertEqual(self.e.cash(account),cash+withdrawn);self.e.refresh_player_banks();self.e.reconcile()
 def test_api_exposes_bank_state_and_policy(self):
  from vantage.bridge import Bridge
  from types import SimpleNamespace
  self.licensed();reply=json.loads(Bridge.process(SimpleNamespace(engine=self.e),None,json.dumps({'path':'/api/bank_policy','method':'POST','body':{'entity':self.bank,'deposit_rate':3.5}})))
  self.assertTrue(reply['ok']);self.assertEqual(reply['data']['state']['world']['player_banks'][self.bank]['deposit_rate'],3.5);self.e.reconcile()
 def test_reload_and_ownership(self):
  self.licensed();self.e.execute('bank_customer_transfer',{'account':'personal','bank':self.bank,'product':'current','amount':1000});state=copy.deepcopy(self.e.state);path=self.e.path;self.e.close();self.e=Engine(path);self.assertEqual(self.e.state,state);self.assertEqual(self.e.state['entities'][self.bank]['parent'],self.parent);self.e.reconcile()
 # Identity-aware banking does not force surplus depositors to borrow. A separate
 # real liquidity-need fixture verifies autonomous lending without a prior deposit.
 def test_new_borrower_without_deposit(self):
  b=self.licensed();candidates=['npc_'+n['id'] for n in self.e.state['npcs']]+[e['id'] for e in self.e.state['entities'].values() if e['kind']=='issuer' and e['status']=='ACTIVE'];candidates.sort(key=lambda account:__import__('hashlib').sha256((b['id']+'|'+account).encode()).hexdigest());account=candidates[1%len(candidates)];profile=self.e.customer_profile(account);profile['liquidity_reserve']=str(self.e.available_cash(account)+200);profile['rate_tolerance']=.5;self.e.execute('bank_policy',{'entity':self.bank,'deposit_rate':0});self.e.state['tick']=24;bank_cash=self.e.cash(self.bank);borrower_cash=self.e.cash(account);supplier_cash=self.e.cash('economy_suppliers')
  with self.e.db:self.e.player_bank_tick()
  loans=[loan for loan in self.e.state['loans'] if loan['bank']==self.bank and loan['account']==account];self.assertEqual(len(loans),1);principal=D(loans[0]['principal']);self.assertEqual(self.e.cash(self.bank),bank_cash-principal);self.assertEqual(self.e.cash(account),borrower_cash);self.assertEqual(self.e.cash('economy_suppliers'),supplier_cash+principal);self.assertEqual(self.e.balance('savings:'+account+':'+self.bank),0);self.assertEqual(b['customers'][account]['status'],'BORROWER');self.e.refresh_player_banks();self.e.reconcile()

if __name__=='__main__':unittest.main()

