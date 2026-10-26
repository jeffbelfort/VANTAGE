"""Shared additive SQLite schema used by gameplay and offline save imports."""
SCHEMA_VERSION = 1
SCHEMA_SQL = r"""CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS worlds(id TEXT PRIMARY KEY,name TEXT NOT NULL,state TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS journal(id TEXT PRIMARY KEY,world TEXT NOT NULL,time TEXT NOT NULL,description TEXT NOT NULL,lines TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS journal_world ON journal(world,time);
            CREATE TABLE IF NOT EXISTS requests(world TEXT NOT NULL,key TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(world,key));
            CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,world TEXT NOT NULL,time TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS executions(id TEXT PRIMARY KEY,world TEXT NOT NULL,data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS execution_world ON executions(world);
            CREATE INDEX IF NOT EXISTS execution_order ON executions(world,json_extract(data,'$.order'));
            CREATE INDEX IF NOT EXISTS execution_account ON executions(world,json_extract(data,'$.account'));
            CREATE TABLE IF NOT EXISTS evidence_records(id TEXT PRIMARY KEY,world TEXT NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS order_archive(id TEXT PRIMARY KEY,world TEXT NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scheduled_events(world TEXT NOT NULL,event TEXT NOT NULL,time TEXT NOT NULL,PRIMARY KEY(world,event));
            INSERT OR IGNORE INTO metadata VALUES('schema','1');
CREATE TABLE IF NOT EXISTS save_imports(
 source_digest TEXT PRIMARY KEY, imported_at TEXT NOT NULL,
 source_path TEXT NOT NULL, previous_save TEXT NOT NULL, report_path TEXT NOT NULL
);
"""

def ensure_schema(db):
 version=db.execute('pragma user_version').fetchone()[0]
 if version > SCHEMA_VERSION:
  raise ValueError('Database was created by a newer VANTAGE version')
 db.execute('pragma foreign_keys=ON')
 db.executescript(SCHEMA_SQL)
 if version<SCHEMA_VERSION:db.execute('pragma user_version=1')
 db.commit()
