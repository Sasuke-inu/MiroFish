"""HTTP adapter for MiroFish's local Graphiti service.

Only the application-facing Zep shapes are retained. No requests are sent to
Zep Cloud, and ontology models are converted to provider-neutral definitions.
"""

from functools import lru_cache
import ipaddress
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

import httpx
from zep_cloud import NotFoundError
from zep_cloud.core.api_error import ApiError
from ..provider_settings import get_model_settings


def _record(value):
    if isinstance(value, list):
        return [_record(item) for item in value]
    if not isinstance(value, dict):
        return value
    # Attributes and metadata must remain dictionaries for existing callers.
    return SimpleNamespace(**{
        key: item if key in {'attributes', 'metadata', 'ontology', 'error', 'node_mapping'} else _record(item)
        for key, item in value.items()
    })


def _path(value):
    return quote(str(value), safe='')


def _model_snapshot(stage=None):
    value = get_model_settings(stage=stage)
    return {key: value[key] for key in ('provider', 'base_url', 'model', 'api_key')}


def _private_service_endpoint(value, *, mocked=False):
    """Model keys may only cross the configured local Graphiti boundary."""
    try:
        if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 33 for char in value) or '\\' in value:
            raise ValueError()
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        valid_port = parts.port is None or 0 < parts.port < 65536
        if (parts.scheme not in {'http', 'https'} or not host or not valid_port or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment or parts.path not in {'', '/'}):
            raise ValueError()
        allowed = host in {'graphiti', 'localhost', 'host.docker.internal', 'gateway.docker.internal'}
        try:
            address = ipaddress.ip_address(host)
            allowed = allowed or address.is_loopback or any(address in network for network in (
                ipaddress.ip_network('10.0.0.0/8'), ipaddress.ip_network('172.16.0.0/12'),
                ipaddress.ip_network('192.168.0.0/16'), ipaddress.ip_network('fc00::/7')))
        except ValueError:
            pass
        if not allowed and not mocked:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Graphiti must use an explicitly local service endpoint without URL credentials') from None


def _model_definition(name, model):
    return {
        'name': name,
        'description': model.__doc__ or name,
        'attributes': [
            {'name': key, 'description': field.description or key}
            for key, field in model.model_fields.items()
        ],
    }


class GraphitiClient:
    def __init__(self, base_url, api_key, timeout=60, *, transport=None):
        if float(timeout) <= 0:
            raise ValueError('Graphiti request timeout must be greater than 0')
        _private_service_endpoint(base_url, mocked=isinstance(transport, httpx.MockTransport))
        self.http = httpx.Client(
            base_url=base_url.rstrip('/'), timeout=float(timeout), transport=transport,
            headers={'Authorization': f'Bearer {api_key}'}, trust_env=False, follow_redirects=False,
        )
        self.graph = _Graph(self)
        self.batch = _Batch(self)

    def request(self, method, path, *, json=None, params=None, raw=False):
        response = self.http.request(method, path, json=json, params=params)
        if response.is_redirect:
            raise ApiError(status_code=response.status_code, body={'message': 'Graphiti service redirects are not allowed'})
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {'message': f'Graphiti returned HTTP {response.status_code}'}
            # A faulty service must not echo model credentials into ApiError,
            # whose string is sometimes logged by existing backend callers.
            private = (json or {}).get('model_snapshot', {})
            secrets = [private.get('api_key'), self.http.headers.get('Authorization', '').removeprefix('Bearer ')]
            def safe(value):
                if isinstance(value, dict):
                    return {key: safe(item) for key, item in value.items()
                            if key.lower() not in {'model_snapshot', 'api_key', 'authorization', 'balance_api_key'}}
                if isinstance(value, list):
                    return [safe(item) for item in value]
                if isinstance(value, str):
                    for secret in secrets:
                        if secret:
                            value = value.replace(secret, '[REDACTED]')
                return value
            body = safe(body)
            headers = safe({key: value for key, value in response.headers.items()
                            if key.lower() in {'retry-after', 'content-type'}})
            if response.status_code == 404:
                raise NotFoundError(body=body, headers=headers)
            raise ApiError(status_code=response.status_code, body=body, headers=headers)
        data = response.json()
        if raw:
            return SimpleNamespace(data=_record(data), headers=dict(response.headers))
        return _record(data)


class _Items:
    def __init__(self, client, kind):
        self.client, self.kind = client, kind
        self.with_raw_response = SimpleNamespace(get_by_graph_id=self._raw_page)

    def get_by_graph_id(self, graph_id, *, limit=100, cursor=None):
        return self._raw_page(graph_id, limit=limit, cursor=cursor).data

    def _raw_page(self, graph_id, *, limit=100, cursor=None):
        return self.client.request('GET', f'/graphs/{_path(graph_id)}/{self.kind}',
                                   params={'limit': limit, **({'cursor': cursor} if cursor else {})}, raw=True)

    def get(self, uuid_):
        return self.client.request('GET', f'/{self.kind}/{_path(uuid_)}')

    def get_edges(self, node_uuid):
        return self.client.request('GET', f'/nodes/{_path(node_uuid)}/edges')


class _Graph:
    def __init__(self, client):
        self.client = client
        self.node, self.edge, self.episode = (_Items(client, kind) for kind in ('nodes', 'edges', 'episodes'))

    def create(self, **kwargs):
        return self.client.request('POST', '/graphs', json={**kwargs, 'model_snapshot': _model_snapshot()})

    def get(self, graph_id):
        return self.client.request('GET', f'/graphs/{_path(graph_id)}')

    def clone(self, source_graph_id, *, graph_id, operation_id):
        return self.client.request('POST', f'/graphs/{_path(source_graph_id)}/clone',
                                   json={'graph_id': graph_id, 'operation_id': operation_id,
                                         'model_snapshot': _model_snapshot(stage='simulation')})

    def clone_receipt(self, operation_id):
        return self.client.request('GET', f'/graph-clones/{_path(operation_id)}')

    def delete(self, graph_id):
        return self.client.request('DELETE', f'/graphs/{_path(graph_id)}')

    def set_ontology(self, graph_ids, entities, edges=None):
        definitions = []
        for name, (model, pairs) in (edges or {}).items():
            definition = _model_definition(name, model)
            definition['source_targets'] = [{'source': pair.source, 'target': pair.target} for pair in pairs]
            definitions.append(definition)
        ontology = {'entity_types': [_model_definition(name, model) for name, model in entities.items()],
                    'edge_types': definitions}
        return self.client.request('PUT', '/ontology', json={'graph_ids': graph_ids, 'ontology': ontology})

    def add(self, **kwargs):
        return self.client.request('POST', '/episodes', json={**kwargs, 'model_snapshot': _model_snapshot()})

    def search(self, **kwargs):
        return self.client.request('POST', '/search', json=kwargs)


class _Batch:
    def __init__(self, client):
        self.client = client

    def create(self, *, metadata):
        return self.client.request('POST', '/batches', json={'metadata': metadata, 'model_snapshot': _model_snapshot()})

    def add(self, batch_id, items):
        return self.client.request('POST', f'/batches/{_path(batch_id)}/items',
                                   json={'items': [item.model_dump(mode='json', exclude_none=True) for item in items]})

    def process(self, batch_id):
        return self.client.request('POST', f'/batches/{_path(batch_id)}/process')

    def get(self, batch_id):
        return self.client.request('GET', f'/batches/{_path(batch_id)}')

    def list(self, *, limit=100, cursor=None):
        return self.client.request('GET', '/batches', params={'limit': limit, **({'cursor': cursor} if cursor is not None else {})})

    def list_items(self, batch_id, *, limit=100, cursor=None):
        return self.client.request('GET', f'/batches/{_path(batch_id)}/items',
                                   params={'limit': limit, **({'cursor': cursor} if cursor is not None else {})})


@lru_cache(maxsize=4)
def get_graphiti_client(base_url, api_key, timeout=60):
    return GraphitiClient(base_url, api_key, timeout)


def clear_graphiti_client_cache():
    get_graphiti_client.cache_clear()
