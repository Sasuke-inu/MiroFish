"""R12 follow-up: a generate request that fails during setup must not leave a zombie claim.

After the version claim succeeds, the initial save / reader registration /
thread start can still fail. If that failure leaves the claimed task pending
while no worker ever starts, later requests keep reusing the dead claim
(worker_alive is true for the live server process). Setup failures must fail
the task and release whatever was already registered.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.api import report as api
from app.config import Config
from app.models.project import ProjectStatus
from app.models.task import TaskManager, TaskStatus
from app.services.report_agent import ReportManager, ReportStatus
from app.services.simulation_runner import RunnerStatus


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'fixture-only-not-a-real-key')
    monkeypatch.setattr(api, 'SimulationManager', lambda: SimpleNamespace(get_simulation=lambda _: SimpleNamespace(
        project_id='proj_safe', graph_id='graph_run', source_graph_id='graph_safe', graph_namespace_status='ready')))
    monkeypatch.setattr(api.ProjectManager, 'get_project', lambda _: SimpleNamespace(
        status=ProjectStatus.GRAPH_COMPLETED, graph_id='graph_safe', simulation_requirement='Synthetic fixture'))
    run = SimpleNamespace(runner_status=RunnerStatus.COMPLETED, graph_ready=True, run_id='run_safe')
    monkeypatch.setattr(api.SimulationRunner, 'get_run_state', lambda _: run)
    monkeypatch.setattr(api.ZepGraphMemoryManager, 'get_updater', lambda _: None)
    started = []

    class ParkedThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(api.threading, 'Thread', ParkedThread)
    app = Flask(__name__)
    app.register_blueprint(api.report_bp, url_prefix='/api/report')
    return app.test_client(), started


def test_failed_initial_save_fails_the_claim_and_the_next_request_gets_a_new_version(environment, monkeypatch):
    client, started = environment
    real_save = ReportManager.save_report
    failures = {'count': 0}

    def flaky_save(report):
        if report.status == ReportStatus.PENDING and failures['count'] == 0:
            failures['count'] += 1
            raise OSError('disk full (fixture)')
        return real_save(report)

    monkeypatch.setattr(ReportManager, 'save_report', staticmethod(flaky_save))

    first = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})
    assert first.status_code == 500
    manager = TaskManager()
    zombie = manager.find_task('report:sim_safe:v1')
    assert zombie is not None
    # 認領後啟動失敗：工作必須是終端狀態，不得永遠 pending。
    assert zombie.status == TaskStatus.FAILED
    assert not started  # 背景工作從未啟動

    second = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})

    assert second.status_code == 200, second.json
    data = second.json['data']
    assert data['task_id'] != zombie.task_id
    assert data['report_id'] != zombie.metadata['report_id']
    assert manager.find_task('report:sim_safe:v2') is not None
    fresh = ReportManager.get_report(data['report_id'])
    assert fresh is not None and fresh.version == 2


def test_registration_failure_fails_the_claim_and_marks_the_initial_report(environment, monkeypatch):
    client, _ = environment

    def broken_register(graph_id, report_id):
        raise RuntimeError('registration down (fixture)')

    monkeypatch.setattr(api, 'register_graph_reader', broken_register)

    response = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})

    assert response.status_code == 500
    zombie = TaskManager().find_task('report:sim_safe:v1')
    assert zombie.status == TaskStatus.FAILED
    saved = ReportManager.get_report(zombie.metadata['report_id'])
    assert saved is not None and saved.status == ReportStatus.FAILED


def test_thread_start_failure_fails_the_claim_and_releases_the_registration(environment, monkeypatch):
    client, _ = environment
    released = []
    monkeypatch.setattr(api, 'unregister_graph_reader',
                        lambda graph_id, report_id: released.append((graph_id, report_id)))

    class ExplodingThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            raise RuntimeError('can not start new thread')

    monkeypatch.setattr(api.threading, 'Thread', ExplodingThread)

    response = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})

    assert response.status_code == 500
    zombie = TaskManager().find_task('report:sim_safe:v1')
    assert zombie.status == TaskStatus.FAILED
    assert released == [('graph_run', zombie.metadata['report_id'])]


def test_never_started_failed_report_does_not_block_a_normal_retry(environment, monkeypatch):
    """A report that was marked FAILED before its worker started must not be
    returned by a plain retry: with nothing produced there is no artifact to
    reuse, so the request must allocate the next version instead."""
    client, started = environment
    calls = {'n': 0}
    real_register = api.register_graph_reader

    def flaky_register(graph_id, report_id):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('registration down (fixture)')
        return real_register(graph_id, report_id)

    monkeypatch.setattr(api, 'register_graph_reader', flaky_register)

    first = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})
    assert first.status_code == 500
    manager = TaskManager()
    failed = manager.find_task('report:sim_safe:v1')
    assert failed.status == TaskStatus.FAILED

    second = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})

    assert second.status_code == 200, second.json
    data = second.json['data']
    assert data['task_id'] != failed.task_id
    assert data['report_id'] != failed.metadata['report_id']
    assert manager.find_task('report:sim_safe:v2') is not None
    fresh = ReportManager.get_report(data['report_id'])
    assert fresh is not None and fresh.version == 2
