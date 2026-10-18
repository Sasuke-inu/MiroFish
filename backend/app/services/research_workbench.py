"""Local research views over existing projects, runs, reports and evidence.

No method in this module calls a model, starts a run or contacts a URL.
Source material is untrusted text. Exports escape it and select one project.
"""
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import uuid

from ..storage import database
from ..models.project import ProjectManager
from ..models.execution import RunStore, public_manifest
from ..models.task import TaskManager
from .evidence_store import EvidenceStore, EvidenceError


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise EvidenceError('無效的研究識別碼。')
    return value


def preserve_upload(project_id, filename, text):
    """Recognize only server-preserved Firecrawl content, never a forged header."""
    from ..config import Config
    from .source_importer import SourceImporter
    from .text_processor import TextProcessor
    from flask import current_app
    evidence = EvidenceStore()
    source_type, identity, locator, fetched = 'document', filename, None, None
    if filename.startswith('web-'):
        settings = {**{key: getattr(Config, key) for key in dir(Config) if key.isupper()}, **current_app.config}
        importer = SourceImporter(settings)
        with importer.db() as db:
            cached = db.execute('SELECT document FROM cache ORDER BY fetched DESC LIMIT 200').fetchall()
        for row in cached:
            document = json.loads(row['document'])
            if document.get('filename') == filename and TextProcessor.preprocess_text(document.get('markdown', '')) == text:
                source_type, identity, locator = 'web', document['url'], document['url']
                fetched = document.get('fetched_at')
                break
    source = evidence.create_source(project_id, source_type, identity, title=filename, locator=locator)
    return evidence.add_version(source['source_id'], text,
                                parser_version='firecrawl-upload-v1' if source_type == 'web' else 'file-parser-v1',
                                fetched_at=fetched)


class ResearchWorkbench:
    def __init__(self):
        self.evidence = EvidenceStore()
        with database() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS research_meta (
                    project_id TEXT PRIMARY KEY, archived INTEGER NOT NULL DEFAULT 0,
                    demo TEXT, origin_project_id TEXT
                );
                CREATE TABLE IF NOT EXISTS research_plans (
                    plan_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    kind TEXT NOT NULL, definition TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS demo_installations (
                    demo_id TEXT PRIMARY KEY, project_id TEXT NOT NULL
                );
            ''')

    def project(self, project_id):
        project = ProjectManager.get_project(valid_id(project_id))
        if not project:
            raise EvidenceError('找不到此研究。')
        result = public_manifest(project.to_dict())
        with database() as db:
            meta = db.execute('SELECT * FROM research_meta WHERE project_id=?', (project_id,)).fetchone()
        result.update(archived=bool(meta['archived']) if meta else False,
                      demo=meta['demo'] if meta else None,
                      origin_project_id=meta['origin_project_id'] if meta else None)
        return result

    def projects(self, query='', archived=False, limit=50, offset=0):
        # A navigation list needs summaries, not every project's full ontology
        # and uploaded-file metadata. Read each project file only once.
        with database() as db:
            metadata = {row['project_id']: dict(row) for row in db.execute('SELECT * FROM research_meta')}
        items = []
        for project in ProjectManager.list_projects(limit=None):
            meta = metadata.get(project.project_id, {})
            item = {key: value for key, value in public_manifest(project.to_dict()).items()
                    if key in {'project_id', 'name', 'status', 'created_at', 'updated_at',
                               'simulation_requirement', 'graph_id', 'total_text_length'}}
            item.update(archived=bool(meta.get('archived')), demo=meta.get('demo'),
                        origin_project_id=meta.get('origin_project_id'))
            items.append(item)
        items = [item for item in items if item['archived'] == archived and
                 query.casefold() in (item['name'] + ' ' + (item.get('simulation_requirement') or '')).casefold()]
        return {'items': items[offset:offset+limit], 'total': len(items), 'has_more': offset+limit < len(items)}

    def create(self, name, requirement=''):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise EvidenceError('研究名稱須為 1–200 個字。')
        if not isinstance(requirement, str) or len(requirement) > 12000:
            raise EvidenceError('研究問題太長。')
        project = ProjectManager.create_project(name.strip())
        project.simulation_requirement = requirement
        ProjectManager.save_project(project)
        return self.project(project.project_id)

    def edit(self, project_id, changes):
        self.project(project_id)
        if not changes or set(changes) - {'name', 'archived'}:
            raise EvidenceError('只可修改研究名稱或封存狀態。')
        if 'name' in changes:
            name = changes['name']
            if not isinstance(name, str) or not name.strip() or len(name) > 200:
                raise EvidenceError('研究名稱須為 1–200 個字。')
            project = ProjectManager.get_project(project_id)
            project.name = name.strip()
            ProjectManager.save_project(project)
        if 'archived' in changes:
            if type(changes['archived']) is not bool:
                raise EvidenceError('封存狀態必須是布林值。')
            with database() as db:
                db.execute('INSERT INTO research_meta(project_id,archived) VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET archived=excluded.archived',
                           (project_id, int(changes['archived'])))
        return self.project(project_id)

    def clone(self, project_id):
        original = self.project(project_id)
        draft = self.create(original['name'][:190] + ' · 副本', original.get('simulation_requirement') or '')
        with database() as db:
            db.execute('INSERT INTO research_meta(project_id,origin_project_id) VALUES(?,?)', (draft['project_id'], project_id))
        # Source snapshots are copied as inputs; no graph, tasks, environment,
        # credentials or mutable run state crosses the new project identity.
        for source in self.all_sources(project_id):
            version = self.latest_version(source['source_id'], include_content=True)
            if version:
                self.save_source(draft['project_id'], title=source['title'], source_type=source['source_type'],
                                 identity=source['identity'], locator=source.get('locator'),
                                 content=version.get('content'), status=version['status'],
                                 parser_version=version['parser_version'])
        return self.project(draft['project_id'])

    def all_sources(self, project_id):
        result, offset = [], 0
        while True:
            page = self.evidence.list_sources(project_id, limit=200, offset=offset)
            result.extend(page['items'])
            if not page['has_more']:
                return result
            offset += 200

    def latest_version(self, source_id, *, include_content=False):
        """The last observed version; legacy rows without a pointer fall back."""
        version = self.evidence.latest_version(source_id, include_content=include_content)
        if version is not None:
            return version
        page = self.evidence.list_versions(source_id, limit=1)['items']
        return self.evidence.get_version(page[0]['version_id'], include_content=include_content) if page else None

    def save_source(self, project_id, *, title, content=None, source_type='document', identity=None,
                    locator=None, parser_version='text-v1', status='saved', fetched_at=None, published_at=None):
        self.project(project_id)
        source = self.evidence.create_source(project_id, source_type, identity or uuid.uuid4().hex,
                                             title=title, locator=locator)
        version = self.evidence.add_version(source['source_id'], content, parser_version=parser_version,
                                            status=status, fetched_at=fetched_at, published_at=published_at)
        # A draft can enter the existing ontology/build journey without a
        # second uploader. Historical projects keep their frozen build text.
        with ProjectManager.input_mutation_lock(project_id):
            project = ProjectManager.get_project(project_id)
            if (str(getattr(project.status, 'value', project.status)) == 'created'
                    and not TaskManager().find_task(f'ontology:{project_id}')):
                parts, input_versions = [], []
                for item in self.all_sources(project_id):
                    saved = self.latest_version(item['source_id'], include_content=True)
                    if saved and saved.get('content'):
                        parts.append(f"=== {item['title']} ===\n{saved['content']}")
                        input_versions.append({key: saved[key] for key in ('source_id', 'version_id', 'sha256')})
                combined = '\n\n'.join(parts)
                ProjectManager.save_input_snapshot(project_id, combined, input_versions)
                ProjectManager.save_extracted_text(project_id, combined)
                project.total_text_length = len(combined)
                project.source_versions = input_versions
                ProjectManager.save_project(project)
        return {'source': source, 'version': version}

    def legacy_sources(self, project_id):
        """Explicit, repeatable indexing of stored text; never re-run extraction."""
        self.project(project_id)
        text = ProjectManager.get_extracted_text(project_id)
        return self.save_source(project_id, title='既有研究保存文字', identity='legacy-extracted-text',
                                source_type='legacy_document', content=text if text else None,
                                status='saved' if text else 'missing', parser_version='legacy-combined-v1')

    def runs(self, project_id):
        from .simulation_manager import SimulationManager
        from .simulation_runner import SimulationRunner
        result = []
        for simulation in SimulationManager().list_simulations(project_id=project_id):
            row = RunStore.get(simulation.simulation_id, reconcile=True)
            if row:
                result.append({k: v for k, v in public_manifest(row).items() if k not in {'owner', 'worker_id'}})
            else:
                state = SimulationRunner.get_run_state(simulation.simulation_id)
                result.append({'simulation_id': simulation.simulation_id, 'run_id': None,
                               'status': state.runner_status.value if state else simulation.status.value,
                               'graph_ready': False, 'manifest': {}, 'legacy': True,
                               'limitations': ['歷史紀錄沒有完整執行快照，不補造來源或模型。']})
        # Synthetic fixtures use the same RunStore without creating an OASIS process.
        with database() as db:
            RunStore._schema(db)
            rows = [RunStore._decode(row) for row in db.execute('SELECT * FROM executions')]
        known = {item['simulation_id'] for item in result}
        for row in rows:
            if row['manifest'].get('project_id') == project_id and row['simulation_id'] not in known:
                result.append({k: v for k, v in public_manifest(row).items() if k not in {'owner', 'worker_id'}})
        return result

    @staticmethod
    def _public_report(report):
        raw = report.to_dict()
        allowed = {'report_id', 'simulation_id', 'graph_id', 'simulation_requirement', 'status',
                   'outline', 'markdown_content', 'created_at', 'completed_at', 'run_id', 'task_id', 'version'}
        result = {key: raw[key] for key in allowed if key in raw}
        result['error'] = '報告未完整完成；內部診斷未包含於公開資料。' if raw.get('error') else None
        # Body and saved outline text are intentional report content. Metadata
        # is handled separately so sanitizing diagnostics never deletes prose.
        manifest_keys = {'model', 'graph_id', 'execution', 'version', 'completeness', 'kind',
                         'source_versions', 'generator_version', 'external_calls'}
        def metadata(value):
            if isinstance(value, dict):
                return {key: metadata(item) for key, item in value.items()
                        if str(key).lower() not in {'error', 'traceback', 'stack_trace', 'debug', 'logs', 'diagnostics', 'raw_response'}
                        and not str(key).lower().endswith(('_path', '_folder', '_directory', '_dir'))}
            if isinstance(value, list):
                return [metadata(item) for item in value]
            return value
        raw_manifest = raw.get('manifest') if isinstance(raw.get('manifest'), dict) else {}
        result['manifest'] = public_manifest(metadata({key: raw_manifest[key] for key in manifest_keys if key in raw_manifest}))
        return result

    def detail(self, project_id):
        from .report_agent import ReportManager
        project = self.project(project_id)
        runs = self.runs(project_id)
        ids = {run['simulation_id'] for run in runs}
        reports = [self._public_report(report) for report in ReportManager.list_reports(limit=None) if report.simulation_id in ids]
        return {'project': project, 'sources': self.evidence.list_sources(project_id),
                'references': self.references(project_id), 'runs': runs, 'reports': reports}

    def references(self, project_id, **kwargs):
        from .event_store import EventStore
        page = self.evidence.list_references(project_id, **kwargs)
        for ref in page['items']:
            ref['validation'] = self.evidence.validate_reference(ref['reference_id'], event_resolver=EventStore.get_event)
        return page

    def quality(self, project_id, *, _export=None):
        # An export already loaded these immutable records. Reuse that snapshot
        # instead of repeating every file and ledger read on Windows mounts.
        if _export is None:
            self.project(project_id)
            sources = self.all_sources(project_id)
            refs, offset = [], 0
            while True:
                page = self.references(project_id, limit=200, offset=offset)
                refs.extend(page['items'])
                if not page['has_more']:
                    break
                offset += 200
            latest = [self.latest_version(source['source_id']) for source in sources]
            runs = self.runs(project_id)
        else:
            sources = _export['sources']['items']
            refs = _export['references']['items']
            latest = [self.latest_version(source['source_id']) for source in sources]
            runs = _export['runs']
        source_refs = [ref for ref in refs if ref['category'] == 'source_record']
        valid = sum(ref['validation']['location_status'] == 'valid' for ref in source_refs)
        missing = sum(version is None or version['status'] != 'saved' for version in latest)
        from .quality_evaluation import QualityEvaluation
        observed = QualityEvaluation.evaluate(runs)
        return {'calculation_version': 'evidence-quality-v1',
                'source_preservation': {'numerator': len(sources)-missing, 'denominator': len(sources),
                                        'value': (len(sources)-missing)/len(sources) if sources else None,
                                        'definition': '已保存文字的來源數／全部來源；不代表內容正確。'},
                'citation_location': {'numerator': valid, 'denominator': len(source_refs),
                                      'value': valid/len(source_refs) if source_refs else None,
                                      'definition': '目標、版本及引句定位有效的引用／來源引用；未判斷語意支持。'},
                'assumptions': [ref for ref in refs if ref['category'] == 'user_assumption'],
                'contradictions': [ref for ref in refs if ref['relation'] == 'contradicts'],
                'run_counts': {'total': len(runs), 'completed': sum(run['status'] == 'completed' for run in runs),
                               'incomplete': sum(run['status'] != 'completed' for run in runs)},
                'repeat_stability': observed['repeat_stability'],
                'model_sensitivity': observed['model_sensitivity'],
                'real_world_validation': {'status': 'not_evaluated'},
                'limitations': ['探索性情境，並非未來預測。', '定位有效不代表論點已獲證實。',
                                '重複執行與不同模型的評估須有可比較樣本及另行授權。']}

    def tasks(self):
        return {'items': TaskManager().list_tasks()[:100],
                'runs': [{k: v for k, v in public_manifest(RunStore.get(row['simulation_id'], reconcile=True)).items()
                          if k not in {'owner', 'worker_id'}} for row in RunStore.list(limit=100)]}

    def plans(self, project_id, kind=None, definition=None):
        self.project(project_id)
        if definition is not None:
            if kind not in {'source_update', 'sensitivity'} or not isinstance(definition, dict):
                raise EvidenceError('不支援此實驗／更新計畫。')
            if definition.get('enabled') is not False:
                raise EvidenceError('目前只能保存停用計畫，啟用需要獨立授權。')
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            definition = dict(definition)
            if set(definition) - {'enabled', 'frequency', 'timezone', 'scope', 'budget', 'max_attempts', 'repeat_count', 'model_profile_ids'}:
                raise EvidenceError('計畫含不支援的欄位。')
            if definition.get('frequency', 'manual') not in {'manual', 'daily', 'weekly'}:
                raise EvidenceError('請選擇手動、每日或每週頻率。')
            try:
                ZoneInfo(definition.get('timezone', 'Australia/Sydney'))
            except (ZoneInfoNotFoundError, TypeError, ValueError):
                raise EvidenceError('計畫時區無效。') from None
            if not isinstance(definition.get('scope', ''), str) or len(definition.get('scope', '')) > 2000:
                raise EvidenceError('請以最多 2000 字描述計畫範圍。')
            budget = definition.get('budget', {'max_attempts': definition.pop('max_attempts', 0)})
            if not isinstance(budget, dict) or set(budget) - {'max_attempts', 'max_model_calls'}:
                raise EvidenceError('預算欄位無效。')
            attempts = budget.get('max_attempts', 0)
            if type(attempts) is not int or not 0 <= attempts <= 3 or budget.get('max_model_calls', 0) != 0:
                raise EvidenceError('停用計畫每次最多 3 次擷取嘗試，模型呼叫預算維持 0。')
            definition['budget'] = {'max_attempts': attempts, 'max_model_calls': 0}
            repeats = definition.get('repeat_count', 1)
            profile_ids = definition.get('model_profile_ids', [])
            if type(repeats) is not int or not 1 <= repeats <= 5 or not isinstance(profile_ids, list) or len(profile_ids) > 4 or any(not isinstance(value, str) for value in profile_ids):
                raise EvidenceError('重複次數為 1–5 次，最多比較 4 組已保存連線。')
            if profile_ids:
                from ..provider_settings import profiles_config
                known = {item['id']: item for item in profiles_config()['profiles']}
                if any(value not in known for value in profile_ids):
                    raise EvidenceError('找不到選取的模型連線，請重新載入。')
                definition['model_snapshots'] = [{key: known[value].get(key) for key in ('id', 'name', 'provider', 'base_url', 'model')} for value in dict.fromkeys(profile_ids)]
            definition['source_versions'] = self.project(project_id).get('source_versions', [])
            # Definitions are never evaluated as code, timers or model calls.
            definition = public_manifest(definition)
            with database() as db:
                db.execute('INSERT INTO research_plans VALUES(?,?,?,?,?)',
                           ('plan_' + uuid.uuid4().hex, project_id, kind, json.dumps(definition, ensure_ascii=False),
                            datetime.now(timezone.utc).isoformat()))
        with database() as db:
            rows = db.execute('SELECT * FROM research_plans WHERE project_id=? ORDER BY created_at DESC', (project_id,)).fetchall()
        return {'items': [{**dict(row), 'definition': json.loads(row['definition']), 'enabled': False,
                           'next_execution': None, 'status': 'disabled_authorization_required'} for row in rows]}

    def export(self, project_id, format):
        data = self.detail(project_id)
        def all_rows(fetch):
            rows, offset = [], 0
            while True:
                page = fetch(limit=200, offset=offset)
                rows.extend(page['items'])
                if not page['has_more']:
                    return rows
                offset += len(page['items'])
        sources = self.all_sources(project_id) if data['sources']['has_more'] else data['sources']['items']
        references = (all_rows(lambda **paging: self.references(project_id, **paging))
                      if data['references']['has_more'] else data['references']['items'])
        data['sources'] = {'items': sources, 'total': len(sources), 'has_more': False, 'complete': True}
        data['references'] = {'items': references, 'total': len(references), 'has_more': False, 'complete': True}
        # Include precisely the selected project's preserved source versions.
        # Paths, provider keys, other projects and raw database files are excluded.
        data['evidence_index'] = []
        for source in sources:
            versions = all_rows(lambda **paging: self.evidence.list_versions(source['source_id'], **paging))
            for version in versions:
                version['spans'] = all_rows(lambda **paging: self.evidence.list_spans(version['version_id'], **paging))
            data['evidence_index'].append({'source': source, 'versions': versions})
        data['quality'] = self.quality(project_id, _export=data)
        data['export_version'] = 'research-export-v1'
        data['limitations'] = data['quality']['limitations']
        if format == 'json':
            return json.dumps(data, ensure_ascii=False, indent=2), 'application/json; charset=utf-8'
        label = '合成示範／Synthetic fixture' if data['project']['demo'] else '探索性研究／Exploratory research'
        lines = [f"# {data['project']['name']}", '', label, '', '## 研究問題', data['project'].get('simulation_requirement') or '',
                 '', '## 保存的報告']
        for report in data['reports']:
            lines += [f"### {report.get('report_id')} · v{report.get('version', 1)} · {report.get('status')}",
                      report.get('markdown_content') or '(尚無保存內容)']
            if not report.get('markdown_content') or report.get('status') != 'completed':
                for section in (report.get('outline') or {}).get('sections', []):
                    lines += [str(section.get('title', '')), str(section.get('content', ''))]
        lines += ['', '## 執行配置與來源版本', json.dumps(data['runs'], ensure_ascii=False, indent=2),
                  '', '## 證據索引', json.dumps(data['evidence_index'], ensure_ascii=False, indent=2),
                  '', '## 引用與假設', json.dumps(data['references']['items'], ensure_ascii=False, indent=2),
                  '', '## 限制', *data['limitations']]
        markdown = '\n\n'.join(lines)
        if format == 'md':
            return markdown, 'text/markdown; charset=utf-8'
        if format != 'html':
            raise EvidenceError('支援 HTML、Markdown 與 JSON 匯出。')
        from .report_export import render_html
        return render_html(data), 'text/html; charset=utf-8'
