"""Optional sources API; uploaded files and the graph workflow remain independent."""

from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, current_app, request

from ..services.source_importer import SourceImporter, SourceImportError

sources_bp = Blueprint('sources', __name__)


def importer():
    # SQLite also protects reservations if concurrent first requests make two adapters.
    if 'source_importer' not in current_app.extensions:
        current_app.extensions['source_importer'] = SourceImporter(current_app.config)
    return current_app.extensions['source_importer']


def handle_errors(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            if request.method == 'POST':
                origin = request.headers.get('Origin')
                if origin and urlsplit(origin).hostname not in {'localhost', '127.0.0.1', '::1'}:
                    raise SourceImportError('origin', '請從本機 MiroFish 網站使用網頁資料擷取。', 403)
            return {'success': True, 'data': func(*args, **kwargs)}
        except SourceImportError as exc:
            return {'success': False, 'error': str(exc), 'code': exc.code}, exc.status
        except Exception:
            # Never leak API keys, provider responses or database paths. A storage
            # failure stops work rather than letting requests bypass the budget.
            return {'success': False, 'error': '網頁資料收集暫時無法使用，請稍後再試。', 'code': 'storage'}, 503
    return wrapped


def body_with_only(key):
    if request.content_length and request.content_length > 16 * 1024:
        raise SourceImportError('invalid_url', '網址清單太長，請減少網址數量。')
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {key}:
        raise SourceImportError('invalid_request', '請使用畫面提供的擷取操作。')
    return body[key]


@sources_bp.get('/status')
@handle_errors
def status():
    return importer().status(probe=True)


@sources_bp.post('/plan')
@handle_errors
def plan():
    return importer().plan(body_with_only('urls'))


@sources_bp.post('/fetch')
@handle_errors
def fetch():
    return importer().fetch(body_with_only('plan_id'))
