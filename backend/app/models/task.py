"""Durable background tasks in the existing uploads ledger.

Claims are transactionally idempotent. Reading an orphan never restarts it.
"""
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from ..storage import database
from ..utils.locale import t
from .execution import ACTIVE, public_manifest, utc_now, worker_identity, worker_alive


class TaskStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    QUEUED = 'queued'
    CANCELLING = 'cancelling'
    FINALIZING = 'finalizing'
    INTERRUPTED = 'interrupted'
    NEEDS_REVIEW = 'needs_review'


@dataclass
class Task:
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0
    message: str = ''
    result: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    progress_detail: Dict = field(default_factory=dict)
    heartbeat: Optional[str] = None
    attempt_id: Optional[str] = None
    owner: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {'task_id': self.task_id, 'task_type': self.task_type, 'status': self.status.value,
                'created_at': self.created_at.isoformat(), 'updated_at': self.updated_at.isoformat(),
                'progress': self.progress, 'message': self.message, 'progress_detail': self.progress_detail,
                'result': self.result, 'error': self.error, 'metadata': self.metadata,
                'heartbeat': self.heartbeat, 'attempt_id': self.attempt_id}


class TaskManager:
    @staticmethod
    def _schema(db):
        db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY, resource_key TEXT NOT NULL UNIQUE,
            task_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, heartbeat TEXT NOT NULL, owner TEXT NOT NULL,
            attempt_id TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '', result TEXT, error TEXT,
            metadata TEXT NOT NULL DEFAULT '{}', progress_detail TEXT NOT NULL DEFAULT '{}'
        )''')

    @staticmethod
    def _task(row):
        if row is None:
            return None
        data = dict(row)
        data.pop('resource_key')
        for key in ('owner', 'metadata', 'progress_detail', 'result'):
            data[key] = json.loads(data[key]) if data[key] is not None else None
        data['status'] = TaskStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return Task(**data)

    def claim_task(self, task_type, resource_key, metadata=None):
        with database() as db:
            self._schema(db)
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT task_id FROM tasks WHERE resource_key=?', (resource_key,)).fetchone()
            if existing:
                return existing['task_id'], False
            task_id, now = str(uuid.uuid4()), utc_now()
            db.execute('''INSERT INTO tasks(task_id,resource_key,task_type,status,created_at,updated_at,
                heartbeat,owner,attempt_id,metadata) VALUES(?,?,?,'pending',?,?,?,?,?,?)''',
                (task_id, resource_key, task_type, now, now, now, json.dumps(worker_identity()),
                 f'attempt_{uuid.uuid4().hex}', json.dumps(public_manifest(metadata or {}), ensure_ascii=False)))
            return task_id, True

    def claim_report_version(self, simulation_id: str, metadata: Optional[Dict] = None):
        """Allocate the next report version and claim its task in one transaction.

        Versions come from a persistent ledger and are never recycled by
        deleting a report. A candidate key that already exists is a duplicate
        request: that task is reused without moving the ledger further.
        """
        with database() as db:
            self._schema(db)
            db.execute('''CREATE TABLE IF NOT EXISTS report_versions (
                simulation_id TEXT PRIMARY KEY, last_version INTEGER NOT NULL)''')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT last_version FROM report_versions WHERE simulation_id=?',
                             (simulation_id,)).fetchone()
            if row is None:
                current = self._report_version_floor(db, simulation_id)
                db.execute('INSERT INTO report_versions(simulation_id,last_version) VALUES(?,?)',
                           (simulation_id, current))
            else:
                current = row['last_version']
            version = current + 1
            # 先重用仍在執行中的最新認領：跨交易的同時重複請求（含其他
            # 程序）只認領同一份新工作，帳本號碼只在沒有活動認領時前進。
            if current > 0:
                latest = db.execute('SELECT task_id, status, owner FROM tasks WHERE resource_key=?',
                                    (f'report:{simulation_id}:v{current}',)).fetchone()
                if (latest and latest['status'] in ACTIVE
                        and worker_alive(json.loads(latest['owner'])) is True):
                    return latest['task_id'], False, current
            resource_key = f'report:{simulation_id}:v{version}'
            existing = db.execute('SELECT task_id FROM tasks WHERE resource_key=?', (resource_key,)).fetchone()
            if existing:
                return existing['task_id'], False, version
            task_id, now = str(uuid.uuid4()), utc_now()
            db.execute('''INSERT INTO tasks(task_id,resource_key,task_type,status,created_at,updated_at,
                heartbeat,owner,attempt_id,metadata) VALUES(?,?,?,'pending',?,?,?,?,?,?)''',
                (task_id, resource_key, 'report_generate', now, now, now, json.dumps(worker_identity()),
                 f'attempt_{uuid.uuid4().hex}', json.dumps(public_manifest(metadata or {}), ensure_ascii=False)))
            db.execute('UPDATE report_versions SET last_version=? WHERE simulation_id=?', (version, simulation_id))
            return task_id, True, version

    def _report_version_floor(self, db, simulation_id: str) -> int:
        """First ledger value: highest saved report version or task claim, never lower."""
        from ..services.report_agent import ReportManager
        versions = [report.version or 1 for report in ReportManager.list_reports(simulation_id, limit=None)]
        prefix = f'report:{simulation_id}:v'
        claimed = [int(row['resource_key'][len(prefix):])
                   for row in db.execute('SELECT resource_key FROM tasks WHERE resource_key LIKE ?',
                                         (f'{prefix}%',))
                   if row['resource_key'][len(prefix):].isdigit()]
        return max(versions + claimed + [0])

    def create_task(self, task_type: str, metadata: Optional[Dict] = None) -> str:
        return self.claim_task(task_type, f'{task_type}:{uuid.uuid4().hex}', metadata)[0]

    def find_task(self, resource_key):
        with database() as db:
            self._schema(db)
            row = db.execute('SELECT task_id FROM tasks WHERE resource_key=?', (resource_key,)).fetchone()
        return self.get_task(row['task_id']) if row else None

    def get_task(self, task_id: str) -> Optional[Task]:
        with database() as db:
            self._schema(db)
            task = self._task(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())
            if task and task.status.value in ACTIVE:
                alive = worker_alive(task.owner)
                if alive is not True:
                    task.status = TaskStatus.INTERRUPTED if alive is False else TaskStatus.NEEDS_REVIEW
                    task.error = '原工作的執行者已中斷或無法核對；保留成果，未自動重試。'
                    task.updated_at = datetime.fromisoformat(utc_now())
                    db.execute('UPDATE tasks SET status=?,error=?,updated_at=? WHERE task_id=?',
                               (task.status.value, task.error, task.updated_at.isoformat(), task_id))
            return task

    def update_task(self, task_id, status=None, progress=None, message=None, result=None,
                    error=None, progress_detail=None):
        with database() as db:
            self._schema(db)
            db.execute('BEGIN IMMEDIATE')
            task = self._task(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())
            if task is None:
                return
            changes = {'updated_at': utc_now(), 'heartbeat': utc_now()}
            if status is not None:
                target = TaskStatus(status)
                if task.status.value not in ACTIVE and target.value in ACTIVE:
                    raise ValueError('A terminal task cannot be restarted; create an explicit new version')
                changes['status'] = target.value
            for key, value in (('progress', progress), ('message', message), ('error', error)):
                if value is not None:
                    changes[key] = value
            for key, value in (('result', result), ('progress_detail', progress_detail)):
                if value is not None:
                    changes[key] = json.dumps(public_manifest(value), ensure_ascii=False)
            db.execute(f"UPDATE tasks SET {','.join(key + '=?' for key in changes)} WHERE task_id=?",
                       (*changes.values(), task_id))

    def complete_task(self, task_id: str, result: Dict):
        self.update_task(task_id, status=TaskStatus.COMPLETED, progress=100,
                         message=t('progress.taskComplete'), result=result)

    def fail_task(self, task_id: str, error: str):
        self.update_task(task_id, status=TaskStatus.FAILED, message=t('progress.taskFailed'), error=error)

    def list_tasks(self, task_type: Optional[str] = None) -> list:
        with database() as db:
            self._schema(db)
            ids = [row['task_id'] for row in db.execute(
                'SELECT task_id FROM tasks WHERE (? IS NULL OR task_type=?) ORDER BY created_at DESC',
                (task_type, task_type))]
        return [task.to_dict() for task_id in ids if (task := self.get_task(task_id))]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        # Retention is explicit, never a consequence of reading or restarting.
        return 0

