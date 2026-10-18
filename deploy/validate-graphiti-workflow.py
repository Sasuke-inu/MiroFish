"""Exercise real MiroFish endpoints with an explicitly fictional local scenario.

Run with: uv run --no-project --with httpx --python 3.12
          deploy/validate-graphiti-workflow.py <phase>
Receipts are saved between phases; no mutation is silently retried.
"""
import argparse
import json
import hashlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / 'deploy' / 'graphiti-validation.json'
state = json.loads(RECEIPTS.read_text(encoding='utf-8')) if RECEIPTS.exists() else {
    'started_at': datetime.now(timezone.utc).isoformat(), 'scenario': 'fictional cafe', 'evidence': {}
}
client = httpx.Client(base_url='http://127.0.0.1:3100', timeout=300,
                      headers={'Accept-Language': 'zh-TW'}, trust_env=False)


def save():
    RECEIPTS.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def api(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    value = response.json()
    if response.is_error or value.get('success') is False:
        raise RuntimeError(f'{method} {path}: HTTP {response.status_code}: {value.get("error", value)}')
    return value.get('data', value)


def poll(path, *, json_body=None, timeout=1500, status_key='status', terminal='completed'):
    started = time.monotonic()
    previous = None
    while time.monotonic() - started < timeout:
        result = api('POST' if json_body is not None else 'GET', path, **({'json': json_body} if json_body is not None else {}))
        display = (result.get(status_key), result.get('progress'), result.get('message'))
        if display != previous:
            print(json.dumps({'stage': path, 'status': display[0], 'progress': display[1], 'message': display[2]}, ensure_ascii=True), flush=True)
            previous = display
        if result.get(status_key) == terminal:
            return result
        if result.get(status_key) in ('failed', 'error', 'stopped'):
            raise RuntimeError(f'Workflow failed: {result}')
        time.sleep(5)
    raise TimeoutError(f'Workflow did not complete: {path}')


def upload():
    if 'project_id' in state:
        raise RuntimeError('An upload receipt already exists; reuse the following phase instead of uploading again')
    ready = api('GET', '/api/system/status')
    assert ready['ready'] and ready['graph_provider'] == 'graphiti' and ready['embedding'] == 'local'
    source = ROOT / 'deploy' / 'smoke-seed.md'
    with source.open('rb') as file:
        result = api('POST', '/api/graph/ontology/generate',
                     files={'files': (source.name, file, 'text/markdown')},
                     data={'project_name': state.get('project_name', '本機圖譜驗證：橙子小屋（虛構）'),
                           'simulation_requirement': '這是完全虛構的軟體測試。模擬小橙、小青、小藍和小紫討論免費桌遊活動，觀察安靜需求與鄰里交流是否能兼顧。只使用文件明確提到的角色，不新增虛構人物。請使用繁體中文。'})
    state['project_id'] = result['project_id']
    state['evidence']['upload'] = {'status': 'passed', 'entity_types': len(result['ontology']['entity_types']),
                                   'edge_types': len(result['ontology']['edge_types'])}
    save()
    print(json.dumps({'project_id': state['project_id'], **state['evidence']['upload']}, ensure_ascii=False), flush=True)


def build():
    project = api('GET', f'/api/graph/project/{state["project_id"]}')
    if project['status'] != 'graph_completed' and 'graph_task_id' not in state:
        result = api('POST', '/api/graph/build', json={'project_id': state['project_id']})
        state['graph_task_id'] = result['task_id']
        save()
    if project['status'] != 'graph_completed':
        poll(f'/api/graph/task/{state["graph_task_id"]}')
    project = api('GET', f'/api/graph/project/{state["project_id"]}')
    state['graph_id'] = project['graph_id']
    graph = api('GET', f'/api/graph/data/{state["graph_id"]}')
    assert graph['node_count'] > 0 and graph['edge_count'] > 0
    assert all(edge.get('episodes') for edge in graph['edges'])
    state['evidence']['build'] = {'status': 'passed', 'nodes': graph['node_count'], 'edges': graph['edge_count'],
                                'source_provenance': True, 'graph_id': state['graph_id']}
    save()
    print(json.dumps(state['evidence']['build'], ensure_ascii=False), flush=True)


def recover_upload():
    if 'project_id' in state:
        raise RuntimeError('An upload receipt already exists')
    matches = [project for project in api('GET', '/api/graph/project/list')
               if project['name'] == '本機圖譜驗證：橙子小屋（虛構）'
               and project['status'] == 'ontology_generated'
               and project['files'] == [{'filename': 'smoke-seed.md', 'size': (ROOT / 'deploy/smoke-seed.md').stat().st_size}]]
    assert len(matches) == 1, 'Recovery must identify one completed upload without guessing'
    project = matches[0]
    state['project_id'] = project['project_id']
    state['evidence']['upload'] = {'status': 'passed', 'entity_types': len(project['ontology']['entity_types']),
                                   'edge_types': len(project['ontology']['edge_types']),
                                   'receipt_recovered': 'Frontend update interrupted response; original project verified without resubmission'}
    save()
    print(json.dumps({'project_id': state['project_id'], **state['evidence']['upload']}, ensure_ascii=False), flush=True)


def rebuild():
    project = api('GET', f'/api/graph/project/{state["project_id"]}')
    assert project['status'] == 'failed', 'Only an unsuccessful test graph may be rebuilt'
    state.setdefault('repaired_attempts', []).append({'task_id': state.pop('graph_task_id'), 'error': project.get('error')})
    save()
    build()


def prepare():
    if 'simulation_id' not in state:
        result = api('POST', '/api/simulation/create', json={'project_id': state['project_id'], 'enable_twitter': True, 'enable_reddit': True})
        state['simulation_id'] = result['simulation_id']
        save()
    if 'prepare_task_id' not in state:
        entities = api('GET', f'/api/simulation/entities/{state["graph_id"]}')
        types = sorted({label for entity in entities['entities'] if entity['name'] in ('小橙', '小青', '小藍', '小紫')
                        for label in entity['labels'] if label != 'Entity'})
        assert types, 'Named fictional people must be classified into the requested entity types'
        result = api('POST', '/api/simulation/prepare', json={'simulation_id': state['simulation_id'], 'entity_types': types,
                     'use_llm_for_profiles': True, 'parallel_profile_count': 2})
        state['prepare_task_id'] = result['task_id']
        save()
    result = poll('/api/simulation/prepare/status', json_body={'task_id': state['prepare_task_id']})
    simulation = api('GET', f'/api/simulation/{state["simulation_id"]}')
    assert simulation['status'] == 'ready' and simulation['profiles_count'] > 0
    profiles = json.loads((ROOT / 'backend/uploads/simulations' / state['simulation_id'] / 'reddit_profiles.json').read_text(encoding='utf-8'))
    assert all(len(profile['persona']) >= 100 for profile in profiles), 'Detailed model profiles must not silently fall back to node summaries'
    state['evidence']['prepare'] = {'status': 'passed', 'profiles': simulation['profiles_count'],
                                  'twitter': simulation['enable_twitter'], 'reddit': simulation['enable_reddit']}
    save()
    print(json.dumps({'simulation_id': state['simulation_id'], **state['evidence']['prepare']}, ensure_ascii=False), flush=True)


def fresh():
    current = api('GET', f'/api/simulation/{state["simulation_id"]}/run-status')
    assert current['runner_status'] == 'completed'
    report = api('GET', f'/api/report/{state["report_id"]}')
    assert report['status'] == 'completed'
    api('POST', '/api/simulation/close-env', json={'simulation_id': state['simulation_id'], 'timeout': 30})
    graph = api('GET', f'/api/graph/data/{state["graph_id"]}')
    (ROOT / 'deploy/graphiti-restart-before.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    state['evidence']['report']['status'] = 'needs_rerun_with_registered_tools'
    state['evidence']['test_conditions']['seed_poster_correction'] = 'Resolve the cafe owner by name instead of assuming numeric agent ID zero'
    (ROOT / 'deploy/graphiti-previous-validation.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    previous = {key: state[key] for key in ('project_id', 'simulation_id', 'graph_id', 'report_id')}
    state.clear()
    state.update(started_at=datetime.now(timezone.utc).isoformat(), scenario='fictional cafe', evidence={},
                 project_name='本機圖譜驗證：橙子小屋（完成版）', previous_validation=previous)
    save()
    print(json.dumps({'fresh_validation': True, 'previous_data_preserved': True}), flush=True)


def restart_check():
    before = json.loads((ROOT / 'deploy/graphiti-restart-before.json').read_text(encoding='utf-8'))
    after = api('GET', f'/api/graph/data/{before["graph_id"]}')
    assert before == after, 'Graph facts, IDs, source episodes and times must survive container restart'
    ready = api('GET', '/api/system/status')
    assert ready['ready'] and ready['graph_provider'] == 'graphiti'
    state['evidence']['restart'] = {'status': 'passed', 'preserved_graph': before['graph_id'],
                                  'nodes': after['node_count'], 'edges': after['edge_count'], 'full_record_comparison': True}
    save()
    print(json.dumps(state['evidence']['restart']), flush=True)


def run():
    if not state.get('run_started'):
        result = api('POST', '/api/simulation/start', json={'simulation_id': state['simulation_id'], 'platform': 'parallel',
                     'max_rounds': 2, 'enable_graph_memory_update': True, 'force': bool(state.get('retry_run'))})
        state['run_started'] = True
        save()
    result = poll(f'/api/simulation/{state["simulation_id"]}/run-status', status_key='runner_status', timeout=1500)
    assert result['twitter_actions_count'] > 0 and result['reddit_actions_count'] > 0, 'Both platforms must perform real actions'
    for platform in ('twitter', 'reddit'):
        action_file = ROOT / 'backend/uploads/simulations' / state['simulation_id'] / platform / 'actions.jsonl'
        actions = [json.loads(line) for line in action_file.read_text(encoding='utf-8').splitlines()]
        assert any(action.get('round', 0) > 0 and 'action_type' in action for action in actions), 'Seed posts alone are not a model simulation'
    graph = api('GET', f'/api/graph/data/{state["graph_id"]}')
    state['evidence']['run'] = {'status': 'passed', 'result': result, 'nodes_after': graph['node_count'], 'edges_after': graph['edge_count']}
    save()
    print(json.dumps({'run_completed': True, 'nodes_after': graph['node_count'], 'edges_after': graph['edge_count']}, ensure_ascii=False), flush=True)


def activate():
    """Prepare only this fictional test for two active, bounded model rounds."""
    simulation_id = state['simulation_id']
    status = api('GET', f'/api/simulation/{simulation_id}/run-status')
    if status['runner_status'] != 'idle':
        assert status['total_actions_count'] == 0, 'Never replace a run containing actual participant actions'
        stopped = api('POST', '/api/simulation/stop', json={'simulation_id': simulation_id})
        assert stopped['runner_status'] == 'stopped'
    config_path = ROOT / 'backend/uploads/simulations' / simulation_id / 'simulation_config.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    (ROOT / 'deploy/graphiti-generated-config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    config['time_config'].update(agents_per_hour_min=1, agents_per_hour_max=1,
                               peak_activity_multiplier=1, off_peak_activity_multiplier=1)
    for agent in config['agent_configs']:
        agent.update(active_hours=list(range(24)), activity_level=1)
    owner = next(agent for agent in config['agent_configs'] if agent['entity_name'] == '小橙')
    config['event_config']['initial_posts'] = [{'poster_agent_id': owner['agent_id'], 'poster_type': owner['entity_type'],
        'content': '我是小橙。橙子小屋預計週六舉辦免費桌遊活動。小青會協助安排，小藍關心噪音，小紫想認識鄰居。大家覺得怎麼安排比較好？這是虛構測試。'}]
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if status['runner_status'] != 'idle':
        state['repaired_attempts'].append({'stage': 'run', 'total_actions': 0,
            'reason': 'Two midnight rounds had no active actors; monitor also waited indefinitely for the interview process'})
    state['evidence']['test_conditions'] = {'rounds': 2, 'active_actors_per_round': 1,
        'all_hours_enabled_for_test_only': True, 'seed_posts_per_platform': 1, 'original_config_preserved': True}
    state['run_started'] = False
    state['retry_run'] = status['runner_status'] != 'idle'
    save()
    print(json.dumps({'stage': 'test_configuration', 'stopped': True, **state['evidence']['test_conditions']}), flush=True)


def close_failed_environment():
    current = api('GET', f'/api/simulation/{state["simulation_id"]}/run-status')
    assert current['runner_status'] == 'failed'
    result = api('POST', '/api/simulation/close-env', json={'simulation_id': state['simulation_id'], 'timeout': 30})
    state['repaired_attempts'].append({'stage': 'graph_memory', 'simulation_id': state['simulation_id'], 'graph_id': state['graph_id'],
                                     'error': current['error'], 'actions_preserved': current['total_actions_count']})
    save()
    print(json.dumps({'environment_closed': result.get('success')}), flush=True)


def reset_graph():
    # Rebuild only this explicitly fictional validation graph after correcting
    # the extraction contract; never retry a partially applied episode.
    assert state['scenario'] == 'fictional cafe'
    run_status = api('GET', f'/api/simulation/{state["simulation_id"]}/run-status')
    if run_status['runner_status'] == 'stopping':
        # Explicitly acknowledge the saved failed test after the old producer
        # and updater have stopped. The failure receipt is retained above.
        assert run_status['error'] and run_status['twitter_completed'] and run_status['reddit_completed']
        api('POST', '/api/simulation/stop', json={'simulation_id': state['simulation_id']})
    result = api('POST', f'/api/graph/project/{state["project_id"]}/reset')
    assert result['status'] == 'ontology_generated'
    state['repaired_simulation_ids'] = state.get('repaired_simulation_ids', []) + [state['simulation_id']]
    for key in ('simulation_id', 'prepare_task_id', 'graph_task_id', 'graph_id', 'run_started', 'retry_run'):
        state.pop(key, None)
    for key in ('build', 'prepare', 'run'):
        state['evidence'].pop(key, None)
    save()
    build()


def report():
    if 'report_id' not in state:
        result = api('POST', '/api/report/generate', json={'simulation_id': state['simulation_id']})
        state['report_id'] = result['report_id']
        state['report_task_id'] = result['task_id']
        save()
    result = poll('/api/report/generate/status', json_body={'task_id': state['report_task_id'], 'simulation_id': state['simulation_id']}, timeout=2400)
    report = api('GET', f'/api/report/{state["report_id"]}')
    download = client.get(f'/api/report/{state["report_id"]}/download')
    download.raise_for_status()
    assert len(download.content) > 100
    logs = ROOT / 'backend/uploads/reports' / state['report_id'] / 'agent_log.jsonl'
    activity = [json.loads(line) for line in logs.read_text(encoding='utf-8').splitlines()]
    tool_calls = [entry for entry in activity if entry['action'] == 'tool_call']
    assert tool_calls, 'Report generation must actually retrieve evidence, not merely produce prose'
    for entry in activity:
        if entry['action'] == 'section_content':
            assert entry['details']['tool_calls_count'] >= 3, 'Each section needs real retrieval'
    path = ROOT / 'deploy' / 'graphiti-test-report.md'
    path.write_bytes(download.content)
    state['evidence']['report'] = {'status': 'passed', 'download_bytes': len(download.content),
                                 'actual_tool_calls': len(tool_calls), 'details': report}
    save()
    print(json.dumps({'report_id': state['report_id'], 'download_bytes': len(download.content)}, ensure_ascii=False), flush=True)


def archive_interview_failure():
    """Preserve the confirmed failed interview before preparing a new test run."""
    assert state['scenario'] == 'fictional cafe'
    assert state['evidence']['run']['status'] == 'passed' and state['evidence']['report']['status'] == 'passed'
    responses = ROOT / 'backend/uploads/simulations' / state['simulation_id'] / 'ipc_responses'
    failed = [json.loads(path.read_text(encoding='utf-8')) for path in responses.glob('*.json')]
    assert len(failed) == 1 and failed[0]['status'] == 'failed'
    assert failed[0]['error'] == "ChatAgent._aget_model_response() got an unexpected keyword argument 'num_tokens'"
    state['evidence']['single_interview'] = {'status': 'failed_before_repair', 'result': failed[0]}
    api('POST', '/api/simulation/close-env', json={'simulation_id': state['simulation_id'], 'timeout': 30})
    (ROOT / 'deploy/graphiti-interview-repair.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    state['preserved_pre_repair_simulation'] = {'simulation_id': state['simulation_id'], 'report_id': state['report_id']}
    state.setdefault('repaired_attempts', []).append({'stage': 'interview', 'error': failed[0]['error'],
                                                    'fix': 'OASIS agent wrapper removes the obsolete token-count keyword for CAMEL 0.2.90'})
    for key in ('simulation_id', 'prepare_task_id', 'run_started', 'retry_run', 'report_id', 'report_task_id', 'interaction_started'):
        state.pop(key, None)
    for key in ('prepare', 'run', 'report', 'test_conditions', 'single_interview'):
        state['evidence'].pop(key, None)
    save()
    print(json.dumps({'failed_receipt_preserved': True, 'previous_results_preserved': True}), flush=True)


def close_for_deploy():
    assert state['evidence']['run']['status'] == 'passed' and state['evidence']['report']['status'] == 'passed'
    result = api('POST', '/api/simulation/close-env', json={'simulation_id': state['simulation_id'], 'timeout': 30})
    assert result['success']
    graph = api('GET', f'/api/graph/data/{state["graph_id"]}')
    (ROOT / 'deploy/graphiti-final-restart-before.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    state['evidence']['test_environment'] = {'closed_after_live_ui_tests': True, 'saved_results_preserved': True}
    save()
    print(json.dumps({'test_environment_closed': True, 'final_graph_snapshot': True}), flush=True)


def final_restart_check():
    before = json.loads((ROOT / 'deploy/graphiti-final-restart-before.json').read_text(encoding='utf-8'))
    after = api('GET', f'/api/graph/data/{state["graph_id"]}')
    assert before == after
    state['evidence']['final_restart'] = {'status': 'passed', 'nodes': after['node_count'],
                                         'edges': after['edge_count'], 'full_record_comparison': True}
    save()
    print(json.dumps(state['evidence']['final_restart']), flush=True)


def interact():
    """Verify the existing post-simulation features against actual model replies."""
    assert state['evidence']['run']['status'] == 'passed'
    simulation_id = state['simulation_id']
    if not all(state['evidence'].get(name, {}).get('status') == 'passed'
               for name in ('single_interview', 'batch_interview', 'survey')):
        environment = api('POST', '/api/simulation/env-status', json={'simulation_id': simulation_id})
        assert environment['env_alive'] and environment['twitter_available'] and environment['reddit_available']
    config = json.loads((ROOT / 'backend/uploads/simulations' / simulation_id / 'simulation_config.json').read_text(encoding='utf-8'))
    agents = {agent['entity_name']: agent['agent_id'] for agent in config['agent_configs']}

    def recorded(name, path, body):
        evidence = state['evidence']
        if name in evidence:
            return evidence[name]['result']
        assert name not in state.get('interaction_started', []), 'An unconfirmed model request must not be resubmitted automatically'
        state.setdefault('interaction_started', []).append(name)
        save()
        result = api('POST', path, json={'simulation_id': simulation_id, **body})
        evidence[name] = {'status': 'received', 'result': result}
        save()
        return result

    single = recorded('single_interview', '/api/simulation/interview', {
        'agent_id': agents['小橙'], 'platform': 'twitter', 'timeout': 120,
        'prompt': '請以小橙的身分，用繁體中文簡短說明：你會如何兼顧桌遊活動與鄰居的安靜需求？這是虛構測試。'})
    assert single['result']['response'].strip() and single['result']['agent_id'] == agents['小橙']
    state['evidence']['single_interview']['status'] = 'passed'
    save()
    print(json.dumps({'single_interview': 'passed'}), flush=True)

    batch = recorded('batch_interview', '/api/simulation/interview/batch', {
        'interviews': [{'agent_id': agents[name], 'prompt': '請用繁體中文簡短說明：你最重視桌遊活動的哪一項安排？這是虛構測試。'}
                       for name in ('小藍', '小紫')], 'platform': 'reddit', 'timeout': 180})
    assert len(batch['result']['results']) == 2
    assert all(reply['response'].strip() for reply in batch['result']['results'].values())
    state['evidence']['batch_interview']['status'] = 'passed'
    save()
    print(json.dumps({'batch_interview': 'passed', 'responses': 2}), flush=True)

    survey = recorded('survey', '/api/simulation/interview/all', {
        'platform': 'reddit', 'timeout': 180,
        'prompt': '問卷：你是否支持週六白天舉辦免費桌遊活動，並設安靜區和明確結束時間？請用繁體中文回答支持、反對或有條件支持，附一句理由。這是虛構測試。'})
    assert len(survey['result']['results']) == len(agents)
    assert all(reply['response'].strip() for reply in survey['result']['results'].values())
    state['evidence']['survey']['status'] = 'passed'
    save()
    print(json.dumps({'survey': 'passed', 'responses': len(agents)}), flush=True)

    if 'report' not in state['evidence']:
        print(json.dumps({'interviews_completed': True, 'report_chat': 'awaiting_report'}), flush=True)
        return
    assert state['evidence']['report']['status'] == 'passed'
    chat = recorded('report_chat', '/api/report/chat', {
        'message': '請先呼叫 quick_search 搜尋本次圖譜中小藍對噪音的要求，再依照找到的實際資料，用繁體中文說明如何安排活動。不要直接猜測。',
        'chat_history': []})
    assert chat['response'].strip() and chat['tool_calls'], 'Report chat must retrieve actual graph evidence'
    state['evidence']['report_chat']['status'] = 'passed'
    history = api('POST', '/api/simulation/interview/history', json={'simulation_id': simulation_id, 'limit': 100})
    assert history['count'] >= 7 and all(reply['response'].strip() for reply in history['history'])
    assert all(reply['timestamp_source'] == 'interview_command' for reply in history['history'])
    simulations = api('GET', '/api/simulation/history?limit=100')
    current = next(item for item in simulations if item['simulation_id'] == simulation_id)
    assert current['report_id'] == state['report_id'] and current['runner_status'] == 'completed'
    state['evidence']['history'] = {'status': 'passed', 'interview_count': history['count'],
                                  'simulation_and_report_listed': True, 'real_command_times_preserved': True,
                                  'records': history['history']}
    save()
    print(json.dumps({'report_chat': 'passed', 'retrieval_calls': len(chat['tool_calls']), 'history': 'passed'}), flush=True)


def finalize():
    for name in ('upload', 'build', 'prepare', 'run', 'report', 'single_interview', 'batch_interview',
                 'survey', 'report_chat', 'history', 'restart', 'final_restart'):
        assert state['evidence'][name]['status'] == 'passed', name
    status = api('GET', '/api/system/status')
    assert status['ready'] and status['graph_provider'] == 'graphiti' and status['embedding'] == 'local'
    backend_log = (ROOT / 'deploy/graphiti-tests.log').read_text(encoding='utf-8-sig')
    ui_log = (ROOT / 'deploy/graphiti-ui-tests.log').read_text(encoding='utf-8-sig')
    assert '167 passed' in backend_log and '31 passed' in ui_log
    audit = json.loads((ROOT / 'deploy/graphiti-python-audit.json').read_text(encoding='utf-8-sig'))
    frontend_audit = json.loads((ROOT / 'deploy/graphiti-npm-audit.json').read_text(encoding='utf-8-sig'))
    assert len(audit['dependencies']) == 108 and not any(package['vulns'] for package in audit['dependencies'])
    assert frontend_audit['metadata']['vulnerabilities']['total'] == 0
    privacy = {}
    for filename in ('graphiti-privacy.json', 'graphiti-service-privacy.json'):
        result = json.loads((ROOT / 'deploy' / filename).read_text(encoding='utf-8-sig'))
        assert result['environment_opt_outs'] and not result['graphiti_telemetry_enabled']
        assert not result['graphiti_posthog_initialized'] and not result['huggingface_telemetry_thread_started']
        assert not result['camel_langfuse_enabled']
        privacy[filename] = result
    docker_privacy = json.loads((ROOT / 'deploy/graphiti-docker-privacy.json').read_text(encoding='utf-8-sig'))
    assert docker_privacy['analytics_enabled'] is False
    privacy['docker_desktop'] = docker_privacy
    offline_log = (ROOT / 'deploy/graphiti-offline-embedding.log').read_text(encoding='utf-8-sig')
    offline = json.loads(next(line for line in reversed(offline_log.splitlines()) if line.startswith('{')))
    assert offline['semantic_check'] == 'passed' and offline['embedding_dimension'] == 384

    files = list((ROOT / 'backend/app').rglob('*.py')) + list((ROOT / 'backend/scripts').glob('*.py'))
    files += [ROOT / 'backend/serve.py', ROOT / 'backend/serve_graphiti.py', ROOT / 'backend/pyproject.toml', ROOT / 'backend/uv.lock']
    names = [str(path.relative_to(ROOT / 'backend')).replace('\\', '/') for path in files]
    local = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in zip(names, files)}
    script = 'import hashlib,json,sys;from pathlib import Path;print(json.dumps({name:hashlib.sha256((Path("/app/backend")/name).read_bytes()).hexdigest() for name in json.loads(sys.argv[1])}))'
    deployed = json.loads(subprocess.check_output(['docker', 'exec', 'mirofish-local-backend-1', 'python', '-c', script, json.dumps(names)], text=True))
    assert local == deployed, 'The deployed runtime must contain the exact tested source and dependency locks'
    subprocess.run(['docker', 'exec', 'mirofish-local-backend-1', '/bin/uv', 'pip', 'check',
                    '--python', '/app/backend/.venv/bin/python'], check=True, capture_output=True)
    service_states = {name: subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Health.Status}}',
                      f'mirofish-local-{name}-1'], text=True).strip() for name in ('backend', 'frontend', 'graphiti', 'neo4j')}
    assert all(value == 'healthy' for value in service_states.values())
    report_log = ROOT / 'backend/uploads/reports' / state['report_id'] / 'agent_log.jsonl'
    activity = [json.loads(line) for line in report_log.read_text(encoding='utf-8').splitlines()]
    results = [entry for entry in activity if entry['action'] == 'tool_result']
    assert len(results) == state['evidence']['report']['actual_tool_calls']
    assert all(not entry['details']['result'].startswith('工具执行失败:') for entry in results)
    state['evidence']['report']['all_retrieval_calls_succeeded'] = True
    state['evidence']['regression'] = {'backend_tests': 167, 'frontend_tests': 31, 'deployed_source_files_verified': len(files)}
    state['evidence']['dependencies'] = {'compatible_installed_packages': 109, 'audited_public_packages': 108,
                                          'python_known_vulnerabilities': 0, 'frontend_known_vulnerabilities': 0}
    state['evidence']['privacy'] = privacy
    state['evidence']['offline_embeddings'] = offline
    state['evidence']['services'] = service_states
    state['evidence']['system_status'] = status
    state['evidence']['browser'] = json.loads((ROOT / 'deploy/graphiti-browser-validation.json').read_text(encoding='utf-8-sig'))
    assert state['evidence']['browser']['report_chat_after_deployment']
    state['completed_at'] = datetime.now(timezone.utc).isoformat()
    state['validation_status'] = 'passed'
    state['report_url'] = f'http://localhost:3100/report/{state["report_id"]}'
    state['limitations'] = ['Four fictional people, two rounds per platform with explicitly active test hours and seed posts',
                            'Large documents and long-running simulations not benchmarked',
                            'LLM requests still use the provider selected in 9Router',
                            'Container persistence verified; Windows reboot not tested']
    save()
    print(json.dumps({'status': 'passed', 'backend_tests': 167, 'frontend_tests': 31, 'interviews_saved': state['evidence']['history']['interview_count'],
                      'retrieval_calls': len(results), 'report_url': state['report_url']}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['upload', 'recover_upload', 'build', 'rebuild', 'prepare', 'activate', 'fresh', 'restart_check', 'close_failed_environment', 'reset_graph', 'run', 'report', 'archive_interview_failure', 'interact', 'close_for_deploy', 'final_restart_check', 'finalize'])
    phase = parser.parse_args().phase
    globals()[phase]()
