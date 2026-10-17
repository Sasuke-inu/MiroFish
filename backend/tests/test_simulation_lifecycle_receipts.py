"""R02/R03/R07/R15 lifecycle receipts, log cursor and simulated hours.

Producer functions are exercised through AST isolation (no OASIS import) with
stub environments; runner paths use in-memory state and tmp_path logs.
"""
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from app.services.simulation_runner import SimulationRunner, SimulationRunState, RunnerStatus
from app.services import simulation_runner as module


BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / 'scripts'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    for field in ('_run_states', '_processes', '_graph_memory_enabled', '_action_queues'):
        monkeypatch.setattr(SimulationRunner, field, {})
    monkeypatch.setattr(SimulationRunner, '_manual_stop_requests', set())
    monkeypatch.setattr(SimulationRunner, '_sync_simulation_status', classmethod(lambda *_: None))
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda *_: None))


def load_function(filename, name, **context):
    tree = ast.parse((SCRIPTS / filename).read_text(encoding='utf-8'))
    function = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    isolated_module = ast.Module(body=[function], type_ignores=[])
    namespace = dict(Any=Any, Dict=Dict, List=List, Optional=Optional, Tuple=Tuple, **context)
    exec(compile(isolated_module, filename, 'exec'), namespace)
    return namespace


def load_action_logger():
    spec = importlib.util.spec_from_file_location('fixture_action_logger', SCRIPTS / 'action_logger.py')
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    return producer


class PlatformSimulation:
    def __init__(self):
        self.env = None
        self.agent_graph = None
        self.total_actions = 0


class StubEnv:
    def __init__(self):
        self.steps = 0

    async def reset(self):
        pass

    async def step(self, actions):
        self.steps += 1


class StubAgentGraph:
    def get_agents(self):
        return []

    def get_agent(self, agent_id):
        raise KeyError(agent_id)


def run_producer_platform(tmp_path, monkeypatch, platform, *, total_simulation_hours=5, minutes_per_round=30,
                          max_rounds=None, stop_after_rounds=None):
    """Run one platform producer loop with a stub environment.

    stop_after_rounds=None -> natural completion; 0 -> shutdown before round 1;
    N>0 -> shutdown event set during round N (that round still completes).
    """
    monkeypatch.setenv('MIROFISH_RUN_ID', 'run_fixture')
    monkeypatch.setenv('MIROFISH_ATTEMPT_ID', 'attempt_fixture')
    producer = load_action_logger()
    if platform == 'twitter':
        (tmp_path / 'twitter_profiles.csv').write_text('user_id,name\n0,Fixture\n', encoding='utf-8')
        function_name, graph_name, actions_name, env_key = (
            'run_twitter_simulation', 'generate_twitter_agent_graph', 'TWITTER_ACTIONS', 'TWITTER')
    else:
        (tmp_path / 'reddit_profiles.json').write_text('[]', encoding='utf-8')
        function_name, graph_name, actions_name, env_key = (
            'run_reddit_simulation', 'generate_reddit_agent_graph', 'REDDIT_ACTIONS', 'REDDIT')
    shutdown = asyncio.Event()
    rounds_seen = {'count': 0}

    if stop_after_rounds == 0:
        shutdown.set()

    def active_agents(env, config, simulated_hour, round_num):
        rounds_seen['count'] += 1
        if stop_after_rounds is not None and stop_after_rounds > 0 and rounds_seen['count'] >= stop_after_rounds:
            shutdown.set()
        return []

    async def graph_stub(**_kwargs):
        return StubAgentGraph()

    namespace = load_function(
        'run_parallel_simulation.py', function_name,
        os=__import__('os'), datetime=__import__('datetime').datetime,
        PlatformSimulation=PlatformSimulation,
        create_model=lambda config, **kwargs: None,
        get_agent_names_from_config=lambda config: {},
        get_active_agents_for_round=active_agents,
        fetch_new_actions_from_db=lambda db_path, last_rowid, agent_names: ([], last_rowid),
        oasis=SimpleNamespace(make=lambda **kwargs: StubEnv(),
                              DefaultPlatformType=SimpleNamespace(TWITTER='twitter', REDDIT='reddit')),
        ManualAction=lambda **kwargs: kwargs, LLMAction=lambda **kwargs: kwargs,
        ActionType=SimpleNamespace(CREATE_POST='CREATE_POST'),
        _shutdown_event=shutdown,
        PlatformActionLogger=producer.PlatformActionLogger,
        SimulationLogManager=producer.SimulationLogManager,
        **{graph_name: graph_stub, actions_name: []})
    producer_function = namespace[function_name]
    logger = producer.PlatformActionLogger(platform, str(tmp_path))
    config = {'time_config': {'total_simulation_hours': total_simulation_hours,
                              'minutes_per_round': minutes_per_round}, 'event_config': {}}
    asyncio.run(producer_function(config, str(tmp_path), action_logger=logger, max_rounds=max_rounds))
    events = [json.loads(line) for line in
              (tmp_path / platform / 'actions.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return events, rounds_seen['count']


def test_r02_stopped_platform_receipt_reports_actual_rounds(tmp_path, monkeypatch):
    events, executed = run_producer_platform(tmp_path, monkeypatch, 'twitter', stop_after_rounds=3)
    receipt = next(e for e in events if e.get('event_type') == 'simulation_end')
    assert executed == 3
    assert receipt['exit_reason'] == 'stopped'
    assert receipt['total_rounds'] == 3
    assert receipt['planned_rounds'] == 10


def test_r02_early_shutdown_before_first_round_is_stopped_with_zero_rounds(tmp_path, monkeypatch):
    for platform in ('twitter', 'reddit'):
        events, executed = run_producer_platform(tmp_path, monkeypatch, platform, stop_after_rounds=0)
        receipt = next(e for e in events if e.get('event_type') == 'simulation_end')
        assert executed == 0
        assert receipt['exit_reason'] == 'stopped'
        assert receipt['total_rounds'] == 0
        assert receipt['planned_rounds'] == 10


def test_r02_natural_completion_reports_completed_and_planned_equals_actual(tmp_path, monkeypatch):
    events, executed = run_producer_platform(tmp_path, monkeypatch, 'reddit')
    receipt = next(e for e in events if e.get('event_type') == 'simulation_end')
    assert executed == 10
    assert receipt['exit_reason'] == 'completed'
    assert receipt['total_rounds'] == 10
    assert receipt['planned_rounds'] == 10


def test_r02_runner_ignores_stopped_receipt(tmp_path):
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a',
                                'exit_reason': 'stopped', 'total_rounds': 3, 'planned_rounds': 10}) + '\n',
                    encoding='utf-8')
    state = SimulationRunState('sim_stopped', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_completed is False
    assert state.reddit_running is False
    assert SimulationRunner._check_all_platforms_completed(state) is False


def test_r02_runner_requires_actual_rounds_to_match_plan(tmp_path):
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a',
                                'exit_reason': 'completed', 'total_rounds': 9, 'planned_rounds': 10}) + '\n',
                    encoding='utf-8')
    state = SimulationRunState('sim_short', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_completed is False


def test_r02_runner_accepts_completed_receipt_with_matching_rounds(tmp_path):
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a',
                                'exit_reason': 'completed', 'total_rounds': 10, 'planned_rounds': 10}) + '\n',
                    encoding='utf-8')
    state = SimulationRunState('sim_done', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_completed is True


def test_r02_runner_still_accepts_legacy_receipt_without_new_fields(tmp_path):
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'total_rounds': 1, 'total_actions': 0}) + '\n',
                    encoding='utf-8')
    state = SimulationRunState('sim_legacy_receipt', enabled_platforms=['twitter'])
    SimulationRunner._read_action_log(str(path), 0, state, 'twitter')
    assert state.twitter_completed is True


def test_r02_zero_exit_with_stopped_receipt_cannot_complete(tmp_path, monkeypatch):
    directory = tmp_path / 'sim_sigterm' / 'reddit'
    directory.mkdir(parents=True)
    (directory / 'actions.jsonl').write_text(json.dumps(
        {'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a', 'exit_reason': 'stopped',
         'total_rounds': 0, 'planned_rounds': 10}) + '\n', encoding='utf-8')
    state = SimulationRunState('sim_sigterm', run_id='r', attempt_id='a', enabled_platforms=['reddit'],
                               runner_status=RunnerStatus.RUNNING, reddit_running=True)
    monkeypatch.setattr(SimulationRunner, 'get_run_state', classmethod(lambda *_: state))
    SimulationRunner._processes['sim_sigterm'] = SimpleNamespace(poll=lambda: 0, returncode=0)
    SimulationRunner._monitor_simulation('sim_sigterm')
    assert state.runner_status == RunnerStatus.FAILED
    assert state.graph_ready is False


def test_r02_natural_receipt_completes_without_graph_claim(tmp_path, monkeypatch):
    directory = tmp_path / 'sim_natural' / 'reddit'
    directory.mkdir(parents=True)
    (directory / 'actions.jsonl').write_text(json.dumps(
        {'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a', 'exit_reason': 'completed',
         'total_rounds': 10, 'planned_rounds': 10}) + '\n', encoding='utf-8')
    state = SimulationRunState('sim_natural', run_id='r', attempt_id='a', enabled_platforms=['reddit'],
                               runner_status=RunnerStatus.RUNNING, reddit_running=True)
    monkeypatch.setattr(SimulationRunner, 'get_run_state', classmethod(lambda *_: state))
    SimulationRunner._processes['sim_natural'] = SimpleNamespace(poll=lambda: 0, returncode=0)
    SimulationRunner._monitor_simulation('sim_natural')
    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.graph_ready is False
    assert state.graph_update_status == 'not_requested'


def test_r03_updater_disabled_keeps_graph_not_ready(monkeypatch):
    state = SimulationRunState('sim_no_updater', run_id='r', attempt_id='a',
                               enabled_platforms=['reddit'], reddit_completed=True,
                               runner_status=RunnerStatus.RUNNING)
    SimulationRunner._finish_run(state, RunnerStatus.COMPLETED)
    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.graph_ready is False
    assert state.graph_update_status == 'not_requested'
    assert state.to_dict()['graph_ready'] is False


def test_r03_updater_success_marks_graph_confirmed(monkeypatch):
    state = SimulationRunState('sim_ok', run_id='r', attempt_id='a',
                               enabled_platforms=['reddit'], reddit_completed=True,
                               runner_status=RunnerStatus.RUNNING)
    SimulationRunner._graph_memory_enabled['sim_ok'] = True
    monkeypatch.setattr(module.ZepGraphMemoryManager, 'stop_updater', classmethod(lambda *_: None))
    SimulationRunner._finish_run(state, RunnerStatus.COMPLETED)
    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.graph_ready is True
    assert state.graph_update_status == 'confirmed'


def test_r03_updater_failure_marks_graph_failed(monkeypatch):
    state = SimulationRunState('sim_bad', run_id='r', attempt_id='a',
                               enabled_platforms=['reddit'], reddit_completed=True,
                               runner_status=RunnerStatus.RUNNING)
    SimulationRunner._graph_memory_enabled['sim_bad'] = True

    def fail(*_):
        raise TimeoutError('fixture')

    monkeypatch.setattr(module.ZepGraphMemoryManager, 'stop_updater', fail)
    SimulationRunner._finish_run(state, RunnerStatus.COMPLETED)
    assert state.runner_status == RunnerStatus.FAILED
    assert state.graph_ready is False
    assert state.graph_update_status == 'failed'


def test_r03_legacy_state_has_no_graph_update_status_key():
    legacy = SimulationRunState('sim_legacy', run_id='r', attempt_id='a', runner_status=RunnerStatus.COMPLETED)
    assert 'graph_update_status' not in legacy.to_dict()


def test_r07_partial_trailing_line_is_ingested_once_when_completed(tmp_path):
    path = tmp_path / 'actions.jsonl'
    complete = json.dumps({'round': 1, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 0,
                           'agent_name': 'A', 'action_type': 'post', 'action_args': {}}) + '\n'
    partial = json.dumps({'round': 2, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 1,
                          'agent_name': 'B', 'action_type': 'post', 'action_args': {}})
    path.write_bytes((complete + partial[:20]).encode('utf-8'))
    state = SimulationRunState('sim_partial', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    position = SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_actions_count == 1
    assert position == len(complete.encode('utf-8'))
    with open(path, 'ab') as handle:
        handle.write((partial[20:] + '\n').encode('utf-8'))
    SimulationRunner._read_action_log(str(path), position, state, 'reddit')
    assert state.reddit_actions_count == 2
    assert [a.agent_name for a in state.recent_actions] == ['B', 'A']


def test_r07_utf8_split_inside_multibyte_character_is_recovered(tmp_path):
    path = tmp_path / 'actions.jsonl'
    line = json.dumps({'round': 1, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 0,
                       'agent_name': '中文字元', 'action_type': 'post', 'action_args': {}}, ensure_ascii=False) + '\n'
    encoded = line.encode('utf-8')
    cut = encoded.index('中'.encode('utf-8')) + 1  # inside the first multi-byte code point
    path.write_bytes(encoded[:cut])
    state = SimulationRunState('sim_utf8', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    position = SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert position == 0
    assert state.reddit_actions_count == 0
    assert state.log_gaps == []
    with open(path, 'ab') as handle:
        handle.write(encoded[cut:])
    SimulationRunner._read_action_log(str(path), position, state, 'reddit')
    assert state.reddit_actions_count == 1
    assert state.log_gaps == []


def test_r07_corrupt_complete_line_records_visible_gap_and_advances(tmp_path, caplog):
    path = tmp_path / 'actions.jsonl'
    good = json.dumps({'round': 1, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 0,
                       'agent_name': 'A', 'action_type': 'post', 'action_args': {}}) + '\n'
    corrupt = '{"round": 2, "run_id": "r" BROKEN}\n'
    path.write_bytes((good + corrupt).encode('utf-8'))
    state = SimulationRunState('sim_gap', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    position = SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert position == len((good + corrupt).encode('utf-8'))
    assert state.reddit_actions_count == 1
    assert len(state.log_gaps) == 1
    gap = state.log_gaps[0]
    assert gap['platform'] == 'reddit'
    assert gap['offset'] == len(good.encode('utf-8'))
    assert gap['reason']
    assert state.to_dict()['log_gaps'] == [gap]


def test_r15_producer_reports_cumulative_simulated_hours(tmp_path, monkeypatch):
    events, executed = run_producer_platform(tmp_path, monkeypatch, 'reddit', minutes_per_round=45,
                                             total_simulation_hours=3)
    round_ends = [e for e in events if e.get('event_type') == 'round_end']
    assert executed == 4
    assert round_ends[0]['simulated_hours'] == 0
    assert [e['simulated_hours'] for e in round_ends] == [0, 0.75, 1.5, 2.25, 3.0]


def test_r15_producer_truncated_run_counts_only_executed_rounds(tmp_path, monkeypatch):
    events, executed = run_producer_platform(tmp_path, monkeypatch, 'twitter', max_rounds=4)
    round_ends = [e for e in events if e.get('event_type') == 'round_end']
    assert executed == 4
    assert round_ends[-1]['simulated_hours'] == 2.0


def test_r15_runner_updates_hours_only_when_present_and_numeric(tmp_path):
    path = tmp_path / 'actions.jsonl'
    events = [
        {'event_type': 'round_end', 'round': 1, 'run_id': 'r', 'attempt_id': 'a', 'simulated_hours': 0.5},
        {'event_type': 'round_end', 'round': 2, 'run_id': 'r', 'attempt_id': 'a', 'simulated_hours': 1.0},
        {'event_type': 'round_end', 'round': 3, 'run_id': 'r', 'attempt_id': 'a'},
        {'event_type': 'round_end', 'round': 4, 'run_id': 'r', 'attempt_id': 'a', 'simulated_hours': 'bad'},
    ]
    path.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')
    state = SimulationRunState('sim_hours', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_simulated_hours == 1.0
    assert state.simulated_hours == 1.0
    assert state.reddit_current_round == 4


def test_r02_receipt_with_reason_requires_valid_rounds(tmp_path):
    """A receipt carrying exit_reason must prove rounds; a missing plan is not a proof."""
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a',
                                'exit_reason': 'completed', 'total_rounds': 10}) + '\n', encoding='utf-8')
    state = SimulationRunState('sim_reason_no_plan', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_completed is False


def test_r02_null_fields_do_not_count_as_legacy_receipt(tmp_path):
    """Legacy is decided by absent keys, not by null values."""
    path = tmp_path / 'actions.jsonl'
    path.write_text(json.dumps({'event_type': 'simulation_end', 'run_id': 'r', 'attempt_id': 'a',
                                'exit_reason': None, 'planned_rounds': None, 'total_rounds': 10}) + '\n',
                    encoding='utf-8')
    state = SimulationRunState('sim_null_receipt', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert state.reddit_completed is False


def test_r07_non_object_line_records_gap_and_keeps_reading(tmp_path):
    path = tmp_path / 'actions.jsonl'
    good = json.dumps({'round': 1, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 0,
                       'agent_name': 'A', 'action_type': 'post', 'action_args': {}}) + '\n'
    path.write_bytes(('null\n' + good).encode('utf-8'))
    state = SimulationRunState('sim_obj_gap', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    position = SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert position == path.stat().st_size
    assert state.reddit_actions_count == 1
    assert len(state.log_gaps) == 1 and state.log_gaps[0]['reason'] == 'not_a_json_object'


def test_r07_processing_failure_records_gap_and_next_line_still_ingested(tmp_path, monkeypatch):
    path = tmp_path / 'actions.jsonl'
    first = json.dumps({'round': 1, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 0,
                        'agent_name': 'A', 'action_type': 'post', 'action_args': {}}) + '\n'
    second = json.dumps({'round': 2, 'run_id': 'r', 'attempt_id': 'a', 'agent_id': 1,
                         'agent_name': 'B', 'action_type': 'post', 'action_args': {}}) + '\n'
    path.write_bytes((first + second).encode('utf-8'))

    class FailingUpdater:
        def add_activity_from_dict(self, data, platform):
            if data.get('agent_id') == 0:
                raise RuntimeError('dispatch down')

    state = SimulationRunState('sim_dispatch_gap', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    SimulationRunner._graph_memory_enabled['sim_dispatch_gap'] = True
    monkeypatch.setattr(module.ZepGraphMemoryManager, 'get_updater', classmethod(lambda *_: FailingUpdater()))
    position = SimulationRunner._read_action_log(str(path), 0, state, 'reddit')
    assert position == path.stat().st_size
    assert state.reddit_actions_count == 2
    assert len(state.log_gaps) == 1
    assert state.log_gaps[0]['reason'].startswith('processing_error:')
