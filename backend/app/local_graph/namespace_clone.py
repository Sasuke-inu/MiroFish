"""Copy a saved Graphiti namespace without generating text or embeddings."""
from collections import defaultdict
import hashlib
import json
import re
import uuid

from .store import ServiceError

MAX_NODES = 10_000
MAX_EDGES = 50_000
RELATION_TYPES = {'RELATES_TO', 'MENTIONS', 'HAS_MEMBER'}


def mapped_uuid(target_graph_id, original_uuid, kind='node'):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'mirofish:{target_graph_id}:{kind}:{original_uuid}'))


def records_digest(nodes, edges):
    canonical = {'nodes': sorted([dict(row, labels=sorted(row['labels'])) for row in nodes], key=lambda row: row['props']['uuid']),
                 'edges': sorted(edges, key=lambda row: row['props']['uuid'])}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def prepare_records(source_graph_id, target_graph_id, nodes, edges):
    """Validate persisted shapes and remap every structural UUID reference."""
    if source_graph_id == target_graph_id or not nodes or len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ServiceError('來源圖譜為空、超過複製上限，或目標與來源相同', 409)
    node_ids, edge_ids = set(), set()
    for node in nodes:
        props, labels = node['props'], node['labels']
        identity = props.get('uuid')
        if (not isinstance(identity, str) or not identity or identity in node_ids
                or props.get('group_id') != source_graph_id
                or not set(labels).intersection({'Entity', 'Episodic', 'Community'})
                or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', label) for label in labels)):
            raise ServiceError('來源節點識別、群組或類型無法安全複製', 409)
        node_ids.add(identity)
        if 'Episodic' in labels:
            metadata = props.get('mirofish_metadata') or '{}'
            try:
                metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
            except ValueError:
                raise ServiceError('來源記憶的來源資訊需要核對', 409) from None
            if (not isinstance(metadata, dict) or metadata.get('source') == 'mirofish_simulation'
                    or props.get('source_description') == 'MiroFish simulation activity batch'):
                raise ServiceError('來源圖譜含有模擬事件，請先建立乾淨的來源圖譜', 409)
    for edge in edges:
        props = edge['props']
        identity = props.get('uuid')
        if (not isinstance(identity, str) or not identity or identity in edge_ids
                or props.get('group_id') != source_graph_id or edge['type'] not in RELATION_TYPES
                or edge['source'] not in node_ids or edge['target'] not in node_ids):
            raise ServiceError('來源關係含有跨群組、缺失或不支援的識別', 409)
        edge_ids.add(identity)

    def remap_list(values, identities, kind):
        if values is None:
            return []
        if not isinstance(values, list) or any(value not in identities for value in values):
            raise ServiceError('來源圖譜有無法定位的內部引用，請核對後重建來源圖譜', 409)
        return [mapped_uuid(target_graph_id, value, kind) for value in values]

    copied_nodes, copied_edges = [], []
    for node in nodes:
        props = dict(node['props'])
        original = props['uuid']
        props.update(uuid=mapped_uuid(target_graph_id, original), group_id=target_graph_id,
                     mirofish_source_uuid=props.get('mirofish_source_uuid', original))
        if 'entity_edges' in props:
            props['entity_edges'] = remap_list(props['entity_edges'], edge_ids, 'edge')
        copied_nodes.append({'labels': sorted(set(node['labels'])), 'props': props})
    for edge in edges:
        props = dict(edge['props'])
        original = props['uuid']
        source = mapped_uuid(target_graph_id, edge['source'])
        target = mapped_uuid(target_graph_id, edge['target'])
        props.update(uuid=mapped_uuid(target_graph_id, original, 'edge'), group_id=target_graph_id,
                     mirofish_source_uuid=props.get('mirofish_source_uuid', original))
        if 'source_uuid' in props:
            props['source_uuid'] = source
        if 'target_uuid' in props:
            props['target_uuid'] = target
        if 'episodes' in props:
            props['episodes'] = remap_list(props['episodes'], node_ids, 'node')
        copied_edges.append({'type': edge['type'], 'source': source, 'target': target, 'props': props})
    return copied_nodes, copied_edges, records_digest(nodes, edges)


async def _rows(tx, query, **parameters):
    result = await tx.run(query, **parameters)
    return await result.data()


async def copy_transaction(tx, source_graph_id, target_graph_id, operation_id, model_fingerprint):
    """Atomic Neo4j write, including a durable receipt for lost SQLite commits."""
    receipts = await _rows(tx, 'MATCH (r:MiroFishCloneReceipt {operation_id:$operation}) RETURN properties(r) AS receipt',
                           operation=operation_id)
    if receipts:
        receipt = receipts[0]['receipt']
        if (receipt.get('source_graph_id') != source_graph_id or receipt.get('target_graph_id') != target_graph_id
                or receipt.get('model_fingerprint') != model_fingerprint or receipt.get('status') != 'ready'):
            raise ServiceError('圖譜複製回條不一致，需人工核對', 409)
        saved_nodes = await _rows(tx, '''MATCH (n {group_id:$target}) RETURN labels(n) AS labels, properties(n) AS props LIMIT $limit''',
                                 target=target_graph_id, limit=MAX_NODES + 1)
        saved_edges = await _rows(tx, '''MATCH (a)-[r]->(b) WHERE a.group_id=$target OR b.group_id=$target
            RETURN type(r) AS type,a.uuid AS source,b.uuid AS target,properties(r) AS props LIMIT $limit''',
                                 target=target_graph_id, limit=MAX_EDGES + 1)
        if (len(saved_nodes) != receipt['node_count'] or len(saved_edges) != receipt['edge_count']
                or records_digest(saved_nodes, saved_edges) != receipt.get('target_digest')):
            raise ServiceError('複製完成後的圖譜已變更，不能當作未使用的複製回條', 409)
        return {**{key: receipt[key] for key in ('node_count', 'edge_count', 'source_digest')},
                'node_mapping': json.loads(receipt['node_mapping'])}
    existing = await _rows(tx, 'MATCH (n {group_id:$target}) RETURN count(n) AS count', target=target_graph_id)
    if existing[0]['count']:
        raise ServiceError('目標圖譜已有資料但沒有完整複製回條，需人工核對', 409)
    nodes = await _rows(tx, '''MATCH (n {group_id:$source})
        RETURN labels(n) AS labels, properties(n) AS props LIMIT $limit''', source=source_graph_id, limit=MAX_NODES + 1)
    edges = await _rows(tx, '''MATCH (a)-[r]->(b) WHERE a.group_id=$source OR b.group_id=$source
        RETURN type(r) AS type, a.uuid AS source, b.uuid AS target, properties(r) AS props LIMIT $limit''',
                       source=source_graph_id, limit=MAX_EDGES + 1)
    copied_nodes, copied_edges, digest = prepare_records(source_graph_id, target_graph_id, nodes, edges)
    grouped_nodes, grouped_edges = defaultdict(list), defaultdict(list)
    for node in copied_nodes:
        grouped_nodes[tuple(node['labels'])].append(node)
    for edge in copied_edges:
        grouped_edges[edge['type']].append(edge)
    for labels, rows in grouped_nodes.items():
        # Only validated identifiers are interpolated; all property data is bound.
        query = f'UNWIND $rows AS row CREATE (n:{":".join(labels)}) SET n=row.props'
        await _rows(tx, query, rows=rows)
    for relationship, rows in grouped_edges.items():
        query = f'''UNWIND $rows AS row MATCH (a {{uuid:row.source, group_id:$target}}),
            (b {{uuid:row.target, group_id:$target}}) CREATE (a)-[r:{relationship}]->(b) SET r=row.props'''
        await _rows(tx, query, rows=rows, target=target_graph_id)
    summary = {'node_count': len(nodes), 'edge_count': len(edges), 'source_digest': digest,
               'node_mapping': {row['props']['uuid']: mapped_uuid(target_graph_id, row['props']['uuid']) for row in nodes}}
    await _rows(tx, '''CREATE (r:MiroFishCloneReceipt {operation_id:$operation})
        SET r.source_graph_id=$source, r.target_graph_id=$target, r.model_fingerprint=$fingerprint,
            r.status='ready', r.node_count=$nodes, r.edge_count=$edges, r.source_digest=$digest,
            r.target_digest=$target_digest, r.node_mapping=$mapping''',
                operation=operation_id, source=source_graph_id, target=target_graph_id, fingerprint=model_fingerprint,
                nodes=summary['node_count'], edges=summary['edge_count'], digest=digest,
                target_digest=records_digest(copied_nodes, copied_edges), mapping=json.dumps(summary['node_mapping']))
    return summary
