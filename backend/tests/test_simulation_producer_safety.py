"""Exercise producer helpers without importing or running OASIS simulations."""
import ast
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load_function(filename, name, **context):
    tree = ast.parse((SCRIPTS / filename).read_text(encoding='utf-8'))
    function = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    isolated = ast.Module(body=[function], type_ignores=[])
    namespace = {'os': os, 'Dict': Dict, 'Any': Any, 'List': List, 'Optional': Optional, **context}
    exec(compile(isolated, filename, 'exec'), namespace)
    return namespace[name]


@pytest.mark.parametrize('filename,function_name', [
    ('run_parallel_simulation.py', 'create_model'),
    ('run_reddit_simulation.py', '_create_model'),
    ('run_twitter_simulation.py', '_create_model'),
])
def test_each_producer_disables_hidden_sdk_retries(filename, function_name, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'SYNTHETIC_FIXTURE_KEY')
    monkeypatch.setenv('LLM_MODEL_NAME', 'fixture-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://fixture.invalid/v1')
    monkeypatch.delenv('LLM_BOOST_API_KEY', raising=False)
    create = load_function(filename, function_name,
        ModelFactory=SimpleNamespace(create=lambda **kwargs: kwargs),
        ModelPlatformType=SimpleNamespace(OPENAI='fixture'))
    result = create({}) if function_name == 'create_model' else create(SimpleNamespace(config={}))
    assert result['max_retries'] == 0
    assert result['model_type'] == 'fixture-model'


def test_recorded_follow_saves_target_agent_identity():
    lookup = load_function('run_parallel_simulation.py', '_get_user_name')
    enrich = load_function('run_parallel_simulation.py', '_enrich_action_context', _get_user_name=lookup)
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE follow(follow_id INTEGER,followee_id INTEGER)')
        db.execute('CREATE TABLE user(user_id INTEGER,agent_id INTEGER,name TEXT,user_name TEXT)')
        db.execute("INSERT INTO follow VALUES(1,77)")
        db.execute("INSERT INTO user VALUES(77,0,'Fixture','fixture')")
        args = {'follow_id': 1}
        enrich(db.cursor(), 'FOLLOW', args, {0: 'Fixture'})
        assert args['target_agent_id'] == 0
        assert args['target_user_name'] == 'Fixture'
