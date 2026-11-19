"""Opt-in real HTTP smoke check. Does not create users or their records.
Run: python -m scripts.verify_provider_cache
"""
from unittest.mock import patch
from flask import g
from backend import create_app
from backend.providers import musicbrainz,lrclib
from backend.providers.http import JsonClient,ProviderError


def main():
    app=create_app()
    outcomes=[]
    with app.test_request_context():
        try:
            data=musicbrainz.search('리도어')
            print('MusicBrainz:',data['total'],'recordings; source:',g.provider_status['mode'])
            outcomes.append(True)
        except ProviderError as error:
            print('MusicBrainz NOT VERIFIED:',error.code,'retry after:',error.retry_after)
            outcomes.append(False)
    with app.test_request_context():
        try:
            data=lrclib.client.get('/api/get/37734953')
            assert isinstance(data,dict) and data['trackName']=='Shadow of You'
            print('LRCLIB:',data['trackName'],'; source:',g.provider_status['mode'])
            # New object uses the same on-disk cache, with HTTP explicitly disabled.
            with patch('backend.providers.http.urlopen',side_effect=AssertionError('Cache miss')):
                repeated=JsonClient('https://lrclib.net',.5).get('/api/get/37734953')
                assert repeated==data
            print('LRCLIB repeated request, new client, no HTTP: PASS')
            outcomes.append(True)
        except ProviderError as error:
            print('LRCLIB NOT VERIFIED:',error.code,'retry after:',error.retry_after)
            outcomes.append(False)
    return 0 if all(outcomes) else 1


if __name__=='__main__':
    raise SystemExit(main())
