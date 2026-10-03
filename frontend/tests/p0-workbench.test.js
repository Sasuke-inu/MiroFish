import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import zhTW from '../../locales/zh-TW.json'
import Step2 from '../src/components/Step2EnvSetup.vue'
import Step3 from '../src/components/Step3Simulation.vue'
import Step4 from '../src/components/Step4Report.vue'
import SimulationView from '../src/views/SimulationView.vue'
import SimulationRunView from '../src/views/SimulationRunView.vue'
import MainView from '../src/views/MainView.vue'
import App from '../src/App.vue'
import { setPendingUpload, clearPendingUpload } from '../src/store/pendingUpload'

const { api, recoverNamespace } = vi.hoisted(() => ({ api: vi.fn(), recoverNamespace:vi.fn() }))
vi.mock('../src/api/workbench', () => ({recoverNamespace}))
vi.mock('../src/api/index.js', () => ({ default: Object.assign(api, {
  get: (url, options = {}) => api({ url, method: 'get', ...options }),
  post: (url, data, options = {}) => api({ url, method: 'post', data, ...options })
}) }))

const ok = data => ({ success: true, data })
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
let wrappers, overrides, run, report, actions, reportLogs
const requests = url => api.mock.calls.map(([r]) => r).filter(r => r.url === url)
const writes = () => api.mock.calls.map(([r]) => r).filter(r => r.method === 'post' && !r.url.endsWith('/prepare/status'))
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  wrappers = []; overrides = new Map(); clearPendingUpload()
  recoverNamespace.mockReset().mockResolvedValue({graph_namespace_status:'ready',execution_started:false,preparation_started:false})
  run = { runner_status: 'running', graph_ready: false, total_rounds: 2 }
  report = { report_id: 'r', simulation_id: 's', status: 'generating' }
  actions = []; reportLogs = []
  api.mockReset().mockImplementation(async r => {
    if (overrides.has(r.url)) return overrides.get(r.url)(r)
    if (r.url === '/api/system/status') return ok({ ready: true, graph_configured: true, llm_configured: true })
    if (r.url.endsWith('/run-status/detail')) return ok({ ...run, all_actions: actions })
    if (r.url.endsWith('/run-status')) return ok({ ...run })
    if (r.url === '/api/simulation/start') return ok({ ...run, runner_status: 'starting' })
    if (r.url === '/api/simulation/stop') return ok({ runner_status: 'stopping', graph_ready: false })
    if (r.url === '/api/simulation/env/close') return ok({})
    if (r.url.endsWith('/env-status')) return ok({ env_alive: true })
    if (r.url === '/api/simulation/prepare') return ok({ already_prepared: true })
    if (r.url === '/api/simulation/prepare/status') return ok({ status: 'idle' })
    if (r.url.endsWith('/profiles/realtime')) return ok({ profiles: [], total_expected: 0 })
    if (r.url.endsWith('/config/realtime')) return ok({ config_generated: false, is_generating: false })
    if (r.url.endsWith('/config')) return ok({ time_config: { minutes_per_round: 30 } })
    if (/^\/api\/simulation\/[^/]+$/.test(r.url)) return ok({ simulation_id: r.url.split('/').at(-1), status: 'created' })
    if (r.url === '/api/report/generate') return ok({ report_id: 'r', already_generated: true })
    if (r.url.endsWith('/agent-log')) return ok({ logs: r.params?.from_line ? [] : reportLogs, from_line: r.params?.from_line || 0 })
    if (r.url.endsWith('/console-log')) return ok({ logs: [], from_line: 0 })
    if (/^\/api\/report\/[^/]+$/.test(r.url)) return ok({ ...report })
    if (r.url.startsWith('/api/graph/project/')) return ok({ project_id: 'p', status: 'ontology_generated', graph_id: null })
    if (r.url === '/api/graph/ontology/generate') return ok({ project_id: 'p', status: 'ontology_generated' })
    if (r.url === '/api/graph/build') return ok({ task_id: 't' })
    if (r.url.includes('/task/')) return ok({ status: 'processing' })
    throw new Error(`Unexpected fixture request ${r.url}`)
  })
})
afterEach(() => { wrappers.forEach(w => w.unmount()); vi.clearAllTimers(); vi.useRealTimers(); clearPendingUpload(); document.body.innerHTML = '' })
async function render(component, props = { simulationId: 's', reportId: 'r', systemLogs: [] }, path = '/', stubs = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/process/:projectId', name: 'Process', component: MainView, props: true },
    { path: '/simulation/:simulationId', name: 'Simulation', component: SimulationView, props: true },
    { path: '/simulation/:simulationId/start', name: 'SimulationRun', component: SimulationRunView, props: true },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div />' } },
    { path: '/interaction/:reportId', name: 'Interaction', component: { template: '<div />' } }
  ] })
  await router.push(path); await router.isReady()
  const wrapper = mount(component, { props, attachTo: document.body, global: {
    plugins: [router, createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW } })],
    stubs: { GraphPanel: true, PreferenceControls: true, LanguageSwitcher: true, ...stubs }
  } })
  wrappers.push(wrapper); await flushPromises(); await flushPromises()
  return { wrapper, router }
}

describe('P0: viewing a workspace never purchases or resets work', () => {
  it('attaches report and section evidence to stable saved identities',async()=>{
    report.status='completed';report.outline={title:'報告',summary:'',sections:[{title:'段落',content:'保存文字'}]}
    const {wrapper}=await render(Step4,{projectId:'p',simulationId:'s',reportId:'r',systemLogs:[]},'/',{EvidenceLinks:true})
    expect(wrapper.findAllComponents({name:'EvidenceLinks'}).map(item=>[item.props('subjectType'),item.props('subjectId')])).toEqual([['report','r'],['report_section','r:section:1']])
    expect(writes()).toHaveLength(0)
  })
  it('attaches profile evidence to user_id zero instead of a display name',async()=>{
    overrides.set('/api/simulation/s',()=>ok({simulation_id:'s',status:'ready'}))
    overrides.set('/api/simulation/s/profiles/realtime',()=>ok({profiles:[{user_id:0,username:'角色',name:'alias',bio:'保存介紹'}]}))
    const {wrapper}=await render(Step2,{simulationId:'s',projectData:{project_id:'p'},systemLogs:[]},'/',{EvidenceLinks:true})
    await wrapper.get('.profile-card').trigger('click')
    expect(wrapper.findComponent({name:'EvidenceLinks'}).props('subjectId')).toBe('s:agent:0')
    expect(writes()).toHaveLength(0)
  })
  it('reconciles an uncertain graph copy only after clicking and then reads state without preparing', async () => {
    let state={simulation_id:'s',status:'needs_review',source_graph_id:'source',graph_id:'private',graph_clone_operation_id:'s',graph_namespace_status:'needs_review'}
    overrides.set('/api/simulation/s',()=>ok({...state}))
    const {wrapper}=await render(Step2)
    expect(recoverNamespace).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid=prepare-simulation]').exists()).toBe(false)
    state={...state,status:'created',graph_namespace_status:'ready'}
    await wrapper.get('[data-testid=recover-namespace]').trigger('click');await flushPromises()
    expect(recoverNamespace).toHaveBeenCalledExactlyOnceWith('s')
    expect(wrapper.find('[data-testid=prepare-simulation]').exists()).toBe(true)
    expect(requests('/api/simulation/prepare')).toHaveLength(0)
    expect(requests('/api/simulation/start')).toHaveLength(0)
  })
  it('analyzes saved draft text only after clicking, without automatically building its graph', async () => {
    overrides.set('/api/graph/project/p', () => ok({ project_id:'p',status:'created',simulation_requirement:'保存的問題' }))
    const {wrapper}=await render(MainView, {projectId:'p'}, '/process/p', {Step1GraphBuild:true})
    expect(writes()).toHaveLength(0)
    await wrapper.get('[data-testid=start-project]').trigger('click'); await flushPromises()
    expect(requests('/api/graph/ontology/generate')).toHaveLength(1)
    const form=requests('/api/graph/ontology/generate')[0].data
    expect(form.get('project_id')).toBe('p')
    expect(form.get('simulation_requirement')).toBe('保存的問題')
    expect(form.has('files')).toBe(false)
    expect(requests('/api/graph/build')).toHaveLength(0)
  })
  it.each(['idle', undefined])('reads %s runs without starting', async status => {
    run.runner_status = status
    await render(Step3)
    expect(requests('/api/simulation/start')).toHaveLength(0)
  })
  it('starts only after a cost-labelled user action and never forces a restart', async () => {
    run.runner_status = 'idle'
    const { wrapper } = await render(Step3)
    expect(writes()).toHaveLength(0)
    expect(wrapper.get('.generation-notice').text()).toMatch(/費用/)
    await wrapper.get('[data-testid=start-simulation]').trigger('click'); await flushPromises()
    expect(requests('/api/simulation/start')).toHaveLength(1)
    expect(requests('/api/simulation/start')[0].data.force).toBe(false)
  })
  it('does not stop a live environment when opening setup', async () => {
    await render(SimulationView, {}, '/simulation/s', { Step2EnvSetup: true })
    expect(writes()).toHaveLength(0)
  })
  it('does not prepare profiles when opening step 2', async () => {
    await render(Step2)
    expect(requests('/api/simulation/prepare')).toHaveLength(0)
  })
  it('prepares only after an explicit action, with no force flag', async () => {
    const { wrapper } = await render(Step2)
    expect(writes()).toHaveLength(0)
    await wrapper.get('[data-testid=prepare-simulation]').trigger('click'); await flushPromises()
    expect(requests('/api/simulation/prepare')).toHaveLength(1)
    expect(requests('/api/simulation/prepare')[0].data.force_regenerate).toBe(false)
  })
  it('resumes observing an existing preparation task without submitting another', async () => {
    overrides.set('/api/simulation/s', () => ok({ simulation_id: 's', status: 'preparing', prepare_task_id: 'existing' }))
    await render(Step2)
    await vi.advanceTimersByTimeAsync(6100)
    expect(requests('/api/simulation/prepare')).toHaveLength(0)
    expect(requests('/api/simulation/prepare/status').length).toBeGreaterThan(1)
  })
  it('does not generate an ontology from a pending upload on mount', async () => {
    setPendingUpload([new File(['fictional'], 'fixture.txt')], 'fixture')
    await render(MainView, {}, '/process/new')
    expect(writes()).toHaveLength(0)
  })
  it('does not build an existing ontology on mount', async () => {
    await render(MainView, {}, '/process/p')
    expect(requests('/api/graph/build')).toHaveLength(0)
  })
  it('builds only after the explicit project action', async () => {
    const { wrapper } = await render(MainView, {}, '/process/p')
    await wrapper.get('[data-testid=start-project]').trigger('click'); await flushPromises()
    expect(requests('/api/graph/build')).toHaveLength(1)
    expect(requests('/api/graph/build')[0].data.force).toBe(false)
  })
  it('does not send graph generation after navigating away during its configuration check', async () => {
    const { wrapper } = await render(MainView, {}, '/process/p')
    const pending = deferred(); overrides.set('/api/system/status', () => pending.promise)
    await wrapper.get('[data-testid=start-project]').trigger('click'); wrapper.unmount()
    pending.resolve(ok({ graph_configured: true })); await flushPromises()
    expect(requests('/api/graph/build')).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('ignores an initial status response after unmount', async () => {
    const pending = deferred(); overrides.set('/api/simulation/s/run-status', () => pending.promise)
    const { wrapper } = await render(Step3); wrapper.unmount()
    pending.resolve(ok({ runner_status: 'idle' })); await flushPromises()
    expect(writes()).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('changes simulation identity when the URL changes', async () => {
    const { router } = await render(App, {}, '/simulation/s/start')
    await router.push('/simulation/other/start'); await flushPromises()
    expect(requests('/api/simulation/other/run-status').length).toBeGreaterThan(0)
    const oldCount = requests('/api/simulation/s/run-status').length
    await vi.advanceTimersByTimeAsync(6000)
    expect(requests('/api/simulation/s/run-status')).toHaveLength(oldCount)
  })
})

describe('P0: terminal state and polling ownership', () => {
  it.each(['failed', 'stopped', 'interrupted', 'needs_review'])('does not offer a complete report for %s', async status => {
    run.runner_status = status; run.graph_ready = true
    const { wrapper } = await render(Step3)
    expect(wrapper.get('.action-btn.primary').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role=alert]').text()).not.toBe('')
  })
  it('requires graph readiness even after a completed run', async () => {
    run.runner_status = 'completed'
    const { wrapper } = await render(Step3)
    expect(wrapper.get('.action-btn.primary').attributes('disabled')).toBeDefined()
  })
  it('uses the existing report instead of forcing regeneration', async () => {
    run.runner_status = 'completed'; run.graph_ready = true
    const { wrapper, router } = await render(Step3)
    await wrapper.get('.action-btn.primary').trigger('click'); await flushPromises()
    expect(requests('/api/report/generate')[0].data.force_regenerate).toBe(false)
    expect(router.currentRoute.value.fullPath).toBe('/report/r')
  })
  it('keeps polling while a stop request is still stopping', async () => {
    const { wrapper } = await render(Step3)
    await wrapper.findAll('button').find(b => b.text() === '停止模擬').trigger('click'); await flushPromises()
    const count = requests('/api/simulation/s/run-status').length
    run.runner_status = 'stopping'
    await vi.advanceTimersByTimeAsync(2100)
    expect(requests('/api/simulation/s/run-status').length).toBeGreaterThan(count)
    expect(wrapper.get('.action-btn.primary').attributes('disabled')).toBeDefined()
  })
  it('never overlaps slow status reads', async () => {
    await render(Step3)
    const pending = deferred(); overrides.set('/api/simulation/s/run-status', () => pending.promise)
    const count = requests('/api/simulation/s/run-status').length
    await vi.advanceTimersByTimeAsync(6500)
    expect(requests('/api/simulation/s/run-status').length - count).toBe(1)
    pending.resolve(ok({ ...run })); await flushPromises()
  })
  it('does not let a stale status response undo an acknowledged stop', async () => {
    const { wrapper } = await render(Step3)
    const pending = deferred(); overrides.set('/api/simulation/s/run-status', () => pending.promise)
    await vi.advanceTimersByTimeAsync(2000)
    await wrapper.findAll('button').find(b => b.text() === '停止模擬').trigger('click'); await flushPromises()
    pending.resolve(ok({ runner_status: 'running' })); await flushPromises()
    expect(wrapper.findAll('button').some(b => b.text() === '正在停止')).toBe(true)
    expect(wrapper.get('.action-btn.primary').attributes('disabled')).toBeDefined()
  })
  it('shows a polling connection error while preserving actions and then recovers read-only', async () => {
    actions = [{ id: 'kept', platform: 'twitter', agent_id: 1, action_type: 'CREATE_POST', action_args: { content: '保留內容' }, timestamp: '2026-10-03T00:00:00Z' }]
    const { wrapper } = await render(Step3)
    overrides.set('/api/simulation/s/run-status', () => { throw new Error('fixture disconnected') })
    await vi.advanceTimersByTimeAsync(2100)
    expect(wrapper.get('[role=alert]').text()).toContain('fixture disconnected')
    expect(wrapper.text()).toContain('保留內容')
    overrides.delete('/api/simulation/s/run-status'); await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
    expect(writes()).toHaveLength(0)
  })
  it('reads the final action snapshot after completion', async () => {
    const { wrapper } = await render(Step3)
    actions = [{ id: 'last', platform: 'twitter', agent_id: 1, agent_name: '最後角色', action_type: 'CREATE_POST', action_args: { content: '最後動作' }, timestamp: '2026-10-03T00:00:00Z' }]
    run.runner_status = 'completed'; run.graph_ready = true
    await vi.advanceTimersByTimeAsync(2100); await flushPromises()
    expect(wrapper.text()).toContain('最後動作')
  })
  it.each(['failed', 'interrupted', 'needs_review'])('shows persisted report %s and stops polling without regenerating', async status => {
    report.status = status; report.error = 'fixture stopped safely'
    const { wrapper } = await render(Step4)
    expect(wrapper.get('[role=alert]').text()).toContain('fixture stopped safely')
    const count = api.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(api.mock.calls).toHaveLength(count)
    expect(writes()).toHaveLength(0)
  })
  it('handles terminal error logs even before persisted status catches up', async () => {
    reportLogs = [{ action: 'error', stage: 'failed', details: { error: 'fixture terminal error' } }]
    const { wrapper } = await render(Step4)
    expect(wrapper.get('[role=alert]').text()).toContain('fixture terminal error')
    const count = api.mock.calls.length; await vi.advanceTimersByTimeAsync(6000)
    expect(api.mock.calls).toHaveLength(count)
  })
  it('preserves completed report sections when the report is interrupted', async () => {
    report.status = 'interrupted'
    report.outline = { title: '保留報告', summary: '', sections: [{ title: '已完成', content: '仍可閱讀的內容' }, { title: '未完成', content: '' }] }
    const { wrapper } = await render(Step4)
    expect(wrapper.get('.generated-content').text()).toContain('仍可閱讀的內容')
    expect(wrapper.get('[role=alert]').text()).toContain('1/2')
    expect(wrapper.find('.next-step-btn').exists()).toBe(false)
    expect(wrapper.find('.waiting-animation').exists()).toBe(false)
  })
  it('discards old report logs after switching report identity', async () => {
    const pending = deferred(); overrides.set('/api/report/r/console-log', () => pending.promise)
    const { wrapper } = await render(Step4)
    await wrapper.setProps({ reportId: 'other' }); await flushPromises()
    pending.resolve(ok({ logs: ['OLD SECRET-FREE FIXTURE LOG'], from_line: 0 })); await flushPromises()
    expect(wrapper.text()).not.toContain('OLD SECRET-FREE FIXTURE LOG')
    expect(writes()).toHaveLength(0)
  })
})
