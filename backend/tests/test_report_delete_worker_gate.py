"""R04 follow-up: a report whose background worker is still writing must not be deleted.

A completed-on-disk report can still have an active task window (the worker
finishes its writes and only then marks the task terminal); deleting inside
that window lets the worker recreate the folder afterwards.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from flask import Flask

from app.api import report as api
from app.config import Config
from app.models.task import TaskManager, TaskStatus
from app.services.report_agent import Report, ReportManager, ReportStatus
from app.storage import database


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    app = Flask(__name__)
    app.register_blueprint(api.report_bp, url_prefix='/api/report')
    return app.test_client()


def save_report(report_id, status, task_id):
    ReportManager.save_report(Report(
        report_id=report_id, simulation_id='sim_gate', graph_id='graph_gate',
        simulation_requirement='fixture', status=status, outline=None, markdown_content='body',
        created_at=datetime.now(timezone.utc).isoformat(), task_id=task_id, run_id='run_gate', version=1,
        manifest={}))
    return Path(ReportManager._get_report_folder(report_id))


def live_task(resource_key, report_id):
    manager = TaskManager()
    task_id, created = manager.claim_task('report_generate', resource_key, {'report_id': report_id})
    assert created
    manager.update_task(task_id, status=TaskStatus.PROCESSING)
    return task_id


def test_delete_refused_while_its_task_is_still_active(environment):
    client = environment
    task_id = live_task('report:sim_gate:v1', 'report_live')
    folder = save_report('report_live', ReportStatus.COMPLETED, task_id)

    response = client.delete('/api/report/report_live')

    assert response.status_code == 409
    assert response.json['success'] is False
    assert folder.exists()
    assert ReportManager.get_report('report_live') is not None


def test_delete_allowed_after_task_is_terminal(environment):
    client = environment
    task_id = live_task('report:sim_gate:v2', 'report_done')
    TaskManager().complete_task(task_id, {'report_id': 'report_done'})
    folder = save_report('report_done', ReportStatus.COMPLETED, task_id)

    response = client.delete('/api/report/report_done')

    assert response.status_code == 200
    assert not folder.exists()


def test_delete_allowed_when_task_owner_is_not_verifiable(environment):
    client = environment
    task_id = live_task('report:sim_gate:v3', 'report_orphan')
    with database() as db:
        db.execute('UPDATE tasks SET owner=? WHERE task_id=?',
                   (json.dumps({'instance': 'other', 'host': 'not-this-host', 'pid': 1, 'started': 0}), task_id))
    folder = save_report('report_orphan', ReportStatus.COMPLETED, task_id)

    response = client.delete('/api/report/report_orphan')

    assert response.status_code == 200
    assert not folder.exists()
