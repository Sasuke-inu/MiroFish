"""One async Graphiti runtime shared by the HTTP service's request threads."""

import asyncio
import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from functools import lru_cache
from contextlib import nullcontext
from typing import Optional

import numpy as np
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.edges import EntityEdge
from graphiti_core.errors import NodeNotFoundError, EdgeNotFoundError, GroupsNodesNotFoundError, GroupsEdgesNotFoundError, EdgesNotFoundError
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EntityNode, EpisodicNode, EpisodeType, Node
from graphiti_core.utils.maintenance.graph_data_operations import retrieve_episodes
from graphiti_core.search.search_config import EdgeReranker, NodeReranker
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pydantic import BaseModel, Field, create_model

from ..config import Config
from ..provider_settings import get_model_settings, model_settings_snapshot, canonical_endpoint, SettingsError
from ..utils.openai_chat_compat import create_chat_completion, extract_chat_completion_text
from ..utils.json_object import unwrap_properties
from .store import ServiceError
from .namespace_clone import copy_transaction

logger = logging.getLogger('mirofish.local_graph')


class RouterLLM(OpenAIGenericClient):
    """Use Graphiti extraction framing without replaying an uncertain paid call."""

    def __init__(self, *args, use_saved_settings=False, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.client, 'max_retries'):
            self.client.max_retries = 0
        self.use_saved_settings = use_saved_settings

    async def _generate_response_with_retry(self, messages, response_model=None, max_tokens=16384, model_size=None):
        # Graphiti's default Tenacity wrapper also repeats generation. Any
        # timeout, server error or invalid result needs an explicit new attempt.
        return await self._generate_response(messages, response_model, max_tokens, model_size)

    async def _generate_response(self, messages, response_model=None, max_tokens=16384, model_size=None):
        parameters = [{'role': message.role, 'content': self._clean_input(message.content)}
                      for message in messages if message.role in ('user', 'system', 'assistant')]
        # Each graph owns a private ContextVar snapshot across every ingestion
        # batch and later simulation episode, including after settings changes.
        settings = get_model_settings() if self.use_saved_settings else None
        context = AsyncOpenAI(api_key=settings['api_key'], base_url=settings['base_url'],
                              timeout=180, max_retries=0,
                              http_client=DefaultAsyncHttpxClient(follow_redirects=False, trust_env=False, timeout=180)) if settings else nullcontext(self.client)
        try:
            async with context as client:
                response = await create_chat_completion(
                    client, model=settings['model'] if settings else self.model, messages=parameters, temperature=self.temperature,
                    max_tokens=max_tokens, response_format=self._build_response_format(response_model),
                )
        except Exception as error:
            # Provider error bodies can contain credentials. Keep a safe status
            # for diagnostics; never send the raw exception to Graphiti tracing.
            status = getattr(error, 'status_code', None)
            raise ServiceError('模型請求結果未確認，已停止自動重試，請核對此執行。',
                               status if isinstance(status, int) and 400 <= status < 600 else 502) from None
        content = extract_chat_completion_text(response)
        if not content:
            raise json.JSONDecodeError('9Router returned empty graph extraction', '', 0)
        value = json.loads(self._strip_code_fences(content))
        if response_model is not None:
            value = unwrap_properties(value, response_model.model_fields)
            # Catch incorrect extraction before it can create incomplete graph data.
            try:
                value = response_model.model_validate(value).model_dump()
            except ValueError as error:
                raise json.JSONDecodeError(f'Invalid graph extraction schema: {error}', content, 0) from error
        return value


class LocalEmbedder(EmbedderClient):
    def __init__(self, model_name=None):
        from sentence_transformers import SentenceTransformer
        import torch
        torch.set_num_threads(int(os.environ.get('EMBEDDING_CPU_THREADS', '4')))
        self.model_name = model_name or os.environ.get(
            'GRAPHITI_EMBEDDING_MODEL', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        # Remote model code is never executed. After the first download, this
        # operates entirely from the persistent model cache.
        self.model = SentenceTransformer(self.model_name, device='cpu', trust_remote_code=False)
        self.dimension = self.model.get_sentence_embedding_dimension()
        self._lock = threading.Lock()

    @lru_cache(maxsize=4096)
    def _encode(self, text):
        with self._lock:
            return self.model.encode(text, normalize_embeddings=True, show_progress_bar=False).tolist()

    async def create(self, input_data):
        if isinstance(input_data, list) and all(isinstance(item, str) for item in input_data):
            input_data = '\n'.join(input_data)
        if not isinstance(input_data, str):
            raise ValueError('Local embeddings require text')
        return await asyncio.to_thread(self._encode, input_data)

    async def create_batch(self, input_data_list):
        if not input_data_list:
            return []
        return [await self.create(text) for text in input_data_list]


class LocalReranker(CrossEncoderClient):
    """Local semantic reranking; no third-party model calls or telemetry."""

    def __init__(self, embedder):
        self.embedder = embedder

    async def rank(self, query, passages):
        query_vector = await self.embedder.create(query)
        vectors = await self.embedder.create_batch(passages)
        return sorted(zip(passages, [float(np.dot(query_vector, vector)) for vector in vectors]),
                      key=lambda item: item[1], reverse=True)


def ontology_models(ontology):
    def models(definitions):
        result = {}
        for definition in definitions:
            model = create_model(definition['name'], __base__=BaseModel, **{
                attribute['name']: (Optional[str], Field(default=None, description=attribute.get('description') or attribute['name']))
                for attribute in definition.get('attributes', [])
            })
            model.__doc__ = definition.get('description') or definition['name']
            result[definition['name']] = model
        return result
    entities = models(ontology.get('entity_types', []))
    edges = models(ontology.get('edge_types', []))
    mapping = {}
    for edge in ontology.get('edge_types', []):
        for pair in edge.get('source_targets', []):
            key = (pair.get('source', 'Entity'), pair.get('target', 'Entity'))
            mapping.setdefault(key, []).append(edge['name'])
    return entities, edges, mapping


def serialize(model):
    value = model.model_dump(mode='json', exclude={'name_embedding', 'fact_embedding'})
    value['uuid_'] = value['uuid']
    value.setdefault('attributes', {})
    return value


class Runtime:
    def __init__(self, store):
        self.store = store
        self.ready = False
        self.error = None
        self._graph_model_settings = {}
        self._model_settings_lock = threading.RLock()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name='graphiti-runtime', daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._initialize())
        self.loop.run_forever()

    async def _initialize(self):
        try:
            self.embedder = await asyncio.to_thread(LocalEmbedder)
            settings = get_model_settings()
            llm = RouterLLM(
                config=LLMConfig(api_key=settings['api_key'], base_url=settings['base_url'],
                                 model=settings['model'], small_model=settings['model']),
                client=AsyncOpenAI(api_key=settings['api_key'] or 'not-configured', base_url=settings['base_url'],
                                   timeout=180, max_retries=0),
                structured_output_mode='json_object',
                use_saved_settings=True,
            )
            self.graphiti = Graphiti(
                os.environ.get('NEO4J_URI', 'bolt://neo4j:7687'), os.environ.get('NEO4J_USER', 'neo4j'),
                os.environ['NEO4J_PASSWORD'], llm_client=llm, embedder=self.embedder,
                cross_encoder=LocalReranker(self.embedder), max_coroutines=2,
            )
            # Neo4jDriver 0.30.2 already starts initialization in its constructor.
            # Await that task instead of racing a second index creation.
            initial_setup = getattr(self.graphiti.driver, '_init_task', None)
            if initial_setup is not None:
                await initial_setup
            else:
                await self.graphiti.build_indices_and_constraints()
            await self.graphiti.driver.execute_query('CALL db.awaitIndexes(60)')
            for job in self.store.interrupted():
                records, _, _ = await self.graphiti.driver.execute_query(
                    'MATCH (n:Episodic {uuid:$uuid,group_id:$group_id}) RETURN n.mirofish_complete AS complete',
                    uuid=job['episode_uuid'], group_id=job['graph_id'], routing_='r')
                if records and records[0]['complete']:
                    self.store.finish(job['episode_uuid'])
                else:
                    # Never replay an ambiguous ingestion after a crash.
                    self.store.finish(job['episode_uuid'], '處理途中服務重啟；請重新建立圖譜以避免重複資料')
            self.ready = True
            logger.info('Local Graphiti ready; embedding dimension=%s', self.embedder.dimension)
            self.loop.create_task(self._worker())
        except Exception as error:
            self.error = '本機圖譜初始化失敗，請查看圖譜服務紀錄'
            logger.error('Graphiti initialization failed (%s)', type(error).__name__)

    @staticmethod
    def private_settings(value):
        """Allow only model credentials, never balance/admin credentials."""
        if not isinstance(value, dict):
            raise ServiceError('模型設定快照格式不正確')
        settings = {key: value.get(key) for key in ('provider', 'base_url', 'model', 'api_key')}
        if any(not isinstance(item, str) or not item.strip() or len(item) > 4096
               or any(ord(char) < 32 for char in item) for item in settings.values()):
            raise ServiceError('模型設定快照不完整或包含無效字元')
        try:
            settings['base_url'] = canonical_endpoint(settings['base_url'])
        except SettingsError:
            raise ServiceError('模型設定快照的服務網址無效') from None
        return settings

    @staticmethod
    def settings_fingerprint(settings):
        value = {key: settings[key] for key in ('provider', 'base_url', 'model')}
        value['api_key_sha256'] = hashlib.sha256(settings['api_key'].encode()).hexdigest()
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def bind_graph_settings(self, graph_id, settings=None):
        """Bind an explicitly submitted graph operation before it can enqueue."""
        private = self.private_settings(get_model_settings() if settings is None else settings)
        fingerprint = self.settings_fingerprint(private)
        with self._model_settings_lock:
            self.store.bind_model_fingerprint(graph_id, fingerprint)
            previous = self._graph_model_settings.get(graph_id)
            if previous is not None and self.settings_fingerprint(previous) != fingerprint:
                raise ServiceError('圖譜的模型設定已固定，請核對後建立新執行', 409)
            self._graph_model_settings[graph_id] = private
        return fingerprint

    def settings_for_graph(self, graph_id):
        """Restore credentials only when the persisted identity still matches."""
        with self._model_settings_lock:
            if graph_id in self._graph_model_settings:
                return dict(self._graph_model_settings[graph_id])
            expected = self.store.graph(graph_id).get('model_fingerprint')
            if expected is None:
                raise ServiceError('圖譜缺少模型設定識別，新增寫入前需核對', 409)
            private = self.private_settings(get_model_settings())
            if self.settings_fingerprint(private) != expected:
                raise ServiceError('重啟後模型設定與圖譜原設定不一致，需核對後才能繼續寫入', 409)
            self._graph_model_settings[graph_id] = private
            return dict(private)

    def call(self, operation, *args, **kwargs):
        if not self.ready:
            raise ServiceError(self.error or '本機圖譜正在準備', 503)
        future = asyncio.run_coroutine_threadsafe(operation(*args, **kwargs), self.loop)
        return future.result(timeout=55)

    async def _worker(self):
        while True:
            job = self.store.claim()
            if job is None:
                await asyncio.sleep(0.5)
                continue
            try:
                with model_settings_snapshot(self.settings_for_graph(job['graph_id'])):
                    graph = self.store.graph(job['graph_id'])
                    entities, edges, mapping = ontology_models(graph['ontology'])
                    reference_time = datetime.fromisoformat(job['created_at'].replace('Z', '+00:00'))
                    # Graphiti interprets uuid= as an existing episode, rather than
                    # a requested ID for a new one. Create that durable identity
                    # first, while excluding the current episode from its history.
                    previous = await retrieve_episodes(self.graphiti.driver, reference_time,
                                                       group_ids=[job['graph_id']], source=EpisodeType[job['data_type']])
                    episode = EpisodicNode(
                        uuid=job['episode_uuid'], name=f'MiroFish {job["episode_uuid"]}', group_id=job['graph_id'],
                        source=EpisodeType[job['data_type']], source_description=job['source_description'],
                        content=job['data'], valid_at=reference_time, episode_metadata=job['metadata'],
                    )
                    await episode.save(self.graphiti.driver)
                    await self.graphiti.add_episode(
                        name=f'MiroFish {job["episode_uuid"]}', episode_body=job['data'],
                        source_description=job['source_description'],
                        reference_time=reference_time,
                        source=EpisodeType[job['data_type']], group_id=job['graph_id'], uuid=job['episode_uuid'],
                        previous_episode_uuids=[item.uuid for item in previous],
                        entity_types=entities or None, edge_types=edges or None, edge_type_map=mapping or None,
                        custom_extraction_instructions=(
                            'Extract only explicitly supported facts. Preserve names and summarize in the language of the input. '
                            'Classify people and organizations using the supplied entity types; do not invent participants. '
                            'Simulation episodes describe activities in a fictional simulation, not real-world events.'
                        ),
                    )
                    await self.graphiti.driver.execute_query(
                        'MATCH (n:Episodic {uuid:$uuid,group_id:$group_id}) '
                        'SET n.mirofish_complete=true, n.mirofish_metadata=$metadata',
                        uuid=job['episode_uuid'], group_id=job['graph_id'], metadata=json.dumps(job['metadata']))
                    self.store.finish(job['episode_uuid'])
                    logger.info('Graphiti episode complete: graph=%s, episode=%s', job['graph_id'], job['episode_uuid'])
            except Exception as error:
                # Provider exceptions can echo Authorization or request content.
                # Keep the safe service explanation and exception type only.
                logger.error('Graphiti episode failed: %s (%s)', job['episode_uuid'], type(error).__name__)
                message = str(error) if isinstance(error, ServiceError) else f'圖譜處理失敗（{type(error).__name__}）；請核對服務狀態'
                self.store.finish(job['episode_uuid'], message)

    async def page(self, graph_id, kind, limit, cursor=None):
        model = EntityNode if kind == 'nodes' else EntityEdge
        try:
            values = await model.get_by_group_ids(self.graphiti.driver, [graph_id], limit=limit + 1, uuid_cursor=cursor)
        except (GroupsNodesNotFoundError, GroupsEdgesNotFoundError):
            values = []
        return [serialize(value) for value in values[:limit]], values[limit - 1].uuid if len(values) > limit else None

    async def item(self, kind, uuid):
        model = EntityNode if kind == 'nodes' else EntityEdge
        try:
            value = await model.get_by_uuid(self.graphiti.driver, uuid)
        except (NodeNotFoundError, EdgeNotFoundError):
            raise ServiceError('找不到這個對象或關係', 404)
        self.store.graph(value.group_id)
        return serialize(value)

    async def node_edges(self, uuid):
        node = await self.item('nodes', uuid)
        try:
            edges = await EntityEdge.get_by_node_uuid(self.graphiti.driver, uuid)
        except EdgesNotFoundError:
            edges = []
        return [serialize(edge) for edge in edges if edge.group_id == node['group_id']]

    async def search(self, graph_id, query, limit, scope, reranker):
        config = COMBINED_HYBRID_SEARCH_RRF.model_copy(deep=True)
        config.limit = limit
        config.community_config = config.episode_config = None
        if scope == 'nodes':
            config.edge_config = None
            if reranker == 'cross_encoder':
                config.node_config.reranker = NodeReranker.cross_encoder
        else:
            config.node_config = None
            if reranker == 'cross_encoder':
                config.edge_config.reranker = EdgeReranker.cross_encoder
        result = await self.graphiti.search_(query=query, config=config, group_ids=[graph_id])
        return {'nodes': [serialize(node) for node in result.nodes],
                'edges': [serialize(edge) for edge in result.edges]}

    async def delete(self, graph_id):
        self.store.check_delete(graph_id)
        await Node.delete_by_group_id(self.graphiti.driver, graph_id)
        await self.graphiti.driver.execute_query('MATCH (r:MiroFishCloneReceipt {target_graph_id:$graph}) DELETE r', graph=graph_id)
        self.store.delete_graph(graph_id)
        with self._model_settings_lock:
            self._graph_model_settings.pop(graph_id, None)
        return {'success': True, 'graph_id': graph_id}

    async def clone(self, source_graph_id, target_graph_id, operation_id, settings=None):
        private = self.private_settings(get_model_settings() if settings is None else settings)
        fingerprint = self.settings_fingerprint(private)
        receipt = self.store.begin_clone(source_graph_id, target_graph_id, operation_id, fingerprint)
        if receipt['status'] == 'ready':
            return receipt
        self.bind_graph_settings(target_graph_id, private)
        try:
            await self.graphiti.driver.execute_query('''CREATE CONSTRAINT mirofish_clone_operation IF NOT EXISTS
                FOR (r:MiroFishCloneReceipt) REQUIRE r.operation_id IS UNIQUE''')
            async with self.graphiti.driver.session() as session:
                summary = await session.execute_write(copy_transaction, source_graph_id, target_graph_id,
                                                      operation_id, fingerprint)
            return self.store.finish_clone(operation_id, summary)
        except Exception as error:
            self.store.review_clone(operation_id)
            logger.error('Graphiti namespace copy requires review: %s (%s)', operation_id, type(error).__name__)
            if isinstance(error, ServiceError):
                raise
            raise ServiceError('圖譜複製結果尚未確認，請用相同執行識別核對', 409) from None

    async def database_health(self):
        await self.graphiti.driver.execute_query('RETURN 1 AS alive', routing_='r')
        return True
