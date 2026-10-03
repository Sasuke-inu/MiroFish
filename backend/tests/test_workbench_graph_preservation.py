from datetime import datetime
from types import SimpleNamespace
import pytest
from flask import Flask
from app.api import graph as api
from app.models.project import Project, ProjectStatus


@pytest.mark.parametrize('state,force', [(ProjectStatus.GRAPH_COMPLETED, True), (ProjectStatus.FAILED, False)])
def test_rebuild_never_deletes_previous_graph(monkeypatch, state, force):
    project = Project('proj_preserved', 'Fixture', state, datetime.now().isoformat(), '',
                      graph_id='graph_preserved', ontology={'entity_types': [], 'edge_types': []})
    deleted, saved = [], []
    monkeypatch.setattr(api.Config, 'graph_configuration_errors', lambda: [])
    monkeypatch.setattr(api.ProjectManager, 'get_project', lambda _: project)
    monkeypatch.setattr(api.ProjectManager, 'get_extracted_text', lambda _: 'Synthetic evidence')
    monkeypatch.setattr(api.ProjectManager, 'save_project', lambda value: saved.append(value))
    monkeypatch.setattr(api, '_delete_cloud_graph_if_present', lambda ident: deleted.append(ident))
    monkeypatch.setattr(api, 'TaskManager', lambda: SimpleNamespace(create_task=lambda *a, **kw: 'task_unused'))
    monkeypatch.setattr(api.threading, 'Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    app = Flask(__name__)
    with app.test_request_context('/build', method='POST', json={'project_id': project.project_id, 'force': force}):
        response = api.build_graph()
    body, status = response if isinstance(response, tuple) else (response, response.status_code)
    assert status == 409
    assert deleted == []
    assert project.graph_id == 'graph_preserved'


def test_reset_cannot_destroy_historical_graph(monkeypatch):
    project = Project('proj_reset', 'Fixture', ProjectStatus.GRAPH_COMPLETED, '', '', graph_id='graph_old')
    deleted = []
    monkeypatch.setattr(api.ProjectManager, 'get_project', lambda _: project)
    monkeypatch.setattr(api.ProjectManager, 'save_project', lambda _: None)
    monkeypatch.setattr(api, '_delete_cloud_graph_if_present', lambda value: deleted.append(value))
    app = Flask(__name__)
    with app.test_request_context('/reset', method='POST'):
        response, status = api.reset_project(project.project_id)
    assert status == 409
    assert response.json['new_project_required'] is True
    assert deleted == []
    assert project.graph_id == 'graph_old'
