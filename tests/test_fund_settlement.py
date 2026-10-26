import copy,tempfile,unittest,json,sqlite3
from pathlib import Path
from decimal import Decimal as D
from vantage.engine import Engine

class FundSettlementTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'world.sqlite';self.e=Engine(self.path);self.e.execute('create',{'_static_market':True,'name':'Settlement','career':'Professional Trader'});self.f=self.e.execute('fund',{'amount':1000});self.id=self.f['id'];self.f['lock_until']=0
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def request(self,investor='personal',units=1000,key=None):return self.e.execute('redeem',{'fund':self.id,'investor':investor,'units':units,'queue':True},key)
 def test_seed_redemption_to_personal_portfolio(self):
  self.assertEqual(self.e.metrics()['equity'],'500000.00');r=self.request(key='once');self.assertEqual(r['status'],'SETTLED');self.assertEqual(self.e.cash(),D('500000'));self.assertEqual(self.e.metrics()['equity'],'500000.00');self.assertEqual(self.e.metrics(self.id)['equity'],'0.00');self.assertEqual(self.request(key='once'),r);self.e.reconcile()
 def test_illiquid_request_remains_liability(self):
  self.e.execute('subscribe',{'fund':self.id,'investor':'lp0','amount':10000});self.e.execute('savings',{'account':self.id,'amount':11000,'direction':'deposit'});r=self.request('lp0',10000);self.assertEqual(r['remaining'],'10000.00');self.assertEqual(self.e.state['npcs'][0]['wealth'],'1990000.00');self.assertEqual(self.e.metrics(self.id)['debt'],'10000.00');self.assertEqual(self.e.metrics(self.id)['equity'],'1000.00')
  self.e.execute('savings',{'account':self.id,'amount':2500,'direction':'withdraw'});self.e.execute('redemption_settle',{'fund':self.id});r=self.e.state['redemptions'][0];self.assertEqual(r['status'],'PARTIAL');self.assertEqual(r['remaining'],'7500.00');self.assertEqual(self.e.state['npcs'][0]['wealth'],'1992500.00');self.e.reconcile()
  self.e.execute('savings',{'account':self.id,'amount':7500,'direction':'withdraw'});self.e.execute('redemption_settle',{'fund':self.id});self.assertEqual(r['status'],'SETTLED');self.assertEqual(self.e.state['npcs'][0]['wealth'],'2000000.00');before=copy.deepcopy(self.e.state);self.e.execute('redemption_settle',{'fund':self.id});self.assertEqual(self.e.state,before);self.e.reconcile()
 def test_pending_personal_value_survives_reload(self):
  self.e.execute('savings',{'account':self.id,'amount':1000,'direction':'deposit'});r=self.request();self.assertEqual(r['remaining'],'1000.00');self.assertEqual(self.e.metrics()['equity'],'500000.00');self.assertEqual(self.e.metrics()['receivables'],'1000.00');before=self.e.snapshot();self.e.close();self.e=Engine(self.path);self.assertEqual(before,self.e.snapshot());self.assertEqual(self.e.statement()['difference'],'0.00');self.e.reconcile()
 def test_gate_and_suspend(self):
  self.e.execute('fund_policy',{'fund':self.id,'gate_daily_pct':25});r=self.request();self.assertEqual(r['paid'],'250.00');self.assertEqual(r['remaining'],'750.00');self.e.execute('fund_policy',{'fund':self.id,'suspended':True});self.e.execute('advance',{'hours':24});self.assertEqual(self.e.state['redemptions'][0]['remaining'],'750.00');self.e.execute('fund_policy',{'fund':self.id,'suspended':False});self.e.execute('redemption_settle',{'fund':self.id});self.assertGreater(D(self.e.state['redemptions'][0]['paid']),250);self.e.reconcile()
 def test_lockup_queues_until_eligible(self):
  self.f['lock_until']=2;r=self.request();self.assertEqual(r['paid'],'0.00');self.e.execute('advance',{'hours':2});self.assertEqual(self.e.state['redemptions'][0]['status'],'SETTLED');self.e.reconcile()
 def test_promised_returns_are_expense_and_obligation_not_money(self):
  self.e.execute('subscribe',{'fund':self.id,'investor':'lp0','amount':10000});cash=self.e.cash()+self.e.cash(self.id)+D(self.e.state['npcs'][0]['wealth']);self.e.execute('fund_policy',{'fund':self.id,'promised_apr':36.5,'suspended':True});self.e.execute('advance',{'hours':24});self.assertEqual(self.e.metrics(self.id)['debt'],'11.00');self.assertEqual(self.e.cash()+self.e.cash(self.id)+D(self.e.state['npcs'][0]['wealth']),cash);self.assertEqual(self.e.statement(self.id)['difference'],'0.00');self.assertEqual(self.e.statement()['difference'],'0.00');self.e.reconcile()
 def test_reported_nav_no_cash_and_understatement_evidence(self):
  before=self.e.cash(self.id);self.e.execute('report',{'fund':self.id,'reported':1000000});self.e.execute('advance',{'hours':72});self.assertEqual(self.e.cash(self.id),before);self.assertGreater(self.e.state['claims'][0]['evidence'],0);self.e.reconcile()
 def test_original_both_worlds_balance_preservation(self):
  evidence=Path(Path('reports/latest-fund-evidence.txt').read_text().strip())/'vantage.sqlite';source=sqlite3.connect(f'file:{evidence.resolve()}?mode=ro&immutable=1',uri=True);copy_path=Path(self.tmp.name)/'original.sqlite';target=sqlite3.connect(copy_path);source.backup(target);old={id:json.loads(raw) for id,raw in source.execute('select id,state from worlds')};original=list(source.execute('select * from journal'));source.close();target.close();e=Engine(copy_path)
  try:
   for id,w in old.items():
    e.execute('load',{'id':id});self.assertEqual(e.state['loans'],w['loans']);self.assertTrue(all(e.state['positions'][k]==v for k,v in w['positions'].items()))
    for k,v in w['balances'].items():self.assertEqual(e.state['balances'][k],v)
    for a in e.accounts():self.assertEqual(e.statement(a)['difference'],'0.00')
    e.reconcile()
   now={r[0]:r for r in e.db.execute('select * from journal')};self.assertTrue(all(now[r[0]]==r for r in original))
  finally:e.close()
 def test_contractual_coupon_survives_negative_fund_nav(self):
  self.e.execute('subscribe',{'fund':self.id,'investor':'lp0','amount':10000});self.e.execute('fund_policy',{'fund':self.id,'promised_apr':36.5,'suspended':True});self.e.execute('budget',{'fund':self.id,'amount':20000});self.e.state['npcs'][0]['horizon_days']=365;self.e.state['tick']=719;self.e.execute('advance',{'hours':1});self.assertLess(D(self.e.metrics(self.id)['equity']),0);before=sum((D(r['amount']) for r in self.e.state['redemptions'] if r.get('kind')=='CONTRACTUAL RETURN'),D(0));self.e.execute('advance',{'hours':24});after=sum((D(r['amount']) for r in self.e.state['redemptions'] if r.get('kind')=='CONTRACTUAL RETURN'),D(0));self.assertEqual(after-before,D('11.00'));self.e.reconcile()
