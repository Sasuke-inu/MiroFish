"""Private HTTP service for Graphiti. Published only on the Compose network."""

import hmac
import logging
import os
import re
import threading
from concurrent.futures import TimeoutError as FutureTimeout

from flask import Flask, jsonify, request, g

from .store import ServiceError, Store


def create_service(store, runtime, api_key):
    app = Flask('mirofish-graphiti')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.json.ensure_ascii = False
    mutation_lock = threading.RLock()

    @app.before_request
    def guard():
        if request.path == '/health':
            return
        supplied = request.headers.get('Authorization', '')
        if not api_key or not hmac.compare_digest(supplied, f'Bearer {api_key}'):
            raise ServiceError('圖譜服務驗證失敗', 401)
        if not runtime.ready:
            raise ServiceError(runtime.error or '本機圖譜正在準備', 503)
        if request.method != 'GET':
            mutation_lock.acquire()
            g.mutation_lock = True

    @app.teardown_request
    def release_lock(_error):
        if g.pop('mutation_lock', False):
            mutation_lock.release()

    @app.errorhandler(ServiceError)
    def service_error(error):
        return jsonify({'message': str(error)}), error.status

    @app.errorhandler(FutureTimeout)
    def operation_timeout(_error):
        return jsonify({'message': '圖譜操作逾時；寫入結果請先查詢確認，避免重複提交'}), 504

    @app.errorhandler(Exception)
    def unexpected(error):
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            return jsonify({'message': error.description}), error.code
        app.logger.exception('Local graph request failed')
        return jsonify({'message': '本機圖譜操作失敗，請查看圖譜服務紀錄'}), 500

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise ServiceError('請提供 JSON 物件')
        return value

    def pagination():
        try:
            limit = int(request.args.get('limit', 100))
            cursor = int(request.args.get('cursor', 0))
        except ValueError:
            raise ServiceError('無效的分頁設定')
        return limit, cursor

    @app.get('/health')
    def health():
        if not runtime.ready:
            return jsonify({'status': 'starting', 'error': runtime.error}), 503
        try:
            runtime.call(runtime.database_health)
        except Exception:
            return jsonify({'status': 'unavailable'}), 503
        return jsonify({'status': 'ok', 'provider': 'graphiti', 'embedding': 'local',
                        'embedding_dimension': getattr(runtime.embedder, 'dimension', None),
                        'telemetry_enabled': os.environ.get('GRAPHITI_TELEMETRY_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')})

    @app.post('/graphs')
    def create_graph():
        value = body()
        if not isinstance(value.get('name'), str) or not value['name'].strip():
            raise ServiceError('圖譜名稱不能空白')
        snapshot = runtime.private_settings(value.pop('model_snapshot', None)) if 'model_snapshot' in value else None
        graph_id = value.get('graph_id')
        store.create_graph(graph_id, value['name'], value.get('description') or '')
        runtime.bind_graph_settings(graph_id, snapshot)
        return jsonify(store.graph(graph_id))

    @app.get('/graphs/<graph_id>')
    def graph(graph_id):
        return jsonify(store.graph(graph_id))

    @app.post('/graphs/<graph_id>/clone')
    def clone_graph(graph_id):
        value = body()
        return jsonify(runtime.call(runtime.clone, graph_id, value.get('graph_id'),
                                    value.get('operation_id'), value.pop('model_snapshot', None)))

    @app.get('/graph-clones/<operation_id>')
    def clone_receipt(operation_id):
        return jsonify(store.clone_receipt(operation_id))

    @app.delete('/graphs/<graph_id>')
    def delete(graph_id):
        store.graph(graph_id)
        return jsonify(runtime.call(runtime.delete, graph_id))

    @app.put('/ontology')
    def ontology():
        value = body()
        graph_ids, ontology = value.get('graph_ids'), value.get('ontology')
        if not isinstance(graph_ids, list) or not graph_ids or not isinstance(ontology, dict):
            raise ServiceError('圖譜和類型資料不完整')
        for key in ('entity_types', 'edge_types'):
            definitions = ontology.get(key, [])
            if not isinstance(definitions, list) or len(definitions) > 10:
                raise ServiceError('每種對象或關係最多 10 個類型')
            names = set()
            for definition in definitions:
                name = definition.get('name', '')
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or name in names:
                    raise ServiceError('類型名稱必須唯一，使用英文字母、數字或底線')
                names.add(name)
                for attr in definition.get('attributes', []):
                    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', attr.get('name', '')):
                        raise ServiceError('無效的類型欄位名稱')
        return jsonify(store.set_ontology(graph_ids, ontology))

    @app.get('/graphs/<graph_id>/<kind>')
    def graph_items(graph_id, kind):
        store.graph(graph_id)
        if kind not in ('nodes', 'edges'):
            raise ServiceError('不支援的圖譜資料', 404)
        try:
            limit = int(request.args.get('limit', 100))
        except ValueError:
            raise ServiceError('無效的分頁設定')
        if not 1 <= limit <= 100:
            raise ServiceError('每頁最多 100 筆資料')
        values, cursor = runtime.call(runtime.page, graph_id, kind, limit, request.args.get('cursor'))
        response = jsonify(values)
        if cursor:
            response.headers['zep-next-cursor'] = cursor
        return response

    @app.get('/nodes/<uuid>')
    def node(uuid):
        return jsonify(runtime.call(runtime.item, 'nodes', uuid))

    @app.get('/edges/<uuid>')
    def edge(uuid):
        return jsonify(runtime.call(runtime.item, 'edges', uuid))

    @app.get('/nodes/<uuid>/edges')
    def node_edges(uuid):
        return jsonify(runtime.call(runtime.node_edges, uuid))

    @app.post('/episodes')
    def add_episode():
        value = body()
        snapshot = value.pop('model_snapshot', None)
        runtime.bind_graph_settings(value.get('graph_id'), snapshot)
        return jsonify(store.add_episode(value))

    @app.get('/episodes/<uuid>')
    def episode(uuid):
        result = store.episode(uuid)
        if result['status'] == 'failed':
            raise ServiceError(f'記憶處理失敗：{result["error"]}', 422)
        return jsonify(result)

    @app.post('/search')
    def search():
        value = body()
        graph_id, query, scope = value.get('graph_id'), value.get('query'), value.get('scope', 'edges')
        store.graph(graph_id)
        if not isinstance(query, str) or not query.strip() or len(query) > 400:
            raise ServiceError('搜尋文字必須介於 1 至 400 字')
        try:
            limit = int(value.get('limit', 10))
        except (ValueError, TypeError):
            raise ServiceError('無效的搜尋筆數')
        reranker = value.get('reranker', 'rrf')
        if scope not in ('nodes', 'edges') or not 1 <= limit <= 50 or reranker not in ('rrf', 'cross_encoder'):
            raise ServiceError('無效的搜尋設定')
        return jsonify(runtime.call(runtime.search, graph_id, query.strip(), limit, scope, reranker))

    @app.post('/batches')
    def create_batch():
        value = body()
        metadata = value.get('metadata', {})
        if not isinstance(metadata, dict):
            raise ServiceError('資料批次的附加資訊格式不正確')
        runtime.bind_graph_settings(metadata.get('graph_id'), value.pop('model_snapshot', None))
        return jsonify(store.create_batch(metadata))

    @app.get('/batches')
    def list_batches():
        limit, cursor = pagination()
        return jsonify(store.page(limit=limit, cursor=cursor))

    @app.get('/batches/<batch_id>')
    def batch(batch_id):
        return jsonify(store.batch(batch_id))

    @app.post('/batches/<batch_id>/items')
    def add_items(batch_id):
        return jsonify(store.add_items(batch_id, body().get('items')))

    @app.get('/batches/<batch_id>/items')
    def list_items(batch_id):
        limit, cursor = pagination()
        return jsonify(store.page(batch_id, limit=limit, cursor=cursor))

    @app.post('/batches/<batch_id>/process')
    def process(batch_id):
        runtime.settings_for_graph(store.batch(batch_id)['graph_id'])
        return jsonify(store.process(batch_id))

    return app


def main():
    from waitress import serve
    from .runtime import Runtime
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    key = os.environ.get('GRAPHITI_API_KEY', '')
    if not key:
        raise RuntimeError('GRAPHITI_API_KEY must be configured')
    store = Store(os.environ.get('GRAPHITI_STATE_PATH', '/app/backend/graphiti-state/journal.sqlite'))
    runtime = Runtime(store)
    serve(create_service(store, runtime, key), host='0.0.0.0', port=5010, threads=8)
