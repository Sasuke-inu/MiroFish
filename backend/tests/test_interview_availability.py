from datetime import datetime, timezone
import json
import sqlite3
from types import SimpleNamespace

from flask import Flask
import pytest

from app.api import simulation as api
from app.services.simulation_runner import SimulationRunner


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(SimulationRunner, '_processes', {})
    directory = tmp_path / 'sim_fixture'
    directory.mkdir()
    (directory / 'run_state.json').write_text(json.dumps({'runner_status': 'completed', 'graph_ready': True,
        'run_id': 'run_fixture', 'attempt_id': 'attempt_fixture'}))
    (directory / 'env_status.json').write_text(json.dumps({'status': 'alive', 'run_id': 'run_fixture',
        'attempt_id': 'attempt_fixture', 'timestamp': datetime.now(timezone.utc).isoformat()}))
    (directory / 'simulation_config.json').write_text(json.dumps({'agent_configs': [{'agent_id': 0}]}))
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    return app.test_client(), directory


@pytest.mark.parametrize('producer', ['missing', 'exited', 'alive'])
def test_recent_heartbeat_requires_verified_live_producer(environment, producer):
    if producer != 'missing':
        SimulationRunner._processes['sim_fixture'] = SimpleNamespace(poll=lambda: None if producer == 'alive' else 0)
    assert SimulationRunner.check_env_alive('sim_fixture') is (producer == 'alive')


@pytest.mark.parametrize('route,payload', [
    ('interview', {'agent_id': 0, 'prompt': 'Synthetic question'}),
    ('interview/batch', {'interviews': [{'agent_id': 0, 'prompt': 'Synthetic question'}]}),
    ('interview/all', {'prompt': 'Synthetic question'}),
])
def test_closed_producer_api_is_history_only_and_never_sends(environment, monkeypatch, route, payload):
    client, directory = environment
    def forbidden(*_a, **_kw):
        pytest.fail('Closed producer cannot receive new interview commands')
    for method in ('interview_agent', 'interview_agents_batch', 'interview_all_agents'):
        monkeypatch.setattr(SimulationRunner, method, forbidden)
    response = client.post(f'/api/simulation/{route}', json={'simulation_id': 'sim_fixture', **payload})
    assert response.status_code == 409
    assert response.json['code'] == 'interview_unavailable' and response.json['history_only'] is True
    assert not (directory / 'ipc_commands').exists()


@pytest.mark.parametrize('method,args', [
    ('interview_agent', (0, 'Synthetic question')),
    ('interview_agents_batch', ([{'agent_id': 0, 'prompt': 'Synthetic question'}],)),
    ('interview_all_agents', ('Synthetic question',)),
])
def test_direct_runner_entry_cannot_bypass_producer_gate(environment, monkeypatch, method, args):
    from app.services.simulation_ipc import SimulationIPCClient
    _client, directory = environment
    monkeypatch.setattr(SimulationIPCClient, 'send_command', lambda *_a, **_kw: pytest.fail('No IPC send'))
    with pytest.raises(ValueError, match='未運行|未运行|核對'):
        getattr(SimulationRunner, method)('sim_fixture', *args)
    assert not (directory / 'ipc_commands').exists()


def test_closed_producer_history_remains_readable_without_ipc(environment):
    client, directory = environment
    with sqlite3.connect(directory / 'reddit_simulation.db') as db:
        db.execute('CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT, created_at TEXT)')
        db.execute('INSERT INTO trace VALUES (0,?,?,?)', ('interview', json.dumps({'prompt': 'Saved question', 'response': 'Saved answer'}), '2026-01-01'))
    response = client.post('/api/simulation/interview/history', json={'simulation_id': 'sim_fixture'})
    assert response.status_code == 200
    assert response.json['data']['history'][0]['response'] == 'Saved answer'
    assert not (directory / 'ipc_commands').exists()


def test_env_status_api_does_not_expose_stale_alive_heartbeat(environment):
    client, _directory = environment
    response = client.post('/api/simulation/env-status', json={'simulation_id': 'sim_fixture'})
    assert response.status_code == 200
    assert response.json['data']['env_alive'] is False
    assert response.json['data']['twitter_available'] is False
    assert response.json['data']['reddit_available'] is False


def test_explicit_interview_api_can_use_a_verified_alive_producer(environment, monkeypatch):
    client, _directory = environment
    SimulationRunner._processes['sim_fixture'] = SimpleNamespace(poll=lambda: None)
    sent = []
    def interview(**payload):
        sent.append(payload)
        return {'success': True, 'result': {'response': 'Synthetic answer'}}
    monkeypatch.setattr(SimulationRunner, 'interview_agent', interview)
    response = client.post('/api/simulation/interview', json={'simulation_id': 'sim_fixture', 'agent_id': 0, 'prompt': 'Explicit question'})
    assert response.status_code == 200
    assert len(sent) == 1 and sent[0]['prompt'].endswith('Explicit question')
    assert sent[0]['simulation_id'] == 'sim_fixture' and sent[0]['agent_id'] == 0
