import json
from unittest.mock import patch
import pytest
from flask import g
from backend import create_app,db
from backend.models import User,Album,Song,Review,ReviewLink
from backend.providers import hellokpop,izm
from backend.providers.http import ProviderError
from backend.providers.review_matching import same_title,same_artist
from backend import reviews

URL='https://www.hellokpop.com/review/2025-in-review-day-3-the-honorable-mentions/'


def article():
    return dict(id=123,title={'rendered':'2025 In Review: Day 3 &#8211; The Honorable Mentions'},link=URL,author=62,
                _embedded={'author':[{'id':62,'name':'Editor','description':'Do not retain personal profiles'}]},
                content={'rendered':'<h1>Rock and Alternative</h1><h2>Albums</h2><p>Other – Hospital</p><h2>Songs</h2><p>Redoor – 욕망주사기 (Syringe)<br>Other – Syringe</p><script>unsafe()</script>'})


@pytest.mark.parametrize('left,right,result',[
    ('욕망주사기','욕망주사기 (Syringe)',True),('Syringe','욕망주사기 (Syringe)',True),
    ('Hospital','Hospital - EP',True),('Song','Song (Live)',False),
    ('Song','Song (Inst.)',False),('Album','Album (Deluxe)',False),
])
def test_review_title_variants_preserve_version_boundaries(left,right,result):
    assert same_title(left,right) is result


def test_bilingual_artist_keys_do_not_accept_features():
    assert same_artist('Redoor(리도어)',['리도어'])
    assert not same_artist('Other (feat. Redoor)',['Redoor'])


def test_selection_parser_keeps_only_verified_editorial_metadata():
    rows=hellokpop.normalize_search([article()])
    assert rows[0]['author']=='Editor' and rows[0]['entries'][1]['title']=='욕망주사기 (Syringe)'
    serialized=json.dumps(rows)
    assert 'unsafe' not in serialized and 'description' not in serialized and 'content' not in serialized
    unrelated=article();unrelated['title']['rendered']='Concert announcement mentioning Syringe'
    assert hellokpop.normalize_search([unrelated])==[]
    bad=article();bad['link']='https://evil.test/review/article'
    assert hellokpop.normalize_search([bad])==[]
    missing=article();missing['_embedded']={'author':[{'id':99,'name':'Wrong author'}]}
    assert hellokpop.normalize_search([missing])==[]


def test_selected_entry_requires_artist_and_title_and_is_not_a_review():
    rows=hellokpop.normalize_search([article()])
    with patch.object(hellokpop.client,'get',return_value=rows):
        item=hellokpop.find('욕망주사기','Redoor',title_aliases=['Syringe'])[0]
        assert item['article_type']=='selection' and item['source']=='HELLOKPOP'
        assert '욕망주사기' in item['context'] and 'Rock and Alternative' in item['context']
        assert hellokpop.find('욕망주사기','Unrelated')==[]
        assert hellokpop.find('Some Other Song','Redoor')==[]
    with patch.object(hellokpop.client,'get',side_effect=AssertionError('No instrumental query')):
        assert hellokpop.find('욕망주사기 (instrumental)','Redoor',instrumental=True)==[]


@pytest.fixture
def app(tmp_path):
    import uuid
    app=create_app({'TESTING':True,'SECRET_KEY':'test','SESSION_SQLALCHEMY_TABLE':'editorial_'+uuid.uuid4().hex,
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'test.db')})
    with app.app_context():
        db.create_all()
        a=Album(provider='fixture',external_id='hospital',title='Hospital',artist='Redoor')
        db.session.add(a);db.session.flush()
        db.session.add_all([User(id=1,email='editorial@example.com',username='editorial',name='Test',password_hash='unused'),
            Song(id=1,provider='fixture',external_id='syringe',title='욕망주사기',artist='Redoor',album_id=a.id,duration_ms=263000),
            Song(id=2,provider='fixture',external_id='other',title='Other Song',artist='Other')]);db.session.commit()
    yield app
    izm.client.cache.clear();hellokpop.client.cache.clear()


def client(app):
    c=app.test_client()
    with c.session_transaction() as session:session['user_id']=1
    return c


def send(c,data=None):
    token=c.get('/api/session').json['csrf_token']
    return c.post('/api/songs/1/reviews',json=data or {},headers={'X-CSRFToken':token})


def test_secondary_source_recovers_primary_failure_and_saves_type(app):
    c=client(app)
    with patch.object(hellokpop.client,'get',return_value=hellokpop.normalize_search([article()])):
        item=hellokpop.find('욕망주사기','Redoor')[0]
    with patch.object(izm,'find',side_effect=ProviderError('temporary')),patch.object(hellokpop,'find',return_value=[item]):
        result=send(c)
        assert result.status_code==200 and result.json['status']=='available' and result.json['partial']
        row=result.json['reviews'][0]
        assert row['article_type']=='selection' and row['source']=='HELLOKPOP'
        assert '욕망주사기' in row['introduction']
    with patch.object(izm,'find',side_effect=AssertionError('No external query')),patch.object(hellokpop,'find',side_effect=AssertionError('No external query')):
        assert send(c).json['from_database']


def test_shared_selection_keeps_context_separate_for_each_song(app):
    with app.app_context():
        item=dict(title='Year-end selection',author='Editor',url=URL,introduction='General overview',article_type='selection',source='HELLOKPOP',relation='song',context='First song selection')
        first=db.session.get(Song,1);second=db.session.get(Song,2)
        reviews.save(first,[item]);reviews.save(second,[{**item,'context':'Second song selection'}])
        assert db.session.query(Review).count()==1 and db.session.query(ReviewLink).count()==2
        assert reviews.for_song(first)[0]['introduction']=='First song selection'
        assert reviews.for_song(second)[0]['introduction']=='Second song selection'


def test_missing_retry_uses_remaining_time_and_checks_both_sources(app):
    c=client(app)
    import time
    now=time.time()
    with patch.object(izm,'find',return_value=[]) as primary,patch.object(hellokpop,'find',return_value=[]) as secondary:
        assert send(c).json['status']=='missing'
        with patch('backend.reviews.time.time',return_value=now+299):assert send(c).json['retry_after']<=2
        assert primary.call_count==secondary.call_count==1
        with patch('backend.reviews.time.time',return_value=now+302):assert send(c).json['status']=='missing'
        assert primary.call_count==secondary.call_count==2


def test_provider_budget_is_restored_for_next_source(app):
    import time
    with app.test_request_context():
        deadline=time.monotonic()+18;g.provider_deadline=deadline
        with reviews.provider_budget(1):assert g.provider_deadline<deadline-15
        assert g.provider_deadline==deadline


def test_manual_review_retry_checks_both_providers_after_eight_seconds(app):
    c=client(app)
    import time
    with patch('backend.reviews.time.time',return_value=time.time()) as clock, patch.object(izm,'find',return_value=[]) as iz, patch.object(hellokpop,'find',return_value=[]) as hk:
        assert send(c).json=={'status':'missing','reviews':[],'retry_after':8}
        clock.return_value+=3
        assert send(c,{'refresh':True}).json['retry_after']==5
        clock.return_value+=5
        assert send(c).json['retry_after']==0
        assert iz.call_count==hk.call_count==1
        assert send(c,{'refresh':True}).json['retry_after']==8
        assert iz.call_count==hk.call_count==2


def test_review_refresh_revalidates_unmatched_rows_and_honors_rate_limit(app):
    c=client(app)
    import time
    with patch('backend.reviews.time.time',return_value=time.time()) as clock, patch.object(izm.client,'open',side_effect=AssertionError('unexpected HTTP')):
        with app.test_request_context():
            params={'keyword':'Unrelated'}
            from urllib.parse import urlencode
            izm.client._write('/content/search/?'+urlencode(params),[{'title':'Unrelated'}],None)
            clock.return_value+=9
            assert izm.client.get('/content/search/',params)==[{'title':'Unrelated'}]
            g.refresh_reviews=True
            with pytest.raises(AssertionError,match='unexpected HTTP'):
                izm.client.get('/content/search/',params)
        with patch.object(izm,'find',side_effect=ProviderError('limited','provider_rate_limited',503,25)) as iz, patch.object(hellokpop,'find',return_value=[]):
            assert send(c).json=={'status':'unavailable','reviews':[],'retry_after':25}
            clock.return_value+=8
            assert send(c,{'refresh':True}).json['retry_after']==17
            assert iz.call_count==1
