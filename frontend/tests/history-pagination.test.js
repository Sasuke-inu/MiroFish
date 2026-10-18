import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import HistoryDatabase from '../src/components/HistoryDatabase.vue'
import zhTW from '../../locales/zh-TW.json'
import zh from '../../locales/zh.json'
import en from '../../locales/en.json'

const { history } = vi.hoisted(() => ({ history: vi.fn() }))
vi.mock('../src/api/simulation', () => ({ getSimulationHistory: history }))
let wrapper
const records = Array.from({ length: 45 }, (_, index) => ({
  simulation_id: `sim_${index}`, project_id: `project_${index}`, report_id: `report_${index}`,
  simulation_requirement: `探索問題 ${index}：咖啡店調整營業時間後，附近居民與常客會如何互動？`,
  created_at: '2026-10-03T09:00:00', total_rounds: 2, current_round: 2,
  files: Array.from({ length: 5 }, (_, file) => ({ filename: `source-${file}.md` }))
}))
const page = (offset, limit = 20) => ({ success: true, data: records.slice(offset, offset + limit), pagination: {
  offset, limit, total: records.length, next_offset: Math.min(offset + limit, records.length), has_more: offset + limit < records.length
} })
beforeEach(() => history.mockReset().mockImplementation((limit, offset) => Promise.resolve(page(offset, limit))))
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; document.body.style.overflow = '' })

async function render(locale = 'zh-TW') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/process/:projectId', name: 'Process', component: { template: '<div />' } },
    { path: '/simulation/:simulationId', name: 'Simulation', component: { template: '<div />' } },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div />' } }
  ] })
  await router.push('/')
  wrapper = mount(HistoryDatabase, { attachTo: document.body, global: { plugins: [router,
    createI18n({ legacy: false, locale, messages: { 'zh-TW': zhTW, zh, en } })] } })
  await flushPromises()
  return router
}

describe('History pagination and replay', () => {
  it('reaches all 45 records in three bounded pages and focuses newly loaded content', async () => {
    await render()
    expect(wrapper.get('h2#history-heading').attributes('tabindex')).toBe('-1')
    expect(wrapper.findAll('.project-card')).toHaveLength(20)
    await wrapper.get('.load-more').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(40)
    expect(document.activeElement).toBe(wrapper.findAll('.project-card')[20].element)
    await wrapper.get('.load-more').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(45)
    expect(wrapper.find('.load-more').exists()).toBe(false)
    expect(history.mock.calls).toEqual([[20, 0], [20, 20], [20, 40]])
    expect(wrapper.get('.history-count').text()).toContain('45／45')
  })

  it('keeps existing records and retries the same offset after a later page fails', async () => {
    await render()
    history.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('.load-more').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(20)
    expect(wrapper.get('.history-error').text()).toContain(zhTW.history.list.moreFailed)
    await wrapper.get('.history-error button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(40)
    expect(history.mock.calls).toEqual([[20, 0], [20, 20], [20, 20]])
  })

  it('does not duplicate a page while loading and can recover if a server repeats a page', async () => {
    await render()
    let finish
    history.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('.load-more').trigger('click')
    await wrapper.get('.load-more').trigger('click')
    expect(history).toHaveBeenCalledTimes(2)
    finish(page(0))
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(20)
    expect(wrapper.find('.history-error').exists()).toBe(true)
    await wrapper.get('.history-error button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(40)
  })

  it.each(['zh-TW', 'zh', 'en'])('shows fuller questions, readable status and all files in %s', async locale => {
    await render(locale)
    const messages = { 'zh-TW': zhTW, zh, en }[locale]
    const row = wrapper.get('.project-card')
    expect(row.get('.card-title').text()).toBe(records[0].simulation_requirement)
    expect(row.attributes('aria-label')).toContain('2026-10-03 09:00')
    expect(row.get('.card-progress').text()).toContain(messages.history.list.completed)
    expect(row.text()).not.toContain('sim_0')
    await row.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    const dialog = document.querySelector('[role=dialog]')
    expect(dialog.querySelectorAll('.modal-file-item')).toHaveLength(5)
    expect(dialog.querySelector('.modal-id').textContent).toBe('sim_0')
    expect(dialog.textContent).not.toContain('history.list.')
  })

  it.each([
    ['.btn-project', '/process/project_0'],
    ['.btn-simulation', '/simulation/sim_0'],
    ['.btn-report', '/report/report_0']
  ])('preserves replay path %s', async (button, expected) => {
    const router = await render()
    await wrapper.get('.project-card').trigger('click')
    await flushPromises()
    document.querySelector(button).click()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(expected)
    expect(document.querySelector('[role=dialog]')).toBeNull()
  })
})
