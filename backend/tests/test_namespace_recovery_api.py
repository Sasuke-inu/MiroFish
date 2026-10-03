"""Explicit local-only graph-copy reconciliation never launches paid work."""
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_cors import CORS

from app.api import simulation as module
from app.api.settings import csrf_token


@pytest.fixture
def recovery_api(monkeypatch, tmp_path):
    app = Flask(__name__)
    CORS(app, resources={r'/api/*': {'origins': '*'}})
    app.register_blueprint(module.simulation_bp, url_prefix='/api/simulation')
    monkeypatch.setattr(module.SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    calls = []
    state = SimpleNamespace(to_dict=lambda: {'simulation_id': 'sim_fixture', 'graph_id': 'run_fixture',
        'source_graph_id': 'source_fixture', 'graph_namespace_status': 'ready', 'status': 'created',
        'simulation_model_snapshot': {'model': 'fixture', 'api_key': 'should-never-return'}})
    manager = SimpleNamespace(get_simulation=lambda *_: state,
                              recover_namespace=lambda identity: calls.append(identity) or state)
    monkeypatch.setattr(module, 'SimulationManager', lambda: manager)
    monkeypatch.setattr(module.SimulationRunner, 'start_simulation', lambda *_a, **_kw: pytest.fail('recovery started a run'))
    manager.prepare_simulation = lambda *_a, **_kw: pytest.fail('recovery prepared a run')
    with app.app_context():
        token = csrf_token()
    return app.test_client(), manager, calls, {'X-MiroFish-CSRF': token, 'Origin': 'http://localhost:3100'}


def test_valid_recovery_only_reconciles_copy_and_returns_private_response(recovery_api):
    client, _, calls, headers = recovery_api
    response = client.post('/api/simulation/sim_fixture/recover-namespace', json={}, headers=headers)
    assert response.status_code == 200
    assert calls == ['sim_fixture']
    assert response.json['data']['graph_namespace_status'] == 'ready'
    assert response.json['execution_started'] is False and response.json['preparation_started'] is False
    assert 'should-never-return' not in response.get_data(as_text=True)
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'Access-Control-Allow-Origin' not in response.headers


@pytest.mark.parametrize('damage', ['csrf', 'origin', 'host', 'cross_site'])
def test_recovery_reuses_local_write_guards_before_manager_call(recovery_api, damage):
    client, _, calls, headers = recovery_api
    options = {}
    if damage == 'csrf':
        headers.pop('X-MiroFish-CSRF')
    elif damage == 'origin':
        headers['Origin'] = 'https://external.invalid'
    elif damage == 'host':
        options['base_url'] = 'http://external.invalid'
    else:
        headers['Sec-Fetch-Site'] = 'cross-site'
    response = client.post('/api/simulation/sim_fixture/recover-namespace', json={}, headers=headers, **options)
    assert response.status_code == 403
    assert calls == []
    assert 'Access-Control-Allow-Origin' not in response.headers


@pytest.mark.parametrize('body', [{'force': True}, {'start': True}, [], None])
def test_recovery_has_no_force_or_start_options(recovery_api, body):
    client, _, calls, headers = recovery_api
    response = client.post('/api/simulation/sim_fixture/recover-namespace', json=body, headers=headers)
    assert response.status_code in {400, 413, 415}
    assert not calls


def test_reading_recovery_url_cannot_modify_state(recovery_api):
    client, _, calls, headers = recovery_api
    assert client.get('/api/simulation/sim_fixture/recover-namespace', headers=headers).status_code == 405
    assert not calls


def test_missing_and_invalid_identity_cannot_recover(recovery_api):
    client, manager, calls, headers = recovery_api
    manager.get_simulation = lambda *_: None
    assert client.post('/api/simulation/sim_missing/recover-namespace', json={}, headers=headers).status_code == 404
    assert client.post('/api/simulation/sim.bad/recover-namespace', json={}, headers=headers).status_code == 400
    assert not calls


@pytest.mark.parametrize('error,status', [(ValueError('原模型連線已變更'), 409), (RuntimeError('private-provider-body'), 502)])
def test_unresolved_recovery_keeps_failure_and_never_returns_provider_details(recovery_api, error, status):
    client, manager, _, headers = recovery_api
    manager.recover_namespace = lambda *_: (_ for _ in ()).throw(error)
    response = client.post('/api/simulation/sim_fixture/recover-namespace', json={}, headers=headers)
    assert response.status_code == status
    assert response.json['success'] is False
    assert 'private-provider-body' not in response.get_data(as_text=True)
