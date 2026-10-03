import json
import pytest
from app import provider_settings as providers
from app.config import Config


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.delenv('MIROFISH_MODEL_SNAPSHOT', raising=False)
    return {'UPLOAD_FOLDER': str(tmp_path), 'LLM_BASE_URL': 'https://example.test/v1',
            'LLM_API_KEY': 'fixture-private-key', 'LLM_MODEL_NAME': 'original'}


def test_additive_migration_keeps_default_and_stage_snapshot(settings):
    initial = providers.get_model_settings(settings)
    assert not providers.settings_path(settings).exists()
    result = providers.save_profile({'name': '報告模型', 'from_default': True}, settings)
    profile_id = result['profiles'][0]['id']
    assert 'fixture-private-key' not in json.dumps(result)
    assert result['schema_version'] == 2
    providers.assign_profiles({'report': profile_id}, settings)
    snapshot = providers.get_model_settings(settings, stage='report')
    providers.save_settings({'model': 'next-default'}, settings)
    assert providers.get_model_settings(settings)['model'] == 'next-default'
    assert providers.get_model_settings(settings, stage='report')['model'] == 'original'
    with providers.model_settings_snapshot(snapshot):
        assert providers.get_model_settings(settings, stage='graph')['model'] == 'original'
    assert providers.profiles_config(settings)['assignments']['report'] == profile_id
    assert initial['api_key'] == snapshot['api_key']


def test_profile_removal_drops_key_and_requires_unassign(settings):
    result = providers.save_profile({'name': 'Temporary', 'from_default': True}, settings)
    profile_id = result['profiles'][0]['id']
    providers.assign_profiles({'graph': profile_id}, settings)
    with pytest.raises(providers.SettingsError):
        providers.remove_profile(profile_id, settings)
    providers.assign_profiles({'graph': 'default'}, settings)
    providers.remove_profile(profile_id, settings)
    assert profile_id not in json.loads(providers.settings_path(settings).read_text())['profiles']


def test_profile_endpoint_change_does_not_forward_previous_key(settings):
    result = providers.save_profile({'name': 'One', 'from_default': True}, settings)
    profile_id = result['profiles'][0]['id']
    with pytest.raises(providers.SettingsError):
        providers.save_profile({'id': profile_id, 'name': 'Changed', 'config': {'provider': 'custom',
            'base_url': 'https://different.test/v1', 'model': 'other', 'api_key': ''}}, settings)
    with pytest.raises(providers.SettingsError):
        providers.save_profile({'name': 'Admin', 'config': {'balance_api_key': 'not-permitted'}}, settings)


def test_empty_catalogue_does_not_invent_generation_capability(settings, monkeypatch):
    result = providers.save_profile({'name': 'One', 'from_default': True}, settings)
    profile_id = result['profiles'][0]['id']
    calls = []
    monkeypatch.setattr(providers, '_request_json', lambda value, suffix: calls.append(suffix) or {'data': []})
    result = providers.test_profile(profile_id, settings)
    assert calls == ['/models']
    assert result['models'] == [] and result['generation_performed'] is False
    assert result['capabilities']['text_generation'] == 'not_verified'
    assert result['capabilities']['structured_output'] == 'not_verified'
    assert result['capabilities']['task_usable'] == 'not_verified'


def test_late_test_response_does_not_overwrite_changed_connection(settings, monkeypatch):
    result = providers.save_profile({'name': 'One', 'from_default': True}, settings)
    profile_id = result['profiles'][0]['id']
    def changed(value, suffix):
        providers.save_profile({'id': profile_id, 'name': 'Changed', 'config': {
            'provider': 'custom', 'base_url': value['base_url'], 'model': 'different', 'api_key': ''}}, settings)
        return {'data': [{'id': 'stale'}]}
    monkeypatch.setattr(providers, '_request_json', changed)
    with pytest.raises(providers.SettingsError, match='已變更'):
        providers.test_profile(profile_id, settings)
    assert providers.profiles_config(settings)['profiles'][0]['capabilities']['model_list'] == 'not_verified'
