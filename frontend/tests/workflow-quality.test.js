import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import zhTW from '../../locales/zh-TW.json'
import { createFixtureAdapter } from './fixtures/api'
import Step1 from '../src/components/Step1GraphBuild.vue'
import Step2 from '../src/components/Step2EnvSetup.vue'
import Step3 from '../src/components/Step3Simulation.vue'
import Step4 from '../src/components/Step4Report.vue'
import Step5 from '../src/components/Step5Interaction.vue'
import MainView from '../src/views/MainView.vue'
import SimulationView from '../src/views/SimulationView.vue'
import SimulationRunView from '../src/views/SimulationRunView.vue'
import ReportView from '../src/views/ReportView.vue'
import InteractionView from '../src/views/InteractionView.vue'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/index.js', () => ({ default: Object.assign(api, {
  get: (url, options = {}) => api({ url, method: 'get', ...options }),
  post: (url, data, options = {}) => api({ url, method: 'post', data, ...options })
}) }))

let mounted = []
let overrides
const ok = data => ({ success: true, data })
const props = { simulationId: 'sim_fixture', reportId: 'report_fixture', systemLogs: [] }

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  overrides = new Map()
  const fixture = createFixtureAdapter()
  api.mockReset().mockImplementation(async request => {
    if (overrides.has(request.url)) return overrides.get(request.url)(request)
    return (await fixture(request)).data
  })
})

afterEach(() => {
  mounted.forEach(wrapper => wrapper.unmount())
  mounted = []
  document.body.innerHTML = ''
  vi.clearAllTimers()
  vi.useRealTimers()
})

async function render(component, componentProps = props, path = '/', stubs = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/process/:projectId', name: 'Process', component: MainView },
    { path: '/simulation/:simulationId', name: 'Simulation', component: SimulationView },
    { path: '/simulation/:simulationId/start', name: 'SimulationRun', component: SimulationRunView },
    { path: '/report/:reportId', name: 'Report', component: ReportView },
    { path: '/interaction/:reportId', name: 'Interaction', component: InteractionView }
  ] })
  await router.push(path)
  const wrapper = mount(component, { props: componentProps, attachTo: document.body, global: {
    plugins: [router, createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW } })], stubs
  } })
  mounted.push(wrapper)
  await flushPromises()
  await flushPromises()
  return wrapper
}

function calls(url) { return api.mock.calls.map(([request]) => request).filter(request => request.url === url) }

describe('Workflow quality regressions', () => {
  it('opens ontology details with the keyboard and restores focus on Escape', async () => {
    const wrapper = await render(Step1, { currentPhase: 2, projectData: { project_id: 'proj_fixture', graph_id: 'graph_fixture', ontology: { entity_types: [{ name: 'Resident', description: '住戶' }] } }, systemLogs: [] })
    const tag = wrapper.get('.entity-tag')
    tag.element.focus()
    await tag.trigger('keydown', { key: 'Enter' })
    expect(wrapper.get('.ontology-detail-overlay').attributes('role')).toBe('region')
    expect(document.activeElement).toBe(wrapper.get('.close-btn').element)
    await wrapper.get('.close-btn').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.ontology-detail-overlay').exists()).toBe(false)
    expect(document.activeElement).toBe(tag.element)
  })

  it('shows simulation creation errors beside the action without a browser alert', async () => {
    overrides.set('/api/simulation/create', () => ({ success: false, error: '服務尚未回應' }))
    const wrapper = await render(Step1, { currentPhase: 2, projectData: { project_id: 'proj_fixture', graph_id: 'graph_fixture' }, systemLogs: [] })
    await wrapper.get('.action-btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('服務尚未回應')
    expect(wrapper.get('.action-btn').attributes('disabled')).toBeUndefined()
  })

  it('preserves a two-round plan and allows an inexpensive one-round test', async () => {
    overrides.set('/api/simulation/sim_fixture/config/realtime', () => ok({ config_generated: true, config: { time_config: { total_simulation_hours: 1, minutes_per_round: 30 }, agent_configs: [], event_config: {} } }))
    const wrapper = await render(Step2)
    expect(wrapper.get('.auto-value').text()).toContain('2')
    await wrapper.get('.switch-control input').setValue(true)
    const slider = wrapper.get('input[type=range]')
    expect(slider.attributes('min')).toBe('1')
    expect(slider.attributes('max')).toBe('2')
    expect(slider.element.value).toBe('2')
    expect(wrapper.find('.mark-recommend').exists()).toBe(false)
    await slider.setValue('1')
    await wrapper.get('.action-btn.primary').trigger('click')
    expect(wrapper.emitted('next-step')[0][0]).toEqual({ maxRounds: 1 })
  })

  it('keeps the one-round slider valid and names it for screen readers', async () => {
    overrides.set('/api/simulation/sim_fixture/config/realtime', () => ok({ config_generated: true, config: { time_config: { total_simulation_hours: 0.5, minutes_per_round: 30 }, agent_configs: [], event_config: {} } }))
    const wrapper = await render(Step2)
    await wrapper.get('.switch-control input').setValue(true)
    const slider = wrapper.get('input[type=range]')
    expect(slider.attributes('max')).toBe('1')
    expect(slider.attributes('aria-label')).toBeTruthy()
    expect(slider.attributes('style')).not.toMatch(/NaN|Infinity/)
  })

  it('supports keyboard profile details, trapped focus and Escape', async () => {
    const wrapper = await render(Step2)
    const card = wrapper.findAll('.profile-card')[0]
    card.element.focus()
    await card.trigger('keydown', { key: 'Enter' })
    const close = wrapper.get('.profile-modal .close-btn')
    expect(wrapper.get('[role=dialog]').attributes('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(close.element)
    await close.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(close.element)
    await close.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role=dialog]').exists()).toBe(false)
    expect(document.activeElement).toBe(card.element)
  })

  it('puts startup failures where users can see them', async () => {
    overrides.set('/api/simulation/sim_fixture/run-status', () => ({ success: false, error: '模型未連線' }))
    const wrapper = await render(Step3)
    expect(wrapper.get('[role=alert]').text()).toContain('模型未連線')
    expect(calls('/api/simulation/start')).toHaveLength(0)
  })

  it('shows preparation failure and does not enable the start button', async () => {
    overrides.set('/api/simulation/sim_fixture', () => ok({ simulation_id: 'sim_fixture', status: 'created' }))
    overrides.set('/api/simulation/prepare', () => ({ success: false, error: '缺少角色資料' }))
    const wrapper = await render(Step2)
    await wrapper.get('[data-testid=prepare-simulation]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('缺少角色資料')
    expect(wrapper.get('.action-btn.primary').attributes('disabled')).toBeDefined()
  })

  it('shows a report connection failure and recovers without generating a new report', async () => {
    overrides.set('/api/report/report_fixture/agent-log', () => {
      overrides.delete('/api/report/report_fixture/agent-log')
      return { success: false, error: '連線中斷' }
    })
    const wrapper = await render(Step4)
    expect(wrapper.get('[role=alert]').text()).toContain('連線中斷')
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
    expect(wrapper.find('.generated-content').exists()).toBe(true)
    expect(calls('/api/report/generate')).toHaveLength(0)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
  })

  it.each([Step4, Step5])('renders untrusted report HTML as text while preserving emphasis and blockquotes', async component => {
    overrides.set('/api/report/report_fixture/agent-log', () => ok({ from_line: 0, logs: [
      { action: 'planning_complete', timestamp: '2026-10-03T01:00:00Z', details: { outline: { title: '測試報告', sections: [{ title: '章節' }] } } },
      { action: 'section_complete', timestamp: '2026-10-03T01:00:01Z', section_index: 1, details: { content: '**重點**\n\n> 引文\n\n<img src=x onerror="alert(1)"><script>alert(2)</script>' } },
      { action: 'report_complete', timestamp: '2026-10-03T01:00:02Z' }
    ] }))
    const wrapper = await render(component)
    const content = wrapper.get('.generated-content')
    expect(content.find('img, script').exists()).toBe(false)
    expect(content.get('strong').text()).toBe('重點')
    expect(content.get('blockquote').text()).toBe('引文')
    expect(content.text()).toContain('<img')
    const section = wrapper.get('.section-header-row')
    await section.trigger('keydown', { key: 'Enter' })
    expect(section.attributes('aria-expanded')).toBe('false')
  })

  it('does not submit while Enter is confirming Chinese text composition', async () => {
    const wrapper = await render(Step5)
    expect(calls('/api/report/report_fixture')).toHaveLength(1)
    expect(calls('/api/simulation/sim_fixture/profiles/realtime')).toHaveLength(1)
    const input = wrapper.get('.chat-input')
    await input.setValue('住戶的意見')
    await input.trigger('keydown', { key: 'Enter', isComposing: true })
    expect(calls('/api/report/chat')).toHaveLength(0)
    expect(input.element.value).toBe('住戶的意見')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(calls('/api/report/chat')).toHaveLength(1)
  })

  it('keeps each conversation separate when moving between report, agent and survey', async () => {
    overrides.set('/api/simulation/env-status', () => ok({ env_alive: true }))
    const wrapper = await render(Step5)
    await wrapper.get('.chat-input').setValue('報告問題')
    await wrapper.get('.send-btn').trigger('click')
    await flushPromises()
    await wrapper.get('.agent-pill').trigger('click')
    await wrapper.findAll('.dropdown-item')[0].trigger('click')
    expect(wrapper.findAll('.message-text')).toHaveLength(0)
    await wrapper.get('.chat-input').setValue('個人問題')
    await wrapper.get('.send-btn').trigger('click')
    await flushPromises()
    expect(calls('/api/simulation/interview/batch')[0].data.interviews[0].prompt).toBe('個人問題')
    await wrapper.get('.survey-pill').trigger('click')
    await wrapper.get('.action-bar-tabs > .tab-pill').trigger('click')
    expect(wrapper.findAll('.message-text').map(item => item.text()).join(' ')).toContain('報告問題')
    expect(wrapper.findAll('.message-text').map(item => item.text()).join(' ')).not.toContain('個人問題')
    await wrapper.get('.agent-pill').trigger('click')
    await wrapper.findAll('.dropdown-item')[0].trigger('click')
    expect(wrapper.findAll('.message-text').map(item => item.text()).join(' ')).toContain('個人問題')
  })

  it('locks conversation changes while the pending reply is being attached', async () => {
    let finish
    overrides.set('/api/report/chat', () => new Promise(resolve => { finish = resolve }))
    const wrapper = await render(Step5)
    await wrapper.get('.chat-input').setValue('稍後回覆')
    await wrapper.get('.send-btn').trigger('click')
    expect(wrapper.get('.agent-pill').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.survey-pill').attributes('disabled')).toBeDefined()
    finish(ok({ response: '完成回覆' }))
    await flushPromises()
    expect(wrapper.get('.agent-pill').attributes('disabled')).toBeUndefined()
    expect(wrapper.findAll('.message-text').map(item => item.text())).toContain('完成回覆')
  })

  it('shows survey failure next to the form and keeps the question for retry', async () => {
    overrides.set('/api/simulation/env-status', () => ok({ env_alive: true }))
    overrides.set('/api/simulation/interview/batch', () => ({ success: false, error: '稍後再試' }))
    const wrapper = await render(Step5)
    await wrapper.get('.survey-pill').trigger('click')
    await wrapper.findAll('.agent-checkbox input')[0].setValue(true)
    await wrapper.get('.survey-input').setValue('同意延長營業嗎？')
    await wrapper.get('.survey-submit-btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('稍後再試')
    expect(wrapper.get('.survey-input').element.value).toBe('同意延長營業嗎？')
  })

  it('labels a pending saved-report read as loading rather than generation', async () => {
    let finish
    overrides.set('/api/report/report_fixture', () => new Promise(resolve => { finish = resolve }))
    const wrapper = await render(ReportView, {}, '/report/report_fixture', { GraphPanel: true, Step4Report: true, PreferenceControls: true, LanguageSwitcher: true })
    expect(wrapper.get('[role=status]').text()).toBe('載入中...')
    finish(ok({report_id:'report_fixture', status:'completed'}))
    await flushPromises()
    expect(wrapper.get('[role=status]').text()).toBe('已完成')
    expect(api.mock.calls.flat().filter(call => call.method === 'post')).toHaveLength(0)
  })

  it.each([
    [MainView, '/process/proj_fixture'], [SimulationView, '/simulation/sim_fixture'],
    [SimulationRunView, '/simulation/sim_fixture/start'], [ReportView, '/report/report_fixture'],
    [InteractionView, '/interaction/report_fixture']
  ])('hides inactive panels without unmounting the workflow', async (component, path) => {
    const wrapper = await render(component, {}, path, { GraphPanel: true, Step1GraphBuild: true, Step2EnvSetup: true, Step3Simulation: true, Step4Report: true, Step5Interaction: true, PreferenceControls: true, LanguageSwitcher: true })
    expect(wrapper.get('#workspace-content').attributes('tabindex')).toBe('-1')
    const modes = wrapper.findAll('.switch-btn')
    await modes[0].trigger('click')
    expect(wrapper.get('.panel-wrapper.right').isVisible()).toBe(false)
    expect(wrapper.get('.panel-wrapper.right').attributes('inert')).toBeDefined()
    await modes[2].trigger('click')
    expect(wrapper.get('.panel-wrapper.left').isVisible()).toBe(false)
    await modes[1].trigger('click')
    expect(wrapper.get('.panel-wrapper.left').isVisible()).toBe(true)
    expect(wrapper.get('.panel-wrapper.right').isVisible()).toBe(true)
  })
})
