"""Private, atomic model settings shared by Flask, simulation jobs and Graphiti.

Secrets stay in the server's existing uploads volume. Public responses are built
from an explicit allowlist; neither upstream bodies nor exception text is exposed.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx


PRESETS = [
    {'id': 'openai', 'label': 'OpenAI', 'base_url': 'https://api.openai.com/v1', 'balance_support': 'unsupported'},
    {'id': 'openrouter', 'label': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1', 'balance_support': 'key_allowance'},
    {'id': 'opencode_zen', 'label': 'OpenCode Zen', 'base_url': 'https://opencode.ai/zen/v1', 'balance_support': 'unsupported'},
    {'id': 'opencode_go', 'label': 'OpenCode Go', 'base_url': 'https://opencode.ai/zen/go/v1', 'balance_support': 'subscription_quota'},
    {'id': 'ninerouter', 'label': '9Router', 'base_url': 'http://host.docker.internal:20128/v1', 'balance_support': 'dashboard_required'},
    {'id': 'custom', 'label': 'OpenAI 相容／自訂端點', 'base_url': '', 'balance_support': 'unsupported'},
]
_PRESETS = {item['id']: item for item in PRESETS}
_LOCK = threading.RLock()
_SNAPSHOT = ContextVar('mirofish_model_settings', default=None)
# Official endpoint tables, checked 2026-10-03. A catalogue entry alone does
# not establish Chat Completions compatibility (Zen and Go differ).
OPENCODE_CHAT_MODELS = {
    'opencode_zen': set(('qwen3.8-max deepseek-v4.1-flash deepseek-v4-pro deepseek-v4-flash '
        'deepseek-v4-flash-vision-exp minimax-m3 minimax-m2.7 minimax-m2.5 glm-5.3-flash '
        'glm-5.3 glm-5.2 glm-5.1 glm-5 kimi-k2.5 kimi-k2.6 kimi-k2.7-code kimi-k3 big-pickle '
        'space-bunny-free longcat-2.5-preview-free mimo-v2.6-flash-free mimo-v2.5-free '
        'ling-3.1-flash-free ling-3.0-flash-fin-free nemotron-3-ultra-free nemotron-3.5-lightning-free').split()),
    'opencode_go': set(('glm-5.3-flash glm-5.3 glm-5.2 kimi-k3 kimi-k2.7-code kimi-k2.6 '
        'longcat-2.0 longcat-2.5-preview-free deepseek-v4.1-flash deepseek-v4-pro deepseek-v4-flash '
        'deepseek-v4-flash-vision-exp mimo-v2.6-flash mimo-v2.6-pro mimo-v2.5 mimo-v2.5-pro '
        'hy4-preview hy3 space-bunny-free').split()),
}


class SettingsError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def settings_path(settings=None):
    from .config import Config
    get = settings.get if settings is not None else lambda key, default=None: getattr(Config, key, default)
    configured = get('PROVIDER_SETTINGS_PATH') or os.environ.get('PROVIDER_SETTINGS_PATH')
    return Path(configured) if configured else Path(get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER)) / 'settings' / 'providers.json'


def canonical_endpoint(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise SettingsError('請填入完整的模型服務網址。')
    value = value.strip()
    if any(ord(char) < 33 for char in value) or '\\' in value:
        raise SettingsError('服務網址不能包含空白或特殊控制字元。')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        port = parts.port
    except ValueError:
        raise SettingsError('服務網址格式不正確。') from None
    if parts.scheme not in {'http', 'https'} or not host or parts.username is not None or parts.password is not None:
        raise SettingsError('請使用 http 或 https 網址；帳號或金鑰請填在獨立欄位。')
    if parts.query or parts.fragment or '?' in value or '#' in value or '%' in host:
        raise SettingsError('服務網址不能包含查詢參數或頁面定位。')
    if parts.scheme == 'http':
        local = host in {'localhost', 'host.docker.internal', 'gateway.docker.internal'} or host.endswith('.localhost')
        try:
            address = ipaddress.ip_address(host)
            local = address.is_loopback or address in ipaddress.ip_network('10.0.0.0/8') or address in ipaddress.ip_network('172.16.0.0/12') or address in ipaddress.ip_network('192.168.0.0/16') or address in ipaddress.ip_network('fc00::/7')
        except ValueError:
            pass
        if not local:
            raise SettingsError('公開服務請使用 HTTPS；HTTP 僅允許本機或私人網路位址。')
    if port == (443 if parts.scheme == 'https' else 80):
        port = None
    netloc = f'[{host}]' if ':' in host else host
    if port is not None:
        netloc += f':{port}'
    path = parts.path.rstrip('/')
    if '..' in path.split('/') or '%2e' in path.lower() or '%2f' in path.lower():
        raise SettingsError('服務網址路徑不正確。')
    if path.endswith(('/chat/completions', '/responses', '/models', '/messages')):
        raise SettingsError('請填入 API 基礎網址（通常以 /v1 結尾），不要加上 /models 或 /chat/completions。')
    return urlunsplit((parts.scheme, netloc, path, '', ''))


def _infer_provider(base_url):
    for item in PRESETS:
        if item['base_url'] and base_url.rstrip('/') == item['base_url']:
            return item['id']
    try:
        if urlsplit(base_url).port == 20128:
            return 'ninerouter'
    except ValueError:
        pass
    return 'custom'


def get_model_settings(settings=None, *, stage=None, profile_id=None):
    """Read on each new client/job; an explicit job context always wins."""
    snapshot = _SNAPSHOT.get()
    if snapshot is not None:
        return dict(snapshot)
    from .config import Config
    get = settings.get if settings is not None else lambda key, default=None: getattr(Config, key, default)
    # Simulation subprocesses inherit a frozen config, even if a user saves again.
    if os.environ.get('MIROFISH_MODEL_SNAPSHOT') == '1':
        base_url = os.environ.get('LLM_BASE_URL', '')
        return {'provider': os.environ.get('LLM_PROVIDER', _infer_provider(base_url)),
                'base_url': base_url, 'model': os.environ.get('LLM_MODEL_NAME', ''),
                'api_key': os.environ.get('LLM_API_KEY', ''), 'source': 'job_snapshot', 'updated_at': None}
    path = settings_path(settings)
    try:
        with path.open(encoding='utf-8') as stream:
            value = json.load(stream)
        if not isinstance(value, dict) or not all(isinstance(value.get(key), str) for key in ('provider', 'base_url', 'model', 'api_key')):
            raise ValueError('invalid saved settings')
        if stage or profile_id:
            profile_id = profile_id or value.get('stage_assignments', {}).get(stage)
            if profile_id and profile_id != 'default':
                profile = value.get('profiles', {}).get(profile_id)
                if not profile:
                    raise ValueError('Stage points to an absent profile')
                value = {**profile['config'], 'profile_id': profile_id, 'profile_name': profile['name']}
        return {**{key: item for key, item in value.items() if key not in {'profiles', 'stage_assignments', 'capabilities'}}, 'source': 'saved'}
    except FileNotFoundError:
        if profile_id and profile_id != 'default':
            raise SettingsError('原工作使用的具名連線不存在，已停止啟動。', 409) from None
        base_url = get('LLM_BASE_URL', 'https://api.openai.com/v1') or ''
        return {'provider': _infer_provider(base_url), 'base_url': base_url,
                'model': get('LLM_MODEL_NAME', '') or '', 'api_key': get('LLM_API_KEY', '') or '',
                'source': 'environment', 'updated_at': None}
    except (OSError, ValueError):
        # Do not silently run against a different paid provider after corruption.
        raise SettingsError('無法讀取已儲存的模型設定，請檢查伺服器設定檔。', 503) from None


@contextmanager
def model_settings_snapshot(settings=None):
    token = _SNAPSHOT.set(dict(settings or get_model_settings()))
    try:
        yield _SNAPSHOT.get()
    finally:
        _SNAPSHOT.reset(token)


def model_environment(settings=None):
    value = settings or get_model_settings()
    return {'LLM_API_KEY': value['api_key'], 'LLM_BASE_URL': value['base_url'],
            'LLM_MODEL_NAME': value['model'], 'LLM_PROVIDER': value['provider'],
            'MIROFISH_MODEL_SNAPSHOT': '1',
            # Every explicit run snapshot owns its model choice. An inherited
            # boost environment must not override that recorded selection.
            'LLM_BOOST_API_KEY': '', 'LLM_BOOST_BASE_URL': '', 'LLM_BOOST_MODEL_NAME': ''}


def with_model_snapshot(function):
    """Bind synchronous multi-stage jobs to the settings active when they start."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with model_settings_snapshot():
            return function(*args, **kwargs)
    return wrapped


def public_config(value):
    return {key: value.get(key) for key in ('provider', 'base_url', 'model', 'source', 'updated_at')} | {
        'has_api_key': bool(value.get('api_key')), 'has_balance_api_key': bool(value.get('balance_api_key')),
        'balance_account_id': value.get('balance_account_id') or None}


def model_compatibility(base_url, model):
    provider = _infer_provider(base_url)
    if provider in OPENCODE_CHAT_MODELS:
        compatible = model in OPENCODE_CHAT_MODELS[provider]
        return {'id': model, 'compatible': compatible, 'reason': '' if compatible else '此模型的對話格式尚未確認相容；請透過 9Router 轉接。'}
    return {'id': model, 'compatible': True, 'reason': ''}


def validate_draft(payload, current, *, require_compatible=True, require_model=True):
    if not isinstance(payload, dict) or set(payload) - {'provider', 'base_url', 'model', 'api_key', 'balance_api_key', 'balance_account_id', 'expected_base_url', 'expected_provider', 'clear_balance_authorization'}:
        raise SettingsError('設定內容格式不正確。')
    if 'clear_balance_authorization' in payload and not isinstance(payload['clear_balance_authorization'], bool):
        raise SettingsError('解除餘額授權的設定格式不正確。')
    if 'expected_base_url' in payload and canonical_endpoint(payload['expected_base_url']) != canonical_endpoint(current['base_url']):
        raise SettingsError('模型服務網址已變更，請重新載入設定後再試。', 409)
    if 'expected_provider' in payload and payload['expected_provider'] != current['provider']:
        raise SettingsError('模型服務已變更，請重新載入設定後再試。', 409)
    provider = payload.get('provider', current['provider'])
    if not isinstance(provider, str) or provider not in _PRESETS:
        raise SettingsError('請選擇支援的模型服務。')
    base_url = canonical_endpoint(payload.get('base_url', current['base_url']))
    # Brand-specific balance and protocol logic applies only to the real service.
    preset_url = _PRESETS[provider]['base_url']
    if provider not in {'custom', 'ninerouter'} and base_url != preset_url:
        raise SettingsError('這個服務的網址與官方網址不同；代理或私人服務請選擇自訂端點。')
    model = payload.get('model', current['model'])
    if not isinstance(model, str) or len(model) > 200 or (require_model and not model.strip()) or any(ord(char) < 32 for char in model):
        raise SettingsError('請填入模型名稱（最多 200 字元）。')
    if require_compatible and not model_compatibility(base_url, model.strip())['compatible']:
        raise SettingsError('此 OpenCode 模型並非已確認的 Chat Completions 模型，請選擇清單中的相容模型或透過 9Router 轉接。', 422)
    api_key = payload.get('api_key', '')
    if not isinstance(api_key, str) or len(api_key) > 4096 or any(ord(char) < 32 or ord(char) > 126 for char in api_key):
        raise SettingsError('API 金鑰格式不正確。')
    api_key = api_key.strip()
    try:
        same_endpoint = base_url == canonical_endpoint(current['base_url'])
    except SettingsError:
        same_endpoint = False
    if not api_key and provider == current['provider'] and same_endpoint:
        api_key = current.get('api_key', '')
    if not api_key:
        raise SettingsError('請填入此服務的 API 金鑰。切換服務或網址時不會沿用原金鑰。')
    balance_key = payload.get('balance_api_key', '')
    if not isinstance(balance_key, str) or len(balance_key) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in balance_key.strip()):
        raise SettingsError('餘額查詢授權碼格式不正確。')
    balance_key = balance_key.strip()
    if not balance_key and provider == current['provider'] and same_endpoint:
        balance_key = current.get('balance_api_key', '')
    account = payload.get('balance_account_id', current.get('balance_account_id') if provider == current['provider'] and same_endpoint else '') or ''
    if not isinstance(account, str) or account and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', account):
        raise SettingsError('請重新選擇餘額查詢帳戶。')
    if provider != 'ninerouter' or payload.get('clear_balance_authorization') is True:
        balance_key, account = '', ''
    elif balance_key:
        validate_router_admin_origin(base_url)
    return {'provider': provider, 'base_url': base_url, 'model': model.strip(), 'api_key': api_key,
            'balance_api_key': balance_key, 'balance_account_id': account, 'source': 'saved', 'updated_at': now()}


def save_settings(payload, settings=None):
    with _LOCK:
        value = validate_draft(payload, get_model_settings(settings))
        path = settings_path(settings)
        temporary = None
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.providers-', suffix='.tmp', dir=path.parent)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                existing = _profile_document(settings)
                preserved = {key: existing[key] for key in ('schema_version', 'profiles', 'stage_assignments', 'capabilities') if key in existing}
                json.dump({**preserved, **{key: item for key, item in value.items() if key != 'source'}}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            return public_config(value)
        except OSError:
            raise SettingsError('無法儲存設定；原有設定仍保留。請檢查資料夾權限與磁碟空間。', 503) from None
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def validate_router_admin_origin(base_url):
    parts = urlsplit(canonical_endpoint(base_url))
    if parts.hostname not in {'localhost', '127.0.0.1', '::1', 'host.docker.internal'} or parts.port != 20128 or parts.path != '/v1':
        raise SettingsError('9Router 管理授權碼僅能用於本機的 20128 連接埠（/v1）；不會傳送至其他服務。', 400)


def _request_json(value, suffix, *, balance_admin=False):
    base = canonical_endpoint(value['base_url'])
    if balance_admin:
        validate_router_admin_origin(base)
        parts = urlsplit(base)
        base = urlunsplit((parts.scheme, parts.netloc, '', '', ''))
        headers = {'x-9r-cli-token': value['balance_api_key'], 'Accept': 'application/json'}
    else:
        headers = {'Authorization': 'Bearer ' + value['api_key'], 'Accept': 'application/json'}
    url = base + suffix
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', url, headers=headers) as response:
                if 300 <= response.status_code < 400:
                    raise SettingsError('服務要求重新導向；為保護金鑰，請改填最終的 API 基礎網址。', 502)
                if response.status_code in {401, 403}:
                    raise SettingsError('服務拒絕這組金鑰，請檢查金鑰及存取權限。', 502)
                if response.status_code == 429:
                    raise SettingsError('服務目前限制請求，請稍後手動重試。', 429)
                if response.status_code == 404:
                    raise SettingsError('服務沒有提供這個查詢介面，請檢查 API 基礎網址。', 502)
                if response.status_code != 200:
                    raise SettingsError(f'服務暫時無法完成查詢（HTTP {response.status_code}）。', 502)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2 * 1024 * 1024:
                        raise SettingsError('服務回應過大，無法安全讀取。', 502)
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise ValueError('invalid document')
                return result
    except SettingsError:
        raise
    except httpx.TimeoutException:
        raise SettingsError('連線逾時；請檢查服務是否啟動，再手動重試。', 504) from None
    except httpx.HTTPError:
        raise SettingsError('無法連線到模型服務，請檢查網址、網路及憑證。', 502) from None
    except (ValueError, UnicodeError):
        raise SettingsError('服務回傳了無法辨識的資料。', 502) from None


def test_connection(payload, settings=None):
    value = validate_draft(payload, get_model_settings(settings), require_compatible=False, require_model=False)
    document = _request_json(value, '/models')
    rows = document.get('data')
    if not isinstance(rows, list):
        raise SettingsError('服務沒有回傳標準的模型清單。', 502)
    models = sorted({row['id'] for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)
                     and row['id'].strip() and len(row['id']) <= 200})[:3000]
    return {'connected': True, 'models': [model_compatibility(value['base_url'], model) for model in models],
            'model_available': value['model'] in models if value['model'] else None, 'checked_at': now(), 'mode': 'models_only',
            'message': '已讀取模型清單；沒有執行推論，也尚未驗證模型的文字生成能力。'}


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def provider_accounts(settings=None, *, value=None):
    value = value or get_model_settings(settings)
    if value['provider'] != 'ninerouter' or not value.get('balance_api_key'):
        raise SettingsError('請先儲存 9Router 的獨立餘額查詢授權碼。')
    document = _request_json(value, '/api/providers/client?provider=opencode-go&pageSize=500', balance_admin=True)
    connections = document.get('connections')
    if not isinstance(connections, list):
        raise SettingsError('9Router 未回傳可辨識的帳戶清單。', 502)
    return {'accounts': [{'id': row['id'], 'name': str(row.get('displayName') or row.get('name') or 'OpenCode Go')[:160],
                          'is_active': row.get('isActive') is True}
                         for row in connections if isinstance(row, dict) and row.get('provider') == 'opencode-go'
                         and isinstance(row.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', row['id'])]}


STAGES = ('graph', 'prepare', 'simulation', 'report')


def _profile_document(settings=None):
    """Read the existing private file; migration is additive and explicit."""
    path = settings_path(settings)
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(document, dict):
            raise ValueError()
        return document
    except FileNotFoundError:
        return {key: value for key, value in get_model_settings(settings).items() if key != 'source'}
    except (OSError, ValueError):
        raise SettingsError('無法讀取模型連線，已保留原設定。', 503) from None


def _write_profile_document(document, settings=None):
    from .utils.atomic import write_json
    path = settings_path(settings)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_json(path, document)
        os.chmod(path, 0o600)
    except OSError:
        raise SettingsError('無法保存模型連線；請檢查儲存空間。', 503) from None


def _capability_defaults(config):
    return {'configuration': 'configured' if config.get('api_key') and config.get('model') else 'incomplete',
            'reachable': 'not_verified', 'model_list': 'not_verified', 'text_generation': 'not_verified',
            'structured_output': 'not_verified', 'task_usable': 'not_verified',
            'api': 'chat_completions', 'structured_output_api': None, 'checked_at': None}


def profiles_config(settings=None):
    document = _profile_document(settings)
    profiles = []
    for profile_id, item in document.get('profiles', {}).items():
        profiles.append({'id': profile_id, 'name': item['name'], **public_config(item['config']),
                         'capabilities': item.get('capabilities') or _capability_defaults(item['config'])})
    return {'schema_version': document.get('schema_version', 1), 'profiles': profiles,
            'default': public_config(get_model_settings(settings)),
            'assignments': {stage: document.get('stage_assignments', {}).get(stage, 'default') for stage in STAGES},
            'embedding': {'provider': 'local', 'status': 'separate_configuration',
                          'message': '聊天連線不會變更 embedding 模型或維度，也不會重建索引。'}}


def save_profile(payload, settings=None):
    import uuid
    if not isinstance(payload, dict) or set(payload) - {'id', 'name', 'config', 'from_default'}:
        raise SettingsError('模型連線格式不正確。')
    name = payload.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise SettingsError('請填入 1–100 字的連線名稱。')
    profile_id = payload.get('id') or 'connection_' + uuid.uuid4().hex
    if not isinstance(profile_id, str) or not re.fullmatch(r'connection_[a-f0-9]{32}', profile_id):
        raise SettingsError('連線識別碼不正確。')
    draft = payload.get('config')
    if payload.get('from_default') is True:
        selected = get_model_settings(settings)
        draft = {key: selected[key] for key in ('provider', 'base_url', 'model', 'api_key')}
    if not isinstance(draft, dict) or set(draft) - {'provider', 'base_url', 'model', 'api_key'}:
        raise SettingsError('具名連線只保存模型金鑰，不承接管理授權。')
    with _LOCK:
        document = _profile_document(settings)
        profiles = document.setdefault('profiles', {})
        if len(profiles) >= 20 and profile_id not in profiles:
            raise SettingsError('最多保存 20 組具名連線。')
        current = profiles.get(profile_id, {}).get('config') or {'provider': '', 'base_url': '', 'model': '', 'api_key': ''}
        validated = validate_draft(draft, current, require_compatible=False)
        validated.pop('balance_api_key', None)
        validated.pop('balance_account_id', None)
        profiles[profile_id] = {'name': name.strip(), 'config': validated, 'capabilities': _capability_defaults(validated)}
        document['schema_version'] = 2
        _write_profile_document(document, settings)
    return profiles_config(settings)


def assign_profiles(payload, settings=None):
    if not isinstance(payload, dict) or set(payload) - set(STAGES):
        raise SettingsError('階段配置格式不正確。')
    with _LOCK:
        document = _profile_document(settings)
        known = {'default', *document.get('profiles', {})}
        if any(not isinstance(value, str) or value not in known for value in payload.values()):
            raise SettingsError('請選擇已保存的連線。')
        document.setdefault('stage_assignments', {}).update(payload)
        document['schema_version'] = 2
        _write_profile_document(document, settings)
    return profiles_config(settings)


def remove_profile(profile_id, settings=None):
    with _LOCK:
        document = _profile_document(settings)
        if profile_id in document.get('stage_assignments', {}).values():
            raise SettingsError('請先將使用這組連線的階段改回預設，再移除。', 409)
        if profile_id not in document.get('profiles', {}):
            raise SettingsError('找不到此連線。', 404)
        del document['profiles'][profile_id]
        _write_profile_document(document, settings)
    return profiles_config(settings)


def test_profile(profile_id, settings=None):
    with _LOCK:
        document = _profile_document(settings)
        original = document.get('profiles', {}).get(profile_id)
        if not original:
            raise SettingsError('找不到此連線。', 404)
        config = dict(original['config'])
    rows = _request_json(config, '/models').get('data')
    if not isinstance(rows, list):
        raise SettingsError('服務沒有回傳模型清單；仍可手動指定模型，生成能力尚未驗證。', 502)
    models = sorted({row['id'] for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str) and len(row['id']) <= 200})[:3000]
    capability = {**_capability_defaults(config), 'reachable': 'verified', 'model_list': 'verified', 'checked_at': now()}
    with _LOCK:
        latest = _profile_document(settings)
        current = latest.get('profiles', {}).get(profile_id)
        if not current or current['config'] != config:
            raise SettingsError('測試期間連線已變更，已丟棄舊結果。', 409)
        current['capabilities'] = capability
        _write_profile_document(latest, settings)
    return {'profile_id': profile_id, 'models': models, 'capabilities': capability,
            'mode': 'models_only', 'generation_performed': False}


def _router_wallet(value, result):
    if not value.get('balance_api_key'):
        return result | {'status': 'authorization_required', 'message': '請填入獨立的 9Router CLI 授權碼，以唯讀方式查詢帳戶。模型金鑰不能代替此授權。'}
    account_id = value.get('balance_account_id')
    if not account_id:
        return result | {'status': 'account_required', 'message': '請先選擇要查看餘額的 OpenCode Go 帳戶。'}
    accounts = provider_accounts(value=value)['accounts']
    if account_id not in {row['id'] for row in accounts}:
        raise SettingsError('找不到已選擇的 OpenCode Go 帳戶，請重新載入帳戶清單。', 409)
    data = _request_json(value, '/api/usage/' + account_id, balance_admin=True)
    wallet = data.get('walletSync') if isinstance(data.get('walletSync'), dict) else {}
    snapshot = data.get('consoleSnapshot') if isinstance(data.get('consoleSnapshot'), dict) else {}
    balance = wallet.get('balanceUSD')
    checked_at, source = wallet.get('checkedAt'), 'wallet_sync'
    valid_balance = lambda amount: isinstance(amount, (int, float)) and not isinstance(amount, bool) and math.isfinite(amount)
    if not valid_balance(balance) and valid_balance(snapshot.get('balanceUSD')):
        balance, checked_at, source = snapshot['balanceUSD'], snapshot.get('checkedAt'), 'manual_snapshot'
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(checked_at.replace('Z', '+00:00'))).total_seconds()
    except (AttributeError, ValueError, TypeError):
        age = math.inf
    fresh = source == 'wallet_sync' and wallet.get('status') == 'ok' and 0 <= age <= 660
    status = ('available' if fresh else 'stale') if valid_balance(balance) else 'not_synced'
    quotas = []
    raw_quotas = data.get('quotas')
    for key, label in (('Session (5h)', 'rolling'), ('Weekly', 'weekly'), ('Monthly', 'monthly')):
        row = raw_quotas.get(key) if isinstance(raw_quotas, dict) else None
        if isinstance(row, dict) and _number(row.get('remainingPercentage')) is not None:
            remaining = min(100, row['remainingPercentage'])
            quotas.append({'id': label, 'remaining_percent': remaining, 'used_percent': 100 - remaining,
                           'resets_at': _timestamp(row.get('resetAt')),
                           'status': row.get('status') if row.get('status') in {'ok', 'rate-limited'} else 'unknown'})
    message = {'available': '這是 9Router 最近同步的 OpenCode 帳戶餘額。',
               'stale': '顯示上次取得的餘額；同步資料已過期或尚未完成，請在 9Router 查看同步狀態。',
               'not_synced': '尚未取得錢包餘額。請在 9Router 完成 OpenCode 帳戶登入與餘額同步。'}[status]
    if source == 'manual_snapshot':
        message = '這是 9Router 的手動帳戶快照，不會自動更新，請確認資料時間。'
    return result | {'supported': True, 'status': status, 'kind': 'wallet', 'currency': 'USD',
                     'remaining': balance if valid_balance(balance) else None, 'quotas': quotas,
                     'source': source, 'checked_at': _timestamp(checked_at),
                     'fetched_at': now(), 'message': message,
                     'sync_status': wallet.get('status') if wallet.get('status') in {'ok', 'checking', 'login-required', 'account-mismatch', 'page-changed', 'unavailable'} else 'unknown'}


def provider_balance(settings=None):
    value = get_model_settings(settings)
    result = {'supported': False, 'status': 'unsupported', 'kind': None, 'currency': None,
              'remaining': None, 'used': None, 'limit': None, 'quotas': [], 'checked_at': now()}
    provider = value['provider']
    expected = _PRESETS.get(provider, {}).get('base_url')
    if provider == 'ninerouter':
        return _router_wallet(value, result)
    if provider not in {'openrouter', 'opencode_go'} or value['base_url'].rstrip('/') != expected:
        return result | {'message': '此服務沒有供一般模型金鑰使用的標準餘額介面，請至服務商帳戶頁查看。'}
    if not value['api_key']:
        raise SettingsError('請先儲存模型服務金鑰。')
    if provider == 'openrouter':
        data = _request_json(value, '/key').get('data')
        if not isinstance(data, dict) or 'limit' not in data or 'limit_remaining' not in data:
            raise SettingsError('OpenRouter 未提供可辨識的金鑰額度。', 502)
        limit, remaining, used = _number(data.get('limit')), _number(data.get('limit_remaining')), _number(data.get('usage'))
        unlimited = data.get('limit') is None and data.get('limit_remaining') is None
        if not unlimited and (limit is None or remaining is None):
            raise SettingsError('OpenRouter 額度資料不完整，請至官方帳戶頁確認。', 502)
        return result | {'supported': True, 'status': 'unlimited' if unlimited else 'available',
                         'kind': 'key_allowance', 'currency': 'USD', 'remaining': remaining, 'used': used, 'limit': limit,
                         'message': '這是目前 API 金鑰的可用限額，不是帳戶錢包餘額。' + ('此金鑰未設定限額。' if unlimited else '')}
    data = _request_json(value, '/usage').get('usage')
    if not isinstance(data, dict):
        raise SettingsError('OpenCode Go 未提供可辨識的用量資料。', 502)
    quotas = []
    for period in ('rolling', 'weekly', 'monthly'):
        row = data.get(period)
        if not isinstance(row, dict):
            continue
        percent = _number(row.get('percent'))
        if percent is None:
            continue
        reset = row.get('resetsAt')
        quotas.append({'id': period, 'used_percent': min(100, percent), 'remaining_percent': max(0, 100 - percent),
                       'resets_at': _timestamp(reset),
                       'status': row.get('status') if row.get('status') in {'ok', 'rate-limited'} else 'unknown'})
    if not quotas:
        raise SettingsError('OpenCode Go 用量資料不完整，請至官方帳戶頁確認。', 502)
    return result | {'supported': True, 'status': 'available', 'kind': 'subscription_quota', 'quotas': quotas,
                     'message': '顯示 OpenCode Go 訂閱用量與重設時間；服務沒有提供美元錢包餘額。'}
