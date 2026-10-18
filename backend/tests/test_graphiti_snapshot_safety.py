"""Offline contracts for graph-scoped model identity and private credentials."""
import asyncio
import json
import sqlite3
import threading
from types import SimpleNamespace

import httpx
import pytest
from zep_cloud.core.api_error import ApiError

from app import provider_settings as providers
from app.local_graph import runtime
from app.local_graph.server import create_service
from app.local_graph.store import ServiceError, Store
from app.utils.graphiti_client import GraphitiClient


OLD = {'provider': 'custom', 'base_url': 'http://127.0.0.1:9001/v1',
       'model': 'fixture-old', 'api_key': 'synthetic-secret-old'}
NEW = {**OLD, 'model': 'fixture-new', 'api_key': 'synthetic-secret-new'}


def worker(store):
    value = object.__new__(runtime.Runtime)
    value.store = store
    value.ready, value.error = True, None
    value._graph_model_settings = {}
    value._model_settings_lock = threading.RLock()
    return value


@pytest.fixture
def graph_store(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'get_model_settings', lambda: dict(OLD))
    store = Store(tmp_path / 'graph.sqlite')
    store.create_graph('graph', '合成圖譜')
    return store


def test_client_only_sends_minimal_snapshot_in_authenticated_mutation_body():
    sent = []
    def transport(request):
        sent.append(request)
        return httpx.Response(200, json={})
    client = GraphitiClient('http://graphiti.test', 'synthetic-internal-auth', transport=httpx.MockTransport(transport))
    with providers.model_settings_snapshot({**OLD, 'balance_api_key': 'never-forward-management-key'}):
        client.graph.create(graph_id='graph', name='fixture')
        client.batch.create(metadata={'graph_id': 'graph'})
        client.graph.add(graph_id='graph', type='text', data='合成事件')
        client.graph.get('graph')
    for request in sent[:3]:
        payload = json.loads(request.content)
        assert payload['model_snapshot'] == OLD
        assert 'model_snapshot' not in payload.get('metadata', {})
        assert request.headers['Authorization'] == 'Bearer synthetic-internal-auth'
        assert 'never-forward-management-key' not in request.content.decode()
    assert sent[-1].content == b''


@pytest.mark.parametrize('endpoint', ['https://public.example/v1', 'http://169.254.169.254',
                                      'http://user:password@graphiti:5010', 'http://graphiti:5010/?secret=value'])
def test_private_model_snapshot_cannot_be_sent_to_untrusted_service_endpoint(endpoint):
    with pytest.raises(ValueError):
        GraphitiClient(endpoint, 'synthetic-internal-auth')


def test_graphiti_redirect_is_rejected_without_forwarding_credentials():
    seen = []
    def redirect(request):
        seen.append(request)
        return httpx.Response(307, headers={'Location': 'https://external.example/'})
    client = GraphitiClient('http://graphiti.test', 'synthetic-internal-auth', transport=httpx.MockTransport(redirect))
    with providers.model_settings_snapshot(OLD), pytest.raises(ApiError) as error:
        client.graph.create(graph_id='graph', name='fixture')
    assert error.value.status_code == 307
    assert len(seen) == 1


def test_faulty_service_error_cannot_echo_private_snapshot_or_credentials():
    def failure(request):
        return httpx.Response(500, headers={'Authorization': OLD['api_key'], 'x-debug-key': OLD['api_key']},
                              json={'model_snapshot': OLD, 'message': OLD['api_key'] + ' synthetic-internal-auth'})
    client = GraphitiClient('http://graphiti.test', 'synthetic-internal-auth', transport=httpx.MockTransport(failure))
    with providers.model_settings_snapshot(OLD), pytest.raises(ApiError) as error:
        client.graph.create(graph_id='graph', name='fixture')
    assert error.value.status_code == 500
    assert OLD['api_key'] not in str(error.value)
    assert 'synthetic-internal-auth' not in str(error.value)
    assert 'model_snapshot' not in str(error.value)


def test_authenticated_service_never_persists_or_returns_snapshot(graph_store):
    engine = worker(graph_store)
    service = create_service(graph_store, engine, 'synthetic-internal-auth').test_client()
    headers = {'Authorization': 'Bearer synthetic-internal-auth'}
    for url, payload in [
        ('/graphs', {'graph_id': 'new-graph', 'name': '合成圖譜', 'model_snapshot': OLD}),
        ('/batches', {'metadata': {'graph_id': 'new-graph', 'chunk_count': 1}, 'model_snapshot': OLD}),
        ('/episodes', {'graph_id': 'new-graph', 'type': 'text', 'data': '合成事件', 'model_snapshot': OLD}),
    ]:
        response = service.post(url, json=payload, headers=headers)
        assert response.status_code == 200
        assert 'synthetic-secret' not in response.get_data(as_text=True)
        assert 'model_snapshot' not in response.get_data(as_text=True)
    with graph_store.db() as conn:
        dumped = '\n'.join(conn.iterdump())
    assert 'synthetic-secret' not in dumped and 'model_snapshot' not in dumped
    assert len(graph_store.graph('new-graph')['model_fingerprint']) == 64
    assert engine._graph_model_settings['new-graph'] == OLD


def test_other_snapshot_is_rejected_before_new_episode_or_batch(graph_store):
    engine = worker(graph_store)
    engine.bind_graph_settings('graph', OLD)
    service = create_service(graph_store, engine, 'synthetic-internal-auth').test_client()
    headers = {'Authorization': 'Bearer synthetic-internal-auth'}
    for url, payload in [('/episodes', {'graph_id': 'graph', 'type': 'text', 'data': '合成事件'}),
                         ('/batches', {'metadata': {'graph_id': 'graph'}})]:
        response = service.post(url, json={**payload, 'model_snapshot': NEW}, headers=headers)
        assert response.status_code == 409
        assert 'synthetic-secret' not in response.get_data(as_text=True)
    with graph_store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM batches').fetchone()[0] == 0


@pytest.mark.parametrize('changed', [NEW, {**OLD, 'api_key': 'rotated-fixture-key'}])
def test_restart_requires_exact_fingerprint_including_key(graph_store, monkeypatch, changed):
    engine = worker(graph_store)
    engine.bind_graph_settings('graph', OLD)
    restored = worker(Store(graph_store.path))
    monkeypatch.setattr(runtime, 'get_model_settings', lambda: dict(changed))
    with pytest.raises(ServiceError) as error:
        restored.settings_for_graph('graph')
    assert error.value.status == 409
    assert 'synthetic-secret' not in str(error.value)
    assert restored._graph_model_settings == {}
    monkeypatch.setattr(runtime, 'get_model_settings', lambda: {**OLD, 'source': 'saved', 'updated_at': 'later'})
    assert restored.settings_for_graph('graph') == OLD


def test_legacy_populated_graph_has_no_implicit_model_identity(graph_store):
    graph_store.add_episode({'graph_id': 'graph', 'type': 'text', 'data': '舊資料'})
    engine = worker(graph_store)
    with pytest.raises(ServiceError, match='核對'):
        engine.bind_graph_settings('graph', OLD)
    assert graph_store.graph('graph')['model_fingerprint'] is None
    assert engine._graph_model_settings == {}


def test_private_transport_fields_are_rejected_inside_persisted_metadata(graph_store):
    with pytest.raises(ServiceError):
        graph_store.create_batch({'graph_id': 'graph', 'nested': {'model_snapshot': OLD}})
    with pytest.raises(ServiceError):
        graph_store.add_episode({'graph_id': 'graph', 'type': 'text', 'data': '合成事件',
                                 'metadata': {'items': [{'api_key': OLD['api_key']}]}})
    with graph_store.db() as conn:
        assert 'synthetic-secret' not in '\n'.join(conn.iterdump())


def test_all_batches_and_single_episode_keep_graph_snapshot_after_settings_change(graph_store, monkeypatch):
    engine = worker(graph_store)
    engine.bind_graph_settings('graph', OLD)
    for index in range(2):
        batch = graph_store.create_batch({'graph_id': 'graph', 'chunk_count': 1})
        graph_store.add_items(batch['batch_id'], [{'graph_id': 'graph', 'type': 'graph_episode', 'data': str(index)}])
        graph_store.process(batch['batch_id'])
    graph_store.add_episode({'graph_id': 'graph', 'type': 'text', 'data': '獨立事件'})
    models = []
    async def noop(*args, **kwargs):
        return []
    async def add_episode(**kwargs):
        models.append(providers.get_model_settings()['model'])
        monkeypatch.setattr(runtime, 'get_model_settings', lambda: dict(NEW))
    claim = graph_store.claim
    def stop_after_jobs():
        job = claim()
        if job is None:
            raise StopAsyncIteration('all fixture jobs processed')
        return job
    monkeypatch.setattr(graph_store, 'claim', stop_after_jobs)
    monkeypatch.setattr(runtime, 'retrieve_episodes', noop)
    monkeypatch.setattr(runtime, 'EpisodicNode', lambda **kwargs: SimpleNamespace(save=noop))
    engine.graphiti = SimpleNamespace(driver=SimpleNamespace(execute_query=noop), add_episode=add_episode)
    with pytest.raises(StopAsyncIteration):
        asyncio.run(engine._worker())
    assert models == ['fixture-old'] * 3
    assert engine._graph_model_settings['graph'] == OLD


def test_graph_schema_migration_retains_legacy_content(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE graphs (graph_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, ontology TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO graphs VALUES ('legacy', '舊圖譜', '', '{}', '2026-10-01')")
    store = Store(path)
    assert store.graph('legacy')['name'] == '舊圖譜'
    assert store.graph('legacy')['model_fingerprint'] is None
