"""Saved event navigation and disabled plans never start external work."""
import pytest
from test_research_workbench import workbench
from app.models.execution import RunStore
from app.services.event_store import EventStore


def test_event_reference_resolves_exact_project_run_and_sequence(workbench, monkeypatch):
    service, client, _ = workbench
    pid = service.create('事件定位')['project_id']
    other = service.create('另一研究')['project_id']
    run, _ = RunStore.claim('sim_navigation', {'project_id': pid})
    event = EventStore.append('sim_navigation', {'kind': 'post', 'content': '已保存事件'})
    def forbidden(*args, **kwargs):
        raise AssertionError('Reference lookup must not ingest or execute work')
    monkeypatch.setattr(EventStore, 'ingest', forbidden)
    suffix = f"/events/{event['event_id']}?run_id={run['run_id']}"
    response = client.get(f'/api/workbench/projects/{pid}{suffix}')
    assert response.status_code == 200
    assert response.json['data']['seq'] == 1
    assert response.json['data']['simulation_id'] == 'sim_navigation'
    assert client.get(f'/api/workbench/projects/{other}{suffix}').status_code == 404
    assert client.get(f"/api/workbench/projects/{pid}/events/{event['event_id']}?run_id=missing").status_code == 404


@pytest.mark.parametrize('definition', [
    {'repeat_count': 6}, {'repeat_count': True}, {'timezone': 'invalid/timezone'},
    {'budget': {'max_attempts': 4}}, {'budget': {'max_model_calls': 1}},
    {'model_profile_ids': ['missing']}, {'frequency': 'everysecond'},
])
def test_disabled_plan_rejects_unbounded_or_unknown_inputs(workbench, definition):
    service, client, headers = workbench
    pid = service.create('停用計畫')['project_id']
    response = client.post(f'/api/workbench/projects/{pid}/plans', headers=headers,
                           json={'kind': 'sensitivity', 'definition': {'enabled': False, **definition}})
    assert response.status_code == 400
    assert service.plans(pid)['items'] == []


def test_plan_freezes_public_profile_and_source_versions(workbench, monkeypatch):
    from app import provider_settings
    service, _, _ = workbench
    pid = service.create('配置快照')['project_id']
    source = service.save_source(pid, title='來源', content='VERSION-ONE', identity='same')
    profile = {'id': 'profile_fixture', 'name': '本機', 'model': 'first',
               'provider': 'custom', 'base_url': 'http://localhost:9999/v1', 'api_key': 'PRIVATE-KEY'}
    monkeypatch.setattr(provider_settings, 'profiles_config', lambda: {'profiles': [profile]})
    service.plans(pid, 'sensitivity', {'enabled': False, 'repeat_count': 3, 'model_profile_ids': [profile['id']]})
    profile['model'] = 'changed'
    service.save_source(pid, title='來源', content='VERSION-TWO', identity='same')
    plan = service.plans(pid)['items'][0]
    assert plan['next_execution'] is None and plan['enabled'] is False
    assert plan['definition']['model_snapshots'][0]['model'] == 'first'
    assert 'api_key' not in plan['definition']['model_snapshots'][0]
    assert plan['definition']['source_versions'][0]['version_id'] == source['version']['version_id']
    assert plan['definition']['budget']['max_model_calls'] == 0
