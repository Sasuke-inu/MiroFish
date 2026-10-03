"""Cross-process input gates and immutable ontology settings, using only fixtures."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import multiprocessing
from threading import Event

from flask import Flask
import pytest

from app.api import graph
from app.config import Config
from app.models.project import ProjectManager, ProjectStatus
from app.models.task import TaskManager
from app.provider_settings import get_model_settings
from app.services.research_workbench import ResearchWorkbench


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    selected = {'provider': 'custom', 'base_url': 'http://127.0.0.1:1/v1', 'model': 'model-a', 'api_key': 'synthetic-key-a'}
    monkeypatch.setattr(graph, 'get_model_settings', lambda **_: deepcopy(selected))
    class Generator:
        def generate(self, **kwargs):
            return {'entity_types': [{'name': 'Person'}], 'edge_types': [], 'analysis_summary': 'Synthetic'}
    monkeypatch.setattr(graph, 'OntologyGenerator', Generator)
    app = Flask(__name__)
    app.register_blueprint(graph.graph_bp, url_prefix='/api/graph')
    service = ResearchWorkbench()
    pid = service.create('Input gate fixture', 'Synthetic requirement')['project_id']
    first = service.save_source(pid, title='source', identity='one', content='Original source')
    return service, pid, first, app, selected


def test_source_materialization_cannot_overwrite_completed_ontology(context, monkeypatch):
    service, pid, _, app, _ = context
    source_paused, release_source, generation_started = Event(), Event(), Event()
    original_sources = service.all_sources
    def paused_sources(project_id):
        source_paused.set()
        assert release_source.wait(10)
        return original_sources(project_id)
    monkeypatch.setattr(service, 'all_sources', paused_sources)
    original_generator = graph.OntologyGenerator
    class Generator(original_generator):
        def generate(self, **kwargs):
            generation_started.set()
            return super().generate(**kwargs)
    monkeypatch.setattr(graph, 'OntologyGenerator', Generator)
    with ThreadPoolExecutor(max_workers=2) as pool:
        source = pool.submit(service.save_source, pid, title='source', identity='one', content='Newer source')
        assert source_paused.wait(10)
        ontology = pool.submit(lambda: app.test_client().post('/api/graph/ontology/generate', data={'project_id': pid}))
        try:
            # With no shared gate the API completes while the stale source
            # writer is paused; it subsequently erases the completed metadata.
            assert not generation_started.wait(.3)
        finally:
            release_source.set()
        source.result(timeout=10)
        response = ontology.result(timeout=10)
    assert response.status_code == 200, response.json
    saved = ProjectManager.get_project(pid)
    assert saved.status == ProjectStatus.ONTOLOGY_GENERATED and saved.ontology
    assert ProjectManager.get_input_snapshot(pid)['source_versions'] == saved.source_versions
    assert 'Newer source' in ProjectManager.get_input_snapshot(pid)['text']


def test_updates_during_generation_preserve_claimed_input(context, monkeypatch):
    service, pid, first, app, _ = context
    generating, release = Event(), Event()
    original_generator = graph.OntologyGenerator
    class Generator(original_generator):
        def generate(self, **kwargs):
            generating.set()
            assert release.wait(10)
            return super().generate(**kwargs)
    monkeypatch.setattr(graph, 'OntologyGenerator', Generator)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(lambda: app.test_client().post('/api/graph/ontology/generate', data={'project_id': pid}))
        assert generating.wait(10)
        try:
            # Generation does not hold the gate or prevent preserving new evidence.
            updated = pool.submit(service.save_source, pid, title='source', identity='one', content='Later source').result(timeout=3)
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 200
    saved = ProjectManager.get_project(pid)
    assert saved.source_versions[0]['version_id'] == first['version']['version_id']
    assert saved.source_versions[0]['version_id'] != updated['version']['version_id']
    assert ProjectManager.get_input_snapshot(pid)['source_versions'] == saved.source_versions


def test_ontology_model_is_frozen_before_file_parsing_and_recorded_without_key(context, monkeypatch):
    _, _, _, app, selected = context
    observed = []
    def extract(_path):
        selected.update(model='model-b', api_key='synthetic-key-b')
        return 'Synthetic uploaded source'
    monkeypatch.setattr(graph.FileParser, 'extract_text', extract)
    class Generator:
        def generate(self, **kwargs):
            observed.append(get_model_settings())
            return {'entity_types': [{'name': 'Person'}], 'edge_types': [], 'analysis_summary': 'Synthetic'}
    monkeypatch.setattr(graph, 'OntologyGenerator', Generator)
    response = app.test_client().post('/api/graph/ontology/generate', data={
        'simulation_requirement': 'Synthetic requirement', 'files': (io.BytesIO(b'synthetic'), 'source.md')},
        content_type='multipart/form-data')
    assert response.status_code == 200, response.json
    assert observed[0]['model'] == 'model-a'
    pid = response.json['data']['project_id']
    metadata = TaskManager().find_task(f'ontology:{pid}').metadata
    assert metadata['model_snapshot']['model'] == 'model-a'
    assert metadata['model_frozen_at']
    assert 'api_key' not in metadata['model_snapshot']


def _other_process_gate(root, pid, ready, entered):
    ProjectManager.PROJECTS_DIR = root
    ready.set()
    with ProjectManager.input_mutation_lock(pid):
        entered.set()


def test_input_gate_serializes_independent_processes(context):
    _, pid, _, _, _ = context
    ctx = multiprocessing.get_context('spawn')
    ready, entered = ctx.Event(), ctx.Event()
    process = ctx.Process(target=_other_process_gate, args=(ProjectManager.PROJECTS_DIR, pid, ready, entered))
    try:
        with ProjectManager.input_mutation_lock(pid):
            process.start()
            assert ready.wait(15)
            assert not entered.wait(.2)
        assert entered.wait(15)
        process.join(timeout=15)
        assert process.exitcode == 0
    finally:
        if process.pid and process.is_alive():
            process.terminate()
            process.join(timeout=5)
