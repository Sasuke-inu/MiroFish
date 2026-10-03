"""Offline synthetic event-store benchmark; no thresholds or live uploads."""
import gzip
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def measure():
    from app.config import Config
    from app.models.execution import RunStore
    from app.services.event_store import EventStore
    from app.services.report_agent import ReportManager
    results = []
    with tempfile.TemporaryDirectory(prefix='mirofish-event-benchmark-') as temporary:
        root = Path(temporary)
        os.environ['MIROFISH_WORKBENCH_DB'] = str(root / 'ledger.sqlite3')
        Config.OASIS_SIMULATION_DATA_DIR = str(root / 'simulations')
        ReportManager.REPORTS_DIR = str(root / 'reports')
        for count in (100, 1000, 10000):
            sim = f'sim_benchmark_{count}'
            run, _ = RunStore.claim(sim, {'kind': 'synthetic_benchmark', 'project_id': 'project_benchmark'})
            folder = Path(Config.OASIS_SIMULATION_DATA_DIR) / sim / 'reddit'
            folder.mkdir(parents=True)
            with (folder / 'actions.jsonl').open('w', encoding='utf-8') as output:
                for index in range(count):
                    output.write(json.dumps({'run_id': run['run_id'], 'attempt_id': run['attempt_id'],
                        'agent_id': index % 20, 'round': index // 20, 'action_type': 'CREATE_POST',
                        'simulation_time': index // 20, 'action_args': {'content': f'合成事件 {index}，用於測量本機事件分頁。'}},
                        ensure_ascii=False) + '\n')
            RunStore.update(sim, 'completed')
            start = perf_counter()
            ingested = EventStore.ingest(sim)
            ingest_ms = (perf_counter() - start) * 1000
            page_times = []
            for _ in range(5):
                start = perf_counter()
                page = EventStore.page(sim, limit=100)
                page_times.append((perf_counter() - start) * 1000)
            page_bytes = json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode()
            start = perf_counter()
            projection = EventStore.project(sim, count)
            projection_ms = (perf_counter() - start) * 1000
            projection_bytes = json.dumps(projection, ensure_ascii=False, separators=(',', ':')).encode()
            other_sim = sim + '_variant'
            other, _ = RunStore.claim(other_sim, {'kind': 'synthetic_benchmark', 'project_id': 'project_benchmark'})
            other_folder = Path(Config.OASIS_SIMULATION_DATA_DIR) / other_sim / 'reddit'
            other_folder.mkdir(parents=True)
            with (folder / 'actions.jsonl').open(encoding='utf-8') as source, (other_folder / 'actions.jsonl').open('w', encoding='utf-8') as target:
                for index, raw in enumerate(source):
                    event = json.loads(raw)
                    event.update(run_id=other['run_id'], attempt_id=other['attempt_id'])
                    if index == count - 1:
                        event['action_args']['content'] = '最後一筆合成差異'
                    target.write(json.dumps(event, ensure_ascii=False) + '\n')
            RunStore.update(other_sim, 'completed')
            EventStore.ingest(other_sim)
            start = perf_counter()
            comparison = EventStore.compare(sim, other_sim)
            compare_ms = (perf_counter() - start) * 1000
            compare_bytes = json.dumps(comparison, ensure_ascii=False, separators=(',', ':')).encode()
            assert ingested['total'] == count
            assert len(page['items']) == min(100, count)
            assert projection['event_count'] == count and len(projection['events']) == min(200, count)
            assert comparison['first_difference']['index'] == count
            results.append({'events': count, 'initial_ingest_ms': round(ingest_ms, 2),
                'page_limit': 100, 'page_latency_ms_median_5': round(statistics.median(page_times), 2),
                'page_latency_ms_max_5': round(max(page_times), 2),
                'page_payload_bytes': len(page_bytes), 'page_payload_gzip_bytes': len(gzip.compress(page_bytes)),
                'full_projection_ms': round(projection_ms, 2), 'projection_event_count': len(projection['events']),
                'projection_payload_bytes': len(projection_bytes),
                'projection_payload_gzip_bytes': len(gzip.compress(projection_bytes)),
                'compare_events_each_side': count, 'compare_ms': round(compare_ms, 2),
                'compare_payload_bytes': len(compare_bytes)})
    return {'fixture': 'synthetic_only', 'network': 'disabled by Docker caller',
            'timing_scope': 'Python service calls including ingest checks; excludes HTTP, browser and model work',
            'limitations': ['Single local container sample; not an end-to-end performance guarantee.',
                            'Projection reduces all saved events; comparison currently loads both completed event lists.'],
            'results': results}


if __name__ == '__main__':
    print(json.dumps(measure(), ensure_ascii=False, indent=2))
