import json

import pytest

from app.config import Config
from app.models.execution import RunStore
from app.models.project import ProjectManager
from app.services.event_store import EventStore
from app.services.report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
from app.services.research_workbench import ResearchWorkbench


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))
    return ResearchWorkbench()


def completed(workbench, sim, project_id):
    row, _ = RunStore.claim(sim, {'project_id': project_id})
    RunStore.update(sim, 'completed', graph_ready=True)
    return row


def report(row, identifier, summary, content, version=1, status=ReportStatus.COMPLETED):
    saved = Report(identifier, row['simulation_id'], '', '保存的問題', status,
        outline=ReportOutline('報告', summary, [ReportSection('觀察', content)]),
        markdown_content=content, run_id=row['run_id'], version=version,
        created_at=f'2026-01-{version:02d}T00:00:00+00:00')
    ReportManager.save_report(saved)
    return saved


def test_comparison_uses_latest_completed_same_run_reports_and_scoped_references(workbench):
    pid = workbench.create('比較')['project_id']
    left = completed(workbench, 'sim_left', pid)
    right = completed(workbench, 'sim_right', pid)
    report(left, 'report_left_old', '舊摘要', '舊正文')
    report(left, 'report_left', '左摘要', '左正文', 2)
    report(left, 'report_left_partial', '未完成摘要', '未完成正文', 3, ReportStatus.FAILED)
    report(right, 'report_right', '右摘要', '右正文')
    saved = workbench.save_source(pid, title='來源', content='保存的原文')
    span = workbench.evidence.create_span(saved['version']['version_id'], 0, 5, '保存的原文')
    pointers = {'source_id': saved['source']['source_id'], 'version_id': saved['version']['version_id'], 'span_id': span['span_id']}
    workbench.evidence.add_reference(pid, 'report_section', 'report_left:section:1', 'source_record', 'supports', **pointers)
    workbench.evidence.add_reference(pid, 'report_section', 'report_right:section:1', 'source_record', 'contradicts', **pointers)
    workbench.evidence.add_reference(pid, 'report', 'report_right', 'source_record', 'insufficient',
                                    source_id='missing', allow_missing=True)
    workbench.evidence.add_reference(pid, 'report_section', 'report_right:section:999', 'user_assumption', 'supports', note='NONEXISTENT_SECTION')
    other = workbench.create('其他研究')['project_id']
    other_run = completed(workbench, 'sim_other', other)
    report(other_run, 'report_other', 'PRIVATE_OTHER_SUMMARY', 'PRIVATE_OTHER_BODY')
    workbench.evidence.add_reference(other, 'report', 'report_right', 'user_assumption', 'supports', note='PRIVATE_OTHER_REFERENCE')

    result = EventStore.compare('sim_left', 'sim_right')
    diff = result['report_diff']
    assert diff['status'] == 'compared'
    assert diff['left']['selected_report_id'] == 'report_left'
    assert len(diff['left']['reports']) == 3
    assert diff['summary_changed'] is True
    assert diff['sections'][0]['left']['content'] == '左正文'
    assert diff['sections'][0]['right']['content'] == '右正文'
    assert diff['sections'][0]['changed'] is True
    assert diff['semantic_evaluation'] == 'not_evaluated'
    evidence = result['evidence_diff']
    assert evidence['left']['counts']['supports'] == 1
    assert evidence['right']['counts']['contradicts'] == 1
    assert evidence['delta']['missing'] == 1
    assert evidence['delta']['supports'] == -1
    assert len(evidence['added']) == 2 and len(evidence['removed']) == 1
    assert evidence['right']['references'][0]['validation']['semantic_support'] == 'not_evaluated'
    text = json.dumps(result)
    assert 'PRIVATE_OTHER_' not in text and 'NONEXISTENT_SECTION' not in text


def test_legacy_report_without_matching_run_identity_is_explicitly_unavailable(workbench):
    pid = workbench.create('舊報告')['project_id']
    left = completed(workbench, 'sim_left', pid)
    right = completed(workbench, 'sim_right', pid)
    legacy = Report('report_legacy', left['simulation_id'], '', '歷史問題', ReportStatus.COMPLETED,
                    markdown_content='UNVERIFIED_BODY', run_id=None)
    ReportManager.save_report(legacy)
    report(right, 'report_right', '右摘要', '右正文')
    result = EventStore.compare('sim_left', 'sim_right')
    assert result['report_diff']['status'] == 'unavailable'
    assert result['report_diff']['summary_changed'] is None
    assert result['report_diff']['left']['excluded'][0]['reason'] == 'run_identity_unverified'
    assert result['evidence_diff']['status'] == 'unavailable'
    assert 'UNVERIFIED_' not in json.dumps(result)
