"""Durable event projections use only local synthetic records."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.models.execution import RunStore


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from app.config import Config
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    return tmp_path / 'simulations'


def service():
    from app.services.event_store import EventStore
    return EventStore


def run(sim='sim_a', **manifest):
    return RunStore.claim(sim, {'model': {'provider': 'fixture', 'model': 'deterministic'},
                               'source_versions': ['version_a'], 'scenario': {'choice': 'a'}, **manifest})[0]


def line(row, **fields):
    return json.dumps({'run_id': row['run_id'], 'attempt_id': row['attempt_id'],
                       'agent_id': 0, 'round': 1, 'action_type': 'CREATE_POST',
                       'action_args': {'content': '第一筆內容'}, **fields}, ensure_ascii=False).encode() + b'\n'


def test_ingestion_is_durable_idempotent_and_does_not_rewrite_source(isolated):
    row = run()
    path = isolated / 'sim_a' / 'reddit' / 'actions.jsonl'
    path.parent.mkdir(parents=True)
    original = line(row) + line(row, agent_id=1, action_type='FOLLOW', action_args={'followee_id': 0})
    path.write_bytes(original)
    assert service().ingest('sim_a')['ingested'] == 2
    first = service().page('sim_a')
    assert service().ingest('sim_a')['ingested'] == 0
    assert service().page('sim_a')['items'] == first['items']
    assert [item['seq'] for item in first['items']] == [1, 2]
    assert all(item['run_id'] == row['run_id'] for item in first['items'])
    assert first['items'][0]['content']['action_args']['content'] == '第一筆內容'
    assert first['capability'] == 'exact_event_projection'
    assert path.read_bytes() == original


def test_partial_line_waits_for_newline_and_wrong_run_is_not_misattributed(isolated):
    row = run()
    path = isolated / 'sim_a' / 'reddit' / 'actions.jsonl'
    path.parent.mkdir(parents=True)
    partial = line(row)[:-1]
    path.write_bytes(partial)
    assert service().page('sim_a')['items'] == []
    with path.open('ab') as handle:
        handle.write(b'\n' + line(row, run_id='old_run'))
    result = service().page('sim_a')
    assert len(result['items']) == 1
    assert result['capability'] == 'event_list'
    assert any('身分' in warning for warning in result['limitations'])


def test_cursor_keeps_position_after_append_and_is_filter_scoped():
    run()
    for index in range(4):
        service().append('sim_a', {'event_id': f'event_{index}', 'platform': 'reddit',
                                  'agent_id': index % 2, 'kind': 'post', 'content': str(index)})
    first = service().page('sim_a', limit=2)
    assert first['has_more'] is True
    service().append('sim_a', {'platform': 'twitter', 'kind': 'post', 'content': 'later'})
    second = service().page('sim_a', cursor=first['next_cursor'], limit=20)
    assert [item['seq'] for item in second['items']] == [3, 4, 5]
    assert second['has_more'] is False
    assert [item['seq'] for item in service().page('sim_a', agent_id='0')['items']] == [1, 3]
    with pytest.raises(ValueError):
        service().page('sim_a', cursor=first['next_cursor'], platform='reddit')
    with pytest.raises(ValueError):
        service().page('sim_a', cursor='not-a-cursor')


def test_append_is_idempotent_but_conflicting_identity_cannot_overwrite():
    run()
    event = {'event_id': 'same_event', 'platform': 'reddit', 'kind': 'post', 'content': 'saved'}
    first = service().append('sim_a', event)
    assert service().append('sim_a', event) == first
    with pytest.raises(ValueError):
        service().append('sim_a', {**event, 'content': 'replacement'})
    assert service().page('sim_a')['items'] == [first]


def test_concurrent_ingestion_assigns_one_stable_sequence(isolated):
    row = run()
    path = isolated / 'sim_a' / 'twitter' / 'actions.jsonl'
    path.parent.mkdir(parents=True)
    path.write_bytes(b''.join(line(row, agent_id=index) for index in range(6)))
    with ThreadPoolExecutor(max_workers=3) as pool:
        counts = list(pool.map(lambda _: service().ingest('sim_a')['ingested'], range(3)))
    assert sum(counts) == 6
    assert [item['seq'] for item in service().page('sim_a')['items']] == list(range(1, 7))


def test_projection_has_no_future_actor_content_or_relationship():
    run()
    service().append('sim_a', {'agent_id': 'a', 'platform': 'reddit', 'kind': 'post', 'content': 'past'})
    service().append('sim_a', {'agent_id': 'b', 'platform': 'reddit', 'kind': 'FOLLOW',
                              'content': {'action_args': {'followee_id': 'a'}}})
    service().append('sim_a', {'agent_id': 'future', 'platform': 'reddit', 'kind': 'post', 'content': 'SECRET_FUTURE'})
    before = service().project('sim_a', 1)
    assert [item['seq'] for item in before['events']] == [1]
    assert before['relationships'] == []
    assert {item['agent_id'] for item in before['actors']} == {'a'}
    assert 'SECRET_FUTURE' not in json.dumps(before)
    after = service().project('sim_a', 2)
    assert len(after['relationships']) == 1
    assert after['relationships'][0]['target_agent_id'] == 'a'
    assert 'future' not in json.dumps(after)
    assert service().project('sim_a', 0)['events'] == []


def test_legacy_events_and_interrupted_tail_have_explicit_limits(isolated):
    path = isolated / 'sim_legacy' / 'reddit' / 'actions.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text('{"action_type":"post","agent_id":1}\n', encoding='utf-8')
    legacy = service().page('sim_legacy')
    assert legacy['capability'] == 'event_list'
    assert legacy['items'][0]['run_id'] is None
    assert legacy['limitations']
    run()
    RunStore.update('sim_a', 'interrupted')
    current = service().page('sim_a')
    assert current['cost']['status'] == 'unknown'
    assert any('尾段' in warning for warning in current['limitations'])


def test_modified_source_never_replaces_preserved_events(isolated):
    row = run()
    path = isolated / 'sim_a' / 'reddit' / 'actions.jsonl'
    path.parent.mkdir(parents=True)
    path.write_bytes(line(row))
    original = service().page('sim_a')['items']
    path.write_bytes(line(row, action_args={'content': 'changed'}))
    result = service().page('sim_a')
    assert result['items'] == original
    assert result['capability'] == 'event_list'
    assert any('變更' in warning for warning in result['limitations'])


def test_compare_requires_completed_and_discloses_model_source_differences():
    run('sim_a')
    run('sim_b', model={'provider': 'fixture', 'model': 'different'}, source_versions=['version_b'])
    for sim, value in [('sim_a', 'original'), ('sim_b', 'changed')]:
        service().append(sim, {'platform': 'reddit', 'kind': 'post', 'content': value})
    with pytest.raises(ValueError):
        service().compare('sim_a', 'sim_b')
    RunStore.update('sim_a', 'completed')
    RunStore.update('sim_b', 'completed')
    result = service().compare('sim_a', 'sim_b')
    assert result['non_single_variable'] is True
    assert {item['path'] for item in result['manifest_diff']} == {'model.model', 'source_versions'}
    assert result['kind_counts']['left']['reddit']['post'] == 1
    assert result['first_difference']['left']['seq'] == 1
    assert result['cost']['status'] == 'unknown'


def test_compare_one_scenario_change_never_claims_causal_proof():
    run('sim_a')
    run('sim_b', scenario={'choice': 'b'})
    for sim in ('sim_a', 'sim_b'):
        service().append(sim, {'kind': 'post', 'content': 'same'})
        RunStore.update(sim, 'completed')
    result = service().compare('sim_a', 'sim_b')
    assert result['non_single_variable'] is False
    assert result['first_difference'] is None
    assert result['causal_claim'] is False


def test_identity_validation_and_structured_secrets_are_not_exposed():
    run()
    with pytest.raises(ValueError):
        service().ingest('../escape')
    event = service().append('sim_a', {'kind': 'post', 'content': {'content': 'visible', 'api_key': 'PRIVATE_VALUE'}})
    assert event['content']['content'] == 'visible'
    assert 'PRIVATE_VALUE' not in json.dumps(event)


def test_projection_applies_only_successful_recorded_relationship_changes():
    run()
    relation = {'agent_id': 'a', 'platform': 'reddit', 'content': {'action_args': {'followee_id': 'b'}}}
    service().append('sim_a', {**relation, 'kind': 'FOLLOW'})
    service().append('sim_a', {**relation, 'kind': 'UNFOLLOW', 'content': {'action_args': {'followee_id': 'b'}, 'success': False}})
    service().append('sim_a', {**relation, 'kind': 'UNFOLLOW'})
    assert len(service().project('sim_a', 2)['relationships']) == 1
    assert service().project('sim_a', 3)['relationships'] == []


def test_event_evidence_resolves_only_the_saved_run_and_rejects_timestamp_rewrite():
    row = run()
    raw = {'event_id': 'saved', 'kind': 'post', 'observed_at': '2026-01-01T00:00:00+00:00', 'content': 'fixture'}
    event = service().append('sim_a', raw)
    assert service().get_event(row['run_id'], 'saved') == event
    assert service().get_event('wrong_run', 'saved') is None
    with pytest.raises(ValueError):
        service().append('sim_a', {**raw, 'observed_at': '2026-01-02T00:00:00+00:00'})


def test_recorded_wall_clock_differences_are_not_simulation_content_differences(isolated):
    for sim, timestamp in [('sim_a', '2026-01-01'), ('sim_b', '2026-01-02')]:
        row = run(sim)
        path = isolated / sim / 'reddit' / 'actions.jsonl'
        path.parent.mkdir(parents=True)
        path.write_bytes(line(row, timestamp=timestamp))
        RunStore.update(sim, 'completed')
    assert service().compare('sim_a', 'sim_b')['first_difference'] is None


def test_projection_reduces_all_events_but_returns_only_last_200():
    run(project_id='project_fixture')
    for index in range(205):
        service().append('sim_a', {'agent_id': 'a', 'kind': 'post', 'content': str(index)})
    projection = service().project('sim_a', 203)
    assert projection['event_count'] == 203
    assert projection['events_truncated'] is True
    assert [event['seq'] for event in projection['events']] == list(range(4, 204))
    assert projection['actors'][0]['actions_count'] == 203
    event = projection['events'][0]
    assert service().get_event(event['run_id'], event['event_id'])['project_id'] == 'project_fixture'
