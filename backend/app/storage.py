"""Small transactional ledger inside the existing private uploads volume."""
import os
import sqlite3
import threading
import time
import queue
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

_INITIALIZE = threading.Lock()
_POOLS_LOCK = threading.Lock()
_POOLS = OrderedDict()


def _close_idle(entry):
    while True:
        try:
            entry['connections'].get_nowait().close()
        except queue.Empty:
            return


def _identity(path):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (os.getpid(), stat.st_dev, stat.st_ino)


def _pool(path):
    """Connections are exclusively leased, never shared by concurrent jobs.

    Keeping idle connections avoids a WAL checkpoint on every small read on
    Docker's Windows bind mount. FULL synchronous durability is unchanged.
    An external replacement or a fork cannot reuse a stale connection.
    """
    # abspath normalizes the configured path without repeated filesystem reads.
    key = os.path.abspath(path)
    with _POOLS_LOCK:
        entry = _POOLS.get(key)
        identity = _identity(path)
        if entry and entry['identity'] != identity:
            _POOLS.pop(key)
            _close_idle(entry)
            entry = None
        if entry is None:
            entry = {'identity': identity, 'connections': queue.LifoQueue(maxsize=16)}
            _POOLS[key] = entry
        _POOLS.move_to_end(key)
        while len(_POOLS) > 8:
            _, old = _POOLS.popitem(last=False)
            _close_idle(old)
        return key, entry


def database_path():
    from .config import Config
    return Path(os.environ.get('MIROFISH_WORKBENCH_DB') or Path(Config.UPLOAD_FOLDER) / 'workbench' / 'ledger.sqlite3')


@contextmanager
def database():
    path = database_path()
    key, pool = _pool(path)
    try:
        connection = pool['connections'].get_nowait()
    except queue.Empty:
        # Only physical opens need initialization; pooled leases already retain
        # these settings. FULL synchronous durability remains SQLite's default.
        with _INITIALIZE:
            if pool['identity'] is None:
                path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA busy_timeout=30000')
            connection.execute('PRAGMA foreign_keys=ON')
            deadline = time.monotonic() + 10
            while True:
                try:
                    if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
                        connection.execute('PRAGMA journal_mode=WAL')
                    break
                except sqlite3.OperationalError as error:
                    if 'locked' not in str(error).lower() or time.monotonic() >= deadline:
                        connection.close()
                        raise
                    time.sleep(.02)
            pool['identity'] = _identity(path)
    try:
        with connection:
            yield connection
    finally:
        # with connection already committed/rolled back; no transaction is
        # carried into the next lease. Close replaced/evicted pool members.
        with _POOLS_LOCK:
            reusable = _POOLS.get(key) is pool and pool['identity'] == _identity(path)
            if reusable:
                try:
                    pool['connections'].put_nowait(connection)
                except queue.Full:
                    connection.close()
            else:
                connection.close()
