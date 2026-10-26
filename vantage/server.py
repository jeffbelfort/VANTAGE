"""Loopback-only HTTP transport with per-process CSRF capability."""
import argparse, json, logging, os, secrets, signal, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from .engine import Engine
ROOT=Path(__file__).resolve().parent.parent
log=logging.getLogger('vantage')

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,engine,port=0):
        self.engine=engine;self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port),Handler)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):log.info(fmt,*args)
    def reply(self,status,obj):
        body=json.dumps(obj,separators=(',',':'),ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def valid_host(self):return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.valid_host():return self.reply(403,{'error':'Invalid host'})
        path=urlparse(self.path).path
        if path=='/api/state':return self.reply(200,self.server.engine.snapshot(view=self.headers.get('X-Vantage-View') if self.headers.get('X-Vantage-View') in ('banking','trading') else 'full'))
        if path=='/api/health':return self.reply(200,{'ok':True,'version':'0.6.1','storage':str(self.server.engine.path)})
        if path=='/api/backups':return self.reply(200,{'files':[p.name for p in sorted((ROOT/'runtime'/'backups').glob('vantage-*.sqlite'),reverse=True)]})
        if path=='/':path='/index.html'
        file=(ROOT/'static'/path.lstrip('/')).resolve()
        if not file.is_relative_to(ROOT/'static') or not file.is_file():return self.reply(404,{'error':'Not found'})
        content=file.read_bytes()
        if file.suffix=='.html':content=content.replace(b'__TOKEN__',self.server.token.encode())
        self.send_response(200);self.send_header('Content-Type',{'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'}.get(file.suffix,'application/octet-stream'));self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(content)
    def do_POST(self):
        if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Vantage-Token',''),self.server.token):return self.reply(403,{'error':'Invalid local session token'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<2200000:raise ValueError('Invalid request length')
            body=json.loads(self.rfile.read(length));action=urlparse(self.path).path.removeprefix('/api/')
            if action=='equity_refresh':result=self.server.engine.equity_references.refresh(str(body['symbol']))
            elif action=='equity_import':result=self.server.engine.equity_references.import_quote(body)
            elif action=='reference_refresh':result=self.server.engine.references.refresh()
            elif action=='reference_import':result=self.server.engine.references.import_xml(str(body['xml']))
            elif action=='backup':result={'file':self.server.engine.backup(ROOT/'runtime'/'backups')}
            elif action=='restore':result=self.server.engine.restore(ROOT/'runtime'/'backups',str(body['file']),body.get('confirm'))
            else:result=self.server.engine.execute(action,body,self.headers.get('Idempotency-Key'))
            self.reply(200,{'result':result,'state':self.server.engine.snapshot(view='trading' if self.headers.get('X-Vantage-View')=='trading' and action in ('order','cancel','modify','control','advance','chain','employee_task','employee_approve') else 'banking' if self.headers.get('X-Vantage-View')=='banking' and action in ('bank_policy','bank_rules','bank_licence','bank_customer_transfer','loan','savings','repay','advance') else 'full')})
        except (ValueError,KeyError,StopIteration,TypeError) as exc:self.reply(400,{'error':str(exc) or 'Requested record was not found'})
        except Exception:
            log.exception('Action failed');self.reply(500,{'error':'The action failed and was rolled back. See data/vantage.log.'})

def make_server(path=None,port=0):return Server(Engine(path or ROOT/'runtime'/'vantage.sqlite'),port)

def run_clock(server,stop):
    while not stop.wait(5):
        try:
            e=server.engine
            with e.lock:
                if e.state and not e.state['paused']:e.execute('advance',{'hours':e.state['speed']})
        except Exception:log.exception('Simulation clock paused');server.engine.execute('control',{'paused':True})

def start(path=None,port=0):
    from .logging_config import configure
    configure(ROOT)
    server=make_server(path,port);stop=threading.Event()
    threading.Thread(target=server.serve_forever,daemon=True).start();threading.Thread(target=run_clock,args=(server,stop),daemon=True).start()
    return server,stop

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--database');args=parser.parse_args()
    server,stop=start(args.database,args.port)
    print(f'VANTAGE http://127.0.0.1:{server.server_port}',flush=True)
    try:signal.pause()
    except KeyboardInterrupt:pass
    finally:stop.set();server.shutdown();server.engine.close()
