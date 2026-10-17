"""Same-origin, local-only workbench API. Viewing never starts paid work."""
from flask import Blueprint, Response, jsonify, request
from .settings import guard_settings, private_response, safe_error, csrf_token
from ..provider_settings import SettingsError
from ..services.research_workbench import ResearchWorkbench, valid_id
from ..services.evidence_store import EvidenceError
from ..services.source_importer import SourceImportError

workbench_bp = Blueprint('workbench', __name__)
workbench_bp.before_request(guard_settings)
workbench_bp.after_request(private_response)
workbench_bp.register_error_handler(SettingsError, safe_error)


@workbench_bp.errorhandler(SourceImportError)
def collection_error(error):
    return jsonify(success=False, error=str(error), code=error.code), error.status


@workbench_bp.errorhandler(EvidenceError)
@workbench_bp.errorhandler(ValueError)
def invalid(error):
    return jsonify(success=False, error=str(error)), 400


def body(allowed):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise EvidenceError('請求欄位無效。')
    return data


def page_args():
    limit, offset = int(request.args.get('limit', 50)), int(request.args.get('offset', 0))
    if not 1 <= limit <= 200 or offset < 0:
        raise EvidenceError('分頁範圍無效。')
    return {'limit': limit, 'offset': offset}


def ok(data):
    return jsonify(success=True, data=data)


@workbench_bp.get('/session')
def session():
    return ok({'csrf_token': csrf_token()})


@workbench_bp.get('/projects')
def projects():
    return ok(ResearchWorkbench().projects(request.args.get('q', ''), request.args.get('archived') == '1', **page_args()))


@workbench_bp.post('/projects')
def create_project():
    data = body({'name', 'requirement'})
    return ok(ResearchWorkbench().create(data.get('name'), data.get('requirement', ''))), 201


@workbench_bp.get('/projects/<project_id>')
def project(project_id):
    return ok(ResearchWorkbench().detail(project_id))


@workbench_bp.patch('/projects/<project_id>')
def edit_project(project_id):
    return ok(ResearchWorkbench().edit(project_id, body({'name', 'archived'})))


@workbench_bp.post('/projects/<project_id>/clone')
def clone_project(project_id):
    body(set())
    return ok(ResearchWorkbench().clone(project_id)), 201


@workbench_bp.post('/projects/<project_id>/legacy-index')
def legacy_index(project_id):
    body(set())
    return ok(ResearchWorkbench().legacy_sources(project_id))


@workbench_bp.get('/projects/<project_id>/sources')
def project_sources(project_id):
    service = ResearchWorkbench()
    service.project(project_id)
    return ok(service.evidence.list_sources(project_id, **page_args()))


@workbench_bp.post('/projects/<project_id>/sources')
def add_source(project_id):
    data = body({'title', 'content', 'source_type', 'identity'})
    if data.get('source_type', 'document') not in {'document', 'user_note'} or not isinstance(data.get('content'), str):
        raise EvidenceError('請提供本機文件文字。網址擷取請使用網頁來源入口。')
    return ok(ResearchWorkbench().save_source(project_id, **data)), 201


@workbench_bp.get('/sources/<source_id>')
def source(source_id):
    evidence = ResearchWorkbench().evidence
    row = evidence.get_source(valid_id(source_id))
    if not row:
        raise EvidenceError('找不到此來源。')
    return ok({'source': row, 'versions': evidence.list_versions(source_id, **page_args()),
               'latest_version_id': evidence.latest_version_id(source_id)})


@workbench_bp.get('/versions/<version_id>')
def version(version_id):
    evidence = ResearchWorkbench().evidence
    row = evidence.get_version(valid_id(version_id), include_content=True)
    if not row:
        raise EvidenceError('找不到此保存版本。')
    return ok({**row, 'spans': evidence.list_spans(version_id, **page_args())})


@workbench_bp.post('/versions/<version_id>/spans')
def span(version_id):
    data = body({'start', 'end', 'quote'})
    return ok(ResearchWorkbench().evidence.create_span(valid_id(version_id), data.get('start'), data.get('end'), data.get('quote'))), 201


@workbench_bp.get('/projects/<project_id>/references')
def references(project_id):
    service = ResearchWorkbench()
    service.project(project_id)
    return ok(service.references(project_id, subject_type=request.args.get('subject_type'),
                                 subject_id=request.args.get('subject_id'), **page_args()))


@workbench_bp.post('/projects/<project_id>/references')
def reference(project_id):
    data = body({'subject_type', 'subject_id', 'category', 'relation', 'source_id', 'version_id', 'span_id', 'run_id', 'event_id', 'note'})
    service = ResearchWorkbench()
    service.project(project_id)
    if not {'subject_type', 'subject_id', 'category', 'relation'} <= set(data):
        raise EvidenceError('引用缺少分類或對象。')
    return ok(service.evidence.add_reference(project_id, **data)), 201


@workbench_bp.get('/projects/<project_id>/quality')
def quality(project_id):
    return ok(ResearchWorkbench().quality(project_id))


@workbench_bp.get('/tasks')
def tasks():
    return ok(ResearchWorkbench().tasks())


@workbench_bp.route('/projects/<project_id>/plans', methods=['GET', 'POST'])
def plans(project_id):
    data = body({'kind', 'definition'}) if request.method == 'POST' else {}
    return ok(ResearchWorkbench().plans(project_id, **data))


@workbench_bp.get('/projects/<project_id>/export')
def export(project_id):
    format = request.args.get('format', 'md')
    text, mimetype = ResearchWorkbench().export(project_id, format)
    response = Response(text, content_type=mimetype)
    response.headers['Content-Disposition'] = f'{"inline" if format == "html" else "attachment"}; filename="{valid_id(project_id)}.{format}"'
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'"
    return response


@workbench_bp.get('/simulations/<simulation_id>/events')
def events(simulation_id):
    from ..services.event_store import EventStore
    return ok(EventStore.page(valid_id(simulation_id), cursor=request.args.get('cursor'),
                             limit=page_args()['limit'], platform=request.args.get('platform'),
                             agent_id=request.args.get('agent_id')))


@workbench_bp.get('/projects/<project_id>/events/<event_id>')
def saved_event(project_id, event_id):
    """Resolve only a preserved pointer; never ingest logs or start execution."""
    from ..services.event_store import EventStore
    ResearchWorkbench().project(project_id)
    event = EventStore.get_event(valid_id(request.args.get('run_id')), valid_id(event_id))
    if not event or event.get('project_id') != project_id:
        return jsonify(success=False, error='找不到此研究中的保存事件。'), 404
    return ok(event)


@workbench_bp.get('/simulations/<simulation_id>/projection')
def projection(simulation_id):
    from ..services.event_store import EventStore
    return ok(EventStore.project(valid_id(simulation_id), int(request.args.get('through_seq', 0))))


@workbench_bp.get('/compare')
def compare():
    from ..services.event_store import EventStore
    return ok(EventStore.compare(valid_id(request.args.get('left')), valid_id(request.args.get('right'))))


@workbench_bp.get('/demos')
def demos():
    from ..services.workbench_demos import CATALOG
    return ok({'items': CATALOG})


@workbench_bp.post('/demos/<demo_id>')
def demo(demo_id):
    from ..services.workbench_demos import install
    body(set())
    return ok(install(demo_id)), 201


@workbench_bp.post('/sources/<source_id>/refresh')
def refresh(source_id):
    # Same adapter, reservations, failure accounting, DNS rules and 24h cache.
    # Refresh cannot bypass the budget or automatically rebuild a graph.
    from .sources import importer
    body(set())
    service = ResearchWorkbench()
    source = service.evidence.get_source(valid_id(source_id))
    if not source or source['source_type'] != 'web' or not source['locator']:
        raise EvidenceError('此來源不是可更新的網頁。')
    plan = importer().plan([source['locator']])
    result = importer().fetch(plan['plan_id'])
    versions = []
    for document in result['documents']:
        record = service.save_source(source['project_id'], title=source['title'],
                    content=document['markdown'], identity=source['identity'],
                    source_type='web', locator=source['locator'],
                    parser_version='firecrawl-markdown-v1', fetched_at=document['fetched_at'],
                    published_at=document.get('published_at'))
        versions.append(record['version'])
    return ok({'versions': versions, 'collection': result, 'rebuild_started': False})


@workbench_bp.post('/projects/<project_id>/web-plan')
def web_plan(project_id):
    from .sources import importer
    ResearchWorkbench().project(project_id)
    data = body({'urls'})
    return ok(importer().plan(data.get('urls'), project_id=project_id))


@workbench_bp.post('/projects/<project_id>/web-preview')
def web_preview(project_id):
    from .sources import importer
    ResearchWorkbench().project(project_id)
    data = body({'plan_id'})
    adapter = importer()
    adapter.require_plan_project(data.get('plan_id'), project_id)
    result = adapter.fetch(data.get('plan_id'))
    candidates = [{**document, 'published_at': document.get('published_at'),
                   'parse_status': document.get('parse_status', 'truncated' if document.get('truncated') else 'parsed')}
                  for document in result['documents']]
    return ok({'plan_id': data['plan_id'], 'candidates': candidates,
               'collection': {key: value for key, value in result.items() if key != 'documents'},
               'sources_saved': False, 'rebuild_started': False})


def _save_web_documents(service, project_id, documents):
    return [service.save_source(project_id, title=document['title'], content=document['markdown'],
                source_type='web', identity=document['url'], locator=document['url'],
                parser_version='firecrawl-markdown-v1', fetched_at=document['fetched_at'],
                published_at=document.get('published_at')) for document in documents]


@workbench_bp.post('/projects/<project_id>/web-adopt')
def web_adopt(project_id):
    from .sources import importer
    service = ResearchWorkbench()
    service.project(project_id)
    data = body({'plan_id', 'urls'})
    documents = importer().saved_selection(data.get('plan_id'), data.get('urls'), project_id=project_id)
    records = _save_web_documents(service, project_id, documents)
    return ok({'plan_id': data['plan_id'], 'selected_urls': [document['url'] for document in documents],
               'records': records, 'external_calls': 0, 'rebuild_started': False})


@workbench_bp.post('/projects/<project_id>/web-fetch')
def web_fetch(project_id):
    from .sources import importer
    service = ResearchWorkbench()
    service.project(project_id)
    data = body({'plan_id'})
    adapter = importer()
    adapter.require_plan_project(data.get('plan_id'), project_id)
    result = adapter.fetch(data.get('plan_id'))
    records = _save_web_documents(service, project_id, result['documents'])
    return ok({'records': records, 'collection': result, 'rebuild_started': False})
