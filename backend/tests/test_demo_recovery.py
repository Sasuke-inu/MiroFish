import pytest

from app.config import Config
from app.models.execution import RunStore
from app.models.project import ProjectManager
from app.services import workbench_demos as demos
from app.services.event_store import EventStore
from app.services.report_agent import Report, ReportManager, ReportStatus
from app.services.simulation_manager import SimulationManager


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('MIROFISH_WORKBENCH_DB', str(tmp_path / 'ledger.sqlite3'))
    monkeypatch.setattr(Config, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(ReportManager, 'REPORTS_DIR', str(tmp_path / 'reports'))


def test_interrupted_demo_resumes_same_identity_after_verifying_all_events(monkeypatch):
    original_append = EventStore.append
    calls = []
    def interrupt(simulation_id, event):
        calls.append(event['event_id'])
        if len(calls) == 3:
            raise RuntimeError('Synthetic interruption')
        return original_append(simulation_id, event)
    monkeypatch.setattr(EventStore, 'append', interrupt)
    with pytest.raises(RuntimeError, match='Synthetic interruption'):
        demos.install('product')
    prior = RunStore.get('sim_demo_product_a')
    assert len(EventStore.page('sim_demo_product_a')['items']) == 2
    RunStore.update('sim_demo_product_a', 'interrupted')
    monkeypatch.setattr(EventStore, 'append', original_append)
    demos.install('product')
    restored = RunStore.get('sim_demo_product_a')
    assert restored['run_id'] == prior['run_id']
    assert restored['attempt_id'] == prior['attempt_id']
    assert restored['manifest'] == prior['manifest']
    assert restored['status'] == 'completed'
    assert restored['graph_ready'] is False
    assert len(EventStore.page('sim_demo_product_a')['items']) == 6
    assert ReportManager.get_report('report_demo_product_a') is not None


def test_demo_refuses_existing_real_run_instead_of_seeding_or_completing_it():
    run, _ = RunStore.claim('sim_demo_product_a', {'kind': 'real_execution', 'model': {'model': 'fixture'}})
    RunStore.update('sim_demo_product_a', 'failed')
    with pytest.raises(ValueError):
        demos.install('product')
    assert RunStore.get('sim_demo_product_a')['status'] == 'failed'
    assert RunStore.get('sim_demo_product_a')['run_id'] == run['run_id']
    assert EventStore.page('sim_demo_product_a')['items'] == []


def test_demo_does_not_publish_completion_after_unexpected_saved_event(monkeypatch):
    original = EventStore.append
    def interrupt(simulation_id, event):
        original(simulation_id, event)
        raise RuntimeError('Synthetic interruption')
    monkeypatch.setattr(EventStore, 'append', interrupt)
    with pytest.raises(RuntimeError):
        demos.install('product')
    monkeypatch.setattr(EventStore, 'append', original)
    EventStore.append('sim_demo_product_a', {'event_id': 'unexpected', 'kind': 'post', 'content': 'extra'})
    RunStore.update('sim_demo_product_a', 'interrupted')
    with pytest.raises(ValueError):
        demos.install('product')
    assert RunStore.get('sim_demo_product_a')['status'] == 'interrupted'
    assert ReportManager.get_report('report_demo_product_a') is None


def test_new_demo_report_has_real_sections_with_valid_original_text_links():
    from app.services.research_workbench import ResearchWorkbench
    project_id = demos.install('contradiction')['project_id']
    workbench = ResearchWorkbench()
    report = ReportManager.get_report('report_demo_contradiction_a')
    assert len(report.outline.sections) == 2
    refs = workbench.references(project_id, limit=200)['items']
    related = [ref for ref in refs if ref['subject_id'] == report.report_id or
               ref['subject_id'].startswith(report.report_id + ':section:')]
    assert len(related) == 5  # Two report pointers, two real sections, one honest gap.
    assert {ref['subject_id'] for ref in related if ref['subject_type'] == 'report_section'} == {
        report.report_id + ':section:1', report.report_id + ':section:2'}
    assert sum(ref['validation']['location_status'] == 'valid' for ref in related) == 4
    original_ids = {ref['reference_id'] for ref in refs}
    demos.install('contradiction')
    assert {ref['reference_id'] for ref in workbench.references(project_id, limit=200)['items']} == original_ids


def test_existing_demo_backfills_only_report_links_without_rewriting_history(monkeypatch):
    from pathlib import Path
    from app.services.research_workbench import ResearchWorkbench
    original_save = ReportManager.save_report
    def interrupt(report):
        raise RuntimeError('before synthetic report save')
    monkeypatch.setattr(ReportManager, 'save_report', interrupt)
    with pytest.raises(RuntimeError):
        demos.install('contradiction')
    monkeypatch.setattr(ReportManager, 'save_report', original_save)
    run = RunStore.get('sim_demo_contradiction_a')
    legacy = Report('report_demo_contradiction_a', run['simulation_id'], '', '舊合成示範', ReportStatus.COMPLETED,
                    markdown_content='# 既有報告\n\n不能改寫的保存文字', run_id=run['run_id'],
                    manifest={'kind': 'synthetic_fixture'})
    original_save(legacy)
    folder = Path(ReportManager.REPORTS_DIR) / legacy.report_id
    saved_bytes = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    project_id = demos.install('contradiction')['project_id']
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == saved_bytes
    assert RunStore.get(run['simulation_id'])['run_id'] == run['run_id']
    refs = ResearchWorkbench().references(project_id, subject_type='report', subject_id=legacy.report_id)['items']
    assert len(refs) == 3
    assert sum(ref['validation']['location_status'] == 'valid' for ref in refs) == 2
    assert not ResearchWorkbench().references(project_id, subject_type='report_section', subject_id=legacy.report_id + ':section:1')['items']
    first_ids = {ref['reference_id'] for ref in refs}
    demos.install('contradiction')
    assert {ref['reference_id'] for ref in ResearchWorkbench().references(
        project_id, subject_type='report', subject_id=legacy.report_id)['items']} == first_ids


def test_reference_idempotency_is_atomic_and_conflicting_payload_is_rejected():
    from concurrent.futures import ThreadPoolExecutor
    from app.services.research_workbench import ResearchWorkbench
    workbench = ResearchWorkbench()
    pid = workbench.create('相同引用')['project_id']
    def save(_):
        return workbench.evidence.add_reference(pid, 'report', 'saved_report', 'user_assumption', 'insufficient',
                                               note='合成假設', idempotency_key='fixture-link')
    with ThreadPoolExecutor(max_workers=2) as pool:
        refs = list(pool.map(save, range(2)))
    assert refs[0] == refs[1]
    assert workbench.evidence.list_references(pid)['total'] == 1
    with pytest.raises(ValueError, match='Idempotency'):
        workbench.evidence.add_reference(pid, 'report', 'saved_report', 'user_assumption', 'supports',
                                         note='合成假設', idempotency_key='fixture-link')
    other = workbench.create('另一研究')['project_id']
    other_ref = workbench.evidence.add_reference(other, 'report', 'saved_report', 'user_assumption', 'insufficient',
                                                note='合成假設', idempotency_key='fixture-link')
    assert other_ref['reference_id'] != refs[0]['reference_id']
