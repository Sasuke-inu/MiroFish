"""Immutable source versions and evidence pointers in the shared workbench ledger.

Source text is untrusted data: this module neither renders it nor follows URLs.
Offsets count Unicode code points, with an inclusive start and exclusive end.
Location validation never establishes that a quote supports a claim.
"""

from datetime import datetime, timezone
import hashlib
import uuid


class EvidenceError(ValueError):
    """A caller supplied an invalid source, version, span, or reference."""


class EvidenceStore:
    VERSION_STATUSES = frozenset({'saved', 'missing', 'parse_failed', 'unavailable'})
    CATEGORIES = frozenset({'source_record', 'user_assumption', 'model_inference', 'simulation_event'})
    RELATIONS = frozenset({'supports', 'contradicts', 'insufficient'})

    def __init__(self, database_factory=None, clock=None):
        if database_factory is None:
            from ..storage import database
            database_factory = database
        self.database = database_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self.database() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS evidence_sources (
                    source_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL, identity TEXT NOT NULL,
                    title TEXT NOT NULL, locator TEXT, created_at TEXT NOT NULL,
                    UNIQUE(project_id, source_type, identity)
                );
                CREATE TABLE IF NOT EXISTS evidence_contents (
                    sha256 TEXT PRIMARY KEY, content TEXT NOT NULL,
                    character_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_versions (
                    version_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES evidence_sources(source_id),
                    sha256 TEXT REFERENCES evidence_contents(sha256),
                    parser_version TEXT NOT NULL, status TEXT NOT NULL,
                    fetched_at TEXT, published_at TEXT, created_at TEXT NOT NULL,
                    UNIQUE(source_id, sha256),
                    CHECK(status IN ('saved', 'missing', 'parse_failed', 'unavailable')),
                    CHECK((status = 'saved' AND sha256 IS NOT NULL) OR
                          (status != 'saved' AND sha256 IS NULL))
                );
                CREATE TABLE IF NOT EXISTS evidence_spans (
                    span_id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL REFERENCES evidence_versions(version_id),
                    start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(version_id, start, end), CHECK(start >= 0 AND end > start)
                );
                CREATE TABLE IF NOT EXISTS evidence_references (
                    reference_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    subject_type TEXT NOT NULL, subject_id TEXT NOT NULL,
                    category TEXT NOT NULL, relation TEXT NOT NULL,
                    source_id TEXT, version_id TEXT, span_id TEXT,
                    run_id TEXT, event_id TEXT, note TEXT NOT NULL,
                    legacy INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                    CHECK(category IN ('source_record', 'user_assumption',
                                       'model_inference', 'simulation_event')),
                    CHECK(relation IN ('supports', 'contradicts', 'insufficient'))
                );
                CREATE TABLE IF NOT EXISTS evidence_latest (
                    source_id TEXT PRIMARY KEY, version_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS evidence_versions_source ON evidence_versions(source_id);
                CREATE INDEX IF NOT EXISTS evidence_spans_version ON evidence_spans(version_id);
                CREATE INDEX IF NOT EXISTS evidence_references_subject
                    ON evidence_references(project_id, subject_type, subject_id);
            ''')
            # References deliberately allow absent legacy targets. New pointers
            # are checked below; old unavailable targets stay visible as gaps.
            for table in ('evidence_sources', 'evidence_contents', 'evidence_versions',
                          'evidence_spans', 'evidence_references'):
                for operation in ('UPDATE', 'DELETE'):
                    conn.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'Evidence records are immutable'); END''')
            # Conservative migration: a source without a pointer adopts its
            # newest recorded row. Sources that never had a version get none,
            # so no observation and no text is fabricated.
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''INSERT INTO evidence_latest(source_id, version_id, observed_at)
                SELECT v.source_id, v.version_id, ?
                FROM evidence_versions v
                WHERE v.rowid = (SELECT MAX(w.rowid) FROM evidence_versions w
                                 WHERE w.source_id = v.source_id)
                  AND NOT EXISTS (SELECT 1 FROM evidence_latest l WHERE l.source_id = v.source_id)''',
                (self._now(),))

    def _now(self):
        value = self.clock()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise EvidenceError('The evidence clock must include a timezone')
            return value.astimezone(timezone.utc).isoformat()
        return self._timestamp(value, 'clock', required=True)

    @staticmethod
    def _text(value, name, *, optional=False, max_length=2048):
        if optional and value is None:
            return None
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise EvidenceError(f'{name} must be a non-empty string of at most {max_length} characters')
        if any(ord(char) < 32 for char in value):
            raise EvidenceError(f'{name} must not contain control characters')
        return value

    @staticmethod
    def _timestamp(value, name, *, required=False):
        if value is None and not required:
            return None
        if not isinstance(value, str):
            raise EvidenceError(f'{name} must be an ISO timestamp with timezone')
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            raise EvidenceError(f'{name} must be an ISO timestamp with timezone') from None

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None

    @staticmethod
    def _id(prefix):
        return f'{prefix}_{uuid.uuid4().hex}'

    def create_source(self, project_id, source_type, identity, *, title='', locator=None):
        """Return a stable project-scoped source; never merge distinct identities."""
        project_id = self._text(project_id, 'project_id')
        source_type = self._text(source_type, 'source_type', max_length=64)
        identity = self._text(identity, 'identity')
        locator = self._text(locator, 'locator', optional=True, max_length=4096)
        if not isinstance(title, str) or len(title) > 1000:
            raise EvidenceError('title must be a string of at most 1000 characters')
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM evidence_sources WHERE project_id=? AND source_type=? AND identity=?',
                               (project_id, source_type, identity)).fetchone()
            if row:
                return dict(row)
            source_id = self._id('src')
            conn.execute('INSERT INTO evidence_sources VALUES (?,?,?,?,?,?,?)',
                         (source_id, project_id, source_type, identity, title, locator, self._now()))
            return dict(conn.execute('SELECT * FROM evidence_sources WHERE source_id=?', (source_id,)).fetchone())

    def add_version(self, source_id, content=None, *, parser_version, status='saved',
                    fetched_at=None, published_at=None):
        """Append a version, or reuse this source's exact saved content version.

        Repeated identical content keeps the original version metadata. Distinct
        sources may share content storage but always have their own version IDs.
        Every call also records the returned version as what was observed last,
        so restoring earlier text moves the pointer back without touching rows.
        Missing legacy content is explicit and is never represented as empty text.
        """
        parser_version = self._text(parser_version, 'parser_version', max_length=256)
        if status not in self.VERSION_STATUSES:
            raise EvidenceError('Unknown source preservation status')
        if (status == 'saved' and not isinstance(content, str)) or (status != 'saved' and content is not None):
            raise EvidenceError('Saved versions require text; unavailable versions must omit content')
        fetched_at = self._timestamp(fetched_at, 'fetched_at')
        published_at = self._timestamp(published_at, 'published_at')
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest() if content is not None else None
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT 1 FROM evidence_sources WHERE source_id=?', (source_id,)).fetchone():
                raise EvidenceError('Source does not exist')
            if digest:
                existing = conn.execute('SELECT version_id FROM evidence_versions WHERE source_id=? AND sha256=?',
                                        (source_id, digest)).fetchone()
                if existing:
                    self._point_latest(conn, source_id, existing['version_id'])
                    return self._version(conn, existing['version_id'], include_content=False)
                conn.execute('INSERT OR IGNORE INTO evidence_contents VALUES (?,?,?)',
                             (digest, content, len(content)))
            version_id = self._id('ver')
            conn.execute('INSERT INTO evidence_versions VALUES (?,?,?,?,?,?,?,?)',
                         (version_id, source_id, digest, parser_version, status,
                          fetched_at, published_at, self._now()))
            self._point_latest(conn, source_id, version_id)
            return self._version(conn, version_id, include_content=False)

    def _point_latest(self, conn, source_id, version_id):
        """Upsert the mutable observation pointer inside the caller's transaction."""
        conn.execute('''INSERT INTO evidence_latest(source_id, version_id, observed_at) VALUES (?,?,?)
            ON CONFLICT(source_id) DO UPDATE SET version_id=excluded.version_id,
                                                 observed_at=excluded.observed_at''',
                     (source_id, version_id, self._now()))

    def latest_version_id(self, source_id):
        """The version last observed for this source, not the last distinct text."""
        with self.database() as conn:
            row = conn.execute('SELECT version_id FROM evidence_latest WHERE source_id=?',
                               (source_id,)).fetchone()
        return row['version_id'] if row else None

    def latest_version(self, source_id, *, include_content=False):
        with self.database() as conn:
            row = conn.execute('SELECT version_id FROM evidence_latest WHERE source_id=?',
                               (source_id,)).fetchone()
            return self._version(conn, row['version_id'], include_content=include_content) if row else None

    @staticmethod
    def _version(conn, version_id, *, include_content):
        content = ', c.content' if include_content else ''
        row = conn.execute(f'''SELECT v.*, c.character_count{content}
            FROM evidence_versions v LEFT JOIN evidence_contents c ON c.sha256=v.sha256
            WHERE v.version_id=?''', (version_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['content_available'] = result['sha256'] is not None and result['character_count'] is not None
        result['offset_unit'] = 'unicode_codepoint'
        return result

    def get_source(self, source_id):
        with self.database() as conn:
            return self._row(conn.execute('SELECT * FROM evidence_sources WHERE source_id=?', (source_id,)).fetchone())

    def get_version(self, version_id, *, include_content=False):
        with self.database() as conn:
            return self._version(conn, version_id, include_content=include_content)

    def create_span(self, version_id, start, end, quote=None):
        """Validate an exact half-open Unicode range before saving the pointer."""
        if type(start) is not int or type(end) is not int or start < 0 or end <= start:
            raise EvidenceError('Span requires a non-empty integer range')
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            version = self._version(conn, version_id, include_content=True)
            if not version or not version['content_available']:
                raise EvidenceError('Cannot locate a span without preserved source text')
            if end > len(version['content']):
                raise EvidenceError('Span lies outside the preserved text')
            exact = version['content'][start:end]
            if quote is not None and quote != exact:
                raise EvidenceError('Quote does not match the preserved text at this range')
            existing = conn.execute('SELECT * FROM evidence_spans WHERE version_id=? AND start=? AND end=?',
                                    (version_id, start, end)).fetchone()
            if existing:
                return {**dict(existing), 'offset_unit': 'unicode_codepoint'}
            span_id = self._id('span')
            conn.execute('INSERT INTO evidence_spans VALUES (?,?,?,?,?,?)',
                         (span_id, version_id, start, end, exact, self._now()))
            return {**dict(conn.execute('SELECT * FROM evidence_spans WHERE span_id=?', (span_id,)).fetchone()),
                    'offset_unit': 'unicode_codepoint'}

    def get_span(self, span_id):
        with self.database() as conn:
            row = conn.execute('SELECT * FROM evidence_spans WHERE span_id=?', (span_id,)).fetchone()
            return {**dict(row), 'offset_unit': 'unicode_codepoint'} if row else None

    def add_reference(self, project_id, subject_type, subject_id, category, relation, *,
                      source_id=None, version_id=None, span_id=None, run_id=None,
                      event_id=None, note='', allow_missing=False, idempotency_key=None):
        """Record a declared evidence relation, never a semantic verification.

        ``allow_missing`` is for importing incomplete historical records. It
        preserves missing pointers instead of fabricating text or positions.
        Event existence is checked separately via validate_reference's resolver.
        """
        for name, value in (('project_id', project_id), ('subject_type', subject_type), ('subject_id', subject_id)):
            self._text(value, name)
        for name, value in (('source_id', source_id), ('version_id', version_id), ('span_id', span_id),
                            ('run_id', run_id), ('event_id', event_id)):
            self._text(value, name, optional=True)
        if category not in self.CATEGORIES or relation not in self.RELATIONS:
            raise EvidenceError('Unknown evidence category or relation')
        if not isinstance(note, str) or len(note) > 20000:
            raise EvidenceError('note must be a string of at most 20000 characters')
        if type(allow_missing) is not bool:
            raise EvidenceError('allow_missing must be a boolean')
        if idempotency_key is not None:
            self._text(idempotency_key, 'idempotency_key')
        if category != 'source_record' and any((source_id, version_id, span_id)):
            raise EvidenceError('Source pointers require the source_record category')
        if category != 'simulation_event' and any((run_id, event_id)):
            raise EvidenceError('Event pointers require the simulation_event category')
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if category == 'source_record':
                span = conn.execute('SELECT * FROM evidence_spans WHERE span_id=?', (span_id,)).fetchone()
                if span:
                    if version_id and version_id != span['version_id']:
                        raise EvidenceError('Span belongs to a different version')
                    version_id = span['version_id']
                version = self._version(conn, version_id, include_content=False)
                if version:
                    if source_id and source_id != version['source_id']:
                        raise EvidenceError('Version belongs to a different source')
                    source_id = version['source_id']
                source = conn.execute('SELECT * FROM evidence_sources WHERE source_id=?', (source_id,)).fetchone()
                if source and source['project_id'] != project_id:
                    raise EvidenceError('Evidence belongs to a different project')
                if not allow_missing and not (span and version and source and version['content_available']):
                    raise EvidenceError('Source references require a saved version and exact span')
            elif category == 'simulation_event' and not allow_missing and not (run_id and event_id):
                raise EvidenceError('Event references require both run_id and event_id')
            reference_id = ('ref_' + hashlib.sha256((project_id + '\0' + idempotency_key).encode()).hexdigest()
                            if idempotency_key is not None else self._id('ref'))
            fields = {'project_id': project_id, 'subject_type': subject_type, 'subject_id': subject_id,
                      'category': category, 'relation': relation, 'source_id': source_id,
                      'version_id': version_id, 'span_id': span_id, 'run_id': run_id,
                      'event_id': event_id, 'note': note, 'legacy': int(allow_missing)}
            existing = conn.execute('SELECT * FROM evidence_references WHERE reference_id=?', (reference_id,)).fetchone()
            if existing:
                if any(existing[key] != value for key, value in fields.items()):
                    raise EvidenceError('Idempotency key already belongs to a different reference')
                return dict(existing)
            conn.execute('INSERT INTO evidence_references VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (reference_id, project_id, subject_type, subject_id, category, relation,
                          source_id, version_id, span_id, run_id, event_id, note, int(allow_missing), self._now()))
            return dict(conn.execute('SELECT * FROM evidence_references WHERE reference_id=?', (reference_id,)).fetchone())

    def get_reference(self, reference_id):
        with self.database() as conn:
            return self._row(conn.execute('SELECT * FROM evidence_references WHERE reference_id=?', (reference_id,)).fetchone())

    def validate_reference(self, reference_id, *, event_resolver=None):
        """Only check location integrity; semantic support is always unevaluated.

        An event resolver accepts (run_id, event_id), returning the event mapping
        or None. It must read persisted events only, without running a model.
        """
        result = {'reference_id': reference_id, 'semantic_support': 'not_evaluated'}
        def outcome(status, reason):
            return {**result, 'location_status': status, 'location_reason': reason}
        with self.database() as conn:
            ref = conn.execute('SELECT * FROM evidence_references WHERE reference_id=?', (reference_id,)).fetchone()
            if not ref:
                return outcome('missing', 'reference_missing')
            if ref['category'] in {'user_assumption', 'model_inference'}:
                return outcome('not_applicable', 'declared_non_source_statement')
            if ref['category'] == 'source_record':
                source = conn.execute('SELECT * FROM evidence_sources WHERE source_id=?', (ref['source_id'],)).fetchone()
                if not source:
                    return outcome('missing', 'source_missing')
                if source['project_id'] != ref['project_id']:
                    return outcome('invalid', 'project_mismatch')
                version = self._version(conn, ref['version_id'], include_content=True)
                if not version:
                    return outcome('missing', 'version_missing')
                if version['source_id'] != source['source_id']:
                    return outcome('invalid', 'source_version_mismatch')
                if not version['content_available']:
                    return outcome('missing', 'content_missing')
                span = conn.execute('SELECT * FROM evidence_spans WHERE span_id=?', (ref['span_id'],)).fetchone()
                if not span:
                    return outcome('missing', 'span_missing')
                if span['version_id'] != version['version_id']:
                    return outcome('invalid', 'span_version_mismatch')
                if not (0 <= span['start'] < span['end'] <= len(version['content'])):
                    return outcome('invalid', 'range_outside_content')
                if version['content'][span['start']:span['end']] != span['quote']:
                    return outcome('invalid', 'quote_mismatch')
                return outcome('valid', 'quote_match')
        if not ref['run_id'] or not ref['event_id']:
            return outcome('missing', 'event_locator_missing')
        if event_resolver is None:
            return outcome('unverified', 'event_resolver_required')
        event = event_resolver(ref['run_id'], ref['event_id'])
        if event is None:
            return outcome('missing', 'event_missing')
        if (not isinstance(event, dict) or event.get('event_id') != ref['event_id']
                or event.get('run_id') != ref['run_id'] or event.get('project_id') != ref['project_id']):
            return outcome('invalid', 'event_identity_mismatch')
        return outcome('valid', 'event_exists')

    def _list(self, table, filters, *, limit, offset):
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise EvidenceError('Pagination requires limit 1..200 and a non-negative offset')
        where = ' AND '.join(f'{name}=?' for name in filters) or '1=1'
        parameters = tuple(filters.values())
        with self.database() as conn:
            total = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {where}', parameters).fetchone()[0]
            order = 'DESC' if table == 'evidence_versions' else 'ASC'
            columns = '*'
            if table == 'evidence_versions':
                columns += ', (SELECT character_count FROM evidence_contents WHERE sha256=evidence_versions.sha256) AS character_count'
            rows = conn.execute(f'SELECT {columns} FROM {table} WHERE {where} ORDER BY rowid {order} LIMIT ? OFFSET ?',
                                (*parameters, limit, offset)).fetchall()
        return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit,
                'offset': offset, 'has_more': offset + len(rows) < total}

    def list_sources(self, project_id, *, limit=50, offset=0):
        return self._list('evidence_sources', {'project_id': project_id}, limit=limit, offset=offset)

    def list_versions(self, source_id, *, limit=50, offset=0):
        return self._list('evidence_versions', {'source_id': source_id}, limit=limit, offset=offset)

    def list_spans(self, version_id, *, limit=50, offset=0):
        return self._list('evidence_spans', {'version_id': version_id}, limit=limit, offset=offset)

    def list_references(self, project_id, *, subject_type=None, subject_id=None, limit=50, offset=0):
        filters = {'project_id': project_id}
        if subject_type is not None:
            filters['subject_type'] = subject_type
        if subject_id is not None:
            filters['subject_id'] = subject_id
        return self._list('evidence_references', filters, limit=limit, offset=offset)
