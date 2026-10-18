"""Offline proof for preview -> explicit adoption; no network/provider fixtures."""
from datetime import datetime
import json
import socket

from flask import Flask
import httpx
import pytest

from app.api.workbench import workbench_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.research_workbench import ResearchWorkbench
from app.services.source_importer import SourceImporter


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'workbench.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    settings = {'UPLOAD_FOLDER': str(tmp_path), 'FIRECRAWL_ENABLED': True,
                'FIRECRAWL_BASE_URL': 'http://127.0.0.1:3002', 'FIRECRAWL_MAX_PAGES_PER_JOB': 3,
                'FIRECRAWL_DAILY_PAGE_LIMIT': 10, 'FIRECRAWL_BUDGET_TIMEZONE': 'Australia/Sydney'}
    clock = [datetime.fromisoformat('2026-10-03T01:00:00+00:00').timestamp()]
    calls, content = [], {'text': 'Synthetic preserved source', 'failure': False}
    def respond(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'message': 'Firecrawl fixture'})
        if content['failure']:
            raise httpx.ReadTimeout('unknown synthetic result', request=request)
        return httpx.Response(200, json={'success': True, 'data': {'markdown': content['text'],
            'metadata': {'title': 'Synthetic title', 'publishedTime': '2026-09-01T12:00:00+08:00'}}})
    importer = SourceImporter(settings, transport=httpx.MockTransport(respond), clock=lambda: clock[0],
        resolver=lambda *_a, **_kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 0))])
    app = Flask(__name__)
    app.register_blueprint(workbench_bp, url_prefix='/api/workbench')
    app.extensions['source_importer'] = importer
    client = app.test_client()
    token = client.get('/api/workbench/session').json['data']['csrf_token']
    service = ResearchWorkbench()
    pid = service.create('Synthetic preview research')['project_id']
    def post(action, data, project_id=pid):
        return client.post(f'/api/workbench/projects/{project_id}/{action}', json=data,
                           headers={'X-MiroFish-CSRF': token})
    return service, importer, post, pid, calls, clock, content, client


def planned(post, urls=None):
    result = post('web-plan', {'urls': urls or ['https://example.com/a']})
    assert result.status_code == 200, result.json
    return result.json['data']['plan_id']


def test_preview_then_selected_adoption_is_offline_and_repeatable(flow, monkeypatch):
    service, importer, post, pid, calls, *_ = flow
    plan = planned(post, ['https://example.com/a', 'https://example.com/b'])
    preview = post('web-preview', {'plan_id': plan})
    assert preview.status_code == 200, preview.json
    data = preview.json['data']
    assert len(data['candidates']) == 2 and data['sources_saved'] is False
    assert data['candidates'][0]['parse_status'] == 'parsed'
    assert data['candidates'][0]['published_at'] == '2026-09-01T04:00:00+00:00'
    assert service.all_sources(pid) == []
    assert post('web-preview', {'plan_id': plan}).json['data']['collection']['replayed'] is True
    assert len(calls) == 2
    monkeypatch.setattr(importer, 'fetch', lambda *_: pytest.fail('adoption must not fetch'))
    monkeypatch.setattr(importer, 'client', lambda: pytest.fail('adoption must remain offline'))
    importer.enabled = False  # Saved candidates remain usable when provider is disabled.
    first = post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/b']})
    again = post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/b']})
    assert first.status_code == again.status_code == 200
    assert first.json['data']['external_calls'] == 0
    assert first.json['data']['records'] == again.json['data']['records']
    records = first.json['data']['records']
    assert records[0]['source']['identity'] == 'https://example.com/b'
    assert records[0]['version']['published_at'] == '2026-09-01T04:00:00+00:00'
    assert len(service.all_sources(pid)) == 1 and len(calls) == 2


@pytest.mark.parametrize('action', ['web-preview', 'web-adopt', 'web-fetch'])
@pytest.mark.parametrize('scope', ['foreign_project', 'unbound_legacy_plan'])
def test_project_plan_binding_prevents_foreign_or_legacy_adoption(flow, action, scope):
    service, importer, post, pid, calls, *_ = flow
    if scope == 'foreign_project':
        foreign = service.create('Other research')['project_id']
        plan = post('web-plan', {'urls': ['https://example.com/a']}, foreign).json['data']['plan_id']
    else:
        plan = importer.plan(['https://example.com/a'])['plan_id']
    payload = {'plan_id': plan}
    if action == 'web-adopt':
        payload['urls'] = ['https://example.com/a']
    response = post(action, payload)
    assert response.status_code == 409, response.json
    assert response.json['code'] == 'plan_scope'
    assert calls == [] and service.all_sources(pid) == []


@pytest.mark.parametrize('status', ['planned', 'running', 'interrupted', 'failed'])
def test_only_completed_saved_plan_can_be_adopted(flow, status):
    service, importer, post, pid, calls, *_ = flow
    plan = planned(post)
    with importer.db() as conn:
        conn.execute('UPDATE plans SET status=? WHERE id=?', (status, plan))
    response = post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/a']})
    assert response.status_code == 409 and response.json['code'] == 'plan_incomplete'
    assert calls == [] and service.all_sources(pid) == []


@pytest.mark.parametrize('urls', [[], 'https://example.com/a', ['https://example.com/outside'],
    ['https://example.com/a'] * 4, ['http://127.0.0.1/private']])
def test_adoption_validates_selection_before_saving(flow, urls):
    service, _, post, pid, calls, *_ = flow
    plan = planned(post)
    assert post('web-preview', {'plan_id': plan}).status_code == 200
    response = post('web-adopt', {'plan_id': plan, 'urls': urls})
    assert response.status_code == 400
    assert len(calls) == 1 and service.all_sources(pid) == []


def test_failed_unknown_preview_never_retries_or_adopts(flow):
    service, _, post, pid, calls, _, content, _ = flow
    content['failure'] = True
    plan = planned(post)
    first = post('web-preview', {'plan_id': plan})
    again = post('web-preview', {'plan_id': plan})
    assert first.status_code == again.status_code == 200
    assert first.json['data']['collection']['status'] == 'failed'
    assert first.json['data']['collection']['errors'][0]['code'] == 'timeout'
    assert post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/a']}).status_code == 409
    assert len(calls) == 1 and service.all_sources(pid) == []


def test_new_preview_creates_version_and_keeps_old_quote(flow):
    service, _, post, pid, calls, clock, content, _ = flow
    plan = planned(post)
    post('web-preview', {'plan_id': plan})
    first = post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/a']}).json['data']['records'][0]
    old = service.evidence.get_version(first['version']['version_id'], include_content=True)
    span = service.evidence.create_span(old['version_id'], 0, 1, '#')
    reference = service.evidence.add_reference(pid, 'claim', 'claim-one', 'source_record', 'supports',
        source_id=first['source']['source_id'], version_id=old['version_id'], span_id=span['span_id'])
    clock[0] += 86401
    content['text'] = 'Updated synthetic preserved source'
    newer_plan = planned(post)
    post('web-preview', {'plan_id': newer_plan})
    newer = post('web-adopt', {'plan_id': newer_plan, 'urls': ['https://example.com/a']}).json['data']['records'][0]
    assert first['source']['source_id'] == newer['source']['source_id']
    assert first['version']['version_id'] != newer['version']['version_id']
    assert service.evidence.validate_reference(reference['reference_id'])['location_status'] == 'valid'
    assert len(calls) == 2
    # The old plan keeps its exact version even after the URL cache is replaced.
    old_again = post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/a']}).json['data']['records'][0]
    assert old_again['version']['version_id'] == old['version_id']
    assert len(calls) == 2


def test_completed_preview_survives_adapter_restart_without_provider(flow):
    _, importer, post, pid, calls, _, _, client = flow
    plan = planned(post)
    assert post('web-preview', {'plan_id': plan}).status_code == 200
    def forbidden(_request):
        pytest.fail('saved adoption cannot call any provider')
    restarted = SourceImporter({**importer.settings, 'FIRECRAWL_ENABLED': False},
                               transport=httpx.MockTransport(forbidden))
    client.application.extensions['source_importer'] = restarted
    adopted = post('web-adopt', {'plan_id': plan, 'urls': ['https://example.com/a']})
    assert adopted.status_code == 200 and len(calls) == 1
    assert adopted.json['data']['records'][0]['source']['project_id'] == pid


def test_search_status_is_honestly_unverified_and_disabled(flow):
    _, importer, _, _, calls, *_ = flow
    status = importer.status()
    assert status['search'] == {'capability': 'unverified', 'status': 'disabled_authorization',
                                'enabled': False, 'provider_version': None}
    assert calls == []
    importer.status(probe=True)
    assert len(calls) == 1 and calls[0].method == 'GET' and calls[0].url.path == '/'


@pytest.mark.parametrize('metadata,expected', [
    ({'publishedTime': '2026-09-01T12:00:00+08:00'}, '2026-09-01T04:00:00+00:00'),
    ({'article:published_time': '2026-09-01T04:00:00Z'}, '2026-09-01T04:00:00+00:00'),
    ({'datePublished': '2026-09-01'}, None), ({'publishedAt': '<script>bad()</script>'}, None),
    ({'published_at': '2026-02-30T04:00:00Z'}, None), ({'publishedTime': {'text': 'untrusted'}}, None),
    ({'dateModified': '2026-09-01T04:00:00Z'}, None),
])
def test_published_metadata_only_accepts_explicit_iso_timestamp(flow, metadata, expected):
    _, importer, *_ = flow
    document = importer._document('https://example.com/a', {'markdown': 'Synthetic', 'metadata': metadata})
    assert document['published_at'] == expected


def test_existing_web_fetch_contract_still_saves_and_guards_remain(flow):
    service, _, post, pid, calls, _, _, client = flow
    plan = planned(post)
    blocked = client.post(f'/api/workbench/projects/{pid}/web-preview', json={'plan_id': plan})
    assert blocked.status_code == 403 and calls == []
    saved = post('web-fetch', {'plan_id': plan})
    assert saved.status_code == 200 and len(saved.json['data']['records']) == 1
    assert saved.json['data']['rebuild_started'] is False
    assert len(service.all_sources(pid)) == 1
