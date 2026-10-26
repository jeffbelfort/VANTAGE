"""Synthetic-profile frozen-engine checks and actual WebEngine launch monitoring."""
import json
import os
from pathlib import Path
import socket
from .paths import prepare_release, runtime_directory
from .engine import Engine

def engine_checks():
    prepare_release()
    path=runtime_directory()/'vantage.sqlite'
    assert not path.exists(), 'Only run this test with a new disposable XDG_DATA_HOME / LOCALAPPDATA'
    e=Engine(path)
    assert e.state is None
    try: Engine(path)
    except ValueError: pass
    else: raise AssertionError('Concurrent save access was accepted')
    # Prove the normal packaged profile cannot escape into an existing developer save.
    try: Engine(Path.cwd()/'forbidden.sqlite')
    except ValueError: pass
    else: raise AssertionError('Save location escaped profile')
    e.execute('create',{'_legacy_fixture':True,'name':'Disposable Release Test','career':'Professional Trader'})
    e.execute('admin',{'op':'price','symbol':'ALTN','price':100})
    e.execute('order',{'side':'buy','qty':10,'symbol':'ALTN'})
    e.execute('admin',{'op':'price','symbol':'ALTN','price':110})
    e.execute('order',{'side':'sell','qty':10,'symbol':'ALTN'})
    assert float(e.metrics()['realised'])>0
    order=e.execute('order',{'side':'buy','qty':1,'symbol':'ALTN','type':'limit','limit':90})
    assert order['status']=='OPEN'
    e.execute('modify',{'id':order['id'],'limit':120})
    assert any(o['id']==order['id'] and o['status']=='FILLED' for o in e.state['orders'])
    chain=e.execute('chain',{'symbol':'ALTN','days':7})
    e.execute('order',{'side':'buy','qty':1,'symbol':chain[4]['call']['symbol']})
    fund=e.execute('fund',{'amount':10000,'name':'Disposable Fund'})
    e.execute('subscribe',{'fund':fund['id'],'investor':'lp0','amount':10000})
    loan=e.execute('loan',{'amount':1000,'months':12});assert loan['approved']
    e.execute('repay',{'id':e.state['loans'][0]['id'],'amount':100})
    e.execute('advance',{'hours':1});e.reconcile()
    backup=e.backup(path.parent/'backups');assert backup
    before=e.snapshot();e.close()
    e=Engine(path);assert e.snapshot()==before;e.reconcile()
    # Enforce no network availability for simulation actions.
    old=socket.create_connection
    socket.create_connection=lambda *a,**kw: (_ for _ in ()).throw(OSError('offline'))
    try:e.execute('advance',{'hours':1});e.reconcile()
    finally:socket.create_connection=old
    e.execute('create',{'career':'Professional Trader','capital':2100000000,'_static_market':True,'_ai_corporate_economy':True})
    acquisition_fund=e.execute('fund',{'name':'Disposable Acquisition Fund','amount':2000000000,'fund_type':'private_equity'})
    e.execute('controls',{'entity':acquisition_fund['id'],'level':1})
    value=float(e.ma_valuation('private_0')['equity_value'])
    offer=e.execute('ma_offer',{'buyer':acquisition_fund['id'],'entity':'private_0','percent':100,'amount':value*1.1,'debt':0})
    for action in ('ma_diligence','ma_approve','ma_close'):
        e.execute(action,{'id':offer['id']})
    assert e.state['entities']['private_0']['controlled']
    e.reconcile()
    e.close()
    return {'passed':True,'acquisition':True,'single_instance_lock':True,'fresh_profile':True,'trades':True,'limit_execution':True,'options':True,'funds':True,'lending':True,'backup':True,'persistence':True,'offline':True,'reconciliation':True}

def monitor_webengine(app, view, bridge):
    """Exercise the production page, its JavaScript bundle and Qt WebChannel."""
    from PyQt6.QtCore import QTimer
    target = Path(os.environ['VANTAGE_VALIDATION_REPORT'])
    completed = False
    attempts = 0
    timer = QTimer(view)
    def finish(passed, **details):
        nonlocal completed
        if completed:
            return
        completed = True
        timer.stop()
        target.write_text(json.dumps({'passed':passed, 'webengine':True, **details}, indent=2), encoding='utf-8')
        view.window().close()
        app.exit(0 if passed else 1)
    def evaluate():
        nonlocal attempts
        attempts += 1
        if attempts > 60:
            return finish(False, error='React onboarding / WebChannel failed to initialise in 60 seconds')
        def got_state(value):
            if completed or not isinstance(value, dict):
                return
            if value.get('ready'):
                finish(bridge.engine.state is None and view.window().isVisible(),
                       onboarding=True, webchannel=value.get('bridge'), fresh_profile=bridge.engine.state is None,
                       qt_version=__import__('PyQt6.QtCore',fromlist=['QT_VERSION_STR']).QT_VERSION_STR)
        view.page().runJavaScript("({ready:!!document.querySelector('.onboarding form') && !!window.qt && document.querySelector('.onboarding img').naturalWidth>0 && document.styleSheets.length>0, bridge:!!window.qt, text:document.body.innerText.slice(0,100)})", got_state)
    timer.timeout.connect(evaluate)
    timer.start(1000)
    # Retain the callback/timer for the full renderer lifecycle.
    view._release_smoke_timer = timer
