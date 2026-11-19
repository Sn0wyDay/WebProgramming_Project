"""Lyric lookup state and availability; network failures never mean 'no lyrics'."""
import math
from datetime import datetime,timedelta,timezone
from sqlalchemy.exc import IntegrityError
from . import db
from .models import LyricVersion,LyricLookup
from .music import fetch_lyrics,lyric_candidates
from .providers.versions import is_instrumental
from .providers.http import ProviderError,report

MESSAGES={
    'unqueried':'아직 가사를 조회하지 않았습니다.',
    'instrumental':'이 곡은 반주·연주 버전이라 가사가 없습니다. 가사를 보려면 보컬 버전을 선택하세요.',
    'missing':'가사 제공처에서 일치하는 가사를 찾지 못했습니다. 미등록 또는 한글·영문 표기 차이일 수 있습니다.',
    'unmatched':'제목이 다른 가사 후보가 있습니다. 같은 곡인지 확인해 주세요.',
    'error':'일시적으로 가사를 조회하지 못했습니다. 가사가 없다는 뜻은 아닙니다.'
}


def now():return datetime.now(timezone.utc).replace(tzinfo=None)


def remaining(state):
    return max(0,math.ceil((state.retry_at-now()).total_seconds())) if state and state.retry_at else 0


def latest(song):
    return db.session.scalar(db.select(LyricVersion).where(LyricVersion.song_id==song.id).order_by(LyricVersion.id.desc()))


def save_state(song,status,delay=0,code=None):
    state=db.session.get(LyricLookup,song.id)
    if not state:
        state=LyricLookup(song_id=song.id,status=status)
        db.session.add(state)
        try:db.session.flush()
        except IntegrityError:
            db.session.rollback();state=db.session.get(LyricLookup,song.id)
    state.status=status;state.checked_at=now();state.retry_at=now()+timedelta(seconds=delay) if delay else None;state.error_code=code
    db.session.commit()
    return state


def availability(song):
    state=db.session.get(LyricLookup,song.id)
    if latest(song):status='available'
    elif song.is_instrumental or is_instrumental(song.title):status='instrumental'
    else:status=state.status if state else 'unqueried'
    return dict(lyrics_status=status,lyrics_message=MESSAGES.get(status,''),lyrics_retry_after=remaining(state) if state and state.status in ('error','missing') else 0)


def lookup(song,refresh=False,candidate_id=None):
    existing=latest(song)
    if existing and candidate_id is None and not refresh:
        return dict(status='available',version_id=existing.id,from_database=True)
    if not existing and (song.is_instrumental or is_instrumental(song.title)):
        save_state(song,'instrumental')
        return dict(status='instrumental',message=MESSAGES['instrumental'])
    prior=db.session.get(LyricLookup,song.id)
    wait=remaining(prior)
    if prior and prior.status=='error' and wait and candidate_id is None:
        if existing:
            return dict(status='available',version_id=existing.id,from_database=True,refresh_failed=True,retry_after=wait,message=MESSAGES['error']+' 저장된 가사를 표시합니다.')
        raise ProviderError(MESSAGES['error'],prior.error_code or 'provider_error',503,wait)
    if prior and prior.status=='missing' and wait and candidate_id is None:
        return dict(status='missing',cached=True,retry_after=wait,message=MESSAGES['missing'])
    try:
        version=fetch_lyrics(song,candidate_id=candidate_id)
        if version:
            save_state(song,'available')
            return dict(status='available',version_id=version.id)
        candidates=lyric_candidates(song)
        if existing:
            save_state(song,'available')
            return dict(status='available',version_id=existing.id,from_database=True,refresh_failed=True,message='새 가사를 찾지 못해 저장된 가사를 유지했습니다.')
        status='unmatched' if candidates else 'missing'
        save_state(song,status,300)
        return dict(status='candidates' if candidates else 'missing',message=MESSAGES[status],retry_after=0 if candidates else 300,candidates=[dict(id=int(c['external_id']),title=c['title'],artist=c['artist'],album=c['album'],duration=c['duration'],preview='\n'.join(c['text'].splitlines()[:2])[:400]) for c in candidates])
    except ProviderError as error:
        if error.status<500 and error.status!=429:raise
        delay=max(15,error.retry_after)
        save_state(song,'error',delay,error.code)
        if existing:
            report('stale','가사 갱신에 실패해 저장된 가사를 표시합니다.')
            return dict(status='available',version_id=existing.id,from_database=True,refresh_failed=True,retry_after=delay,message=MESSAGES['error']+' 저장된 가사를 표시합니다.')
        error.retry_after=delay
        raise
