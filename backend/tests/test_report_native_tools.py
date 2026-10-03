from types import SimpleNamespace

import pytest

from app.services.report_agent import ReportAgent
from app.utils.llm_client import LLMClient, LLMResponseError


def client_with_tool(arguments='{"query":"橙子小屋","limit":5}'):
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(function=SimpleNamespace(name='quick_search', arguments=arguments))
        ]))])

    client = LLMClient(api_key='test', model='cx/gpt-5.6-luna')
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, requests


def test_native_calls_reach_existing_report_dispatcher_with_valid_parameters():
    client, requests = client_with_tool()
    agent = object.__new__(ReportAgent)
    agent.tools = agent._define_tools()
    response = client.chat(messages=[{'role': 'user', 'content': '搜尋資料'}],
                           tools=agent._native_tools(), tool_choice='required', temperature=0.5)
    assert agent._parse_tool_calls(response) == [{'name': 'quick_search', 'parameters': {'query': '橙子小屋', 'limit': 5}}]
    assert len(requests[0]['tools']) == 4
    assert requests[0]['tool_choice'] == 'required'
    assert requests[0]['parallel_tool_calls'] is False
    assert 'temperature' not in requests[0]


@pytest.mark.parametrize('arguments', ['{broken', '[]'])
def test_invalid_native_arguments_do_not_dispatch_a_graph_operation(arguments):
    client, _requests = client_with_tool(arguments)
    with pytest.raises(LLMResponseError):
        client.chat(messages=[], tools=[{'type': 'function'}])
