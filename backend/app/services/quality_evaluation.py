"""Observational event-count comparisons; no model calls or accuracy claims."""
import hashlib
import json
from collections import defaultdict

from ..storage import database
from .event_store import EventStore

_LIMITS = [
    '只統計已保存的事件種類與數量，不代表內容正確、預測準確或因果關係。',
    '模型分組依保存的請求設定；代理服務實際路由到哪個模型可能仍未知。',
    '隨機狀態及外部影響未完全控制；相同設定下的觀察範圍不是信賴區間。',
    '合成示範與真實執行分開計算，合成結果不能當作真實模型的驗證。',
]
_IDENTITY = {'simulation_id', 'run_id', 'attempt_id', 'graph_id', 'project_id', 'entity_uuid', 'source_entity_uuid'}
_BOOKKEEPING = _IDENTITY | {'created_at', 'updated_at', 'captured_at', 'model_frozen_at', 'completed_at',
    'profile_hashes', 'config_sha256', 'reported_cost', 'model_resolution'}
_MESSAGES = {
    'legacy_identity': '歷史紀錄沒有可驗證的執行身分。',
    'model_unknown': '缺少完整的請求模型設定。',
    'sources_unknown': '缺少可核對的來源版本或建圖沿革。',
    'roles_unknown': '缺少完整的角色快照。',
    'configuration_unknown': '缺少可比較的完整設定快照。',
    'execution_unverified': '執行尚未確認完整平台結果與圖譜寫入完成。',
    'events_unavailable': '沒有可統計的保存事件。',
    'events_incomplete': '事件來源有缺口，不能當作完整樣本。',
    'no_matching_samples': '尚無其他符合分組條件的已完成樣本。',
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _without_identity(value):
    if isinstance(value, dict):
        return {key: _without_identity(item) for key, item in value.items() if key not in _IDENTITY}
    if isinstance(value, list):
        return [_without_identity(item) for item in value]
    return value


class QualityEvaluation:
    @staticmethod
    def _exclusion(run, reason):
        return {'simulation_id': run.get('simulation_id'), 'run_id': run.get('run_id'), 'reason': reason,
                'message': _MESSAGES.get(reason, '執行尚未完整完成，不能納入已完成樣本。')}

    @staticmethod
    def _input_problem(run):
        if run.get('legacy') or not run.get('run_id') or not run.get('manifest'):
            return 'legacy_identity'
        if run.get('status') != 'completed':
            return 'status_' + str(run.get('status') or 'unknown')
        manifest = run['manifest']
        model = manifest.get('model')
        if not isinstance(model, dict) or not model.get('provider') or not model.get('model'):
            return 'model_unknown'
        synthetic = manifest.get('kind') == 'synthetic_fixture'
        if not synthetic and run.get('graph_ready') is not True:
            return 'execution_unverified'
        sources = manifest.get('source_versions')
        if not isinstance(sources, list) or not sources:
            return 'sources_unknown'
        if not synthetic and (manifest.get('source_lineage_status') != 'graph_build_snapshot'
                or not all(isinstance(source, dict) and all(source.get(key) for key in ('source_id', 'version_id', 'sha256')) for source in sources)):
            return 'sources_unknown'
        if not isinstance(manifest.get('roles'), list) or not manifest['roles']:
            return 'roles_unknown'
        if not synthetic and manifest.get('roles_snapshot_status') != 'complete':
            return 'roles_unknown'
        if not synthetic and not manifest.get('configuration_comparison_sha256'):
            return 'configuration_unknown'
        if synthetic and not any(isinstance(manifest.get(key), dict) for key in ('scenario', 'configuration')):
            return 'configuration_unknown'
        return None

    @staticmethod
    def _signature(manifest, include_model):
        selected = {key: _without_identity(value) for key, value in manifest.items() if key not in _BOOKKEEPING}
        selected['kind'] = 'synthetic_fixture' if manifest.get('kind') == 'synthetic_fixture' else 'real'
        model = {key: manifest['model'].get(key) for key in ('provider', 'base_url', 'model')}
        if include_model:
            selected['model'] = model
        else:
            selected.pop('model', None)
        selected['source_versions'] = sorted(selected['source_versions'], key=_json)
        if isinstance(selected.get('configuration'), dict):
            selected['configuration'] = {key: value for key, value in selected['configuration'].items()
                                          if key not in {'llm_model', 'llm_base_url'}}
        if isinstance(selected.get('preparation_model'), dict):
            selected['preparation_model'] = {key: selected['preparation_model'].get(key) for key in ('provider', 'base_url', 'model')}
        return _json(selected)

    @staticmethod
    def _counts(simulation_id):
        info = EventStore.ingest(simulation_id)
        if not info['total']:
            return None, 'events_unavailable'
        if info['capability'] != 'exact_event_projection':
            return None, 'events_incomplete'
        counts = {}
        with database() as db:
            for row in db.execute('''SELECT platform,json_extract(payload,'$.kind') AS kind,COUNT(*) AS n
                                      FROM workbench_events WHERE simulation_id=? GROUP BY platform,kind''', (simulation_id,)):
                counts[(row['platform'], row['kind'])] = row['n']
        return counts, None

    @classmethod
    def _metric(cls, eligible, excluded, include_model):
        buckets = defaultdict(list)
        for item in eligible:
            buckets[cls._signature(item['run']['manifest'], include_model)].append(item)
        groups, unmatched = [], []
        for signature, members in buckets.items():
            distinct_models = {_json(member['model']) for member in members}
            if len(members) < 2 or (not include_model and len(distinct_models) < 2):
                unmatched.extend(cls._exclusion(member['run'], 'no_matching_samples') for member in members)
                continue
            categories = sorted(set().union(*(set(member['counts']) for member in members)))
            counts = {}
            for platform, kind in categories:
                values = [{'run_id': member['run']['run_id'], 'count': member['counts'].get((platform, kind), 0)} for member in members]
                counts.setdefault(platform, {})[kind] = {'min': min(item['count'] for item in values),
                    'max': max(item['count'] for item in values), 'values': values}
            groups.append({'group_id': 'quality_' + hashlib.sha256(signature.encode()).hexdigest()[:20],
                'kind': 'synthetic_fixture' if members[0]['run']['manifest'].get('kind') == 'synthetic_fixture' else 'real',
                'sample_size': len(members), 'run_ids': [member['run']['run_id'] for member in members],
                'simulation_ids': [member['run']['simulation_id'] for member in members], 'kind_counts': counts,
                'models': [{'run_id': member['run']['run_id'], 'model': member['model']} for member in members]})
        return {'status': 'observed' if groups else 'not_evaluated',
                'calculation_version': 'recorded-event-counts-v1',
                'sample_size': sum(group['sample_size'] for group in groups), 'groups': groups,
                'excluded': [*excluded, *unmatched], 'limitations': list(_LIMITS), 'causal_claim': False,
                'model_basis': 'requested_configuration', 'cost': {'status': 'unknown', 'value': None, 'currency': None}}

    @classmethod
    def evaluate(cls, runs):
        eligible, excluded, seen = [], [], set()
        for run in runs:
            if run.get('run_id') and run['run_id'] in seen:
                continue
            if run.get('run_id'):
                seen.add(run['run_id'])
            problem = cls._input_problem(run)
            if problem:
                excluded.append(cls._exclusion(run, problem))
                continue
            try:
                counts, problem = cls._counts(run['simulation_id'])
            except ValueError:
                counts, problem = None, 'events_unavailable'
            if problem:
                excluded.append(cls._exclusion(run, problem))
                continue
            eligible.append({'run': run, 'counts': counts,
                             'model': {key: run['manifest']['model'].get(key) for key in ('provider', 'base_url', 'model')}})
        return {'repeat_stability': cls._metric(eligible, excluded, include_model=True),
                'model_sensitivity': cls._metric(eligible, excluded, include_model=False)}
