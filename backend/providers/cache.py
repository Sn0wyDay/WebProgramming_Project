"""Small public-response cache and cross-process request leases, using stdlib SQLite."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class DiskCache:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT NOT NULL, saved REAL NOT NULL, expires REAL NOT NULL, stale_until REAL NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, next_at REAL NOT NULL DEFAULT 0, cooldown REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0, token TEXT)')

    @contextmanager
    def connection(self):
        conn=sqlite3.connect(str(self.path),timeout=2)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def read(self,key):
        with self.connection() as conn:
            row=conn.execute('SELECT value,saved,expires,stale_until FROM responses WHERE key=?',(key,)).fetchone()
        if row is None:return None
        try:return dict(value=json.loads(row[0]),saved=row[1],expires=row[2],stale_until=row[3])
        except ValueError:return None

    def write(self,key,value,ttl,stale_ttl):
        now=time.time()
        with self.connection() as conn:
            conn.execute('INSERT OR REPLACE INTO responses VALUES (?,?,?,?,?)',(key,json.dumps(value,ensure_ascii=False),now,now+ttl,now+stale_ttl))
            conn.execute('DELETE FROM responses WHERE key IN (SELECT key FROM responses ORDER BY saved DESC LIMIT -1 OFFSET 512)')

    def reserve(self,provider,lease_seconds=20):
        now=time.time()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT OR IGNORE INTO providers(name) VALUES (?)',(provider,))
            next_at,cooldown,lease_until=conn.execute('SELECT next_at,cooldown,lease_until FROM providers WHERE name=?',(provider,)).fetchone()
            if cooldown>now:return None,'cooldown',cooldown-now
            if lease_until>now:return None,'busy',lease_until-now
            token=uuid.uuid4().hex
            conn.execute('UPDATE providers SET lease_until=?,token=? WHERE name=?',(now+lease_seconds,token,provider))
            return token,'ready',max(0,next_at-now)

    def started(self,provider,token,interval):
        with self.connection() as conn:
            conn.execute('UPDATE providers SET next_at=? WHERE name=? AND token=?',(time.time()+interval,provider,token))

    def release(self,provider,token,cooldown=0):
        with self.connection() as conn:
            conn.execute('UPDATE providers SET lease_until=0,token=NULL,cooldown=MAX(cooldown,?) WHERE name=? AND token=?',(time.time()+cooldown if cooldown else 0,provider,token))
