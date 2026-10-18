"""Verify real paging, retrieval, source memory and project isolation."""
import json
import os
import sys
from importlib.metadata import version

from neo4j import GraphDatabase

sys.path.insert(0, '/app/backend')
from app.config import Config
from app.utils.zep import get_zep_client
from app.utils.zep_paging import fetch_all_nodes, fetch_all_edges

client = get_zep_client()
graph_id = sys.argv[1]
nodes = fetch_all_nodes(client, graph_id)
edges = fetch_all_edges(client, graph_id)


def pages(kind):
    result, cursor = [], None
    while True:
        page = kind.with_raw_response.get_by_graph_id(graph_id, limit=2, cursor=cursor)
        result.extend(item.uuid_ for item in page.data)
        cursor = page.headers.get('zep-next-cursor')
        if not cursor:
            break
    assert len(result) == len(set(result))
    return result


assert set(pages(client.graph.node)) == {item.uuid_ for item in nodes}
assert set(pages(client.graph.edge)) == {item.uuid_ for item in edges}
edge = edges[0]
for uuid in (edge.source_node_uuid, edge.target_node_uuid):
    assert edge.uuid_ in {item.uuid_ for item in client.graph.node.get_edges(uuid)}
episode = client.graph.episode.get(edge.episodes[0])
assert episode.processed and isinstance(episode.metadata, dict)
assert episode.created_at
found = client.graph.search(graph_id=graph_id, query='橙子小屋與小橙的關係', scope='edges', limit=10, reranker='cross_encoder')
assert found.edges and all(item.group_id == graph_id for item in found.edges)
# A separately created empty test project must not see the fixture's facts.
empty_id = 'mirofish_contract_isolation_test'
client.graph.create(graph_id=empty_id, name='專案隔離測試（虛構）')
assert client.graph.node.get_by_graph_id(empty_id) == []
assert not client.graph.search(graph_id=empty_id, query='橙子小屋', scope='edges', limit=5).edges
client.graph.delete(empty_id)
with GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', os.environ['NEO4J_PASSWORD'])) as driver:
    settings = driver.execute_query("SHOW SETTINGS YIELD name, value WHERE name='dbms.usage_report.enabled' RETURN value").records
    assert settings[0]['value'] == 'false'
    db_version = driver.execute_query('CALL dbms.components() YIELD versions RETURN versions[0] AS version').records[0]['version']
print(json.dumps({'paging': 'passed', 'node_count': len(nodes), 'edge_count': len(edges),
                  'bidirectional_relationships': 'passed', 'source_memory': 'passed',
                  'real_semantic_search': 'passed', 'project_isolation': 'passed',
                  'graphiti_version': version('graphiti-core'), 'neo4j_version': db_version,
                  'neo4j_usage_reports': False, 'zep_key_is_empty': not bool(Config.ZEP_API_KEY)}, indent=2))
