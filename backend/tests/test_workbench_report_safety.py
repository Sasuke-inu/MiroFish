from types import SimpleNamespace
from flask import Flask
import pytest

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
    monkeypatch.setattr(api, 'SimulationManager', lambda: SimpleNamespace(get_simulation=lambda _: SimpleNamespace(project_id='proj_safe', graph_id='graph_run', source_graph_id='graph_safe', graph_namespace_status='ready')))
    monkeypatch.setattr(api.ProjectManager, 'get_project', lambda _: SimpleNamespace(status=ProjectStatus.GRAPH_COMPLETED, graph_id='graph_safe', simulation_requirement='Synthetic fixture'))
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
    return app.test_client(), run, threads


def test_duplicate_report_request_reuses_task_and_report_identity(environment):
    client, _, threads = environment
    first = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})
    second = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})
    assert first.status_code == second.status_code == 200
    assert first.json['data']['task_id'] == second.json['data']['task_id']
    assert first.json['data']['report_id'] == second.json['data']['report_id']
    assert len(threads) == 1


@pytest.mark.parametrize('state,ready', [('stopped', True), ('failed', True), ('completed', False)])
def test_incomplete_run_never_generates_formal_report(environment, state, ready):
    client, run, threads = environment
    run.runner_status = RunnerStatus(state)
    run.graph_ready = ready
    response = client.post('/api/report/generate', json={'simulation_id': 'sim_safe'})
    assert response.status_code == 409
    assert not threads


def test_specific_task_status_wins_over_old_completed_report(environment):
    client, _, _ = environment
    old = Report('report_old', 'sim_safe', 'graph_safe', 'Fixture', ReportStatus.COMPLETED, created_at='2025-01-01')
    ReportManager.save_report(old)
    task = TaskManager().create_task('report_generate', {'simulation_id': 'sim_safe'})
    response = client.post('/api/report/generate/status', json={'simulation_id': 'sim_safe', 'task_id': task})
    assert response.status_code == 200
    assert response.json['data']['status'] == 'pending'


def test_report_versions_are_ordered_and_old_content_is_preserved(environment):
    for ident, created, content in [('report_old', '2025-01-01', 'Older'), ('report_new', '2025-01-02', 'Newer')]:
        ReportManager.save_report(Report(ident, 'sim_safe', 'graph_safe', 'Fixture', ReportStatus.COMPLETED,
                                        created_at=created, markdown_content=content))
    assert ReportManager.get_report_by_simulation('sim_safe').report_id == 'report_new'
    assert ReportManager.get_report('report_old').markdown_content == 'Older'
