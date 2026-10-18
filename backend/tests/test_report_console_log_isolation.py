"""R14: concurrent report generations must not mix console logs."""
import logging

import pytest

from app.config import Config
from app.services import report_agent as module
from app.services.report_agent import (
    ReportAgent,
    ReportConsoleLogger,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)

A_QUERY = 'SYNTHETIC_QUERY_ONLY_REPORT_A 合成查詢A'
B_QUERY = 'SYNTHETIC_QUERY_ONLY_REPORT_B 合成查詢B'


def bind(report_id):
    """Bind the report identity the way ReportAgent.generate_report does."""
    setter = getattr(module, 'current_report_id', None)
    if setter is None:
        return None
    return setter.set(report_id)


def unbind(token):
    if token is not None:
        module.current_report_id.reset(token)


def console_text(report_id):
    with open(ReportManager._get_console_log_path(report_id), encoding='utf-8') as stream:
        return stream.read()


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    report_agent_logger = logging.getLogger('mirofish.report_agent')
    zep_logger = logging.getLogger('mirofish.zep_tools')
    return report_agent_logger, zep_logger, (len(report_agent_logger.handlers), len(zep_logger.handlers))


def test_interleaved_reports_keep_their_own_console_lines(logs):
    report_agent_logger, zep_logger, before = logs
    logger_a = ReportConsoleLogger('report_A')
    logger_b = ReportConsoleLogger('report_B')

    token = bind('report_A')
    zep_logger.info('graphSearch graphId=%s query=%s', 'graph_A', A_QUERY)
    unbind(token)

    token = bind('report_B')
    report_agent_logger.info('sectionSaved report=%s %s', 'report_B', B_QUERY)
    unbind(token)

    logger_a.close()
    logger_b.close()

    text_a, text_b = console_text('report_A'), console_text('report_B')
    assert A_QUERY in text_a and B_QUERY not in text_a
    assert B_QUERY in text_b and A_QUERY not in text_b
    assert (len(report_agent_logger.handlers), len(zep_logger.handlers)) == before


def test_records_without_a_report_identity_are_dropped(logs):
    report_agent_logger, zep_logger, before = logs
    console = ReportConsoleLogger('report_ctx')
    zep_logger.info('NO_CONTEXT_LINE 無歸屬紀錄')
    console.close()
    assert 'NO_CONTEXT_LINE' not in console_text('report_ctx')
    assert (len(report_agent_logger.handlers), len(zep_logger.handlers)) == before


def test_generate_report_binds_and_releases_its_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    zep_logger = logging.getLogger('mirofish.zep_tools')
    before = (len(logging.getLogger('mirofish.report_agent').handlers), len(zep_logger.handlers))

    agent = object.__new__(ReportAgent)
    agent.simulation_id, agent.graph_id, agent.simulation_requirement = 'sim_fixture', 'graph_fixture', '合成問題'
    agent.plan_outline = lambda **_: ReportOutline('標題', '摘要', [ReportSection('章節')])
    seen = {}

    def section(section, **kwargs):
        seen['identity'] = module.current_report_id.get()
        zep_logger.info('DURING_GENERATION_QUERY %s', 'SYNTHETIC_DURING_GENERATION')
        return '合成章節正文'

    agent._generate_section_react = section
    report = agent.generate_report(report_id='report_bound')

    assert report.status == ReportStatus.COMPLETED
    assert seen['identity'] == 'report_bound'
    assert 'SYNTHETIC_DURING_GENERATION' in console_text('report_bound')
    assert module.current_report_id.get() is None
    assert (len(logging.getLogger('mirofish.report_agent').handlers), len(zep_logger.handlers)) == before
