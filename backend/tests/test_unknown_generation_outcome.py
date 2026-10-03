import httpx
import pytest
import openai
from app.utils.llm_client import LLMClient
from app.utils.openai_chat_compat import ModelServiceError


def test_sdk_never_retries_a_timeout_with_unknown_generation_outcome():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('synthetic timeout', request=request)
    client = LLMClient(api_key='fixture-not-a-key', base_url='https://provider.test/v1', model='fixture')
    assert client.client.max_retries == 0
    client.client.close()
    client.client = openai.OpenAI(api_key='fixture-not-a-key', base_url='https://provider.test/v1', max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(ModelServiceError, match='逾時'):
        client.chat([{'role': 'user', 'content': 'synthetic'}])
    assert len(calls) == 1
    client.client.close()
