"""Immutable run identities and process ownership; never stores model keys."""
import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import psutil

from ..storage import database

WORKER_ID = uuid.uuid4().hex
_WORKER = {'instance': WORKER_ID, 'host': socket.gethostname(), 'pid': os.getpid(),
           'started': psutil.Process().create_time()}
ACTIVE = {'pending', 'queued', 'starting', 'running', 'processing', 'paused', 'cancelling', 'stopping', 'finalizing'}
_PRIVATE_KEYS = re.compile(r'(api.?key|secret|password|(^|_)access_token|(^|_)refresh_token|^token$|authorization|credential|cookie|private.?key|balance_account)', re.I)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def worker_identity():
    return dict(_WORKER)


def worker_alive(owner):
    """A PID alone is never proof. Different hosts are unknown, not alive."""
    if not isinstance(owner, dict) or not all(key in owner for key in ('host', 'pid', 'started', 'instance')):
        return None
    if owner['host'] != socket.gethostname():
        return None
    try:
        process = psutil.Process(int(owner['pid']))
        return abs(process.create_time() - float(owner['started'])) < .001 and process.is_running()
    except (psutil.NoSuchProcess, ValueError, TypeError):
        return False
    except psutil.AccessDenied:
        return None


def public_manifest(value):
    """Strip credentials and host paths from structured execution metadata."""
    if isinstance(value, dict):
        return {str(key): public_manifest(item) for key, item in value.items()
                if not _PRIVATE_KEYS.search(str(key)) and str(key).lower() not in {'path', 'file_path', 'internal_path', 'content', 'raw_text'}}
    if isinstance(value, (list, tuple)):
        return [public_manifest(item) for item in value]
    if isinstance(value, str) and value.startswith(('https://', 'http://')):
        parts = urlsplit(value)
        return urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, '', ''))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class RunStore:
    @staticmethod
    def _schema(db):
        db.execute('''CREATE TABLE IF NOT EXISTS executions (
            simulation_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, attempt_id TEXT NOT NULL,
            worker_id TEXT NOT NULL, owner TEXT NOT NULL, manifest TEXT NOT NULL, status TEXT NOT NULL,
            heartbeat TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            completed_at TEXT, graph_ready INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '{}'
        )''')

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ('owner', 'manifest', 'detail'):
            result[key] = json.loads(result[key])
        result['graph_ready'] = bool(result['graph_ready'])
        return result

    @classmethod
    def claim(cls, simulation_id, manifest):
        if not isinstance(simulation_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', simulation_id):
            raise ValueError('Invalid simulation identity')
        frozen = json.dumps(public_manifest(manifest), ensure_ascii=False, sort_keys=True, allow_nan=False)
        with database() as db:
            cls._schema(db)
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM executions WHERE simulation_id=?', (simulation_id,)).fetchone()
            if existing:
                return cls._decode(existing), False
            now = utc_now()
            db.execute('''INSERT INTO executions(simulation_id,run_id,attempt_id,worker_id,owner,manifest,
                          status,heartbeat,created_at,updated_at) VALUES(?,?,?,?,?,?,'starting',?,?,?)''',
                       (simulation_id, f'run_{uuid.uuid4().hex}', f'attempt_{uuid.uuid4().hex}', WORKER_ID,
                        json.dumps(worker_identity()), frozen, now, now, now))
            return cls._decode(db.execute('SELECT * FROM executions WHERE simulation_id=?', (simulation_id,)).fetchone()), True

    @classmethod
    def get(cls, simulation_id, reconcile=False):
        with database() as db:
            cls._schema(db)
            row = cls._decode(db.execute('SELECT * FROM executions WHERE simulation_id=?', (simulation_id,)).fetchone())
            if row and reconcile and row['status'] in ACTIVE:
                alive = worker_alive(row['owner'])
                if alive is not True:
                    status = 'interrupted' if alive is False else 'needs_review'
                    db.execute('UPDATE executions SET status=?,graph_ready=0,updated_at=? WHERE simulation_id=?',
                               (status, utc_now(), simulation_id))
                    row.update(status=status, graph_ready=False)
            return row

    @classmethod
    def update(cls, simulation_id, status, **fields):
        if set(fields) & {'manifest', 'owner', 'run_id', 'attempt_id', 'worker_id', 'created_at'}:
            raise ValueError('Execution identity and manifest are immutable')
        with database() as db:
            cls._schema(db)
            db.execute('BEGIN IMMEDIATE')
            row = cls._decode(db.execute('SELECT * FROM executions WHERE simulation_id=?', (simulation_id,)).fetchone())
            if row is None:
                raise KeyError(simulation_id)
            if status in ACTIVE and row['status'] not in ACTIVE:
                raise ValueError('A terminal execution cannot be restarted')
            now = utc_now()
            ready = bool(fields.pop('graph_ready', row['graph_ready'])) and status == 'completed'
            completed_at = fields.pop('completed_at', row['completed_at'])
            if status not in ACTIVE and not completed_at:
                completed_at = now
            detail = row['detail'] | public_manifest(fields)
            db.execute('UPDATE executions SET status=?,heartbeat=?,updated_at=?,completed_at=?,graph_ready=?,detail=? WHERE simulation_id=?',
                       (status, now, now, completed_at, int(ready), json.dumps(detail, ensure_ascii=False), simulation_id))
            return cls._decode(db.execute('SELECT * FROM executions WHERE simulation_id=?', (simulation_id,)).fetchone())

    @classmethod
    def list(cls, limit=50, offset=0):
        with database() as db:
            cls._schema(db)
            return [cls._decode(row) for row in db.execute('SELECT * FROM executions ORDER BY created_at DESC LIMIT ? OFFSET ?',
                    (min(max(int(limit), 1), 100), max(int(offset), 0)))]
