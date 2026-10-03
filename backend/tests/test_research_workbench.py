import json
import pytest
from flask import Flask

from app.api.workbench import workbench_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.research_workbench import ResearchWorkbench
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner
from app.services.report_agent import ReportManager


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path/'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path/'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path/'simulations'))
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path/'runs'), raising=False)
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path/'reports'))
    app = Flask(__name__)
    app.register_blueprint(workbench_bp, url_prefix='/api/workbench')
    client = app.test_client()
    token = client.get('/api/workbench/session').json['data']['csrf_token']
    return ResearchWorkbench(), client, {'X-MiroFish-CSRF': token}


def test_saved_sources_enter_existing_draft_without_model(workbench):
    service, client, headers = workbench
    project = client.post('/api/workbench/projects', json={'name': '離線研究', 'requirement': '範例'}, headers=headers).json['data']
    saved = client.post(f"/api/workbench/projects/{project['project_id']}/sources",
                        json={'title': '來源 A', 'content': '<script>untrusted()</script>原文'}, headers=headers)
    assert saved.status_code == 201
    assert '原文' in ProjectManager.get_extracted_text(project['project_id'])
    assert service.detail(project['project_id'])['sources']['total'] == 1
    assert service.detail(project['project_id'])['runs'] == []


def test_source_update_preserves_old_reference_and_clone_latest(workbench):
    service, _, _ = workbench
    project = service.create('來源版本')
    pid = project['project_id']
    saved = service.save_source(pid, title='來源', content='舊的原文', identity='one')
    span = service.evidence.create_span(saved['version']['version_id'], 0, 2, '舊的')
    ref = service.evidence.add_reference(pid, 'claim', 'one', 'source_record', 'supports',
            source_id=saved['source']['source_id'], version_id=saved['version']['version_id'], span_id=span['span_id'])
    newer = service.save_source(pid, title='來源', content='更新的原文', identity='one')
    assert newer['version']['version_id'] != saved['version']['version_id']
    assert service.evidence.validate_reference(ref['reference_id'])['location_status'] == 'valid'
    draft = service.clone(pid)
    assert draft['graph_id'] is None and service.runs(draft['project_id']) == []
    assert '更新的原文' in ProjectManager.get_extracted_text(draft['project_id'])
    assert service.evidence.get_version(saved['version']['version_id'], include_content=True)['content'] == '舊的原文'


def test_archive_is_reversible_and_search_works(workbench):
    service, _, _ = workbench
    project = service.create('舊名字')
    service.edit(project['project_id'], {'name': '新名字', 'archived': True})
    assert service.projects('新名字')['total'] == 0
    assert service.projects('新名字', archived=True)['total'] == 1
    service.edit(project['project_id'], {'archived': False})
    assert service.projects('新名字')['total'] == 1


def test_quality_unknown_and_missing_are_not_zero_or_semantic_proof(workbench):
    service, _, _ = workbench
    pid = service.create('缺口')['project_id']
    quality = service.quality(pid)
    assert quality['citation_location']['value'] is None
    assert quality['source_preservation']['value'] is None
    assert quality['real_world_validation']['status'] == 'not_evaluated'
    service.evidence.add_reference(pid, 'claim', 'one', 'source_record', 'insufficient', allow_missing=True)
    quality = service.quality(pid)
    assert quality['citation_location']['denominator'] == 1
    assert quality['citation_location']['numerator'] == 0
    assert quality['model_sensitivity']['sample_size'] == 0


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://localhost:9999'])
def test_csrf_origin_and_host_protect_private_research(workbench, origin):
    _, client, headers = workbench
    assert client.post('/api/workbench/projects', json={'name': 'x'}).status_code == 403
    assert client.get('/api/workbench/projects', headers={'Origin': origin}).status_code == 403
    assert client.get('/api/workbench/projects', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/api/workbench/projects', json={'name': 'x'}, headers=headers).status_code == 201


def test_exports_escape_untrusted_content_and_select_only_one_project(workbench):
    service, client, _ = workbench
    first = service.create('<script>alert(1)</script>')['project_id']
    other = service.create('PRIVATE-OTHER-PROJECT')['project_id']
    service.save_source(other, title='private', content='UNSELECTED-CONTENT')
    content, _ = service.export(first, 'html')
    assert '<script>' not in content and '&lt;script&gt;' in content
    assert 'PRIVATE-OTHER-PROJECT' not in content and 'UNSELECTED-CONTENT' not in content
    response = client.get(f'/api/workbench/projects/{first}/export?format=html')
    assert "default-src 'none'" in response.headers['Content-Security-Policy']
    data, _ = service.export(first, 'json')
    assert json.loads(data)['project']['project_id'] == first


def test_disabled_plan_cannot_be_enabled_or_schedule_calls(workbench):
    service, client, headers = workbench
    pid = service.create('更新計畫')['project_id']
    endpoint = f'/api/workbench/projects/{pid}/plans'
    denied = client.post(endpoint, headers=headers, json={'kind': 'source_update', 'definition': {'enabled': True}})
    assert denied.status_code == 400
    saved = client.post(endpoint, headers=headers, json={'kind': 'source_update', 'definition': {'enabled': False, 'timezone': 'Australia/Sydney', 'frequency': 'weekly', 'max_attempts': 3}})
    assert saved.status_code == 200
    assert saved.json['data']['items'][0]['next_execution'] is None
    assert service.plans(pid)['items'][0]['enabled'] is False


def test_unknown_identity_rejected_before_filesystem(workbench):
    service, _, _ = workbench
    with pytest.raises(ValueError):
        service.project('../private')


def test_existing_draft_enters_real_ontology_api_once(workbench, monkeypatch):
    from app.api import graph
    service, _, _ = workbench
    pid = service.create('本機草稿', '比較合成來源')['project_id']
    saved = service.save_source(pid, title='合成原文', content='已保存的來源')
    calls = []
    class Generator:
        def generate(self, **kwargs):
            calls.append(kwargs)
            return {'entity_types': [], 'edge_types': [], 'analysis_summary': 'Fixture only'}
    monkeypatch.setattr(graph, 'OntologyGenerator', Generator)
    app = Flask(__name__)
    app.register_blueprint(graph.graph_bp, url_prefix='/api/graph')
    client = app.test_client()
    result = client.post('/api/graph/ontology/generate', data={'project_id': pid})
    assert result.status_code == 200, result.json
    assert '已保存的來源' in calls[0]['document_texts'][0]
    again = client.post('/api/graph/ontology/generate', data={'project_id': pid})
    assert again.status_code == 409 and len(calls) == 1
    assert service.evidence.get_version(saved['version']['version_id'], include_content=True)['content'] == '已保存的來源'


def test_source_update_does_not_relabel_frozen_graph_input(workbench, monkeypatch):
    from app.api import graph
    from types import SimpleNamespace
    service, _, _ = workbench
    pid = service.create('版本追溯', '合成驗證')['project_id']
    first = service.save_source(pid, title='來源', content='VERSION-ONE', identity='same')
    class Generator:
        def generate(self, **kwargs):
            # Updating while analysis runs must not replace its input snapshot.
            service.save_source(pid, title='來源', content='VERSION-TWO', identity='same')
            return {'entity_types': [], 'edge_types': [], 'analysis_summary': 'Fixture'}
    monkeypatch.setattr(graph, 'OntologyGenerator', Generator)
    monkeypatch.setattr(graph.Config, 'graph_configuration_errors', lambda: [])
    monkeypatch.setattr(graph.threading, 'Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    app = Flask(__name__)
    app.register_blueprint(graph.graph_bp, url_prefix='/api/graph')
    client = app.test_client()
    assert client.post('/api/graph/ontology/generate', data={'project_id': pid}).status_code == 200
    service.save_source(pid, title='來源', content='VERSION-THREE', identity='same')
    assert client.post('/api/graph/build', json={'project_id': pid}).status_code == 200
    project = ProjectManager.get_project(pid)
    assert project.source_versions == [{key: first['version'][key] for key in ('source_id', 'version_id', 'sha256')}]
    assert 'VERSION-ONE' in ProjectManager.get_extracted_text(pid)
    assert 'VERSION-THREE' not in ProjectManager.get_extracted_text(pid)
    assert len(service.evidence.list_versions(first['source']['source_id'])['items']) == 3


@pytest.mark.parametrize('demo_id', ['product', 'story', 'contradiction'])
def test_three_real_store_demos_are_idempotent_offline_and_exportable(workbench, monkeypatch, demo_id):
    import httpx
    import requests
    from app.services.workbench_demos import install
    from app.services.event_store import EventStore
    def forbidden(*args, **kwargs):
        raise AssertionError('A demo must not call any external service')
    monkeypatch.setattr(httpx.Client, 'request', forbidden)
    monkeypatch.setattr(requests.Session, 'request', forbidden)
    service, client, headers = workbench
    first = client.post(f'/api/workbench/demos/{demo_id}', json={}, headers=headers)
    assert first.status_code == 201, first.json
    pid = first.json['data']['project_id']
    detail = service.detail(pid)
    assert detail['project']['demo'] == 'synthetic-fixture-v1'
    assert len(detail['runs']) == len(detail['reports']) == 2
    again = install(demo_id)
    assert again['project_id'] == pid
    for run in detail['runs']:
        assert run['manifest']['kind'] == 'synthetic_fixture'
        events = EventStore.page(run['simulation_id'])
        assert len(events['items']) == 6
        assert run['graph_ready'] is False  # never masquerades as live graph completion
    comparison = EventStore.compare(detail['runs'][0]['simulation_id'], detail['runs'][1]['simulation_id'])
    assert comparison
    for format in ('html', 'md', 'json'):
        response = client.get(f'/api/workbench/projects/{pid}/export?format={format}')
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert '合成' in text or 'synthetic_fixture' in text
        assert 'api_key' not in text
        assert '6' in text
    if demo_id == 'contradiction':
        quality = service.quality(pid)
        # Preserve the two original conclusion links and add four valid links
        # per report (report + its actual sections), with all three gaps visible.
        assert quality['citation_location']['numerator'] == 10
        assert quality['citation_location']['denominator'] == 13
