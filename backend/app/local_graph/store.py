"""Durable graph definitions and ingestion receipts, independent of Flask."""

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class ServiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS graphs (
                    graph_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                    ontology TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY, graph_id TEXT NOT NULL REFERENCES graphs ON DELETE CASCADE,
                    metadata TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    episode_uuid TEXT PRIMARY KEY, graph_id TEXT NOT NULL REFERENCES graphs ON DELETE CASCADE,
                    batch_id TEXT REFERENCES batches ON DELETE CASCADE, sequence_index INTEGER NOT NULL,
                    data TEXT NOT NULL, data_type TEXT NOT NULL, source_description TEXT NOT NULL,
                    metadata TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
                    UNIQUE(batch_id, sequence_index)
                );
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS graph_clones (
                    operation_id TEXT PRIMARY KEY, source_graph_id TEXT NOT NULL,
                    target_graph_id TEXT NOT NULL UNIQUE REFERENCES graphs(graph_id) ON DELETE CASCADE,
                    status TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, completed_at TEXT, error TEXT
                );
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(graphs)')}
            if 'model_fingerprint' not in columns:
                db.execute('ALTER TABLE graphs ADD COLUMN model_fingerprint TEXT')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        value = dict(row)
        for key in ('metadata', 'ontology'):
            if key in value:
                value[key] = json.loads(value[key])
        return value

    def graph(self, graph_id, db=None):
        if db is None:
            with self.db() as db:
                return self.graph(graph_id, db)
        value = self.decode(db.execute('SELECT * FROM graphs WHERE graph_id=?', (graph_id,)).fetchone())
        if value is None:
            raise ServiceError('找不到這個圖譜', 404)
        return value

    def create_graph(self, graph_id, name, description=''):
        if not isinstance(graph_id, str) or not graph_id or len(graph_id) > 200:
            raise ServiceError('graph_id 必須是非空文字，最長 200 字')
        with self.db() as db:
            existing = db.execute('SELECT * FROM graphs WHERE graph_id=?', (graph_id,)).fetchone()
            if existing:
                if existing['name'] != name or existing['description'] != description:
                    raise ServiceError('圖譜識別碼已被其他資料使用', 409)
            else:
                db.execute('INSERT INTO graphs(graph_id,name,description,created_at) VALUES(?,?,?,?)',
                           (graph_id, name, description, now()))
            return self.graph(graph_id, db)

    def bind_model_fingerprint(self, graph_id, fingerprint):
        """Persist only a non-secret identity; populated legacy graphs fail closed."""
        if not isinstance(fingerprint, str) or not re.fullmatch(r'[a-f0-9]{64}', fingerprint):
            raise ServiceError('模型設定識別無效')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            graph = self.graph(graph_id, db)
            previous = graph['model_fingerprint']
            if previous is not None and previous != fingerprint:
                raise ServiceError('圖譜的模型設定與本次工作不一致，請核對後建立新執行', 409)
            if previous is None:
                if db.execute('SELECT 1 FROM jobs WHERE graph_id=? LIMIT 1', (graph_id,)).fetchone():
                    raise ServiceError('舊圖譜缺少模型設定識別；可讀取既有資料，新增寫入前需核對', 409)
                db.execute('UPDATE graphs SET model_fingerprint=? WHERE graph_id=?', (fingerprint, graph_id))
        return fingerprint

    @staticmethod
    def check_metadata(value):
        """Do not allow private transport settings to become source metadata."""
        if isinstance(value, dict):
            if any(str(key).lower() in {'model_snapshot', 'api_key', 'balance_api_key', 'authorization'} for key in value):
                raise ServiceError('附加資訊不能包含私密連線設定')
            for item in value.values():
                Store.check_metadata(item)
        elif isinstance(value, list):
            for item in value:
                Store.check_metadata(item)

    def set_ontology(self, graph_ids, ontology):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for graph_id in graph_ids:
                self.graph(graph_id, db)
                self.assert_writable(graph_id, db)
                if db.execute('SELECT 1 FROM jobs WHERE graph_id=? LIMIT 1', (graph_id,)).fetchone():
                    raise ServiceError('圖譜已有資料，請重新建立圖譜後再修改類型', 409)
            for graph_id in graph_ids:
                db.execute('UPDATE graphs SET ontology=? WHERE graph_id=?', (json.dumps(ontology), graph_id))
        return {'success': True}

    def create_batch(self, metadata):
        self.check_metadata(metadata)
        graph_id = metadata.get('graph_id')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.graph(graph_id, db)
            operation = metadata.get('mirofish_operation_id')
            if operation:
                # A lost receipt can be safely reconciled without duplicate ingestion.
                for row in db.execute('SELECT * FROM batches WHERE graph_id=?', (graph_id,)):
                    if json.loads(row['metadata']).get('mirofish_operation_id') == operation:
                        if json.loads(row['metadata']) != metadata:
                            raise ServiceError('處理識別碼的資料不一致', 409)
                        return self.batch(row['batch_id'], db)
            self.assert_writable(graph_id, db)
            batch_id = f'batch_{uuid.uuid4().hex}'
            db.execute('INSERT INTO batches VALUES(?,?,?,?,?)',
                       (batch_id, graph_id, json.dumps(metadata), 'draft', now()))
            return self.batch(batch_id, db)

    def batch(self, batch_id, db=None):
        if db is None:
            with self.db() as db:
                return self.batch(batch_id, db)
        row = self.decode(db.execute('SELECT * FROM batches WHERE batch_id=?', (batch_id,)).fetchone())
        if row is None:
            raise ServiceError('找不到這批資料', 404)
        counts = {item['status']: item['count'] for item in db.execute(
            'SELECT status,COUNT(*) AS count FROM jobs WHERE batch_id=? GROUP BY status', (batch_id,))}
        total, succeeded = sum(counts.values()), counts.get('succeeded', 0)
        row['progress'] = {'percent_complete': succeeded * 100 / total if total else 0,
                           'succeeded_items': succeeded, 'total_items': total, 'failed_items': counts.get('failed', 0)}
        return row

    @staticmethod
    def job_response(row):
        return {**row, 'uuid_': row['episode_uuid'], 'uuid': row['episode_uuid'],
                'source_uuid': row['episode_uuid'], 'processed': row['status'] == 'succeeded'}

    def add_items(self, batch_id, items):
        if not isinstance(items, list) or not 1 <= len(items) <= 350:
            raise ServiceError('每次加入的資料筆數必須介於 1 至 350')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            batch = self.batch(batch_id, db)
            if batch['status'] != 'draft':
                raise ServiceError('這批資料已開始處理，不能再加入資料', 409)
            offset = db.execute('SELECT COUNT(*) FROM jobs WHERE batch_id=?', (batch_id,)).fetchone()[0]
            if offset + len(items) > 50_000:
                raise ServiceError('一批資料最多 50,000 筆')
            results = []
            for index, item in enumerate(items, offset):
                if item.get('graph_id') != batch['graph_id'] or item.get('type') != 'graph_episode':
                    raise ServiceError('資料必須屬於這批資料的圖譜')
                results.append(self._insert_job(db, item, batch_id, index, 'draft'))
            return results

    def add_episode(self, item):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.graph(item.get('graph_id'), db)
            self.assert_writable(item.get('graph_id'), db)
            return self._insert_job(db, {**item, 'data_type': item.get('type', 'text')}, None, 0, 'queued')

    def _insert_job(self, db, item, batch_id, index, status):
        self.check_metadata(item.get('metadata') or {})
        data = item.get('data')
        if not isinstance(data, str) or not data.strip() or len(data) > 10_000:
            raise ServiceError('每筆資料必須是非空文字，最長 10,000 字')
        data_type = item.get('data_type', 'text')
        if data_type not in ('text', 'json', 'message'):
            raise ServiceError('不支援的資料格式')
        created_at = item.get('created_at') or now()
        try:
            timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                raise ValueError('timezone required')
        except (AttributeError, TypeError, ValueError):
            raise ServiceError('事件時間必須包含時區')
        episode_uuid = str(uuid.uuid4())
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (episode_uuid, item['graph_id'], batch_id, index, data, data_type,
                    item.get('source_description') or 'MiroFish episode', json.dumps(item.get('metadata') or {}),
                    created_at, status, None))
        return self.episode(episode_uuid, db)

    def process(self, batch_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            batch = self.batch(batch_id, db)
            if batch['status'] != 'draft':
                return batch
            expected = batch['metadata'].get('chunk_count')
            actual = batch['progress']['total_items']
            if not actual or (expected is not None and expected != actual):
                raise ServiceError('資料筆數不完整，尚未開始處理', 409)
            db.execute("UPDATE jobs SET status='queued' WHERE batch_id=?", (batch_id,))
            db.execute("UPDATE batches SET status='queued' WHERE batch_id=?", (batch_id,))
            return self.batch(batch_id, db)

    def episode(self, episode_uuid, db=None):
        if db is None:
            with self.db() as db:
                return self.episode(episode_uuid, db)
        row = self.decode(db.execute('SELECT * FROM jobs WHERE episode_uuid=?', (episode_uuid,)).fetchone())
        if row is None:
            raise ServiceError('找不到這筆記憶', 404)
        return self.job_response(row)

    def page(self, batch_id=None, limit=100, cursor=0):
        if not 1 <= limit <= 100 or cursor < 0:
            raise ServiceError('無效的分頁設定')
        with self.db() as db:
            if batch_id is not None:
                self.batch(batch_id, db)
                rows = db.execute('SELECT * FROM jobs WHERE batch_id=? ORDER BY sequence_index LIMIT ? OFFSET ?',
                                  (batch_id, limit + 1, cursor)).fetchall()
                values, key = [self.job_response(self.decode(row)) for row in rows[:limit]], 'items'
            else:
                rows = db.execute('SELECT * FROM batches ORDER BY created_at,batch_id LIMIT ? OFFSET ?',
                                  (limit + 1, cursor)).fetchall()
                values, key = [self.batch(row['batch_id'], db) for row in rows[:limit]], 'batches'
            return {key: values, 'next_cursor': cursor + limit if len(rows) > limit else None}

    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='processing' WHERE episode_uuid=?", (row['episode_uuid'],))
            if row['batch_id']:
                db.execute("UPDATE batches SET status='processing' WHERE batch_id=?", (row['batch_id'],))
            return self.decode(row)

    def finish(self, episode_uuid, error=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self.episode(episode_uuid, db)
            db.execute('UPDATE jobs SET status=?,error=? WHERE episode_uuid=?',
                       ('failed' if error else 'succeeded', error, episode_uuid))
            if job['batch_id']:
                counts = {row['status']: row['count'] for row in db.execute(
                    'SELECT status,COUNT(*) AS count FROM jobs WHERE batch_id=? GROUP BY status', (job['batch_id'],))}
                if counts.get('failed'):
                    # Stop the batch at its first failure, preserving sequential context.
                    db.execute("UPDATE jobs SET status='failed',error='Earlier item failed; not ingested' WHERE batch_id=? AND status='queued'",
                               (job['batch_id'],))
                    db.execute("UPDATE batches SET status='failed' WHERE batch_id=?", (job['batch_id'],))
                elif not counts.get('queued') and not counts.get('processing'):
                    db.execute("UPDATE batches SET status='succeeded' WHERE batch_id=?", (job['batch_id'],))

    def interrupted(self):
        with self.db() as db:
            return [self.decode(row) for row in db.execute("SELECT * FROM jobs WHERE status='processing'")]

    def check_delete(self, graph_id):
        with self.db() as db:
            self.graph(graph_id, db)
            if db.execute('SELECT 1 FROM graph_clones WHERE source_graph_id=? LIMIT 1', (graph_id,)).fetchone():
                raise ServiceError('來源仍被執行副本引用，請先處理相關副本後再刪除', 409)
            if db.execute("SELECT 1 FROM graph_clones WHERE target_graph_id=? AND status!='ready'", (graph_id,)).fetchone():
                raise ServiceError('圖譜複製尚未確認，請先核對結果再刪除', 409)
            if db.execute("SELECT 1 FROM jobs WHERE graph_id=? AND status IN ('queued','processing') LIMIT 1", (graph_id,)).fetchone():
                raise ServiceError('圖譜仍在處理資料，請等候完成再刪除', 409)

    def delete_graph(self, graph_id):
        with self.db() as db:
            db.execute('DELETE FROM graphs WHERE graph_id=?', (graph_id,))

    def assert_writable(self, graph_id, db):
        if db.execute('SELECT 1 FROM graph_clones WHERE source_graph_id=? LIMIT 1', (graph_id,)).fetchone():
            raise ServiceError('此圖譜已作為執行來源保存為唯讀；新內容需要建立新的來源圖譜', 409)
        target = db.execute('SELECT status FROM graph_clones WHERE target_graph_id=?', (graph_id,)).fetchone()
        if target and target['status'] != 'ready':
            raise ServiceError('獨立圖譜尚未完成複製，需先核對複製狀態', 409)

    def clone_receipt(self, operation_id, db=None):
        if db is None:
            with self.db() as db:
                return self.clone_receipt(operation_id, db)
        row = db.execute('SELECT * FROM graph_clones WHERE operation_id=?', (operation_id,)).fetchone()
        if row is None:
            raise ServiceError('找不到圖譜複製回條', 404)
        result = dict(row)
        result['summary'] = json.loads(result['summary'])
        return result

    def begin_clone(self, source_graph_id, target_graph_id, operation_id, fingerprint):
        for identity in (source_graph_id, target_graph_id, operation_id):
            if not isinstance(identity, str) or not identity or len(identity) > 200:
                raise ServiceError('圖譜複製識別無效')
        if source_graph_id == target_graph_id:
            raise ServiceError('執行圖譜必須與來源分開', 409)
        if not isinstance(fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
            raise ServiceError('模型設定識別無效')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT * FROM graph_clones WHERE operation_id=?', (operation_id,)).fetchone()
            if prior:
                if (prior['source_graph_id'] != source_graph_id or prior['target_graph_id'] != target_graph_id
                        or self.graph(target_graph_id, db)['model_fingerprint'] != fingerprint):
                    raise ServiceError('圖譜複製識別已用於不同的來源、目標或模型設定', 409)
                return self.clone_receipt(operation_id, db)
            source = self.graph(source_graph_id, db)
            if db.execute('SELECT 1 FROM graph_clones WHERE target_graph_id=?', (source_graph_id,)).fetchone():
                raise ServiceError('執行副本不能作為來源圖譜，請使用原始來源', 409)
            if db.execute('SELECT 1 FROM graphs WHERE graph_id=?', (target_graph_id,)).fetchone():
                raise ServiceError('目標圖譜識別已存在，不能覆寫', 409)
            for row in db.execute('SELECT status,metadata,source_description FROM jobs WHERE graph_id=?', (source_graph_id,)):
                if row['status'] != 'succeeded':
                    raise ServiceError('來源圖譜仍在處理或有未完成資料，不能建立執行副本', 409)
                if (json.loads(row['metadata']).get('source') == 'mirofish_simulation'
                        or row['source_description'] == 'MiroFish simulation activity batch'):
                    raise ServiceError('來源圖譜含有模擬事件，請先建立乾淨的來源圖譜', 409)
            timestamp = now()
            db.execute('INSERT INTO graphs(graph_id,name,description,ontology,created_at,model_fingerprint) VALUES(?,?,?,?,?,?)',
                       (target_graph_id, source['name'] + ' / 執行副本', source['description'],
                        json.dumps(source['ontology']), timestamp, fingerprint))
            db.execute('INSERT INTO graph_clones(operation_id,source_graph_id,target_graph_id,status,created_at) VALUES(?,?,?,?,?)',
                       (operation_id, source_graph_id, target_graph_id, 'preparing', timestamp))
            return self.clone_receipt(operation_id, db)

    def finish_clone(self, operation_id, summary):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = self.clone_receipt(operation_id, db)
            if receipt['status'] == 'ready':
                if receipt['summary'] != summary:
                    raise ServiceError('圖譜複製回條不一致，需核對', 409)
                return receipt
            db.execute("UPDATE graph_clones SET status='ready',summary=?,completed_at=?,error=NULL WHERE operation_id=?",
                       (json.dumps(summary), now(), operation_id))
            return self.clone_receipt(operation_id, db)

    def review_clone(self, operation_id):
        with self.db() as db:
            db.execute("UPDATE graph_clones SET status='needs_review',error=? WHERE operation_id=? AND status!='ready'",
                       ('複製結果尚未確認；請以相同執行識別核對，不要改寫來源', operation_id))
