"""R12 follow-up: a duplicate claim joins the still-running claim instead of allocating a new version.

The audit requires two simultaneous requests to claim ONE new piece of work;
per-process locks cannot cover concurrent processes, so the ledger itself must
reuse an active claim before handing out the next version.
"""
import json

import pytest

from app.models.task import TaskManager
from app.storage import database


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))


def test_duplicate_claims_join_the_active_claim():
    manager = TaskManager()
    first = manager.claim_report_version('sim_join', {'report_id': 'report_one'})
    second = manager.claim_report_version('sim_join', {'report_id': 'report_two'})

    assert second[0] == first[0] and second[2] == first[2]
    assert second[1] is False


def test_new_version_only_after_the_claim_is_terminal():
    manager = TaskManager()
    task_id, created, version = manager.claim_report_version('sim_next', {'report_id': 'r1'})
    assert created is True and version == 1
    manager.complete_task(task_id, {'report_id': 'r1'})

    again = manager.claim_report_version('sim_next', {'report_id': 'r2'})

    assert again[1] is True and again[2] == 2
    assert again[0] != task_id


def test_dead_owner_claim_is_not_joined():
    manager = TaskManager()
    task_id, created, version = manager.claim_report_version('sim_dead', {'report_id': 'r1'})
    assert created is True and version == 1
    with database() as db:
        db.execute('UPDATE tasks SET owner=? WHERE task_id=?',
                   (json.dumps({'instance': 'other', 'host': 'not-this-host', 'pid': 1, 'started': 0}), task_id))

    again = manager.claim_report_version('sim_dead', {'report_id': 'r2'})

    assert again[1] is True and again[2] == 2
