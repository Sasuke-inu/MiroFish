import pytest

from app.config import Config
from app.models.execution import RunStore
from app.services.event_store import EventStore


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))


def saved(simulation_id, model='model_a', kind='real', scenario='same', counts=None, **overrides):
    manifest = {'project_id': 'project_fixture', 'kind': kind,
                'model': {'provider': 'fixture', 'base_url': 'https://fixture.invalid/v1', 'model': model},
                'source_versions': [{'source_id': 'source_fixture', 'version_id': 'version_fixture', 'sha256': 'source_hash'}],
                'source_lineage_status': 'graph_build_snapshot', 'roles': [{'platform': 'reddit', 'sha256': 'role_hash', 'count': 2}],
                'roles_snapshot_status': 'complete', 'configuration_comparison_sha256': 'config_hash_' + scenario,
                'configuration': {'simulation_id': simulation_id, 'graph_id': 'graph_' + simulation_id, 'llm_model': model,
                                  'scenario': scenario},
                'graph_id': 'graph_' + simulation_id, 'model_frozen_at': simulation_id, **overrides}
    row, _ = RunStore.claim(simulation_id, manifest)
    for event_kind, count in (counts or {'post': 1}).items():
        for index in range(count):
            EventStore.append(simulation_id, {'event_id': f'{event_kind}_{index}', 'platform': 'reddit', 'kind': event_kind, 'content': 'fixture'})
    RunStore.update(simulation_id, 'completed', graph_ready=kind != 'synthetic_fixture')
    return RunStore.get(simulation_id)


def evaluate(rows):
    from app.services.quality_evaluation import QualityEvaluation
    return QualityEvaluation.evaluate(rows)


def test_repeats_count_observed_event_ranges_and_zero_for_absent_kind():
    left = saved('sim_a', counts={'post': 2, 'comment': 1})
    right = saved('sim_b', counts={'post': 4})
    result = evaluate([left, right])['repeat_stability']
    assert result['status'] == 'observed' and result['sample_size'] == 2
    group = result['groups'][0]
    assert set(group['run_ids']) == {left['run_id'], right['run_id']}
    assert group['kind_counts']['reddit']['post']['min'] == 2
    assert group['kind_counts']['reddit']['post']['max'] == 4
    assert group['kind_counts']['reddit']['comment']['min'] == 0
    assert group['kind_counts']['reddit']['comment']['max'] == 1
    assert result['causal_claim'] is False


def test_model_sensitivity_requires_same_other_configuration():
    rows = [saved('sim_a'), saved('sim_b', model='model_b', counts={'post': 3}),
            saved('sim_other', model='model_c', scenario='different')]
    result = evaluate(rows)['model_sensitivity']
    assert result['status'] == 'observed' and result['sample_size'] == 2
    assert set(result['groups'][0]['simulation_ids']) == {'sim_a', 'sim_b'}
    assert result['excluded'][0]['simulation_id'] == 'sim_other'
    assert result['excluded'][0]['reason'] == 'no_matching_samples'
    assert result['groups'][0]['kind_counts']['reddit']['post']['max'] == 3


def test_synthetic_and_real_runs_never_form_a_shared_group():
    result = evaluate([saved('sim_real'), saved('sim_synthetic', kind='synthetic_fixture')])
    for name in ('repeat_stability', 'model_sensitivity'):
        assert result[name]['status'] == 'not_evaluated'
        assert result[name]['sample_size'] == 0
        assert len(result[name]['excluded']) == 2


def test_failed_legacy_and_unknown_inputs_have_explicit_exclusion_reasons():
    failed = saved('sim_failed')
    failed['status'] = 'failed'
    unknown = saved('sim_unknown', roles=[])
    legacy = {'simulation_id': 'sim_legacy', 'run_id': None, 'status': 'completed', 'manifest': {}, 'legacy': True}
    result = evaluate([failed, unknown, legacy])['repeat_stability']
    assert result['status'] == 'not_evaluated'
    reasons = {item['simulation_id']: item['reason'] for item in result['excluded']}
    assert reasons == {'sim_failed': 'status_failed', 'sim_unknown': 'roles_unknown', 'sim_legacy': 'legacy_identity'}
    assert all(item['message'] for item in result['excluded'])


def test_missing_graph_lineage_or_configuration_cannot_be_called_comparable():
    rows = [saved('sim_source', source_lineage_status='unverified'),
            saved('sim_config', configuration_comparison_sha256=None)]
    result = evaluate(rows)['model_sensitivity']
    assert result['status'] == 'not_evaluated'
    assert {item['reason'] for item in result['excluded']} == {'sources_unknown', 'configuration_unknown'}


def test_statistics_use_persisted_events_not_action_content_or_claimed_cost():
    left, right = saved('sim_a'), saved('sim_b')
    before = evaluate([left, right])
    EventStore.append('sim_b', {'kind': 'comment', 'platform': 'reddit', 'content': 'no accuracy score or paid cost'})
    after = evaluate([RunStore.get('sim_a'), RunStore.get('sim_b')])
    assert 'comment' not in before['repeat_stability']['groups'][0]['kind_counts']['reddit']
    assert after['repeat_stability']['groups'][0]['kind_counts']['reddit']['comment']['max'] == 1
    assert after['repeat_stability']['cost']['status'] == 'unknown'
