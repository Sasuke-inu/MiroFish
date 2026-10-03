"""Local-only settings API: no secrets in responses, logs, caches or URLs."""
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request

from ..provider_settings import (PRESETS, SettingsError, get_model_settings,
                                 provider_accounts, provider_balance, public_config,
                                 save_settings, test_connection)

settings_bp = Blueprint('settings', __name__)
_LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def csrf_token():
    return current_app.extensions.setdefault('provider_settings_csrf', secrets.token_urlsafe(32))


@settings_bp.before_request
def guard_settings():
    # Do not trust forwarded headers: only local desktop hosts can administer
    # this installation. This also rejects DNS-rebinding Host values.
    try:
        host = urlsplit('http://' + request.host).hostname
    except ValueError:
        host = None
    if host not in _LOCAL_HOSTS:
        raise SettingsError('服務設定只能從本機存取。', 403)
    origin = request.headers.get('Origin')
    if origin:
        try:
            parts = urlsplit(origin)
            trusted = parts.scheme in {'http', 'https'} and parts.hostname in _LOCAL_HOSTS and parts.port in {None, 3000, 3100, 5001}
        except ValueError:
            trusted = False
        if not trusted:
            raise SettingsError('不允許此外部網頁存取服務設定。', 403)
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        raise SettingsError('不允許跨網站存取服務設定。', 403)
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        if request.content_length is None or request.content_length > 16 * 1024:
            raise SettingsError('設定請求過大或缺少長度。', 413)
        if not request.is_json:
            raise SettingsError('請使用 JSON 格式儲存設定。', 415)
        supplied = request.headers.get('X-MiroFish-CSRF', '')
        if not supplied or not secrets.compare_digest(supplied, csrf_token()):
            raise SettingsError('設定頁已過期，請重新載入後再試。', 403)


@settings_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Flask-CORS must not turn a local settings endpoint into a public API.
    response.headers.pop('Access-Control-Allow-Origin', None)
    return response


@settings_bp.errorhandler(SettingsError)
def safe_error(error):
    return jsonify(success=False, error=str(error)), error.status


def envelope(config):
    return {'config': config, 'presets': PRESETS, 'csrf_token': csrf_token()}


@settings_bp.get('/providers')
def get_providers():
    return jsonify(success=True, data=envelope(public_config(get_model_settings(current_app.config))))


@settings_bp.put('/providers')
def put_providers():
    config = save_settings(request.get_json(silent=True), current_app.config)
    return jsonify(success=True, data=envelope(config))


@settings_bp.post('/providers/test')
def test_provider():
    return jsonify(success=True, data=test_connection(request.get_json(silent=True), current_app.config))


@settings_bp.get('/providers/accounts')
def get_accounts():
    return jsonify(success=True, data=provider_accounts(current_app.config))


@settings_bp.get('/providers/balance')
def get_balance():
    return jsonify(success=True, data=provider_balance(current_app.config))
