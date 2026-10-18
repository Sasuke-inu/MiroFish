import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import GraphPanel from '../src/components/GraphPanel.vue'
import HistoryDatabase from '../src/components/HistoryDatabase.vue'
import LanguageSwitcher from '../src/components/LanguageSwitcher.vue'
import zhTW from '../../locales/zh-TW.json'
import en from '../../locales/en.json'

const { history } = vi.hoisted(() => ({ history: vi.fn() }))
vi.mock('../src/api/simulation', () => ({ getSimulationHistory: history }))
const mounted = []
const sample = { simulation_id: 'sim_accessible', project_id: 'proj_accessible', report_id: 'report_accessible', simulation_requirement: '探索社區的咖啡店', created_at: '2026-10-03T09:00:00', total_rounds: 2, current_round: 2 }
const graph = { nodes: [
  { uuid: 'person', name: '住戶', labels: ['Entity', 'Resident'], attributes: { visits: 0, subscribed: false } },
  { uuid: 'shop', name: '咖啡店', labels: ['Entity', 'Shop'] }
], edges: [{ uuid: 'edge', source_node_uuid: 'person', target_node_uuid: 'shop', name: 'VISITS', fact: '住戶到店消費。' }] }

beforeEach(() => {
  history.mockReset().mockResolvedValue({ success: true, data: [sample] })
  localStorage.clear()
})
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  document.body.innerHTML = ''
  document.body.style.overflow = ''
})

async function render(component, props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/process/:projectId', name: 'Process', component: { template: '<div />' } },
    { path: '/simulation/:simulationId', name: 'Simulation', component: { template: '<div />' } },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div />' } }
  ] })
  await router.push('/')
  const i18n = createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en }, missingWarn: false, fallbackWarn: false })
  const wrapper = mount(component, { props, attachTo: document.body, global: { plugins: [router, i18n] } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

describe('Graph interaction quality', () => {
  it('filters the existing graph and offers a paged keyboard table with the same selection', async () => {
    const data = structuredClone(graph)
    for(let i=0;i<54;i++) data.nodes.push({uuid:`extra_${i}`,name:`額外 ${i}`,labels:['Entity','Resident']})
    const {wrapper}=await render(GraphPanel,{graphData:data})
    await wrapper.get('.graph-filters input').setValue('咖啡')
    await flushPromises()
    expect(wrapper.findAll('.nodes circle')).toHaveLength(1)
    await wrapper.get('.graph-filters input').setValue('')
    await wrapper.get('.graph-filters select').setValue('Resident')
    await wrapper.get('.graph-filters button').trigger('click')
    expect(wrapper.findAll('.graph-table-view tbody tr')).toHaveLength(50)
    await wrapper.findAll('.graph-table-paging button')[1].trigger('click')
    expect(wrapper.findAll('.graph-table-view tbody tr')).toHaveLength(5)
    const trigger=wrapper.get('.graph-table-view tbody button')
    trigger.element.focus()
    await trigger.trigger('click')
    await flushPromises()
    expect(wrapper.get('.detail-panel').text()).toContain('額外 49')
    await wrapper.get('.detail-close').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(trigger.element)
    expect(data.nodes).toHaveLength(56)
  })
  it('renders initially supplied data and opens node details with the keyboard without losing zero or false', async () => {
    const { wrapper } = await render(GraphPanel, { graphData: structuredClone(graph) })
    const node = wrapper.get('.nodes circle[role=button]')
    expect(node.attributes('tabindex')).toBe('0')
    node.element.focus()
    await node.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.findAll('.property-value').map(item => item.text())).toEqual(['0', 'false'])
    expect(document.activeElement).toBe(wrapper.get('.detail-close').element)
    await wrapper.get('.detail-panel').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(wrapper.find('.detail-panel').exists()).toBe(false)
    expect(document.activeElement).toBe(node.element)
  })

  it('opens relationships with Space and preserves node selection after zoom controls', async () => {
    const { wrapper } = await render(GraphPanel, { graphData: structuredClone(graph) })
    const edge = wrapper.get('.links path[role=button]')
    await edge.trigger('keydown', { key: ' ' })
    await flushPromises()
    expect(wrapper.get('.detail-content').text()).toContain('住戶到店消費。')
    await wrapper.get('.detail-close').trigger('click')
    const controls = wrapper.findAll('.graph-zoom-tools button')
    await controls[0].trigger('click')
    expect(wrapper.get('.graph-svg > g').attributes('transform')).toContain('scale(1.3)')
    await controls[2].trigger('click')
    expect(wrapper.get('.graph-svg > g').attributes('transform')).toBe('translate(0,0) scale(1)')
    await wrapper.get('.nodes circle').trigger('click')
    expect(wrapper.get('.detail-content').text()).toContain('住戶')
  })

  it('shows an explicit empty state and loading state rather than an empty SVG', async () => {
    const { wrapper } = await render(GraphPanel, { graphData: { nodes: [], edges: [] } })
    expect(wrapper.find('.graph-svg').exists()).toBe(false)
    expect(wrapper.get('[role=status]').text()).not.toBe('')
    expect(wrapper.find('.graph-zoom-tools').exists()).toBe(false)
    await wrapper.setProps({ loading: true })
    expect(wrapper.get('[role=status]').text()).toContain(zhTW.graph.graphDataLoading)
  })

  it('refreshes the selected details and removes them when the node is no longer in the graph', async () => {
    const { wrapper } = await render(GraphPanel, { graphData: structuredClone(graph) })
    await wrapper.get('.nodes circle').trigger('click')
    const refreshed = structuredClone(graph)
    refreshed.nodes[0].summary = '已更新的來源內容'
    await wrapper.setProps({ graphData: refreshed })
    expect(wrapper.get('.detail-panel').text()).toContain('已更新的來源內容')
    await wrapper.setProps({ graphData: { nodes: [refreshed.nodes[1]], edges: [] } })
    expect(wrapper.find('.detail-panel').exists()).toBe(false)
  })
})

describe('History recovery and keyboard navigation', () => {
  it('distinguishes unavailable history from no history and supports retry', async () => {
    history.mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = await render(HistoryDatabase)
    expect(wrapper.find('.history-empty').exists()).toBe(false)
    expect(wrapper.find('[role=alert]').exists()).toBe(true)
    await wrapper.get('.history-error button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
    expect(wrapper.findAll('.project-card')).toHaveLength(1)
    expect(history).toHaveBeenCalledTimes(2)
  })

  it('opens replay with keyboard, contains focus, and restores page state and opener on Escape', async () => {
    document.body.style.overflow = 'auto'
    const { wrapper } = await render(HistoryDatabase)
    const card = wrapper.get('.project-card')
    card.element.focus()
    await card.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    const dialog = document.querySelector('[role=dialog]')
    const close = dialog.querySelector('.modal-close')
    const last = dialog.querySelector('.btn-report')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(close)
    expect(document.body.style.overflow).toBe('hidden')
    close.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(last)
    last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(close)
    close.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role=dialog]')).toBeNull()
    expect(document.body.style.overflow).toBe('auto')
    expect(document.activeElement).toBe(card.element)
  })

  it('keeps the page scrollable when leaving while a replay is open', async () => {
    const { wrapper } = await render(HistoryDatabase)
    await wrapper.get('.project-card').trigger('click')
    await flushPromises()
    expect(document.body.style.overflow).toBe('hidden')
    wrapper.unmount()
    expect(document.body.style.overflow).toBe('')
    mounted.splice(mounted.indexOf(wrapper), 1)
  })
})

describe('Language chooser focus', () => {
  it('supports arrow navigation, Escape, and a focus return after choosing a language', async () => {
    const { wrapper } = await render(LanguageSwitcher)
    const trigger = wrapper.get('.switcher-trigger')
    trigger.element.focus()
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    const choices = wrapper.findAll('.locale-choice')
    expect(document.activeElement).toBe(choices[0].element)
    await choices[0].trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(choices[1].element)
    await choices[1].trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.switcher-dropdown').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    await trigger.trigger('click')
    await wrapper.findAll('.locale-choice').find(choice => choice.text() === 'English').trigger('click')
    expect(document.documentElement.lang).toBe('en')
    expect(document.activeElement).toBe(trigger.element)
  })
})
