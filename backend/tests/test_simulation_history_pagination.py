from types import SimpleNamespace
import json

import pytest

from app import create_app
from app.api import simulation
from app.services.report_agent import ReportManager

REAL_REPORT_LOOKUP = simulation._get_report_id_for_simulation


@pytest.fixture
def history_client(monkeypatch, tmp_path):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    records = []
    for index in range(45):
        values = {
            'simulation_id': f'sim_{index:03}',
            'project_id': f'project_{index:03}',
            'created_at': f'2026-10-03T{index // 60:02}:{index % 60:02}:00',
        }
        records.append(SimpleNamespace(**values, to_dict=lambda values=values: dict(values)))
    config_calls = []

    def config(simulation_id):
        config_calls.append(simulation_id)
        return {'simulation_requirement': f'Question for {simulation_id}', 'time_config': {}}

    monkeypatch.setattr(simulation, 'SimulationManager', lambda: SimpleNamespace(
        list_simulations=lambda: records, get_simulation_config=config))
    monkeypatch.setattr(simulation.SimulationRunner, 'get_run_state', lambda _id: None)
    monkeypatch.setattr(simulation.ProjectManager, 'get_project', lambda _id: SimpleNamespace(
        files=[{'filename': f'source-{i}.md'} for i in range(5)]))
    monkeypatch.setattr(simulation, '_get_report_id_for_simulation', lambda _id: f'report_{_id}')
    return create_app().test_client(), config_calls


def test_every_record_is_reachable_in_bounded_newest_first_pages(history_client):
    client, config_calls = history_client
    ids = []
    offset = 0
    for expected_count in [20, 20, 5]:
        response = client.get(f'/api/simulation/history?limit=20&offset={offset}')
        assert response.status_code == 200
        payload = response.json
        assert payload['count'] == expected_count
        assert len(payload['data']) == expected_count
        assert payload['pagination']['total'] == 45
        assert payload['pagination']['offset'] == offset
        ids.extend(row['simulation_id'] for row in payload['data'])
        offset = payload['pagination']['next_offset']
        assert payload['pagination']['has_more'] is (offset < 45)
    assert ids == [f'sim_{index:03}' for index in reversed(range(45))]
    assert len(config_calls) == 45


def test_replay_keeps_all_file_names_and_existing_navigation_identifiers(history_client):
    client, config_calls = history_client
    row = client.get('/api/simulation/history?limit=1').json['data'][0]
    assert row['files'] == [{'filename': f'source-{i}.md'} for i in range(5)]
    assert row['project_id'] == 'project_044'
    assert row['simulation_id'] == 'sim_044'
    assert row['report_id'] == 'report_sim_044'
    assert len(config_calls) == 1


@pytest.mark.parametrize(('query', 'limit', 'offset', 'count'), [
    ('limit=1000000&offset=-20', 100, 0, 45),
    ('limit=0&offset=44', 1, 44, 1),
    ('limit=-2&offset=999', 1, 999, 0),
    ('limit=bad&offset=bad', 20, 0, 20),
])
def test_invalid_page_parameters_stay_bounded(history_client, query, limit, offset, count):
    client, config_calls = history_client
    payload = client.get(f'/api/simulation/history?{query}').json
    assert payload['pagination']['limit'] == limit
    assert payload['pagination']['offset'] == offset
    assert payload['count'] == count
    assert len(config_calls) == count
    if offset >= 45:
        assert payload['pagination']['has_more'] is False


@pytest.mark.parametrize('status', ['completed', 'failed', 'needs_review', None])
def test_history_returns_saved_report_status_without_inference(history_client, status):
    from pathlib import Path
    client, _ = history_client
    if status is not None:
        folder = Path(ReportManager.REPORTS_DIR) / 'report_sim_044'
        folder.mkdir(parents=True)
        (folder / 'meta.json').write_text(json.dumps({'report_id': 'report_sim_044',
            'simulation_id': 'sim_044', 'status': status}), encoding='utf-8')
    row = client.get('/api/simulation/history?limit=1').json['data'][0]
    assert row['report_id'] == 'report_sim_044'
    assert row['report_status'] == status


@pytest.mark.parametrize('metadata', [
    {'report_id': 'report_sim_044', 'simulation_id': 'sim_044'},
    {'report_id': 'report_sim_044', 'simulation_id': 'sim_other', 'status': 'completed'},
    {'report_id': 'report_other', 'simulation_id': 'sim_044', 'status': 'completed'},
    {'report_id': 'report_sim_044', 'simulation_id': 'sim_044', 'status': 'invented'},
])
def test_missing_or_mismatched_report_metadata_is_not_completed(history_client, metadata):
    from pathlib import Path
    client, _ = history_client
    folder = Path(ReportManager.REPORTS_DIR) / 'report_sim_044'
    folder.mkdir(parents=True)
    (folder / 'meta.json').write_text(json.dumps(metadata), encoding='utf-8')
    row = client.get('/api/simulation/history?limit=1').json['data'][0]
    assert row['report_status'] is None


def test_history_uses_latest_saved_report_and_keeps_string_helper_contract(history_client, monkeypatch):
    from pathlib import Path
    client, _ = history_client
    for index, status in [(1, 'completed'), (2, 'failed')]:
        report_id = f'report_version_{index}'
        folder = Path(ReportManager.REPORTS_DIR) / report_id
        folder.mkdir(parents=True)
        (folder / 'meta.json').write_text(json.dumps({'report_id': report_id,
            'simulation_id': 'sim_044', 'created_at': f'2026-10-0{index}', 'status': status}), encoding='utf-8')
    monkeypatch.setattr(simulation, '_get_report_id_for_simulation', REAL_REPORT_LOOKUP)
    assert simulation._get_report_id_for_simulation('sim_044') == 'report_version_2'
    row = client.get('/api/simulation/history?limit=1').json['data'][0]
    assert row['report_id'] == 'report_version_2'
    assert row['report_status'] == 'failed'
