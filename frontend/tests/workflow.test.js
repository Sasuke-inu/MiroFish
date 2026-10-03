import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import zhTW from '../../locales/zh-TW.json'
import en from '../../locales/en.json'
import zh from '../../locales/zh.json'
import Home from '../src/views/Home.vue'
import MainView from '../src/views/MainView.vue'
import SimulationView from '../src/views/SimulationView.vue'
import SimulationRunView from '../src/views/SimulationRunView.vue'
import ReportView from '../src/views/ReportView.vue'
import InteractionView from '../src/views/InteractionView.vue'
import LanguageSwitcher from '../src/components/LanguageSwitcher.vue'
import WorkflowProgress from '../src/components/WorkflowProgress.vue'
import GraphPanel from '../src/components/GraphPanel.vue'
import Step1 from '../src/components/Step1GraphBuild.vue'
import Step2 from '../src/components/Step2EnvSetup.vue'
import Step3 from '../src/components/Step3Simulation.vue'
import Step4 from '../src/components/Step4Report.vue'
import Step5 from '../src/components/Step5Interaction.vue'
import HistoryDatabase from '../src/components/HistoryDatabase.vue'
import App from '../src/App.vue'
import productionRouter from '../src/router'
import { providerClient } from '../src/api/providers'
import { createFixtureAdapter } from './fixtures/api'
import { getPendingUpload, clearPendingUpload, setPendingUpload } from '../src/store/pendingUpload'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/index.js', () => ({ default: Object.assign(api, {
  get: (url, options = {}) => api({ url, method: 'get', ...options }),
  post: (url, data, options = {}) => api({ url, method: 'post', data, ...options })
}) }))

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
let mounted = []
let state
const ok = data => ({ success: true, data })

function dispatch(request) {
  const { url, data, params = {} } = request
  if (url === '/api/system/status') return ok(state.status)
  if (url === '/api/sources/status') return ok({ enabled: true, configured: true, online: true,
    mode: 'local', cloud_credits: 0, max_pages_per_job: 3, max_chars_per_page: 8000, cache_hours: 24,
    budget: { used: 0, daily_limit: 10, remaining: 10, resets_at: '2026-10-03T00:00:00+10:00', timezone: 'Australia/Sydney' } })
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

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  clearPendingUpload()
  providerClient.defaults.adapter = createFixtureAdapter()
  state = { status: { ready: true, llm_configured: true, graph_configured: true }, history: [historyItem], project: structuredClone(project), unexpected: [], runStatus: { runner_status: 'running', total_rounds: 2, twitter_running: true, reddit_running: true, twitter_current_round: 1, reddit_current_round: 1 } }
  api.mockReset().mockImplementation(async request => dispatch(request))
})
afterEach(() => {
  mounted.forEach(wrapper => wrapper.unmount())
  mounted = []
  document.body.innerHTML = ''
  vi.clearAllTimers()
  vi.useRealTimers()
  expect(state.unexpected).toEqual([])
})

async function render(component, path = '/', props = {}, options = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: productionRouter.options.routes })
  await router.push(path)
  await router.isReady()
  const i18n = createI18n({ legacy: false, locale: 'zh-TW', fallbackLocale: 'zh-TW', messages: { 'zh-TW': zhTW, en, zh } })
  const wrapper = mount(component, { props, attachTo: document.body, global: { plugins: [router, i18n], provide: { systemStatus: ref(state.status) }, stubs: options.stubs || {} } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router, i18n }
}
function requestTo(url) { return api.mock.calls.map(([request]) => request).filter(request => request.url === url) }
async function settle() { await flushPromises(); await flushPromises() }
async function openSettingsSection(wrapper, label) {
  await wrapper.findAll('.settings-index > button').find(button => button.text().includes(label)).trigger('click')
}

describe('Upload and language controls', () => {
  it('keeps all locale keys, arrays and placeholders available in Traditional Chinese', () => {
    function check(source, translated, path = '') {
      expect(Array.isArray(translated), path).toBe(Array.isArray(source))
      if (typeof source === 'string') {
        expect(typeof translated, path).toBe('string')
        expect(translated.match(/\{[^}]+\}/g) || [], path).toEqual(source.match(/\{[^}]+\}/g) || [])
      } else {
        expect(Object.keys(translated).sort(), path).toEqual(Object.keys(source).sort())
        for (const key in source) check(source[key], translated[key], `${path}.${key}`)
      }
    }
    check(en, zhTW)
  })
  it('uploads multiple supported files, removes one, and preserves the goal for the next page', async () => {
    const { wrapper, router } = await render(Home)
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeDefined()
    const source = new File(['reference'], 'cafe.md', { type: 'text/markdown' })
    const second = new File(['notes'], 'notes.txt', { type: 'text/plain' })
    Object.defineProperty(wrapper.get('input[type=file]').element, 'files', { configurable: true, value: [source, second, new File(['x'], 'image.png')] })
    await wrapper.get('input[type=file]').trigger('change')
    expect(wrapper.findAll('.upload-zone .file-item')).toHaveLength(2)
    await wrapper.get('.remove-btn').trigger('click')
    await wrapper.get('#simulation-goal').setValue('延長營業時間會有哪些反應？')
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeUndefined()
    await wrapper.get('.start-engine-btn').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/process/new')
    expect(getPendingUpload().files.map(file => file.name)).toEqual(['notes.txt'])
    expect(getPendingUpload().simulationRequirement).toBe('延長營業時間會有哪些反應？')
  })
  it('keeps drag and drop and rejects unsupported files', async () => {
    const { wrapper } = await render(Home)
    await wrapper.get('#simulation-goal').setValue('探索')
    await wrapper.get('.upload-zone').trigger('drop', { dataTransfer: { files: [new File(['x'], 'photo.png')] } })
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeDefined()
    await wrapper.get('.upload-zone').trigger('dragover')
    expect(wrapper.get('.upload-zone').classes()).toContain('drag-over')
    await wrapper.get('.upload-zone').trigger('drop', { dataTransfer: { files: [new File(['x'], 'story.pdf')] } })
    expect(wrapper.get('.file-name').text()).toBe('story.pdf')
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeUndefined()
  })
  it('retains all language choices, remembers selection and closes with Escape', async () => {
    const { wrapper, i18n } = await render(LanguageSwitcher)
    await wrapper.get('.switcher-trigger').trigger('click')
    expect(wrapper.findAll('.locale-choice').map(item => item.text()).sort()).toEqual(['English', '简体中文', '繁體中文'].sort())
    await wrapper.findAll('.locale-choice').find(button => button.text() === 'English').trigger('click')
    expect(i18n.global.locale.value).toBe('en')
    expect(localStorage.getItem('locale')).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    await wrapper.get('.switcher-trigger').trigger('click')
    await wrapper.get('.switcher-trigger').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.switcher-dropdown').exists()).toBe(false)
  })
  it('shows an accurate missing-graph state while preserving completed analysis', async () => {
    state.status = { ready: false, llm_configured: true, graph_configured: false }
    state.project = { ...project, graph_id: null, status: 'ontology_generated' }
    const { wrapper } = await render(MainView, '/process/proj_fixture', {}, { stubs: { GraphPanel: true } })
    expect(wrapper.text()).toContain('等待圖譜服務設定')
    expect(wrapper.text()).toContain('分析資料內容')
    expect(wrapper.find('.entity-tag').text()).toBe('Resident')
    expect(requestTo('/api/graph/build')).toHaveLength(0)
  })
  it('passes source files and goal through the existing multipart upload API', async () => {
    state.status.graph_configured = false
    setPendingUpload([new File(['facts'], 'cafe.md')], '探索營業時間')
    const { router } = await render(MainView, '/process/new', {}, { stubs: { GraphPanel: true } })
    const upload = requestTo('/api/graph/ontology/generate')[0]
    expect(upload.data.get('files').name).toBe('cafe.md')
    expect(upload.data.get('simulation_requirement')).toBe('探索營業時間')
    expect(getPendingUpload().isPending).toBe(false)
    expect(router.currentRoute.value.params.projectId).toBe('proj_fixture')
  })
})

describe('All workflow views', () => {
  for (const [component, path, step] of [[MainView, '/process/proj_fixture', 1], [SimulationView, '/simulation/sim_fixture', 2], [SimulationRunView, '/simulation/sim_fixture/start?maxRounds=2', 3], [ReportView, '/report/report_fixture', 4], [InteractionView, '/interaction/report_fixture', 5]]) {
    it(`${component.__name} retains graph, split, workbench and home navigation`, async () => {
      const { wrapper, router } = await render(component, path, {}, { stubs: { GraphPanel: true } })
      expect(wrapper.findAll('.studio-progress li')).toHaveLength(5)
      expect(wrapper.get('.settings-link').attributes('href')).toContain('/settings?from=')
      await wrapper.get('.appearance-toggle').trigger('click')
      expect(document.documentElement.dataset.theme).toBe('dark')
      await wrapper.get('.appearance-toggle').trigger('click')
      expect(document.documentElement.dataset.theme).toBe('light')
      expect(wrapper.get('.studio-progress [aria-current=step]').text()).toContain(zhTW.main.stepNames[step - 1])
      const buttons = wrapper.findAll('.switch-btn')
      for (const [index, mode] of ['graph', 'split', 'workbench'].entries()) {
        await buttons[index].trigger('click')
        expect(wrapper.get('.main-view').attributes('data-layout')).toBe(mode)
        expect(wrapper.get('.panel-wrapper.left').element.style.width).toBe(mode === 'graph' ? '100%' : mode === 'split' ? '50%' : '0%')
        expect(wrapper.get('.panel-wrapper.right').element.style.width).toBe(mode === 'workbench' ? '100%' : mode === 'split' ? '50%' : '0%')
      }
      await wrapper.get('.brand').trigger('keydown', { key: 'Enter' })
      await settle()
      expect(router.currentRoute.value.name).toBe('Home')
    })
  }
  it('keeps a readable progress indicator for the current step', async () => {
    const { wrapper } = await render(WorkflowProgress, '/', { current: 4 })
    expect(wrapper.findAll('.passed')).toHaveLength(3)
    expect(wrapper.get('[aria-current=step]').text()).toContain('分析報告')
  })
})

describe('Settings preserve the workspace', () => {
  it('renders home when the first route resolves after the application mounts', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: productionRouter.options.routes })
    const i18n = createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en, zh } })
    const wrapper = mount(App, { attachTo: document.body, global: { plugins: [router, i18n] } })
    mounted.push(wrapper)
    await router.isReady()
    await settle()
    expect(wrapper.get('.home-container h1').text()).toBe(zhTW.studio.refined.headline)
    expect(wrapper.get('.settings-link').text()).toContain('設定')
  })
  it('opens from home, changes appearance and returns with the goal and files intact', async () => {
    const { wrapper, router } = await render(App)
    const file = new File(['Cafe scenario'], 'draft.md', { type: 'text/markdown' })
    Object.defineProperty(wrapper.get('input[type=file]').element, 'files', { configurable: true, value: [file] })
    await wrapper.get('input[type=file]').trigger('change')
    await wrapper.get('#simulation-goal').setValue('尚未送出的探索目標')
    await wrapper.get('.settings-link').trigger('click')
    await settle()
    expect(router.currentRoute.value.name).toBe('Settings')
    expect(wrapper.get('.home-container').isVisible()).toBe(false)
    await openSettingsSection(wrapper, zhTW.providers.appearanceNav)
    await wrapper.get('input[name=appearance][value=dark]').setValue()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('mirofish.theme')).toBe('dark')
    await wrapper.get('.settings-back').trigger('click')
    await settle()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(wrapper.get('#simulation-goal').element.value).toBe('尚未送出的探索目標')
    expect(wrapper.get('.file-list').text()).toContain('draft.md')
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeUndefined()
  })
  it('keeps a report conversation and an unsent question when visiting settings', async () => {
    const { wrapper, router } = await render(App, '/interaction/report_fixture')
    await wrapper.get('.chat-input').setValue('住戶的觀點是什麼？')
    await wrapper.get('.send-btn').trigger('click')
    await settle()
    await wrapper.get('.chat-input').setValue('接下來想追問的內容')
    await wrapper.get('.settings-link').trigger('click')
    await settle()
    await openSettingsSection(wrapper, zhTW.providers.appearanceNav)
    await wrapper.get('input[name=appearance][value=dark]').setValue()
    await wrapper.get('.settings-back').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/interaction/report_fixture')
    expect(wrapper.get('.chat-input').element.value).toBe('接下來想追問的內容')
    expect(wrapper.get('.chat-messages').text()).toContain('已整理住戶觀點。')
    expect(requestTo('/api/report/chat')).toHaveLength(1)
  })
  it('keeps the running simulation and selected layout without restarting or stopping it', async () => {
    const { wrapper, router } = await render(App, '/simulation/sim_fixture/start?maxRounds=2')
    await wrapper.findAll('.switch-btn')[2].trigger('click')
    await wrapper.get('.settings-link').trigger('click')
    await settle()
    await openSettingsSection(wrapper, zhTW.providers.appearanceNav)
    await wrapper.get('input[name=appearance][value=dark]').setValue()
    await wrapper.get('.settings-back').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/simulation/sim_fixture/start?maxRounds=2')
    expect(wrapper.get('.main-view').attributes('data-layout')).toBe('workbench')
    expect(requestTo('/api/simulation/start')).toHaveLength(0)
    expect(requestTo('/api/simulation/stop')).toHaveLength(0)
    expect(requestTo('/api/simulation/env/close')).toHaveLength(0)
  })
  it('changes the language in settings and applies it to the restored workspace', async () => {
    const { wrapper, router, i18n } = await render(App)
    await wrapper.get('.settings-link').trigger('click')
    await settle()
    await openSettingsSection(wrapper, zhTW.providers.appearanceNav)
    const settings = wrapper.get('.settings-page')
    await settings.get('.switcher-trigger').trigger('click')
    await settings.findAll('.locale-choice').find(button => button.text() === 'English').trigger('click')
    expect(settings.get('h1').text()).toBe('Settings')
    expect(i18n.global.locale.value).toBe('en')
    expect(localStorage.getItem('locale')).toBe('en')
    await settings.get('.settings-back').trigger('click')
    await settle()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(wrapper.get('.settings-link').text()).toContain('Settings')
  })
  it('opens directly, shows local services and safely falls back to home for an external return path', async () => {
    state.status = { ready: true, llm_configured: true, graph_configured: true, graph_provider: 'graphiti', embedding: 'local' }
    const { wrapper, router } = await render(App, '/settings?from=%2F%2Fexample.com')
    await openSettingsSection(wrapper, zhTW.settings.services)
    expect(wrapper.get('.settings-services').text()).toContain('Graphiti＋Neo4j（本機）')
    expect(wrapper.get('.settings-services').text()).toContain('在本機處理')
    expect(wrapper.find('.home-container').exists()).toBe(false)
    await wrapper.get('.settings-refresh').trigger('click')
    await settle()
    expect(requestTo('/api/system/status')).toHaveLength(2)
    await wrapper.get('.settings-back').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/')
  })
  it('reports a status failure and recovers when the user refreshes', async () => {
    let failStatus = true
    api.mockImplementation(async request => {
      if (request.url === '/api/system/status' && failStatus) {
        failStatus = false
        throw new Error('Service unavailable')
      }
      return dispatch(request)
    })
    const { wrapper } = await render(App, '/settings')
    await openSettingsSection(wrapper, zhTW.settings.services)
    expect(wrapper.get('.settings-error').text()).toContain('無法連接網站服務')
    expect(wrapper.get('.settings-services').text()).toContain('無法取得狀態')
    await wrapper.get('.settings-refresh').trigger('click')
    await settle()
    expect(wrapper.find('.settings-error').exists()).toBe(false)
    expect(wrapper.get('.settings-services').text()).toContain('已設定')
  })
})

describe('Graph and simulation features', () => {
  it('keeps graph refresh, maximize, node details and edge-label toggling', async () => {
    const { wrapper } = await render(GraphPanel, '/', { graphData: null, loading: false, currentPhase: 2 })
    await wrapper.setProps({ graphData: structuredClone(graph) })
    await settle()
    expect(wrapper.findAll('svg circle')).length.greaterThanOrEqual(2)
    await wrapper.findAll('.tool-btn')[0].trigger('click')
    await wrapper.findAll('.tool-btn')[1].trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('toggle-maximize')).toHaveLength(1)
    const circles = wrapper.findAll('svg circle')
    await circles[0].trigger('click')
    expect(wrapper.get('.detail-panel').text()).toContain('附近住戶')
    await wrapper.get('.detail-close').trigger('click')
    expect(wrapper.find('.detail-panel').exists()).toBe(false)
    await wrapper.get('.edge-labels-toggle input').setValue(false)
    expect(wrapper.get('.edge-labels-toggle input').element.checked).toBe(false)
  })
  it('keeps ontology details and creation of both simulation platforms', async () => {
    const { wrapper, router } = await render(Step1, '/', { currentPhase: 2, projectData: project, graphData: graph, systemLogs: [] })
    await wrapper.get('.entity-tag.clickable').trigger('click')
    expect(wrapper.get('.ontology-detail-overlay').text()).toContain('居住地區')
    await wrapper.get('.close-btn').trigger('click')
    expect(wrapper.find('.ontology-detail-overlay').exists()).toBe(false)
    await wrapper.get('.action-btn').trigger('click')
    await settle()
    expect(requestTo('/api/simulation/create')[0].data).toEqual({ project_id: 'proj_fixture', graph_id: 'graph_fixture', enable_twitter: true, enable_reddit: true })
    expect(router.currentRoute.value.fullPath).toBe('/simulation/sim_fixture')
  })
  it('resizes the graph canvas when a panel changes size without a window resize', async () => {
    const originalObserver = globalThis.ResizeObserver
    let onResize
    const disconnect = vi.fn()
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback) { onResize = callback }
      observe() {}
      disconnect() { disconnect() }
    })
    try {
      const { wrapper } = await render(GraphPanel, '/', { graphData: null, currentPhase: 2 })
      await wrapper.setProps({ graphData: structuredClone(graph) })
      await settle()
      Object.defineProperty(wrapper.get('.graph-container').element, 'clientWidth', { configurable: true, value: 510 })
      onResize()
      await vi.advanceTimersByTimeAsync(125)
      await settle()
      expect(wrapper.get('.graph-svg').attributes('viewBox')).toBe('0 0 510 600')
      wrapper.unmount()
      mounted = mounted.filter(item => item !== wrapper)
      expect(disconnect).toHaveBeenCalledOnce()
    } finally {
      vi.stubGlobal('ResizeObserver', originalObserver)
    }
  })
  it('keeps prepared profiles and custom simulation rounds', async () => {
    const { wrapper } = await render(Step2, '/', { simulationId: 'sim_fixture', projectData: project, graphData: graph, systemLogs: [] })
    expect(wrapper.text()).toContain('附近住戶')
    await wrapper.get('.switch-control input').setValue(true)
    await wrapper.get('input[type=range]').setValue(20)
    await wrapper.findAll('button').find(button => button.text().includes(zhTW.step2.startDualWorldSim)).trigger('click')
    expect(wrapper.emitted('next-step').at(-1)[0]).toEqual({ maxRounds: 20 })
  })
  it('retains simulation start and sends the selected round limit', async () => {
    state.runStatus.runner_status = 'idle'
    await render(Step3, '/', { simulationId: 'sim_fixture', maxRounds: 2, minutesPerRound: 30, systemLogs: [] })
    expect(requestTo('/api/simulation/start')[0].data).toEqual({ simulation_id: 'sim_fixture', platform: 'parallel', force: true, enable_graph_memory_update: true, max_rounds: 2 })
  })
  it.each(['running', 'stopping', 'completed'])('restores %s runs without starting or erasing them', async status => {
    state.runStatus.runner_status = status
    await render(Step3, '/', { simulationId: 'sim_fixture', maxRounds: 2, systemLogs: [] })
    expect(requestTo('/api/simulation/start')).toHaveLength(0)
    expect(requestTo('/api/simulation/sim_fixture/run-status/detail')).toHaveLength(1)
  })
  it('lets users stop a running simulation and clears further polling', async () => {
    const { wrapper } = await render(Step3, '/', { simulationId: 'sim_fixture', maxRounds: 2, systemLogs: [] })
    const stopButton = wrapper.findAll('button').find(button => button.text() === '停止模擬')
    expect(stopButton).toBeDefined()
    await stopButton.trigger('click')
    await settle()
    expect(requestTo('/api/simulation/stop')[0].data).toEqual({ simulation_id: 'sim_fixture' })
    const polls = requestTo('/api/simulation/sim_fixture/run-status').length
    await vi.advanceTimersByTimeAsync(6000)
    expect(requestTo('/api/simulation/sim_fixture/run-status')).toHaveLength(polls)
  })
  it('keeps report generation and its destination after simulation completes', async () => {
    state.runStatus.runner_status = 'completed'
    const { wrapper, router } = await render(Step3, '/', { simulationId: 'sim_fixture', maxRounds: 2, systemLogs: [] })
    await vi.advanceTimersByTimeAsync(2000)
    await wrapper.get('.action-btn.primary').trigger('click')
    await settle()
    expect(requestTo('/api/report/generate')[0].data).toEqual({ simulation_id: 'sim_fixture', force_regenerate: true })
    expect(router.currentRoute.value.fullPath).toBe('/report/report_fixture')
  })
})

describe('Reports, conversations, surveys and history', () => {
  it('renders report sections, collapses them and enters conversation', async () => {
    const { wrapper, router } = await render(Step4, '/', { reportId: 'report_fixture', simulationId: 'sim_fixture', systemLogs: [] })
    expect(wrapper.text()).toContain('咖啡店探索報告')
    expect(wrapper.get('.generated-content strong').text()).toBe('安靜的生活')
    await wrapper.get('.section-header-row').trigger('click')
    expect(wrapper.get('.section-body').element.style.display).toBe('none')
    await wrapper.get('.next-step-btn').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/interaction/report_fixture')
  })
  it('sends questions to the report assistant and retains conversation history', async () => {
    const { wrapper } = await render(Step5, '/', { reportId: 'report_fixture', simulationId: 'sim_fixture', systemLogs: [] })
    await wrapper.get('.chat-input').setValue('住戶關心什麼？')
    await wrapper.get('.send-btn').trigger('click')
    await settle()
    expect(wrapper.text()).toContain('已整理住戶觀點。')
    await wrapper.get('.chat-input').setValue('還有哪些影響？')
    await wrapper.get('.chat-input').trigger('keydown', { key: 'Enter' })
    await settle()
    expect(requestTo('/api/report/chat')[1].data.chat_history).toEqual([{ role: 'user', content: '住戶關心什麼？' }, { role: 'assistant', content: '已整理住戶觀點。' }])
  })
  it('switches to an individual character and restores the report conversation', async () => {
    const { wrapper } = await render(Step5, '/', { reportId: 'report_fixture', simulationId: 'sim_fixture', systemLogs: [] })
    await wrapper.get('.chat-input').setValue('住戶關心什麼？')
    await wrapper.get('.send-btn').trigger('click')
    await settle()
    await wrapper.get('.agent-pill').trigger('click')
    await wrapper.get('.dropdown-item').trigger('click')
    await wrapper.get('.chat-input').setValue('你對晚間營業有何看法？')
    await wrapper.get('.send-btn').trigger('click')
    await settle()
    expect(requestTo('/api/simulation/interview/batch')[0].data.interviews).toEqual([{ agent_id: 0, prompt: '你對晚間營業有何看法？' }])
    expect(wrapper.text()).toContain('附近住戶的回答。')
    await wrapper.findAll('.tab-pill')[0].trigger('click')
    expect(wrapper.text()).toContain('住戶關心什麼？')
    expect(wrapper.text()).toContain('已整理住戶觀點。')
  })
  it('keeps survey selection, clearing, batch submission and answers', async () => {
    const { wrapper } = await render(Step5, '/', { reportId: 'report_fixture', simulationId: 'sim_fixture', systemLogs: [] })
    await wrapper.get('.survey-pill').trigger('click')
    await wrapper.findAll('.action-link')[0].trigger('click')
    expect(wrapper.findAll('input[type=checkbox]').every(input => input.element.checked)).toBe(true)
    await wrapper.findAll('.action-link')[1].trigger('click')
    expect(wrapper.findAll('input[type=checkbox]').every(input => !input.element.checked)).toBe(true)
    await wrapper.findAll('.action-link')[0].trigger('click')
    await wrapper.get('.survey-input').setValue('是否支持延長營業？')
    await wrapper.get('.survey-submit-btn').trigger('click')
    await settle()
    expect(requestTo('/api/simulation/interview/batch')[0].data.interviews).toHaveLength(2)
    expect(wrapper.findAll('.result-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('咖啡店常客的回答。')
  })
  for (const [selector, expected] of [['.btn-project', '/process/proj_fixture'], ['.btn-simulation', '/simulation/sim_fixture'], ['.btn-report', '/report/report_fixture']]) {
    it(`history replay retains ${expected} navigation and closes its dialog`, async () => {
      const { wrapper, router } = await render(HistoryDatabase)
      await wrapper.get('.project-card').trigger('click')
      expect(document.body.querySelector('.modal-content').textContent).toContain('cafe.md')
      document.body.querySelector(selector).click()
      await settle()
      expect(router.currentRoute.value.fullPath).toBe(expected)
      expect(document.body.querySelector('.modal-overlay')).toBeNull()
    })
  }
  it('shows an empty history without hiding the upload feature', async () => {
    state.history = []
    const { wrapper } = await render(Home)
    expect(wrapper.text()).toContain('尚無模擬紀錄')
    expect(wrapper.find('input[type=file]').exists()).toBe(true)
  })
  it('keeps the missing-service notice in the current UI language', async () => {
    state.status = { ready: false, llm_configured: true, graph_configured: false }
    const { wrapper } = await render(App, '/', {}, { stubs: { RouterView: true } })
    expect(wrapper.get('.setup-notice').text()).toContain('圖譜服務尚未就緒')
  })
})
