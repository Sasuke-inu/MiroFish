"""R08 consumers: draft input, quality, clone and the source API use the latest observation."""
import json

import pytest
from flask import Flask

from app.api.workbench import workbench_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.report_agent import ReportManager
from app.services.research_workbench import ResearchWorkbench
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path / 'runs'), raising=False)
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    app = Flask(__name__)
    app.register_blueprint(workbench_bp, url_prefix='/api/workbench')
    client = app.test_client()
    token = client.get('/api/workbench/session').json['data']['csrf_token']
    return ResearchWorkbench(), client, {'X-MiroFish-CSRF': token}


def test_restored_text_returns_to_draft_and_source_api(workbench):
    service, client, _ = workbench
    pid = service.create('復原來源')['project_id']
    a = service.save_source(pid, title='來源', content='ALPHA 原文', identity='same')
    service.save_source(pid, title='來源', content='BRAVO 原文', identity='same')
    assert 'BRAVO' in ProjectManager.get_extracted_text(pid)
    again = service.save_source(pid, title='來源', content='ALPHA 原文', identity='same')
    assert again['version']['version_id'] == a['version']['version_id']
    assert 'ALPHA' in ProjectManager.get_extracted_text(pid)
    assert 'BRAVO' not in ProjectManager.get_extracted_text(pid)
    data = client.get(f"/api/workbench/sources/{a['source']['source_id']}").json['data']
    assert data['latest_version_id'] == a['version']['version_id']
    bare = service.evidence.create_source(pid, 'document', 'no-versions', title='空的')
    assert client.get(f"/api/workbench/sources/{bare['source_id']}").json['data']['latest_version_id'] is None
    # The versions history itself is not reordered or rewritten.
    assert data['versions']['items'][0]['version_id'] != a['version']['version_id']
    assert service.evidence.list_versions(a['source']['source_id'])['total'] == 2


def test_missing_then_restored_text_counts_as_preserved(workbench):
    service, _, _ = workbench
    pid = service.create('缺失復原')['project_id']
    service.save_source(pid, title='來源', content='ALPHA 原文', identity='same')
    service.save_source(pid, title='來源', status='missing', identity='same')
    assert service.quality(pid)['source_preservation']['numerator'] == 0
    service.save_source(pid, title='來源', content='ALPHA 原文', identity='same')
    quality = service.quality(pid)
    assert quality['source_preservation']['numerator'] == 1
    assert quality['source_preservation']['value'] == 1
    exported = json.loads(service.export(pid, 'json')[0])
    assert exported['quality']['source_preservation']['value'] == 1


def test_clone_copies_latest_observed_text(workbench):
    service, _, _ = workbench
    pid = service.create('複製版本')['project_id']
    service.save_source(pid, title='來源', content='ALPHA 原文', identity='same')
    service.save_source(pid, title='來源', content='BRAVO 原文', identity='same')
    service.save_source(pid, title='來源', content='ALPHA 原文', identity='same')
    draft = service.clone(pid)
    assert 'ALPHA' in ProjectManager.get_extracted_text(draft['project_id'])
    assert 'BRAVO' not in ProjectManager.get_extracted_text(draft['project_id'])
