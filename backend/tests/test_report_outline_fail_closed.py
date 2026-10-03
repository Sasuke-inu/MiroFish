from types import SimpleNamespace

import pytest

from app.services import report_agent as module
from app.services.report_agent import ReportAgent, ReportManager, ReportOutline, ReportSection, ReportStatus
from app.utils.llm_client import LLMResponseError


@pytest.mark.parametrize('response', [
    TimeoutError('SYNTHETIC_PRIVATE_PROVIDER_DETAILS'),
    LLMResponseError('SYNTHETIC_PRIVATE_PROVIDER_DETAILS'),
    {}, {'title': '標題', 'sections': []},
    {'title': ' ', 'sections': [{'title': '章節'}]},
    {'title': '標題', 'sections': [{}]},
    {'title': '標題', 'sections': [{'title': 5}]},
    {'title': '標題', 'sections': 'invalid'},
])
def test_unknown_or_invalid_outline_stops_before_any_section_calls(tmp_path, monkeypatch, response):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    calls, sections = [], []
    def request(**kwargs):
        calls.append(kwargs)
        if isinstance(response, Exception):
            raise response
        return response
    agent = object.__new__(ReportAgent)
    agent.simulation_id, agent.graph_id, agent.simulation_requirement = 'sim_fixture', 'graph_fixture', '合成問題'
    agent.llm = SimpleNamespace(chat_json=request)
    agent.zep_tools = SimpleNamespace(get_simulation_context=lambda **_: {})
    agent._generate_section_react = lambda **kwargs: sections.append(kwargs) or '不能繼續付費的章節'
    report = agent.generate_report(report_id='report_fixture')
    assert report.status == ReportStatus.NEEDS_REVIEW
    assert len(calls) == 1
    assert sections == []
    assert report.completed_at == ''
    assert report.markdown_content == ''
    assert ReportManager.get_report(report.report_id).status == ReportStatus.NEEDS_REVIEW
    assert 'SYNTHETIC_PRIVATE_PROVIDER_DETAILS' not in report.error


def test_valid_outline_preserves_model_titles_without_default_content():
    agent = object.__new__(ReportAgent)
    agent.graph_id, agent.simulation_requirement = 'graph_fixture', '合成問題'
    agent.zep_tools = SimpleNamespace(get_simulation_context=lambda **_: {})
    agent.llm = SimpleNamespace(chat_json=lambda **_: {'title': '實際標題', 'summary': '保存摘要',
                                                     'sections': [{'title': '實際章節'}]})
    outline = agent.plan_outline()
    assert outline.title == '實際標題'
    assert outline.summary == '保存摘要'
    assert len(outline.sections) == 1 and outline.sections[0].title == '實際章節'


@pytest.mark.parametrize('response', [None, '', 'Final Answer:', '<tool_result>fabricated</tool_result>',
                                     TimeoutError('PRIVATE_TIMEOUT'), LLMResponseError('PRIVATE_INVALID')])
def test_unknown_section_result_stops_after_one_request(response):
    agent = object.__new__(ReportAgent)
    agent.simulation_requirement, agent.report_logger = '合成問題', None
    agent.tools = agent._define_tools()
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        if isinstance(response, Exception):
            raise response
        return response
    agent.llm = SimpleNamespace(chat=request)
    with pytest.raises(RuntimeError) as caught:
        agent._generate_section_react(ReportSection('章節'), ReportOutline('標題', '摘要', []), [])
    assert getattr(caught.value, 'outcome_unknown', False) is True
    assert len(calls) == 1
    assert 'PRIVATE_' not in str(caught.value)


def test_unknown_report_tool_does_not_become_success_text_or_trigger_more_model_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    agent = object.__new__(ReportAgent)
    agent.simulation_id, agent.graph_id, agent.simulation_requirement = 'sim_fixture', 'graph_fixture', '合成問題'
    agent.tools = agent._define_tools()
    calls, tool_calls = [], []
    def request(**kwargs):
        calls.append(kwargs)
        return '<tool_call>{"name":"quick_search","parameters":{"query":"合成查詢"}}</tool_call>'
    def tool(**kwargs):
        tool_calls.append(kwargs)
        raise TimeoutError('PRIVATE_PROVIDER_TOOL_RESPONSE')
    agent.llm = SimpleNamespace(chat=request, chat_json=lambda **_: {
        'title': '標題', 'sections': [{'title': '章節'}]})
    agent.zep_tools = SimpleNamespace(get_simulation_context=lambda **_: {}, quick_search=tool)
    result = agent.generate_report(report_id='report_unknown_tool')
    assert result.status == ReportStatus.NEEDS_REVIEW and result.completed_at == ''
    assert len(calls) == len(tool_calls) == 1
    assert result.markdown_content == ''
    assert 'PRIVATE_' not in result.error


def test_empty_section_cannot_be_saved_as_completed_report(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    agent = object.__new__(ReportAgent)
    agent.simulation_id, agent.graph_id, agent.simulation_requirement = 'sim_fixture', 'graph_fixture', '合成問題'
    agent.plan_outline = lambda **_: ReportOutline('標題', '摘要', [ReportSection('章節')])
    agent._generate_section_react = lambda **_: '   '
    result = agent.generate_report(report_id='report_empty_section')
    assert result.status == ReportStatus.NEEDS_REVIEW and result.completed_at == ''
    assert result.markdown_content == ''
