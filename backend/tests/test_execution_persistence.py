"""Execution safety contracts. Temporary data only; no provider calls."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import Config


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    from app.models.execution import RunStore
    return RunStore


def test_two_callers_claim_one_immutable_execution(store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.claim('sim_race', {'model': 'first', 'api_key': 'PRIVATE-TEST-ONLY'}), range(2)))
    assert sum(created for _, created in results) == 1
    assert len({row['run_id'] for row, _ in results}) == 1
    original = store.get('sim_race')
    row, created = store.claim('sim_race', {'model': 'different'})
    assert created is False
    assert row['manifest'] == original['manifest']
    assert 'PRIVATE-TEST-ONLY' not in json.dumps(row)
    assert 'api_key' not in row['manifest']


def test_completed_run_cannot_be_claimed_again_or_manifest_changed(store):
    first, _ = store.claim('sim_done', {'model': 'first'})
    store.update('sim_done', 'completed', graph_ready=True)
    again, created = store.claim('sim_done', {'model': 'second'})
    assert not created and again['run_id'] == first['run_id']
    assert again['status'] == 'completed'
    with pytest.raises(ValueError):
        store.update('sim_done', 'running', manifest={'model': 'second'})


def test_orphaned_owner_is_not_treated_as_running(store, monkeypatch):
    from app.models import execution
    store.claim('sim_lost', {'model': 'one'})
    monkeypatch.setattr(execution, 'worker_alive', lambda owner: False)
    row = store.get('sim_lost', reconcile=True)
    assert row['status'] == 'interrupted'
    assert row['graph_ready'] is False


def test_tasks_survive_new_manager_and_claim_is_atomic(store):
    from app.models.task import TaskManager, TaskStatus
    manager = TaskManager()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: manager.claim_task('prepare', 'prepare:sim_one', {'simulation_id': 'sim_one'}), range(2)))
    assert sum(created for _, created in results) == 1
    task_id = results[0][0]
    manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=23, message='Preparing')
    other = TaskManager()
    assert other.get_task(task_id).progress == 23
    other.complete_task(task_id, {'simulation_id': 'sim_one'})
    assert manager.get_task(task_id).status == TaskStatus.COMPLETED


def test_worker_identity_requires_start_time_not_pid_alone(store, monkeypatch):
    from app.models.execution import worker_alive, worker_identity
    owner = worker_identity()
    assert worker_alive(owner) is True
    assert worker_alive({**owner, 'started': owner['started'] - 100}) is False


def test_real_exited_worker_is_reconciled_without_restarting(store):
    import subprocess
    import sys
    process = subprocess.run([sys.executable, '-c',
        "from app.models.execution import RunStore; from app.models.task import TaskManager; "
        "RunStore.claim('sim_subprocess', {'model':'frozen', 'max_tokens':512}); "
        "TaskManager().claim_task('prepare', 'prepare:subprocess', {})"], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    row = store.get('sim_subprocess', reconcile=True)
    assert row['status'] == 'interrupted' and row['graph_ready'] is False
    assert row['manifest']['max_tokens'] == 512
    from app.models.task import TaskManager
    task = TaskManager().find_task('prepare:subprocess')
    assert task.status.value == 'interrupted'
