"""One simulation, one immutable execution; no live services or user data."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from flask import Flask

from app.api import simulation as api
from app.services import simulation_runner as module
from app.services.simulation_runner import SimulationRunner, SimulationRunState, RunnerStatus
from app.services.simulation_ipc import SimulationIPCClient


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from app.config import Config
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    for field in ('_run_states', '_processes', '_monitor_threads', '_graph_memory_enabled', '_action_queues', '_stdout_files', '_stderr_files'):
        monkeypatch.setattr(SimulationRunner, field, {})
    monkeypatch.setattr(SimulationRunner, '_manual_stop_requests', set())
    monkeypatch.setattr(SimulationRunner, '_sync_simulation_status', classmethod(lambda *_: None))


def test_legacy_success_is_not_verified_graph_ready():
    state = SimulationRunState('sim_legacy', runner_status=RunnerStatus.COMPLETED)
    assert state.to_dict()['graph_ready'] is False


def test_duplicate_completed_start_returns_original_without_touching_files(monkeypatch):
    state = SimulationRunState('sim_done', runner_status=RunnerStatus.COMPLETED)
    monkeypatch.setattr(SimulationRunner, 'get_run_state', classmethod(lambda *_: state))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('duplicate process'))
    assert SimulationRunner.start_simulation('sim_done') is state


def test_force_start_rejected_before_any_cleanup(monkeypatch):
    monkeypatch.setattr(SimulationRunner, 'cleanup_simulation_logs', classmethod(lambda *_: pytest.fail('destructive cleanup')))
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    result = app.test_client().post('/api/simulation/start', json={'simulation_id': 'sim_done', 'force': True})
    assert result.status_code == 409


def test_cleanup_never_deletes_prior_execution(tmp_path):
    directory = tmp_path / 'sim_done'
    directory.mkdir()
    saved = directory / 'run_state.json'
    saved.write_text('{"runner_status":"completed"}', encoding='utf-8')
    result = SimulationRunner.cleanup_simulation_logs('sim_done')
    assert result['success'] is False
    assert saved.read_text(encoding='utf-8') == '{"runner_status":"completed"}'


def test_completion_requires_all_selected_platforms_even_without_a_log(tmp_path):
    directory = tmp_path / 'sim_pair' / 'twitter'
    directory.mkdir(parents=True)
    (directory / 'actions.jsonl').write_text('', encoding='utf-8')
    state = SimulationRunState('sim_pair', enabled_platforms=['twitter', 'reddit'], twitter_completed=True)
    assert SimulationRunner._check_all_platforms_completed(state) is False


def test_zero_exit_without_completion_receipts_cannot_be_success(monkeypatch):
    state = SimulationRunState('sim_empty', enabled_platforms=['reddit'], runner_status=RunnerStatus.RUNNING)
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda *_: None))
    SimulationRunner._finish_run(state, RunnerStatus.COMPLETED)
    assert state.runner_status != RunnerStatus.COMPLETED
    assert state.graph_ready is False


def test_nonzero_exit_public_error_keeps_code_without_private_log_tail(tmp_path, monkeypatch):
    directory = tmp_path / 'sim_exit'
    directory.mkdir()
    (directory / 'simulation.log').write_text('SYNTHETIC_PRIVATE_KEY /private/local/path', encoding='utf-8')
    state = SimulationRunState('sim_exit', runner_status=RunnerStatus.RUNNING)
    monkeypatch.setattr(SimulationRunner, 'get_run_state', classmethod(lambda *_: state))
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda *_: None))
    SimulationRunner._processes[state.simulation_id] = SimpleNamespace(poll=lambda: 7, returncode=7)
    SimulationRunner._monitor_simulation(state.simulation_id)
    assert state.runner_status == RunnerStatus.FAILED and not state.graph_ready
    assert '7' in state.error
    assert 'SYNTHETIC_PRIVATE' not in state.error and '/private/' not in state.error


def test_updater_failure_public_error_only_contains_exception_type(monkeypatch):
    state = SimulationRunState('sim_updater_error', runner_status=RunnerStatus.RUNNING)
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda *_: None))
    SimulationRunner._graph_memory_enabled[state.simulation_id] = True
    def fail(*_):
        raise TimeoutError('SYNTHETIC_PRIVATE_KEY /private/local/path')
    monkeypatch.setattr(module.ZepGraphMemoryManager, 'stop_updater', fail)
    SimulationRunner._finish_run(state, RunnerStatus.STOPPED)
    assert state.runner_status == RunnerStatus.FAILED and not state.graph_ready
    assert 'TimeoutError' in state.error
    assert 'SYNTHETIC_PRIVATE' not in state.error and '/private/' not in state.error


def test_graph_ready_is_published_only_after_complete_receipts_and_drain(monkeypatch):
    state = SimulationRunState('sim_valid', run_id='run_valid', attempt_id='attempt_valid', enabled_platforms=['reddit'], reddit_completed=True, runner_status=RunnerStatus.RUNNING)
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda *_: None))
    SimulationRunner._graph_memory_enabled[state.simulation_id] = True
    def drain(*_):
        assert state.graph_ready is False
        assert state.runner_status == RunnerStatus.FINALIZING
    monkeypatch.setattr(module.ZepGraphMemoryManager, 'stop_updater', classmethod(drain))
    SimulationRunner._finish_run(state, RunnerStatus.COMPLETED)
    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.graph_ready is True


def test_lost_owner_cannot_be_stopped_into_success(monkeypatch):
    state = SimulationRunState('sim_orphan', runner_status=RunnerStatus.RUNNING, process_pid=4242)
    monkeypatch.setattr(SimulationRunner, 'get_run_state', classmethod(lambda *_: state))
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda *_: None))
    with pytest.raises(RuntimeError):
        SimulationRunner.stop_simulation(state.simulation_id)
    assert state.runner_status in {RunnerStatus.INTERRUPTED, RunnerStatus.NEEDS_REVIEW}
    assert state.graph_ready is False


def test_prior_run_completion_marker_is_ignored(tmp_path):
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'run_id': 'old', 'attempt_id': 'old', 'total_rounds': 1}) + '\n', encoding='utf-8')
    state = SimulationRunState('sim_new', run_id='new', attempt_id='new', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert not state.reddit_completed


def test_expired_interview_heartbeat_is_not_alive(tmp_path):
    (tmp_path / 'env_status.json').write_text(json.dumps({'status': 'alive', 'timestamp': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}), encoding='utf-8')
    assert SimulationIPCClient(str(tmp_path)).check_env_alive() is False


def test_prepare_status_restores_claimed_task_without_reposting():
    from app.models.task import TaskManager, TaskStatus
    task_id, _ = TaskManager().claim_task('simulation_prepare', 'prepare:sim_waiting', {'simulation_id': 'sim_waiting'})
    TaskManager().update_task(task_id, status=TaskStatus.PROCESSING, progress=21)
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    result = app.test_client().post('/api/simulation/prepare/status', json={'simulation_id': 'sim_waiting'})
    assert result.status_code == 200
    assert result.json['data']['task_id'] == task_id
    assert result.json['data']['status'] == 'processing'


def test_clone_copies_only_prepared_inputs_and_keeps_original(tmp_path, monkeypatch):
    from app.services.simulation_manager import SimulationManager, SimulationStatus
    from app.services import simulation_manager as manager_module
    monkeypatch.setattr(manager_module.Config, 'GRAPH_PROVIDER', 'graphiti')
    def clone_graph(source, *, graph_id, operation_id):
        assert source == 'graph_fixture'
        return SimpleNamespace(source_graph_id=source, target_graph_id=graph_id,
                               operation_id=operation_id, status='ready', summary={'node_mapping': {}})
    monkeypatch.setattr(manager_module, 'get_zep_client', lambda: SimpleNamespace(graph=SimpleNamespace(clone=clone_graph)))
    monkeypatch.setattr(manager_module, 'get_model_settings', lambda **_: {'provider': 'fixture', 'base_url': 'https://fixture.invalid', 'model': 'fixture', 'api_key': 'fixture'})
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path))
    manager = SimulationManager()
    source = manager.create_simulation('proj_fixture', 'graph_fixture', False, True)
    source.status = SimulationStatus.COMPLETED
    source.config_generated = source.profiles_generated = True
    manager._save_simulation_state(source)
    directory = tmp_path / source.simulation_id
    (directory / 'simulation_config.json').write_text(json.dumps({'simulation_id': source.simulation_id}), encoding='utf-8')
    (directory / 'reddit_profiles.json').write_text('[]', encoding='utf-8')
    (directory / 'reddit_simulation.db').write_bytes(b'original-result')
    clone = manager.clone_simulation(source.simulation_id)
    assert clone.simulation_id != source.simulation_id
    assert clone.status == SimulationStatus.READY
    assert json.loads((tmp_path / clone.simulation_id / 'simulation_config.json').read_text())['simulation_id'] == clone.simulation_id
    assert not (tmp_path / clone.simulation_id / 'reddit_simulation.db').exists()
    assert (directory / 'reddit_simulation.db').read_bytes() == b'original-result'
    assert clone.source_graph_id == source.source_graph_id == 'graph_fixture'
    assert clone.graph_id != source.graph_id


def test_concurrent_starts_spawn_once_and_return_same_identity(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.provider_settings import get_model_settings
    folder = tmp_path / 'sim_concurrent'
    folder.mkdir()
    (folder / 'state.json').write_text(json.dumps({'graph_namespace_status': 'ready', 'source_graph_id': 'source_graph', 'graph_id': 'run_graph',
        'simulation_model_snapshot': module.public_manifest(get_model_settings())}), encoding='utf-8')
    (folder / 'simulation_config.json').write_text(json.dumps({'time_config': {'total_simulation_hours': 1, 'minutes_per_round': 60}}), encoding='utf-8')
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'run_parallel_simulation.py').write_text('pass', encoding='utf-8')
    monkeypatch.setattr(SimulationRunner, 'SCRIPTS_DIR', str(scripts))
    calls = []
    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(SimulationRunner, '_monitor_simulation', classmethod(lambda *_: None))
    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(lambda _: SimulationRunner.start_simulation('sim_concurrent', platform='reddit'), range(2)))
    assert len(calls) == 1
    assert states[0].run_id == states[1].run_id
    assert '--reddit-only' in calls[0][0]
    assert calls[0][1]['env']['MIROFISH_RUN_ID'] == states[0].run_id
    for handle in SimulationRunner._stdout_files.values():
        handle.close()


def test_prepare_claims_once_and_binds_model_before_background_thread(monkeypatch):
    import threading
    from app.models.task import TaskManager
    from app.provider_settings import get_model_settings
    from app.services.simulation_manager import SimulationState, SimulationStatus
    state = SimulationState('sim_prepare', 'project', 'graph')
    state.source_graph_id = 'source_graph'
    state.graph_namespace_status = 'ready'
    background, models, previews = [], [], []
    class Worker:
        def __init__(self, target, **_):
            self.target = target
        def start(self):
            background.append(self.target)
    class Manager:
        def get_simulation(self, _):
            return state
        def _save_simulation_state(self, _):
            pass
        def prepare_simulation(self, **_):
            models.append(get_model_settings()['model'])
            state.status = SimulationStatus.READY
            return state
    def preview(**_):
        previews.append(True)
        return SimpleNamespace(filtered_count=1, entity_types=['Person'])
    monkeypatch.setattr(threading, 'Thread', Worker)
    monkeypatch.setattr(api, 'SimulationManager', Manager)
    monkeypatch.setattr(api, '_check_simulation_prepared', lambda _: (False, {}))
    monkeypatch.setattr(api.ProjectManager, 'get_project', lambda _: SimpleNamespace(simulation_requirement='Fixture objective'))
    monkeypatch.setattr(api.ProjectManager, 'get_extracted_text', lambda _: 'Fixture document')
    monkeypatch.setattr(api, 'ZepEntityReader', lambda: SimpleNamespace(filter_defined_entities=preview))
    monkeypatch.setattr(api, 'get_model_settings', lambda **_: {'model': 'first', 'provider': 'fixture', 'base_url': 'https://fixture.invalid', 'api_key': 'PRIVATE-FIXTURE'})
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    first = app.test_client().post('/api/simulation/prepare', json={'simulation_id': state.simulation_id})
    monkeypatch.setattr(api, 'get_model_settings', lambda **_: {'model': 'second'})
    second = app.test_client().post('/api/simulation/prepare', json={'simulation_id': state.simulation_id})
    assert first.status_code == second.status_code == 200
    assert first.json['data']['task_id'] == second.json['data']['task_id']
    assert len(background) == len(previews) == 1
    background[0]()
    assert models == ['first']
    task = TaskManager().get_task(first.json['data']['task_id'])
    assert 'PRIVATE-FIXTURE' not in json.dumps(task.to_dict())


def test_producer_logs_identity_and_heartbeat_is_scoped_to_completed_run(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'action_logger.py'
    spec = importlib.util.spec_from_file_location('fixture_action_logger', path)
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    monkeypatch.setenv('MIROFISH_RUN_ID', 'run_fixture')
    monkeypatch.setenv('MIROFISH_ATTEMPT_ID', 'attempt_fixture')
    logger = producer.PlatformActionLogger('reddit', str(tmp_path))
    logger.log_simulation_end(1, 2)
    receipt = json.loads((tmp_path / 'reddit' / 'actions.jsonl').read_text())
    assert receipt['run_id'] == 'run_fixture'
    assert receipt['attempt_id'] == 'attempt_fixture'
    compatibility = producer.ActionLogger(str(tmp_path / 'legacy_actions.jsonl'))
    compatibility.log_round_start(1, 1, 'twitter')
    compatibility.log_round_start(1, 2, 'reddit')
    compatibility.log_action(1, 'twitter', 0, 'Fixture', 'post')
    legacy_event = json.loads((tmp_path / 'legacy_actions.jsonl').read_text().splitlines()[-1])
    assert legacy_event['run_id'] == 'run_fixture'
    assert legacy_event['simulation_time'] == 1
    state = {'run_id': 'run_fixture', 'attempt_id': 'attempt_fixture', 'runner_status': 'completed', 'graph_ready': True}
    (tmp_path / 'run_state.json').write_text(json.dumps(state), encoding='utf-8')
    heartbeat = producer.EnvironmentHeartbeat(str(tmp_path / 'env_status.json'))
    try:
        heartbeat.update('alive', reddit_available=True)
        assert heartbeat.thread.is_alive()
        client = SimulationIPCClient(str(tmp_path))
        assert client.check_env_alive() is True
        state['run_id'] = 'another_run'
        (tmp_path / 'run_state.json').write_text(json.dumps(state), encoding='utf-8')
        assert client.check_env_alive() is False
        heartbeat.update('stopped')
        assert client.check_env_alive() is False
    finally:
        heartbeat.update('stopped')
        heartbeat.thread.join(timeout=1)


def test_start_uses_frozen_simulation_connection_and_preserves_manifest(tmp_path, monkeypatch):
    import hashlib
    from app import provider_settings
    from app.models.project import ProjectManager
    folder = tmp_path / 'sim_snapshot'
    folder.mkdir()
    frozen = {'provider': 'fixture', 'base_url': 'https://fixture.invalid', 'model': 'frozen_model',
              'profile_id': 'original_profile', 'connection_fingerprint': hashlib.sha256(b'FIXTURE_KEY').hexdigest()}
    (folder / 'state.json').write_text(json.dumps({'graph_namespace_status': 'ready', 'source_graph_id': 'source_graph',
        'graph_id': 'run_graph', 'simulation_model_snapshot': frozen, 'simulation_model_frozen_at': '2026-01-01T00:00:00Z',
        'model_snapshot': {'model': 'prepare_model'}, 'project_id': 'project_fixture'}), encoding='utf-8')
    (folder / 'simulation_config.json').write_text(json.dumps({'seed': 7}), encoding='utf-8')
    profile_text = json.dumps([{'user_id': 0, 'entity_uuid': 'namespace_specific', 'persona': 'fixture'}])
    (folder / 'reddit_profiles.json').write_text(profile_text, encoding='utf-8')
    def selected_connection(**kwargs):
        assert kwargs == {'profile_id': 'original_profile'}
        return {**frozen, 'model': 'changed_after_creation', 'api_key': 'FIXTURE_KEY', 'source': 'saved'}
    monkeypatch.setattr(provider_settings, 'get_model_settings', selected_connection)
    sources = [{'source_id': 'src_fixture', 'version_id': 'version_graph_build', 'sha256': 'fixture_hash'}]
    monkeypatch.setattr(ProjectManager, 'get_project', lambda _: SimpleNamespace(graph_id='source_graph', source_versions=sources))
    calls = []
    def spawn(*_, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(SimulationRunner, '_monitor_simulation', classmethod(lambda *_: None))
    state = SimulationRunner.start_simulation('sim_snapshot', platform='reddit')
    assert calls[0]['env']['LLM_MODEL_NAME'] == 'frozen_model'
    assert state.manifest['model']['model'] == 'frozen_model'
    assert state.manifest['preparation_model']['model'] == 'prepare_model'
    assert state.manifest['source_versions'] == sources
    assert state.manifest['configuration']['seed'] == 7
    assert state.manifest['profile_hashes']['reddit_profiles.json'] == hashlib.sha256(profile_text.encode()).hexdigest()
    assert state.manifest['roles_snapshot_status'] == 'complete'
    assert state.manifest['roles'][0]['count'] == 1
    expected_roles = json.dumps([{'user_id': 0, 'persona': 'fixture'}], ensure_ascii=False, sort_keys=True)
    assert state.manifest['roles'][0]['sha256'] == hashlib.sha256(expected_roles.encode()).hexdigest()
    assert state.manifest['configuration_comparison_sha256']
    assert state.manifest['model_resolution']['requested']['model'] == 'frozen_model'
    assert state.manifest['model_resolution']['actual']['status'] == 'unknown'
    assert state.manifest['budget']['status'] == 'unknown'
    assert state.manifest['prompt_version']['status'] == 'unknown'
    assert state.manifest['code_hashes']['simulation_runner.py']
    assert 'FIXTURE_KEY' not in json.dumps(state.to_dict())
    for handle in SimulationRunner._stdout_files.values():
        handle.close()


def test_orphaned_runtime_files_are_not_reused_as_a_new_execution(tmp_path, monkeypatch):
    from app.provider_settings import get_model_settings
    folder = tmp_path / 'sim_orphaned_files'
    folder.mkdir()
    (folder / 'state.json').write_text(json.dumps({'graph_namespace_status': 'ready', 'source_graph_id': 'source_graph',
        'graph_id': 'run_graph', 'simulation_model_snapshot': module.public_manifest(get_model_settings())}), encoding='utf-8')
    (folder / 'simulation_config.json').write_text('{}', encoding='utf-8')
    (folder / 'reddit_simulation.db').write_bytes(b'original')
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('orphan overwrite'))
    with pytest.raises(ValueError, match='existing execution'):
        SimulationRunner.start_simulation('sim_orphaned_files')
    assert (folder / 'reddit_simulation.db').read_bytes() == b'original'


def test_simulation_identity_cannot_escape_storage_or_touch_original(tmp_path, monkeypatch):
    root = tmp_path / 'runs'
    root.mkdir()
    outside = tmp_path / 'original'
    outside.mkdir()
    original = '{"runner_status":"completed","simulation_id":"original"}'
    (outside / 'run_state.json').write_text(original, encoding='utf-8')
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(root))
    for method in (SimulationRunner.get_run_state, SimulationRunner.start_simulation, SimulationRunner.check_env_alive):
        with pytest.raises(ValueError):
            method('../original')
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    result = app.test_client().post('/api/simulation/prepare/status', json={'simulation_id': '../original'})
    assert result.status_code == 400
    assert (outside / 'run_state.json').read_text() == original
