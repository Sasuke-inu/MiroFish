"""Provider boundary, durable ingestion and failure tests; real integration is separate."""
import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from zep_cloud import BatchAddItem, NotFoundError
from zep_cloud.core.api_error import ApiError

from app.config import Config
from app.local_graph.server import create_service
from app.local_graph.runtime import Runtime
from app.local_graph.store import ServiceError, Store
from app.provider_settings import model_settings_snapshot
from app.utils.graphiti_client import GraphitiClient
from app.utils.zep import get_zep_client, clear_zep_client_cache
from app.utils.zep_paging import fetch_all_nodes


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / 'state' / 'journal.sqlite')
    result.create_graph('first', '第一個專案')
    result.create_graph('second', '第二個專案')
    return result


def batch(store, count=2):
    return store.create_batch({'graph_id': 'first', 'mirofish_operation_id': 'test-operation', 'chunk_count': count})['batch_id']


def item(text='小橙經營咖啡店', graph_id='first'):
    return {'type': 'graph_episode', 'graph_id': graph_id, 'data': text, 'data_type': 'text',
            'source_description': 'test document', 'metadata': {'source': 'test'}}


def test_draft_batch_persists_without_starting_or_recreating(store):
    batch_id = batch(store)
    items = store.add_items(batch_id, [item(), item('小青是桌遊社成員')])
    reloaded = Store(store.path)
    assert reloaded.claim() is None
    assert batch(reloaded) == batch_id
    assert reloaded.page(batch_id)['items'][0]['episode_uuid'] == items[0]['episode_uuid']
    assert reloaded.batch(batch_id)['status'] == 'draft'


def test_batch_requires_complete_payload_and_rolls_back_mixed_projects(store):
    batch_id = batch(store)
    with pytest.raises(ServiceError):
        store.add_items(batch_id, [item(), item(graph_id='second')])
    assert store.page(batch_id)['items'] == []
    store.add_items(batch_id, [item()])
    with pytest.raises(ServiceError, match='不完整'):
        store.process(batch_id)
    assert store.claim() is None


def test_batch_receipts_and_success_barrier(store):
    batch_id = batch(store)
    receipt = store.add_items(batch_id, [item(), item('居民希望保持安靜')])
    store.process(batch_id)
    job = store.claim()
    assert job['episode_uuid'] == receipt[0]['episode_uuid']
    assert store.batch(batch_id)['status'] == 'processing'
    assert store.episode(job['episode_uuid'])['processed'] is False
    store.finish(job['episode_uuid'])
    assert store.batch(batch_id)['status'] == 'processing'
    store.finish(store.claim()['episode_uuid'])
    result = store.batch(batch_id)
    assert result['status'] == 'succeeded'
    assert result['progress']['percent_complete'] == 100
    assert all(row['source_uuid'] == row['episode_uuid'] and row['processed'] for row in store.page(batch_id)['items'])
    assert store.process(batch_id)['status'] == 'succeeded'


def test_interrupted_ingestion_is_visible_and_never_replayed(store):
    batch_id = batch(store)
    store.add_items(batch_id, [item(), item('居民希望保持安靜')])
    store.process(batch_id)
    job = store.claim()
    reloaded = Store(store.path)
    assert [row['episode_uuid'] for row in reloaded.interrupted()] == [job['episode_uuid']]
    reloaded.finish(job['episode_uuid'], 'interrupted')
    assert reloaded.batch(batch_id)['status'] == 'failed'
    assert reloaded.claim() is None
    assert all(row['status'] == 'failed' for row in reloaded.page(batch_id)['items'])


def test_delete_rejects_ingestion_and_preserves_other_project(store):
    activity = store.add_episode({'graph_id': 'first', 'type': 'text', 'data': '小橙公告活動'})
    with pytest.raises(ServiceError, match='處理'):
        store.check_delete('first')
    store.claim()
    store.finish(activity['episode_uuid'])
    store.check_delete('first')
    store.delete_graph('first')
    with pytest.raises(ServiceError) as error:
        store.episode(activity['episode_uuid'])
    assert error.value.status == 404
    assert store.graph('second')['name'] == '第二個專案'


def test_source_time_metadata_and_pagination_survive_restart(store):
    batch_id = batch(store, count=3)
    source = item()
    source['created_at'] = '2026-10-02T10:20:00+10:00'
    receipt = store.add_items(batch_id, [source, item('小藍希望安靜'), item('小紫想認識鄰居')])
    restarted = Store(store.path)
    page = restarted.page(batch_id, limit=2)
    assert page['next_cursor'] == 2
    assert restarted.page(batch_id, limit=2, cursor=2)['items'][0]['episode_uuid'] == receipt[-1]['episode_uuid']
    assert page['items'][0]['created_at'] == source['created_at']
    assert page['items'][0]['metadata'] == source['metadata']
    assert page['items'][0]['source_description'] == 'test document'


class FakeRuntime(Runtime):
    ready, error = True, None
    embedder = SimpleNamespace(dimension=384)

    def __init__(self, store):
        self.store = store
        self._graph_model_settings = {}
        self._model_settings_lock = threading.RLock()

    def call(self, operation, *args):
        return operation(*args)

    def database_health(self):
        return True

    def page(self, graph_id, kind, limit, cursor):
        if cursor is None:
            return [{'uuid_': 'b', 'name': '小橙', 'attributes': {'role': '店主'}, 'labels': ['Entity', 'Person']}], 'b'
        return [{'uuid_': 'a', 'name': '小青', 'attributes': {}, 'labels': ['Entity', 'Person']}], None

    def search(self, graph_id, query, limit, scope, reranker):
        return {'nodes': [], 'edges': [{'uuid_': 'e', 'fact': '小橙經營咖啡店', 'episodes': ['episode'],
                                      'attributes': {'source': 'test'}}]}


@pytest.fixture
def service(store):
    app = create_service(store, FakeRuntime(store), 'local-test-key')
    client = app.test_client()

    def transport(request):
        response = client.open(request.url.raw_path.decode(), method=request.method,
                               data=request.content, headers=dict(request.headers))
        return httpx.Response(response.status_code, headers=dict(response.headers), content=response.data)

    with model_settings_snapshot({'provider': 'custom', 'base_url': 'http://127.0.0.1:9001/v1',
                                  'model': 'fixture-model', 'api_key': 'synthetic-model-key'}):
        yield GraphitiClient('http://graphiti.test', 'local-test-key', transport=httpx.MockTransport(transport)), client


def test_local_http_adapter_keeps_paging_attributes_search_and_batch_contract(service, store):
    adapter, _ = service
    nodes = fetch_all_nodes(adapter, 'first', page_size=1)
    assert [node.name for node in nodes] == ['小橙', '小青']
    assert nodes[0].attributes == {'role': '店主'}
    result = adapter.graph.search(graph_id='first', query='咖啡店', scope='edges', limit=2, reranker='cross_encoder')
    assert result.edges[0].fact == '小橙經營咖啡店'
    assert result.edges[0].episodes == ['episode']
    batch_id = adapter.batch.create(metadata={'graph_id': 'first', 'chunk_count': 1}).batch_id
    receipts = adapter.batch.add(batch_id, [BatchAddItem(**item())])
    assert receipts[0].processed is False
    adapter.batch.process(batch_id)
    store.finish(store.claim()['episode_uuid'])
    assert adapter.batch.get(batch_id).progress.percent_complete == 100
    assert adapter.batch.list_items(batch_id).items[0].status == 'succeeded'


def test_failed_memory_surfaces_error_and_missing_graph_is_not_empty(service, store):
    adapter, _ = service
    episode = adapter.graph.add(graph_id='first', type='text', data='小橙公告活動')
    store.claim()
    store.finish(episode.uuid_, 'extraction failed')
    with pytest.raises(ApiError) as error:
        adapter.graph.episode.get(episode.uuid_)
    assert error.value.status_code == 422
    with pytest.raises(NotFoundError):
        adapter.graph.get('absent')


def test_service_requires_authentication_and_refuses_bad_ontology(service):
    _, client = service
    assert client.get('/graphs/first').status_code == 401
    response = client.put('/ontology', json={'graph_ids': ['first'], 'ontology': {'entity_types': [{'name': 'bad-label'}]}},
                          headers={'Authorization': 'Bearer local-test-key'})
    assert response.status_code == 400
    assert 'local-test-key' not in response.get_data(as_text=True)


def test_selected_local_provider_needs_no_zep_key_and_never_calls_cloud(monkeypatch):
    from app.utils import zep
    monkeypatch.setattr(Config, 'GRAPH_PROVIDER', 'graphiti')
    monkeypatch.setattr(Config, 'ZEP_API_KEY', '')
    monkeypatch.setattr(Config, 'GRAPHITI_BASE_URL', 'http://graphiti:5010')
    monkeypatch.setattr(Config, 'GRAPHITI_API_KEY', 'test-key')
    monkeypatch.setattr(zep, 'Zep', lambda **_: pytest.fail('Cloud client must not be constructed'))
    clear_zep_client_cache()
    assert isinstance(get_zep_client(), GraphitiClient)
    assert Config.graph_configuration_errors() == []
    clear_zep_client_cache()


def test_ontology_conversion_preserves_roles_attributes_and_relationship_constraints(service, monkeypatch):
    from app.services.graph_builder import GraphBuilderService
    from app.local_graph.runtime import ontology_models
    adapter, _ = service
    builder = object.__new__(GraphBuilderService)
    builder.client = adapter
    builder.set_ontology('first', {
        'entity_types': [{'name': 'Person', 'description': '參加者', 'attributes': [{'name': 'role', 'description': '角色'}]}],
        'edge_types': [{'name': 'KNOWS', 'description': '互相認識', 'attributes': [],
                        'source_targets': [{'source': 'Person', 'target': 'Person'}]}],
    })
    ontology = adapter.graph.get('first').ontology
    entities, edges, mapping = ontology_models(ontology)
    assert entities['Person'].__doc__ == '參加者'
    assert entities['Person'].model_fields['role'].description == '角色'
    assert ('Person', 'Person') in mapping
    assert mapping[('Person', 'Person')] == ['KNOWS']
    assert 'KNOWS' in edges
