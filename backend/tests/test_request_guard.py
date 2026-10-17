"""R01: every /api route shares the local-only + CSRF guard.

Blueprint-only tests elsewhere keep building their own Flask apps; this file
proves create_app() itself enforces the policy for graph/simulation/report and
that rejected requests never reach a handler (recording doubles, zero calls).
"""
import io
from types import SimpleNamespace

import pytest

from app import create_app
from app.api import graph as graph_api
from app.api import report as report_api
from app.api import simulation as simulation_api
from app.services.simulation_runner import SimulationRunner

HOSTILE_ORIGINS = ['https://evil.example', 'http://localhost:9999', 'null']
WRITE_ROWS = [
    ('post', '/api/simulation/generate-profiles', {'json': {'graph_id': 'g1'}}),
    ('post', '/api/report/generate', {'json': {'simulation_id': 'sim_x'}}),
    ('post', '/api/simulation/start', {'json': {'simulation_id': 'sim_x'}}),
    ('delete', '/api/report/report_x', {}),
    ('delete', '/api/graph/project/proj_x', {}),
]


def _multipart_ontology():
    return {"project_id": "proj_x",
            "files": (io.BytesIO(b"A short source document."), "source.md")}


def _csrf(client):
    return {'X-MiroFish-CSRF': client.get('/api/session').json['data']['csrf_token']}


@pytest.fixture
def guarded(monkeypatch):
    calls = []

    class RecordingReader:
        def filter_defined_entities(self, **kwargs):
            calls.append('entity_reader')
            return SimpleNamespace(entities=[object()], entity_types={'Person'}, filtered_count=1)

    class RecordingProfileGenerator:
        def generate_profiles_from_entities(self, **kwargs):
            calls.append('profile_generator')
            return [SimpleNamespace(to_reddit_format=lambda: {'name': 'a'},
                                    to_twitter_format=lambda: {'name': 'a'},
                                    to_dict=lambda: {'name': 'a'})]

    class RecordingProjectManager:
        @staticmethod
        def get_project(project_id):
            calls.append('project_manager.get_project')
            return None

    class RecordingReportManager:
        @staticmethod
        def delete_report(report_id):
            calls.append('report_manager.delete_report')
            return None

    class RecordingSimulationManager:
        def __init__(self, *args, **kwargs):
            calls.append('simulation_manager.init')

        def get_simulation(self, simulation_id):
            calls.append('simulation_manager.get_simulation')
            return None

    monkeypatch.setattr(simulation_api, 'ZepEntityReader', RecordingReader)
    monkeypatch.setattr(simulation_api, 'OasisProfileGenerator', RecordingProfileGenerator)
    monkeypatch.setattr(simulation_api, 'SimulationManager', RecordingSimulationManager)
    monkeypatch.setattr(graph_api, 'ProjectManager', RecordingProjectManager)
    monkeypatch.setattr(report_api, 'ReportManager', RecordingReportManager)
    monkeypatch.setattr(report_api, 'SimulationManager', RecordingSimulationManager)
    monkeypatch.setattr(SimulationRunner, 'start_simulation',
                        lambda **kwargs: calls.append('runner.start_simulation'))

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client(), calls, app


@pytest.mark.parametrize('origin', HOSTILE_ORIGINS)
def test_untrusted_origin_is_rejected_before_any_handler(guarded, origin):
    client, calls, _ = guarded
    for method, url, kwargs in WRITE_ROWS:
        calls.clear()
        response = getattr(client, method)(url, headers={'Origin': origin}, **kwargs)
        assert response.status_code == 403, (url, response.json)
        assert response.json['success'] is False and response.json['error']
        assert 'traceback' not in response.json
        assert calls == [], (url, calls)

    calls.clear()
    response = client.post('/api/graph/ontology/generate', data=_multipart_ontology(),
                           content_type='multipart/form-data', headers={'Origin': origin})
    assert response.status_code == 403
    assert calls == []


def test_write_methods_require_the_shared_csrf_token(guarded):
    client, calls, _ = guarded
    for method, url, kwargs in WRITE_ROWS:
        calls.clear()
        response = getattr(client, method)(url, headers={'Origin': 'http://localhost:3100'}, **kwargs)
        assert response.status_code == 403, (url, response.json)
        assert calls == [], (url, calls)

        calls.clear()
        response = getattr(client, method)(url, headers={'X-MiroFish-CSRF': 'not-the-token'}, **kwargs)
        assert response.status_code == 403, (url, response.json)
        assert calls == [], (url, calls)


def test_foreign_or_non_ascii_tokens_cannot_be_guessed(guarded):
    client, calls, _ = guarded
    foreign = create_app().test_client().get('/api/session').json['data']['csrf_token']
    calls.clear()
    response = client.post('/api/simulation/generate-profiles', json={'graph_id': 'g1'},
                           headers={'X-MiroFish-CSRF': foreign})
    assert response.status_code == 403
    assert calls == []

    response = client.post('/api/simulation/generate-profiles', json={'graph_id': 'g1'},
                           headers={'X-MiroFish-CSRF': 'n\u00f6n-ascii'})
    assert response.status_code == 403  # never a 500 from the token comparison
    assert calls == []


def test_bad_host_is_rejected_for_reads_and_writes(guarded):
    client, calls, _ = guarded
    assert client.get('/api/system/status', base_url='http://evil.example').status_code == 403
    assert client.get('/api/system/status', base_url='http://127.0.0.1.evil.example').status_code == 403
    assert client.post('/api/simulation/generate-profiles', json={'graph_id': 'g1'},
                       base_url='http://evil.example').status_code == 403
    assert calls == []
    assert client.get('/api/system/status', base_url='http://127.0.0.1:5001').status_code == 200
    assert client.get('/api/system/status', base_url='http://localhost:5001').status_code == 200


def test_cross_site_fetch_metadata_is_rejected(guarded):
    client, calls, _ = guarded
    cross = client.get('/api/system/status', headers={'Sec-Fetch-Site': 'cross-site'})
    assert cross.status_code == 403
    same = client.get('/api/system/status', headers={'Sec-Fetch-Site': 'same-origin'})
    assert same.status_code == 200
    assert calls == []


def test_health_stays_outside_the_guard(guarded):
    client, _, _ = guarded
    assert client.get('/health', base_url='http://evil.example').status_code == 200


def test_session_endpoint_bootstraps_the_shared_token(guarded):
    client, _, app = guarded
    response = client.get('/api/session')
    assert response.status_code == 200
    token = response.json['data']['csrf_token']
    assert token == app.extensions['provider_settings_csrf']
    workbench = client.get('/api/workbench/session')
    assert workbench.status_code == 200
    assert workbench.json['data']['csrf_token'] == token


def test_legit_json_with_token_reaches_the_handler(guarded):
    client, calls, _ = guarded
    response = client.post('/api/simulation/generate-profiles', json={'graph_id': 'g1'},
                           headers={**_csrf(client), 'Origin': 'http://localhost:3100'})
    assert response.status_code == 200
    assert response.json['data']['platform'] == 'reddit'
    assert calls == ['entity_reader', 'profile_generator']


def test_legit_delete_with_token_reaches_the_handler(guarded):
    client, calls, _ = guarded
    response = client.delete('/api/graph/project/proj_x', headers=_csrf(client))
    assert response.status_code == 404  # handler answered; the guard did not
    assert calls == ['project_manager.get_project']


def test_legit_start_with_token_reaches_the_handler_not_the_runner(guarded):
    client, calls, _ = guarded
    response = client.post('/api/simulation/start', json={'simulation_id': 'sim_x'}, headers=_csrf(client))
    assert response.status_code == 404  # the handler answered; the guard let it through
    assert calls == ['simulation_manager.init', 'simulation_manager.get_simulation']


def test_multipart_ontology_upload_passes_the_guard(guarded):
    client, calls, _ = guarded
    response = client.post('/api/graph/ontology/generate', data=_multipart_ontology(),
                           content_type='multipart/form-data', headers=_csrf(client))
    assert response.status_code != 403
    assert 'project_manager.get_project' in calls


def test_cors_headers_only_cover_local_origins(guarded):
    client, _, _ = guarded
    trusted = client.get('/api/graph/tasks', headers={'Origin': 'http://localhost:3000'})
    assert trusted.headers.get('Access-Control-Allow-Origin') == 'http://localhost:3000'
    proxied = client.get('/api/graph/tasks', headers={'Origin': 'http://127.0.0.1:3100'})
    assert proxied.headers.get('Access-Control-Allow-Origin') == 'http://127.0.0.1:3100'
    blocked = client.get('/api/graph/tasks', headers={'Origin': 'https://evil.example'})
    assert blocked.status_code == 403
    assert 'Access-Control-Allow-Origin' not in blocked.headers


def test_settings_blueprint_keeps_its_own_rules_after_the_global_guard(guarded):
    client, calls, _ = guarded
    assert client.get('/api/settings/providers').status_code == 200
    assert client.put('/api/settings/providers', json={}).status_code == 403
    assert calls == []
