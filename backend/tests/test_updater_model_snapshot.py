from types import SimpleNamespace
import threading

import pytest

from app.provider_settings import get_model_settings, model_settings_snapshot
from app.services import zep_graph_memory_updater as module

SETTINGS = {'provider': 'custom', 'base_url': 'http://127.0.0.1:9001/v1', 'model': 'frozen', 'api_key': 'synthetic-secret'}


def activity(number):
    return module.AgentActivity('twitter', number, 'fixture', 'CREATE_POST', {'content': 'synthetic'}, number, '2026-01-01T00:00:00Z')


def test_worker_and_final_drain_keep_private_snapshot_after_settings_change(monkeypatch):
    writes, polls = [], []
    sent = threading.Event()
    def add(**kwargs):
        writes.append(get_model_settings())
        sent.set()
        return SimpleNamespace(uuid_='episode-' + str(len(writes)))
    def episode(**kwargs):
        polls.append(get_model_settings())
        return SimpleNamespace(processed=True)
    client = SimpleNamespace(graph=SimpleNamespace(add=add, episode=SimpleNamespace(get=episode)))
    monkeypatch.setattr(module, 'get_zep_client', lambda *_: client)
    snapshot = dict(SETTINGS)
    updater = module.ZepGraphMemoryUpdater('run_fixture', model_snapshot=snapshot)
    snapshot['model'] = 'caller-mutated'
    updater.BATCH_SIZE = 2
    updater.SEND_INTERVAL = 0
    with model_settings_snapshot({**SETTINGS, 'model': 'new-global'}):
        updater.start()
        updater.add_activity(activity(1))
        updater.add_activity(activity(2))
        assert sent.wait(3)
        updater.add_activity(activity(3))
        updater.stop()
    assert len(writes) == 2 and polls
    assert all(value == SETTINGS for value in writes + polls)
    assert 'api_key' not in updater.get_stats()


def test_provider_error_body_is_not_retained_or_logged(monkeypatch, caplog):
    def add(**kwargs):
        raise RuntimeError('remote echoed ' + SETTINGS['api_key'])
    monkeypatch.setattr(module, 'get_zep_client', lambda *_: SimpleNamespace(graph=SimpleNamespace(add=add)))
    updater = module.ZepGraphMemoryUpdater('run_fixture', model_snapshot=SETTINGS)
    updater._send_batch_activities([activity(1)], 'twitter')
    with pytest.raises(RuntimeError, match='incomplete') as error:
        updater.stop()
    assert SETTINGS['api_key'] not in caplog.text + str(error.value) + str(updater._failed_batches)


def test_stop_all_aggregate_does_not_expose_provider_error_body(monkeypatch, caplog):
    manager = module.ZepGraphMemoryManager
    monkeypatch.setattr(manager, '_updaters', {'sim_fixture': object()})
    monkeypatch.setattr(manager, '_stop_all_done', False)
    def fail(_simulation_id):
        raise RuntimeError('provider echoed ' + SETTINGS['api_key'])
    monkeypatch.setattr(manager, 'stop_updater', fail)
    with pytest.raises(RuntimeError) as error:
        manager.stop_all()
    assert SETTINGS['api_key'] not in str(error.value) + caplog.text
    assert 'sim_fixture: RuntimeError' in str(error.value)
