import json
import sqlite3

from app.services.simulation_runner import SimulationRunner


def database(path, rows):
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT, created_at)')
        for agent, answer, timestamp in rows:
            connection.execute('INSERT INTO trace VALUES (?, ?, ?, ?)',
                               (agent, 'interview', json.dumps({'prompt': '問卷', 'response': answer}), timestamp))


def test_dual_platform_history_orders_actual_commands_and_preserves_simulation_clocks(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    folder = tmp_path / 'sim-history'
    folder.mkdir()
    database(folder / 'twitter_simulation.db', [(0, 'Twitter answer', 3)])
    database(folder / 'reddit_simulation.db', [(1, 'Reddit answer', '2026-10-02 05:01:51')])
    responses = folder / 'ipc_responses'
    responses.mkdir()
    for name, result, timestamp in [
        ('single', {'agent_id': 0, 'response': 'Twitter answer', 'timestamp': 3, 'platform': 'twitter'}, '2026-10-02T02:31:46'),
        ('batch', {'results': {'reddit_1': {'agent_id': 1, 'response': 'Reddit answer',
                                          'timestamp': '2026-10-02 05:01:51', 'platform': 'reddit'}}}, '2026-10-02T02:31:50'),
    ]:
        (responses / f'{name}.json').write_text(json.dumps({'status': 'completed', 'result': result, 'timestamp': timestamp}))
    history = SimulationRunner.get_interview_history('sim-history')
    assert [item['response'] for item in history] == ['Reddit answer', 'Twitter answer']
    assert [item['timestamp'] for item in history] == ['2026-10-02T02:31:50', '2026-10-02T02:31:46']
    assert [item['simulation_timestamp'] for item in history] == ['2026-10-02 05:01:51', 3]
    assert all(item['timestamp_source'] == 'interview_command' for item in history)
    assert SimulationRunner.get_interview_history('sim-history', agent_id=0)[0]['response'] == 'Twitter answer'
    assert len(SimulationRunner.get_interview_history('sim-history', limit=1)) == 1


def test_legacy_mixed_platform_times_remain_readable_without_fabricated_epoch_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    folder = tmp_path / 'sim-legacy'
    folder.mkdir()
    database(folder / 'twitter_simulation.db', [(0, 'Older tick', 3), (0, 'Newer tick', 4)])
    database(folder / 'reddit_simulation.db', [(1, 'Dated answer', '2026-10-02 05:01:51')])
    history = SimulationRunner.get_interview_history('sim-legacy')
    assert len(history) == 3 and {item['response'] for item in history} == {'Older tick', 'Newer tick', 'Dated answer'}
    twitter = SimulationRunner.get_interview_history('sim-legacy', platform='twitter')
    assert [item['timestamp'] for item in twitter] == [4, 3]
    assert all(item['timestamp_source'] == 'simulation' and 'simulation_timestamp' not in item for item in history)


def test_incomplete_and_failed_receipts_do_not_hide_saved_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(tmp_path))
    folder = tmp_path / 'sim-partial'
    folder.mkdir()
    database(folder / 'twitter_simulation.db', [(0, 'Saved answer', 3)])
    responses = folder / 'ipc_responses'
    responses.mkdir()
    (responses / 'partial.json').write_text('{')
    (responses / 'legacy-list.json').write_text('[]')
    (responses / 'failed.json').write_text(json.dumps({'status': 'failed', 'timestamp': '2026-10-02T02:32:00',
        'result': {'agent_id': 0, 'platform': 'twitter', 'timestamp': 3, 'response': 'Saved answer'}}))
    result = SimulationRunner.get_interview_history('sim-partial')
    assert result[0]['response'] == 'Saved answer' and result[0]['timestamp'] == 3
