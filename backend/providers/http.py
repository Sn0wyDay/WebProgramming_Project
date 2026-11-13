import json
import socket
import threading
import time
from collections import OrderedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = 'REVERSE/0.2 (https://github.com/Sn0wyDay/WebProgramming_Project_Front)'


class ProviderError(Exception):
    def __init__(self, message, code='provider_error', status=502):
        super().__init__(message)
        self.code, self.status = code, status


class JsonClient:
    """Bounded cache + serialized requests: one local Flask process, no extra service."""
    def __init__(self, base, interval):
        self.base, self.interval = base, interval
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.next_request = 0
        self.blocked_until = 0

    def get(self, path, params=None):
        url = self.base + path + ('?' + urlencode(params) if params else '')
        if not self.lock.acquire(timeout=2):
            raise ProviderError('외부 조회가 진행 중입니다. 잠시 뒤 다시 시도하세요.', 'provider_busy', 503)
        try:
            cached = self.cache.get(url)
            if cached and cached[0] > time.monotonic():
                self.cache.move_to_end(url)
                return cached[1]
            if self.blocked_until > time.monotonic():
                raise ProviderError('제공처 호출 제한 중입니다. 잠시 뒤 다시 시도하세요.', 'provider_rate_limited', 503)
            time.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + self.interval
            try:
                req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
                with urlopen(req, timeout=8) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('oversized response')
                result = json.loads(raw)
            except HTTPError as error:
                if error.code == 404:
                    result = None
                elif error.code in (429, 503):
                    try:
                        delay = min(300, max(5, int(error.headers.get('Retry-After', '30'))))
                    except ValueError:
                        delay = 30
                    self.blocked_until = time.monotonic() + delay
                    raise ProviderError('음악 제공처가 혼잡하거나 호출이 제한되었습니다.', 'provider_rate_limited', 503) from error
                else:
                    raise ProviderError('음악 제공처가 요청을 처리하지 못했습니다.') from error
            except (TimeoutError, socket.timeout) as error:
                raise ProviderError('음악 제공처 응답 시간이 초과되었습니다.', 'provider_timeout', 504) from error
            except (URLError, OSError) as error:
                if isinstance(getattr(error, 'reason', None), (TimeoutError, socket.timeout)):
                    raise ProviderError('음악 제공처 응답 시간이 초과되었습니다.', 'provider_timeout', 504) from error
                raise ProviderError('음악 제공처에 연결하지 못했습니다. 인터넷 연결을 확인하세요.') from error
            except (ValueError, UnicodeError) as error:
                raise ProviderError('음악 제공처의 응답 형식이 올바르지 않습니다.') from error
            self.cache[url] = (time.monotonic() + 600, result)
            self.cache.move_to_end(url)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
            return result
        finally:
            self.lock.release()
