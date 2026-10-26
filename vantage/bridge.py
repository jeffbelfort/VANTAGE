"""Qt WebChannel transport: works without loopback socket permission."""
import json,logging,sqlite3,threading,os
from pathlib import Path
from PyQt6.QtCore import QObject,pyqtSlot,pyqtSignal,QRunnable,QThreadPool,QTimer
from .engine import Engine
ROOT=Path(__file__).resolve().parent.parent

class Job(QRunnable):
 def __init__(self,callback):super().__init__();self.callback=callback
 def run(self):self.callback()

class Bridge(QObject):
 response=pyqtSignal(str,str)
 progress=pyqtSignal(str)
 def __init__(self,path=None,parent=None):
  super().__init__(parent);self.engine=Engine(path or os.environ.get('VANTAGE_DATABASE') or ROOT/'runtime'/'vantage.sqlite');self.backup_directory=ROOT/'backups' if self.engine.path.parent==ROOT/'data' else self.engine.path.parent/'backups';self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1);self.closing=False;self._queue_lock=threading.Lock();self._state_waiters={};self._state_pending=set();self._tick_pending=False;self._clock_yield=threading.Event();self._clock_remaining=0;self._clock_world=None
  self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.tick);self.timer.start()
 def tick(self):
  if not self.engine.state or self.engine.state['paused'] or self.closing:return
  with self._queue_lock:
   if self._tick_pending:return
   self._tick_pending=True;self._clock_remaining=self.engine.state['speed'];self._clock_world=self.engine.state['id']
  self.pool.start(Job(self._run_tick))
 def _run_tick(self):
  again=False
  try:
   e=self.engine
   if not self.closing and e.state and not e.state['paused'] and e.state['id']==self._clock_world:
    self._clock_yield.clear();e._clock_should_yield=self._clock_yield.is_set
    result=e.execute('advance',{'hours':self._clock_remaining})
    self._clock_remaining-=result['hours'];again=self._clock_remaining>0
  except Exception:
   logging.exception('Clock paused');self.engine.execute('control',{'paused':True})
  finally:
   self.engine._clock_should_yield=None
   with self._queue_lock:
    if again and not self.closing:self.pool.start(Job(self._run_tick),-2)
    else:self._tick_pending=False;self._clock_remaining=0
 def advance(self):
  try:
   with self.engine.lock:
    if self.engine.state and not self.engine.state['paused']:self.engine.execute('advance',{'hours':self.engine.state['speed']})
  except Exception:logging.exception('Clock paused');self.engine.execute('control',{'paused':True})
 @pyqtSlot(str,str)
 def request(self,id,encoded):
  if self.closing:return
  try:req=json.loads(encoded)
  except (ValueError,TypeError):self.response.emit(id,json.dumps({'ok':False,'data':{'error':'Invalid local request'}}));return
  self._clock_yield.set()
  if req.get('method','GET')=='GET' and req.get('path')=='/api/state':
   view=req.get('view') if req.get('view') in ('banking','trading') else 'full'
   with self._queue_lock:
    if sum(len(v) for v in self._state_waiters.values())>=256:
     self.response.emit(id,json.dumps({'ok':False,'data':{'error':'State refresh already in progress'}}));return
    self._state_waiters.setdefault(view,[]).append(id)
    if view in self._state_pending:return
    self._state_pending.add(view)
   self.pool.start(Job(lambda:self._reply_state(view)),-1)
  else:self.pool.start(Job(lambda:self.process(id,encoded)),1)
 def _reply_state(self,view='full'):
  try:
   encoded=self.process(None,json.dumps({'path':'/api/state','method':'GET','view':view})) if not self.closing else json.dumps({'ok':False,'data':{'error':'Game is closing'}})
  except Exception:
   logging.exception('State refresh failed');encoded=json.dumps({'ok':False,'data':{'error':'State refresh failed; saved progress is retained'}})
  with self._queue_lock:
   waiters=self._state_waiters.pop(view,[]);self._state_pending.discard(view)
  for id in waiters:self.response.emit(id,encoded)
 def process(self,id,encoded):
  try:
   req=json.loads(encoded);path=req['path'];action=path.removeprefix('/api/');p=req.get('body',{});e=self.engine
   if req.get('method','GET')=='GET':
    if action=='state':result=e.snapshot(view=req.get('view') if req.get('view') in ('banking','trading') else 'full')
    elif action=='health':result={'ok':True,'version':'0.7.0-phase-a','storage':str(e.path)}
    elif action=='backups':result={'files':[f.name for f in sorted(self.backup_directory.glob('vantage-*.sqlite'),reverse=True)]}
    else:raise ValueError('Unknown local request')
   else:
    if action=='equity_refresh':value=e.equity_references.refresh(str(p['symbol']))
    elif action=='equity_import':value=e.equity_references.import_quote(p)
    elif action=='reference_refresh':value=e.references.refresh()
    elif action=='reference_import':value=e.references.import_xml(str(p['xml']))
    elif action=='backup':value={'file':e.backup(self.backup_directory)}
    elif action=='restore':value=e.restore(self.backup_directory,str(p['file']),p.get('confirm'))
    else:
     if action=='advance' and hasattr(self,'progress'):e._progress_callback=lambda step,total:self.progress.emit('Processing simulation hour '+str(step)+' / '+str(total)+'; accounting not yet committed')
     try:value=e.execute(action,p,req.get('key'))
     finally:
      if action=='advance':e._progress_callback=None
    result={'result':value,'state':e.snapshot(view='trading' if req.get('view')=='trading' and action in ('order','cancel','modify','control','advance','chain','employee_task','employee_approve') else 'banking' if req.get('view')=='banking' and action in ('bank_policy','bank_rules','bank_licence','bank_customer_transfer','loan','savings','repay','advance') else 'full')}
   response={'ok':True,'data':result}
  except (ValueError,KeyError,StopIteration,TypeError) as exc:response={'ok':False,'data':{'error':str(exc) or 'Record not found'}}
  except sqlite3.Error as exc:
   logging.exception('Database request failed')
   message='Disk is full. Free space on the save drive, then restart VANTAGE. The failed transaction was rolled back.' if getattr(exc,'sqlite_errorcode',None)==sqlite3.SQLITE_FULL else 'Database action failed: '+str(exc)
   response={'ok':False,'data':{'error':message}}
  except Exception:
   logging.exception('Desktop request failed');log=Path(os.environ.get('VANTAGE_LOG_DIR') or ROOT/'runtime'/'logs')/'vantage.log';response={'ok':False,'data':{'error':'Action failed. See '+str(log)+' for details.'}}
  encoded=json.dumps(response,separators=(',',':'),ensure_ascii=False)
  if id is not None:self.response.emit(id,encoded)
  return encoded
 def close(self):
  # Actions commit with FULL durability. Closing must not create a full save
  # copy and exhaust the same drive needed for the next transaction. Explicit
  # backup/restore actions remain available.
  self.closing=True;self.timer.stop();self.pool.waitForDone();self.engine.close()
