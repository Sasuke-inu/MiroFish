"""R09: the demo catalog reports an installed project instead of inviting a re-install."""
import pytest
from flask import Flask

from app.api.workbench import workbench_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services import workbench_demos as demos
from app.services.report_agent import ReportManager
from app.services.research_workbench import ResearchWorkbench
from app.services.simulation_manager import SimulationManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    app = Flask(__name__)
    app.register_blueprint(workbench_bp, url_prefix='/api/workbench')
    return app.test_client()


def test_catalog_exposes_installed_project_and_leaves_others_null(client):
    before = client.get('/api/workbench/demos').json['data']['items']
    assert {item['id'] for item in before} == {'product', 'story', 'contradiction'}
    assert {item['project_id'] for item in before} == {None}

    installed = demos.install('story')['project_id']
    items = {item['id']: item for item in client.get('/api/workbench/demos').json['data']['items']}
    assert items['story']['project_id'] == installed
    assert items['product']['project_id'] is None
    assert items['contradiction']['project_id'] is None
    assert (items['story']['title'], items['story']['description'],
            items['story']['kind']) == ('故事角色互動', '虛構村落中兩位角色的選擇與互動。', 'synthetic_fixture')

    # A second install keeps the same project and does not duplicate sources.
    sources = ResearchWorkbench().detail(installed)['sources']['total']
    assert demos.install('story')['project_id'] == installed
    assert ResearchWorkbench().detail(installed)['sources']['total'] == sources
    assert {item['id']: item['project_id'] for item in
            client.get('/api/workbench/demos').json['data']['items']}['story'] == installed
