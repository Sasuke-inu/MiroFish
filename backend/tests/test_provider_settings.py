"""Provider settings regressions. All external services are local test doubles."""
import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from flask import Flask

from app.api.settings import settings_bp
from app import provider_settings as providers
from app.config import Config


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv('MIROFISH_MODEL_SNAPSHOT', raising=False)
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'test-original-secret')
    monkeypatch.setattr(Config, 'LLM_BASE_URL', 'http://host.docker.internal:20128/v1')
    monkeypatch.setattr(Config, 'LLM_MODEL_NAME', 'ocg/test-model')
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    client = app.test_client()
    token = client.get('/api/settings/providers').json['data']['csrf_token']
    return SimpleNamespace(app=app, client=client, path=providers.settings_path(app.config),
                           headers={'X-MiroFish-CSRF': token, 'Origin': 'http://localhost:3000'})


def put(setup, payload, **kwargs):
    return setup.client.put('/api/settings/providers', json=payload, headers=setup.headers, **kwargs)


def transport(monkeypatch, handler):
    original = httpx.Client
    calls = []
    def factory(**kwargs):
        assert kwargs['follow_redirects'] is False
        assert kwargs['trust_env'] is False
        def record(request):
            calls.append(request)
            return handler(request)
        return original(transport=httpx.MockTransport(record), **kwargs)
    monkeypatch.setattr(providers.httpx, 'Client', factory)
    return calls


def test_read_preserves_environment_and_never_returns_secrets(setup):
    response = setup.client.get('/api/settings/providers')
    assert response.status_code == 200
    assert response.json['data']['config']['provider'] == 'ninerouter'
    assert response.json['data']['config']['has_api_key'] is True
    assert response.json['data']['config']['source'] == 'environment'
    assert 'test-original-secret' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert not setup.path.exists()


def test_atomic_save_blank_key_retained_only_same_provider_and_endpoint(setup):
    assert put(setup, {'model': 'ocg/another-model', 'api_key': ''}).status_code == 200
    assert json.loads(setup.path.read_text())['api_key'] == 'test-original-secret'
    current = setup.path.read_bytes()
    response = put(setup, {'base_url': 'http://127.0.0.1:8888/v1', 'api_key': ''})
    assert response.status_code == 400
    assert setup.path.read_bytes() == current
    response = put(setup, {'provider': 'custom', 'api_key': ''})
    assert response.status_code == 400
    assert put(setup, {'provider': 'custom', 'base_url': 'https://models.example/v1', 'api_key': 'new-secret'}).status_code == 200
    assert providers.get_model_settings(setup.app.config)['api_key'] == 'new-secret'
    assert not list(setup.path.parent.glob('*.tmp'))


@pytest.mark.parametrize('endpoint', ['https://user:password@example.com/v1', 'http://public.example/v1',
    'https://example.com/v1?key=secret', 'https://example.com/v1#secret', 'https://example.com/v1/chat/completions',
    'https://example.com/v1\\evil', 'file:///etc/passwd', 'https://example.com:bad/v1', 'http://169.254.169.254/v1'])
def test_unsafe_endpoint_rejected_before_request(setup, endpoint):
    response = put(setup, {'provider': 'custom', 'base_url': endpoint, 'api_key': 'new-secret'})
    assert response.status_code == 400
    assert not setup.path.exists()


def test_canonical_endpoint_keeps_local_ipv6_and_default_https_port():
    assert providers.canonical_endpoint('https://API.EXAMPLE:443/v1/') == 'https://api.example/v1'
    assert providers.canonical_endpoint('http://[::1]:1234/v1/') == 'http://[::1]:1234/v1'


def test_external_origins_rebinding_and_missing_csrf_rejected(setup):
    assert setup.client.get('/api/settings/providers', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert setup.client.get('/api/settings/providers', base_url='http://evil.example').status_code == 403
    assert setup.client.get('/api/settings/providers', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert setup.client.put('/api/settings/providers', json={'model': 'new-model'}).status_code == 403
    assert setup.client.put('/api/settings/providers', data='model=test', headers=setup.headers).status_code == 415
    assert not setup.path.exists()


@pytest.mark.parametrize('payload', [None, [], {'provider': []}, {'provider': {}}, {'api_key': 'secret\nheader'}, {'api_key': '非ascii'}])
def test_malformed_settings_return_safe_validation_error(setup, payload):
    response = put(setup, payload)
    assert response.status_code in {400, 413, 415}
    assert not setup.path.exists()


def test_connection_uses_only_models_without_writing_or_exposing_errors(setup, monkeypatch):
    calls = transport(monkeypatch, lambda request: httpx.Response(200, json={'data': [{'id': 'ocg/test-model'}, {'id': 'b'}]}))
    response = setup.client.post('/api/settings/providers/test', json={}, headers=setup.headers)
    assert response.status_code == 200
    assert response.json['data']['model_available'] is True
    assert [request.method for request in calls] == ['GET']
    assert str(calls[0].url).endswith('/v1/models')
    assert not setup.path.exists()
    assert 'test-original-secret' not in response.text


def test_redirect_does_not_forward_secret_or_retry(setup, monkeypatch):
    calls = transport(monkeypatch, lambda request: httpx.Response(302, headers={'Location': 'https://evil.example/key'}))
    response = setup.client.post('/api/settings/providers/test', json={}, headers=setup.headers)
    assert response.status_code == 502
    assert len(calls) == 1
    assert '重新導向' in response.json['error']
    assert 'test-original-secret' not in response.text


def test_model_discovery_does_not_require_a_model_but_save_does(setup, monkeypatch):
    calls = transport(monkeypatch, lambda request: httpx.Response(200, json={'data': [{'id': 'new-model'}]}))
    payload = {'model': '', 'provider': 'openai', 'base_url': 'https://api.openai.com/v1', 'api_key': 'new-secret'}
    response = setup.client.post('/api/settings/providers/test', json=payload, headers=setup.headers)
    assert response.status_code == 200
    assert response.json['data']['model_available'] is None
    assert len(calls) == 1
    assert put(setup, payload).status_code == 400


def test_upstream_body_never_exposed_and_rate_limit_not_retried(setup, monkeypatch):
    calls = transport(monkeypatch, lambda request: httpx.Response(429, json={'error': 'test-original-secret confidential details'}))
    response = setup.client.post('/api/settings/providers/test', json={}, headers=setup.headers)
    assert response.status_code == 429
    assert len(calls) == 1
    assert 'confidential' not in response.text


def test_openrouter_key_limit_is_not_wallet_and_null_is_not_zero(setup, monkeypatch):
    assert put(setup, {'provider': 'openrouter', 'base_url': 'https://openrouter.ai/api/v1', 'model': 'test/model', 'api_key': 'router-secret'}).status_code == 200
    calls = transport(monkeypatch, lambda request: httpx.Response(200, json={'data': {'limit': None, 'limit_remaining': None, 'usage': 2.5}}))
    response = setup.client.get('/api/settings/providers/balance')
    assert response.json['data']['kind'] == 'key_allowance'
    assert response.json['data']['status'] == 'unlimited'
    assert response.json['data']['remaining'] is None
    assert str(calls[0].url) == 'https://openrouter.ai/api/v1/key'


def test_opencode_go_reads_subscription_quota_not_dollar_balance(setup, monkeypatch):
    assert put(setup, {'provider': 'opencode_go', 'base_url': 'https://opencode.ai/zen/go/v1', 'model': 'kimi-k3', 'api_key': 'go-secret'}).status_code == 200
    calls = transport(monkeypatch, lambda request: httpx.Response(200, json={'usage': {'rolling': {'percent': 37, 'resetsAt': '2026-10-03T13:00:00Z', 'status': 'ok'}}}))
    data = setup.client.get('/api/settings/providers/balance').json['data']
    assert data['kind'] == 'subscription_quota'
    assert data['currency'] is None
    assert data['remaining'] is None
    assert data['quotas'][0]['remaining_percent'] == 63
    assert str(calls[0].url).endswith('/zen/go/v1/usage')


def test_opencode_protocols_differ_by_provider_and_unknown_cannot_be_saved(setup):
    assert providers.model_compatibility('https://opencode.ai/zen/v1', 'minimax-m3')['compatible'] is True
    assert providers.model_compatibility('https://opencode.ai/zen/go/v1', 'minimax-m3')['compatible'] is False
    response = put(setup, {'provider': 'opencode_go', 'base_url': 'https://opencode.ai/zen/go/v1', 'model': 'gpt-5.6', 'api_key': 'go-secret'})
    assert response.status_code == 422
    # Choosing Custom for the same direct endpoint must not bypass the guard.
    assert put(setup, {'provider': 'custom', 'base_url': 'https://opencode.ai/zen/go/v1', 'model': 'gpt-5.6', 'api_key': 'go-secret'}).status_code == 422


def test_openai_ordinary_key_has_no_wallet_endpoint(setup, monkeypatch):
    assert put(setup, {'provider': 'openai', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini', 'api_key': 'openai-secret'}).status_code == 200
    monkeypatch.setattr(providers, '_request_json', lambda *_args, **_kwargs: pytest.fail('unsupported balance must not make a request'))
    data = setup.client.get('/api/settings/providers/balance').json['data']
    assert data['supported'] is False
    assert data['remaining'] is None


def test_balance_token_has_independent_endpoint_binding_and_compare_and_swap(setup):
    response = put(setup, {'balance_api_key': 'cli-secret', 'expected_base_url': 'http://host.docker.internal:20128/v1', 'expected_provider': 'ninerouter'})
    assert response.status_code == 200
    assert response.json['data']['config']['has_balance_api_key'] is True
    assert 'cli-secret' not in response.text
    assert put(setup, {'balance_api_key': 'other', 'expected_provider': 'custom'}).status_code == 409
    assert put(setup, {'balance_api_key': 'other', 'expected_base_url': 'http://localhost:8888/v1'}).status_code == 409
    assert put(setup, {'base_url': 'http://localhost:20128/v1', 'api_key': 'new-model-secret'}).status_code == 200
    assert providers.get_model_settings(setup.app.config)['balance_api_key'] == ''


def test_admin_authorization_cannot_be_sent_to_remote_or_other_local_service(setup, monkeypatch):
    for url in ('https://evil.example/v1', 'http://localhost:9999/v1', 'http://192.168.1.1:20128/v1', 'http://localhost:20128/evil'):
        response = put(setup, {'base_url': url, 'api_key': 'model-key', 'balance_api_key': 'sensitive-admin'})
        assert response.status_code == 400
        assert 'sensitive-admin' not in response.text
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: pytest.fail('admin origin rejected before any network activity'))
    with pytest.raises(providers.SettingsError):
        providers._request_json({'base_url': 'https://evil.example/v1', 'balance_api_key': 'secret'}, '/api/providers/client', balance_admin=True)


def test_router_accounts_use_sanitized_route_and_wallet_drops_personal_fields(setup, monkeypatch):
    assert put(setup, {'balance_api_key': 'cli-secret', 'balance_account_id': 'account_1'}).status_code == 200
    def handler(request):
        assert request.headers.get('x-9r-cli-token') == 'cli-secret'
        assert 'Authorization' not in request.headers
        if request.url.path == '/api/providers/client':
            assert request.url.params['provider'] == 'opencode-go'
            return httpx.Response(200, json={'connections': [{'id': 'account_1', 'provider': 'opencode-go', 'displayName': 'My Go', 'isActive': True, 'apiKey': 'should-not-leak'}, {'id': 'different', 'provider': 'openai'}]})
        assert request.url.path == '/api/usage/account_1'
        return httpx.Response(200, json={'walletSync': {'status': 'ok', 'balanceUSD': -0.25, 'checkedAt': providers.now(), 'accountEmail': 'private@example.com', 'workspaceId': 'private-workspace'}})
    calls = transport(monkeypatch, handler)
    response = setup.client.get('/api/settings/providers/balance')
    data = response.json['data']
    assert data['kind'] == 'wallet'
    assert data['status'] == 'available'
    assert data['remaining'] == -0.25
    assert len(calls) == 2
    for secret in ('cli-secret', 'private@example.com', 'private-workspace', 'should-not-leak'):
        assert secret not in response.text


@pytest.mark.parametrize('status,seconds,expected', [('ok', 900, 'stale'), ('login-required', 10, 'stale'), ('ok', 10, 'available')])
def test_router_wallet_staleness_keeps_last_balance(setup, monkeypatch, status, seconds, expected):
    assert put(setup, {'balance_api_key': 'cli-secret', 'balance_account_id': 'account_1'}).status_code == 200
    monkeypatch.setattr(providers, 'provider_accounts', lambda **kwargs: {'accounts': [{'id': 'account_1'}]})
    checked = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    monkeypatch.setattr(providers, '_request_json', lambda *_args, **_kwargs: {'walletSync': {'status': status, 'balanceUSD': 4.25, 'checkedAt': checked}})
    data = setup.client.get('/api/settings/providers/balance').json['data']
    assert data['status'] == expected
    assert data['remaining'] == 4.25
    assert data['checked_at'] == checked


def test_router_missing_wallet_is_not_zero_and_account_must_be_listed(setup, monkeypatch):
    data = setup.client.get('/api/settings/providers/balance').json['data']
    assert data['status'] == 'authorization_required' and data['remaining'] is None
    assert put(setup, {'balance_api_key': 'cli-secret', 'balance_account_id': 'account_1'}).status_code == 200
    monkeypatch.setattr(providers, 'provider_accounts', lambda **kwargs: {'accounts': []})
    monkeypatch.setattr(providers, '_request_json', lambda *_args, **_kwargs: pytest.fail('unlisted account must never be queried'))
    assert setup.client.get('/api/settings/providers/balance').status_code == 409


def test_new_clients_read_new_settings_and_running_snapshot_is_stable(setup, monkeypatch):
    from app.utils.llm_client import LLMClient
    import app.utils.llm_client as module
    monkeypatch.setattr(module, 'OpenAI', lambda **kwargs: SimpleNamespace(**kwargs))
    first = LLMClient()
    assert first.model == 'ocg/test-model'
    with providers.model_settings_snapshot():
        assert put(setup, {'model': 'ocg/new-model'}).status_code == 200
        assert LLMClient().model == 'ocg/test-model'
    assert LLMClient().model == 'ocg/new-model'
    assert first.model == 'ocg/test-model'


def test_real_sdk_initializes_with_its_supported_http_client_without_network(setup):
    from app.utils.llm_client import LLMClient
    client = LLMClient()
    assert client.client.api_key == 'test-original-secret'
    assert str(client.client.base_url) == 'http://host.docker.internal:20128/v1/'
    client.client.close()


def test_graphiti_dynamic_sdk_uses_snapshot_model_without_network(setup, monkeypatch):
    from app.local_graph import runtime
    observed = []
    async def completion(client, **kwargs):
        observed.append((client.api_key, str(client.base_url), kwargs['model']))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"facts":[]}'))])
    monkeypatch.setattr(runtime, 'create_chat_completion', completion)
    llm = runtime.RouterLLM(config=runtime.LLMConfig(api_key='old-key', model='old-model'), use_saved_settings=True)
    assert put(setup, {'model': 'ocg/new-model'}).status_code == 200
    assert asyncio.run(llm._generate_response([])) == {'facts': []}
    assert observed == [('test-original-secret', 'http://host.docker.internal:20128/v1/', 'ocg/new-model')]
    asyncio.run(llm.client.close())


def test_clear_balance_authorization_preserves_primary_settings(setup):
    assert put(setup, {'balance_api_key': 'cli-secret', 'balance_account_id': 'account_1'}).status_code == 200
    before = providers.get_model_settings(setup.app.config)
    response = put(setup, {'clear_balance_authorization': True, 'expected_base_url': before['base_url'], 'expected_provider': before['provider']})
    assert response.status_code == 200
    assert response.json['data']['config']['has_balance_api_key'] is False
    assert response.json['data']['config']['balance_account_id'] is None
    after = providers.get_model_settings(setup.app.config)
    assert all(after[key] == before[key] for key in ('api_key', 'provider', 'model', 'base_url'))
    assert after['balance_api_key'] == ''


def test_subprocess_snapshot_prevents_environment_or_file_changes(setup, monkeypatch):
    frozen = providers.model_environment()
    assert put(setup, {'model': 'ocg/new-model'}).status_code == 200
    for key, value in frozen.items():
        monkeypatch.setenv(key, value)
    assert providers.get_model_settings()['model'] == 'ocg/test-model'
    assert providers.get_model_settings()['source'] == 'job_snapshot'


def test_multistage_job_snapshot_does_not_change_mid_job(setup):
    observed = []
    @providers.with_model_snapshot
    def prepare():
        observed.append(providers.get_model_settings()['model'])
        providers.save_settings({'model': 'ocg/new-model'}, setup.app.config)
        observed.append(providers.get_model_settings()['model'])
    prepare()
    assert observed == ['ocg/test-model', 'ocg/test-model']
    assert providers.get_model_settings()['model'] == 'ocg/new-model'


def test_report_search_tools_share_report_model_client(setup, monkeypatch):
    from app.services import report_agent
    chosen = SimpleNamespace(model='chosen-for-report')
    monkeypatch.setattr(report_agent, 'ZepToolsService', lambda **kwargs: SimpleNamespace(llm=kwargs['llm_client']))
    report = report_agent.ReportAgent('graph', 'simulation', 'requirement', llm_client=chosen)
    assert report.zep_tools.llm is chosen


def test_corrupted_saved_settings_fail_closed(setup):
    setup.path.parent.mkdir(parents=True)
    setup.path.write_text('{not-json', encoding='utf-8')
    response = setup.client.get('/api/settings/providers')
    assert response.status_code == 503
    assert 'test-original-secret' not in response.text


def test_native_startup_validation_accepts_saved_key_without_environment_key(setup, monkeypatch):
    assert put(setup, {'api_key': 'saved-secret'}).status_code == 200
    monkeypatch.setattr(Config, 'LLM_API_KEY', '')
    assert 'LLM_API_KEY 未配置' not in Config.validate()


def test_graphiti_batches_keep_snapshot_and_next_batch_uses_saved_model(setup, monkeypatch):
    from app.local_graph import runtime
    jobs = [{'episode_uuid': 'one', 'batch_id': 'first', 'graph_id': 'graph', 'created_at': providers.now(),
             'data_type': 'text', 'source_description': 'test', 'data': 'data', 'metadata': {}},
            {'episode_uuid': 'two', 'batch_id': 'first', 'graph_id': 'graph', 'created_at': providers.now(),
             'data_type': 'text', 'source_description': 'test', 'data': 'data', 'metadata': {}},
            {'episode_uuid': 'three', 'batch_id': 'second', 'graph_id': 'graph', 'created_at': providers.now(),
             'data_type': 'text', 'source_description': 'test', 'data': 'data', 'metadata': {}}]
    pending = iter(jobs)
    finished, models = [], []
    def claim():
        try:
            return next(pending)
        except StopIteration:
            raise StopAsyncIteration('all fixture jobs processed')
    async def noop(*args, **kwargs):
        return []
    async def add_episode(**kwargs):
        models.append(providers.get_model_settings()['model'])
        if len(models) == 1:
            providers.save_settings({'model': 'ocg/new-model'}, setup.app.config)
        assert providers.get_model_settings()['model'] == models[-1]
    monkeypatch.setattr(runtime, 'retrieve_episodes', noop)
    monkeypatch.setattr(runtime, 'EpisodicNode', lambda **kwargs: SimpleNamespace(save=noop))
    worker = object.__new__(runtime.Runtime)
    worker._batch_model_settings = {}
    worker.store = SimpleNamespace(claim=claim, graph=lambda _: {'ontology': {}},
        finish=lambda uuid, *args: finished.append(uuid),
        batch=lambda batch: {'status': 'succeeded' if (batch == 'first' and len(finished) >= 2) or (batch == 'second' and len(finished) >= 3) else 'processing'})
    worker.graphiti = SimpleNamespace(driver=SimpleNamespace(execute_query=noop), add_episode=add_episode)
    with pytest.raises(StopAsyncIteration):
        asyncio.run(worker._worker())
    assert models == ['ocg/test-model', 'ocg/test-model', 'ocg/new-model']
    assert finished == ['one', 'two', 'three']
    assert worker._batch_model_settings == {}


def test_failed_atomic_write_preserves_previous_settings(setup, monkeypatch):
    assert put(setup, {'model': 'ocg/current'}).status_code == 200
    original = setup.path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('test-disk-failure-with-secret')
    monkeypatch.setattr(providers.os, 'replace', fail)
    response = put(setup, {'model': 'ocg/new'})
    assert response.status_code == 503
    assert 'test-disk-failure' not in response.text
    assert setup.path.read_bytes() == original
    assert not list(setup.path.parent.glob('*.tmp'))


def test_sync_model_error_redacts_body_and_preserves_json_mode_negotiation():
    from openai import BadRequestError
    from app.utils.llm_client import LLMClient
    from app.utils.openai_chat_compat import create_chat_completion, ModelServiceError
    error = BadRequestError('credential-echo-private', response=httpx.Response(400, request=httpx.Request('POST', 'https://example.com/v1/chat/completions')),
        body={'error': {'message': 'response_format unsupported credential-echo-private', 'param': 'response_format', 'code': 'unsupported_parameter'}})
    def fail(**kwargs):
        raise error
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(ModelServiceError) as caught:
        create_chat_completion(client, model='example', messages=[])
    safe = caught.value
    assert 'credential-echo-private' not in ''.join(traceback.format_exception(safe))
    assert 'credential-echo-private' not in json.dumps(safe.body)
    assert safe.status_code == 400
    results = iter([error, SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='{"ok":true}'))])])
    calls = []
    def completion(**kwargs):
        calls.append(kwargs)
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result
    llm = object.__new__(LLMClient)
    llm.model = 'example'
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
    assert llm.chat_json([]) == {'ok': True}
    assert len(calls) == 2
    assert 'response_format' in calls[0]
    assert 'response_format' not in calls[1]


def test_async_model_error_does_not_expose_upstream_content():
    from openai import AuthenticationError
    from app.utils.openai_chat_compat import create_chat_completion, ModelServiceError
    async def fail(**kwargs):
        raise AuthenticationError('private-key-echo', response=httpx.Response(401, request=httpx.Request('POST', 'https://example.com/v1/chat/completions')),
                                  body={'error': {'message': 'private-key-echo'}})
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(ModelServiceError) as caught:
        asyncio.run(create_chat_completion(client, model='example', messages=[]))
    assert caught.value.status_code == 401
    assert 'private-key-echo' not in ''.join(traceback.format_exception(caught.value))
