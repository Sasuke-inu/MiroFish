"""R07 follow-up: every unparseable complete line must land in log_gaps before the cursor moves.

json.loads can raise beyond JSONDecodeError for some payloads - integer
strings over the interpreter digit limit raise ValueError, and very deep
nesting raises RecursionError. Those lines must follow the same contract as
other corrupt lines: record a visible gap, then consume the line. Never a
silent skip with the cursor already past the line.
"""
import json

import pytest

from app.services.simulation_runner import SimulationRunner, SimulationRunState


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(SimulationRunner, '_graph_memory_enabled', {})


def test_oversized_integer_line_becomes_gap_and_later_lines_are_ingested(tmp_path):
    path = tmp_path / 'actions.jsonl'
    first = json.dumps({'run_id': 'r', 'attempt_id': 'a', 'round': 1, 'agent_id': 0,
                        'agent_name': 'A', 'action_type': 'post', 'action_args': {}})
    poisoned = '{"run_id": "r", "attempt_id": "a", "round": ' + '9' * 5000 + '}'
    last = json.dumps({'run_id': 'r', 'attempt_id': 'a', 'round': 2, 'agent_id': 1,
                       'agent_name': 'B', 'action_type': 'post', 'action_args': {}})
    path.write_bytes((first + '\n' + poisoned + '\n' + last + '\n').encode('utf-8'))

    state = SimulationRunState('sim_gap', run_id='r', attempt_id='a', enabled_platforms=['reddit'])
    position = SimulationRunner._read_action_log(str(path), 0, state, 'reddit')

    assert position == path.stat().st_size
    assert len(state.log_gaps) == 1
    assert state.log_gaps[0]['reason'] == 'json_decode_error'
    assert state.log_gaps[0]['offset'] == len(first.encode('utf-8')) + 1
    # 缺口之後的完整行仍要被處理：尾段不得整段消失。
    assert state.reddit_actions_count == 2
    assert [a.agent_name for a in state.recent_actions] == ['B', 'A']
    assert state.current_round == 2
