"""Small durable queue for public catalog resources; no account data is queued."""
import hashlib
import json
import math
import random
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from flask import current_app,g
from .providers.http import ProviderError


class JobStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
                job_key TEXT PRIMARY KEY,id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,
                song_id INTEGER NOT NULL,options TEXT NOT NULL,status TEXT NOT NULL,
                created REAL NOT NULL,due REAL NOT NULL,lease REAL NOT NULL DEFAULT 0,
                token TEXT,attempts INTEGER NOT NULL DEFAULT 0,result TEXT,reuse_until REAL NOT NULL DEFAULT 0)''')
            conn.execute('CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(status,due,lease)')

    @contextmanager
    def connection(self):
        conn=sqlite3.connect(str(self.path),timeout=3)
        conn.row_factory=sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:conn.close()

    def submit(self,song_id,kind,options,identity=None):
        options=json.dumps(options,sort_keys=True,separators=(',',':'))
        key=hashlib.sha256(f'{kind}:{identity or song_id}:{options}'.encode()).hexdigest()
        now=time.time()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM jobs WHERE job_key=?',(key,)).fetchone()
            if row and (row['status'] in ('queued','running') or row['reuse_until']>now):return dict(row)
            pending=conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if pending>=128:raise ProviderError('조회 대기 중인 자료가 많습니다. 잠시 뒤 다시 시도해 주세요.','resource_busy',503,5)
            conn.execute('INSERT OR REPLACE INTO jobs(job_key,id,kind,song_id,options,status,created,due) VALUES (?,?,?,?,?,?,?,?)',
                         (key,uuid.uuid4().hex,kind,song_id,options,'queued',now,now))
            conn.execute("DELETE FROM jobs WHERE status IN ('completed','failed') AND job_key IN (SELECT job_key FROM jobs WHERE status IN ('completed','failed') ORDER BY created DESC LIMIT -1 OFFSET 256)")
            return dict(conn.execute('SELECT * FROM jobs WHERE job_key=?',(key,)).fetchone())

    def get(self,job_id):
        with self.connection() as conn:
            row=conn.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            return dict(row) if row else None

    def claim(self):
        now=time.time()
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # A crashed worker cannot leave a resource permanently loading.
            conn.execute("UPDATE jobs SET status='failed',result=?,reuse_until=? WHERE status='running' AND lease<? AND attempts>=2",
                         (json.dumps(dict(error='이전 조회가 중단되었습니다. 다시 시도해 주세요.',code='resource_interrupted',retry_after=5)),now+5,now))
            row=conn.execute("""SELECT * FROM jobs WHERE (status='queued' AND due<=?) OR (status='running' AND lease<? AND attempts<2)
                ORDER BY CASE kind WHEN 'lyrics' THEN 0 WHEN 'catalog' THEN 1 WHEN 'reviews' THEN 2 ELSE 3 END,created LIMIT 1""",(now,now)).fetchone()
            if not row:return None
            token=uuid.uuid4().hex
            conn.execute("UPDATE jobs SET status='running',token=?,lease=?,attempts=attempts+1 WHERE job_key=?",(token,now+60,row['job_key']))
            return dict(conn.execute('SELECT * FROM jobs WHERE job_key=?',(row['job_key'],)).fetchone())

    def finish(self,job,result,failed=False):
        delay=max(1,result.get('retry_after',60))
        ttl=3600 if result.get('status')=='available' and not result.get('refresh_failed') else (300 if result.get('status')=='candidates' else delay)
        with self.connection() as conn:
            conn.execute("UPDATE jobs SET status=?,result=?,reuse_until=?,lease=0,token=NULL WHERE job_key=? AND token=? AND status='running'",
                         ('failed' if failed else 'completed',json.dumps(result,ensure_ascii=False),time.time()+ttl,job['job_key'],job['token']))

    def retry(self,job,delay):
        with self.connection() as conn:
            conn.execute("UPDATE jobs SET status='queued',due=?,lease=0,token=NULL WHERE job_key=? AND token=? AND status='running'",
                         (time.time()+delay+random.uniform(.1,.5),job['job_key'],job['token']))


def perform(job):
    from . import db
    from .models import Song
    if job['kind']=='catalog':
        from .providers import musicbrainz
        result=musicbrainz.search(**json.loads(job['options']))
        return dict(result,status='available' if result['items'] else 'missing',retry_after=0 if result['items'] else 300)
    song=db.session.get(Song,job['song_id'])
    if song is None:raise ProviderError('해당 곡을 찾을 수 없습니다.','song_not_found',404)
    if job['kind']=='lyrics':
        from .lyric_service import lookup
        return lookup(song,**json.loads(job['options']))
    if job['kind']=='reviews':
        from .reviews import lookup
        return lookup(song)
    from .artwork_service import lookup
    return lookup(song)


class ResourceQueue:
    def __init__(self,app):
        self.app=app
        self._store=None
        self.stop=threading.Event()
        self.wake=threading.Event()
        self.lock=threading.Lock()
        self.threads=[]

    @property
    def store(self):
        with self.lock:
            if self._store is None:self._store=JobStore(self.app.config['RESOURCE_JOB_PATH'])
            return self._store

    def start(self):
        with self.lock:
            if self.threads:return
            for index in range(2):
                thread=threading.Thread(target=self.worker,name=f'catalog-resource-{index}',daemon=True)
                self.threads.append(thread);thread.start()

    def close(self):
        self.stop.set();self.wake.set()
        for thread in self.threads:thread.join(timeout=3)

    def worker(self):
        while not self.stop.is_set():
            try:
                job=self.store.claim()
                if job:self.run(job);continue
            except Exception:
                self.app.logger.exception('Public resource queue failed')
            self.wake.wait(1);self.wake.clear()

    def run(self,job):
        try:
            # Give the worker its own context and database session, never the
            # originating request's session, cookies, or personal records.
            with self.app.test_request_context('/internal/catalog-resource'):
                g.provider_deadline=time.monotonic()+18
                result=perform(job)
                if getattr(g,'provider_status',None):result['_provider_status']=g.provider_status
            retryable=result.get('status')=='unavailable' or result.get('refresh_failed')
            delay=max(2,result.get('retry_after',15))
            if retryable and job['attempts']<2 and delay<=60:self.store.retry(job,delay)
            else:self.store.finish(job,result)
        except ProviderError as error:
            delay=max(2,error.retry_after or 5)
            if error.status>=500 and job['attempts']<2 and delay<=60:self.store.retry(job,delay)
            else:self.store.finish(job,dict(error=str(error),code=error.code,retry_after=delay),failed=True)
        except Exception:
            self.app.logger.exception('Public resource job failed: kind=%s song_id=%s',job['kind'],job['song_id'])
            self.store.finish(job,dict(error='자료를 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.',code='resource_error',retry_after=15),failed=True)


def queue():
    app=current_app._get_current_object()
    return app.extensions['resource_queue']


def response(job):
    if job['status'] in ('completed','failed'):
        result=json.loads(job['result'])
        if result.get('retry_after',0)>0:result['retry_after']=max(0,math.ceil(job['reuse_until']-time.time()))
        return dict(status=job['status'],job_id=job['id'],result=result)
    return dict(status='pending',state=job['status'],job_id=job['id'],attempt=job['attempts'],
                retry_after=max(0,round(job['due']-time.time())),poll_after_ms=900)
