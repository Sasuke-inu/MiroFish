"""Explicit, deterministic synthetic examples; no provider, crawl or graph calls."""
import hashlib
import json
import threading

from .research_workbench import ResearchWorkbench
from .evidence_store import EvidenceError
from ..storage import database
from ..models.execution import RunStore, public_manifest

CATALOG = [
    {'id': 'product', 'title': '產品方案比較', 'description': '比較月付與年付方案的合成討論。', 'kind': 'synthetic_fixture'},
    {'id': 'story', 'title': '故事角色互動', 'description': '虛構村落中兩位角色的選擇與互動。', 'kind': 'synthetic_fixture'},
    {'id': 'contradiction', 'title': '相互矛盾的來源', 'description': '保留相反記載、缺失引用及更新前版本。', 'kind': 'synthetic_fixture'},
]
_LOCK = threading.Lock()


def install(demo_id):
    item = next((row for row in CATALOG if row['id'] == demo_id), None)
    if not item:
        raise EvidenceError('找不到此示範。')
    workbench = ResearchWorkbench()
    # Serialized cross-process claim. A crash leaves the same partial fixture
    # identity and repeatable seed operations; it cannot create paid work.
    with _LOCK:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT project_id FROM demo_installations WHERE demo_id=?', (demo_id,)).fetchone()
            if row:
                project_id = row['project_id']
            else:
                project = workbench.create(item['title'], '合成示範：檢查來源、回放事件及比較設定；不是模型結果。')
                project_id = project['project_id']
                db.execute('INSERT INTO demo_installations VALUES(?,?)', (demo_id, project_id))
                db.execute('INSERT INTO research_meta(project_id,demo) VALUES(?,?)', (project_id, 'synthetic-fixture-v1'))
        _seed(workbench, project_id, demo_id)
    return {'project_id': project_id, 'kind': 'synthetic_fixture', 'external_calls': 0}


def catalog():
    """Catalog entries plus the installed project id, or None when uninstalled."""
    ResearchWorkbench()  # creates demo_installations and the research ledger
    with database() as db:
        installed = {row['demo_id']: row['project_id']
                     for row in db.execute('SELECT demo_id, project_id FROM demo_installations')}
    return [{**item, 'project_id': installed.get(item['id'])} for item in CATALOG]


def _seed(workbench, project_id, demo_id):
    from .event_store import EventStore
    from .report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
    evidence = workbench.evidence
    texts = {
        'product': ['合成訪談 A：使用者偏好低月費，願意逐月評估。', '合成訪談 B：使用者重視全年服務保障，接受年付。'],
        'story': ['虛構角色阿禾希望修復橋梁，讓旅人安全通行。', '虛構角色小杉擔心施工破壞河岸，要求先觀察生態。'],
        'contradiction': ['合成來源 A 記載：廣場在週六開放。', '合成來源 B 記載：廣場在週六關閉。'],
    }[demo_id]
    existing_refs = evidence.list_references(project_id, limit=200)['items']
    versions, pointers = [], []
    for index, text in enumerate(texts):
        saved = workbench.save_source(project_id, title=f'合成來源 {index+1}', source_type='synthetic_fixture',
                                     identity=f'fixture:{index}', content=text, parser_version='fixture-generator-v1')
        versions.append(saved['version']['version_id'])
        span = evidence.create_span(saved['version']['version_id'], 0, len(text), text)
        pointers.append({'source_id': saved['source']['source_id'], 'version_id': saved['version']['version_id'],
                         'span_id': span['span_id'], 'text': text, 'relation': 'supports' if index == 0 else 'contradicts'})
        if not any(ref['subject_id'] == f'conclusion-{index}' for ref in existing_refs):
            evidence.add_reference(project_id, 'conclusion', f'conclusion-{index}', 'source_record',
                                   'supports' if index == 0 else 'contradicts',
                                   source_id=saved['source']['source_id'], version_id=saved['version']['version_id'],
                                   span_id=span['span_id'], note='合成引用；只驗證定位，未做語意評審。')
    if not any(ref['category'] == 'user_assumption' for ref in existing_refs):
        evidence.add_reference(project_id, 'scenario', 'shared-assumption', 'user_assumption', 'insufficient',
                               note='示範假設：只觀察兩位虛構角色，不代表真實人口。')
    if demo_id == 'contradiction':
        first_source = next(row for row in workbench.all_sources(project_id) if row['identity'] == 'fixture:0')
        evidence.add_version(first_source['source_id'], '更新後合成來源 A：廣場改為週日開放。', parser_version='fixture-generator-v2')
        if not any(ref['subject_id'] == 'missing-proof' for ref in existing_refs):
            evidence.add_reference(project_id, 'conclusion', 'missing-proof', 'source_record', 'insufficient',
                                   source_id='src_unavailable_fixture', version_id='ver_unavailable_fixture',
                                   span_id='span_unavailable_fixture', allow_missing=True, note='故意缺失的示範資料，不能當作證明。')
    for variant in ('a', 'b'):
        simulation_id = f'sim_demo_{demo_id}_{variant}'
        manifest = {'project_id': project_id, 'kind': 'synthetic_fixture', 'generator_version': 'fixture-generator-v1',
                    'source_versions': versions, 'assumptions': ['兩位虛構角色'],
                    'scenario': {'version': 1, 'variant': variant}, 'roles': ['阿禾', '小杉'],
                    'model': {'provider': 'none', 'model': 'deterministic_fixture'}, 'platforms': ['twitter', 'reddit'],
                    'max_rounds': 3, 'seed': 0, 'budget': {'external_calls': 0}, 'reported_cost': {'value': 0, 'currency': None, 'source': 'synthetic_fixture'}}
        run, _ = RunStore.claim(simulation_id, manifest)
        if run['manifest'] != public_manifest(manifest) or run['manifest'].get('kind') != 'synthetic_fixture':
            raise EvidenceError('既有執行與此合成示範的保存設定不符，已保留原紀錄。')
        expected_events = []
        for sequence in range(1, 7):
            platform = 'twitter' if sequence % 2 else 'reddit'
            content = f'合成事件 {sequence}：' + (texts[sequence % 2] if variant == 'a' or sequence < 4 else '角色改為先詢問更多資料。')
            event = EventStore.append(simulation_id, {'event_id': f'fixture_{demo_id}_{variant}_{sequence}',
                              'platform': platform, 'agent_id': str(sequence % 2), 'round': (sequence+1)//2,
                              'simulation_time': f'round-{(sequence+1)//2}',
                              'observed_at': f'2026-01-01T00:00:0{sequence}+00:00',
                              'kind': 'post' if sequence < 4 else 'comment', 'content': content,
                              'run_id': run['run_id'], 'attempt_id': run['attempt_id']})
            expected_events.append(event)
        preserved = EventStore.page(simulation_id, limit=100)
        if preserved['has_more'] or preserved['items'] != expected_events:
            raise EvidenceError('合成示範的事件紀錄不完整或有額外事件，不能標示完成。')
        # A synthetic fixture can finish an interrupted seed only after its
        # immutable manifest and every deterministic event have been checked.
        # This does not restart a process, reset identity or promote real runs.
        if run['status'] != 'completed':
            RunStore.update(simulation_id, 'completed', graph_ready=False, fixture_complete=True,
                            completed_units=6, completion_basis='six deterministic synthetic events; no graph/model generation')
        report_id = f'report_demo_{demo_id}_{variant}'
        report = ReportManager.get_report(report_id)
        if not report:
            outline = ReportOutline(f'{demo_id} · 情境 {variant.upper()}',
                '合成示範，非模型執行結果。' + ('角色持續原有觀點。' if variant == 'a' else '角色在第 4 筆事件起詢問更多資料。'),
                [ReportSection(f'合成來源 {index + 1}', text) for index, text in enumerate(texts)])
            report = Report(report_id, simulation_id, '', '合成情境示範', ReportStatus.COMPLETED,
                            outline=outline,
                            markdown_content=f'# {demo_id} · 情境 {variant.upper()}\n\n合成示範，非模型執行結果。\n\n'
                            '兩位虛構角色在三輪、兩平台中留下 6 筆事件。\n\n'
                            '第 4 筆事件起，情境 B 改為詢問更多資料；情境 A 持續原有觀點。'
                            '\n\n相反資料同時保留；引用定位有效不代表內容已證實。\n\n' +
                            '\n'.join(section.to_markdown() for section in outline.sections),
                            created_at='2026-01-01T00:00:00+00:00', completed_at='2026-01-01T00:00:06+00:00',
                            run_id=run['run_id'], manifest={'kind': 'synthetic_fixture', 'source_versions': versions,
                                                         'generator_version': 'fixture-generator-v1', 'external_calls': 0})
            ReportManager.save_report(report)
        if report.run_id != run['run_id'] or report.manifest.get('kind') != 'synthetic_fixture':
            raise EvidenceError('保存報告不屬於此合成示範，已保留原紀錄。')
        _link_report_evidence(evidence, project_id, report, pointers, demo_id)


def _link_report_evidence(evidence, project_id, report, pointers, demo_id):
    """Append links to saved reports; never rewrite older fixture content."""
    for pointer in pointers:
        subjects = [('report', report.report_id)]
        # Old demos had no outline. Only link sections actually saved with the
        # exact fixture source text; never fabricate sections during reinstall.
        if report.outline:
            subjects.extend(('report_section', f'{report.report_id}:section:{index + 1}')
                for index, section in enumerate(report.outline.sections) if section.content == pointer['text'])
        for subject_type, subject_id in subjects:
            evidence.add_reference(project_id, subject_type, subject_id, 'source_record', pointer['relation'],
                source_id=pointer['source_id'], version_id=pointer['version_id'], span_id=pointer['span_id'],
                note='合成來源連結；支持或相反為示範宣告，只驗證原文定位，未做語意評審。',
                idempotency_key=f"demo-report-link:{subject_type}:{subject_id}:{pointer['span_id']}:{pointer['relation']}")
    if demo_id == 'contradiction':
        evidence.add_reference(project_id, 'report', report.report_id, 'source_record', 'insufficient',
            source_id='src_unavailable_fixture', version_id='ver_unavailable_fixture',
            span_id='span_unavailable_fixture', allow_missing=True, note='故意缺失的示範資料，不能當作證明。',
            idempotency_key=f'demo-report-link:{report.report_id}:missing-proof')
