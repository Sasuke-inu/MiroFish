import json

import pytest

from app.config import Config
from app.models.execution import RunStore
from app.models.project import ProjectManager
from app.services.research_workbench import ResearchWorkbench
from app.services.report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
from app.services.simulation_manager import SimulationManager


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    return ResearchWorkbench()


def test_export_keeps_more_than_one_page_of_versions_references_and_original_quote(workbench):
    project_id = workbench.create('歷史證據')['project_id']
    saved = workbench.save_source(project_id, title='來源', identity='fixture', content='最舊但仍被引用的原文')
    original = saved['version']['version_id']
    span = workbench.evidence.create_span(original, 0, 3, '最舊但')
    for index in range(51):
        workbench.evidence.add_version(saved['source']['source_id'], f'新版本 {index}', parser_version='fixture')
        workbench.evidence.add_reference(project_id, 'claim', f'claim_{index}', 'source_record', 'supports',
            source_id=saved['source']['source_id'], version_id=original, span_id=span['span_id'])
    text, _ = workbench.export(project_id, 'json')
    document = json.loads(text)
    assert len(document['references']['items']) == 51
    versions = document['evidence_index'][0]['versions']
    assert len(versions) == 52
    historical = next(version for version in versions if version['version_id'] == original)
    assert historical['spans'][0]['quote'] == '最舊但'
    for format in ('md', 'html'):
        text, _ = workbench.export(project_id, format)
        assert 'claim_0' in text and 'claim_50' in text
        assert original in text and '最舊但' in text


def test_export_keeps_more_than_200_spans_without_other_project_data(workbench):
    pid = workbench.create('所有引句')['project_id']
    saved = workbench.save_source(pid, title='長原文', content='x' * 205)
    for index in range(205):
        workbench.evidence.create_span(saved['version']['version_id'], index, index + 1, 'x')
    other = workbench.create('另一研究')['project_id']
    workbench.save_source(other, title='PRIVATE_OTHER_TITLE', content='PRIVATE_OTHER_CONTENT')
    text, _ = workbench.export(pid, 'json')
    document = json.loads(text)
    assert len(document['evidence_index'][0]['versions'][0]['spans']) == 205
    assert 'PRIVATE_OTHER_' not in text


def test_public_report_preserves_body_but_excludes_private_diagnostics_and_metadata(workbench):
    pid = workbench.create('報告隱私')['project_id']
    run, _ = RunStore.claim('sim_export', {'project_id': pid})
    report = Report('report_private', 'sim_export', '', '問題', ReportStatus.FAILED,
        markdown_content='公開正文 <script>fixture()</script>',
        outline=ReportOutline('標題', '公開摘要', [ReportSection('章節', '保存中的章節正文')]),
        error='INTERNAL_DIAGNOSTIC /synthetic/private/provider.json', run_id=run['run_id'],
        manifest={'model': {'model': 'fixture', 'api_key': 'SYNTHETIC_PRIVATE_KEY'},
                  'file_path': '/synthetic/private/provider.json',
                  'execution': {'configuration': {'db_path': '/synthetic/private/database', 'seed': 7}}})
    ReportManager.save_report(report)
    public = workbench.detail(pid)['reports'][0]
    assert public['outline']['sections'][0]['content'] == '保存中的章節正文'
    for format in ('json', 'md', 'html'):
        text, _ = workbench.export(pid, format)
        assert '公開正文' in text and '保存中的章節正文' in text
        assert 'SYNTHETIC_PRIVATE_KEY' not in text
        assert 'INTERNAL_DIAGNOSTIC' not in text
        assert '/synthetic/private/' not in text
        if format == 'html':
            assert '<script>' not in text
    original = ReportManager.get_report(report.report_id)
    assert original.error == report.error
    assert original.manifest == report.manifest
