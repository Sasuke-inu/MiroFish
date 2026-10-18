from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.oasis_camel_compat import apply_oasis_camel_compat


@pytest.mark.asyncio
async def test_removed_token_hint_preserves_modern_options_and_response():
    received = {}
    response = object()

    class ModernAgent:
        async def _aget_model_response(self, openai_messages, current_iteration=0,
                                       response_format=None, tool_schemas=None):
            received.update(messages=openai_messages, iteration=current_iteration,
                            response_format=response_format, tools=tool_schemas)
            return response

    assert apply_oasis_camel_compat(ModernAgent)
    wrapped = ModernAgent._aget_model_response
    assert not apply_oasis_camel_compat(ModernAgent)
    assert ModernAgent._aget_model_response is wrapped
    messages, tools = [{'role': 'user', 'content': 'Interview'}], [{'type': 'function'}]
    actual = await ModernAgent()._aget_model_response(messages, num_tokens=23,
                                                    current_iteration=2, tool_schemas=tools)
    assert actual is response
    assert received == {'messages': messages, 'iteration': 2, 'response_format': None, 'tools': tools}


def test_runtime_with_old_token_parameter_is_left_unchanged():
    class LegacyAgent:
        async def _aget_model_response(self, openai_messages, num_tokens):
            return num_tokens

    original = LegacyAgent._aget_model_response
    assert not apply_oasis_camel_compat(LegacyAgent)
    assert LegacyAgent._aget_model_response is original


@pytest.mark.asyncio
async def test_real_oasis_interview_uses_current_camel_response_and_persists_answer(monkeypatch):
    from camel.agents import ChatAgent
    from oasis.social_agent.agent import SocialAgent

    async def model_response(self, openai_messages, current_iteration=0,
                             response_format=None, tool_schemas=None,
                             prev_num_openai_messages=0):
        assert openai_messages[-1]['content'] == '請回答這份問卷'
        return SimpleNamespace(output_messages=[SimpleNamespace(content='支持，請維持安靜。')])

    monkeypatch.setattr(SocialAgent, '_aget_model_response', model_response)
    untouched = ChatAgent._aget_model_response
    assert apply_oasis_camel_compat()
    agent = SimpleNamespace(
        social_agent_id=7, interview_record=False,
        memory=SimpleNamespace(get_context=lambda: ([], 25)),
        system_message=SimpleNamespace(role_name='system', content='Role persona'),
        env=SimpleNamespace(action=SimpleNamespace(perform_action=AsyncMock(return_value={'success': True}))))
    agent._aget_model_response = SocialAgent._aget_model_response.__get__(agent)
    result = await SocialAgent.perform_interview(agent, '請回答這份問卷')
    assert result['content'] == '支持，請維持安靜。' and result['success']
    assert agent.env.action.perform_action.await_args.args[0] == {
        'prompt': '請回答這份問卷', 'response': '支持，請維持安靜。'}
    assert ChatAgent._aget_model_response is untouched
