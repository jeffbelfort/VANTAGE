"""Read-only environment report plus isolated SQLite transaction/locking probe."""
import json,os,shutil,sqlite3,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def report():
 result={'database':os.environ.get('VANTAGE_DATABASE',str(ROOT/'data'/'vantage.sqlite')),'test_build':bool(os.environ.get('VANTAGE_TEST_BUILD')),'project':str(ROOT),'version':'0.7.0-phase-a','cwd':str(Path.cwd()),'bundle':(ROOT/'static'/'app.js').is_file()}
 for name,path in [('root','/'),('project',str(ROOT))]:
  free=shutil.disk_usage(path).free;result[name+'_free_gb']=round(free/1024**3,2)
  result[name+'_storage_ok']=free>=(5 if name=='root' else 15)*1024**3
 try:
  from PyQt6.QtCore import QT_VERSION_STR
  from PyQt6.QtWebEngineWidgets import QWebEngineView
  result['qt']=QT_VERSION_STR
 except ImportError as exc:result['qt_error']=str(exc)
 try:
  with tempfile.TemporaryDirectory(dir=ROOT/'data',prefix='diagnostic-') as directory:
   db=sqlite3.connect(Path(directory)/'probe.sqlite');result['journal_mode']=db.execute('pragma journal_mode=wal').fetchone()[0];db.execute('create table t (amount text)');db.execute("insert into t values ('12.34')");db.commit();result['sqlite_ok']=db.execute('select amount from t').fetchone()[0]=='12.34';db.close()
 except Exception as exc:result['storage_error']=str(exc)
 result['renderer']='Requires interactive Qt verification; imports alone do not verify Chromium'
 return result

if __name__=='__main__':print(json.dumps(report(),indent=2))
