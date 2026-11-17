"""Prepare existing public catalog resources without creating personal records."""
import argparse
import time
from flask import g
from run import prepare_app
from backend import db
from backend.models import Song
from backend import lyric_service,reviews,artwork_service
from backend.providers.http import ProviderError


def main():
    parser=argparse.ArgumentParser(description='저장된 곡의 가사·평론·표지 준비 상태를 확인합니다.')
    parser.add_argument('--fetch',action='store_true',help='없는 자료를 실제 제공처에서 조회해 저장')
    parser.add_argument('--song-id',type=int,action='append',help='준비할 기존 곡 ID, 반복 가능')
    parser.add_argument('--limit',type=int,default=10,help='최대 곡 수 (1~50, 기본 10)')
    parser.add_argument('--resources',nargs='+',choices=('lyrics','reviews','artwork'),default=['lyrics','reviews','artwork'])
    args=parser.parse_args()
    if not 1<=args.limit<=50:parser.error('--limit은 1~50이어야 합니다.')
    app=prepare_app()
    with app.app_context():
        stmt=db.select(Song.id).order_by(Song.id)
        if args.song_id:stmt=stmt.where(Song.id.in_(args.song_id))
        ids=list(db.session.scalars(stmt.limit(args.limit)))
    if not ids:print('등록된 곡이 없습니다. 화면에서 실제 곡을 먼저 추가해 주세요.');return
    for sid in ids:
        for kind in args.resources:
            with app.test_request_context('/internal/prepare-catalog'):
                g.provider_deadline=time.monotonic()+18
                song=db.session.get(Song,sid)
                if not args.fetch:
                    present={'lyrics':lambda:bool(lyric_service.latest(song)),
                             'reviews':lambda:bool(reviews.for_song(song)),
                             'artwork':lambda:bool(artwork_service.cached(song))}[kind]()
                    result={'status':'saved' if present else 'not_saved'}
                else:
                    try:result={'lyrics':lyric_service.lookup,'reviews':reviews.lookup,'artwork':artwork_service.lookup}[kind](song)
                    except ProviderError as error:result=dict(status='unavailable',retry_after=error.retry_after)
                print(f"{sid} / {song.artist} / {song.title} / {kind}: {result['status']}"+
                      (f" (재조회 대기 {result['retry_after']}초)" if result.get('retry_after') else ''),flush=True)


if __name__=='__main__':main()
