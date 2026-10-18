from app import create_app
from app.config import Config


def test_partial_install_stays_live_and_reports_missing_graph_key():
    class PartialConfig(Config):
        LLM_API_KEY = 'private-router-key'
        ZEP_API_KEY = ''
        GRAPH_PROVIDER = 'zep'

    client = create_app(PartialConfig).test_client()
    assert client.get('/health').status_code == 200
    response = client.get('/api/system/status')
    assert response.status_code == 200
    assert response.json['data'] == {
        'ready': False,
        'llm_configured': True,
        'graph_configured': False,
        'missing': ['ZEP_API_KEY'],
    }
    assert 'private-router-key' not in response.get_data(as_text=True)


def test_fully_configured_install_reports_readiness_without_exposing_keys():
    class ReadyConfig(Config):
        LLM_API_KEY = 'private-router-key'
        ZEP_API_KEY = 'private-zep-key'
        GRAPH_PROVIDER = 'zep'

    response = create_app(ReadyConfig).test_client().get('/api/system/status')
    assert response.json['data']['ready'] is True
    assert response.json['data']['missing'] == []
    assert 'private-' not in response.get_data(as_text=True)


def test_graph_build_without_zep_reports_configuration_dependency(monkeypatch):
    from app.api import graph
    monkeypatch.setattr(graph.Config, 'GRAPH_PROVIDER', 'zep')
    monkeypatch.setattr(graph.Config, 'ZEP_API_KEY', '')
    client = create_app().test_client()
    token = client.get('/api/session').json['data']['csrf_token']
    response = client.post('/api/graph/build', json={}, headers={'X-MiroFish-CSRF': token})
    assert response.status_code == 503
    assert response.json['success'] is False
    assert 'ZEP_API_KEY' in response.json['error']
    assert 'traceback' not in response.json


def test_local_graph_readiness_checks_service_and_requires_no_zep_key(monkeypatch):
    import httpx
    calls = []

    class LocalConfig(Config):
        LLM_API_KEY = 'private-router-key'
        GRAPH_PROVIDER = 'graphiti'
        GRAPHITI_API_KEY = 'private-local-graph-key'
        GRAPHITI_BASE_URL = 'http://graphiti.test'
        ZEP_API_KEY = ''

    def health(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={'status': 'ok'})

    monkeypatch.setattr(httpx, 'get', health)
    response = create_app(LocalConfig).test_client().get('/api/system/status')
    assert response.json['data']['ready'] is True
    assert response.json['data']['graph_provider'] == 'graphiti'
    assert response.json['data']['embedding'] == 'local'
    assert calls == ['http://graphiti.test/health']
    assert 'private-' not in response.get_data(as_text=True)

    monkeypatch.setattr(httpx, 'get', lambda *_args, **_kwargs: httpx.Response(503, json={'status': 'starting'}))
    response = create_app(LocalConfig).test_client().get('/api/system/status')
    assert response.json['data']['ready'] is False
    assert response.json['data']['graph_configured'] is False
    assert response.json['data']['missing'] == ['GRAPHITI_SERVICE']


def test_local_graph_and_entity_routes_do_not_require_a_cloud_key(monkeypatch):
    from app.api import graph, simulation
    from types import SimpleNamespace
    monkeypatch.setattr(Config, 'GRAPH_PROVIDER', 'graphiti')
    monkeypatch.setattr(Config, 'GRAPHITI_API_KEY', 'private-local-key')
    monkeypatch.setattr(Config, 'GRAPHITI_BASE_URL', 'http://graphiti.test')
    monkeypatch.setattr(Config, 'ZEP_API_KEY', '')
    monkeypatch.setattr(graph, 'GraphBuilderService', lambda **_: SimpleNamespace(
        get_graph_data=lambda graph_id: {'graph_id': graph_id, 'nodes': [], 'edges': []}))
    monkeypatch.setattr(simulation, 'ZepEntityReader', lambda: SimpleNamespace(
        filter_defined_entities=lambda **_: SimpleNamespace(to_dict=lambda: {'entities': [], 'filtered_count': 0})))
    client = create_app().test_client()
    assert client.get('/api/graph/data/test-graph').status_code == 200
    assert client.get('/api/simulation/entities/test-graph').status_code == 200
