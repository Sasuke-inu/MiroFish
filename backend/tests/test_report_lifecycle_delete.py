"""R04: report delete vs. live generation, per-report lifecycle lock, assembly completeness."""
import os
import threading

import pytest
from flask import Flask

from app.api import report as api
from app.config import Config
from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    app = Flask(__name__)
    app.register_blueprint(api.report_bp, url_prefix='/api/report')
    return app.test_client()


@pytest.mark.parametrize('status', [ReportStatus.PENDING, ReportStatus.PLANNING, ReportStatus.GENERATING])
def test_delete_is_refused_while_the_report_is_still_generating(client, status):
    ReportManager.save_report(Report('report_busy', 'sim_busy', 'graph_busy', 'Fixture', status,
                                     created_at='2025-01-01'))
    ReportManager.save_section('report_busy', 1, ReportSection('第一章', 'SYNTHETIC_SECTION_BODY'))

    response = client.delete('/api/report/report_busy')

    assert response.status_code == 409
    assert response.json['success'] is False
    assert '生成' in response.json['error']
    assert ReportManager.get_report('report_busy').status == status
    assert os.path.exists(ReportManager._get_section_path('report_busy', 1))


def test_delete_still_removes_finished_reports_and_keeps_404(client):
    assert client.delete('/api/report/report_absent').status_code == 404

    ReportManager.save_report(Report('report_done', 'sim_done', 'graph_done', 'Fixture',
                                     ReportStatus.COMPLETED, created_at='2025-01-01'))
    response = client.delete('/api/report/report_done')
    assert response.status_code == 200
    assert ReportManager.get_report('report_done') is None


def test_delete_waits_for_the_report_lifecycle_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    ReportManager.save_report(Report('report_locked', 'sim_locked', 'graph_locked', 'Fixture',
                                     ReportStatus.COMPLETED, created_at='2025-01-01'))

    done = threading.Event()
    with ReportManager.report_lock('report_locked'):
        worker = threading.Thread(target=lambda: (ReportManager.delete_report('report_locked'), done.set()))
        worker.start()
        assert not done.wait(0.5)  # a delete cannot interleave with a live save/assembly

    worker.join(5)
    assert done.is_set()
    assert ReportManager.get_report('report_locked') is None


def test_assembly_refuses_an_outline_section_without_a_saved_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    outline = ReportOutline('標題', '摘要', [ReportSection('第一章'), ReportSection('第二章')])
    ReportManager.save_section('report_partial', 2, ReportSection('第二章', 'SYNTHETIC_SECOND_BODY'))

    assert ReportManager.assemble_full_report('report_partial', outline) is None
    assert not os.path.exists(ReportManager._get_report_markdown_path('report_partial'))


def test_completion_path_never_declares_a_report_with_missing_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    agent = object.__new__(ReportAgent)
    agent.simulation_id, agent.graph_id, agent.simulation_requirement = 'sim_fixture', 'graph_fixture', '合成問題'
    agent.plan_outline = lambda **_: ReportOutline('標題', '摘要', [ReportSection('第一章'), ReportSection('第二章')])
    agent._generate_section_react = lambda section, **_: f'SYNTHETIC_BODY_{section.title}'
    real_save_section = ReportManager.save_section

    def save_without_the_first_section(report_id, section_index, section):
        if section_index == 1:
            return ''  # the folder lost the first section file before assembly
        return real_save_section(report_id, section_index, section)

    monkeypatch.setattr(ReportManager, 'save_section', save_without_the_first_section)

    report = agent.generate_report(report_id='report_missing_section')

    assert report.status == ReportStatus.NEEDS_REVIEW
    assert report.completed_at == ''
    assert report.markdown_content == ''
    assert '1' in (report.error or '')
    assert not os.path.exists(ReportManager._get_report_markdown_path('report_missing_section'))
    assert os.path.exists(ReportManager._get_section_path('report_missing_section', 2))
    assert ReportManager.get_report('report_missing_section').status == ReportStatus.NEEDS_REVIEW


def test_complete_two_section_report_is_still_declared_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    agent = object.__new__(ReportAgent)
    agent.simulation_id, agent.graph_id, agent.simulation_requirement = 'sim_fixture', 'graph_fixture', '合成問題'
    agent.plan_outline = lambda **_: ReportOutline('標題', '摘要', [ReportSection('第一章'), ReportSection('第二章')])
    agent._generate_section_react = lambda section, **_: f'SYNTHETIC_BODY_{section.title}'

    report = agent.generate_report(report_id='report_complete')

    assert report.status == ReportStatus.COMPLETED
    assert 'SYNTHETIC_BODY_第一章' in report.markdown_content
    assert 'SYNTHETIC_BODY_第二章' in report.markdown_content
