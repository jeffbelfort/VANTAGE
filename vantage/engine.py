"""Transactional local financial sandbox. All authoritative money uses Decimal."""
from __future__ import annotations
import copy, json, math, random, sqlite3, threading, uuid
from . import filelock as fcntl
from .paths import runtime_directory
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_DOWN
from pathlib import Path
from .execution import depth,execute_depth
from .marketdata import ReferenceStore
from .integrity import IntegrityMixin
from .lending import LendingMixin
from .player_banking import PlayerBankingMixin
from .empire import EmpireMixin
from .funds import FundSystemMixin
from .living import LivingMarketMixin
from .empire_finance import EmpireFinanceMixin
from .ma import MAMixin
from .entity_capabilities import EntityCapabilitiesMixin
from .world_market import WorldMarketMixin
from .mega import MegaMarketMixin
from .corporate_lifecycle import CorporateLifecycleMixin
from .corporate import CorporateMixin
from .governance import GovernanceMixin
from .resolution import ResolutionMixin
from .economy import EconomyMixin
from .business import BusinessMixin
from .employees import EmployeeMixin
from .research import ResearchMixin
from .wealth import WealthMixin
from .offices import OfficeMixin
from .securities import SecuritiesMixin,EquityReferences,catalogue
from .federal_reserve import FederalReserveMixin

D = Decimal
CENT = D('.01')
CAREERS = {'Retail Investor': '5000', 'Professional Trader': '500000', 'Investment Firm Founder': '10000000', 'Hedge Fund Manager': '1000000000', 'Investment Bank Trader': '20000000000', 'Global Financial Institution': '250000000000', 'Custom Career': '25000'}
INSTRUMENTS = [
 ('ALTN','Alton Technologies','Technology',142, .32),('MRDN','Meridian Bank','Financials',48,.24),
 ('HLX','Helix Therapeutics','Healthcare',86,.30),('NOVA','Nova Energy','Energy',64,.28),
 ('ATLS','Atlas Industrials','Industrials',112,.23),('VERD','Verdant Consumer','Consumer',37,.20),
 ('AUR','Aurum Gold Trust','Commodities',198,.18),('V100','Vantage 100 Index Fund','Index',250,.17),
 ('GLT','Sterling Sovereign Bond Fund','Fixed income',102,.07),('ORBT','Orbit Communications','Technology',29,.42),
 ('CRST','Crest Property','Property',76,.25),('WAVE','Wave Utilities','Utilities',54,.15)]

def money(x):
    try: v = D(str(x))
    except Exception: raise ValueError('Enter a valid number')
    if not v.is_finite() or abs(v)>D('1e18'): raise ValueError('Number outside supported range')
    return v.quantize(CENT, rounding=ROUND_HALF_EVEN)

def s(x): return format(money(x),'f')
def uid(): return uuid.uuid4().hex[:12]
def gbp_for_message(v):return f'£{D(v):,.2f}'
def positive(x):
    v=money(x)
    if v<=0: raise ValueError('Amount must be positive')
    return v

def option_value(spot, strike, years, vol, rate, kind):
    """European Black–Scholes theoretical premium and Greeks, per share."""
    if years<=0:
        return {'price': max(0,spot-strike) if kind=='call' else max(0,strike-spot), 'delta':float(spot>strike) if kind=='call' else -float(spot<strike),'gamma':0,'theta':0,'vega':0,'rho':0}
    n=lambda x:(1+math.erf(x/math.sqrt(2)))/2
    pdf=lambda x:math.exp(-x*x/2)/math.sqrt(2*math.pi)
    t=math.sqrt(years); d1=(math.log(spot/strike)+(rate+vol*vol/2)*years)/(vol*t);d2=d1-vol*t
    disc=math.exp(-rate*years)
    call=spot*n(d1)-strike*disc*n(d2)
    price=call if kind=='call' else call-spot+strike*disc
    theta=-spot*pdf(d1)*vol/(2*t)+(-rate*strike*disc*n(d2) if kind=='call' else rate*strike*disc*n(-d2))
    return dict(price=max(.001,price), delta=n(d1)-(kind=='put'), gamma=pdf(d1)/(spot*vol*t),theta=theta/365,vega=spot*pdf(d1)*t/100,rho=(strike*years*disc*n(d2) if kind=='call' else -strike*years*disc*n(-d2))/100)

class OrderRejected(ValueError):pass

from .living_world import LivingWorldMixin
from .world_phase2 import WorldPhaseTwoMixin
from .institutional import InstitutionalMixin
from .options_clearing import PutClearingMixin

class Engine(FederalReserveMixin,MAMixin,EmpireFinanceMixin,EntityCapabilitiesMixin,WorldMarketMixin,MegaMarketMixin,CorporateLifecycleMixin,CorporateMixin,PutClearingMixin,InstitutionalMixin,WorldPhaseTwoMixin,LivingWorldMixin,EmpireMixin,PlayerBankingMixin,OfficeMixin,WealthMixin,ResearchMixin,EmployeeMixin,IntegrityMixin,LendingMixin,SecuritiesMixin,FundSystemMixin,LivingMarketMixin,GovernanceMixin,ResolutionMixin,EconomyMixin,BusinessMixin):
    def __init__(self, path):
        if Path(path).resolve().is_relative_to(Path(__file__).resolve().parent.parent/'evidence'):raise ValueError('Evidence databases are read-only. Copy the snapshot to an isolated test directory before opening it.')
        runtime=runtime_directory()
        candidate=Path(path).resolve()
        if runtime.resolve()!=runtime or not candidate.is_relative_to(runtime):
            raise ValueError('Development build refuses database outside its own runtime directory')
        if (Path(path).parent/'.vantage-import-pending.json').exists():raise ValueError('An interrupted save import needs recovery. Run scripts/import_stable_save.py --rollback with the recorded import directory before launching.')
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.references=ReferenceStore(self.path.parent/'reference-cache.json');self.equity_references=EquityReferences(self.path.parent/'equity-reference-cache.json')
        self._advancing=False;self.lock=threading.RLock();self.instance_lock=open(str(self.path)+'.lock','a+')
        try:fcntl.flock(self.instance_lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.instance_lock.close();raise ValueError('This save database is already open in another VANTAGE process')
        try:
            self.db=sqlite3.connect(self.path,check_same_thread=False,timeout=10)
            version=self.db.execute('pragma user_version').fetchone()[0]
            if version>1:raise ValueError('Database was created by a newer VANTAGE version')
            if version<1:self.db.execute('pragma user_version=1')
            self.db.execute('pragma journal_mode=WAL');self.db.execute('pragma synchronous=FULL');self.db.execute('pragma foreign_keys=ON')
            # Bound WAL growth, but checkpoint batches off the UI worker. FULL durability is retained.
            self.db.execute('pragma wal_autocheckpoint=65536')
            from .schema import ensure_schema
            ensure_schema(self.db)
            self.db.commit();self.state=None
            active=self.db.execute("select value from metadata where key='active'").fetchone()
            if active:
                row=self.db.execute('select state from worlds where id=?',active).fetchone()
                if row:
                    self.state=json.loads(row[0]);self.reconcile()
                    if not self.state.get('business_version') or not self.state.get('economy_version') or not self.state.get('resolution_version') or self.state.get('governance_version',0)<1 or self.state.get('market_system_version',0)<1 or self.state.get('fund_system_version',0)<1 or self.state.get('financial_version',0)<2 or (self.state.get('catalogue_version',0)<1 and not self.state.get('_legacy_fixture')):
                        self.backup(self.path.parent/'pre-upgrade-backups',automatic=True)
                        with self.db:
                            self.migrate_financial_state()
                            if not self.state.get('_legacy_fixture'):self.install_real_securities(legacy=True)
                            self.migrate_fund_system();self.install_living_market();self.install_governance();self.install_resolution();self.install_economy();self.install_business();self.install_employees();self.install_research();self.install_wealth();self.install_offices();self.install_living_world()
                            self.state['paused']=True;self.persist()
            if self.state and not self.state.get('employee_version'):
                self.backup(self.path.parent/'pre-employee-backups',automatic=True)
                with self.db:
                    self.install_employees();self.reconcile();self.persist()
            if self.state and not self.state.get('stock_research_version'):
                self.backup(self.path.parent/'pre-research-backups',automatic=True)
                with self.db:self.install_research();self.reconcile();self.persist()
            if self.state and not self.state.get('wealth_version'):
                self.backup(self.path.parent/'pre-wealth-backups',automatic=True)
                with self.db:self.install_wealth();self.reconcile();self.persist()
            if self.state and not self.state.get('office_version'):
                self.backup(self.path.parent/'pre-office-backups',automatic=True)
                with self.db:self.install_offices();self.reconcile();self.persist()
            if self.state and (not self.state.get('living_world_version') or not self.state.get('living_world_phase2_version')):
                with self.db:self.install_living_world();self.reconcile();self.persist()
            if self.state and self.state.get('microstructure_enabled') and self.state.get('liquidity_quote_version',0)<1 and not (self.state.get('market_generation_version')==2 and self.state.get('institutional_world_initialized')):
                with self.db:
                    self.repair_market_liquidity();self.reconcile();self.persist()
            if self.state and self.state.get('empire_a_version',0)<1:
                self.backup(self.path.parent/'pre-v070-phase-a-backups',automatic=True)
                with self.db:self.install_empire_a();self.reconcile();self.persist()
            if self.state and not self.state.get('public_ownership_version'):
                with self.db:self.install_public_ownership();self.public_control_refresh();self.persist()
        except Exception:
            if hasattr(self,'db'):self.db.close()
            self.instance_lock.close();raise

    def persist(self):
        w=self.state
        self.db.execute('insert or replace into worlds values(?,?,?,?)',(w['id'],w['name'],json.dumps(w,separators=(',',':'),ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        self.db.execute("insert or replace into metadata values('active',?)",(w['id'],))

    def post(self,description,lines):
        if getattr(self,'_snapshot_metrics_cache',None) is not None:self._snapshot_metrics_cache.clear();self._projection_ledger={}
        lines={k:s(v) for k,v in lines.items() if money(v)!=0}
        if sum((D(v) for v in lines.values()),D(0))!=0:raise ValueError('Unbalanced journal')
        w=self.state
        npc_aliases={'npc_'+n['id']:n for n in w.get('npcs',[])};touched=[]
        for key in list(lines):
            if key.startswith('cash:') and key[5:] in npc_aliases:
                npc=npc_aliases[key[5:]];target='npc:'+npc['id']+':cash';lines[target]=s(D(lines.get(target,'0'))+D(lines.pop(key)));touched.append(npc)
        indexed=getattr(self,'_account_ledger_source',None) is w['balances'] and getattr(self,'_account_ledger_count',-1)==len(w['balances'])
        for k,v in lines.items():
            if indexed and k not in w['balances']:
                for token in set(k.split(':')[1:]):self._account_ledger_index.setdefault(token,[]).append(k)
            w['balances'][k]=s(D(w['balances'].get(k,'0'))+D(v))
        if indexed:self._account_ledger_count=len(w['balances'])
        else:self._account_ledger_source=None
        for npc in touched:npc['wealth']=w['balances']['npc:'+npc['id']+':cash']
        self.db.execute('insert into journal values(?,?,?,?,?)',(uid(),w['id'],w['time'],description,json.dumps(lines)))
        self._ledger_generation=getattr(self,'_ledger_generation',0)+1

    def audit(self,action,detail):
        self.db.execute('insert into audit values(?,?,?,?,?)',(uid(),self.state['id'],self.state['time'],action,json.dumps(detail)))

    def news(self,title,body,category='WORLD'):
        self.state['news'].insert(0,dict(id=uid(),time=self.state['time'],title=title,body=body,category=category,source='VANTAGE internal scenario wire',quality='SYNTHETIC'))
        self.state['news']=self.state['news'][:200]

    def message(self,sender,subject,body):
        self.state['messages'].insert(0,dict(id=uid(),time=self.state['time'],sender=sender,subject=subject,body=body))
        self.state['messages']=self.state['messages'][:200]

    def create(self,p):
        career=p.get('career','Retail Investor')
        if career not in CAREERS:raise ValueError('Unknown career')
        capital=positive(p.get('capital',CAREERS[career]));name=str(p.get('name','New career')).strip()[:80]
        if not name:raise ValueError('Name is required')
        institutional=career in list(CAREERS)[2:6]
        rng=random.Random(int(p.get('seed',42)));now='2026-01-05T08:00:00+00:00' if p.get('_legacy_fixture') else '2026-10-23T08:00:00+00:00'
        w=dict(market_generation_version=1 if p.get('_legacy_fixture') or p.get('_static_market') or p.get('_market_generation_legacy') else 2,_legacy_fixture=bool(p.get('_legacy_fixture')),_static_market=bool(p.get('_static_market')),id=uid(),name=name,career=career,currency='GBP',seed=int(p.get('seed',42)),tick=0,time=now,paused=True,speed=1,
            financial_version=2,balances={},positions={},orders=[],fills=[],loans=[],funds=[],options={},news=[],messages=[],history=[],
            reputation=65,credit=700,investigations=[],claims=[],relationships={},macro=dict(rate=4.25,inflation=2.8,growth=1.7,stress=0),instruments={},
            banks=[dict(id='sterling',name='Sterling & Co.',cash='500000000000.00',loans='0.00',deposits='400000000000.00',equity='100000000000.00',spread=3.25),dict(id='north',name='Northbridge Bank',cash='200000000000.00',loans='0.00',deposits='160000000000.00',equity='40000000000.00',spread=2.75)],
            npcs=[dict(id=f'lp{i}',name=n,wealth=s(v),trust=70,units={},risk=r) for i,(n,v,r) in enumerate([('Eleanor Shaw',2000000,.3),('Oakridge Endowment',45000000,.2),('Marius Chen',7500000,.7),('Aster Pension Partners',180000000,.15)])])
        self.state=w
        common_history=[rng.gauss(0,1) for _ in range(100)]
        sector_history={sector:[rng.gauss(0,1) for _ in range(100)] for sector in sorted({i[2] for i in INSTRUMENTS})}
        for sym,n,sector,price,vol in INSTRUMENTS:
            hist=[];last=price
            for j in range(100):
                shock=.6*common_history[j]+.4*sector_history[sector][j]+math.sqrt(.48)*rng.gauss(0,1)
                close=last*math.exp(vol/math.sqrt(365*24)*shock)
                hist.append(dict(t=j-100,o=round(last,2),h=round(max(last,close)*1.006,2),l=round(min(last,close)*.994,2),c=round(close,2),v=rng.randint(5000,50000)))
                last=close
            w['instruments'][sym]=dict(symbol=sym,name=n,sector=sector,price=s(last),previous=s(last),vol=vol,exchange='VANTAGE SIM',currency='GBP',source='Seeded VANTAGE model',quality='SYNTHETIC',delay='Simulation time',status='OPEN',timestamp=now,liquidity=5000,history=hist,fundamentals=dict(revenue=s(price*1000000),profit=s(price*100000),debt=s(price*200000),shares=10000000))
        if not p.get('_legacy_fixture'):self.install_real_securities()
        self.post('Opening personal capital',{'cash:personal':s(5000 if institutional else capital),'equity:personal':s(-D(5000 if institutional else capital))})
        if institutional:
            w['funds'].append(dict(id='book',name=name+' • Trading book',units=s(capital),highwater='1.00',reported=s(capital),management=0,performance=0,compensation_authorized=False,investors={'sponsor':s(capital)},lock_until=0))
            self.post('Institutional sponsor capital',{'cash:book':capital,'equity:book':-capital})
        for bank in w['banks']:self.bank_sync(bank,'Opening bank balance sheet')
        self.migrate_fund_system();self.install_living_market();self.install_governance();self.install_resolution();self.install_economy();self.install_business();self.install_employees();self.install_research();self.install_wealth();self.install_offices();self.install_living_world()
        self.message('VANTAGE Operations','Your workstation is ready','Listed-company execution markets use archived reference baselines. Trading book assets are separate from personal wealth. Simulation time advances only when requested or resumed. Every financial action is journalled.')
        self.news('Opening bell: a new mandate','The market session opens with stable model credit conditions. Reference data is separate from this market.')
        if w.get('market_generation_version')==2 or p.get('_ai_corporate_economy'):self.ma_generate()
        if p.get('federal_reserve',not w.get('_static_market') and not w.get('_legacy_fixture')):self.install_fed()
        self.record_history();return {'id':w['id']}

    def balance(self,key):return D(self.state['balances'].get(key,'0'))
    def cash(self,acct='personal'):return self.balance('npc:'+acct[4:]+':cash' if acct.startswith('npc_') and any(n['id']==acct[4:] for n in self.state.get('npcs',[])) else 'cash:'+acct)
    def instrument(self,symbol):
        if symbol in self.state['instruments']:return self.state['instruments'][symbol]
        if symbol in self.state['options']:
            o=self.state['options'][symbol];base=self.state['instruments'][o['underlying']]
            days=max(0,(datetime.fromisoformat(o['expiry'])-datetime.fromisoformat(self.state['time'])).total_seconds()/86400)
            greeks=option_value(float(base['price']),float(o['strike']),days/365,base['vol'],self.state['macro']['rate']/100,o['kind'])
            return dict(symbol=symbol,name=f"{o['underlying']} {o['kind'].upper()} {o['strike']}",price=s(max(.01,greeks['price']) if days>0 else greeks['price']),previous=s(max(.01,greeks['price']) if days>0 else greeks['price']),multiplier=100,liquidity=100,status='OPEN' if days>0 else 'EXPIRED',greeks=greeks,quality='SIMULATED',currency=base.get('currency','GBP'),exchange='VANTAGE OTC',source='Black–Scholes theoretical',timestamp=self.state['time'])
        for instrument in self.state['instruments'].values():
            if instrument.get('security_id')==symbol:return instrument
        raise ValueError('Unknown instrument')

    def fx_rate(self,currency):
        if currency=='GBP':return D(1)
        return D(self.state.get('fx',{}).get(currency,{}).get('gbp_per_unit','0')) or (_ for _ in ()).throw(ValueError('No recorded FX rate for '+currency))

    def accounts(self):return list(dict.fromkeys(['personal']+(['npc_'+n['id'] for n in self.state.get('npcs',[])] if any(b.get('entity') for b in self.state.get('banks',[])) else [])+[f['id'] for f in self.state['funds']]+[a['account'] for a in self.state.get('participants',[])]+[e['id'] for e in self.state.get('entities',{}).values() if e['kind'] in ('company','holding','credit_fund','bank','issuer','central_bank','sovereign')]))
    def is_frozen(self,account):
        return self.state.get('entities',{}).get(account,{}).get('status') in ('ADMINISTRATION','DISSOLVED','MERGED') or account in self.state.get('frozen_funds',[]) or (self.state.get('frozen',False) and account!='personal' and not account.startswith('agent_'))

    def account(self,p):
        a=p.get('account','personal')
        if a not in self.accounts():raise ValueError('Unknown account')
        return a
    def metrics(self,acct='personal'):
        cache=getattr(self,'_snapshot_metrics_cache',None)
        if cache is None:return self._metrics_uncached(acct)
        if acct not in cache:cache[acct]=self._metrics_uncached(acct)
        return dict(cache[acct])

    def ledger_items(self,account):
        # Index account tokens, not balances: every value is read live. This avoids
        # repeated full-book scans without caching cash, reservations or valuation.
        balances=self.state['balances']
        if getattr(self,'_account_ledger_source',None) is not balances or getattr(self,'_account_ledger_count',-1)!=len(balances):
            index={}
            for key in balances:
                for token in set(key.split(':')[1:]):index.setdefault(token,[]).append(key)
            self._account_ledger_source=balances;self._account_ledger_count=len(balances);self._account_ledger_index=index
        return ((key,balances[key]) for key in self._account_ledger_index.get(account,()))

    def _metrics_uncached(self,acct='personal'):
        cash=self.cash(acct);market=D(0);gross=D(0);unreal=D(0);concentration=[];exposures=[]
        positions=[pos for pos in self.state['positions'].values() if pos['account']==acct]
        for pos in positions:
            ins=self.instrument(pos['symbol']);raw=D(ins['price'])*D(pos['qty'])*D(ins.get('multiplier',1))*self.fx_rate(ins.get('currency','GBP'));value=money(raw);exposures.append(float(abs(raw))*.25)
            market+=value;gross+=abs(value);unreal+=value-D(pos['cost']);concentration.append((pos['symbol'],float(abs(value))))
        debt=-sum((D(v) for k,v in self.ledger_items(acct) if k.startswith('debt:'+acct+':')),D(0))
        savings=sum((D(v) for k,v in self.ledger_items(acct) if k.startswith('savings:'+acct+':')),D(0))
        investment=D(0);investment_cost=D(0)
        fund_ids={f['id'] for f in self.state['funds']}
        for fund in self.state['funds']:
            owned=D(fund['investors'].get(acct,'0'));units=D(fund['units'])
            if owned>0 and units>0:investment+=money(max(D(0),D(self.metrics(fund['id'])['equity']))*owned/units)
            investment_cost+=self.balance('investment:'+acct+':'+fund['id'])
        for entity in self.state.get('entities',{}).values():
            if entity['id'] in fund_ids:continue
            owned=D(entity.get('owners',{}).get(acct,'0'));units=D(entity.get('units','0'))
            if owned and units:investment+=money(self.corporate_interest_value(entity['id'],self.metrics(entity['id']))*owned/units)
            investment_cost+=self.balance('holding:'+acct+':'+entity['id'])
        receivables=D(0)
        for key,face in self.ledger_items(acct):
            if not key.startswith('receivable:'+acct+':'):continue
            fundid=key.split(':',2)[2];fm=self.metrics(fundid);assets=max(D(0),D(fm['cash'])+D(fm['market'])+D(fm['savings'])+D(fm.get('treasury_market','0'))+D(fm.get('reserve_assets','0')));liabilities=D(fm['debt'])
            recovery=min(D(1),assets/liabilities) if liabilities>0 else D(1)
            receivables+=money(D(face)*recovery)
        for claim in self.state.get('claims_book',[]):
            if claim['creditor']!=acct:continue
            debtor=claim['debtor'];tangible=self.cash(debtor)+self.treasury_value(debtor)+self.balance('fed_reserve:'+debtor)+sum((D(v) for k,v in self.ledger_items(debtor) if k.startswith('savings:'+debtor+':')),D(0))
            for position in self.state['positions'].values():
                if position['account']==debtor:
                    instrument=self.instrument(position['symbol']);tangible+=money(D(position['qty'])*D(instrument['price'])*D(instrument.get('multiplier',1))*self.fx_rate(instrument.get('currency','GBP')))
            obligations=-sum((D(v) for k,v in self.ledger_items(debtor) if k.startswith('debt:'+debtor+':')),D(0));other_assets=sum((D(v) for k,v in self.ledger_items(debtor) if k.startswith(('claim:'+debtor+':','allowance:'+debtor+':','holding:'+debtor+':','investment:'+debtor+':'))),D(0));troubled=claim['status'] in ('DEFAULT','OVERDUE') or self.state.get('entities',{}).get(debtor,{}).get('status') in ('ADMINISTRATION','DISSOLVED') or tangible+other_assets<obligations;recovery=min(D(1),max(D(0),tangible)/obligations) if obligations>0 and troubled else D(1)
            receivables+=money(min(max(D(0),D(claim['balance'])-D(claim['allowance'])),D(claim['balance'])*recovery))
        receivables+=sum((D(v) for k,v in self.ledger_items(acct) if k.startswith('escrow:'+acct+':')),D(0))
        receivables+=self.balance('credit_asset:'+acct+':bank_loans')+self.balance('allowance:'+acct+':bank_loans')
        treasury=self.treasury_value(acct);reserves=self.balance('fed_reserve:'+acct);deferred=sum((D(v) for k,v in self.ledger_items(acct) if k.startswith('treasury_discount:'+acct+':')),D(0));outside=self.outside_value(acct);productive=self.productive_value(acct);equity=treasury+reserves+deferred+cash+market+investment+savings+receivables+self.asset_value(acct)+self.office_rou(acct)+outside+productive-debt
        # Fixed-income holdings are real exposure, separate from the equity VaR proxy.
        treasury_dv01=D(0)
        for position in self.state.get('treasury_positions',{}).values():
            if position['account']!=acct:continue
            quote=self.treasury_quote(self.state['treasury_securities'][position['security']])
            value=D(position['face'])/100*D(str(quote['dirty_price']))*self.fx_rate('USD')
            treasury_dv01+=value*D(str(quote['modified_duration']))*D('.0001')
            concentration.append((position['security'],float(abs(value))))
        equity_gross=gross
        gross+=abs(treasury)
        unreal+=treasury-self.treasury_basis(acct)
        unreal+=investment-investment_cost+self.asset_value(acct)-sum((D(v) for k,v in self.ledger_items(acct) if k.startswith('asset:'+acct+':')),D(0))
        income=-self.balance('pnl:'+acct);realised=self.realised_total(acct);fees=self.balance('expense:fees:'+acct);interest=self.balance('expense:interest:'+acct)
        contributed=-self.balance('equity:'+acct)
        profit=equity-contributed
        history=self.state['history'];navs=[float(h.get('nav',{}).get(acct,1)) for h in history]
        current_nav=navs[-1] if navs else 1
        if history:
            prev=history[-1];previous=D(prev.get('accounts',{}).get(acct,'0'));flow=contributed-D(prev.get('contributed',{}).get(acct,str(contributed)))
            if previous>0:current_nav*=float((equity-flow)/previous)
        peak=max(navs+[current_nav,1]);drawdown=max(0,(peak-current_nav)/peak)
        # Covariance proxy with a 0.35 common market correlation.
        sigma=math.sqrt(.65*sum(x*x for x in exposures)+.35*sum(exposures)**2)
        restricted=self.restricted_cash(acct)
        return dict(equity_gross=s(equity_gross),treasury_dv01_gbp=s(treasury_dv01),var_scope='Equity and option proxy only; Treasury rate sensitivity is reported separately as DV01',treasury_market=s(treasury),reserve_assets=s(reserves),deferred_financing=s(deferred),productive_assets=s(productive),outside_assets=s(outside),capital_reserves=s(-self.balance('capital_reserve:'+acct)),office_right_of_use=s(self.office_rou(acct)),owned_assets=s(self.asset_value(acct)),available_cash=s(max(D(0),cash-restricted)),restricted_cash=s(restricted),cash=s(cash),market=s(market),savings=s(savings),receivables=s(receivables),investment=s(investment),liquid_equity=s(cash+market+treasury-debt),debt=s(debt),equity=s(equity),gross=s(gross),net=s(market+treasury),unrealised=s(unreal),realised=s(realised),other_income=s(income-realised),fees=s(fees),interest=s(interest),contributed=s(contributed),profit=s(profit),leverage=float(gross/equity) if equity>0 else (0 if not gross else 999),drawdown=drawdown,var95=s(sigma/math.sqrt(252)*1.645),es95=s(sigma/math.sqrt(252)*2.063),volatility=sigma/max(1,float(equity)),concentration=concentration)

    def order(self,p):
        acct=self.account(p);sym=p['symbol'];ins=self.instrument(sym);sym=ins['symbol']
        if self.state.get('market_generation_version')==2 and sym in self.state['instruments'] and sym not in self.state.get('share_register',{}):raise ValueError('Security requires an issued-share register before trading; activating a reference does not create market capital or inventory')
        plan=self.state.get('operating_plans',{}).get(acct,{})
        if sum(o['account']==acct and not o.get('maker_quote') and o['status'] in ('OPEN','PARTIAL') for o in self.state['orders'])>=plan.get('order_capacity',50):raise ValueError('Operating desk order capacity reached')
        if self.state.get('governance_version') and (self.state['entities'].get(acct,{}).get('controlled') or self.state['entities'].get(acct,{}).get('kind')=='issuer'):
            entity=self.authority(acct,'trade',p.get('actor','player'));sectors=entity['mandate'].get('sectors',[])
            if sectors and ins['sector'] not in sectors:raise ValueError('Security is outside the investment mandate')
        if self.state['entities'].get(acct,{}).get('kind')=='issuer' and self.state.get('issuers',{}).get(sym,{}).get('account')==acct and getattr(self,'_issuer_buyback_account',None)!=acct:raise ValueError('Own shares require the authorised repurchase-and-retire action, not an ordinary treasury investment')
        qty=positive(p['qty'])
        if qty!=int(qty) or qty>D('1e15'):raise ValueError('Quantity exceeds exact ledger numeric precision (10^15 whole units)')
        side=p.get('side','buy');kind=p.get('type','market')
        if side not in ('buy','sell') or kind not in ('market','limit','stop','stop_limit','trailing','bracket'):raise ValueError('Invalid order type or side')
        if ins['status']!='OPEN':raise ValueError('Instrument is not open for trading')
        if self.is_frozen(acct):raise ValueError(self.restriction_message(acct,'Trading'))
        from .pretrade import validate
        admission=validate(self,p,acct,ins,qty)
        employee_delegate=self.employee_order_limit(p,ins)
        order=dict(id=uid(),tick=self.state['tick'],account=acct,symbol=sym,side=side,type=kind,qty=s(qty),remaining=s(qty),filled='0.00',status='OPEN',time=self.state['time'],credit_reserved=admission['credit_reserved'],pretrade_version=1,intent=admission['intent'],reduce_only=admission['reduce_only'],margin=admission['margin'],limit=str(self.quote_price(ins,p.get('limit',ins['price']))),stop=str(self.quote_price(ins,p.get('stop',ins['price']))),trail=s(positive(p.get('trail',5))),anchor=ins['price'],triggered=False,oco=p.get('oco'),take=str(self.quote_price(ins,p.get('take',D(ins['price'])*D('1.1')))),loss=str(self.quote_price(ins,p.get('loss',D(ins['price'])*D('.95')))))
        if kind=='bracket':
            px=D(ins['price']);take=D(order['take']);loss=D(order['loss'])
            if (side=='buy' and not loss<px<take) or (side=='sell' and not take<px<loss):raise ValueError('Bracket exits must sit on opposite sides of the current price')
        if self.state.get('microstructure_enabled') and sym in self.state['market_symbols'] and kind=='limit' and order['margin']:
            notional=qty*D(order['limit'])*self.fx_rate(ins['currency']);m=self.metrics(acct)
            if notional+D(m['gross'])>max(D(0),D(m['liquid_equity']))*2:raise ValueError('Resting margin limit exceeds risk capacity')
            if side=='sell':
                held=D(self.state['positions'].get(acct+':'+sym,{}).get('qty','0'));shorts=sum((abs(D(pos['qty'])) for pos in self.state['positions'].values() if pos['symbol']==sym and D(pos['qty'])<0),D(0));reserved=sum((D(x['remaining']) for x in self.state['orders'] if x['symbol']==sym and x['side']=='sell' and x['status'] in ('OPEN','PARTIAL') and x.get('margin')),D(0))
                if max(D(0),qty-max(D(0),held))+shorts+reserved>D(ins.get('borrow_available',0)):raise ValueError('Resting short exceeds unreserved borrow supply')
        if self.state.get('microstructure_enabled') and sym in self.state['market_symbols'] and kind=='limit' and not order['margin']:
            if side=='buy' and qty*D(order['limit'])*self.fx_rate(ins['currency'])>self.available_cash(acct):raise ValueError('Resting limit exceeds unreserved buying power')
            if side=='sell':
                held=D(self.state['positions'].get(acct+':'+sym,{}).get('qty','0'));reserved=sum((D(x['remaining']) for x in self.state['orders'] if x['account']==acct and x['symbol']==sym and x['side']=='sell' and x['status'] in ('OPEN','PARTIAL') and not x.get('margin')),D(0))
                if qty+reserved>max(D(0),held):raise ValueError('Resting sell limit exceeds unreserved holdings; enable borrowing')
        self.state['order_sequence']=self.state.get('order_sequence',0)+1;order['sequence']=self.state['order_sequence']
        tif=p.get('tif','GTC')
        if tif not in ('GTC','IOC','FOK'):raise ValueError('Unsupported time in force')
        order['tif']=tif;order['arrival_price']=ins['price'];order['executed_notional']='0';order['execution_fees_gbp']='0'
        if p.get('execution_hours'):
            hours=int(p['execution_hours'])
            if not 2<=hours<=744 or tif!='GTC' or kind not in ('market','limit'):raise ValueError('TWAP requires a GTC market or limit order over 2–744 hours')
            if acct=='personal' or sym not in self.state.get('market_symbols',[]) or not self.state.get('microstructure_enabled'):raise ValueError('TWAP requires an institutional account and a matched stock')
            order['execution_schedule']={'kind':'TWAP','hours':hours,'start_tick':self.state['tick']}
        self.configure_execution(order,p)
        self.execution_policy(order,p)
        if getattr(self,'_block_context',None):order['block_reference']=self._block_context
        if employee_delegate is not None:order['employee_cap']=p['_employee_cap'];order['employee_executed']='0.00'
        if p.get('employee'):order['employee']=p['employee']
        elif p.get('actor','').startswith('staff_'):order['employee']=p['actor']
        self.state['orders'].insert(0,order)
        self.explicit_risk_preflight(order)
        if order['status']=='REJECTED':return order
        self.archive_closed_orders()
        for queued in sorted(list(self.state['orders']),key=lambda x:x.get('sequence',0)):
            if queued['symbol']==sym and not queued.get('maker_quote'):self.process_order(queued)
        team=self.state.get('auto_teams',{}).get(acct)
        if team and team['enabled'] and not order.get('employee') and p.get('actor','player')=='player':team.setdefault('manual_choices',{})[sym]=dict(tick=self.state['tick'],order=order['id'],price=ins['price'],macro_rate=self.state['macro']['rate'],fundamentals=self.research_fundamentals(sym)[0],public_earnings_factor=ins.get('public_earnings_factor','1'))
        return order

    @staticmethod
    def quote_price(ins,value):
        value=D(str(value))
        if not value.is_finite() or value<=0 or value>D('1e15'):raise ValueError('Invalid execution price')
        return max(D(ins.get('tick_size','.01')),value.quantize(D(ins.get('tick_size','.01')),rounding=ROUND_HALF_EVEN))

    def process_order(self,o,forced=False):
        if not self.session_open():
            if o.get('tif') in ('IOC','FOK'):o['status']='CANCELLED';o['reason']='Immediate order outside configured trading session'
            return
        if self.state.get('microstructure_enabled') and self.state['paused'] and not self._advancing and not o.get('block_reference'):return
        if o['status'] not in ('OPEN','PARTIAL'):return
        ins=self.instrument(o['symbol']);px=D(ins['price'])
        if ins['status']!='OPEN':return
        buy=o['side']=='buy';kind=o['type']
        if kind=='trailing':
            anchor=D(o['anchor']);anchor=min(anchor,px) if buy else max(anchor,px);o['anchor']=str(anchor)
            trigger=anchor*(1+D(o['trail'])/100) if buy else anchor*(1-D(o['trail'])/100)
            if (buy and px<trigger) or (not buy and px>trigger):return
        if kind in ('stop','stop_limit') and not o['triggered']:
            if (buy and px<D(o['stop'])) or (not buy and px>D(o['stop'])):return
            o['triggered']=True
        limit=kind in ('limit','stop_limit')
        if limit and not (self.state.get('microstructure_enabled') and o['symbol'] in self.state.get('market_symbols',[])) and ((buy and px>D(o['limit'])) or (not buy and px<D(o['limit']))):
            if o.get('tif') in ('IOC','FOK'):o['status']='CANCELLED';o['reason']='Immediate limit is not marketable'
            return
        if self.is_frozen(o['account']) and not forced:
            o['status']='CANCELLED';o['reason']=self.restriction_message(o['account'],'Trading');return
        if o.get('pretrade_version') and not forced:
            from .pretrade import validate
            try:validate(self,{**o,'qty':o['remaining']},o['account'],ins,D(o['remaining']),exclude=o['id'])
            except ValueError as exc:
                o['status']='CANCELLED' if D(o['filled']) else 'REJECTED';o['reason']='Execution revalidation: '+str(exc);return
        if self.state.get('microstructure_enabled') and o['symbol'] in self.state.get('market_symbols',[]):return self.match_order(o,forced)
        if o['symbol'] in self.state['options'] and self.state['options'][o['symbol']]['kind']=='put' and self.state.get('microstructure_enabled') and (o['side']=='buy' or any(t['symbol']==o['symbol'] and t['buyer']==o['account'] and t['status']=='OPEN' for t in self.state.get('secured_puts',[]))):
            return self.process_secured_put(o)
        stored=self.state['instruments'].get(o['symbol']) or self.state['options'][o['symbol']]
        if stored.get('liquidity_tick')!=self.state['tick']:stored['liquidity_tick']=self.state['tick'];stored['liquidity_used']='0.00'
        qty=min(D(o['remaining']),max(D(0),D(ins['liquidity'])-D(stored['liquidity_used'])))
        if o.get('reduce_only') or forced:
            pos=self.state['positions'].get(o['account']+':'+o['symbol']);held=D(pos['qty']) if pos else D(0)
            if held==0 or (buy and held>0) or (not buy and held<0):o['status']='CANCELLED';return
            qty=min(qty,abs(held))
        if qty<=0:return
        if o.get('tif')=='FOK' and qty<D(o['remaining']):o['status']='CANCELLED';o['reason']='Insufficient depth for full immediate fill';return
        if ins.get('security_id'):
            qty,execution=execute_depth(ins,self.state['tick'],qty,buy,D(o['limit']) if limit else None)
            if qty<=0:return
        else:
            impact=D('.0005')+qty/D(ins['liquidity'])*D('.002')
            execution=self.quote_price(ins,px*(1+impact if buy else 1-impact))
            if limit:
                if buy and execution>D(o['limit']):return
                if not buy and execution<D(o['limit']):return
        try:self.fill(o,qty,execution,forced)
        except OrderRejected as e:
            o['status']='REJECTED' if D(o['filled'])==0 else 'CANCELLED';o['reason']=str(e);return
        stored['liquidity_used']=s(D(stored['liquidity_used'])+qty)
        if ins.get('security_id'):
            self.mark(o['symbol'],px*(1+(D(1) if buy else D(-1))*D('.001')*qty/D(ins['liquidity'])))
            stored['history'][-1]['v']+=int(qty)
        o['remaining']=s(D(o['remaining'])-qty);o['filled']=s(D(o['filled'])+qty);o['status']='FILLED' if D(o['remaining'])==0 else 'CANCELLED' if o.get('tif')=='IOC' else 'PARTIAL'
        if o.get('oco'):
            for other in self.state['orders']:
                if other['id']==o['oco'] and other['status'] in ('OPEN','PARTIAL'):
                    other['remaining']=s(max(0,D(other['remaining'])-qty))
                    if D(other['remaining'])==0:other['status']='CANCELLED'
        if kind=='bracket':
            children=[]
            for t,level in [('limit',o['take']),('stop',o['loss'])]:
                child={**o,'id':uid(),'side':'sell' if buy else 'buy','type':t,'qty':s(qty),'remaining':s(qty),'filled':'0.00','status':'OPEN','limit':level,'stop':level,'triggered':False,'oco':None,'reduce_only':True}
                children.append(child)
            children[0]['oco']=children[1]['id'];children[1]['oco']=children[0]['id'];self.state['orders'].extend(children)

    def fill(self,o,qty,price,forced=False):
        acct=o['account'];sym=o['symbol'];ins=self.instrument(sym);mult=D(ins.get('multiplier',1));fx=self.fx_rate(ins.get('currency','GBP'));signed=qty if o['side']=='buy' else -qty
        key=acct+':'+sym;pos=self.state['positions'].get(key,dict(account=acct,symbol=sym,qty='0.00',cost='0.00'))
        old=D(pos['qty']);cost=D(pos['cost']);new=old+signed
        put_writer=mult==100 and o.get('_put_writer') and self.state['options'][sym]['kind']=='put'
        if mult==100 and new<0 and not put_writer:raise OrderRejected('Short option writing is not enabled')
        if new<0 and new<old and not o['margin'] and not put_writer:raise OrderRejected('Enable margin to borrow shares for a short position')
        if new<0 and new<old and not put_writer and abs(new)+sum((abs(D(p['qty'])) for k,p in self.state['positions'].items() if k!=key and p['symbol']==sym and D(p['qty'])<0),D(0))>D(ins.get('borrow_available',D(ins['liquidity'])*20)):raise OrderRejected('Insufficient stock borrow availability')
        gross=money(qty*price*mult*fx);signed_gross=gross if signed>0 else -gross;plan=self.state.get('operating_plans',{}).get(acct,{});fee=max(D('1'),money(gross*D(plan['fee_rate'] if plan.get('enabled') else '.0005')));cash_delta=-signed_gross-fee
        employee_executed=D(o.get('employee_executed','0'))+gross+fee
        if 'employee_cap' in o:
            self.authority(acct,'trade',o['employee'])
            employee=next(e for e in self.state['employees'] if e['id']==o['employee'])
            fill_day=self.state['tick']//24
            spent=D(employee.get('fill_spent','0')) if employee.get('fill_day')==fill_day else D(0)
            if not employee['delegation']['trade'] or employee_executed>min(D(o['employee_cap']),D(employee['delegation']['per_order'])):raise OrderRejected('Actual fill plus fees exceeds employee delegated order limit')
            if spent+gross+fee>D(employee['delegation']['daily']):raise OrderRejected('Actual fills exceed employee delegated daily limit')
            team=self.state.get('auto_teams',{}).get(acct,{})
            if team and self.team_daily_spend(acct)+gross+fee>D(team.get('daily_limit',team.get('portfolio_authority','1e30'))):raise OrderRejected('Actual fills exceed the shared fund trading limit')
        realised=D(0)
        if old*signed<0:
            closing=min(abs(old),qty);released=money(cost*closing/abs(old));closing_consideration=money(gross*closing/qty)
            realised=money(closing_consideration*(1 if old>0 else -1)-released)
        delta=signed_gross+realised;newcost=cost+delta
        metrics=self.metrics(acct);mark=D(ins['price'])*mult*fx;newgross=D(metrics['gross'])-abs(old*mark)+abs(new*price*mult*fx)
        projected=D(metrics['liquid_equity'])-fee-abs(qty*(price-D(ins['price']))*mult*fx)
        old_reserve=self.put_collateral(acct,sym,old,cost,mark)
        new_reserve=self.put_collateral(acct,sym,new,newcost,mark)
        reserve=D(metrics['restricted_cash'])-old_reserve+new_reserve
        from .pretrade import order_cash
        if not o.get('maker_quote'):reserve-=order_cash(self,o)-order_cash(self,o,max(D(0),D(o['remaining'])-qty))
        elif self.state.get('microstructure_enabled') and sym in self.state.get('market_symbols',[]) and o['type']=='limit' and o['side']=='buy' and not o.get('margin') and not o.get('reduce_only'):reserve-=D(o['remaining'])*D(o['limit'])*fx
        financing_need=max(D(0),(reserve if o.get('margin') else D(0))-self.cash(acct)-cash_delta)
        committed_credit=sum((D(other.get('credit_reserved',0))*D(other['remaining'])/D(other['qty']) for other in self.state['orders'] if other['id']!=o['id'] and other['status'] in ('OPEN','PARTIAL','PAUSED')),D(0)) if financing_need else D(0)
        if self.state.get('microstructure_enabled') and financing_need>max(D(0),self.cash('prime')-committed_credit):raise OrderRejected('Prime broker has insufficient uncommitted funding liquidity')
        if not forced:
            reducing=abs(new)<=abs(old) and old*signed<0
            policy=self.state.get('account_limits',{}).get(acct,{})
            leverage=D(policy.get('max_leverage','2'));single=D(policy.get('single_name_pct','200'));unit=price*mult*fx
            if not reducing and newgross>max(D(0),projected)*leverage:
                maximum=max(0,int((max(D(0),projected)*leverage-(D(metrics['gross'])-abs(old*mark)))/unit)-int(old if signed>0 else -old))
                raise OrderRejected(f'Desk gross-exposure limit: projected £{newgross:,.2f} exceeds {leverage}× liquid equity £{projected:,.2f}; maximum approximately {maximum} additional units at this price (before final costs).')
            if not reducing and abs(new*unit)>max(D(0),projected)*single/100:
                maximum=max(0,int(max(D(0),projected)*single/100/unit)-int(old if signed>0 else -old))
                raise OrderRejected(f'Single-name concentration limit: projected £{abs(new*unit):,.2f} exceeds {single}% of liquid equity £{projected:,.2f}; maximum approximately {maximum} additional units at this price (before final costs).')
            if o['margin']:
                if not reducing and newgross>max(D(0),projected)*2:raise OrderRejected('Initial margin requires 50% equity')
            elif self.cash(acct)+cash_delta-reserve<0:raise OrderRejected(f'Unrestricted cash limit: order and fees £{(-cash_delta):,.2f}, cash after collateral £{(self.cash(acct)-reserve):,.2f}; maximum approximately {max(0,int(max(D(0),self.cash(acct)-reserve-fee)/(price*mult*fx)))} units at this price.')
            if new<0 and not put_writer and not reducing and projected<abs(new*mark)*D('.5'):raise OrderRejected('Insufficient short collateral')
        self.public_stock_transfer(acct,sym,old,new)
        self.post(f"{o['side'].upper()} {qty} {sym} @ {price}",{'cash:'+acct:cash_delta,'inventory:'+acct+':'+sym:delta,'pnl:'+acct:-realised,'expense:fees:'+acct:fee})
        if 'employee_cap' in o:
            o['employee_executed']=s(employee_executed);employee['fill_day']=fill_day;employee['fill_spent']=s(spent+gross+fee)
        if new==0:self.state['positions'].pop(key,None)
        else:self.state['positions'][key]=dict(account=acct,symbol=sym,qty=s(new),cost=s(newcost),borrowed=s(max(D(0),-new)))
        if self.cash(acct)<(reserve if o.get('margin') else D(0)):
            loan=(reserve if o.get('margin') else D(0))-self.cash(acct);lines={'cash:'+acct:loan,'debt:'+acct+':margin':-loan}
            if self.state.get('microstructure_enabled'):lines.update({'cash:prime':-loan,'prime:loan:'+acct:loan})
            self.post('Margin financing',lines)
        elif self.balance('debt:'+acct+':margin')<0:
            repaid=min(self.available_cash(acct),-self.balance('debt:'+acct+':margin'))
            lines={'cash:'+acct:-repaid,'debt:'+acct+':margin':repaid}
            if self.state.get('microstructure_enabled'):lines.update({'cash:prime':repaid,'prime:loan:'+acct:-repaid})
            self.post('Margin financing repayment',lines)
        if o.get('execution_policy'):
            o['policy_hour_filled']=str((D(o.get('policy_hour_filled',0)) if o.get('policy_fill_tick')==self.state['tick'] else D(0))+qty);o['policy_fill_tick']=self.state['tick']
        if o.get('execution_schedule') or o.get('display_qty'):
            o['slice_count']=o.get('slice_count',0)+1
        if 'executed_notional' not in o and D(o.get('filled',0))>0:
            old=[json.loads(r[0]) for r in self.db.execute("select data from executions where world=? and json_extract(data,'$.order')=?",(self.state['id'],o['id']))];o['executed_notional']=str(sum((D(f['qty'])*D(f['price']) for f in old),D(0)));o['execution_fees_gbp']=str(sum((D(f['fee']) for f in old),D(0)))
        o['executed_notional']=str(D(o.get('executed_notional',0))+qty*price);o['execution_fees_gbp']=str(D(o.get('execution_fees_gbp',0))+fee)
        actor=next((a for a in self.state.get('participants',[]) if a['account']==acct and a.get('mandate')),None)
        if actor:
            day=self.state['tick']//24;actor['turnover_used']=str((D(actor.get('turnover_used',0)) if actor.get('turnover_day')==day else D(0))+gross);actor['turnover_day']=day
        fill=dict(venue='BLOCK' if o.get('block_reference') else 'EXCHANGE',parent_order=o['id'] if o.get('execution_schedule') or o.get('display_qty') else None,slice=o.get('slice_count'),id=uid(),order=o['id'],account=acct,symbol=sym,side=o['side'],qty=s(qty),price=str(price),currency=ins.get('currency','GBP'),fx_rate=str(fx),consideration_gbp=s(gross),fee=s(fee),time=self.state['time'],realised=s(realised),paired=bool(o.get('_option_paired') or self.state.get('microstructure_enabled') and sym in self.state.get('market_symbols',[])))
        if o.get('_option_paired') or self.state.get('microstructure_enabled') and sym in self.state.get('market_symbols',[]):self.post('Execution fee clearing',{'cash:clearing':fee,'pnl:clearing':-fee})
        self.db.execute('insert into executions values(?,?,?)',(fill['id'],self.state['id'],json.dumps(fill)));self.state['fills'].insert(0,fill);self.state['fills']=self.state['fills'][:2000]

    def loan(self,p):return self.originate_loan(p)

    def repay(self,p):return self.repay_credit(p)

    def savings_transfer(self,p):
        acct=self.account(p);bank=next((b for b in self.state['banks'] if b['id']==p.get('bank','sterling')),None)
        if not bank:raise ValueError('Unknown bank')
        if self.is_frozen(acct):raise ValueError(self.restriction_message(acct,'Savings transfer'))
        if bank.get('entity'):
            self.refresh_player_banks()
            if acct==bank['entity']:raise ValueError('A bank cannot deposit into itself')
            if p.get('direction','deposit')=='deposit' and (bank['licence']!='AUTHORISED' or D(bank['equity'])<D(self.state.get('banking_rules',{}).get('minimum_capital','100000'))):raise ValueError('Bank is not authorised to accept deposits')
        amount=positive(p['amount']);direction=p.get('direction','deposit');key='savings:'+acct+':'+bank['id']
        if direction=='deposit':
            if bank.get('status')=='DISTRESSED':raise ValueError('Bank is distressed; new deposits are suspended')
            if self.available_cash(acct)<amount:raise ValueError('Insufficient settlement cash')
            self.post('Savings deposit at '+bank['name'],{'cash:'+acct:-amount,key:amount})
            bank['cash']=s(D(bank['cash'])+amount);bank['deposits']=s(D(bank['deposits'])+amount)
        elif direction=='withdraw':
            if self.balance(key)<amount:raise ValueError('Insufficient savings balance')
            if D(bank['cash'])<amount or bank.get('status')=='DISTRESSED':raise ValueError('Bank liquidity restriction prevents withdrawal')
            self.post('Savings withdrawal from '+bank['name'],{'cash:'+acct:amount,key:-amount})
            bank['cash']=s(D(bank['cash'])-amount);bank['deposits']=s(D(bank['deposits'])-amount)
        else:raise ValueError('Unknown transfer direction')
        self.bank_sync(bank,'Bank savings transfer')
        if bank.get('entity') and acct not in bank['customers']:
            bank['customers'][acct]={'account':acct,'product':'savings','opened':self.state['time'],'status':'ACTIVE','loan_applied':False};bank['opened']+=1
        return {'balance':s(self.balance(key)),'bank':bank['name']}

    def savings_accrual(self):
        w=self.state;residuals=w.setdefault('savings_residuals',{})
        for bank in w['banks']:
            if bank.get('entity'):
                if bank.get('deposit_accrual_tick')==w['tick']:continue
                bank['deposit_accrual_tick']=w['tick']
            rate=bank.get('deposit_rate',max(0,w['macro']['rate']-1))
            for acct in self.accounts():
                key='savings:'+acct+':'+bank['id'];balance=self.balance(key)
                if balance<=0:continue
                customer_rate=0 if bank.get('customers',{}).get(acct,{}).get('product')=='current' else rate
                raw=balance*D(str(customer_rate))/D(100*365*24)+D(residuals.get(key,'0'));interest=money(raw);residuals[key]=str(raw-interest)
                if interest:
                    self.post('Savings interest '+bank['name'],{key:interest,'pnl:'+acct:-interest})
                    bank['deposits']=s(D(bank['deposits'])+interest);bank['equity']=s(D(bank['equity'])-interest)
            self.bank_sync(bank,'Bank savings interest')
            if D(bank['equity'])<=0 and bank.get('status')!='DISTRESSED':
                bank['status']='DISTRESSED';self.news(bank['name']+' suspends withdrawals','Negative bank capital triggers a deposit restriction. Claims remain recorded; losses are not silently erased.','BANKING')
                self.message(bank['name'],'Deposit restriction','Capital is exhausted. Savings remain recorded but withdrawals are temporarily suspended.')

    def communicate(self,p):
        recipient=next((n for n in self.state['npcs'] if n['id']==p.get('recipient')),None)
        intent=p.get('intent','update');fund=next((f for f in self.state['funds'] if f['id']==p.get('fund')),None)
        if intent=='disclose':
            if not fund:raise ValueError('Select a fund to disclose corrected figures')
            actual=D(self.metrics(fund['id'])['equity']);corrected=[]
            for claim in self.state['claims']:
                if claim['fund']==fund['id'] and claim['status'] in ('PUBLISHED','INQUIRY') and D(claim['gap'])>0:
                    if claim.get('phase2_reporting'):self.statement_correct({'statement':claim['id']})
                    claim['status']='CORRECTED';claim['corrected_time']=self.state['time'];corrected.append(claim['id'])
            if not corrected:raise ValueError('No outstanding misstatements to correct')
            fund['reported']=s(actual)
            for case in self.state['investigations']:
                if case['claim'] in corrected and not case.get('legal_case'):case['status']='REMEDIATION';case['remediation_tick']=self.state['tick']
            for n in self.state['npcs']:
                if n['id'] in fund['investors']:n['trust']=max(0,n['trust']-8)
            self.state['reputation']=max(0,self.state['reputation']-3)
            self.message('Compliance Office','Corrected statement recorded',f"{fund['name']} disclosed actual NAV of £{actual:,.2f}. Original claims remain in the evidence record. Open inquiries enter a review period; existing enforcement is not erased.")
            return {'corrected':len(corrected)}
        if not recipient:raise ValueError('Select an investor recipient')
        memory=self.state.setdefault('contact_history',{});contact=recipient['id']+':'+str(p.get('fund',''))+':'+intent
        if contact in memory and self.state['tick']-memory[contact]<24:raise ValueError('This investor already received this type of contact in the last simulation day')
        memory[contact]=self.state['tick']
        if intent=='update':
            if not fund or recipient['id'] not in fund['investors']:raise ValueError('Recipient must hold units in the selected fund')
            actual=self.metrics(fund['id']);self.message('You → '+recipient['name'],'Verified investor update',f"Actual NAV {gbp_for_message(actual['equity'])}; cash {gbp_for_message(actual['cash'])}; debt {gbp_for_message(actual['debt'])}. Shared figures are drawn from the ledger.")
            recipient['trust']=min(100,recipient['trust']+2);self.message(recipient['name'],'Update acknowledged','Your figures agree with the custodial record. Confidence improves modestly.')
        elif intent=='risk':
            recipient['trust']=min(100,recipient['trust']+1);recipient['last_discussion']=self.state['tick'];self.message(recipient['name'],'Risk preference discussion',f"My risk preference is {recipient['risk']:.2f} on a 0–1 scale. I limit each new allocation to 25% of available wealth and require trust of at least 45.")
        else:raise ValueError('Unknown communication intent')
        return {'trust':recipient['trust']}

    def chain(self,p):
        sym=p.get('symbol','ALTN' if self.state.get('_legacy_fixture') else 'NVDA');ins=self.state['instruments'][sym];days=int(p.get('days',30))
        if not 1<=days<=730:raise ValueError('Expiry must be 1–730 days')
        expiry=(datetime.fromisoformat(self.state['time'])+timedelta(days=days)).replace(hour=16,minute=0,second=0,microsecond=0).isoformat();spot=float(ins['price']);step=max(1,round(spot*.05))
        rows=[]
        for i in range(-4,5):
            strike=max(1,round(spot/step)*step+i*step);row={'strike':strike}
            for kind in ('call','put'):
                symbol=f"{sym}-{expiry[:10]}-{strike}-{kind[0].upper()}"
                self.state['options'].setdefault(symbol,dict(symbol=symbol,underlying=sym,strike=s(strike),expiry=expiry,kind=kind))
                row[kind]=self.instrument(symbol)
            rows.append(row)
        return rows

    def strategy(self,p):
        acct=self.account(p);under=p.get('symbol','ALTN' if self.state.get('_legacy_fixture') else 'NVDA');kind=p.get('strategy','straddle');contracts=int(p.get('contracts',1))
        if not 1<=contracts<=100:raise ValueError('Strategy size must be 1–100 contracts')
        if kind not in ('straddle','strangle','protective_put'):raise ValueError('Supported strategies: straddle, strangle, protective_put')
        chain=self.chain({'symbol':under,'days':int(p.get('days',30))});spot=D(self.state['instruments'][under]['price']);atm=min(chain,key=lambda r:abs(D(r['strike'])-spot))
        if kind=='straddle':legs=[(atm['call']['symbol'],contracts),(atm['put']['symbol'],contracts)]
        elif kind=='strangle':
            put=min(chain,key=lambda r:abs(D(r['strike'])-spot*D('.9')));call=min(chain,key=lambda r:abs(D(r['strike'])-spot*D('1.1')));legs=[(call['call']['symbol'],contracts),(put['put']['symbol'],contracts)]
        else:legs=[(under,contracts*100),(atm['put']['symbol'],contracts)]
        strategy_id=uid();executed=[]
        for sym,qty in legs:
            order=self.order({'account':acct,'symbol':sym,'side':'buy','qty':qty})
            if order['status']!='FILLED':raise ValueError('Strategy could not fill all legs: '+order.get('reason','insufficient hourly liquidity')+'. No legs were committed.')
            order['strategy']=strategy_id;executed.append(order['id'])
        entry=dict(id=strategy_id,type=kind,account=acct,underlying=under,orders=executed,time=self.state['time'])
        self.state.setdefault('strategies',[]).append(entry);return entry

    def fund(self,p):
        owner=p.get('owner','personal');authority=self.authority(owner,'payment')
        if self.is_frozen(owner):raise ValueError('Seed capital is restricted')
        amount=positive(p.get('amount',1000));name=str(p.get('name','New Fund')).strip()[:60]
        if not name:raise ValueError('Fund name required')
        if self.available_cash(owner)<amount:raise ValueError('Insufficient owner cash for seed investment')
        if self.is_fund(owner) and not authority['mandate']['related_parties']:raise ValueError('Owner fund mandate does not permit fund-of-funds investment')
        manager=p.get('manager',owner);self.authority(manager,'govern')
        if self.is_frozen(manager):raise ValueError('Manager account is restricted')
        fund_type=p.get('fund_type','investment_fund')
        if fund_type not in ('investment_fund','hedge_fund','private_equity','credit_fund'):raise ValueError('Unknown fund mandate type')
        if owner!='personal' and amount>D(authority['payment_limit']):raise ValueError('Seed investment exceeds owner payment authority')
        f=dict(id=uid(),name=name,units=s(amount),highwater='1.00',reported=s(amount),management=0,performance=0,compensation_authorized=False,investors={owner:s(amount)},fund_type=fund_type,manager=manager,lock_until=self.state['tick']+(24*365*5 if fund_type=='private_equity' else 24*7))
        self.state['funds'].append(f);self.sync_entities()
        if owner!='personal':self.state['entities'][f['id']]['parent']=owner
        if fund_type in ('private_equity','credit_fund'):self.state['entities'][f['id']]['mandate']['related_parties']=True
        if 'fund_type' in p:
            leverage,single={'investment_fund':('1','25'),'hedge_fund':('2','50'),'private_equity':('1','100'),'credit_fund':('1','20')}[fund_type]
            self.state.setdefault('account_limits',{})[f['id']]={'max_leverage':leverage,'single_name_pct':single}
        self.post('Fund seed transfer',{'cash:'+owner:-amount,'investment:'+owner+':'+f['id']:amount,'cash:'+f['id']:amount,'equity:'+f['id']:-amount})
        self.news('New investment mandate',name+' begins operations with segregated capital.','INSTITUTIONS');return f

    def subscribe(self,p):
        if self.is_frozen(p['fund']):raise ValueError(self.restriction_message(p['fund'],'Fund instruction'))
        f=next(f for f in self.state['funds'] if f['id']==p['fund']);terms=f.get('terms',{})
        if not terms.get('subscription_open',True):raise ValueError('Subscription window is closed')
        if p['investor'] not in terms.get('eligible',[n['id'] for n in self.state['npcs']]):raise ValueError('Investor is not eligible for this share class')
        if D(str(p['amount']))<D(terms.get('minimum','1')):raise ValueError('Below minimum subscription')
        npc=next(n for n in self.state['npcs'] if n['id']==p['investor']);amount=positive(p['amount'])
        if npc['trust']<45:raise ValueError('Investor confidence is too low')
        if amount>D(npc['wealth'])*D('.25') and getattr(self,'_capital_call_context',None)!=(f['id'],npc['id']):raise ValueError('Investor allocation exceeds 25% of available wealth')
        if amount>D(npc['wealth']):raise ValueError('Investor lacks actual subscription cash')
        nav=D(self.metrics(f['id'])['equity']);units=D(f['units'])
        if nav<=0:raise ValueError('Fund has no positive NAV')
        issued=(amount*units/nav).quantize(D('.00000001'),rounding=ROUND_DOWN)
        if issued<=0:raise ValueError('Subscription is below the supported fund unit precision')
        npc['wealth']=s(D(npc['wealth'])-amount);f['units']=str(units+issued);f['investors'][npc['id']]=str(D(f['investors'].get(npc['id'],'0'))+issued)
        self.post('Investor subscription',{'cash:'+f['id']:amount,'equity:'+f['id']:-amount});self.npc_subscription_book(npc,f,amount)
        self.message(npc['name'],'Subscription confirmed',f"Allocated £{amount:,.2f} to {f['name']} at actual net asset value.");return {'units':str(issued)}

    def redeem(self,p):
        if self.is_frozen(p['fund']):raise ValueError(self.restriction_message(p['fund'],'Fund instruction'))
        f=next(f for f in self.state['funds'] if f['id']==p['fund']);investor=p['investor'];units=D(str(p['units']))
        if not units.is_finite() or units<=0:raise ValueError('Positive redemption units required')
        if self.state['tick']<f['lock_until']:raise ValueError('Fund lock-up remains in force until simulation hour '+str(f['lock_until']))
        if units>D(f['investors'].get(investor,'0')):raise ValueError('Insufficient investor units')
        amount=(D(self.metrics(f['id'])['equity'])*units/D(f['units'])).quantize(CENT,rounding=ROUND_DOWN)
        if amount<=0:raise ValueError('Fund has no redeemable NAV')
        if self.available_cash(f['id'])<amount:raise ValueError('Fund liquidity cannot meet redemption; sell positions first')
        self.post('Investor redemption',{'cash:'+f['id']:-amount,'equity:'+f['id']:amount})
        if investor=='personal':
            basis=self.balance('investment:personal:'+f['id'])*units/D(f['investors'][investor]);basis=money(basis)
            self.post('Personal fund redemption',{'cash:personal':amount,'investment:personal:'+f['id']:-basis,'pnl:personal':basis-amount})
        else:
            npc=next(n for n in self.state['npcs'] if n['id']==investor);npc['wealth']=s(D(npc['wealth'])+amount)
            if self.state.get('fund_system_version'):self.npc_claim_release(npc,f,units,amount)
        f['units']=str(D(f['units'])-units);f['investors'][investor]=str(D(f['investors'][investor])-units)
        return {'amount':s(amount),'status':'SETTLED','fund':f['id'],'investor':investor,'destination_account':'personal' if investor=='personal' else 'investor:'+investor,'personal_cash':s(self.cash()),'personal_net_assets':self.metrics()['equity'],'fund_nav':self.metrics(f['id'])['equity']}

    def report(self,p):
        f=next(f for f in self.state['funds'] if f['id']==p['fund']);actual=D(self.metrics(f['id'])['equity']);reported=positive(p['reported'])
        f['reported']=s(reported);gap=reported-actual
        claim=dict(id=uid(),fund=f['id'],actual=s(actual),reported=s(reported),gap=s(gap),time=self.state['time'],evidence=0,status='PUBLISHED')
        self.state['claims'].append(claim)
        self.phase2_statement(claim)
        for n in self.state['npcs']:
            if n['id'] in f['investors']:n['trust']=min(100,n['trust']+(2 if gap>0 else 1))
        self.message('Investor Relations',f"{f['name']} statement distributed",f"Reported NAV £{reported:,.2f}; ledger NAV £{actual:,.2f}. Statements do not create cash. Subsequent audits compare published claims with accounting evidence.")
        return claim

    def mark(self,symbol,price):
        ins=self.state['instruments'][symbol];old=ins['price'];price=str(self.quote_price(ins,price));ins['previous']=old;ins['price']=price;ins['timestamp']=self.state['time']
        self._opportunity_cache=None  # Public marks invalidate within-tick research features.
        if ins['history'] and ins['history'][-1]['t']==self.state['tick']:
            bar=ins['history'][-1];bar['c']=float(price);bar['h']=max(bar['h'],float(price));bar['l']=min(bar['l'],float(price))
        else:
            ins['history'].append(dict(t=self.state['tick'],o=float(old),h=max(float(old),float(price)),l=min(float(old),float(price)),c=float(price),v=0));ins['history']=ins['history'][-500:]

    def macro_change(self,p,reason='Economic conditions updated',rate_information_delta=None):
        macro=self.state['macro'];before=dict(macro)
        for k in ('rate','inflation','growth','stress'):
            if k in p:
                v=float(p[k]);lo=0 if k=='stress' else -10
                if not math.isfinite(v) or not lo<=v<=100:raise ValueError('Economic input outside supported range')
                macro[k]=v
        if self.state.get('fed'):
            fed=self.state['fed']
            for key,field in (('inflation','headline'),('growth','growth'),('stress','stress')):
                if key in p:
                    delta=float(macro[key])-float(before[key]);fed['latent'][field]=float(macro[key]);fed['observed'][field]=float(macro[key])
                    if key=='inflation':fed['latent']['core']=max(-1,min(15,fed['latent']['core']+delta));fed['observed']['core']=fed['latent']['core']
        rate=((macro['rate']-before['rate']) if rate_information_delta is None else rate_information_delta)/100;credit=(macro['stress']-before['stress'])/100;growth=(macro['growth']-before['growth'])/100
        durations={'Fixed income':7,'Technology':6,'Financials':2,'Healthcare':4,'Energy':2,'Industrials':3,'Consumer':4,'Commodities':1,'Index':4,'Property':8,'Utilities':6}
        if rate or credit or growth:
            for sym,ins in self.state['instruments'].items():
                duration=durations.get(ins['sector'],4);sensitivity=.05 if ins['sector'] in ('Fixed income','Commodities') else .25
                if self.state.get('microstructure_enabled') and sym in self.state.get('market_symbols',[]):
                    from .markets import classifications
                    sector=classifications().get(sym,{}).get('sector',ins['sector'])
                    sector={'Financial Services':'Financials','Real Estate':'Property','Consumer Discretionary':'Consumer','Consumer Staples':'Consumer','Communication Services':'Technology'}.get(sector,sector)
                    duration=durations.get(sector,4);sensitivity=.05 if sector in ('Fixed income','Commodities') else .25
                    # Public information reprices investor expectations, not the
                    # tape. Keep dealers anchored to the revised public value;
                    # only actual matched trades may update the observed mark.
                    cyclicality={'Technology':1.5,'Industrials':1.4,'Energy':1.1,'Consumer':1.,'Financials':1.,'Healthcare':.6,'Utilities':.3,'Property':.7}.get(sector,.8)
                    revision=max(-.5,min(.5,math.exp(-duration*rate-sensitivity*credit+cyclicality*growth)-1))
                    if revision:self.market_event({'symbol':sym,'kind':'policy','severity':revision})
                elif rate or credit:self.mark(sym,max(.05,float(ins['price'])*math.exp(-duration*rate-sensitivity*credit)))
        self.news(reason,f"Policy rate {macro['rate']:.2f}%, inflation {macro['inflation']:.2f}%, model growth {macro['growth']:.2f}%, credit stress {macro['stress']:.0f}/100. Valuations reflect duration and credit exposure; new financing and savings rates follow policy.",'ECONOMY')
        return dict(macro)

    def corporate(self,p):
        sym=p.get('symbol','ALTN' if self.state.get('_legacy_fixture') else 'NVDA');ins=self.state['instruments'][sym];kind=p.get('kind','earnings')
        if kind=='dividend':
            if sym in self.state.get('share_register',{}):raise ValueError('Listed dividends require an approved public shareholder resolution')
            per=money(D(ins['price'])*D('.01'))
            for pos in list(self.state['positions'].values()):
                if pos['symbol']==sym:
                    amount=money(D(pos['qty'])*per*self.fx_rate(ins.get('currency','GBP')));self.post('Fictional dividend '+sym,{'cash:'+pos['account']:amount,'pnl:'+pos['account']:-amount})
            self.mark(sym,max(D('.05'),D(ins['price'])-per))
            self.news('Scenario: '+sym+' cash distribution',f"{ins.get('currency','GBP')} {per} per share credited to holders; short borrowers owe the distribution. Ex-distribution price adjusts accordingly.",'CORPORATE')
        elif kind=='earnings':
            ins['expected_cashflows']=ins.get('expected_cashflows',1)*.75
            if ins['fundamentals']['profit'] is not None:ins['fundamentals']['profit']=s(D(ins['fundamentals']['profit'])*D('.75'))
            self.mark(sym,D(ins['price'])*D('.93'));ins['vol']=min(.9,ins['vol']*1.15)
            for key in ('liquidity_anchor','liquidity_center'):
                if key in ins:ins[key]=str(D(ins[key])*D('.93'))
            self.news('Scenario: '+sym+' earnings revision','Model expected cash flows contract 25%. Lower expected cash flows reduce model valuation; uncertainty raises volatility.','CORPORATE')
        elif kind=='split':
            ins['price']=str(D(ins['price'])/2);ins['previous']=str(D(ins['previous'])/2);
            if ins['fundamentals']['shares'] is not None:ins['fundamentals']['shares']*=2
            ins['model_share_factor']=ins.get('model_share_factor',1)*2
            if 'model_fundamental' in ins:ins['model_fundamental']=str(D(ins['model_fundamental'])/2)
            for key in ('liquidity_anchor','liquidity_center'):
                if key in ins:ins[key]=str(D(ins[key])/2)
            if 'model_daily_volume' in ins:ins['model_daily_volume']*=2
            if 'executed_volume' in ins:ins['executed_volume']=str(D(ins['executed_volume'])*2)
            if ins.get('institutional_profile'):
                ins['institutional_profile']['adv']*=2;ins['institutional_profile']['free_float']*=2
            if self.state.get('market_generation_version')==2:
                self.state['issuers'][sym]['model_shares']*=2
                for key in ('outstanding','authorised','free_float','strategic_shares','treasury'):self.state['share_register'][sym][key]=str(D(self.state['share_register'][sym][key])*2)
            for public_bid in self.state.get('public_tenders',[]):
                if public_bid['symbol']==sym and public_bid['status']=='OPEN':
                    self.public_tender_refund(public_bid);public_bid['status']='CANCELLED_CORPORATE_ACTION';public_bid['reason']='Share split requires a fresh offer with revised share terms'
                    self.audit('public_tender_cancelled_for_split',{'id':public_bid['id'],'symbol':sym})
            for stock_loan in self.state.get('stock_loans',[]):
                if stock_loan['symbol']==sym:
                    for loan_field in ('quantity','original_quantity','returned'):
                        if loan_field in stock_loan:stock_loan[loan_field]=str(D(stock_loan[loan_field])*2)
            for legacy_key in self.state.get('legacy_stock_borrow',{}):
                if legacy_key.rsplit(':',1)[-1]==sym:self.state['legacy_stock_borrow'][legacy_key]=str(D(self.state['legacy_stock_borrow'][legacy_key])*2)
            for resolution in self.state.get('public_resolutions',[]):
                if resolution['symbol']==sym and resolution['status']=='OPEN':
                    resolution['voting_total']=str(D(resolution['voting_total'])*2);resolution['eligible']={a:str(D(q)*2) for a,q in resolution['eligible'].items()}
            for flow in ins.get('flow_history',[]):
                flow['qty']*=2;flow['price']=str(D(flow['price'])/2)
            ins['liquidity']*=2
            if 'borrow_available' in ins:ins['borrow_available']*=2
            for bar in ins['history']:
                for key in ('o','h','l','c'):bar[key]=round(bar[key]/2,2)
            for pos in self.state['positions'].values():
                if pos['symbol']==sym:pos['qty']=s(D(pos['qty'])*2);pos['borrowed']=s(max(0,-D(pos['qty'])))
            for o in self.state['orders']:
                if o['symbol']==sym and o['status'] in ('OPEN','PARTIAL'):
                    for k in ('qty','remaining','filled'):o[k]=s(D(o[k])*2)
                    if o.get('arrival_price'):o['arrival_price']=str(D(o['arrival_price'])/2)
                    if o.get('execution_policy'):
                        o['execution_policy']['arrival']=str(D(o['execution_policy']['arrival'])/2);o['policy_hour_filled']=str(D(o.get('policy_hour_filled',0))*2)
                    if o.get('execution_schedule',{}).get('volume_start') is not None:o['execution_schedule']['volume_start']=str(D(o['execution_schedule']['volume_start'])*2)
                    for k in ('limit','stop','anchor','take','loss'):
                        if k in o:o[k]=str(D(o[k])/2)
            # Do not split underlyings with outstanding option contracts: contract adjustment needs a deliverable model.
            self.news(sym+' completes a two-for-one split','Share counts double; prices and outstanding orders adjust. Cost basis is preserved.','CORPORATE')
        else:raise ValueError('Unknown corporate action')
        return {'symbol':sym}

    def advance(self,hours):
        hours=int(hours)
        if not 1<=hours<=744:raise ValueError('Advance between 1 and 744 hours per request')
        w=self.state
        self.ensure_exchange_coverage()
        for _ in range(hours):
            w['tick']+=1;w['time']=(datetime.fromisoformat(w['time'])+timedelta(hours=1)).isoformat()
            self.fed_tick()
            self.refresh_institutional_borrow()
            self.advance_execution_clocks()
            self.business_tick();self.employee_tick();self.research_tick();self.property_tick();self.wealth_tick();self.office_tick();self.living_world_tick()
            rng=random.Random(w['seed']+w['tick']*100003);common=rng.gauss(0,1);sectors={sector:rng.gauss(0,1) for sector in sorted({i['sector'] for i in w['instruments'].values()})}
            for ins in w['instruments'].values():
                if w.get('microstructure_enabled') and ins['symbol'] in w['market_symbols']:
                    ins['previous']=ins['price'];ins['timestamp']=w['time'];v=float(ins['price']);ins['history'].append(dict(t=w['tick'],o=v,h=v,l=v,c=v,v=0));ins['history']=ins['history'][-500:];continue
                old=float(ins['price']);vol=ins['vol']*(1+w['macro']['stress']/100)
                z=.6*common+.4*sectors[ins['sector']]+math.sqrt(.48)*rng.gauss(0,1)
                drift=(w['macro']['growth']-w['macro']['rate']*.35)/100/(365*24)
                if ins['sector']=='Fixed income':drift=-w['macro']['stress']/100000
                close=max(.05,old*math.exp(drift-vol*vol/(2*365*24)+vol/math.sqrt(365*24)*z))
                ins['previous']=ins['price'];ins['price']=str(self.quote_price(ins,close));ins['timestamp']=w['time']
                ins['history'].append(dict(t=w['tick'],o=round(old,2),h=round(max(old,close)*(1+abs(z)*.001),2),l=round(min(old,close)/(1+abs(z)*.001),2),c=float(ins['price']),v=int(ins['liquidity']*rng.uniform(.5,4))))
                ins['history']=ins['history'][-500:]
            self.update_market_information(common,sectors,rng)
            self.agents_tick()
            for o in sorted(list(w['orders']),key=lambda o:o.get('sequence',0)):
                if not o.get('maker_quote'):self.process_order(o,bool(o.get('forced')))
            self.refresh_player_banks();self.economy_tick()
            self.administration_tick()
            self.governance_tick()
            self.institutional_cycle()
            self.operating_business_tick()
            self.ma_company_tick()
            self.fund_obligations_tick()
            self.settle_options();self.savings_accrual()
            self.service_loans();self.player_bank_tick()
            for acct in self.accounts():
                debt=-self.balance('debt:'+acct+':margin')
                if debt>0:
                    residuals=w.setdefault('financing_residuals',{});key='margin:'+acct
                    raw=debt*D(str(max(0,w['macro']['rate']+3)))/D(100*365*24)+D(residuals.get(key,'0'));interest=money(raw);residuals[key]=str(raw-interest)
                    lines={'expense:interest:'+acct:interest,'debt:'+acct+':margin':-interest}
                    if self.state.get('microstructure_enabled'):lines.update({'prime:loan:'+acct:interest,'pnl:prime':-interest})
                    self.post('Margin interest',lines)
                for pos in list(w['positions'].values()):
                    if pos['account']==acct and D(pos['qty'])<0 and pos['symbol'] not in w['options']:
                        residuals=w.setdefault('financing_residuals',{});key='borrow:'+acct+':'+pos['symbol'];ins=self.instrument(pos['symbol'])
                        raw=-D(pos['qty'])*D(ins['price'])*self.fx_rate(ins.get('currency','GBP'))*D(str(ins.get('borrow_fee_apr',3)))/D(100*365*24)+D(residuals.get(key,'0'));borrow=money(raw);residuals[key]=str(raw-borrow)
                        if borrow:
                            lines={'cash:'+acct:-borrow,'expense:interest:'+acct:borrow}
                            if self.state.get('microstructure_enabled'):lines.update({'cash:borrow_desk':borrow,'pnl:borrow_desk':-borrow})
                            self.post('Stock borrow fee',lines)
                if not any(p['account']==acct for p in w['positions'].values()):continue
                m=self.metrics(acct)
                if D(m['equity_gross'])>0 and D(m['liquid_equity'])<D(m['equity_gross'])*D('.25'):
                    self.message('Risk Control','Maintenance margin breach',f"{acct}: equity fell below 25% of gross exposure. Positions are being liquidated against simulated liquidity.")
                    w['credit']=max(300,w['credit']-15) if not acct.startswith('agent_') else w['credit']
                    for order in w['orders']:
                        if order['account']==acct and order['status'] in ('OPEN','PARTIAL'):order['status']='CANCELLED'
                    for pos in list(w['positions'].values()):
                        if pos['account']!=acct:continue
                        o=dict(id=uid(),account=acct,symbol=pos['symbol'],qty=s(abs(D(pos['qty']))),remaining=s(abs(D(pos['qty']))),filled='0.00',side='sell' if D(pos['qty'])>0 else 'buy',type='market',status='OPEN',margin=True,time=w['time'],forced=True)
                        w['orders'].insert(0,o);self.process_order(o,True)
            if w['tick']%24==0:self.daily(rng)
            self.record_history()
            progress=getattr(self,'_progress_callback',None)
            if progress:progress(_+1,hours)
            should_yield=getattr(self,'_clock_should_yield',None)
            if should_yield and should_yield():break
        return {'time':w['time'],'hours':_+1}

    def settle_options(self):
        self.settle_secured_puts()
        for sym,o in list(self.state['options'].items()):
            if datetime.fromisoformat(o['expiry'])>datetime.fromisoformat(self.state['time']):continue
            ins=self.instrument(sym)
            for key,pos in list(self.state['positions'].items()):
                if pos['symbol']!=sym:continue
                amount=money(D(pos['qty'])*D(ins['price'])*100*self.fx_rate(ins.get('currency','GBP')));basis=D(pos['cost']);acct=pos['account']
                self.post('European option cash settlement '+sym,{'cash:'+acct:amount,'inventory:'+acct+':'+sym:-basis,'pnl:'+acct:basis-amount})
                del self.state['positions'][key]
                self.message('Derivatives Clearing','Option settled',f"{sym} settled for £{amount}. These are fictional European cash-settled contracts.")
            for order in self.state['orders']:
                if order['symbol']==sym and order['status'] in ('OPEN','PARTIAL'):order['status']='EXPIRED'

    def fund_fee(self,fund,amount,kind):
        if amount<=0:return
        id=fund['id'];recipient=fund.get('manager','personal')
        self.post('Accrued '+kind+' fee',{'expense:'+kind+':'+id:amount,'debt:'+id+':manager_fees':-amount,'receivable:'+recipient+':'+id:amount,'pnl:'+recipient:-amount})

    def fund_costs(self,fund):
        period='fund_costs:'+fund['id']+':'+str(self.state['tick']//24)
        if self.db.execute('select 1 from scheduled_events where world=? and event=?',(self.state['id'],period)).fetchone():return
        self.db.execute('insert into scheduled_events values(?,?,?)',(self.state['id'],period,self.state['time']))
        if not fund.get('compensation_authorized'):fund['management']=0;fund['performance']=0
        id=fund['id'];nav=D(self.metrics(id)['equity']);fee=money(max(0,nav)*D(str(fund['management']))/D(100*365));self.fund_fee(fund,fee,'management')
        units=D(fund['units'])
        if units>0:
            nav=D(self.metrics(id)['equity']);gain=max(0,nav-D(fund['highwater'])*units);performance=money(gain*D(str(fund['performance']))/100)
            if performance:
                self.fund_fee(fund,performance,'performance');fund['highwater']=str(D(self.metrics(id)['equity'])/units)
        if self.state['tick']%(30*24)==0:
            salary=D(fund.get('monthly_salary','0')) if fund.get('compensation_authorized') else D(0)
            self.fund_fee(fund,salary,'salary')
            expense=D(fund.get('monthly_expenses','0'))
            if expense>0:self.post('Monthly institutional operating cost',{'expense:operations:'+id:expense,'debt:'+id+':operations':-expense})
        if not self.is_frozen(id):
            manager=min(self.available_cash(id),-self.balance('debt:'+id+':manager_fees'))
            recipient=fund.get('manager','personal')
            if manager>0 and not self.is_frozen(recipient):self.post('Manager fee settlement',{'cash:'+id:-manager,'debt:'+id+':manager_fees':manager,'cash:'+recipient:manager,'receivable:'+recipient+':'+id:-manager})
            operations=min(self.available_cash(id),-self.balance('debt:'+id+':operations'))
            if operations>0:self.post('Operating cost settlement',{'cash:'+id:-operations,'debt:'+id+':operations':operations,'cash:operating_suppliers':operations,'pnl:operating_suppliers':-operations})
        overdue=-self.balance('debt:'+id+':operations')
        if overdue>0:self.message('Institution Operations','Unpaid operating obligation',f"{fund['name']} owes £{overdue:,.2f} to service providers. The cost reduces NAV even when cash is unavailable.")

    def daily(self,rng):
        w=self.state
        self.regulatory_daily()
        self.promised_returns()
        self.investor_behaviour()
        for case in w['investigations']:
            if case.get('legal_case'):continue
            if case['status']=='REMEDIATION' and w['tick']-case['remediation_tick']>=7*24:
                case['status']='CLOSED WITH FINDINGS';self.message('Financial Conduct Office','Inquiry closed with findings','Corrected disclosures and seven days of review resolved the preliminary inquiry. Historical claims remain on file.')
        for claim in w['claims']:
            if claim.get('phase2_reporting'):continue
            if claim['status']=='CORRECTED':continue
            if abs(D(claim['gap']))<=max(D(100),abs(D(claim['actual']))*D('.02')):continue
            exposed=sum(1 for f in w['funds'] if f['id']==claim['fund'] for n in w['npcs'] if n['id'] in f['investors'])
            claim['evidence']+=rng.randint(1,8)+exposed*2
            if claim['evidence']>=25 and claim['status']=='PUBLISHED':
                claim['status']='INQUIRY';case=dict(id=uid(),claim=claim['id'],evidence=claim['evidence'],status='INQUIRY',time=w['time']);w['investigations'].append(case)
                self.message('Financial Conduct Office','Document preservation notice','An investor statement differs from recorded net assets. Independent records have prompted a preliminary inquiry. No assets have yet been frozen.')
                self.news('Fund reporting draws an inquiry','Evidence of a discrepancy between investor statements and custodial records has prompted a fictional regulatory inquiry.','INVESTIGATION')
            elif claim['status']=='INQUIRY':
                case=next(c for c in w['investigations'] if c['claim']==claim['id']);case['evidence']=claim['evidence']
                if claim['evidence']>=80:
                    case['status']='ENFORCEMENT';claim['status']='ENFORCEMENT';w.setdefault('frozen_funds',[]).append(claim['fund']);w['reputation']=max(0,w['reputation']-30)
                    self.message('Financial Conduct Office','Institutional assets frozen','Accumulated documentary evidence supports an enforcement order. New institutional trading is restricted. Actual ledger assets remain unchanged.')
                    for n in w['npcs']:n['trust']=max(0,n['trust']-30)
        for f in w['funds']:
            self.fund_costs(f)
            for n in w['npcs']:
                if w.get('_legacy_fixture') and n['id'] in f['investors'] and n['trust']<50 and w['tick']>=f['lock_until'] and D(f['investors'][n['id']])>0:
                    units=money(D(f['investors'][n['id']])*D('.1'))
                    if units>0:
                        try:self.redeem({'fund':f['id'],'investor':n['id'],'units':units});self.message(n['name'],'Redemption executed','Confidence has declined; 10% of my remaining units were redeemed at actual NAV.')
                        except ValueError:self.message(n['name'],'Unmet withdrawal request','Fund liquidity cannot cover my redemption. This unmet obligation reduces confidence.');n['trust']=max(0,n['trust']-2)
        if w['tick']%(24*7)==0 and not w.get('economy_active'):
            macro=w['macro'];growth=round(max(-6,min(6,macro['growth']+rng.gauss(0,.25)-macro['stress']/1000-max(0,macro['rate']-4)*.02)),2)
            inflation=round(max(-2,min(20,macro['inflation']+.05*(growth-2)+rng.gauss(0,.03))),2)
            stress=round(max(0,min(100,macro['stress']+rng.gauss(0,.7)+(macro['rate']-4)*.25-growth*.1)),2)
            rate=macro['rate']
            if inflation>3:rate=min(15,rate+.25)
            elif inflation<1.5:rate=max(0,rate-.25)
            self.macro_change({'growth':growth,'inflation':inflation,'stress':stress,'rate':rate},'Weekly economic bulletin')

    def record_history(self):
        w=self.state;metrics={a:self.metrics(a) for a in self.controlled_accounts()};previous=w['history'][-1] if w['history'] else None
        nav={}
        for a,m in metrics.items():
            last=D(previous.get('accounts',{}).get(a,'0')) if previous else D(0)
            flow=D(m['contributed'])-D(previous.get('contributed',{}).get(a,m['contributed'])) if previous else D(0)
            nav[a]=float(previous.get('nav',{}).get(a,1))*float((D(m['equity'])-flow)/last) if last>0 else 1
        w['history'].append(dict(time=w['time'],tick=w['tick'],accounts={a:m['equity'] for a,m in metrics.items()},contributed={a:m['contributed'] for a,m in metrics.items()},nav=nav));w['history']=w['history'][-1500:]

    def reconcile(self):
        self.validate_treasuries()
        self.validate_institutional_supply()
        self.validate_public_lending()
        self._realised_cache={}
        totals={}
        for (lines,) in self.db.execute('select lines from journal where world=?',(self.state['id'],)):
            j=json.loads(lines)
            if sum((D(v) for v in j.values()),D(0))!=0:raise ValueError('Journal is unbalanced')
            for k,v in j.items():totals[k]=totals.get(k,D(0))+D(v)
        mismatch={k for k in set(totals)|set(self.state['balances']) if totals.get(k,D(0))!=D(self.state['balances'].get(k,'0'))}
        if mismatch:raise ValueError('Ledger mismatch: '+', '.join(sorted(mismatch)))
        for a in self.accounts():
            symbols=set(p['symbol'] for p in self.state['positions'].values() if p['account']==a)|{k.split(':',2)[2] for k in self.state['balances'] if k.startswith('inventory:'+a+':')}
            for sym in symbols:
                if self.balance('inventory:'+a+':'+sym)!=D(self.state['positions'].get(a+':'+sym,{}).get('cost','0')):raise ValueError('Cost basis does not reconcile')
        for loan in self.state['loans']:
            if -self.balance('debt:'+loan['account']+':'+loan['id'])!=D(loan['balance']):raise ValueError('Loan liability does not reconcile')
        for fund in self.state['funds']:
            if sum((D(v) for v in fund['investors'].values()),D(0))!=D(fund['units']):raise ValueError('Investor ownership does not reconcile')
        for office in self.state.get('offices',[]):
            owner=office['entity'];ident=office['id']
            if -self.balance('debt:'+owner+':office_'+ident)!=D(office['unpaid_operations']):raise ValueError('Office operating liabilities do not reconcile')
            if office['mode']=='lease':
                future=D(0) if office['status']=='TERMINATED' else D(office['rent'])*(office['term_months']-min(office['term_months'],office['months_elapsed']))
                if self.balance('rou:'+owner+':'+ident)!=future:raise ValueError('Office right-of-use asset does not reconcile')
                if -self.balance('debt:'+owner+':lease_'+ident)!=future+D(office['unpaid_rent']):raise ValueError('Office rent liability does not reconcile')
        for asset in self.state.get('owned_assets',[]):
            expected=D(0) if asset['status']=='SOLD' else D(asset['purchase_price'])
            if self.balance('asset:'+asset['owner']+':'+asset['id'])!=expected:raise ValueError('Lifestyle asset basis does not reconcile')
            if -self.balance('debt:'+asset['owner']+':lifestyle_'+asset['id'])!=D(asset['unpaid']):raise ValueError('Asset running liability does not reconcile')
        for programme in self.state.get('investment_programmes',[]):
            converted=programme.get('claims_converted',False)
            expected=D(0) if converted else sum((D(r['balance']) for r in programme['investors'].values()),D(0))
            if -self.balance('debt:'+programme['entity']+':programme_'+programme['id'])!=expected:raise ValueError('Programme liabilities do not reconcile')
            for investor,row in programme['investors'].items():
                if self.balance('npc:'+investor+':programme:'+programme['id'])!=(D(0) if converted else D(row['balance'])):raise ValueError('Programme investor receivable does not reconcile')
                if row.get('recovery_claim'):
                    claim=next(c for c in self.state['claims_book'] if c['id']==row['recovery_claim'])
                    if D(row['balance'])!=D(claim['balance']):raise ValueError('Programme recovery claim does not reconcile')
        for event in self.state.get('social_events',[]):
            expected=D(event['cost']) if event['status']=='SCHEDULED' else D(0)
            if self.balance('escrow:'+event['owner']+':'+event['id'])!=expected or -self.balance('debt:activity_escrow:'+event['id'])!=expected:raise ValueError('Activity escrow does not reconcile')
        if self.cash('activity_escrow')!=sum((D(e['cost']) for e in self.state.get('social_events',[]) if e['status']=='SCHEDULED'),D(0)):raise ValueError('Reserved activity cash does not reconcile')
        for employee in self.state.get('employees',[]):
            if -self.balance('debt:'+employee['entity']+':payroll_'+employee['id'])!=D(employee['unpaid']):raise ValueError('Employee payroll liability does not reconcile')
        for claim in self.state.get('claims_book',[]):
            if self.balance('claim:'+claim['creditor']+':'+claim['id'])!=D(claim['balance']) or -self.balance('debt:'+claim['debtor']+':claim_'+claim['id'])!=D(claim['balance']):raise ValueError('Related credit claim does not reconcile')
        # Player-bank fields are a derived corporate view. Payroll, financing
        # and settlement can change the ledger between scheduled refreshes.
        # Validate the journal first, then refresh views before checking banks.
        self.refresh_player_banks()
        for b in self.state['banks']:
            if b.get('entity'):
                entity=b['entity']
                for key,value in [('cash:'+entity,D(b['cash'])),('credit_asset:'+entity+':bank_loans',D(b['loans'])),('allowance:'+entity+':bank_loans',-D(b['allowance'])),('debt:'+entity+':customer_deposits',-D(b['deposits']))]:
                    if self.balance(key)!=value:raise ValueError('Player bank corporate ledger mismatch: '+key)
                deposits=sum((self.balance('savings:'+a+':'+b['id']) for a in self.accounts()),D(0))
                if deposits!=D(b['deposits']):raise ValueError('Customer deposits do not reconcile')
            outstanding=sum((D(l['balance']) for l in self.state['loans'] if l['bank']==b['id']),D(0))
            if outstanding!=D(b['loans']):raise ValueError('Lender assets do not match borrower liabilities')
            if 'bank:'+b['id']+':cash' in self.state['balances']:
                for field,sign in [('cash',1),('loans',1),('deposits',-1),('equity',-1),('allowance',-1)]:
                    if self.balance('bank:'+b['id']+':'+field)!=D(b.get(field,'0'))*sign:raise ValueError('Bank subledger mismatch')
            if D(b['cash'])+D(b['loans'])-D(b.get('allowance','0'))+D(b.get('other_assets','0'))!=D(b['deposits'])+D(b['equity'])+D(b.get('other_liabilities','0')):raise ValueError('Bank balance sheet mismatch')
        if self.state.get('microstructure_enabled'):
            for account in self.accounts():
                if self.balance('prime:loan:'+account)!=-self.balance('debt:'+account+':margin'):raise ValueError('Prime broker asset does not match margin obligation')
            if self.balance('cash:prime')<0:raise ValueError('Prime broker funding liquidity exhausted')
        if self.state.get('fund_system_version'):
            for npc in self.state['npcs']:
                if self.balance('npc:'+npc['id']+':cash')!=D(npc['wealth']):raise ValueError('Investor cash does not reconcile')
            for r in self.state.get('redemptions',[]):
                if -self.balance('debt:'+r['fund']+':redemption:'+r['id'])!=D(r['remaining']):raise ValueError('Redemption obligation does not reconcile')
        return {'balanced':True,'accounts':len(totals),'entries':self.db.execute('select count(*) from journal where world=?',(self.state['id'],)).fetchone()[0]}

    def execute(self,action,p=None,key=None):
        p=p or {}
        with self.lock:
            if action in ('order','batch_orders'):
                for instruction in (p.get('orders',[]) if action=='batch_orders' else [p]):
                    account=instruction.get('account','personal')
                    if instruction.get('actor','').startswith('staff_') and self.state['entities'].get(account,{}).get('kind')=='issuer' and not self.player_controls_entity(account):raise ValueError('Player control is required to submit instructions as corporate staff; existing autonomous mandates continue internally')
            if action=='fed_scenario':return self.fed_scenario(p)
            if action=='load':
                row=self.db.execute('select state from worlds where id=?',(p['id'],)).fetchone()
                if row and (not json.loads(row[0]).get('employee_version') or not json.loads(row[0]).get('stock_research_version') or not json.loads(row[0]).get('wealth_version') or not json.loads(row[0]).get('office_version')):self.backup(self.path.parent/'pre-employee-backups',automatic=True)
            # These UI instructions cannot mutate market/employee history or order books.
            # Share only their untouched collections in the rollback checkpoint.
            read_only=('instruments','events','orders','fills','participants','news','market_starting_snapshot','employee_reports','employee_activity')+ (('history',) if action in ('bank_policy','bank_rules') else ()) if action in ('bank_policy','bank_rules','bank_licence','bank_customer_transfer','loan','savings','repay') else ()
            memo={id(self.state[k]):self.state[k] for k in read_only if self.state and k in self.state}
            if self.state and action in ('order','cancel','modify'):
                # These actions mutate only the traded issuer, orders, books and
                # employee execution counters. Existing history rows are append-only.
                for name in ('events','news','participants','market_starting_snapshot','employee_reports','employee_activity','stock_research','social_events','story_threads'):
                    if name in self.state:memo[id(self.state[name])]=self.state[name]
                target=p.get('symbol')
                if action=='modify':target=next((o['symbol'] for o in self.state['orders'] if o['id']==p.get('id')),None)
                affected={target}
                if target in self.state['options']:affected.add(self.state['options'][target]['underlying'])
                for symbol,instrument in self.state['instruments'].items():
                    if action=='cancel' or (symbol not in affected and instrument.get('security_id')!=target):memo[id(instrument)]=instrument
                for row in self.state['history']:memo[id(row)]=row
            before=copy.deepcopy(self.state,memo)
            ledger_before=getattr(self,'_ledger_generation',0)
            try:
                self.db.execute('BEGIN IMMEDIATE')
                if self.state:self.refresh_player_banks()
                if key and self.state:
                    r=self.db.execute('select result from requests where world=? and key=?',(self.state['id'],key)).fetchone()
                    if r:self.db.rollback();return json.loads(r[0])
                if action=='create':result=self.create(p)
                elif action=='scenario_create':result=self.create_scenario(p)
                elif action=='load':
                    row=self.db.execute('select state from worlds where id=?',(p['id'],)).fetchone()
                    if not row:raise ValueError('Save not found')
                    self.state=json.loads(row[0]);self.reconcile();self.migrate_financial_state()
                    if not self.state.get('_legacy_fixture'):self.install_real_securities(legacy=True)
                    self.migrate_fund_system();self.install_living_market();self.install_governance();self.install_resolution();self.install_economy();self.install_business();self.install_employees();self.install_research();self.install_wealth();self.install_offices();self.install_living_world()
                    result={'loaded':True}
                elif not self.state:raise ValueError('Create a career first')
                elif action in ('security','security_activate'):result=self.activate_security(p)
                elif action=='order':
                    self.authority(self.account(p),'trade',p.get('actor','player'));result=self.order(p)
                elif action=='cancel':
                    o=next(o for o in self.state['orders'] if o['id']==p['id'])
                    self.authority(o['account'],'trade',p.get('actor','player'))
                    if o.get('forced'):raise ValueError('Risk/administrator orders cannot be cancelled or amended')
                    if o['status'] not in ('OPEN','PARTIAL','PAUSED'):raise ValueError('Only working or paused orders may be cancelled')
                    o['status']='CANCELLED';result=o
                elif action=='modify':
                    o=next(o for o in self.state['orders'] if o['id']==p['id'])
                    self.authority(o['account'],'trade',p.get('actor','player'))
                    if o.get('forced'):raise ValueError('Risk/administrator orders cannot be cancelled or amended')
                    if o['status'] not in ('OPEN','PARTIAL'):raise ValueError('Order is no longer working')
                    for k in ('limit','stop','trail'):
                        if k in p:o[k]=s(positive(p[k])) if k=='trail' else str(self.quote_price(self.instrument(o['symbol']),p[k]))
                    from .pretrade import validate
                    validate(self,o,o['account'],self.instrument(o['symbol']),D(o['remaining']),exclude=o['id'])
                    self.process_order(o);result=o
                elif action=='advance':
                    self._advancing=True
                    try:result=self.advance(p.get('hours',1))
                    finally:self._advancing=False
                elif action=='loan':
                    self.authority(self.account(p),'payment',p.get('actor','player'));result=self.loan(p)
                elif action=='repay':
                    obligation=next(l for l in self.state['loans'] if l['id']==p['id']);self.authority(obligation['account'],'payment',p.get('actor','player'))
                    if self.is_frozen(obligation['account']):raise ValueError('Restricted repayment requires administrator or court settlement')
                    result=self.repay(p)
                elif action=='savings':
                    self.authority(self.account(p),'payment',p.get('actor','player'));result=self.savings_transfer(p)
                elif action=='communicate':result=self.communicate(p)
                elif action=='chain':result=self.chain(p)
                elif action=='strategy':result=self.strategy(p)
                elif action=='fund':result=self.fund(p)
                elif action=='fund_class':result=self.fund_class(p)
                elif action=='budget':
                    self.authority(p['fund'],'govern')
                    if self.is_frozen(p['fund']):raise ValueError('Restricted institution cannot commit new expenses')
                    fund=next(f for f in self.state['funds'] if f['id']==p['fund']);amount=money(p['amount'])
                    if amount<0:raise ValueError('Operating budget cannot be negative')
                    fund['monthly_expenses']=s(amount);self.message('Institution Operations','Operating budget updated',fund['name']+' has a monthly service and payroll budget of '+gbp_for_message(amount)+'. Costs accrue every 30 simulation days.');result={'monthly_expenses':s(amount)}
                elif action=='subscribe':result=self.subscribe(p)
                elif action=='redeem':result=self.redemption_request(p) if p.get('queue') else self.redeem(p)
                elif action=='office_start':result=self.office_start(p)
                elif action=='office_end':result=self.office_end(p)
                elif action=='office_relocate':result=self.office_relocate(p)
                elif action=='office_sell':result=self.office_sell(p)
                elif action=='property_lease':result=self.property_lease(p)
                elif action=='property_lease_end':result=self.property_lease_end(p)
                elif action=='fed_initialize':result=self.install_fed()
                elif action=='fed_control':result=self.fed_control(p)
                elif action=='treasury_order':result=self.treasury_order(p)
                elif action=='fed_facility':result=self.fed_facility(p)
                elif action=='fed_reserve':result=self.fed_reserve_transfer(p)
                elif action=='auto_team':result=self.auto_team(p)
                elif action=='staff_policy':result=self.staff_policy(p)
                elif action=='staff_decision':result=self.staff_decision(p)
                elif action=='programme_resolution':result=self.programme_resolution(p)
                elif action=='lifestyle_schedule':result=self.lifestyle_schedule(p)
                elif action=='lifestyle_cancel':result=self.lifestyle_cancel(p)
                elif action=='asset_services':result=self.asset_services(p)
                elif action=='asset_repair':result=self.asset_repair(p)
                elif action=='statement_correct':result=self.statement_correct(p)
                elif action=='case_settlement':result=self.case_settlement(p)
                elif action=='corporate_update':result=self.corporate_update(p)
                elif action=='programme_create':result=self.programme_create(p)
                elif action=='programme_subscribe':result=self.programme_subscribe(p)
                elif action=='programme_redeem':result=self.programme_redeem(p)
                elif action=='insider_approach':result=self.insider_approach(p)
                elif action=='lifestyle_host':result=self.lifestyle_host(p)
                elif action=='staff_research_policy':result=self.staff_research_policy(p)
                elif action=='asset_buy':result=self.asset_buy(p)
                elif action=='asset_sale':result=self.asset_sale(p)
                elif action=='request_analysis':result=self.request_analysis(p)
                elif action=='recruit':result=self.recruit(p)
                elif action=='employment_offer':result=self.employment_offer(p)
                elif action=='employee_hire':result=self.employee_hire(p)
                elif action=='employee_change':result=self.employee_change(p)
                elif action=='employee_task':result=self.employee_task(p)
                elif action=='employee_approve':result=self.employee_approve(p)
                elif action=='operating_plan':result=self.operating_plan(p)
                elif action=='fundraising':result=self.fundraising(p)
                elif action=='bank_licence':result=self.bank_licence(p)
                elif action=='bank_policy':result=self.bank_policy(p)
                elif action=='bank_rules':result=self.bank_rules(p)
                elif action=='bank_customer_transfer':result=self.bank_customer_transfer(p)
                elif action=='financing':result=self.financing(p)
                elif action=='restructure':result=self.restructure(p)
                elif action=='schedule':result=self.schedule_instruction(p)
                elif action=='session_policy':result=self.session_policy(p)
                elif action=='risk_report':result=self.risk_report(p)
                elif action=='batch_orders':
                    orders=p['orders']
                    if not 1<=len(orders)<=50:raise ValueError('Basket must contain1–50 orders')
                    result=[]
                    for instruction in orders:
                        self.authority(self.account(instruction),'trade',instruction.get('actor','player'));order=self.order(instruction)
                        if p.get('all_or_none',True) and order['status']!='FILLED':raise ValueError('Basket did not fill completely; all financial effects rolled back')
                        result.append(order)
                elif action=='network_credit':result=self.network_credit(p)
                elif action=='issuer_event':result=self.issuer_event(p)
                elif action=='economy_policy':result=self.economy_policy(p)
                elif action=='controls':result=self.governance_controls(p)
                elif action=='complaint':result=self.complaint(p)
                elif action=='case_recovery':result=self.case_recovery(p)
                elif action=='case_response':result=self.respond_case(p)
                elif action=='case_review':result=self.review_restrictions(p)
                elif action=='administration':result=self.appoint_administrator(p)
                elif action=='pledge_release':
                    pledge=next(q for q in self.state['pledges'] if q['id']==p['id']);self.authority(pledge['owner'],'govern');result=self.release_pledge(p)
                elif action=='entity_create':result=self.entity_create(p)
                elif action=='entity_policy':result=self.entity_policy(p)
                elif action=='corporate_proposal':result=self.corporate_proposal(p)
                elif action=='corporate_decision':result=self.corporate_decision(p)
                elif action=='corporate_officer':result=self.corporate_officer(p)
                elif action=='pe_commit':result=self.pe_commit(p)
                elif action=='pe_call':result=self.pe_call(p)
                elif action=='pe_call_process':result=self.pe_call_process(p)
                elif action=='business_start':result=self.business_start(p)
                elif action=='ma_market':result=self.ma_market(p)
                elif action=='ma_profile':result=self.ma_profile(p)
                elif action=='ma_offer':result=self.ma_offer(p)
                elif action=='ma_negotiate':result=self.ma_negotiate(p)
                elif action=='ma_diligence':result=self.ma_diligence(p)
                elif action=='ma_approve':result=self.ma_approve(p)
                elif action=='ma_close':result=self.ma_close(p)
                elif action=='ma_withdraw':result=self.ma_withdraw(p)
                elif action=='public_tender':result=self.public_tender(p)
                elif action=='public_resolution':result=self.public_resolution(p)
                elif action=='company_operate':result=self.company_operate(p)
                elif action=='ma_manage':result=self.ma_manage(p)
                elif action=='ma_expand':result=self.ma_expand(p)
                elif action=='ma_dividend':result=self.ma_dividend(p)
                elif action=='ma_exit':result=self.ma_exit(p)
                elif action=='ma_exit_accept':result=self.ma_exit_accept(p)
                elif action=='consolidated_statement':result=self.consolidated_statement(p)
                elif action=='fund_register':result=self.fund_register(p)
                elif action=='fund_contribute':result=self.fund_contribute(p)
                elif action=='execution_resume':result=self.execution_resume(p)
                elif action=='block_quote':result=self.block_quote(p)
                elif action=='block_accept':result=self.block_accept(p)
                elif action=='lifecycle_preview':result=self.lifecycle_preview(p)
                elif action=='lifecycle_propose':result=self.lifecycle_propose(p)
                elif action=='lifecycle_approve':result=self.lifecycle_approve(p)
                elif action=='lifecycle_execute':result=self.lifecycle_execute(p)
                elif action=='lifecycle_counteroffer':result=self.lifecycle_counteroffer(p)
                elif action=='lifecycle_cancel':result=self.lifecycle_cancel(p)
                elif action=='related':result=self.related_instruction(p)
                elif action=='related_approve':result=self.approve_related(p)
                elif action=='claim_repay':result=self.repay_claim(p)
                elif action=='claim_impair':result=self.impairment(p)
                elif action=='fund_terms':result=self.fund_terms(p)
                elif action=='verify_nav':result=self.verified_statement(p)
                elif action=='investor_response':result=self.investor_response(p)
                elif action=='bank_default':result=self.bank_credit_event(p)
                elif action=='market_event':result=self.market_event(p)
                elif action=='risk_policy':
                    acct=self.account(p);self.authority(acct,'govern');leverage=D(str(p['max_leverage']));concentration=D(str(p['single_name_pct']))
                    if not leverage.is_finite() or not concentration.is_finite() or not D('.1')<=leverage<=2 or not 1<=concentration<=200:raise ValueError('Leverage 0.1–2; single-name limit 1–200%')
                    result={'max_leverage':str(leverage),'single_name_pct':str(concentration)};self.state.setdefault('account_limits',{})[acct]=result;self.audit('risk_policy',{'account':acct,**result})
                elif action=='market_preferences':
                    from .markets import normalize_filters
                    result=normalize_filters(p.get('filters',{}));self.state['market_explorer_preferences']=result
                elif action=='market_view':
                    symbol=p['symbol']
                    if symbol not in self.state['instruments'] and not any(r['symbol']==symbol for r in catalogue()):raise ValueError('Unknown supported security')
                    recent=self.state.setdefault('recently_viewed',[]);recent[:]=[symbol]+[x for x in recent if x!=symbol][:29];result={'symbols':recent}
                elif action=='watchlist':
                    if p['symbol'] not in self.state['instruments'] and not any(r['symbol']==p['symbol'] for r in catalogue()):raise ValueError('Unknown supported security')
                    items=self.state.setdefault('watchlist',[])
                    if p['symbol'] in items:items.remove(p['symbol'])
                    else:items.append(p['symbol'])
                    result={'symbols':items}
                elif action=='price_alert':
                    self.instrument(p['symbol']);level=positive(p['price']);direction=p.get('direction','above')
                    if direction not in ('above','below'):raise ValueError('Invalid alert direction')
                    result=dict(id=uid(),symbol=p['symbol'],price=str(level),direction=direction,status='ARMED');self.state['alerts'].append(result)
                elif action=='fund_policy':result=self.fund_policy(p)
                elif action=='redemption_settle':self.settle_redemptions(p.get('fund'));result={'processed':True}
                elif action=='report':result=self.report(p)
                elif action=='corporate':
                    if p.get('kind')=='split' and any(o['underlying']==p.get('symbol') and datetime.fromisoformat(o['expiry'])>datetime.fromisoformat(self.state['time']) for o in self.state['options'].values()):raise ValueError('Split blocked while option contracts remain outstanding')
                    result=self.corporate(p)
                elif action=='admin':result=self.admin(p)
                elif action=='control':
                    if 'paused' in p:self.state['paused']=bool(p['paused'])
                    if 'speed' in p:
                        speed=int(p['speed'])
                        if speed not in (1,6,24):raise ValueError('Choose 1, 6, or 24 hours per cycle')
                        self.state['speed']=speed
                    result={'paused':self.state['paused'],'speed':self.state['speed']}
                elif action=='statement':result=self.statement(self.account(p),p.get('offset',0),p.get('limit',100))
                elif action=='compensation':result=self.compensation(p)
                elif action=='reconcile':result=self.reconcile()
                else:raise ValueError('Unknown action')
                if (action not in ('order','modify') or getattr(self,'_ledger_generation',0)!=ledger_before) and action not in ('create','load','advance','admin','chain','cancel','reconcile','control','statement','redemption_settle','risk_report','lifecycle_preview','consolidated_statement','ma_market','ma_profile','market_preferences','market_view','watchlist','bank_policy','bank_rules'):self.record_history()
                self.install_empire_a();self.install_public_ownership();self.public_control_refresh();self.refresh_player_banks()
                if self.state.get('fed'):self.fed_facility_tick()
                self.persist()
                if key:self.db.execute('insert into requests values(?,?,?)',(self.state['id'],key,json.dumps(result)))
                self.db.commit();self.schedule_checkpoint();return result
            except Exception:
                self.db.rollback();self.state=before;raise

    def admin(self,p):
        op=p.get('op','cash');acct=self.account(p)
        if op=='cash':
            amount=money(p['amount'])
            if amount<0 and self.available_cash(acct)+amount<0:raise ValueError('Administrative removal exceeds unrestricted cash')
            if acct!='personal':
                fund=next((f for f in self.state['funds'] if f['id']==acct),self.state.get('entities',{}).get(acct));ownership=fund.get('investors',fund.get('owners',{}));nav=D(self.metrics(acct)['equity']);units=D(fund['units'])
                price=nav/units if units>0 and nav>0 else D(1)
                change=(amount/price).quantize(D('.00000001'))
                if change<0 and -change>D(ownership.get('admin','0')):raise ValueError('Fund admin withdrawals are limited to administrative ownership; redeem investor units explicitly')
                fund['units']=str(units+change);ownership['admin']=str(D(ownership.get('admin','0'))+change)
            self.post('ADMIN capital adjustment',{'cash:'+acct:amount,'equity:'+acct:-amount})
        elif op=='price':
            self.mark(p['symbol'],p['price'])
        elif op=='halt':
            ins=self.instrument(p['symbol']);status=p.get('status')
            if status not in ('OPEN','HALTED'):raise ValueError('Choose OPEN or HALTED')
            ins['status']=status
        elif op=='macro':
            if self.state.get('fed') and 'rate' in p:
                target=float(p['rate'])
                if not .25<=target<=15 or abs(target*4-round(target*4))>1e-8:raise ValueError('Federal funds target uses quarter-point steps from 0.25 to 15%')
                self.fed_meeting({'id':'ADMIN-'+str(self.state['tick'])+'-'+str(len(self.state['fed']['meetings'])),'time':self.state['time']},override=target)
                self.macro_change({k:v for k,v in p.items() if k!='rate'},'World administration economic scenario')
            else:self.macro_change(p,'Policy and credit conditions reset')
        elif op=='scenario':
            scenario=p.get('scenario');macro=self.state['macro']
            if scenario=='rate_hike':settings={'rate':min(100,macro['rate']+2),'growth':max(-10,macro['growth']-.5)}
            elif scenario=='credit_crunch':settings={'stress':min(100,macro['stress']+40),'growth':max(-10,macro['growth']-2),'inflation':max(-10,macro['inflation']-.3)}
            elif scenario=='recovery':settings={'stress':max(0,macro['stress']-30),'growth':min(10,macro['growth']+1.5),'rate':max(0,macro['rate']-.5)}
            else:raise ValueError('Unknown economic scenario')
            self.macro_change(settings,{'rate_hike':'Central bank announces a two-point rate increase','credit_crunch':'Credit conditions tighten across the fictional economy','recovery':'Credit confidence begins to recover'}[scenario])
        elif op=='reputation':self.state['reputation']=max(0,min(100,int(p['value'])))
        elif op=='trust':
            npc=next(n for n in self.state['npcs'] if n['id']==p['id']);npc['trust']=max(0,min(100,int(p['value'])))
        elif op=='career':
            if p['career'] not in CAREERS:raise ValueError('Unknown career')
            self.state['career']=p['career']
        else:raise ValueError('Unknown administrative operation')
        self.audit(op,p);self.record_history();return {'applied':True}

    def banking_snapshot(self):
        """Version-consistent banking projection, merged with the client's full world."""
        with self.lock:
            if not self.state:return self.snapshot()
            self.refresh_player_banks()
            keys=('id','name','time','tick','paused','speed','banks','loans','npcs','entities','balances','related_transactions','claims_book','pledges','correspondence','messages','history','credit','macro','reputation','customer_identities')
            w=copy.deepcopy({k:self.state[k] for k in keys if k in self.state})
            w['player_banks']=copy.deepcopy(self.player_bank_views())
            w['market_marks']={symbol:{k:ins[k] for k in ('price','previous','status','timestamp') if k in ins} for symbol,ins in self.state['instruments'].items()}
            w['metrics']={a:self.metrics(a) for a in self.accounts()}
            w['restrictions']={a:self.restriction_summary(a) for a in self.controlled_accounts()}
            w['journal']=[dict(id=r[0],time=r[1],description=r[2],lines=json.loads(r[3])) for r in self.db.execute('select id,time,description,lines from journal not indexed where world=? order by rowid desc limit 100',(w['id'],))]
            w['audit']=[dict(time=r[0],action=r[1],detail=json.loads(r[2])) for r in self.db.execute('select time,action,detail from audit not indexed where world=? order by rowid desc limit 100',(w['id'],))]
            saves=[dict(id=r[0],name=r[1],updated=r[2]) for r in self.db.execute('select id,name,updated from worlds order by updated desc')]
            return {'world':w,'saves':saves,'_partial':True}

    def snapshot(self,view='full'):
        # One locked projection only: never retain derived values across commands.
        with self.lock:
            self._snapshot_metrics_cache={};self._projection_ledger={}
            try:return self._snapshot_uncached(view)
            finally:self._snapshot_metrics_cache=None;self._projection_ledger=None

    def _snapshot_uncached(self,view='full'):
        if view=='banking':return self.banking_snapshot()
        if view=='trading':return self.trading_snapshot()
        with self.lock:
            saves=[dict(id=r[0],name=r[1],updated=r[2]) for r in self.db.execute('select id,name,updated from worlds order by updated desc')]
            if not self.state:return {'world':None,'saves':saves,'careers':CAREERS,'references':self.references.snapshot(),'catalogue':catalogue(),'equity_references':self.equity_references.snapshot()}
            self.refresh_player_banks()
            w=copy.deepcopy(self.state)
            if w.get('fed'):w['fed']=self.fed_public_view()
            w['events']=[e for e in w.get('events',[]) if e['published']]
            w['executive']=copy.deepcopy(self.executive_view())
            for asset in w.get('owned_assets',[]):asset['profile']=self.asset_profile(asset)
            w['player_banks']=self.player_bank_views()
            from .offices import OFFICES
            w['office_catalogue']=copy.deepcopy(OFFICES)
            w['office_capacity']={a:self.office_capacity(a) for a in self.controlled_accounts()}
            from .wealth import CATALOGUE
            w['lifestyle_catalogue']=copy.deepcopy(CATALOGUE)
            for rental in w.get('property_contracts',[]):
                rental['paid']=s(sum((D(p['amount']) for c in w['claims_book'] if c['id'] in rental['claims'] for p in c['payments']),D(0)))
            w['stock_research']=self.research_views()
            w['investor_relations']=self.investor_relations_views()
            w['metrics']={a:self.metrics(a) for a in self.accounts()}
            w['corporate']=self.corporate_views(w['metrics'])
            w['company_market']=self.ma_market()+self.public_management_rows()
            w['workforce']={a:self.workforce_view(a) for a in self.controlled_accounts()}
            w['public_companies']=self.public_company_registry()
            for bid in w.get('public_tenders',[]):
                if bid['status']=='OPEN':bid['shareholder_blocks']=self.public_tender_shareholders(bid)
            w['entity_capabilities']=self.entity_capabilities()
            w['institutional_economy']=self.institutional_views(w['metrics'])
            for investor in w['npcs']:investor['aum']=self.investor_aum(investor)
            books=self.depth_map()
            w['order_diagnostics']={o['id']:self.order_diagnostics(o,w['metrics'][o['account']]) for o in self.state['orders'] if o['status'] in ('OPEN','PARTIAL') and o['account'] in self.controlled_accounts()}
            for instrument in w['instruments'].values():
                instrument['borrow_remaining']=str(max(D(0),D(instrument.get('borrow_available',D(instrument['liquidity'])*20))-sum((abs(D(p['qty'])) for p in w['positions'].values() if p['symbol']==instrument['symbol'] and D(p['qty'])<0),D(0))))
                instrument['depth']=books.get(instrument['symbol'],[]) if w.get('microstructure_enabled') and instrument['symbol'] in w['market_symbols'] else depth(instrument,w['tick'])
                instrument['chart_tick']=w['tick'];instrument['chart_time']=w['time']
            from .markets import project_market,execution_stats
            market_stats=execution_stats(self.db,self.state)
            w['market_explorer']=project_market(w,catalogue(),{s:v['volume'] for s,v in market_stats.items()},market_stats)
            for pos in w['positions'].values():
                ins=self.instrument(pos['symbol']);pos['price']=ins['price'];pos['currency']=ins.get('currency','GBP');pos['value']=s(D(pos['qty'])*D(ins['price'])*D(ins.get('multiplier',1))*self.fx_rate(ins.get('currency','GBP')));pos['pnl']=s(D(pos['value'])-D(pos['cost']))
            w['statements']={a:self.statement(a,limit=100) for a in self.controlled_accounts()}
            w['session_open']=self.session_open()
            w['restrictions']={a:self.restriction_summary(a) for a in self.controlled_accounts()}
            w['option_quotes']={sym:self.option_view(sym) for sym in w['options']}
            for symbol,quote in w['option_quotes'].items():
                stored=w['options'][symbol];used=D(stored.get('liquidity_used','0')) if stored.get('liquidity_tick')==w['tick'] else D(0);quote.setdefault('available_liquidity',str(max(D(0),D(quote['liquidity'])-used)))
            w['journal']=[dict(id=r[0],time=r[1],description=r[2],lines=json.loads(r[3])) for r in self.db.execute('select id,time,description,lines from journal not indexed where world=? order by rowid desc limit 100',(w['id'],))]
            w['audit']=[dict(time=r[0],action=r[1],detail=json.loads(r[2])) for r in self.db.execute('select time,action,detail from audit not indexed where world=? order by rowid desc limit 100',(w['id'],))]
            return {'world':w,'saves':saves,'careers':CAREERS,'references':self.references.snapshot(),'catalogue':catalogue(),'equity_references':self.equity_references.snapshot()}

    def backup(self,directory,automatic=False):
        runtime=runtime_directory()
        if runtime.resolve()!=runtime or not Path(directory).resolve().is_relative_to(runtime):
            raise ValueError('Development backups must stay inside the development runtime directory')
        from .storage import AUTOMATIC_BACKUP_LIMIT,prune_backups
        if automatic and self.path.stat().st_size>AUTOMATIC_BACKUP_LIMIT:
            __import__('logging').getLogger(__name__).info('Skipped oversized disposable development migration backup: %s',self.path)
            return None
        with self.lock:
            directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
            target=directory/('vantage-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uid()+'.sqlite')
            out=sqlite3.connect(target);self.db.backup(out);out.close()
            prune_backups(directory)
            return target.name

    def restore(self,directory,name,confirmation):
        if confirmation!='RESTORE':raise ValueError('Restore confirmation required')
        if Path(name).name!=name or not name.startswith('vantage-') or not name.endswith('.sqlite'):raise ValueError('Invalid backup name')
        source=Path(directory)/name
        if not source.is_file():raise ValueError('Backup not found')
        with self.lock:
            c=sqlite3.connect(f'file:{source}?mode=ro',uri=True)
            try:
                if c.execute('pragma integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')
                active=c.execute("select value from metadata where key='active'").fetchone()
                if not active:raise ValueError('Backup has no active world')
                state=json.loads(c.execute('select state from worlds where id=?',active).fetchone()[0])
                probe=object.__new__(Engine);probe.db=c;probe.state=state;probe.reconcile()
                self.backup(directory);c.backup(self.db);self.state=state
                self.db.executescript('CREATE TABLE IF NOT EXISTS evidence_records(id TEXT PRIMARY KEY,world TEXT NOT NULL,data TEXT NOT NULL);CREATE TABLE IF NOT EXISTS order_archive(id TEXT PRIMARY KEY,world TEXT NOT NULL,data TEXT NOT NULL);CREATE TABLE IF NOT EXISTS executions(id TEXT PRIMARY KEY,world TEXT NOT NULL,data TEXT NOT NULL);CREATE INDEX IF NOT EXISTS execution_world ON executions(world);CREATE TABLE IF NOT EXISTS scheduled_events(world TEXT NOT NULL,event TEXT NOT NULL,time TEXT NOT NULL,PRIMARY KEY(world,event));')
                with self.db:
                    restored_original=copy.deepcopy(self.state)
                    self.migrate_financial_state()
                    if not self.state.get('_legacy_fixture'):self.install_real_securities(legacy=True)
                    self.migrate_fund_system();self.install_living_market();self.install_governance();self.install_resolution();self.install_economy();self.install_business();self.install_employees();self.install_research();self.install_wealth();self.install_offices();self.install_living_world()
                    self.reconcile()
                    if self.state!=restored_original:self.persist()
            finally:c.close()
            return {'restored':True}

    def schedule_checkpoint(self):
        """Committed WAL is durable; a separate connection moves pages to the main file."""
        worker=getattr(self,'_checkpoint_thread',None)
        if worker and worker.is_alive():return
        wal=Path(str(self.path)+'-wal')
        try:
            if wal.stat().st_size<32*1024*1024:return
        except FileNotFoundError:return
        def checkpoint():
            connection=None
            try:
                connection=sqlite3.connect(self.path,timeout=0)
                connection.execute('pragma busy_timeout=0')
                connection.execute('pragma wal_checkpoint(PASSIVE)').fetchone()
            except sqlite3.Error:
                # A concurrent writer/reader can postpone maintenance; committed state stays in WAL.
                pass
            finally:
                if connection is not None:connection.close()
        self._checkpoint_thread=threading.Thread(target=checkpoint,name='vantage-checkpoint',daemon=True)
        self._checkpoint_thread.start()

    def close(self):
        worker=getattr(self,'_checkpoint_thread',None)
        if worker and worker is not threading.current_thread():worker.join()
        self.db.close()
        if not self.instance_lock.closed:fcntl.flock(self.instance_lock.fileno(),fcntl.LOCK_UN);self.instance_lock.close()
