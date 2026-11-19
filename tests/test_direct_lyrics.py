from unittest.mock import patch
from urllib.request import Request
import pytest
from flask import Flask
from backend.providers import lrclib
from backend.providers.http import ProviderError


def record(**extra):
    return dict(id=77,trackName='Syringe',artistName='Redoor',albumName='Hospital - EP',
                duration=264,plainLyrics='테스트 구절',**extra)


def test_verified_alias_uses_signature_before_any_search():
    def response(path,params):
        assert path=='/api/get','Search must not be needed'
        assert params['album_name']=='Hospital' and params['duration']==263
        return record() if params['track_name']=='Syringe' else None
    with patch.object(lrclib.client,'get',side_effect=response) as call:
        result=lrclib.find('욕망주사기','Redoor',263000,title_aliases=['Syringe'],album='Hospital')
        assert result['external_id']=='77' and result['match_method']=='title_alias'
        assert call.call_count==2


def test_known_lyric_id_needs_one_request_and_still_checks_identity():
    with patch.object(lrclib.client,'get',return_value=record()) as call:
        result=lrclib.find('욕망주사기','Redoor',263000,title_aliases=['Syringe'],album='Hospital',preferred_id='77')
        assert result['external_id']=='77'
        call.assert_called_once_with('/api/get/77')
    wrong=record();wrong['id']=88
    with patch.object(lrclib.client,'get',return_value=wrong),pytest.raises(ProviderError):
        lrclib.find('Syringe','Redoor',263000,preferred_id='77')


def test_bad_signature_result_does_not_bypass_identity_or_version_checks():
    for field,value in [('artistName','Other'),('trackName','Syringe (Live)'),('duration',280),('albumName','Other Album')]:
        bad=record();bad[field]=value
        with patch.object(lrclib.client,'get',side_effect=lambda path,params:bad if path=='/api/get' else []):
            assert lrclib.find('Syringe','Redoor',263000,album='Hospital') is None
    with patch.object(lrclib.client,'get',return_value=['invalid']),pytest.raises(ProviderError):
        lrclib.find('Syringe','Redoor',263000)


def test_rate_limit_does_not_trigger_more_search_requests():
    with patch.object(lrclib.client,'get',side_effect=ProviderError('limited','provider_rate_limited',503,90)) as call:
        with pytest.raises(ProviderError):lrclib.find('Syringe','Redoor',263000)
        assert call.call_count==1
    assert lrclib.client.interval>=1


def test_registered_key_stays_in_server_header_and_cannot_follow_external_redirect():
    app=Flask(__name__);app.config['LRCLIB_API_KEY']='test-only-key'
    with app.app_context():assert lrclib.client.headers()['Lrclib-Api-Key']=='test-only-key'
    assert 'Lrclib-Api-Key' not in lrclib.client.headers()
    request=Request('https://lrclib.net/api/get/77',headers={'Lrclib-Api-Key':'test-only-key'})
    with pytest.raises(ProviderError):
        lrclib.LyricsRedirects().redirect_request(request,None,302,'',{},'https://other.test/track')
