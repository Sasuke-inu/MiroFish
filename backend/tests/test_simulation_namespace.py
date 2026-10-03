"""Simulation creation only uses isolated graphs and immutable model metadata."""
import hashlib
import json
from types import SimpleNamespace

import pytest

import app.services.simulation_manager as module
from app.local_graph.namespace_clone import mapped_uuid

SETTINGS = {'provider': 'custom', 'base_url': 'http://127.0.0.1:9001/v1',
            'model': 'fixture-stage-simulation', 'api_key': 'synthetic-only-key', 'profile_id': 'fixture-profile'}


@pytest.fixture
def setup_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(module.SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(module.Config, 'GRAPH_PROVIDER', 'graphiti')
    calls = []
    def settings(*, stage=None, **kwargs):
        assert stage == 'simulation' or kwargs.get('profile_id') == 'fixture-profile'
        return dict(SETTINGS)
    def clone(source_graph_id, *, graph_id, operation_id):
        calls.append((source_graph_id, graph_id, operation_id))
        return SimpleNamespace(source_graph_id=source_graph_id, target_graph_id=graph_id,
                               operation_id=operation_id, status='ready',
                               summary={'node_mapping': {'entity': mapped_uuid(graph_id, 'entity')}})
    graph = SimpleNamespace(clone=clone)
    monkeypatch.setattr(module, 'get_model_settings', settings)
    monkeypatch.setattr(module, 'get_zep_client', lambda: SimpleNamespace(graph=graph))
    return module.SimulationManager(), graph, calls, tmp_path


def test_create_new_namespace_freezes_simulation_model_without_persisting_key(setup_manager):
    manager, _, calls, path = setup_manager
    state = manager.create_simulation('project', 'source')
    assert state.graph_id != state.source_graph_id == 'source'
    assert state.graph_namespace_status == 'ready'
    assert calls == [('source', state.graph_id, state.simulation_id)]
    assert state.simulation_model_snapshot['model'] == SETTINGS['model']
    assert state.simulation_model_snapshot['profile_id'] == SETTINGS['profile_id']
    assert state.simulation_model_snapshot['connection_fingerprint'] == hashlib.sha256(SETTINGS['api_key'].encode()).hexdigest()
    saved = (path / state.simulation_id / 'state.json').read_text()
    assert SETTINGS['api_key'] not in saved and '"api_key"' not in saved
    loaded = module.SimulationManager().get_simulation(state.simulation_id)
    assert loaded.source_graph_id == 'source'
    assert loaded.simulation_model_frozen_at and loaded.simulation_model_snapshot == state.simulation_model_snapshot


@pytest.mark.parametrize('failure', ['exception', 'wrong_receipt', 'unsupported_provider'])
def test_failed_clone_preserves_review_state_and_never_falls_back_to_source(setup_manager, monkeypatch, failure):
    manager, graph, _, path = setup_manager
    if failure == 'exception':
        graph.clone = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError(SETTINGS['api_key']))
    elif failure == 'wrong_receipt':
        graph.clone = lambda *a, **kw: SimpleNamespace(status='ready', source_graph_id='wrong')
    else:
        monkeypatch.setattr(module.Config, 'GRAPH_PROVIDER', 'zep')
    with pytest.raises(ValueError, match='simulation_id=') as error:
        manager.create_simulation('project', 'source')
    assert SETTINGS['api_key'] not in str(error.value)
    saved = json.loads(next(path.glob('*/state.json')).read_text())
    assert saved['status'] == saved['graph_namespace_status'] == 'needs_review'
    assert saved['graph_id'] != saved['source_graph_id'] == 'source'
    with pytest.raises(ValueError, match='獨立圖譜'):
        manager.require_namespace(manager.get_simulation(saved['simulation_id']))


def test_legacy_read_survives_but_writing_requires_explicit_new_clone(setup_manager):
    manager, _, _, path = setup_manager
    folder = path / 'sim_legacy'
    folder.mkdir()
    (folder / 'state.json').write_text(json.dumps({'simulation_id': 'sim_legacy', 'project_id': 'p', 'graph_id': 'source'}))
    old = manager.get_simulation('sim_legacy')
    assert old.graph_id == 'source' and old.graph_namespace_status == 'legacy_unverified'
    with pytest.raises(ValueError):
        manager.require_namespace(old)


def test_prepared_clone_uses_clean_source_and_remaps_all_entity_references(setup_manager):
    manager, _, calls, path = setup_manager
    original = manager.create_simulation('project', 'source', True, True)
    old_entity = mapped_uuid(original.graph_id, 'entity')
    original.config_generated = original.profiles_generated = True
    original.status = module.SimulationStatus.COMPLETED
    manager._save_simulation_state(original)
    folder = path / original.simulation_id
    config = {'simulation_id': original.simulation_id, 'graph_id': original.graph_id,
              'agent_configs': [{'agent_id': 0, 'entity_uuid': old_entity}]}
    (folder / 'simulation_config.json').write_text(json.dumps(config))
    (folder / 'reddit_profiles.json').write_text(json.dumps([{'source_entity_uuid': old_entity, 'persona': 'fixture'}]))
    (folder / 'twitter_profiles.csv').write_text('user_id,source_entity_uuid\n0,' + old_entity + '\n')
    (folder / 'reddit_simulation.db').write_bytes(b'parent output preserved')
    clone = manager.clone_simulation(original.simulation_id)
    new_entity = mapped_uuid(clone.graph_id, 'entity')
    assert calls[-1][0] == 'source'
    assert clone.graph_id != original.graph_id and clone.source_graph_id == original.source_graph_id
    new_config = manager.get_simulation_config(clone.simulation_id)
    assert new_config['graph_id'] == clone.graph_id
    assert new_config['agent_configs'][0]['entity_uuid'] == new_entity
    assert manager.get_profiles(clone.simulation_id, 'reddit')[0]['source_entity_uuid'] == new_entity
    assert manager.get_profiles(clone.simulation_id, 'twitter')[0]['source_entity_uuid'] == new_entity
    assert manager.get_simulation_config(original.simulation_id) == config
    assert not (path / clone.simulation_id / 'reddit_simulation.db').exists()
    assert (folder / 'reddit_simulation.db').read_bytes() == b'parent output preserved'


def test_unmapped_prepared_reference_cannot_become_ready(setup_manager):
    manager, _, _, path = setup_manager
    original = manager.create_simulation('project', 'source', False, True)
    original.config_generated = original.profiles_generated = True
    folder = path / original.simulation_id
    (folder / 'simulation_config.json').write_text(json.dumps({'agent_configs': [{'entity_uuid': 'missing'}]}))
    (folder / 'reddit_profiles.json').write_text('[]')
    with pytest.raises(ValueError, match='實體'):
        manager.clone_simulation(original.simulation_id)
    assert any(state.status == module.SimulationStatus.FAILED for state in manager.list_simulations())


def test_explicit_recovery_uses_same_copy_identity_and_never_starts_simulation(setup_manager, monkeypatch):
    manager, graph, calls, _ = setup_manager
    monkeypatch.setattr(module.RunStore, 'get', lambda _: None)
    original_clone = graph.clone
    graph.clone = lambda *a, **kw: (_ for _ in ()).throw(TimeoutError('response lost'))
    with pytest.raises(ValueError):
        manager.create_simulation('project', 'source')
    state = manager.list_simulations()[0]
    target = state.graph_id
    graph.clone = original_clone
    restored = manager.recover_namespace(state.simulation_id)
    assert calls == [('source', target, state.simulation_id)]
    assert restored.status == module.SimulationStatus.CREATED
    assert restored.graph_namespace_status == 'ready'
    assert not restored.config_generated and not restored.profiles_generated


def test_recovery_does_not_accept_changed_connection_key(setup_manager, monkeypatch):
    manager, graph, _, _ = setup_manager
    monkeypatch.setattr(module.RunStore, 'get', lambda _: None)
    graph.clone = lambda *a, **kw: (_ for _ in ()).throw(TimeoutError('response lost'))
    with pytest.raises(ValueError):
        manager.create_simulation('project', 'source')
    state = manager.list_simulations()[0]
    monkeypatch.setattr(module, 'get_model_settings', lambda **_: {**SETTINGS, 'api_key': 'changed'})
    with pytest.raises(ValueError, match='憑證'):
        manager.recover_namespace(state.simulation_id)
    assert state.graph_namespace_status == 'needs_review'


@pytest.mark.parametrize('identity', ['../original', '..\\original', '/absolute', 'a/b', 'a' * 201, '', None])
def test_invalid_simulation_identity_cannot_touch_files_outside_namespace(setup_manager, identity):
    manager, _, _, path = setup_manager
    original = path.parent / 'original'
    original.mkdir(exist_ok=True)
    sentinel = original / 'state.json'
    sentinel.write_text('preserved')
    with pytest.raises(ValueError, match='識別'):
        manager.get_simulation(identity)
    assert sentinel.read_text() == 'preserved'
    assert list(path.iterdir()) == []
