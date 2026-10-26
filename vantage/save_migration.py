"""Offline, fail-closed stable-save import. No SQLite connection ever opens source.

The source DB and WAL are captured under the game's read-only instance lock and
verified byte-for-byte stable. SQLite's backup API then reads that PRIVATE capture
(including committed WAL pages) into a portable snapshot. This avoids SQLite's
otherwise surprising creation/modification of source -wal/-shm files in mode=ro.
"""
from __future__ import annotations
from . import filelock as fcntl
import argparse, contextlib, copy, hashlib, json, os, shutil, sqlite3
import sys, threading, uuid, subprocess
from datetime import datetime, timezone
from pathlib import Path
from .engine import Engine
from .schema import ensure_schema

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'runtime'
STABLE = Path('/media/owner/SSD1/stock/data/test-build/vantage.sqlite')
DESTINATION = RUNTIME / 'vantage.sqlite'
CONFIRM_IMPORT = 'IMPORT-STABLE'
CONFIRM_ROLLBACK = 'RESTORE-DEVELOPMENT'
PENDING = '.vantage-import-pending.json'
REFERENCE_FILES = ('reference-cache.json', 'equity-reference-cache.json')
BASE_VERSIONS = {'financial_version':2,'fund_system_version':1,'market_system_version':1,
 'governance_version':1,'resolution_version':1,'economy_version':1,'business_version':1}
WORLD_MIGRATIONS = (
 ('employee_version',1,'install_employees'),
 ('stock_research_version',1,'install_research'),
 ('wealth_version',1,'install_wealth'),
 ('office_version',1,'install_offices'),
)

class MigrationError(ValueError): pass
class SaveBusy(MigrationError): pass
class DuplicateImport(MigrationError): pass

def utc(): return datetime.now(timezone.utc).isoformat()
def quote(name): return '"'+name.replace('"','""')+'"'
def inside_runtime(path):
 path=Path(path)
 if RUNTIME.resolve()!=RUNTIME or not path.resolve().is_relative_to(RUNTIME):
  raise MigrationError('Migration destination, reports and backups must stay inside development runtime')
 return path.resolve()
def fsync_dir(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def write_json(path,data):
 path=Path(path);temp=path.with_name(path.name+'.tmp')
 with temp.open('w') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(temp,path);fsync_dir(path.parent)
def read_fd(path):
 # O_NOATIME where supported, so even a byte capture need not update source atime.
 try:return os.fdopen(os.open(path,os.O_RDONLY|getattr(os,'O_NOATIME',0)),'rb')
 except PermissionError:return open(path,'rb')
def sha_file(path):
 h=hashlib.sha256()
 with read_fd(path) as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def source_files(path):
 result={}
 for name in ('','-wal','-shm'):
  p=Path(str(path)+name)
  if p.exists():
   s=p.stat();result[name]={'size':s.st_size,'mtime_ns':s.st_mtime_ns,'sha256':sha_file(p)}
 return result

def open_users(path):
 """Best-effort supplementary check; VANTAGE's kernel instance lock is primary."""
 names={str(path),str(path)+'-wal',str(path)+'-shm'};users=set()
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
  try:
   for fd in (proc/'fd').iterdir():
    try:
     if os.readlink(fd) in names:users.add(int(proc.name))
    except OSError:pass
  except OSError:pass
 return sorted(users)

@contextlib.contextmanager
def save_lock(path,source=False):
 lock=Path(str(path)+'.lock')
 if source:
  if not lock.is_file():raise MigrationError('Source instance lock is missing; refusing to create anything in the source directory')
  handle=lock.open('rb')
 else:
  inside_runtime(lock);lock.parent.mkdir(parents=True,exist_ok=True);handle=lock.open('a+b')
 try:
  try:fcntl.flock(handle, (fcntl.LOCK_SH if source else fcntl.LOCK_EX)|fcntl.LOCK_NB)
  except BlockingIOError:raise SaveBusy(('Stable' if source else 'Development')+' save is open in VANTAGE; close both applications and retry') from None
  users=open_users(path)
  if users:raise SaveBusy(f'Save is open by processes {users}; close both applications and retry: {path}')
  yield
 finally:handle.close()

def ro(path):return sqlite3.connect(Path(path).as_uri()+'?mode=ro&immutable=1',uri=True)

def portable(path):
 db=sqlite3.connect(path)
 try:
  checkpoint=db.execute('pragma wal_checkpoint(TRUNCATE)').fetchone()
  if checkpoint and checkpoint[0]:raise SaveBusy('Could not checkpoint private snapshot')
  if db.execute('pragma journal_mode=DELETE').fetchone()[0]!='delete':raise MigrationError('Private snapshot is not standalone')
  db.commit()
 finally:db.close()
 with open(path,'rb') as f:os.fsync(f.fileno())

def capture(path,target):
 """Stable bytes -> private DB/WAL -> SQLite backup API -> standalone SQLite."""
 path=Path(path);target=inside_runtime(target)
 if not path.is_file():raise MigrationError('Save file does not exist: '+str(path))
 before=source_files(path);raw=target.parent/('capture-'+uuid.uuid4().hex);raw.mkdir()
 try:
  for suffix in ('','-wal'):
   if suffix in before:
    p=Path(str(path)+suffix);dest=raw/('source.sqlite'+suffix);digest=hashlib.sha256()
    with read_fd(p) as src, dest.open('xb') as out:
     for block in iter(lambda:src.read(1024*1024),b''):digest.update(block);out.write(block)
     out.flush();os.fsync(out.fileno())
    if digest.hexdigest()!=before[suffix]['sha256']:raise MigrationError('Source changed during capture; nothing imported')
  if source_files(path)!=before:raise MigrationError('Source files changed during capture; nothing imported')
  # SQLite can create SHM/checkpoint files only in the disposable capture directory.
  src=sqlite3.connect((raw/'source.sqlite').as_uri()+'?mode=ro',uri=True)
  out=sqlite3.connect(target)
  try:src.backup(out)
  finally:out.close();src.close()
  portable(target)
  if source_files(path)!=before:raise MigrationError('Source changed while backup API was running')
  return before
 finally:shutil.rmtree(raw)

def schema(db):
 return {'user_version':db.execute('pragma user_version').fetchone()[0],
  'objects':[list(r) for r in db.execute("select type,name,tbl_name,sql from sqlite_master where name not like 'sqlite_%' order by type,name")],
  'foreign_keys':{r[0]:[list(f) for f in db.execute('pragma foreign_key_list('+quote(r[0])+')')] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}}

def rows(db,table):
 try:return db.execute('select rowid,* from '+quote(table)+' order by rowid')
 except sqlite3.OperationalError:return db.execute('select * from '+quote(table)+' order by '+','.join(str(i+1) for i in range(len(db.execute('select * from '+quote(table)+' limit 0').description))))
def row_bytes(row):return json.dumps(list(row),separators=(',',':'),ensure_ascii=True,default=lambda b:{'blob':bytes(b).hex()}).encode()
def table_manifest(db):
 result={}
 for (table,) in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
  h=hashlib.sha256();count=0
  for row in rows(db,table):h.update(row_bytes(row));h.update(b'\n');count+=1
  result[table]={'count':count,'sha256':h.hexdigest()}
 return result

def document_preserved(old,new,path='world'):
 """Every original root field, including unknown future fields, is immutable here."""
 differences=[]
 for key,value in old.items():
  if key in new and new[key]==value:continue
  versions={k:v for k,v,_ in WORLD_MIGRATIONS}
  if key in versions and isinstance(value,int) and value<versions[key] and new.get(key)==versions[key]:continue
  if key in ('employees','employee_activity') and isinstance(value,list) and isinstance(new.get(key),list) and new[key][:len(value)]==value:continue
  if key=='remote_capacity' and isinstance(value,dict) and isinstance(new.get(key),dict) and all(new[key].get(k)==v for k,v in value.items()):continue
  differences.append(path+'.'+key)
 return differences

def probe(db,state):
 e=object.__new__(Engine);e.db=db;e.state=copy.deepcopy(state);e.lock=threading.RLock();e._advancing=False
 return e

def finances(db,state):
 e=probe(db,state);e.reconcile();metrics={a:e.metrics(a) for a in e.accounts()}
 # Check every account, not just whichever entity is visible in the UI.
 for account in metrics:
  statement=e.statement(account,limit=1)
  if not statement['balanced']:raise MigrationError(f"Unreconciled financial statement: {state['name']} / {account}: {statement['difference']}")
 return metrics

def domain_checks(state):
 entities=state.get('entities',{});funds={f['id'] for f in state.get('funds',[])}
 for id,e in entities.items():
  parent=e.get('parent')
  if parent is not None and parent not in entities:raise MigrationError('Unknown parent for '+id)
  seen={id};current=parent
  while current:
   if current in seen:raise MigrationError('Circular corporate ownership: '+id)
   seen.add(current);current=entities[current].get('parent')
  for owner in e.get('owners',{}):
   if owner not in entities:raise MigrationError('Unknown corporate owner: '+owner)
  if id in funds and e.get('kind')!='fund':raise MigrationError('Fund legal type was lost: '+id)
 for f in state.get('funds',[]):
  if f['id'] not in entities:raise MigrationError('Fund entity is missing: '+f['id'])
 for employee in state.get('employees',[]):
  if employee['entity'] not in entities:raise MigrationError('Employee has no legal employer')

def check_sqlite(db):
 if db.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise MigrationError('SQLite integrity check failed')
 if db.execute('pragma foreign_key_check').fetchall():raise MigrationError('SQLite foreign keys failed')

def migrate_candidate(path,progress):
 db=sqlite3.connect(path)
 try:
  before_schema=schema(db);ensure_schema(db)
  for id,name,encoded,updated in db.execute('select id,name,state,updated from worlds').fetchall():
   state=json.loads(encoded)
   for key,version in BASE_VERSIONS.items():
    if state.get(key,0)<version:raise MigrationError(f'{name}: legacy {key} needs a separately verified financial upgrade; refusing to regenerate history')
   if not state.get('_legacy_fixture') and state.get('catalogue_version',0)<1:raise MigrationError(name+': missing security catalogue migration; no import performed')
   e=probe(db,state);domain_checks(state);changes=[]
   with db:
    for key,version,method in WORLD_MIGRATIONS:
     if e.state.get(key,0)>version:raise MigrationError(name+': newer unsupported '+key)
     if e.state.get(key,0)<version:getattr(e,method)();changes.append(key)
    differences=document_preserved(state,e.state,name)
    if differences:raise MigrationError('Migration changed original fields: '+', '.join(differences))
    # Keep the original name, primary key, updated timestamp and active-world pointer.
    db.execute('update worlds set state=? where id=?',(json.dumps(e.state),id))
   progress('Initialised '+name+': '+(', '.join(changes) if changes else 'already current'))
  check_sqlite(db);after_schema=schema(db)
  return {'before':before_schema,'after':after_schema,'added_objects':[r for r in after_schema['objects'] if r not in before_schema['objects']]}
 finally:db.close()

def financial_baseline(snapshot,project,output):
 """Run the original accounting implementation ONLY against a private snapshot.
 -B prevents bytecode writes to the original source; Engine.__init__ is never run.
 """
 code = r"""
import json,sqlite3,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
from vantage.engine import Engine
snapshot=Path(sys.argv[2]);db=sqlite3.connect(snapshot.as_uri()+'?mode=ro&immutable=1',uri=True)
result={}
for ident,encoded in db.execute('select id,state from worlds'):
 e=object.__new__(Engine);e.db=db;e.state=json.loads(encoded);e.reconcile()
 result[ident]={}
 for account in e.accounts():
  metrics=e.metrics(account);statement=e.statement(account,limit=1)
  if not statement['balanced']:raise ValueError('Original statement is unbalanced: '+account)
  result[ident][account]=metrics
Path(sys.argv[3]).write_text(json.dumps(result))
db.close()
"""
 env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env.pop('PYTHONPATH',None)
 completed=subprocess.run(['/usr/bin/python3','-B','-c',code,str(project),str(snapshot),str(output)],cwd=output.parent,env=env,capture_output=True,text=True,timeout=120)
 if completed.returncode:raise MigrationError('Original accounting baseline failed: '+completed.stderr[-3000:])
 return json.loads(output.read_text())

def validate(original,candidate,original_financials=None):
 src=ro(original);dst=ro(candidate)
 try:
  check_sqlite(src);check_sqlite(dst)
  original_schema=schema(src);new_schema=schema(dst)
  if any(row not in new_schema['objects'] for row in original_schema['objects']):raise MigrationError('An original schema object was changed or lost')
  original_tables=table_manifest(src);candidate_tables=table_manifest(dst)
  for table,manifest in original_tables.items():
   if table in ('worlds','audit','save_imports'):continue
   if candidate_tables.get(table)!=manifest:raise MigrationError('Historical table differs: '+table)
  # Audit and import receipts may be appended, but original rows/rowids are exact.
  for table in ('audit','save_imports'):
   if table not in original_tables:continue
   old=list(rows(src,table));new=list(rows(dst,table))
   if new[:len(old)]!=old:raise MigrationError('Original '+table+' rows changed')
  original_worlds=src.execute('select id,name,state,updated from worlds order by id').fetchall();new_worlds=dst.execute('select id,name,state,updated from worlds order by id').fetchall()
  if len(original_worlds)!=len(new_worlds):raise MigrationError('World count changed')
  worlds=[]
  for old,new in zip(original_worlds,new_worlds):
   if (old[0],old[1],old[3])!=(new[0],new[1],new[3]):raise MigrationError('World identity or historical timestamp changed')
   a=json.loads(old[2]);b=json.loads(new[2]);differences=document_preserved(a,b,old[1])
   if differences:raise MigrationError('Original world fields changed: '+', '.join(differences))
   domain_checks(a);domain_checks(b)
   # Source marks and every original state value remain EXACT; there is no repricing.
   # The candidate DB contains identical executions/journal, plus additive schema.
   fm_a=finances(dst,a);fm_b=finances(dst,b)
   if original_financials is not None:
    baseline=copy.deepcopy(original_financials[old[0]])
    if set(baseline)!=set(fm_a):raise MigrationError('Original accounting account list differs: '+old[1])
    for account,values in baseline.items():
     for extra in ('owned_assets','office_right_of_use'):
      if extra not in values:
       if fm_a[account].get(extra)!='0.00':raise MigrationError('Unexpected new asset value on original account: '+account)
       values[extra]='0.00'
    if baseline!=fm_a:raise MigrationError('Development calculation differs from original stable accounting at identical marks: '+old[1])
    fm_a=baseline
   if fm_a!=fm_b:raise MigrationError('Unexplained financial differences: '+old[1])
   worlds.append({'id':old[0],'name':old[1],'time':a['time'],'tick':a['tick'],
    'entities_before':len(a.get('entities',{})),'entities_after':len(b.get('entities',{})),
    'controlled_entities':[{'id':e['id'],'name':e['name'],'kind':e['kind'],'parent':e.get('parent'),'owners':e.get('owners',{})} for e in b['entities'].values() if e.get('controlled')],
    'accounts':{id:{'original':fm_a[id],'migrated':fm_b[id]} for id in fm_a},
    'balances_original':a['balances'],'balances_migrated':b['balances'],
    'positions':len(a['positions']),'options':len(a['options']),
    'new_fields':sorted(set(b)-set(a)),'all_original_fields_exact':True})
  return {'passed':True,'world_count':len(worlds),'worlds':worlds,'original_tables':original_tables,'migrated_tables':candidate_tables,'market_marks':'Exactly preserved; no refresh, time advance or mark recalculation inputs changed','unsupported_records':[]}
 finally:src.close();dst.close()

EXCLUDED_RUNTIME={'save-imports','tmp','pycache','verification'}
def runtime_entries(parent):
 return [p for p in sorted(parent.iterdir()) if p.name not in EXCLUDED_RUNTIME and not p.name.endswith(('.sqlite','.sqlite-wal','.sqlite-shm','.sqlite.lock')) and not p.name.endswith('-backups') and p.name not in ('expansion-backups',PENDING,'.save-import.lock') and not p.name.startswith('capture-')]
def copy_entry(src,dst):
 if src.is_symlink():dst.symlink_to(os.readlink(src))
 elif src.is_dir():
  shutil.copytree(src,dst,symlinks=True)
  for item in dst.rglob('*'):
   if item.is_file() and not item.is_symlink():
    with item.open('rb') as f:os.fsync(f.fileno())
  fsync_dir(dst)
 else:
  shutil.copy2(src,dst)
  with dst.open('rb') as f:os.fsync(f.fileno())
def backup_runtime(parent,target):
 target.mkdir();entries=[]
 for p in runtime_entries(parent):
  if target.is_relative_to(p):continue  # Never recursively archive the archive itself.
  copy_entry(p,target/p.name);entries.append(p.name)
 return entries

def runtime_manifest(folder):
 result={}
 for p in sorted(folder.rglob('*')):
  relative=str(p.relative_to(folder))
  if p.is_symlink():result[relative]={'symlink':os.readlink(p)}
  elif p.is_file():result[relative]={'sha256':sha_file(p),'size':p.stat().st_size}
  elif p.is_dir():result[relative]={'directory':True}
 return result

def check_backup(run):
 manifest=json.loads((run/'backup.json').read_text())
 if sha_file(run/'previous.sqlite')!=manifest['database_sha256']:raise MigrationError('Rollback backup checksum failed; original archive retained')
 if 'runtime_manifest' in manifest and runtime_manifest(run/'previous-runtime')!=manifest['runtime_manifest']:raise MigrationError('Runtime backup checksum failed; no files restored')
 return manifest

def checkpoint_destination(path):
 if not path.exists():return
 db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=0)
 try:
  if db.execute('pragma wal_checkpoint(TRUNCATE)').fetchone()[0]:raise SaveBusy('Development WAL is busy; no replacement permitted')
  if db.execute('pragma journal_mode=DELETE').fetchone()[0]!='delete':raise SaveBusy('Development database still has active readers')
 finally:db.close()

def atomic_copy(source,destination):
 temp=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex+'.tmp')
 shutil.copy2(source,temp)
 with temp.open('rb') as f:os.fsync(f.fileno())
 os.replace(temp,destination);fsync_dir(destination.parent)

def restore_references(run,parent):
 for name in REFERENCE_FILES:
  original=run/'previous-runtime'/name;dest=parent/name
  if original.exists() or original.is_symlink():atomic_copy(original,dest)
  elif dest.exists():dest.unlink()
 fsync_dir(parent)

def restore_previous(run,destination,clear_pending=True):
 manifest=check_backup(run);backup=run/'previous.sqlite'
 checkpoint_destination(destination)
 for suffix in ('-wal','-shm'):
  p=Path(str(destination)+suffix)
  if p.exists():p.unlink()  # Checkpointed, development-only sidecars; never source.
 atomic_copy(backup,destination);restore_references(run,destination.parent)
 pending=destination.parent/PENDING
 if clear_pending and pending.exists():pending.unlink()
 fsync_dir(destination.parent)

class Importer:
 def __init__(self,source=STABLE,destination=DESTINATION,work_root=None,progress=None):
  self.source=Path(source).resolve();self.destination=inside_runtime(destination)
  if self.source==self.destination or (self.source.exists() and self.destination.exists() and os.path.samefile(self.source,self.destination)):raise MigrationError('Source and destination must be different files')
  self.work_root=inside_runtime(work_root or self.destination.parent/'save-imports')
  if self.work_root==self.source or self.work_root==self.destination:raise MigrationError('Invalid migration workspace')
  self.progress=progress or (lambda message:None)
 def after_replace(self):pass  # Test seam for power-loss/replacement-failure recovery.
 def run(self,import_save=False,confirmation=None):
  if import_save and confirmation!=CONFIRM_IMPORT:raise MigrationError('Import requires --confirm '+CONFIRM_IMPORT)
  self.work_root.mkdir(parents=True,exist_ok=True)
  report={'status':'STARTING','source':str(self.source),'destination':str(self.destination),'started_at':utc(),'mode':'import' if import_save else 'dry-run'}
  run=self.work_root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);run.mkdir();report['run']=str(run);pending=self.destination.parent/PENDING
  try:
   with save_lock(self.source,True), save_lock(self.destination):
    if pending.exists():raise MigrationError('Interrupted import exists; use --rollback with its recorded run before launching')
    self.progress('Capturing source bytes read-only, then snapshotting committed WAL with SQLite backup API')
    fingerprint=capture(self.source,run/'source.sqlite');report['source_files_before']=fingerprint
    source=ro(run/'source.sqlite')
    try:report['source_schema']=schema(source);report['source_tables']=table_manifest(source)
    finally:source.close()
    digest=hashlib.sha256(json.dumps(report['source_tables'],sort_keys=True).encode()).hexdigest();report['source_digest']=digest
    if self.destination.exists():
     self.progress('Backing up the existing development database (all saved worlds)')
     capture(self.destination,run/'previous.sqlite')
     previous=ro(run/'previous.sqlite')
     try:
      report['development_schema']=schema(previous);report['previous_worlds']=[list(r) for r in previous.execute('select id,name,updated from worlds')]
      if previous.execute("select 1 from sqlite_master where type='table' and name='save_imports'").fetchone() and previous.execute('select 1 from save_imports where source_digest=?',(digest,)).fetchone():raise DuplicateImport('This exact source save has already been imported; development progress was not overwritten')
     finally:previous.close()
    elif import_save:raise MigrationError('Development save is missing; create or explicitly restore it before replacement')
    source_runtime=run/'source-runtime';source_runtime.mkdir()
    for name in REFERENCE_FILES:
     src=self.source.parent/name
     if src.exists():
      if src.is_symlink():raise MigrationError('Source reference cache is a symlink; review it before import')
      shutil.copy2(src,source_runtime/name)
    self.progress('Applying additive SQL and employee → research → wealth → office migrations')
    shutil.copy2(run/'source.sqlite',run/'candidate.sqlite');report['schema_migrations']=migrate_candidate(run/'candidate.sqlite',self.progress)
    candidate=sqlite3.connect(run/'candidate.sqlite')
    try:
     candidate.execute('insert into save_imports values(?,?,?,?,?)',(digest,utc(),str(self.source),str(run/'previous.sqlite'),str(run/'report.json')));candidate.commit()
    finally:candidate.close()
    portable(run/'candidate.sqlite')
    self.progress('Validating every original field/table, accounting balance, position, option, ownership link and market mark')
    original_financials=None
    if self.source==STABLE:
     self.progress('Independently comparing the original stable accounting code against the private snapshot; no stable runtime is opened')
     original_financials=financial_baseline(run/'source.sqlite',STABLE.parents[2],run/'original-financials.json')
     report['original_accounting_implementation']=str(STABLE.parents[2]/'vantage/engine.py')
    report['validation']=validate(run/'source.sqlite',run/'candidate.sqlite',original_financials)
    if source_files(self.source)!=fingerprint:raise MigrationError('Stable files changed after capture; import cancelled')
    if open_users(self.source) or open_users(self.destination):raise SaveBusy('A save was opened during validation; no replacement permitted')
    report['source_files_after']=source_files(self.source);report['source_untouched']=report['source_files_after']==fingerprint
    report['candidate_sha256']=sha_file(run/'candidate.sqlite')
    report['status']='DRY_RUN_PASSED';write_json(run/'report.json',report)
    if not import_save:return report
    self.progress('Archiving development configuration, caches, logs and other live runtime files')
    entries=backup_runtime(self.destination.parent,run/'previous-runtime');report['runtime_backup_entries']=entries
    write_json(run/'backup.json',{'database_sha256':sha_file(run/'previous.sqlite'),'runtime_entries':entries,'runtime_manifest':runtime_manifest(run/'previous-runtime'),'worlds':report['previous_worlds']})
    report['status']='PREPARED';write_json(run/'report.json',report);write_json(pending,{'run':str(run),'destination':str(self.destination),'source':str(self.source),'phase':'REPLACING'})
    try:
     checkpoint_destination(self.destination)
     os.replace(run/'candidate.sqlite',self.destination);fsync_dir(self.destination.parent)
     for name in REFERENCE_FILES:
      current=self.destination.parent/name;src=source_runtime/name
      if src.exists():atomic_copy(src,current)
      elif current.exists():current.unlink()  # Archived in previous-runtime, never lost.
     self.after_replace()
     if sha_file(self.destination)!=report['candidate_sha256']:raise MigrationError('Installed database checksum differs from the validated candidate')
     installed=ro(self.destination)
     try:check_sqlite(installed)
     finally:installed.close()
     report['status']='IMPORTED';report['completed_at']=utc();write_json(run/'report.json',report)
     pending.unlink();fsync_dir(self.destination.parent);self.progress('Import complete; stable save unchanged and prior development save retained')
    except BaseException:
     self.progress('Import interrupted; restoring the previous development database and reference state')
     restore_previous(run,self.destination);report['status']='ROLLED_BACK';write_json(run/'report.json',report);raise
    return report
  except BaseException as exc:
   if report.get('status')!='ROLLED_BACK':report['status']='FAILED'
   report['error']=str(exc);write_json(run/'report.json',report);exc.migration_report=str(run/'report.json');raise

 def rollback(self,run,confirmation):
  if confirmation!=CONFIRM_ROLLBACK:raise MigrationError('Rollback requires --confirm '+CONFIRM_ROLLBACK)
  run=inside_runtime(run)
  if not run.is_relative_to(self.work_root):raise MigrationError('Rollback run must belong to this importer workspace')
  report=json.loads((run/'report.json').read_text())
  if report['destination']!=str(self.destination):raise MigrationError('Backup belongs to another development save')
  with save_lock(self.source,True),save_lock(self.destination):
   pending=self.destination.parent/PENDING
   if pending.exists() and json.loads(pending.read_text())['run']!=str(run):raise MigrationError('Another interrupted import needs recovery first')
   manifest=check_backup(run)
   archive=self.work_root/('before-rollback-'+uuid.uuid4().hex[:8]);archive.mkdir()
   capture(self.destination,archive/'current.sqlite');backup_runtime(self.destination.parent,archive/'current-runtime')
   write_json(pending,{'run':str(run),'destination':str(self.destination),'source':str(self.source),'phase':'ROLLBACK'})
   restore_previous(run,self.destination,clear_pending=False)
   displaced=archive/'displaced-files';displaced.mkdir()
   for name in manifest['runtime_entries']:
    if Path(name).name!=name:raise MigrationError('Invalid runtime archive path')
    src=run/'previous-runtime'/name;target=self.destination.parent/name
    prepared=self.destination.parent/('.restore-'+uuid.uuid4().hex)
    copy_entry(src,prepared)
    if target.exists() or target.is_symlink():os.replace(target,displaced/name)
    os.replace(prepared,target)
   fsync_dir(self.destination.parent);pending.unlink();fsync_dir(self.destination.parent)
   report['status']='USER_ROLLED_BACK';report['rollback_archive']=str(archive);write_json(run/'report.json',report)
   return {'status':'ROLLED_BACK','restored_database':str(self.destination),'previous_development_save':str(run/'previous.sqlite'),'displaced_runtime_backup':str(archive)}

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,default=STABLE);parser.add_argument('--destination',type=Path,default=DESTINATION)
 mode=parser.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--import',dest='import_save',action='store_true');mode.add_argument('--rollback',type=Path,metavar='RUN_DIRECTORY');parser.add_argument('--confirm');args=parser.parse_args(argv)
 try:
  importer=Importer(args.source,args.destination,progress=lambda m:print(m,flush=True))
  result=importer.rollback(args.rollback,args.confirm) if args.rollback else importer.run(args.import_save,args.confirm)
  print(json.dumps({k:result[k] for k in ('status','run','destination','source_untouched','previous_development_save','displaced_runtime_backup') if k in result},indent=2))
  if 'run' in result:print('Detailed report: '+str(Path(result['run'])/'report.json'))
  return 0
 except (MigrationError,sqlite3.Error,OSError,KeyError) as exc:
  print('Migration stopped: '+str(exc),file=sys.stderr)
  if getattr(exc,'migration_report',None):print('Failure report: '+exc.migration_report,file=sys.stderr)
  return 1

if __name__=='__main__':raise SystemExit(main())
