"""Uniform local-only guard for every /api route.

The settings and workbench blueprints grew their own protection first; the
graph/simulation/report/sources API kept none. This module owns the shared
policy pieces so create_app can enforce them for all of /api in one place.

Policy:
  * Host must resolve to a loopback name (rejects DNS-rebinding Host values).
  * A present Origin must be http(s) on a loopback name with a dev port or none.
  * Sec-Fetch-Site: cross-site is rejected outright.
  * POST/PUT/PATCH/DELETE additionally carry the shared X-MiroFish-CSRF token.
No content-type rule lives here: multipart uploads are legitimate writes.
"""
import secrets
from urllib.parse import urlsplit

from flask import current_app, jsonify, request

LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})
TRUSTED_ORIGIN_PORTS = frozenset({None, 3000, 3100, 5001})
TRUSTED_ORIGINS = tuple(
    f'{scheme}://{host}{"" if port is None else f":{port}"}'
    for scheme in ('http', 'https')
    for host in ('localhost', '127.0.0.1')
    for port in (None, 3000, 3100, 5001)
)
CSRF_HEADER = 'X-MiroFish-CSRF'
WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
# /health lives outside /api, and GET /api/session only bootstraps the token,
# so no path needs an exemption.
GUARD_EXEMPT_PATHS = frozenset()


def csrf_token():
    """Shared session token; same extension key the settings/workbench API uses."""
    return current_app.extensions.setdefault('provider_settings_csrf', secrets.token_urlsafe(32))


def is_trusted_origin(origin: str) -> bool:
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    return (parts.scheme in {'http', 'https'}
            and parts.hostname in LOCAL_HOSTS
            and parts.port in TRUSTED_ORIGIN_PORTS)


def guard_api_request():
    """Return a 403 JSON response for untrusted /api requests, else None."""
    path = request.path
    if path in GUARD_EXEMPT_PATHS or not (path == '/api' or path.startswith('/api/')):
        return None
    try:
        host = urlsplit('http://' + request.host).hostname
    except ValueError:
        host = None
    if host not in LOCAL_HOSTS:
        return jsonify(success=False, error='本服務只能從本機存取。'), 403
    origin = request.headers.get('Origin')
    if origin and not is_trusted_origin(origin):
        return jsonify(success=False, error='不允許此外部網頁存取本服務。'), 403
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        return jsonify(success=False, error='不允許跨網站存取本服務。'), 403
    if request.method in WRITE_METHODS:
        supplied = request.headers.get(CSRF_HEADER, '')
        try:
            matches = bool(supplied) and secrets.compare_digest(supplied, csrf_token())
        except TypeError:  # non-ASCII header value can never be the token
            matches = False
        if not matches:
            return jsonify(success=False, error='操作驗證碼無效，請重新載入頁面後再試。'), 403
    return None
