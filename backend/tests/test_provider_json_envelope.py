import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.local_graph import runtime
from app.utils.json_object import unwrap_properties
from app.services import oasis_profile_generator as profiles


class Duplicates(BaseModel):
    duplicate_facts: list[int]
    contradicted_facts: list[int]


@pytest.mark.parametrize('envelope', [False, True])
def test_graph_extraction_accepts_direct_or_schema_wrapped_values(monkeypatch, envelope):
    values = {'duplicate_facts': [0], 'contradicted_facts': []}
    payload = {'properties': values} if envelope else values

    async def completion(*_args, **_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr(runtime, 'create_chat_completion', completion)
    llm = runtime.RouterLLM(config=runtime.LLMConfig(api_key='test', model='cx/gpt-5.6-luna'))
    result = asyncio.run(llm._generate_response([], response_model=Duplicates))
    assert result == values


def test_schema_definitions_cannot_be_mistaken_for_extracted_values(monkeypatch):
    async def completion(*_args, **_kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(Duplicates.model_json_schema())))])

    monkeypatch.setattr(runtime, 'create_chat_completion', completion)
    llm = runtime.RouterLLM(config=runtime.LLMConfig(api_key='test', model='cx/gpt-5.6-luna'))
    with pytest.raises(json.JSONDecodeError, match='Invalid graph extraction schema'):
        asyncio.run(llm._generate_response([], response_model=Duplicates))


def test_normalization_preserves_normal_objects_and_rejects_unrelated_envelopes():
    normal = {'bio': '虛構角色', 'properties': {'bio': '另一個欄位'}}
    assert unwrap_properties(normal, {'bio'}) is normal
    unrelated = {'properties': {'title': '標題'}, 'unrecognized': True}
    assert unwrap_properties(unrelated, {'title'}) is unrelated
    assert unwrap_properties({'properties': {'initial_posts': [{'content': '活動公告'}]}}, {'initial_posts'}) == {
        'initial_posts': [{'content': '活動公告'}]}


def test_profile_does_not_silently_replace_invalid_schema_with_another_paid_call(monkeypatch):
    responses = iter([{'profile_summary': 'wrong structure'}, {'bio': '虛構店主', 'persona': '這是一份詳細的虛構角色設定。'}])
    calls = []

    def completion(*_args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(next(responses))))])

    monkeypatch.setattr(profiles, 'create_chat_completion', completion)
    monkeypatch.setattr(profiles.time, 'sleep', lambda _seconds: None)
    generator = profiles.OasisProfileGenerator(api_key='test')
    with pytest.raises(profiles.PreparationNeedsReview):
        generator._generate_profile_with_llm('小橙', 'CafeOwner', '店主', {}, '')
    assert len(calls) == 1
    assert 'Do not rename or translate keys' in calls[0]['messages'][0]['content']
    assert generator._is_individual_entity('CafeOwner')
    assert generator._is_individual_entity('ClubMember')
    assert not generator._is_individual_entity('CommunityCafe')
