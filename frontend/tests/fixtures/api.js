// Fictional cafe data for browser acceptance tests. No external model calls.
const profiles = [
  { agent_id: 0, username: '附近住戶', name: '附近住戶', profession: '教師', bio: '重視安靜的生活', persona: '在咖啡店附近居住。', entity_type: 'Resident', age: 35, interested_topics: ['營業時間'] },
  { agent_id: 1, username: '咖啡店常客', name: '咖啡店常客', profession: '設計師', bio: '喜歡晚間閱讀', persona: '下班後常到咖啡店。', entity_type: 'Customer', age: 28, interested_topics: ['咖啡'] }
]
const project = { project_id: 'proj_fixture', graph_id: 'graph_fixture', status: 'graph_completed', simulation_requirement: '探索咖啡店延長營業時間的反應', files: [{ filename: 'cafe.md', size: 150 }], ontology: {
  entity_types: [{ name: 'Resident', description: '附近住戶', attributes: [{ name: 'district', type: 'text', description: '居住地區' }], examples: ['鄰居'] }],
  edge_types: [{ name: 'VISITS', description: '到店消費', source_targets: [{ source: 'Resident', target: 'Cafe' }] }]
} }
const graph = { graph_id: 'graph_fixture', node_count: 2, edge_count: 1, nodes: [
  { uuid: 'resident', name: '附近住戶', labels: ['Entity', 'Resident'], summary: '居住在咖啡店附近。' },
  { uuid: 'cafe', name: '咖啡店', labels: ['Entity', 'Cafe'] }
], edges: [{ uuid: 'visits', name: 'VISITS', source_node_uuid: 'resident', target_node_uuid: 'cafe', fact: '附近住戶到咖啡店消費。' }] }
const simulation = { simulation_id: 'sim_fixture', project_id: 'proj_fixture', graph_id: 'graph_fixture', status: 'prepared', enable_twitter: true, enable_reddit: true }
const config = { time_config: { total_simulation_hours: 24, minutes_per_round: 30, peak_hours: [18, 19], work_hours: [9, 17], morning_hours: [7, 8], off_peak_hours: [0, 1] }, agent_configs: [], event_config: { narrative_direction: '延長營業時間', hot_topics: ['咖啡'], initial_posts: [] } }
const historyItem = { ...simulation, ...project, report_id: 'report_fixture', simulation_id: 'sim_fixture', created_at: '2026-10-01T10:00:00', total_rounds: 2, current_round: 2, runner_status: 'completed', report_status: 'completed' }
const logs = [
  { action: 'report_start', timestamp: '2026-10-01T10:00:00' },
  { action: 'planning_complete', timestamp: '2026-10-01T10:00:01', details: { outline: { title: '咖啡店探索報告', summary: '比較住戶與常客的反應', sections: [{ title: '住戶觀點' }] } } },
  { action: 'section_complete', section_index: 1, timestamp: '2026-10-01T10:00:02', details: { content: '## 住戶觀點\n\n**安靜的生活**仍是主要關切。' } },
  { action: 'report_complete', timestamp: '2026-10-01T10:00:03' }
]
// Provider examples are fictional. This adapter never contacts a model service,
// and deliberately retains only credential-presence flags, not submitted keys.
const providerPresets = [
  { id: 'openai', label: 'OpenAI', base_url: 'https://api.openai.com/v1' },
  { id: 'openrouter', label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1' },
  { id: 'opencode_zen', label: 'OpenCode Zen', base_url: 'https://opencode.ai/zen/v1' },
  { id: 'opencode_go', label: 'OpenCode Go', base_url: 'https://opencode.ai/zen/go/v1' },
  { id: 'ninerouter', label: '9Router', base_url: 'http://host.docker.internal:20128/v1' },
  { id: 'custom', label: 'OpenAI 相容／自訂端點', base_url: '' }
]
const providerEnvelope = () => ({ config: { ...state.provider }, presets: providerPresets, csrf_token: 'fixture-csrf-token' })
function dispatch(request) {
  const { url, data, params = {} } = request
  if (url === '/api/settings/providers') {
    if (request.method?.toLowerCase() === 'put') {
      if (data.clear_balance_authorization) {
        state.provider = { ...state.provider, has_balance_api_key: false, balance_account_id: '' }
        return ok(providerEnvelope())
      }
      const sameEndpoint = data.provider === state.provider.provider && data.base_url.replace(/\/+$/, '') === state.provider.base_url.replace(/\/+$/, '')
      state.provider = {
        provider: data.provider, base_url: data.base_url, model: data.model,
        has_api_key: Boolean(data.api_key || (sameEndpoint && state.provider.has_api_key)),
        has_balance_api_key: data.provider === 'ninerouter' && Boolean(data.balance_api_key || (sameEndpoint && state.provider.has_balance_api_key)),
        balance_account_id: data.provider === 'ninerouter' ? data.balance_account_id || '' : ''
      }
    }
    return ok(providerEnvelope())
  }
  if (url === '/api/settings/providers/test') return ok({ models: [{ id: 'fixture-model', compatible: true }, { id: 'fixture-chat-small', compatible: true }, { id: 'fixture-responses-only', compatible: false }], model_available: ['fixture-model', 'fixture-chat-small'].includes(data.model) })
  if (url === '/api/settings/providers/accounts') return ok({ accounts: [{ id: 'account_fixture', name: '測試用 OpenCode 帳戶', is_active: true }, { id: 'account_inactive_fixture', name: '已停用測試帳戶', is_active: false }] })
  if (url === '/api/settings/providers/balance') {
    if (state.provider.provider === 'ninerouter') {
      if (!state.provider.has_balance_api_key) return ok({ supported: false, status: 'authorization_required', kind: 'wallet', quotas: [] })
      if (!state.provider.balance_account_id) return ok({ supported: false, status: 'account_required', kind: 'wallet', quotas: [] })
      return ok({ supported: true, status: 'stale', kind: 'wallet', remaining: 12.34, currency: 'USD', checked_at: '2026-10-01T10:00:00Z', message: '合成範例資料，並非真實帳戶餘額。', quotas: [{ id: 'weekly', remaining_percent: 76, resets_at: '2026-10-05T00:00:00Z' }] })
    }
    if (state.provider.provider === 'openrouter') return ok({ supported: true, status: 'available', kind: 'key_allowance', remaining: null, currency: 'USD', quotas: [] })
    if (state.provider.provider === 'opencode_go') return ok({ supported: true, status: 'available', kind: 'subscription_quota', quotas: [{ id: 'rolling', remaining_percent: 68 }, { id: 'weekly', remaining_percent: 84 }] })
    return ok({ supported: false, status: 'unsupported', quotas: [] })
  }
  if (url === '/api/system/status') return ok(state.status)
  if (url === '/api/sources/status') return ok({ enabled: true, configured: true, online: true, mode: 'local', cloud_credits: 0, max_pages_per_job: 3, max_chars_per_page: 8000, cache_hours: 24, budget: { used: 0, daily_limit: 10, remaining: 10, resets_at: '2026-10-04T00:00:00+10:00', timezone: 'Australia/Sydney' } })
  if (url === '/api/simulation/history') return ok(state.history)
  if (url === '/api/graph/ontology/generate') return ok({ ...project, graph_id: null, status: 'ontology_generated' })
  if (url === '/api/graph/project/proj_fixture') return ok(state.project)
  if (url === '/api/graph/data/graph_fixture') return ok(structuredClone(graph))
  if (url === '/api/simulation/create') return ok(simulation)
  if (url === '/api/simulation/sim_fixture') return ok(simulation)
  if (url === '/api/simulation/prepare') return ok({ already_prepared: true })
  if (url === '/api/simulation/sim_fixture/profiles/realtime') return ok({ profiles, total_expected: 2 })
  if (url === '/api/simulation/sim_fixture/config/realtime') return ok({ config_generated: true, config })
  if (url === '/api/simulation/sim_fixture/config') return ok(config)
  if (url === '/api/simulation/start' || url === '/api/simulation/sim_fixture/run-status') return ok(state.runStatus)
  if (url === '/api/simulation/stop' || url === '/api/simulation/env/close') return ok({ runner_status: 'stopped' })
  if (url.endsWith('/env-status')) return ok({ env_alive: false, status: 'closed' })
  if (url === '/api/simulation/sim_fixture/run-status/detail') return ok({ all_actions: [], ...state.runStatus })
  if (url === '/api/report/generate') return ok({ report_id: 'report_fixture' })
  if (url === '/api/report/report_fixture') return ok({ report_id: 'report_fixture', simulation_id: 'sim_fixture', status: 'completed' })
  if (url === '/api/report/report_fixture/agent-log') return ok({ logs: params.from_line ? [] : logs, from_line: params.from_line || 0 })
  if (url === '/api/report/report_fixture/console-log') return ok({ logs: [], from_line: 0 })
  if (url === '/api/report/chat') return ok({ response: '已整理住戶觀點。' })
  if (url === '/api/simulation/interview/batch') return ok({ result: { results: Object.fromEntries(data.interviews.map(item => [`reddit_${item.agent_id}`, { response: `${profiles[item.agent_id].username}的回答。` }])) } })
  state.unexpected.push(url)
  throw new Error(`Unexpected test request: ${url}`)
}

const ok = data => ({ success: true, data })
let state
export function createFixtureAdapter({ emptyHistory = false } = {}) {
  state = { status: { ready: true, llm_configured: true, graph_configured: true, graph_provider: 'graphiti', embedding: 'local' }, provider: { provider: 'ninerouter', base_url: 'http://host.docker.internal:20128/v1', model: 'fixture-model', has_api_key: true, has_balance_api_key: false, balance_account_id: '' }, history: [historyItem], project, unexpected: [], runStatus: { runner_status: 'completed', total_rounds: 2, twitter_completed: true, reddit_completed: true, twitter_current_round: 2, reddit_current_round: 2, twitter_actions_count: 3, reddit_actions_count: 3 } }
  if (emptyHistory) state.history = []
  return async request => {
    const data = typeof request.data === 'string' ? JSON.parse(request.data) : request.data
    const response = dispatch({ ...request, data })
    return { data: response, status: 200, statusText: 'OK', headers: {}, config: request }
  }
}
