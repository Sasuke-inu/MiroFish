from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import socket
from threading import Event

import httpx
import pytest

from app.services.source_importer import SourceImporter, SourceImportError


@pytest.fixture
def harness(tmp_path):
    calls = []
    now = [datetime.fromisoformat('2026-10-02T01:00:00+00:00').timestamp()]
    settings = {'UPLOAD_FOLDER': str(tmp_path), 'FIRECRAWL_ENABLED': True,
                'FIRECRAWL_BASE_URL': 'http://127.0.0.1:3002', 'FIRECRAWL_API_KEY': 'private-service-key',
                'FIRECRAWL_MAX_PAGES_PER_JOB': 3, 'FIRECRAWL_DAILY_PAGE_LIMIT': 10,
                'FIRECRAWL_BUDGET_TIMEZONE': 'Australia/Sydney'}

    def respond(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'message': 'Firecrawl API'})
        url = json.loads(request.content)['url']
        return httpx.Response(200, json={'success': True, 'data': {'markdown': 'A useful public article.',
            'metadata': {'title': 'A public article', 'statusCode': 200, 'contentType': 'text/html', 'sourceURL': url}}})

    def build(handler=respond, **overrides):
        return SourceImporter({**settings, **overrides}, transport=httpx.MockTransport(handler),
            resolver=lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 0))],
            clock=lambda: now[0])

    return build, calls, now, settings, respond


def posts(calls):
    return [call for call in calls if call.method == 'POST']


def test_review_is_free_and_deduplicates_fragments(harness):
    build, calls, _, _, _ = harness
    service = build()
    plan = service.plan(['https://example.com/article#one', 'https://example.com/article#two'])
    assert plan['new_pages'] == 1
    assert plan['entries'][0]['url'] == 'https://example.com/article'
    assert calls == []
    assert service.status()['budget']['used'] == 0


@pytest.mark.parametrize('scheme,port', [('https', 443), ('http', 80)])
def test_default_ports_share_one_page_and_cache_key(harness, scheme, port):
    build, calls, _, _, _ = harness
    service = build()
    canonical = f'{scheme}://example.com/article'
    plan = service.plan([f'{scheme}://EXAMPLE.com:{port}/article#top', canonical])
    assert plan['new_pages'] == 1
    assert [entry['url'] for entry in plan['entries']] == [canonical]
    service.fetch(plan['plan_id'])
    assert service.plan([canonical])['cached_pages'] == 1
    assert len(posts(calls)) == 1


def test_scrape_payload_excludes_paid_extraction_and_provenance_survives(harness):
    build, calls, _, _, _ = harness
    service = build()
    result = service.fetch(service.plan(['https://example.com/'])['plan_id'])
    payload = json.loads(posts(calls)[0].content)
    assert payload == {'url': 'https://example.com/', 'formats': ['markdown'], 'onlyMainContent': True,
        'parsers': [], 'proxy': 'basic', 'timeout': 45000, 'removeBase64Images': True, 'skipTlsVerification': False}
    document = result['documents'][0]
    assert 'https://example.com/' in document['markdown']
    assert '2026-10-02' in document['markdown']
    assert 'A useful public article.' in document['markdown']
    assert 'Firecrawl' not in document['markdown'].partition('\n\n---\n\n')[0]
    assert document['filename'].endswith('.md')
    assert result['attempted'] == 1
    assert result['budget']['used'] == 1
    assert result['cloud_credits'] == 0
    assert 'private-service-key' not in json.dumps(result)


@pytest.mark.parametrize('retrieval', ['cache', 'replay'])
def test_legacy_tool_note_is_removed_only_from_prelude(harness, retrieval):
    build, calls, _, _, _ = harness
    note = '收集方式：本機 Firecrawl；以下為來源原文，尚未進行模型分析。'
    body = f'This article discusses Firecrawl.\n{note}\n\n---\n\nIts original footer.'

    def page(request):
        calls.append(request)
        return httpx.Response(200, json={'success': True, 'data': {
            'markdown': body,
            'metadata': {'title': 'Article about Firecrawl', 'sourceURL': 'https://example.com/final'}}})

    service = build(page)
    url = 'https://example.com/article'
    plan = service.plan([url])
    result = service.fetch(plan['plan_id'])
    original = result['documents'][0]
    header, separator, original_body = original['markdown'].partition('\n\n---\n\n')
    legacy = {**original, 'markdown': header + '\n' + note + separator + original_body}
    legacy_result = {**result, 'documents': [legacy]}
    with service.db() as conn:
        conn.execute('UPDATE cache SET document=? WHERE url=?', (json.dumps(legacy), url))
        conn.execute('UPDATE plans SET result=? WHERE id=?', (json.dumps(legacy_result), plan['plan_id']))

    restarted = build(page)
    if retrieval == 'cache':
        clean_result = restarted.fetch(restarted.plan([url])['plan_id'])
        assert clean_result['attempted'] == 0
    else:
        clean_result = restarted.fetch(plan['plan_id'])
        assert clean_result['replayed'] is True
    document = clean_result['documents'][0]
    assert document == {**original, 'cached': retrieval == 'cache'}
    assert document['markdown'].partition(separator)[2] == body
    assert document['markdown'].count(note) == 1
    assert document['markdown'].startswith('# Article about Firecrawl\n')
    assert clean_result['budget']['used'] == 1
    assert len(posts(calls)) == 1
    # Read-time cleanup does not erase the existing cache or historical result.
    with service.db() as conn:
        stored = json.loads(conn.execute('SELECT document FROM cache WHERE url=?', (url,)).fetchone()['document'])
        assert stored == legacy


def test_replay_and_cache_survive_recreating_service_and_a_full_daily_budget(harness):
    build, calls, _, _, _ = harness
    first = build(FIRECRAWL_DAILY_PAGE_LIMIT=1)
    plan = first.plan(['https://example.com/'])
    first.fetch(plan['plan_id'])
    restarted = build(FIRECRAWL_DAILY_PAGE_LIMIT=1)
    replay = restarted.fetch(plan['plan_id'])
    assert replay['replayed'] is True
    assert replay['budget']['remaining'] == 0
    cached_plan = restarted.plan(['https://example.com/'])
    assert cached_plan['new_pages'] == 0
    cached = restarted.fetch(cached_plan['plan_id'])
    assert cached['attempted'] == 0
    assert cached['documents'][0]['cached'] is True
    assert len(posts(calls)) == 1
    with pytest.raises(SourceImportError, match='今日') as error:
        restarted.plan(['https://example.com/new'])
    assert error.value.code == 'daily_limit'


def test_over_limit_batch_is_rejected_before_any_network_work(harness):
    build, calls, _, _, _ = harness
    service = build()
    with pytest.raises(SourceImportError) as error:
        service.plan([f'https://example.com/{n}' for n in range(4)])
    assert error.value.code == 'page_limit'
    assert calls == []


@pytest.mark.parametrize('url', ['http://127.0.0.1/', 'http://10.0.0.2/', 'http://169.254.169.254/',
    'http://[::1]/', 'http://localhost/', 'http://example.local/', 'file:///etc/passwd',
    'https://user:pass@example.com/', 'https://example.com:3002/', 'https://example.com/\nother'])
def test_nonpublic_or_special_url_is_rejected_without_spending(harness, url):
    build, calls, _, _, _ = harness
    with pytest.raises(SourceImportError):
        build().plan([url])
    assert calls == []


def test_public_hostname_resolving_to_private_address_is_blocked(harness):
    build, calls, _, _, _ = harness
    service = build()
    service.resolver = lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.10', 0))]
    result = service.fetch(service.plan(['https://example.com/'])['plan_id'])
    assert result['errors'][0]['code'] == 'invalid_url'
    assert result['attempted'] == 0
    assert calls == []


@pytest.mark.parametrize('overrides', [
    {'FIRECRAWL_BASE_URL': 'https://api.firecrawl.dev'},
    {'FIRECRAWL_MAX_PAGES_PER_JOB': 100}, {'FIRECRAWL_DAILY_PAGE_LIMIT': 999},
    {'FIRECRAWL_DAILY_PAGE_LIMIT': 'invalid'}, {'FIRECRAWL_BASE_URL': 'http://127.0.0.1:bad'},
    {'FIRECRAWL_BUDGET_TIMEZONE': 'invalid/timezone'},
])
def test_cloud_endpoint_or_unsafe_configuration_cannot_be_enabled(harness, overrides):
    build, calls, _, _, _ = harness
    service = build(**overrides)
    assert service.status(probe=True)['configured'] is False
    with pytest.raises(SourceImportError) as error:
        service.plan(['https://example.com/'])
    assert error.value.code == 'configuration'
    assert calls == []


@pytest.mark.parametrize('failure', ['timeout', 'http_error', 'page_error', 'empty', 'malformed', 'pdf'])
def test_failures_stop_batch_count_attempt_and_never_retry_on_replay(harness, failure):
    build, calls, _, _, _ = harness

    def fail(request):
        calls.append(request)
        if failure == 'timeout':
            raise httpx.ReadTimeout('private-provider-message', request=request)
        if failure == 'http_error':
            return httpx.Response(500, text='private-provider-message')
        if failure == 'malformed':
            return httpx.Response(200, text='not json')
        metadata = {'statusCode': 404 if failure == 'page_error' else 200,
                    'contentType': 'application/pdf' if failure == 'pdf' else 'text/html'}
        return httpx.Response(200, json={'success': True, 'data': {
            'markdown': '' if failure == 'empty' else 'An error document.', 'metadata': metadata}})

    service = build(fail)
    plan = service.plan(['https://example.com/one', 'https://example.com/two', 'https://example.com/three'])
    result = service.fetch(plan['plan_id'])
    assert result['status'] == 'failed'
    assert result['documents'] == []
    assert result['attempted'] == 1
    assert result['budget']['remaining'] == 9
    assert 'private-provider-message' not in json.dumps(result)
    replay = build(fail).fetch(plan['plan_id'])
    assert replay['replayed'] is True
    assert len(posts(calls)) == 1


def test_partial_success_stops_before_third_page_and_retains_first(harness):
    build, calls, _, _, respond = harness

    def second_fails(request):
        if len(posts(calls)) == 1:
            calls.append(request)
            return httpx.Response(503)
        return respond(request)

    service = build(second_fails)
    result = service.fetch(service.plan([f'https://example.com/{n}' for n in range(3)])['plan_id'])
    assert len(result['documents']) == 1
    assert result['errors']
    assert result['attempted'] == 2
    assert result['budget']['remaining'] == 8
    assert len(posts(calls)) == 2
    assert result['skipped_urls'] == ['https://example.com/2']


def test_failure_retains_later_cache_hits_and_replay_never_fetches_skipped_urls(harness):
    build, calls, _, _, respond = harness
    cached_url = 'https://example.com/cached'
    build().fetch(build().plan([cached_url])['plan_id'])
    calls.clear()

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout('private-provider-message', request=request)

    service = build(fail)
    plan = service.plan(['https://example.com/fails', 'https://example.com/not-sent', cached_url])
    result = service.fetch(plan['plan_id'])
    assert [doc['url'] for doc in result['documents']] == [cached_url]
    assert result['documents'][0]['cached'] is True
    assert result['errors'][0]['code'] == 'timeout'
    assert result['skipped_urls'] == ['https://example.com/not-sent']
    assert result['attempted'] == 1
    assert result['budget']['used'] == 2  # The original cache fill plus the failed attempt.
    assert result['budget']['reserved'] == 0
    assert 'private-provider-message' not in json.dumps(result)
    replay = build(fail).fetch(plan['plan_id'])
    assert replay['replayed'] is True
    assert replay['documents'] == result['documents']
    assert replay['skipped_urls'] == result['skipped_urls']
    assert len(posts(calls)) == 1


def test_free_cache_arriving_after_plan_prevents_a_duplicate_fetch(harness):
    build, calls, _, _, _ = harness
    service = build()
    url = 'https://example.com/article'
    first, second = service.plan([url]), service.plan([url])
    service.fetch(first['plan_id'])
    result = service.fetch(second['plan_id'])
    assert result['attempted'] == 0
    assert result['documents'][0]['cached'] is True
    assert result['budget']['used'] == 1
    assert len(posts(calls)) == 1


def test_cached_document_provenance_survives_expiry_during_plan(harness):
    build, calls, now, _, _ = harness
    service = build()
    url = 'https://example.com/article'
    document = service.fetch(service.plan([url])['plan_id'])['documents'][0]
    now[0] += service.CACHE_SECONDS - 1
    plan = service.plan([url])
    now[0] += 2
    result = service.fetch(plan['plan_id'])
    assert result['documents'][0]['markdown'] == document['markdown']
    assert result['documents'][0]['fetched_at'] == document['fetched_at']
    assert result['documents'][0]['source_url'] == url
    assert result['attempted'] == 0
    assert len(posts(calls)) == 1


def test_concurrent_duplicate_and_other_plan_cannot_spend_twice(harness):
    build, calls, _, _, respond = harness
    entered, release = Event(), Event()

    def delayed(request):
        entered.set()
        assert release.wait(5)
        return respond(request)

    service = build(delayed)
    first = service.plan(['https://example.com/one'])
    other = service.plan(['https://example.com/two'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(service.fetch, first['plan_id'])
        assert entered.wait(5)
        try:
            for plan in (first, other):
                with pytest.raises(SourceImportError) as error:
                    build(delayed).fetch(plan['plan_id'])
                assert error.value.code == 'busy'
        finally:
            release.set()
        assert running.result()['attempted'] == 1
    assert len(posts(calls)) == 1


def test_expired_plan_is_not_silently_restarted(harness):
    build, calls, now, _, _ = harness
    service = build()
    plan = service.plan(['https://example.com/'])
    now[0] += 601
    with pytest.raises(SourceImportError) as error:
        service.fetch(plan['plan_id'])
    assert error.value.code == 'plan_expired'
    assert calls == []


def test_crashed_worker_releases_only_unsent_reservations_after_restart(harness):
    build, calls, now, _, _ = harness
    service = build()
    plan = service.plan(['https://example.com/one', 'https://example.com/two'])
    service._claim(plan['plan_id'])
    service._mark_attempt(plan['plan_id'])
    assert build().status()['budget']['remaining'] == 8
    now[0] += 601
    assert build().status()['budget']['remaining'] == 9
    assert build().status()['budget']['used'] == 1
    with pytest.raises(SourceImportError):
        build().fetch(plan['plan_id'])
    assert calls == []


def test_cache_expiry_and_daily_reset_follow_sydney_time(harness):
    build, calls, now, _, _ = harness
    service = build()
    service.fetch(service.plan(['https://example.com/'])['plan_id'])
    assert service.status()['budget']['resets_at'] == '2026-10-03T00:00:00+10:00'
    now[0] += 24 * 3600 + 1
    assert service.status()['budget']['used'] == 0
    assert service.plan(['https://example.com/'])['new_pages'] == 1
    assert len(posts(calls)) == 1


def test_batch_does_not_send_remaining_pages_after_midnight(harness):
    build, calls, now, _, respond = harness
    now[0] = datetime.fromisoformat('2026-10-02T13:59:58+00:00').timestamp()

    def crosses_midnight(request):
        response = respond(request)
        now[0] += 5
        return response

    service = build(crosses_midnight)
    result = service.fetch(service.plan(['https://example.com/one', 'https://example.com/two'])['plan_id'])
    assert len(posts(calls)) == 1
    assert len(result['documents']) == 1
    assert result['errors'][0]['code'] == 'plan_expired'


def test_large_text_is_capped_and_html_remains_source_text(harness):
    build, calls, _, _, _ = harness

    def long_page(request):
        calls.append(request)
        return httpx.Response(200, json={'success': True, 'data': {
            'markdown': '<script>alert(1)</script>' + '字' * 20000,
            'metadata': {'title': 'Long\narticle', 'statusCode': 200}}})

    service = build(long_page)
    doc = service.fetch(service.plan(['https://example.com/'])['plan_id'])['documents'][0]
    assert doc['chars'] == 8000
    assert doc['truncated'] is True
    assert len(doc['markdown']) < 8500
    assert doc['title'] == 'Long article'
    assert '<script>' in doc['markdown']  # The UI uses text interpolation, never HTML rendering.


def test_routes_do_not_accept_provider_options_or_foreign_origin(harness, monkeypatch):
    from app import create_app
    build, calls, _, _, _ = harness
    app = create_app()
    app.extensions['source_importer'] = build()
    client = app.test_client()
    # The app-wide guard now also covers the sources API: writes need the
    # session CSRF token obtained from the bootstrap endpoint.
    token = client.get('/api/session').json['data']['csrf_token']
    csrf = {'X-MiroFish-CSRF': token}
    denied = client.post('/api/sources/plan', json={'urls': ['https://example.com/'], 'formats': ['json']},
                         headers=csrf)
    assert denied.status_code == 400
    assert denied.json['code'] == 'invalid_request'
    origin = client.post('/api/sources/plan', json={'urls': ['https://example.com/']},
                         headers={**csrf, 'Origin': 'https://untrusted.example'})
    assert origin.status_code == 403
    allowed = client.post('/api/sources/plan', json={'urls': ['https://example.com/']},
                          headers={**csrf, 'Origin': 'http://localhost:3100'})
    assert allowed.status_code == 200
    assert calls == []
    assert client.post('/api/sources/fetch', json={'urls': ['https://example.com/']},
                       headers=csrf).status_code == 400
    status = client.get('/api/sources/status')
    assert status.json['data']['online'] is True
    assert 'private-service-key' not in status.get_data(as_text=True)
    monkeypatch.setattr(app.extensions['source_importer'], 'db', lambda: (_ for _ in ()).throw(OSError('private-path')))
    failed = client.post('/api/sources/fetch', json={'plan_id': allowed.json['data']['plan_id']}, headers=csrf)
    assert failed.status_code == 503
    assert 'private-path' not in failed.get_data(as_text=True)
    assert len(posts(calls)) == 0
