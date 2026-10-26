import copy,json,tempfile,unittest
from decimal import Decimal as D
from pathlib import Path
from vantage.engine import Engine
class MATests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ma.sqlite';self.e=Engine(self.path);self.e.execute('create',{'career':'Professional Trader','capital':2100000000,'_static_market':True,'_ai_corporate_economy':True});self.f=self.e.execute('fund',{'name':'Omaze','amount':2000000000,'fund_type':'private_equity'});self.e.execute('controls',{'entity':self.f['id'],'level':1});self.target='private_0'
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def cash(self):return sum((D(v) for k,v in self.e.state['balances'].items() if k.startswith('cash:') or k.startswith('npc:') and k.endswith(':cash')),D(0))
 def approach(self,percent=100,debt=0,target=None):
  id=target or self.target;v=D(self.e.ma_valuation(id)['equity_value']);return self.e.execute('ma_offer',{'buyer':self.f['id'],'entity':id,'percent':percent,'amount':v*D(str(percent))/100*D('1.1'),'debt':debt})
 def close(self,r):
  for action in ('ma_diligence','ma_approve','ma_close'):r=self.e.execute(action,{'id':r['id']})
  return r
 def test_generation_independent_and_balanced(self):
  self.assertEqual(len(self.e.state['private_businesses']),48);self.assertEqual(self.e.cash(self.f['id']),2000000000)
  for id in list(self.e.state['private_businesses'])+['corporate_owner_0']:
   self.assertEqual(self.e.statement(id)['difference'],'0.00')
  self.e.reconcile()
 def test_market_filter_and_earnings_valuation(self):
  rows=self.e.execute('ma_market',{'sector':'technology','max_value':10000000});self.assertTrue(rows);self.assertTrue(all(r['sector']=='technology' and D(r['equity_value'])<=10000000 for r in rows));row=rows[0];self.assertNotEqual(row['cash'],row['equity_value']);self.assertIn('forecast',row['basis']);self.assertEqual(self.e.execute('ma_profile',{'entity':row['id']})['statement']['difference'],'0.00')
 def test_rejection_and_negotiation(self):
  r=self.e.execute('ma_offer',{'buyer':self.f['id'],'entity':self.target,'amount':100});self.assertEqual(r['status'],'REJECTED')
  v=D(self.e.ma_valuation(self.target)['equity_value']);r=self.e.execute('ma_offer',{'buyer':self.f['id'],'entity':self.target,'amount':v});self.assertEqual(r['status'],'COUNTERED');self.e.execute('ma_negotiate',{'id':r['id']});self.assertEqual(r['status'],'ACCEPTED');self.assertTrue(r['revisions'])
 def test_full_acquisition_operation_and_exit_cash_conservation(self):
  total=self.cash();r=self.close(self.approach());e=self.e.state['entities'][self.target];self.assertEqual(e['owners'],{self.f['id']:'1000000.000000'});self.assertTrue(e['controlled']);self.assertEqual(total,self.cash())
  with self.assertRaises(ValueError):self.e.authority(self.target,'payment')
  self.e.execute('ma_manage',{'entity':self.target,'strategy':'efficiency','appoint_manager':True});self.e.authority(self.target,'payment')
  with self.e.db:self.e.post('Synthetic customer funds',{'cash:personal':-10000000,'expense:customer_budget:personal':10000000,'cash:economy_households':10000000,'pnl:economy_households':-10000000});self.e.persist()
  self.e.execute('advance',{'hours':72});b=self.e.state['private_businesses'][self.target];self.assertEqual(len(b['history']),3);self.assertGreater(D(b['history'][-1]['revenue']),0);self.assertEqual(self.e.statement(self.target)['difference'],'0.00');before=self.cash();q=self.e.execute('ma_exit',{'entity':self.target,'seller':self.f['id'],'percent':100});self.e.execute('ma_exit_accept',{'id':q['id']});self.assertNotIn(self.f['id'],e['owners']);self.assertFalse(e['controlled']);self.assertEqual(before,self.cash());self.e.reconcile();self.assertEqual(self.e.statement(self.f['id'])['difference'],'0.00')
 def test_minority_rights_no_operating_authority(self):
  self.close(self.approach(percent=20));self.assertFalse(self.e.state['entities'][self.target]['controlled']);self.assertGreater(D(self.e.metrics(self.f['id'])['investment']),0)
  with self.assertRaises(ValueError):self.e.execute('ma_manage',{'entity':self.target,'strategy':'growth'})
 def test_majority_preserves_minorities_and_case_identity(self):
  r=self.close(self.approach(percent=60));e=self.e.state['entities'][self.target];self.assertEqual(len(e['owners']),2);self.assertTrue(e['controlled']);self.assertEqual(sum(map(D,e['owners'].values())),D(e['units']));self.e.reconcile()
 def test_board_required_and_atomic_insufficient_cash(self):
  r=self.approach();self.e.execute('ma_diligence',{'id':r['id']});self.e.execute('controls',{'entity':self.f['id'],'level':0});self.e.execute('entity_policy',{'entity':self.f['id'],'payment_limit':1})
  with self.assertRaises(ValueError):self.e.execute('ma_approve',{'id':r['id']})
  self.e.execute('controls',{'entity':self.f['id'],'level':1});self.e.execute('ma_approve',{'id':r['id']})
  with self.e.db:
   amount=self.e.available_cash(self.f['id'])-1;self.e.post('Synthetic preclosing cash obligation',{'cash:'+self.f['id']:-amount,'expense:fixture:'+self.f['id']:amount,'cash:operating_suppliers':amount,'pnl:operating_suppliers':-amount});self.e.persist()
  before=copy.deepcopy(self.e.state)
  with self.assertRaises(ValueError):self.e.execute('ma_close',{'id':r['id']})
  self.assertEqual(before,self.e.state)
 def test_competing_bid(self):
  r=self.approach();self.e.execute('ma_diligence',{'id':r['id']});self.e.execute('ma_approve',{'id':r['id']});second=self.e.execute('fund',{'name':'Rival controlled fund','amount':10000000,'fund_type':'private_equity'});self.e.execute('ma_offer',{'entity':self.target,'buyer':second['id'],'amount':D(r['amount'])*D('1.2')})
  with self.assertRaisesRegex(ValueError,'competing'):self.e.execute('ma_close',{'id':r['id']})
 def test_ownership_changed_and_restricted_block_closing(self):
  r=self.approach();self.e.execute('ma_diligence',{'id':r['id']});self.e.execute('ma_approve',{'id':r['id']});self.e.state.setdefault('frozen_funds',[]).append(self.target)
  with self.assertRaises(ValueError):self.e.execute('ma_close',{'id':r['id']})
 def test_lbo_declined_no_vehicle_or_money_created(self):
  r=self.approach(debt=1000000);self.e.execute('ma_diligence',{'id':r['id']});self.e.execute('ma_approve',{'id':r['id']});before=copy.deepcopy(self.e.state)
  with self.assertRaisesRegex(ValueError,'LBO declined'):self.e.execute('ma_close',{'id':r['id']})
  self.assertEqual(before,self.e.state)
 def test_lbo_claim_survives_and_cash_is_finite(self):
  r=self.approach(debt=100000);before=self.cash();self.close(r);self.assertEqual(before,self.cash());facility=self.e.state['ma_facilities'][0];c=next(c for c in self.e.state['claims_book'] if c['id']==facility['claim']);self.assertEqual(D(c['balance']),100000);self.assertEqual(c['debtor'],r['vehicle']);self.assertEqual(self.e.state['entities'][self.target]['parent'],r['vehicle']);self.e.reconcile()
 def test_reload_no_duplicate_opening_or_settlement(self):
  r=self.close(self.approach());before=copy.deepcopy(self.e.state);self.e.close();self.e=Engine(self.path);self.e.execute('load',{'id':before['id']});self.assertEqual(before['balances'],self.e.state['balances']);self.assertEqual(len(self.e.state['private_businesses']),48)
  with self.assertRaises(ValueError):self.e.execute('ma_close',{'id':r['id']})
  self.e.reconcile()
 def test_minorities_receive_proportionate_actual_dividends(self):
  self.close(self.approach(percent=60));self.e.execute('ma_manage',{'entity':self.target,'appoint_manager':True});self.e.execute('advance',{'hours':72});owners=self.e.state['entities'][self.target]['owners'];before={id:self.e.cash(id) for id in owners};self.e.execute('ma_dividend',{'entity':self.target,'amount':100})
  for id,q in owners.items():self.assertEqual(self.e.cash(id)-before[id],D(100)*D(q)/1000000)
  self.e.reconcile()
 def test_funded_expansion_and_operating_obligations(self):
  self.close(self.approach());self.e.execute('ma_manage',{'entity':self.target,'appoint_manager':True});cash=self.e.cash(self.target);assets=self.e.productive_value(self.target);self.e.execute('ma_expand',{'entity':self.target,'amount':1000});self.assertEqual(self.e.cash(self.target),cash-1000);self.assertEqual(self.e.productive_value(self.target),assets+1000);self.e.reconcile()
 def test_ai_acquisition_uses_existing_finite_cash(self):
  before=self.cash();owners={id:copy.deepcopy(self.e.state['entities'][id]['owners']) for id in self.e.state['private_businesses']}
  with self.e.db:self.e.state['tick']=168;self.e.ma_ai_tick();self.e.persist()
  self.assertTrue(any(r['ai'] and r['status']=='CLOSED' for r in self.e.state['ma_offers']));self.assertTrue(any(owners[id]!=self.e.state['entities'][id]['owners'] for id in owners));self.assertEqual(before,self.cash());self.e.reconcile()
 def test_snapshot_cache_matches_uncached_values_and_does_not_leak(self):
  self.close(self.approach());expected={id:self.e.metrics(id) for id in self.e.accounts()};snapshot=self.e.snapshot();self.assertEqual(expected,snapshot['world']['metrics']);self.assertIsNone(self.e._snapshot_metrics_cache);self.assertIsNone(self.e._projection_ledger);self.e.execute('ma_diligence',{'id':self.approach(target='private_4')['id']});self.assertNotEqual(expected[self.f['id']]['cash'],self.e.metrics(self.f['id'])['cash'])
 def test_lbo_service_and_covenant_breach_preserve_claim(self):
  r=self.close(self.approach(debt=100000));facility=self.e.state['ma_facilities'][0];claim=next(c for c in self.e.state['claims_book'] if c['id']==facility['claim'])
  with self.e.db:
   self.e.state['tick']=720;self.e.ma_facility_tick();self.e.persist()
  self.assertEqual(facility['status'],'COVENANT_BREACH');self.assertEqual(D(claim['balance']),100000)
  with self.e.db:
   self.e.post('Synthetic equity top-up for debt service',{'cash:'+self.f['id']:-10000,'holding:'+self.f['id']+':'+r['vehicle']:10000,'cash:'+r['vehicle']:10000,'equity:'+r['vehicle']:-10000});self.e.state['tick']=1440;self.e.ma_facility_tick();self.e.persist()
  self.assertLess(D(claim['balance']),100000);self.assertEqual(facility['status'],'ACTIVE');self.e.reconcile()
 def test_debt_and_recovery_remain_attached_to_company_after_sale(self):
  with self.e.db:
   c=self.e.create_claim('corporate_lender',self.target,D(1000),'RECOVERY','synthetic-adjudicated-order');self.e.post('Synthetic recovery order',{'claim:corporate_lender:'+c['id']:1000,'pnl:corporate_lender':-1000,'expense:restitution:'+self.target:1000,'debt:'+self.target+':claim_'+c['id']:-1000});self.e.persist()
  self.close(self.approach());self.assertEqual(c['debtor'],self.target);self.assertEqual(c['balance'],'1000.00');self.assertEqual(c['reference'],'synthetic-adjudicated-order');self.e.reconcile()
 def test_due_diligence_cannot_exceed_payment_authority(self):
  r=self.approach();self.e.execute('entity_policy',{'entity':self.f['id'],'payment_limit':1});before=copy.deepcopy(self.e.state)
  with self.assertRaisesRegex(ValueError,'authority'):self.e.execute('ma_diligence',{'id':r['id']})
  self.assertEqual(before,self.e.state)
 def test_changed_board_limit_requires_fresh_approval(self):
  self.e.execute('controls',{'entity':self.f['id'],'level':0});self.e.execute('entity_policy',{'entity':self.f['id'],'payment_limit':10000000});r=self.approach();self.e.execute('ma_diligence',{'id':r['id']});self.e.execute('ma_approve',{'id':r['id']});self.e.execute('entity_policy',{'entity':self.f['id'],'payment_limit':1})
  with self.assertRaisesRegex(ValueError,'fresh board'):self.e.execute('ma_close',{'id':r['id']})
 def test_group_eliminates_fair_value_portfolio_holding(self):
  r=self.close(self.approach(debt=100000));group=self.e.execute('consolidated_statement',{'entity':r['vehicle']});self.assertEqual(D(group['eliminations']['equity_investments']),D(self.e.ma_valuation(self.target)['equity_value']));self.assertEqual(D(group['equity']),D(self.e.metrics(self.target)['equity'])-100000)
 def test_administration_pays_aggregate_workforce_and_materials(self):
  self.close(self.approach());target=self.target
  with self.e.db:
   self.e.post('Synthetic unpaid operating obligations',{'expense:workforce:'+target:1000,'debt:'+target+':workforce':-1000,'expense:materials:'+target:500,'debt:'+target+':materials':-500});self.e.persist()
  before=self.e.cash('economy_households');self.e.execute('administration',{'entity':target});self.e.execute('advance',{'hours':1});self.assertEqual(self.e.balance('debt:'+target+':workforce'),0);self.assertEqual(self.e.balance('debt:'+target+':materials'),0);self.assertGreaterEqual(self.e.cash('economy_households'),before+1000);self.e.reconcile()
 def test_unfunded_competing_offer_cannot_block_backed_close(self):
  r=self.approach();self.e.execute('ma_diligence',{'id':r['id']});self.e.execute('ma_approve',{'id':r['id']});tiny=self.e.execute('fund',{'name':'Unfunded approach','amount':1000,'fund_type':'private_equity'});self.e.execute('ma_offer',{'entity':self.target,'buyer':tiny['id'],'amount':D(r['amount'])*2});self.e.execute('ma_close',{'id':r['id']});self.assertEqual(self.e.state['entities'][self.target]['parent'],self.f['id'])
