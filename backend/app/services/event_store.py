"""Append-only views of recorded events, never an OASIS world-state restore.

Sequence numbers describe durable observation order across the input logs.
Original JSONL files are read only. A changed consumed prefix is quarantined.
"""
import base64
import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict, deque
from pathlib import Path

from ..config import Config
from ..models.execution import RunStore, utc_now
from ..storage import database

_PRIVATE = re.compile(r'api.?key|secret|password|access_token|refresh_token|^token$|authorization|credential|cookie|private.?key', re.I)
_BASE_LIMITS = [
    '這是已記錄事件的投影，不能還原 OASIS 的完整環境、隨機狀態或未記錄行為。',
    '序號代表保存時的觀察順序；跨平台事件沒有可證明的共同先後順序。',
]
_WARNINGS = {
    'identity': '部分紀錄的執行身分不符，已排除，不能視為完整事件投影。',
    'legacy': '舊紀錄缺少可驗證的執行身分，只提供事件清單。',
    'malformed': '來源含無法解析的完整紀錄，已保留其缺口。',
    'changed': '來源已保存的內容發生變更或截短，保留既有事件並停止讀入該來源。',
    'missing': '先前讀取的來源目前不可用，已保存事件仍保留。',
    'partial': '來源尾端尚有未完成的一行，暫不納入事件。',
}


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise ValueError('模擬或事件識別碼無效。')
    return value


def _clean(value):
    # Unlike execution metadata, event content is intentionally preserved.
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items() if not _PRIVATE.search(str(key))}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ValueError('事件內容必須是 JSON 資料。')


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


class EventStore:
    @staticmethod
    def _schema(db):
        db.execute('''CREATE TABLE IF NOT EXISTS workbench_events (
            simulation_id TEXT NOT NULL, event_id TEXT NOT NULL, seq INTEGER NOT NULL,
            run_id TEXT, attempt_id TEXT, platform TEXT NOT NULL, agent_id TEXT,
            payload TEXT NOT NULL, verified INTEGER NOT NULL,
            PRIMARY KEY(simulation_id,event_id), UNIQUE(simulation_id,seq))''')
        db.execute('''CREATE INDEX IF NOT EXISTS workbench_events_run
                      ON workbench_events(run_id,event_id)''')
        db.execute('''CREATE TABLE IF NOT EXISTS workbench_event_sources (
            simulation_id TEXT NOT NULL, source TEXT NOT NULL, consumed INTEGER NOT NULL,
            prefix_sha TEXT NOT NULL, warnings TEXT NOT NULL,
            PRIMARY KEY(simulation_id,source))''')
        for operation in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS workbench_events_no_{operation.lower()}
                BEFORE {operation} ON workbench_events
                BEGIN SELECT RAISE(ABORT, 'Saved events are immutable'); END''')

    @staticmethod
    def _directory(simulation_id):
        root = Path(Config.OASIS_SIMULATION_DATA_DIR).resolve()
        path = (root / _id(simulation_id)).resolve()
        if not path.is_relative_to(root):
            raise ValueError('模擬資料位置無效。')
        return path

    @staticmethod
    def _normalize(simulation_id, raw, run, platform=None, event_id=None, legacy=False):
        if not isinstance(raw, dict):
            raise ValueError('事件必須是 JSON 物件。')
        if run and not legacy:
            for key in ('run_id', 'attempt_id'):
                if raw.get(key) is not None and raw[key] != run[key]:
                    raise ValueError('事件執行身分不符。')
        identifier = _id(event_id or raw.get('event_id') or 'event_' + uuid.uuid4().hex)
        agent = raw.get('agent_id')
        if agent is not None and (isinstance(agent, (bool, dict, list)) or len(str(agent)) > 200):
            raise ValueError('角色識別碼無效。')
        kind = raw.get('kind') or raw.get('action_type') or raw.get('event_type') or 'unknown'
        if not isinstance(kind, str) or len(kind) > 200:
            raise ValueError('事件類別無效。')
        recorded_platform = platform or raw.get('platform') or 'unknown'
        if not isinstance(recorded_platform, str) or len(recorded_platform) > 100:
            raise ValueError('事件平台無效。')
        content = raw['content'] if 'content' in raw else {
            key: value for key, value in raw.items()
            if key not in {'event_id', 'seq', 'run_id', 'attempt_id', 'observed_at', 'timestamp', 'platform'}
        }
        return {'event_id': identifier, 'simulation_id': simulation_id,
                'project_id': run['manifest'].get('project_id') if run else None,
                'run_id': None if legacy else run['run_id'],
                'attempt_id': None if legacy else run['attempt_id'],
                'platform': recorded_platform, 'agent_id': None if agent is None else str(agent),
                'round': raw.get('round'),
                'simulation_time': raw.get('simulation_time', raw.get('simulated_hour')),
                'observed_at': raw.get('observed_at') or utc_now(),
                'recorded_at': raw.get('timestamp'),
                'kind': kind, 'content': _clean(content)}

    @classmethod
    def _insert(cls, db, event, verified, explicit_timestamp=False):
        old = db.execute('SELECT payload FROM workbench_events WHERE simulation_id=? AND event_id=?',
                         (event['simulation_id'], event['event_id'])).fetchone()
        if old:
            previous = json.loads(old['payload'])
            # Ingestion time is generated once, not a change to event identity.
            exclude = {'seq'} if explicit_timestamp else {'seq', 'observed_at'}
            if {k: v for k, v in previous.items() if k not in exclude} != {k: v for k, v in event.items() if k not in exclude}:
                raise ValueError('相同事件識別碼已有不同內容，禁止覆寫。')
            return previous, False
        seq = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM workbench_events WHERE simulation_id=?',
                         (event['simulation_id'],)).fetchone()[0]
        event = {**event, 'seq': seq}
        db.execute('INSERT INTO workbench_events VALUES(?,?,?,?,?,?,?,?,?)',
                   (event['simulation_id'], event['event_id'], seq, event['run_id'], event['attempt_id'],
                    event['platform'], event['agent_id'], _dump(event), int(verified)))
        return event, True

    @classmethod
    def append(cls, simulation_id, event):
        """Persist a supplied fixture/event through the same immutable ledger."""
        _id(simulation_id)
        run = RunStore.get(simulation_id)
        if run is None:
            raise ValueError('請先保存執行身分，再加入事件。')
        normalized = cls._normalize(simulation_id, event, run)
        with database() as db:
            cls._schema(db)
            db.execute('BEGIN IMMEDIATE')
            return cls._insert(db, normalized, True, bool(event.get('observed_at')))[0]

    @classmethod
    def ingest(cls, simulation_id):
        folder = cls._directory(simulation_id)
        run = RunStore.get(simulation_id, reconcile=True)
        if run is None and not folder.is_dir():
            raise ValueError('找不到模擬紀錄。')
        ingested = 0
        with database() as db:
            cls._schema(db)
            db.execute('BEGIN IMMEDIATE')
            for source, platform in [('twitter/actions.jsonl', 'twitter'), ('reddit/actions.jsonl', 'reddit'), ('actions.jsonl', None)]:
                path = folder / source
                checkpoint = db.execute('SELECT * FROM workbench_event_sources WHERE simulation_id=? AND source=?',
                                        (simulation_id, source)).fetchone()
                warnings = set(json.loads(checkpoint['warnings'])) if checkpoint else set()
                consumed = checkpoint['consumed'] if checkpoint else 0
                prefix_sha = checkpoint['prefix_sha'] if checkpoint else hashlib.sha256(b'').hexdigest()
                warnings.discard('partial')
                if not path.is_file() or not path.resolve().is_relative_to(folder):
                    if not checkpoint:
                        continue
                    warnings.add('missing')
                elif 'changed' not in warnings:
                    warnings.discard('missing')
                    with path.open('rb') as handle:
                        digest = hashlib.sha256()
                        remaining = consumed
                        while remaining:
                            chunk = handle.read(min(remaining, 1024 * 1024))
                            if not chunk:
                                break
                            digest.update(chunk)
                            remaining -= len(chunk)
                        if remaining or digest.hexdigest() != prefix_sha:
                            warnings.add('changed')
                        else:
                            while True:
                                offset = handle.tell()
                                raw_line = handle.readline()
                                if not raw_line:
                                    break
                                if not raw_line.endswith(b'\n'):
                                    warnings.add('partial')
                                    break
                                digest.update(raw_line)
                                consumed = handle.tell()
                                prefix_sha = digest.hexdigest()
                                if not raw_line.strip():
                                    continue
                                try:
                                    raw = json.loads(raw_line)
                                    if not isinstance(raw, dict):
                                        raise ValueError('Expected object')
                                    tagged = bool(raw.get('run_id') and raw.get('attempt_id'))
                                    if tagged and (not run or raw['run_id'] != run['run_id'] or raw['attempt_id'] != run['attempt_id']):
                                        warnings.add('identity')
                                        continue
                                    if not tagged:
                                        warnings.add('legacy')
                                    identity = hashlib.sha256(f'{simulation_id}/{source}/{offset}/'.encode() + raw_line).hexdigest()
                                    event = cls._normalize(simulation_id, raw, run, platform,
                                                           'event_' + identity, legacy=not tagged)
                                    _, created = cls._insert(db, event, bool(run and tagged))
                                    ingested += int(created)
                                except (ValueError, TypeError, UnicodeDecodeError):
                                    warnings.add('malformed')
                db.execute('''INSERT INTO workbench_event_sources VALUES(?,?,?,?,?)
                    ON CONFLICT(simulation_id,source) DO UPDATE SET consumed=excluded.consumed,
                    prefix_sha=excluded.prefix_sha,warnings=excluded.warnings''',
                           (simulation_id, source, consumed, prefix_sha, _dump(sorted(warnings))))
            total = db.execute('SELECT COUNT(*) FROM workbench_events WHERE simulation_id=?', (simulation_id,)).fetchone()[0]
            info = cls._info(db, simulation_id, run)
        return {'ingested': ingested, 'total': total, **info}

    @classmethod
    def _info(cls, db, simulation_id, run):
        warnings = set()
        for row in db.execute('SELECT warnings FROM workbench_event_sources WHERE simulation_id=?', (simulation_id,)):
            warnings.update(json.loads(row['warnings']))
        unverified = db.execute('SELECT 1 FROM workbench_events WHERE simulation_id=? AND verified=0 LIMIT 1',
                                (simulation_id,)).fetchone()
        if run is None or unverified:
            warnings.add('legacy')
        limitations = [*_BASE_LIMITS, *(_WARNINGS[key] for key in sorted(warnings))]
        if run and run['status'] in {'stopped', 'failed', 'interrupted', 'needs_review'}:
            limitations.append('執行未完整完成，尾段可能缺失；沒有紀錄不表示事件未曾發生。')
        return {'capability': 'event_list' if warnings else 'exact_event_projection',
                'limitations': limitations, 'cost': {'status': 'unknown', 'value': None, 'currency': None}}

    @classmethod
    def page(cls, simulation_id, cursor=None, limit=100, platform=None, agent_id=None):
        info = cls.ingest(simulation_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError('每頁筆數須介於 1 到 200。')
        agent_id = None if agent_id is None else str(agent_id)
        scope = {'simulation_id': simulation_id, 'platform': platform, 'agent_id': agent_id}
        after = 0
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode() + b'=' * (-len(cursor) % 4)))
                if decoded.get('v') != 1 or decoded.get('scope') != scope or type(decoded.get('after')) is not int or decoded['after'] < 0:
                    raise ValueError()
                after = decoded['after']
            except (ValueError, TypeError, AttributeError, UnicodeError):
                raise ValueError('事件分頁位置無效，或篩選條件已改變。') from None
        where, args = ['simulation_id=?', 'seq>?'], [simulation_id, after]
        for field, value in [('platform', platform), ('agent_id', agent_id)]:
            if value is not None:
                where.append(field + '=?')
                args.append(value)
        with database() as db:
            rows = db.execute('SELECT payload FROM workbench_events WHERE ' + ' AND '.join(where) + ' ORDER BY seq LIMIT ?',
                              (*args, limit + 1)).fetchall()
        items = [json.loads(row['payload']) for row in rows[:limit]]
        position = items[-1]['seq'] if items else after
        next_cursor = base64.urlsafe_b64encode(_dump({'v': 1, 'scope': scope, 'after': position}).encode()).decode().rstrip('=')
        return {'items': items, 'next_cursor': next_cursor, 'has_more': len(rows) > limit,
                **{key: info[key] for key in ('capability', 'limitations', 'cost')}}

    @classmethod
    def get_event(cls, run_id, event_id):
        """Resolve a saved evidence pointer without ingesting or running work."""
        with database() as db:
            cls._schema(db)
            row = db.execute('SELECT payload FROM workbench_events WHERE run_id=? AND event_id=?', (run_id, event_id)).fetchone()
            return json.loads(row['payload']) if row else None

    @classmethod
    def _iter_events(cls, simulation_id, through_seq):
        with database() as db:
            for row in db.execute('SELECT payload FROM workbench_events WHERE simulation_id=? AND seq<=? ORDER BY seq',
                                  (simulation_id, through_seq)):
                yield json.loads(row['payload'])

    @classmethod
    def project(cls, simulation_id, through_seq):
        if type(through_seq) is not int or through_seq < 0:
            raise ValueError('回看序號必須是非負整數。')
        info = cls.ingest(simulation_id)
        events = deque(maxlen=200)
        event_count = 0
        actors, relationships = {}, {}
        for event in cls._iter_events(simulation_id, through_seq):
            event_count += 1
            events.append(event)
            if event['agent_id'] is None:
                continue
            key = (event['platform'], event['agent_id'])
            actor = actors.setdefault(key, {'platform': key[0], 'agent_id': key[1], 'actions_count': 0,
                                            'kind_counts': {}, 'last_event_seq': 0})
            actor['actions_count'] += 1
            actor['kind_counts'][event['kind']] = actor['kind_counts'].get(event['kind'], 0) + 1
            actor['last_event_seq'] = event['seq']
            content = event['content'] if isinstance(event['content'], dict) else {}
            args = content.get('action_args', content)
            if not isinstance(args, dict) or content.get('success') is False:
                continue
            target = next((args[key] for key in ('followee_id', 'target_agent_id') if args.get(key) is not None), None)
            if target is None or isinstance(target, (dict, list, bool)):
                continue
            relation_key = (*key, str(target))
            if event['kind'].upper() == 'FOLLOW':
                relationships[relation_key] = {'platform': key[0], 'source_agent_id': key[1],
                    'target_agent_id': str(target), 'kind': 'FOLLOW', 'event_id': event['event_id'], 'seq': event['seq']}
            elif event['kind'].upper() == 'UNFOLLOW':
                relationships.pop(relation_key, None)
        run = RunStore.get(simulation_id)
        return {'simulation_id': simulation_id, 'run_id': run['run_id'] if run else None, 'through_seq': through_seq,
                'events': list(events), 'event_count': event_count, 'events_truncated': event_count > 200,
                'actors': list(actors.values()), 'relationships': list(relationships.values()),
                **{key: info[key] for key in ('capability', 'limitations', 'cost')}}

    @staticmethod
    def _diff(left, right, prefix=''):
        result = []
        for key in sorted(set(left) | set(right)):
            path = f'{prefix}.{key}' if prefix else key
            if key in left and key in right and isinstance(left[key], dict) and isinstance(right[key], dict):
                result.extend(EventStore._diff(left[key], right[key], path))
            elif key not in left or key not in right or left[key] != right[key]:
                result.append({'path': path, 'left': left.get(key), 'right': right.get(key),
                               'left_present': key in left, 'right_present': key in right})
        return result

    @classmethod
    def _report_comparison(cls, left, right):
        """Compare saved text and declared evidence; never evaluate semantics."""
        from .report_agent import ReportManager
        from .research_workbench import ResearchWorkbench
        from .evidence_store import EvidenceStore
        evidence = EvidenceStore()
        reports, references = [], []
        for run in (left, right):
            project_id = run['manifest'].get('project_id')
            side = {'reports': [], 'selected_report_id': None, 'summary': None,
                    'sections': [], 'markdown_content': None, 'excluded': []}
            eligible = []
            # Missing project context cannot establish an evidence scope.
            saved = ReportManager.list_reports(run['simulation_id'], limit=None) if project_id else []
            for report in saved:
                manifest = report.manifest or {}
                report_project = manifest.get('project_id') or (manifest.get('execution') or {}).get('project_id')
                if report_project and report_project != project_id:
                    continue
                if report.run_id != run['run_id']:
                    side['excluded'].append({'report_id': report.report_id, 'reason': 'run_identity_unverified'})
                    continue
                public = ResearchWorkbench._public_report(report)
                side['reports'].append({key: public[key] for key in
                    ('report_id', 'version', 'status', 'created_at', 'completed_at', 'run_id')})
                if public['status'] == 'completed':
                    eligible.append(public)
                else:
                    side['excluded'].append({'report_id': report.report_id, 'reason': 'report_incomplete'})
            selected = max(eligible, key=lambda item: (item['created_at'], item['version'], item['report_id'])) if eligible else None
            refs = []
            if selected:
                outline = selected.get('outline') or {}
                side.update(selected_report_id=selected['report_id'],
                            summary=outline.get('summary') or selected['markdown_content'],
                            markdown_content=selected['markdown_content'])
                side['sections'] = [{'section_id': f"{selected['report_id']}:section:{index + 1}",
                                     'title': section.get('title', ''), 'content': section.get('content', '')}
                                    for index, section in enumerate(outline.get('sections') or [])]
                subjects = {('report', selected['report_id']),
                            *(('report_section', item['section_id']) for item in side['sections'])}
                offset = 0
                while True:
                    page = evidence.list_references(project_id, limit=200, offset=offset)
                    for ref in page['items']:
                        if (ref['subject_type'], ref['subject_id']) in subjects:
                            refs.append({**ref, 'validation': evidence.validate_reference(
                                ref['reference_id'], event_resolver=cls.get_event)})
                    if not page['has_more']:
                        break
                    offset += 200
            counts = {key: 0 for key in ('supports', 'contradicts', 'insufficient', 'missing', 'invalid')}
            for ref in refs:
                counts[ref['relation']] += 1
                location = ref['validation']['location_status']
                if location in ('missing', 'invalid'):
                    counts[location] += 1
            reports.append(side)
            references.append({'report_id': side['selected_report_id'], 'references': refs, 'counts': counts})
        available = all(side['selected_report_id'] for side in reports)
        sections = []
        if available:
            for index in range(max(len(side['sections']) for side in reports)):
                pair = [side['sections'][index] if index < len(side['sections']) else None for side in reports]
                normalized = [{key: item[key] for key in ('title', 'content')} if item else None for item in pair]
                sections.append({'index': index + 1, 'left': pair[0], 'right': pair[1], 'changed': normalized[0] != normalized[1]})
        def identity(ref):
            target = 'report' if ref['subject_type'] == 'report' else ref['subject_id'].rsplit(':section:', 1)[-1]
            return _dump({'subject': target, **{key: ref.get(key) for key in
                ('category', 'relation', 'source_id', 'version_id', 'span_id', 'run_id', 'event_id', 'note')},
                'location_status': ref['validation']['location_status']})
        # Counter subtraction preserves duplicate declarations instead of hiding
        # differences with set arithmetic. Instance-specific report IDs are ignored.
        def unmatched(source, other):
            remaining = Counter(identity(ref) for ref in other)
            result = []
            for ref in source:
                key = identity(ref)
                if remaining[key]:
                    remaining[key] -= 1
                else:
                    result.append(ref)
            return result
        status = 'compared' if available else 'unavailable'
        limits = ['只比較已保存文字與宣告的引用關係，未評審語意或預測準確性。',
                  '章節按保存順序對照；摘要缺失時呈現完整保存正文。']
        return {
            'report_diff': {'status': status, 'left': reports[0], 'right': reports[1], 'sections': sections,
                'summary_changed': reports[0]['summary'] != reports[1]['summary'] if available else None,
                'markdown_changed': reports[0]['markdown_content'] != reports[1]['markdown_content'] if available else None,
                'semantic_evaluation': 'not_evaluated', 'limitations': limits},
            'evidence_diff': {'status': status, 'left': references[0], 'right': references[1],
                'delta': {key: references[1]['counts'][key] - references[0]['counts'][key]
                          for key in references[0]['counts']} if available else None,
                'added': unmatched(references[1]['references'], references[0]['references']) if available else [],
                'removed': unmatched(references[0]['references'], references[1]['references']) if available else [],
                'semantic_evaluation': 'not_evaluated',
                'limitations': ['支持、相反與不足是保存時宣告的關係；missing/invalid僅檢查引用定位。',
                                '只計入所選報告及其實際章節的引用；同一原文在不同章節的引用分別計數。']}}

    @classmethod
    def compare(cls, left_sim, right_sim):
        left, right = RunStore.get(_id(left_sim), reconcile=True), RunStore.get(_id(right_sim), reconcile=True)
        if not left or not right or left['status'] != 'completed' or right['status'] != 'completed':
            raise ValueError('只可比較兩個已完整完成的執行；中止或未確認的紀錄不能當作完成結果。')
        infos = [cls.ingest(left_sim), cls.ingest(right_sim)]
        with database() as db:
            sides = [[json.loads(row['payload']) for row in db.execute(
                'SELECT payload FROM workbench_events WHERE simulation_id=? ORDER BY seq', (sim,))]
                for sim in (left_sim, right_sim)]
        counts = []
        for events in sides:
            result = defaultdict(Counter)
            for event in events:
                result[event['platform']][event['kind']] += 1
            counts.append({platform: dict(kinds) for platform, kinds in result.items()})
        ignored = {'seq', 'event_id', 'simulation_id', 'project_id', 'run_id', 'attempt_id', 'observed_at', 'recorded_at'}
        first = None
        for index in range(max(map(len, sides))):
            pair = [events[index] if index < len(events) else None for events in sides]
            comparable = [{key: value for key, value in item.items() if key not in ignored} if item else None for item in pair]
            if comparable[0] != comparable[1]:
                first = {'index': index + 1, 'left': pair[0], 'right': pair[1]}
                break
        difference = cls._diff(left['manifest'], right['manifest'])
        bookkeeping = {'run_id', 'attempt_id', 'simulation_id', 'graph_id', 'created_at', 'captured_at', 'config_sha256'}
        meaningful = [item for item in difference if item['path'].split('.')[0] not in bookkeeping]
        # Only one explicit scenario parameter with identical known source/model
        # metadata is a single changed variable. This still does not prove cause.
        context_known = all(run['manifest'].get('model') and run['manifest'].get('source_versions')
                            and run['manifest'].get('source_lineage_status') != 'unverified'
                            for run in (left, right))
        single = context_known and len(meaningful) == 1 and meaningful[0]['path'].startswith('scenario.')
        limitations = list(dict.fromkeys([*infos[0]['limitations'], *infos[1]['limitations'],
            '比較呈現已保存事件的差異，不能證明因果；未記錄的隨機狀態與外部影響仍可能不同。']))
        if not context_known:
            limitations.append('缺少可驗證的模型或來源版本沿革，不能認定只有一個變項不同。')
        return {'left_simulation_id': left_sim, 'right_simulation_id': right_sim,
                'left_run_id': left['run_id'], 'right_run_id': right['run_id'],
                'manifest_diff': difference, 'kind_counts': {'left': counts[0], 'right': counts[1]},
                'first_difference': first, 'non_single_variable': not single, 'causal_claim': False,
                'limitations': limitations, 'cost': {'status': 'unknown', 'value': None, 'currency': None},
                **cls._report_comparison(left, right)}
