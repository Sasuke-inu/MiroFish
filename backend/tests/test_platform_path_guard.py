"""R13: a platform name may not steer which simulation database is read."""
import json
import sqlite3

from flask import Flask
import pytest

from app.api import simulation as api
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner


def make_db(path, post=None, comment=None):
    conn = sqlite3.connect(path)
    for table, marker in (('post', post), ('comment', comment)):
        if marker is None:
            continue
        conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, content TEXT, created_at TEXT)')
        conn.execute(f'INSERT INTO {table} (content, created_at) VALUES (?, ?)', (marker, '2026-01-01'))
    conn.commit()
    conn.close()


@pytest.fixture
def sims(tmp_path, monkeypatch):
    root = tmp_path / 'simulations'
    (root / 'sim_A').mkdir(parents=True)
    (root / 'sim_B').mkdir(parents=True)
    (root / 'sim_empty').mkdir(parents=True)
    make_db(root / 'sim_A' / 'reddit_simulation.db', post='ONLY_SIM_A', comment='ONLY_SIM_A_COMMENT')
    make_db(root / 'sim_A' / 'twitter_simulation.db', post='ONLY_SIM_A_TWITTER')
    make_db(root / 'sim_B' / 'reddit_simulation.db', post='ONLY_SIM_B', comment='ONLY_SIM_B_COMMENT')
    monkeypatch.setattr(SimulationRunner, 'RUN_STATE_DIR', str(root))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(root))
    app = Flask(__name__)
    app.register_blueprint(api.simulation_bp, url_prefix='/api/simulation')
    return app.test_client(), root


TRAVERSAL = ['../sim_B/reddit', '..\\sim_B\\reddit', 'reddit/../../sim_B/reddit',
             'sim_B/reddit', '/abs/sim_B/reddit', 'Reddit', 'reddit ', 'reddit\x00']


@pytest.mark.parametrize('platform', TRAVERSAL)
def test_foreign_platform_never_opens_a_database(sims, monkeypatch, platform):
    client, _ = sims

    def forbidden(*args, **kwargs):
        raise AssertionError(f'sqlite3.connect must not be called: {args}')

    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    for route in ('posts', 'comments'):
        response = client.get(f'/api/simulation/sim_A/{route}', query_string={'platform': platform})
        assert response.status_code == 400, (route, platform, response.json)
        assert response.json['success'] is False and response.json['error']
        assert 'ONLY_SIM_B' not in response.get_data(as_text=True)


def test_legit_platforms_read_only_their_own_simulation(sims, monkeypatch):
    client, _ = sims
    records = []
    real = sqlite3.connect

    def connect(database, *args, **kwargs):
        records.append((database, kwargs.get('uri', False)))
        return real(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', connect)

    posts = client.get('/api/simulation/sim_A/posts', query_string={'platform': 'reddit'})
    assert [row['content'] for row in posts.json['data']['posts']] == ['ONLY_SIM_A']
    comments = client.get('/api/simulation/sim_A/comments', query_string={'platform': 'reddit'})
    assert [row['content'] for row in comments.json['data']['comments']] == ['ONLY_SIM_A_COMMENT']
    twitter = client.get('/api/simulation/sim_A/posts', query_string={'platform': 'twitter'})
    assert [row['content'] for row in twitter.json['data']['posts']] == ['ONLY_SIM_A_TWITTER']
    other = client.get('/api/simulation/sim_B/comments', query_string={'platform': 'reddit'})
    assert [row['content'] for row in other.json['data']['comments']] == ['ONLY_SIM_B_COMMENT']

    assert records, 'the valid reads must have opened the databases'
    for database, uri in records:
        assert uri is True, database
        assert str(database).startswith('file:'), database
        assert '?mode=ro' in str(database), database
        assert '/sim_A/' in str(database) or '/sim_B/' in str(database)


def test_read_only_uri_cannot_write_or_create(sims):
    client, root = sims
    uri = api._readonly_sqlite_uri(str(root / 'sim_A' / 'reddit_simulation.db'))
    conn = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO post (content, created_at) VALUES ('x', '2026-01-01')")
    conn.close()

    missing = root / 'sim_A' / 'never_created.db'
    with pytest.raises(sqlite3.OperationalError):
        sqlite3.connect(api._readonly_sqlite_uri(str(missing)), uri=True)
    assert not missing.exists()


def test_default_platform_still_follows_the_state_after_validation(sims):
    client, root = sims
    (root / 'sim_A' / 'state.json').write_text(json.dumps(
        {'simulation_id': 'sim_A', 'enable_twitter': True, 'enable_reddit': False}), encoding='utf-8')
    response = client.get('/api/simulation/sim_A/posts')
    assert response.status_code == 200
    assert [row['content'] for row in response.json['data']['posts']] == ['ONLY_SIM_A_TWITTER']


def test_missing_database_keeps_the_friendly_empty_response(sims):
    client, _ = sims
    posts = client.get('/api/simulation/sim_empty/posts', query_string={'platform': 'reddit'})
    assert posts.status_code == 200 and posts.json['success'] is True
    assert posts.json['data'] == {'platform': 'reddit', 'count': 0, 'posts': [],
                                  'message': posts.json['data']['message']}
    comments = client.get('/api/simulation/sim_empty/comments', query_string={'platform': 'reddit'})
    assert comments.status_code == 200
    assert comments.json['data'] == {'count': 0, 'comments': []}


def test_invalid_simulation_identity_still_rejected_before_platform_lookup(sims):
    client, _ = sims
    response = client.get('/api/simulation/..%2Fsim_B/posts', query_string={'platform': 'reddit'})
    assert response.status_code in {400, 404}
    assert 'ONLY_SIM_B' not in response.get_data(as_text=True)
