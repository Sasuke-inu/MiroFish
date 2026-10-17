"""R03 follow-up: a completed run that never requested graph updates keeps its interview window.

decouple the interview env gate from graph_ready: only runs that requested a
graph update must wait for its drain; a run with graph_update_status
'not_requested' is completed and interviewable without graph_ready=True.
"""
from datetime import datetime, timezone
import json

from app.services.simulation_ipc import SimulationIPCClient


def write_state(directory, run_state, env_status=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'run_state.json').write_text(json.dumps(run_state, ensure_ascii=False), encoding='utf-8')
    status = env_status if env_status is not None else {
        'status': 'alive', 'run_id': run_state.get('run_id'), 'attempt_id': run_state.get('attempt_id'),
        'timestamp': datetime.now(timezone.utc).isoformat()}
    (directory / 'env_status.json').write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')


def test_not_requested_graph_update_keeps_env_alive(tmp_path):
    write_state(tmp_path / 'sim_noupdate', {
        'runner_status': 'completed', 'graph_ready': False,
        'graph_update_status': 'not_requested', 'run_id': 'run_ok', 'attempt_id': 'attempt_ok'})
    assert SimulationIPCClient(str(tmp_path / 'sim_noupdate')).check_env_alive() is True


def test_failed_graph_update_blocks_env_alive(tmp_path):
    write_state(tmp_path / 'sim_failed', {
        'runner_status': 'completed', 'graph_ready': False,
        'graph_update_status': 'failed', 'run_id': 'run_fail', 'attempt_id': 'attempt_fail'})
    assert SimulationIPCClient(str(tmp_path / 'sim_failed')).check_env_alive() is False


def test_legacy_confirmed_state_still_requires_graph_ready(tmp_path):
    write_state(tmp_path / 'sim_legacy_true', {
        'runner_status': 'completed', 'graph_ready': True, 'run_id': 'run_l', 'attempt_id': 'attempt_l'})
    assert SimulationIPCClient(str(tmp_path / 'sim_legacy_true')).check_env_alive() is True
    write_state(tmp_path / 'sim_legacy_false', {
        'runner_status': 'completed', 'graph_ready': False, 'run_id': 'run_l', 'attempt_id': 'attempt_l'})
    assert SimulationIPCClient(str(tmp_path / 'sim_legacy_false')).check_env_alive() is False


def test_not_requested_still_requires_fresh_matching_env(tmp_path):
    write_state(tmp_path / 'sim_stale', {
        'runner_status': 'completed', 'graph_ready': False,
        'graph_update_status': 'not_requested', 'run_id': 'run_ok', 'attempt_id': 'attempt_ok'},
        env_status={'status': 'stopped', 'run_id': 'run_ok', 'attempt_id': 'attempt_ok',
                    'timestamp': datetime.now(timezone.utc).isoformat()})
    assert SimulationIPCClient(str(tmp_path / 'sim_stale')).check_env_alive() is False
