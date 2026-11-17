import json
import math
import socket
import threading
import time
from collections import OrderedDict
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from flask import current_app,g,has_app_context,has_request_context
from .cache import DiskCache

USER_AGENT='REVERSE/0.3 (https://github.com/Sn0wyDay/WebProgramming_Project_Front)'


class ProviderError(Exception):
    def __init__(self,message,code='provider_error',status=502,retry_after=0):
        super().__init__(message)
        self.code,self.status,self.retry_after=code,status,max(0,math.ceil(retry_after))


def retry_seconds(value,default=30):
    try:return max(1,int(value))
    except (TypeError,ValueError):
        try:return max(1,math.ceil((parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()))
        except (ValueError,TypeError,OverflowError):return default


def report(mode,message=None):
    if not has_request_context():return
    info=getattr(g,'provider_status',dict(mode='live',warnings=[]))
    if mode=='stale' or info['mode']!='stale':info['mode']=mode
    if message and message not in info['warnings']:info['warnings'].append(message)
    g.provider_status=info


class JsonClient:
    """One local service; bounded persistent public cache, pacing and at most one retry."""
    def __init__(self,base,interval,cache_path=None,ttl=86400,stale_ttl=7*86400,transform=None):
        self.base,self.interval,self.cache_path=base,interval,cache_path
        self.ttl,self.stale_ttl=ttl,stale_ttl
        self.transform=transform
        self.lock=threading.Lock()
        self.cache=OrderedDict()
        self.next_request=0
        self.blocked_until=0

    def store(self):
        path=self.cache_path
        if path is None and has_app_context():
            path=current_app.config.get('PROVIDER_CACHE_PATH')
        return DiskCache(path) if path else None

    def cached(self,path,params=None):
        """Optional metadata must never turn a lyric lookup into another HTTP call."""
        key=path+('?' + urlencode(sorted(params.items())) if params else '')
        row=self._read(key,self.store())
        if row and row['stale_until']>time.time():return row['value']
        return None

    def remember(self,key,value):
        self._write('snapshot:'+key,value,self.store())

    def recall(self,key):
        row=self._read('snapshot:'+key,self.store())
        if row and row['stale_until']>time.time():
            report('cache' if row['expires']>time.time() else 'stale','저장된 곡 정보를 사용했습니다. 최신 정보가 아닐 수 있습니다.' if row['expires']<=time.time() else None)
            return row['value']
        return None

    def _read(self,key,store):
        # Avoid test apps sharing the long-lived production client's memory.
        if store:return store.read(self.base+key)
        namespace=current_app.config.get('SQLALCHEMY_DATABASE_URI','') if has_app_context() else ''
        return self.cache.get((namespace,key))

    def _write(self,key,value,store):
        negative=value is None or value==[] or (isinstance(value,dict) and (value.get('count') in (0,'0') or value.get('total') in (0,'0')))
        ttl=300 if negative else self.ttl
        stale=ttl if negative else self.stale_ttl
        if store:store.write(self.base+key,value,ttl,stale)
        else:
            namespace=current_app.config.get('SQLALCHEMY_DATABASE_URI','') if has_app_context() else ''
            self.cache[(namespace,key)]=dict(value=value,saved=time.time(),expires=time.time()+ttl,stale_until=time.time()+stale)
            self.cache.move_to_end((namespace,key))
            while len(self.cache)>128:self.cache.popitem(last=False)

    def open(self,request,timeout):
        return urlopen(request,timeout=timeout)

    def decode(self,raw,key,headers):
        return json.loads(raw)

    def headers(self):
        return {'User-Agent':USER_AGENT,'Accept':'application/json'}

    def get(self,path,params=None):
        key=path+('?' + urlencode(sorted(params.items())) if params else '')
        store=self.store()
        cached=self._read(key,store)
        if cached and cached['expires']>time.time():
            report('cache');return cached['value']
        if not self.lock.acquire(timeout=2):
            return self._fallback(cached,ProviderError('외부 조회가 진행 중입니다. 잠시 뒤 다시 시도하세요.','provider_busy',503,2))
        token=None;cooldown=0
        try:
            cached=self._read(key,store)
            if cached and cached['expires']>time.time():report('cache');return cached['value']
            if store:
                # A second process waits briefly for a shared response, never sends a duplicate request.
                until=time.monotonic()+2
                while True:
                    token,state,delay=store.reserve(self.base)
                    if token:
                        # A previous client may finish between the cache read
                        # and acquiring its just-released lease.
                        latest=self._read(key,store)
                        if latest and latest['expires']>time.time():report('cache');return latest['value']
                        break
                    cached=self._read(key,store)
                    if cached and cached['expires']>time.time():report('cache');return cached['value']
                    if state=='cooldown':raise ProviderError('제공처가 혼잡하거나 호출 제한 중입니다. 잠시 뒤 다시 시도하세요.','provider_rate_limited',503,delay)
                    if time.monotonic()>=until:raise ProviderError('외부 조회가 진행 중입니다. 잠시 뒤 다시 시도하세요.','provider_busy',503,2)
                    time.sleep(.1)
            else:
                if self.blocked_until>time.time():raise ProviderError('제공처 호출 제한 중입니다. 잠시 뒤 다시 시도하세요.','provider_rate_limited',503,self.blocked_until-time.time())
                delay=max(0,self.next_request-time.time())
            for attempt in range(2):
                if has_request_context():
                    remaining=getattr(g,'provider_deadline',time.monotonic()+18)-time.monotonic()
                else:remaining=18
                wait=delay if attempt==0 else max(1,self.interval)
                if remaining<wait+.2:raise ProviderError('외부 조회 시간이 초과되었습니다. 다시 시도하세요.','provider_timeout',504)
                time.sleep(wait)
                if store:store.started(self.base,token,self.interval)
                else:self.next_request=time.time()+self.interval
                try:
                    req=Request(self.base+key,headers=self.headers())
                    started=time.monotonic()
                    with self.open(req,timeout=min(5,remaining-wait)) as response:
                        raw=response.read(2_000_001)
                        headers=getattr(response,'headers',{})
                    if len(raw)>2_000_000:raise ValueError('oversized response')
                    result=self.decode(raw,key,headers)
                    if self.transform:result=self.transform(result)
                    if has_app_context():current_app.logger.info('provider=%s path=%s status=200 seconds=%.2f',self.base,path,time.monotonic()-started)
                    self._write(key,result,store);report('live');return result
                except HTTPError as error:
                    if has_app_context():current_app.logger.warning('provider=%s path=%s status=%s',self.base,path,error.code)
                    if error.code==404:self._write(key,None,store);report('live');return None
                    if error.code in (429,503):
                        cooldown=retry_seconds(error.headers.get('Retry-After'))
                        self.blocked_until=time.time()+cooldown
                        raise ProviderError('음악 제공처가 혼잡하거나 호출이 제한되었습니다.','provider_rate_limited',503,cooldown) from error
                    if error.code in (502,504) and attempt==0:continue
                    raise ProviderError('음악 제공처가 요청을 처리하지 못했습니다.') from error
                except (TimeoutError,socket.timeout,URLError,OSError) as error:
                    if attempt==0:continue
                    timeout=isinstance(error,(TimeoutError,socket.timeout)) or isinstance(getattr(error,'reason',None),(TimeoutError,socket.timeout))
                    raise ProviderError('음악 제공처 응답 시간이 초과되었습니다.' if timeout else '음악 제공처에 연결하지 못했습니다.', 'provider_timeout' if timeout else 'provider_error',504 if timeout else 502) from error
                except (ValueError,UnicodeError) as error:
                    raise ProviderError('음악 제공처 응답 형식이 올바르지 않습니다.') from error
        except ProviderError as error:
            return self._fallback(cached,error)
        finally:
            if store and token:store.release(self.base,token,cooldown)
            self.lock.release()

    @staticmethod
    def _fallback(cached,error):
        if cached and cached['stale_until']>time.time() and cached['value'] is not None:
            report('stale','제공처 연결이 원활하지 않아 이전에 받은 결과를 표시합니다. 최신 정보가 아닐 수 있습니다.')
            return cached['value']
        raise error
