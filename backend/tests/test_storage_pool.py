from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from app.storage import database, database_path


@pytest.fixture(autouse=True)
def temporary_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path/'ledger.sqlite3'))


def test_exclusive_reuse_keeps_transactions_and_foreign_keys():
    with database() as first:
        first.execute('CREATE TABLE items(id INTEGER PRIMARY KEY)')
        first.execute('INSERT INTO items VALUES(1)')
    with pytest.raises(RuntimeError):
        with database() as second:
            assert first is second
            second.execute('INSERT INTO items VALUES(2)')
            raise RuntimeError('synthetic rollback')
    with database() as third:
        assert [row[0] for row in third.execute('SELECT id FROM items')] == [1]
        assert third.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert third.execute('PRAGMA synchronous').fetchone()[0] == 2


def test_concurrent_leases_never_share_connection_or_lose_updates():
    with database() as conn:
        conn.execute('CREATE TABLE counts(id INTEGER PRIMARY KEY)')
    def insert(value):
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO counts VALUES(?)', (value,))
    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(insert, range(48)))
    with database() as conn:
        assert conn.execute('SELECT COUNT(*) FROM counts').fetchone()[0] == 48


def test_replaced_file_does_not_read_stale_connection():
    with database() as conn:
        conn.execute('CREATE TABLE obsolete(id)')
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    path = database_path()
    replacement = path.with_suffix('.replacement')
    with sqlite3.connect(replacement) as fresh:
        fresh.execute('CREATE TABLE replacement(id)')
    # This isolated Linux filesystem replacement simulates an offline restore.
    path.unlink()
    for suffix in ('-wal', '-shm'):
        path.with_name(path.name+suffix).unlink(missing_ok=True)
    replacement.rename(path)
    with database() as restored:
        assert restored.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0] == 'replacement'
