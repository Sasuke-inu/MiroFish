from types import SimpleNamespace
import json

import httpx
from openai import APITimeoutError
import pytest

from app.services import oasis_profile_generator as profiles
from app.services import simulation_config_generator as configs


def generator(cls):
    value = object.__new__(cls)
    value.client, value.model_name = object(), 'synthetic-model'
    return value


@pytest.mark.parametrize('module,cls,invoke', [
    (profiles, profiles.OasisProfileGenerator, lambda v: v._generate_profile_with_llm('fixture', 'Person', 'synthetic', {}, '')),
    (configs, configs.SimulationConfigGenerator, lambda v: v._call_llm_with_retry('fixture', 'fixture')),
])
@pytest.mark.parametrize('failure', ['timeout', 'invalid_json'])
def test_uncertain_preparation_has_one_attempt_no_fallback(module, cls, invoke, failure, monkeypatch):
    calls = []
    def completion(*args, **kwargs):
        calls.append(kwargs)
        if failure == 'timeout':
            raise APITimeoutError(request=httpx.Request('POST', 'http://127.0.0.1:9001/v1'))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='not JSON'))])
    monkeypatch.setattr(module, 'create_chat_completion', completion)
    monkeypatch.setattr(profiles.time, 'sleep', lambda *_: None)
    with pytest.raises(RuntimeError) as error:
        invoke(generator(cls))
    assert getattr(error.value, 'needs_review', False)
    assert len(calls) == 1


@pytest.mark.parametrize('cls', [profiles.OasisProfileGenerator, configs.SimulationConfigGenerator])
def test_preparation_sdk_retry_is_disabled(cls, monkeypatch):
    monkeypatch.setattr(profiles.Config, 'GRAPH_PROVIDER', 'zep')
    monkeypatch.setattr(profiles.Config, 'ZEP_API_KEY', '')
    value = cls(api_key='synthetic-test-key', base_url='http://127.0.0.1:9001/v1', model_name='fixture')
    assert value.client.max_retries == 0


@pytest.mark.parametrize('stage', ['time', 'event', 'agents'])
def test_config_stages_cannot_hide_failed_generation_with_defaults(stage, monkeypatch):
    value = generator(configs.SimulationConfigGenerator)
    def fail(*args):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(value, '_call_llm_with_retry', fail)
    entity = SimpleNamespace(name='fixture', uuid='entity', summary='synthetic', get_entity_type=lambda:'Person')
    with pytest.raises(RuntimeError):
        if stage == 'time':
            value._generate_time_config('', 1)
        elif stage == 'event':
            value._generate_event_config('', '', [entity])
        else:
            value._generate_agent_configs_batch('', [entity], 0, '')


def test_profile_parallel_worker_propagates_failure_and_keeps_partial_data(monkeypatch, tmp_path):
    value = generator(profiles.OasisProfileGenerator)
    value.graph_id = None
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('synthetic generation unknown')
    monkeypatch.setattr(value, 'generate_profile_from_entity', generate)
    entities = [SimpleNamespace(name='fixture', uuid='entity', summary='synthetic', get_entity_type=lambda:'Person')]
    with pytest.raises(RuntimeError):
        value.generate_profiles_from_entities(entities, parallel_count=1, realtime_output_path=str(tmp_path / 'profiles.json'))
    assert len(calls) == 1
    assert not (tmp_path / 'profiles.json').exists()


def test_local_json_repair_does_not_make_another_generation(monkeypatch):
    calls = []
    def completion(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='```json\n'+json.dumps({'bio':'synthetic','persona':'preserved detail'})+'\n```'))])
    monkeypatch.setattr(profiles, 'create_chat_completion', completion)
    value = generator(profiles.OasisProfileGenerator)
    result = value._generate_profile_with_llm('fixture', 'Person', '', {}, '')
    assert result['persona'] == 'preserved detail' and len(calls) == 1


@pytest.mark.parametrize('failure,expected_status', [
    ('unknown_generation', 'needs_review'), ('no_entities', 'failed'), ('unsafe_value_error', 'failed'),
])
def test_prepare_api_persists_failure_without_reposting_generation(monkeypatch, tmp_path, failure, expected_status):
    import threading
    from flask import Flask
    from app.api import simulation as api
    from app.models.task import TaskManager, TaskStatus
    from app.services.simulation_manager import SimulationState, SimulationStatus
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(api.SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    state = SimulationState('sim_review', 'project', 'run_graph', source_graph_id='source_graph', graph_namespace_status='ready')
    calls = []
    def prepare(**kwargs):
        calls.append(kwargs)
        if failure == 'no_entities':
            raise api.PreparationNoEntities()
        if failure == 'unsafe_value_error':
            raise ValueError('synthetic-secret-provider-body')
        raise profiles.PreparationNeedsReview('角色生成结果未確認；已停止自動重試。')
    manager = SimpleNamespace(get_simulation=lambda _: state, prepare_simulation=prepare, _save_simulation_state=lambda _: None)
    monkeypatch.setattr(api, 'SimulationManager', lambda: manager)
    monkeypatch.setattr(api, '_check_simulation_prepared', lambda _: (False, {}))
    monkeypatch.setattr(api.ProjectManager, 'get_project', lambda _: SimpleNamespace(simulation_requirement='synthetic', graph_id='source_graph'))
    monkeypatch.setattr(api.ProjectManager, 'get_extracted_text', lambda _: 'synthetic input')
    monkeypatch.setattr(api, 'get_model_settings', lambda **_: {'provider':'custom', 'base_url':'http://127.0.0.1:9001/v1', 'model':'fixture', 'api_key':'synthetic-key'})
    monkeypatch.setattr(api, 'ZepEntityReader', lambda: SimpleNamespace(filter_defined_entities=lambda **_: SimpleNamespace(filtered_count=1, entity_types=['Person'])))
    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(threading, 'Thread', ImmediateThread)
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    client = app.test_client()
    first = client.post('/api/simulation/prepare', json={'simulation_id':'sim_review'})
    assert first.status_code == 200
    task = TaskManager().get_task(first.json['data']['task_id'])
    assert task.status.value == expected_status
    assert state.status.value == expected_status
    assert 'synthetic-secret-provider-body' not in task.error
    assert 'synthetic-secret-provider-body' not in state.error
    if failure == 'no_entities':
        assert task.error == state.error == api.PreparationNoEntities.message
    second = client.post('/api/simulation/prepare', json={'simulation_id':'sim_review'})
    assert second.status_code == 200 and second.json['data']['status'] == expected_status
    assert len(calls) == 1


def test_manager_keeps_partial_files_when_generation_needs_review(monkeypatch, tmp_path):
    from app.services import simulation_manager as manager_module
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(manager_module.SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    manager = manager_module.SimulationManager()
    state = manager_module.SimulationState('sim_review', 'project', 'run_graph', source_graph_id='source_graph', graph_namespace_status='ready')
    manager._save_simulation_state(state)
    partial = tmp_path / 'simulations' / 'sim_review' / 'reddit_profiles.json'
    partial.write_text('[{"name":"saved partial"}]')
    monkeypatch.setattr(manager_module, 'ZepEntityReader', lambda: SimpleNamespace(filter_defined_entities=lambda **_: SimpleNamespace(filtered_count=1, entity_types=['Person'], entities=[object()])))
    def fail(**kwargs):
        raise profiles.PreparationNeedsReview('生成結果未確認。')
    monkeypatch.setattr(manager_module, 'OasisProfileGenerator', lambda **_: SimpleNamespace(generate_profiles_from_entities=fail))
    with pytest.raises(profiles.PreparationNeedsReview):
        manager.prepare_simulation('sim_review', 'synthetic', 'synthetic')
    assert manager.get_simulation('sim_review').status == manager_module.SimulationStatus.NEEDS_REVIEW
    assert partial.read_text() == '[{"name":"saved partial"}]'


def test_manager_does_not_publish_arbitrary_value_error(monkeypatch, tmp_path):
    from app.services import simulation_manager as manager_module
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(manager_module.SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    manager = manager_module.SimulationManager()
    state = manager_module.SimulationState('sim_error', 'project', 'run_graph', source_graph_id='source_graph', graph_namespace_status='ready')
    manager._save_simulation_state(state)
    def fail(**kwargs):
        raise ValueError('synthetic-secret-provider-body')
    monkeypatch.setattr(manager_module, 'ZepEntityReader', lambda: SimpleNamespace(filter_defined_entities=fail))
    with pytest.raises(ValueError):
        manager.prepare_simulation('sim_error', 'synthetic', 'synthetic')
    saved = manager.get_simulation('sim_error')
    assert saved.status == manager_module.SimulationStatus.FAILED
    assert saved.error == '模擬準備未完成，請核對已保存內容。'
