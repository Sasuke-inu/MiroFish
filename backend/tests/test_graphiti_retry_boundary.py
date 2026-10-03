import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError, InternalServerError
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message

from app.local_graph.runtime import RouterLLM
from app.local_graph.store import ServiceError


@pytest.mark.parametrize('failure', ['timeout', 'server_error', 'invalid_json'])
def test_paid_generation_does_not_replay_unknown_or_invalid_result(failure):
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        request = httpx.Request('POST', 'http://127.0.0.1:9001/v1/chat/completions')
        if failure == 'timeout':
            raise APITimeoutError(request=request)
        if failure == 'server_error':
            raise InternalServerError('synthetic-key must not leak', response=httpx.Response(500, request=request), body={})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='invalid'))])
    class Client:
        max_retries = 2
        chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
    client = Client()
    llm = RouterLLM(config=LLMConfig(api_key='synthetic-key', model='fixture'), client=client)
    with pytest.raises((ServiceError, json.JSONDecodeError)) as error:
        asyncio.run(llm.generate_response([Message(role='user', content='fixture request')]))
    assert len(calls) == 1
    assert client.max_retries == 0
    assert 'synthetic-key' not in str(error.value)
    if failure == 'server_error':
        assert error.value.status == 500
