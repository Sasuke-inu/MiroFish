"""R12: report versions come from a persistent ledger, never from re-usable claims."""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.api import report as api
from app.config import Config
from app.models.project import ProjectStatus
from app.models.task import TaskManager
from app.services.report_agent import Report, ReportManager, ReportStatus
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
    threads = []

    class ParkedThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            threads.append(self.target)

    monkeypatch.setattr(api.threading, 'Thread', ParkedThread)
    app = Flask(__name__)
    app.register_blueprint(api.report_bp, url_prefix='/api/report')
    return app.test_client(), threads


def generate(client, **payload):
    response = client.post('/api/report/generate', json={'simulation_id': 'sim_safe', **payload})
    assert response.status_code == 200, response.json
    return response.json['data']


def finish(task_id, created_at='2025-01-01'):
    """Mark a claimed report task as finished with its saved artifact."""
    manager = TaskManager()
    report_id = manager.get_task(task_id).metadata['report_id']
    ReportManager.save_report(Report(
        report_id, 'sim_safe', 'graph_safe', 'Fixture', ReportStatus.COMPLETED,
        created_at=created_at, markdown_content=f'BODY_{report_id}'))
    manager.complete_task(task_id, {'report_id': report_id})
    return report_id


def test_deleted_version_is_never_reused(environment):
    client, _ = environment
    manager = TaskManager()
    task_id, created = manager.claim_task(
        'report_generate', 'report:sim_safe:v1',
        {'simulation_id': 'sim_safe', 'graph_id': 'graph_run', 'report_id': 'report_v1'})
    assert created
    ReportManager.save_report(Report('report_v1', 'sim_safe', 'graph_safe', 'Fixture', ReportStatus.COMPLETED,
                                     created_at='2025-01-01', task_id=task_id, version=1, markdown_content='BODY_V1'))
    manager.complete_task(task_id, {'report_id': 'report_v1'})
    assert client.delete('/api/report/report_v1').status_code == 200

    data = generate(client)

    assert data['already_generated'] is False
    fresh = ReportManager.get_report(data['report_id'])
    assert fresh is not None and fresh.version == 2
    assert TaskManager().find_task('report:sim_safe:v2') is not None


def test_delete_of_the_latest_version_advances_the_ledger(environment):
    client, _ = environment
    first = generate(client)
    finish(first['task_id'], '2025-01-01')
    second = generate(client, force_regenerate=True)
    assert second['report_id'] != first['report_id']
    finish(second['task_id'], '2025-01-02')
    assert client.delete(f"/api/report/{second['report_id']}").status_code == 200

    # 未要求重生成時仍重用既有版本（既有行為），且不會指向已刪除的產物
    cached = generate(client)
    assert cached['report_id'] == first['report_id']
    assert cached['already_generated'] is True

    third = generate(client, force_regenerate=True)

    fresh = ReportManager.get_report(third['report_id'])
    assert fresh is not None and fresh.version == 3
    assert TaskManager().find_task('report:sim_safe:v3') is not None
    assert ReportManager.get_report(first['report_id']) is not None


def test_reused_task_without_its_artifact_is_never_already_generated(environment):
    client, _ = environment
    first = generate(client)
    finish(first['task_id'])
    assert client.delete(f"/api/report/{first['report_id']}").status_code == 200
    # A claimed-but-missing artifact for the next version (older task rows survive deletes).
    ghost_id, created = TaskManager().claim_task(
        'report_generate', 'report:sim_safe:v2',
        {'simulation_id': 'sim_safe', 'graph_id': 'graph_run', 'report_id': 'report_absent'})
    assert created
    TaskManager().complete_task(ghost_id, {'report_id': 'report_absent'})

    response = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})

    assert response.status_code == 409
    assert response.json['success'] is False
    assert response.json.get('already_generated') is not True


def test_concurrent_claims_join_one_active_version(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    manager = TaskManager()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: manager.claim_report_version('sim_race', {'simulation_id': 'sim_race'}), range(6)))

    # 同時的重複請求只認領同一份新工作：同一版本、同一工作，只建立一次。
    assert {version for _, _, version in results} == {1}
    assert len({task_id for task_id, _, _ in results}) == 1
    assert sum(created for _, created, _ in results) == 1
    assert TaskManager().find_task('report:sim_race:v1') is not None


def test_concurrent_duplicate_requests_claim_one_task(environment):
    client, threads = environment
    first = generate(client)
    second = generate(client)

    assert first['task_id'] == second['task_id'] == TaskManager().find_task('report:sim_safe:v1').task_id
    assert first['report_id'] == second['report_id']
    assert len(threads) == 1
