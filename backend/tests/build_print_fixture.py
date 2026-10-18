"""Rebuild a synthetic print fixture using the real ResearchWorkbench exporter.

Run in the offline Docker test environment with only /artifact writable.
No source uploads, existing ledgers, provider calls or hand-written HTML.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROWS = 72


class InspectHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.svg = self.tables = self.scripts = 0
        self.external_resources = []

    def handle_starttag(self, tag, attrs):
        if tag == 'svg':
            self.svg += 1
        if tag == 'table':
            self.tables += 1
        if tag == 'script':
            self.scripts += 1
        for key, value in attrs:
            if key in ('src', 'href') and value and value.startswith(('http:', 'https:', '//')):
                self.external_resources.append(value)


def build(output_dir):
    # A test must fail if any code unexpectedly attempts network access.
    def no_network(*_args, **_kwargs):
        raise AssertionError('Synthetic print fixture cannot open a network connection')
    socket.create_connection = no_network
    socket.socket.connect = no_network
    from app.config import Config
    from app.models.execution import RunStore
    from app.models.project import ProjectManager
    from app.services.event_store import EventStore
    from app.services.report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
    from app.services.research_workbench import ResearchWorkbench
    from app.services.simulation_manager import SimulationManager
    from app.storage import database

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mirofish-print-fixture-') as temporary:
        temporary = Path(temporary)
        os.environ['MIROFISH_WORKBENCH_DB'] = str(temporary / 'ledger.sqlite3')
        Config.UPLOAD_FOLDER = str(temporary / 'uploads')
        Config.OASIS_SIMULATION_DATA_DIR = str(temporary / 'simulations')
        ProjectManager.PROJECTS_DIR = str(temporary / 'projects')
        SimulationManager.SIMULATION_DATA_DIR = str(temporary / 'simulations')
        ReportManager.REPORTS_DIR = str(temporary / 'reports')
        workbench = ResearchWorkbench()
        pid = workbench.create('繁體中文長報告列印驗收｜純合成資料',
            '檢查跨頁長表格、繁體中文字型、原文引用、品質 SVG 與 A4 列印排版；本報告沒有真人或即時研究資料。')['project_id']
        with database() as db:
            db.execute('INSERT INTO research_meta(project_id,demo) VALUES(?,?)', (pid, 'synthetic-print-fixture-v1'))

        texts = ['合成來源甲：這段繁體中文原文僅供列印驗收，包含臺灣、資訊、檢核與觀察等文字。',
                 '合成來源乙：此處刻意保存另一種說法，示範相反引用；不代表真實世界已有證據。']
        pointers = []
        for index, text in enumerate(texts):
            saved = workbench.save_source(pid, title=f'列印合成來源 {index + 1}', source_type='synthetic_fixture',
                identity=f'print-fixture:{index}', content=text, parser_version='print-fixture-v1')
            span = workbench.evidence.create_span(saved['version']['version_id'], 0, len(text), text)
            pointers.append((saved, span))
        workbench.save_source(pid, title='刻意缺失的合成來源', source_type='synthetic_fixture',
            identity='print-fixture:missing', content=None, status='missing', parser_version='print-fixture-v1')
        run, _ = RunStore.claim('sim_print_fixture', {
            'project_id': pid, 'kind': 'synthetic_fixture', 'generator_version': 'print-fixture-v1',
            'source_versions': [saved['version']['version_id'] for saved, _ in pointers],
            'model': {'provider': 'none', 'model': 'deterministic_fixture'}, 'roles': ['合成角色'],
            'scenario': {'purpose': 'print_acceptance'}, 'platforms': ['twitter'], 'seed': 72,
            'budget': {'external_calls': 0}, 'reported_cost': {'value': 0, 'source': 'synthetic_fixture'},
        })
        for index in range(3):
            EventStore.append('sim_print_fixture', {'event_id': f'print_event_{index}', 'platform': 'twitter',
                'agent_id': 'fixture', 'round': index + 1, 'kind': 'post', 'content': f'合成列印事件 {index + 1}',
                'observed_at': f'2026-01-01T00:00:0{index}+00:00', 'run_id': run['run_id'], 'attempt_id': run['attempt_id']})
        RunStore.update('sim_print_fixture', 'completed', graph_ready=False, fixture_complete=True)

        table_lines = ['| 列識別碼 | 繁體中文觀察 | 保存方式 | 解讀限制 |', '| --- | --- | --- | --- |']
        for number in range(1, ROWS + 1):
            table_lines.append(f'| PRT_ROW_{number:03d} | 第 {number:02d} 列：合成角色觀察公共廣場與河岸環境。'
                '此段較長文字用來檢查欄位換行、中文字形及列印時的表格邊界。'
                '每列都有獨立編號，方便核對是否跨頁遺漏。 | 保存原文與版本；不連線取得新資料。'
                '引句定位採字元位置，保留繁體中文標點。 | 純合成資料；不是預測、調查統計或模型準確率。 |')
        table_markdown = '\n'.join(table_lines)
        outline = ReportOutline('72 列繁體中文表格與引用驗收',
            '純合成列印測試；內容由本機固定規則建立，沒有模型生成。', [ReportSection('跨頁長表格', table_markdown)])
        report = Report('report_print_fixture', 'sim_print_fixture', '', '純合成列印驗收', ReportStatus.COMPLETED,
            outline=outline, markdown_content='# 純合成列印驗收\n\n以下 72 列是排版測試資料，不能當作研究結論。\n\n'
            '## 跨頁長表格\n\n' + table_markdown + '\n\n## 表格結束檢核\n\n'
            'PRINT_TABLE_END：應能在前方找到 PRT_ROW_001 到 PRT_ROW_072，並核對後續引用與品質圖表。',
            created_at='2026-01-01T00:00:00+00:00', completed_at='2026-01-01T00:00:03+00:00',
            run_id=run['run_id'], manifest={'kind': 'synthetic_fixture', 'generator_version': 'print-fixture-v1', 'external_calls': 0})
        ReportManager.save_report(report)
        for index, (saved, span) in enumerate(pointers):
            workbench.evidence.add_reference(pid, 'report_section', report.report_id + ':section:1',
                'source_record', 'supports' if index == 0 else 'contradicts',
                source_id=saved['source']['source_id'], version_id=saved['version']['version_id'], span_id=span['span_id'],
                note='純合成引用；只驗證保存文字的定位，不代表支持關係已經過語意評審。')
        workbench.evidence.add_reference(pid, 'report', report.report_id, 'source_record', 'insufficient',
            source_id='src_fixture_unavailable', version_id='ver_fixture_unavailable', span_id='span_fixture_unavailable',
            allow_missing=True, note='刻意缺失的合成引用；應清楚顯示缺口。')

        document, content_type = workbench.export(pid, 'html')
        export_json, _ = workbench.export(pid, 'json')
        export_data = json.loads(export_json)
        parser = InspectHTML()
        parser.feed(document)
        assert parser.svg >= 1 and parser.scripts == 0 and not parser.external_resources
        assert all(document.count(f'<td>PRT_ROW_{number:03d}</td>') == 1 for number in range(1, ROWS + 1))
        assert 'PRINT_TABLE_END' in document and '<thead>' in document
        assert export_data['quality']['source_preservation']['numerator'] == 2
        assert export_data['quality']['source_preservation']['denominator'] == 3
        assert export_data['quality']['citation_location']['numerator'] == 2
        assert export_data['quality']['citation_location']['denominator'] == 3
        html_bytes = document.encode('utf-8')
        (output_dir / 'long-report.html').write_bytes(html_bytes)
        renderer = Path(__file__).resolve().parents[1] / 'app' / 'services' / 'report_export.py'
        manifest = {
            'fixture': 'synthetic-print-fixture-v1', 'contains_live_data': False, 'external_calls': 0,
            'created_at': datetime.now(timezone.utc).isoformat(), 'report_table_rows': ROWS,
            'sources': 3, 'references': 3, 'valid_source_references': 2, 'missing_source_references': 1,
            'quality_svg_count': parser.svg, 'html_table_count': parser.tables, 'script_count': parser.scripts,
            'content_type': content_type, 'export_version': export_data['export_version'],
            'artifact': {'file': 'long-report.html', 'bytes': len(html_bytes), 'sha256': hashlib.sha256(html_bytes).hexdigest()},
            'renderer': {'file': 'backend/app/services/report_export.py', 'sha256': hashlib.sha256(renderer.read_bytes()).hexdigest()},
            'generator': {'file': 'backend/tests/build_print_fixture.py', 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            'reproducibility': 'Fixed synthetic content and counts; generated record IDs and storage timestamps vary per rebuild.',
            'visual_review_status': 'pending_browser_print_review',
            'checks': ['All 72 unique table rows exported through ResearchWorkbench.export',
                       'Real product renderer produced inline quality SVG without scripts or external resources',
                       'Saved quote references and an explicit missing reference included',
                       'Ephemeral ledger, reports, sources and simulation folders only'],
        }
        (output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir), ensure_ascii=False, indent=2))
