"""Source namespace copying: fixtures by default, isolated Neo4j only on opt-in."""
import asyncio
from copy import deepcopy
import os
import threading
from types import SimpleNamespace
import uuid

import pytest

from app.local_graph.namespace_clone import prepare_records, mapped_uuid, copy_transaction
from app.local_graph.runtime import Runtime
from app.local_graph.store import Store, ServiceError

SETTINGS = {'provider': 'custom', 'base_url': 'http://127.0.0.1:9001/v1',
            'model': 'fixture-model', 'api_key': 'synthetic-clone-model-key'}


def records(group='source'):
    nodes = [
        {'labels': ['Entity', 'Person'], 'props': {'uuid': 'a', 'group_id': group, 'name': '甲', 'summary': 'source', 'name_embedding': [.1, .2]}},
        {'labels': ['Entity'], 'props': {'uuid': 'b', 'group_id': group, 'name': '乙', 'name_embedding': [.3, .4]}},
        {'labels': ['Episodic'], 'props': {'uuid': 'episode', 'group_id': group, 'source_description': 'source document',
                                         'content': '合成來源', 'entity_edges': ['edge'], 'mirofish_metadata': '{"source":"document"}'}},
    ]
    edges = [
        {'type': 'RELATES_TO', 'source': 'a', 'target': 'b', 'props': {'uuid': 'edge', 'group_id': group,
         'source_uuid': 'a', 'target_uuid': 'b', 'fact': '合成關係', 'fact_embedding': [.5, .6], 'episodes': ['episode']}},
        {'type': 'MENTIONS', 'source': 'episode', 'target': 'a', 'props': {'uuid': 'mention', 'group_id': group}},
    ]
    return nodes, edges


def engine(store):
    value = object.__new__(Runtime)
    value.store = store
    value._graph_model_settings = {}
    value._model_settings_lock = threading.RLock()
    return value


def test_copy_rekeys_structural_references_and_preserves_embeddings_without_mutating_source():
    nodes, edges = records()
    original = deepcopy((nodes, edges))
    copied_nodes, copied_edges, digest = prepare_records('source', 'target', nodes, edges)
    assert (nodes, edges) == original
    assert len(digest) == 64
    assert copied_nodes[0]['props']['name_embedding'] == [.1, .2]
    assert copied_edges[0]['props']['fact_embedding'] == [.5, .6]
    assert copied_nodes[2]['props']['entity_edges'] == [mapped_uuid('target', 'edge', 'edge')]
    assert copied_edges[0]['props']['episodes'] == [mapped_uuid('target', 'episode')]
    assert copied_edges[0]['props']['source_uuid'] == copied_nodes[0]['props']['uuid']
    assert copied_edges[0]['props']['target_uuid'] == copied_nodes[1]['props']['uuid']
    assert all(row['props']['group_id'] == 'target' for row in copied_nodes + copied_edges)
    other_nodes, _, _ = prepare_records('source', 'other', nodes, edges)
    assert {row['props']['uuid'] for row in copied_nodes}.isdisjoint(row['props']['uuid'] for row in other_nodes)


@pytest.mark.parametrize('damage', ['simulation', 'cross_group', 'missing_reference', 'unknown_type', 'unsafe_label'])
def test_unsafe_or_polluted_sources_cannot_be_cloned(damage):
    nodes, edges = records()
    if damage == 'simulation':
        nodes[-1]['props']['mirofish_metadata'] = '{"source":"mirofish_simulation"}'
    elif damage == 'cross_group':
        edges[0]['target'] = 'another_graph_node'
    elif damage == 'missing_reference':
        edges[0]['props']['episodes'] = ['missing_episode']
    elif damage == 'unknown_type':
        edges[0]['type'] = 'UNSUPPORTED'
    else:
        nodes[0]['labels'] = ['Entity', 'A` MATCH(n) DELETE n']
    with pytest.raises(ServiceError):
        prepare_records('source', 'target', nodes, edges)


def test_store_clone_receipt_is_idempotent_and_freezes_source(tmp_path):
    store = Store(tmp_path / 'state.sqlite')
    store.create_graph('source', '合成來源')
    fingerprint = Runtime.settings_fingerprint(SETTINGS)
    receipt = store.begin_clone('source', 'target', 'operation', fingerprint)
    assert store.begin_clone('source', 'target', 'operation', fingerprint) == receipt
    with pytest.raises(ServiceError):
        store.begin_clone('source', 'different-target', 'operation', fingerprint)
    with pytest.raises(ServiceError, match='唯讀'):
        store.add_episode({'graph_id': 'source', 'type': 'text', 'data': 'must not mutate source'})
    with pytest.raises(ServiceError):
        store.add_episode({'graph_id': 'target', 'type': 'text', 'data': 'not ready'})
    with pytest.raises(ServiceError):
        store.check_delete('source')
    with pytest.raises(ServiceError):
        store.check_delete('target')
    summary = {'node_count': 3, 'edge_count': 2, 'source_digest': 'fixture'}
    ready = store.finish_clone('operation', summary)
    assert ready['status'] == 'ready'
    assert store.finish_clone('operation', summary) == ready
    store.add_episode({'graph_id': 'target', 'type': 'text', 'data': 'isolated event'})
    assert store.graph('source')['name'] == '合成來源'
    with pytest.raises(ServiceError, match='執行副本'):
        store.begin_clone('target', 'nested-run', 'nested-operation', fingerprint)


@pytest.mark.parametrize('status,metadata', [('queued', {}), ('failed', {}), ('succeeded', {'source': 'mirofish_simulation'})])
def test_store_refuses_incomplete_or_simulation_polluted_source_before_target_creation(tmp_path, status, metadata):
    store = Store(tmp_path / 'state.sqlite')
    store.create_graph('source', '合成來源')
    job = store.add_episode({'graph_id': 'source', 'type': 'text', 'data': 'fixture', 'metadata': metadata})
    if status != 'queued':
        store.finish(job['uuid'], 'failure' if status == 'failed' else None)
    with pytest.raises(ServiceError):
        store.begin_clone('source', 'target', 'operation', Runtime.settings_fingerprint(SETTINGS))
    with pytest.raises(ServiceError) as error:
        store.graph('target')
    assert error.value.status == 404


def test_lost_sqlite_completion_remains_reviewable_and_retry_reconciles(tmp_path, monkeypatch):
    store = Store(tmp_path / 'state.sqlite')
    store.create_graph('source', '合成來源')
    value = engine(store)
    summary = {'node_count': 3, 'edge_count': 2, 'source_digest': 'fixture'}
    calls = []
    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def execute_write(self, operation, *args):
            calls.append(args)
            return summary
    async def noop(*args, **kwargs):
        return []
    value.graphiti = SimpleNamespace(driver=SimpleNamespace(execute_query=noop, session=Session))
    finish = store.finish_clone
    def interrupted(*args):
        raise OSError('synthetic interruption after graph transaction')
    monkeypatch.setattr(store, 'finish_clone', interrupted)
    with pytest.raises(ServiceError):
        asyncio.run(value.clone('source', 'target', 'operation', SETTINGS))
    assert store.clone_receipt('operation')['status'] == 'needs_review'
    monkeypatch.setattr(store, 'finish_clone', finish)
    ready = asyncio.run(value.clone('source', 'target', 'operation', SETTINGS))
    assert ready['status'] == 'ready'
    assert len(calls) == 2
    assert asyncio.run(value.clone('source', 'target', 'operation', SETTINGS)) == ready
    assert len(calls) == 2


@pytest.mark.skipif(not os.environ.get('MIROFISH_CLONE_TEST_NEO4J'), reason='requires a dedicated isolated Neo4j fixture container')
def test_real_isolated_neo4j_transaction_mapping_recovery_and_parent_isolation(tmp_path, monkeypatch):
    from neo4j import AsyncGraphDatabase
    uri = os.environ['MIROFISH_CLONE_TEST_NEO4J']
    assert uri == 'bolt://127.0.0.1:7687', 'Only the isolated container loopback fixture is allowed'
    async def exercise():
        driver = AsyncGraphDatabase.driver(uri, auth=None)
        suffix = uuid.uuid4().hex
        source, target, second = (f'fixture_{prefix}_{suffix}' for prefix in ('source', 'target', 'second'))
        operation = f'fixture_op_{suffix}'
        nodes, edges = records(source)
        try:
            await driver.execute_query('''UNWIND $nodes AS row CREATE (n:Entity) SET n=row.props''', nodes=nodes[:2])
            await driver.execute_query('CREATE (n:Episodic) SET n=$props', props=nodes[2]['props'])
            await driver.execute_query('''MATCH (a:Entity {uuid:'a',group_id:$group}), (b:Entity {uuid:'b',group_id:$group})
                CREATE (a)-[r:RELATES_TO]->(b) SET r=$props''', group=source, props=edges[0]['props'])
            await driver.execute_query('''MATCH (a:Episodic {uuid:'episode',group_id:$group}), (b:Entity {uuid:'a',group_id:$group})
                CREATE (a)-[r:MENTIONS]->(b) SET r=$props''', group=source, props=edges[1]['props'])
            store = Store(tmp_path / 'real.sqlite')
            store.create_graph(source, '合成来源')
            value = engine(store)
            value.graphiti = SimpleNamespace(driver=driver)
            finish = store.finish_clone
            monkeypatch.setattr(store, 'finish_clone', lambda *_: (_ for _ in ()).throw(OSError('after commit')))
            with pytest.raises(ServiceError):
                await value.clone(source, target, operation, SETTINGS)
            assert store.clone_receipt(operation)['status'] == 'needs_review'
            monkeypatch.setattr(store, 'finish_clone', finish)
            receipt = await value.clone(source, target, operation, SETTINGS)
            assert receipt['status'] == 'ready' and receipt['summary']['node_count'] == 3
            assert await value.clone(source, target, operation, SETTINGS) == receipt
            copied, _, _ = await driver.execute_query('MATCH (n {group_id:$target}) RETURN n.uuid AS uuid,n.name_embedding AS vector', target=target)
            assert len(copied) == 3
            assert {row['uuid'] for row in copied} == {mapped_uuid(target, old) for old in ('a', 'b', 'episode')}
            assert any(row['vector'] == [.1, .2] for row in copied)
            relationships, _, _ = await driver.execute_query('''MATCH (a)-[r:RELATES_TO {group_id:$target}]->(b)
                RETURN a.uuid AS source,b.uuid AS target,r.episodes AS episodes,r.fact_embedding AS vector''', target=target)
            assert relationships[0]['episodes'] == [mapped_uuid(target, 'episode')]
            assert relationships[0]['source'] == mapped_uuid(target, 'a')
            assert relationships[0]['vector'] == [.5, .6]
            await driver.execute_query('MATCH(n {group_id:$target,uuid:$uuid}) SET n.summary="target changed"', target=target, uuid=mapped_uuid(target, 'a'))
            original, _, _ = await driver.execute_query('MATCH(n {group_id:$source,uuid:"a"}) RETURN n.summary AS summary', source=source)
            assert original[0]['summary'] == 'source'
            async with driver.session() as session:
                with pytest.raises(ServiceError, match='已變更'):
                    await session.execute_write(copy_transaction, source, target, operation, Runtime.settings_fingerprint(SETTINGS))
            # Prove a failure after all copy statements rolls back nodes and receipt.
            async def rollback(tx):
                await copy_transaction(tx, source, second, operation + '_rollback', Runtime.settings_fingerprint(SETTINGS))
                raise RuntimeError('synthetic failure before commit')
            async with driver.session() as session:
                with pytest.raises(RuntimeError, match='before commit'):
                    await session.execute_write(rollback)
            rolled_back, _, _ = await driver.execute_query('MATCH(n {group_id:$group}) RETURN count(n) AS count', group=second)
            assert rolled_back[0]['count'] == 0
        finally:
            # Only synthetic namespace IDs from this test are deleted.
            await driver.execute_query('MATCH(n) WHERE n.group_id IN $groups DETACH DELETE n', groups=[source, target, second])
            await driver.execute_query('MATCH(n:MiroFishCloneReceipt) WHERE n.operation_id IN $operations DELETE n', operations=[operation, operation + '_rollback'])
            await driver.close()
    asyncio.run(exercise())
