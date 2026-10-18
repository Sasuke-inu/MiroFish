"""R08: 'latest' is what was observed last, not the last distinct text row."""
from datetime import datetime, timezone
import sqlite3

import pytest

from app.services.evidence_store import EvidenceStore
from app.storage import database


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'workbench.sqlite3'))
    return EvidenceStore(clock=lambda: datetime(2026, 10, 18, tzinfo=timezone.utc))


def source(store):
    return store.create_source('proj_one', 'web', 'article', title='合成測試來源')


def test_restored_earlier_text_becomes_latest_again(store):
    src = source(store)
    a = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    b = store.add_version(src['source_id'], 'BRAVO', parser_version='plain-text/1')
    again = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    assert again['version_id'] == a['version_id']  # immutable reuse
    assert store.latest_version_id(src['source_id']) == a['version_id']
    assert store.latest_version(src['source_id'], include_content=True)['content'] == 'ALPHA'
    assert store.list_versions(src['source_id'])['total'] == 2
    # The history list keeps insertion order; only the live pointer changes.
    assert store.list_versions(src['source_id'], limit=1)['items'][0]['version_id'] == b['version_id']


def test_restored_saved_text_after_missing_is_latest(store):
    src = source(store)
    a = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    missing = store.add_version(src['source_id'], parser_version='legacy/unknown', status='missing')
    assert store.latest_version_id(src['source_id']) == missing['version_id']
    again = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    assert again['version_id'] == a['version_id']
    latest = store.latest_version(src['source_id'], include_content=True)
    assert latest['version_id'] == a['version_id']
    assert latest['status'] == 'saved' and latest['content'] == 'ALPHA'


def test_repeated_identical_save_creates_no_version_and_keeps_pointer(store):
    src = source(store)
    a = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    for _ in range(3):
        reused = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/2')
        assert reused['version_id'] == a['version_id']
    assert store.list_versions(src['source_id'])['total'] == 1
    assert store.latest_version_id(src['source_id']) == a['version_id']


def test_pointer_moves_but_versions_and_references_stay_immutable(store):
    src = source(store)
    a = store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    span = store.create_span(a['version_id'], 0, 5, 'ALPHA')
    ref = store.add_reference('proj_one', 'report', 'one', 'source_record', 'supports', span_id=span['span_id'])
    store.add_version(src['source_id'], 'BRAVO', parser_version='plain-text/1')
    assert store.latest_version(src['source_id'], include_content=True)['content'] == 'BRAVO'
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        with database() as conn:
            conn.execute('UPDATE evidence_versions SET parser_version=parser_version')
    assert store.get_version(a['version_id'], include_content=True)['content'] == 'ALPHA'
    assert store.get_reference(ref['reference_id'])['version_id'] == a['version_id']


def test_legacy_database_without_pointer_migrates_to_newest_recorded_row(store):
    src = source(store)
    store.add_version(src['source_id'], 'ALPHA', parser_version='plain-text/1')
    store.add_version(src['source_id'], 'BRAVO', parser_version='plain-text/1')
    with database() as conn:
        conn.execute('DELETE FROM evidence_latest')
    migrated = EvidenceStore(clock=lambda: datetime(2026, 10, 19, tzinfo=timezone.utc))
    newest = migrated.list_versions(src['source_id'], limit=1)['items'][0]['version_id']
    assert migrated.latest_version_id(src['source_id']) == newest
    # No recorded version means no fabricated observation.
    assert migrated.latest_version_id('src_unknown') is None
    assert migrated.latest_version('src_unknown') is None
