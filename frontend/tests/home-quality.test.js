import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import Home from '../src/views/Home.vue'
import Settings from '../src/views/SettingsView.vue'
import App from '../src/App.vue'
import productionRouter from '../src/router'
import zhTW from '../../locales/zh-TW.json'
import { createFixtureAdapter } from './fixtures/api'
import service from '../src/api'
import { providerClient } from '../src/api/providers'

const wrappers = []
afterEach(() => {
  wrappers.splice(0).forEach(w => w.unmount())
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  localStorage.clear()
})
async function render(component = Home, provide = {}, path = '/') {
  const fixtureAdapter = createFixtureAdapter()
  service.defaults.adapter = fixtureAdapter
  providerClient.defaults.adapter = fixtureAdapter
  const router = createRouter({ history: createMemoryHistory(), routes: productionRouter.options.routes })
  await router.push(path)
  const i18n = createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW } })
  const wrapper = mount(component, { attachTo: document.body, global: { plugins: [router, i18n], provide, stubs: component === Home ? { HistoryDatabase: true, WebSources: true } : {} } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
async function choose(wrapper, files) {
  const input = wrapper.get('#source-files')
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')
}

describe('Workspace quality regressions', () => {
  it('explains rejected files and keeps supported files without duplicating them', async () => {
    const { wrapper } = await render()
    const valid = new File(['source'], 'notes.md', { lastModified: 42 })
    await choose(wrapper, [valid, valid, new File([], 'empty.txt'), new File(['png'], 'photo.png')])
    expect(wrapper.findAll('.file-item')).toHaveLength(1)
    expect(wrapper.get('.file-feedback').text()).toContain('重複')
    expect(wrapper.get('.file-feedback').text()).toContain('空白')
    expect(wrapper.get('.file-feedback').text()).toContain('只支援')
    expect(wrapper.get('.file-summary').text()).toContain('1 份資料')
  })
  it('rejects oversized totals before upload, and allows reselecting a removed file', async () => {
    const { wrapper } = await render()
    const huge = new File(['x'], 'huge.txt')
    Object.defineProperty(huge, 'size', { value: 50 * 1024 * 1024 })
    await choose(wrapper, [huge])
    expect(wrapper.findAll('.file-item')).toHaveLength(0)
    expect(wrapper.get('.file-feedback').text()).toContain('49 MB')
    const valid = new File(['source'], 'notes.md')
    await choose(wrapper, [valid])
    await wrapper.get('.remove-btn').trigger('click')
    await choose(wrapper, [valid])
    expect(wrapper.findAll('.file-item')).toHaveLength(1)
    expect(wrapper.get('#source-files').element.value).toBe('')
  })
  it('accepts the full Markdown extension and rejects names that only resemble an extension', async () => {
    const { wrapper } = await render()
    await choose(wrapper, [new File(['notes'], 'notes.markdown'), new File(['pdf'], 'pdf'), new File(['pdf'], '.pdf'), new File(['text'], 'txt')])
    expect(wrapper.findAll('.file-name').map(file => file.text())).toEqual(['notes.markdown'])
    expect(wrapper.get('.file-feedback').text()).toContain('只支援')
  })
  it('offers examples without starting a request or replacing an existing goal', async () => {
    const { wrapper, router } = await render()
    await wrapper.get('.goal-examples button').trigger('click')
    expect(wrapper.get('#simulation-goal').element.value).toContain('社區')
    expect(wrapper.find('.goal-examples').exists()).toBe(false)
    expect(router.currentRoute.value.path).toBe('/')
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeDefined()
    expect(document.activeElement.id).toBe('simulation-goal')
  })
  it('moves keyboard focus to history when using the shortcut', async () => {
    const scroll = vi.fn()
    const { wrapper } = await render(App)
    const section = wrapper.get('#project-history')
    section.element.scrollIntoView = scroll
    await wrapper.get('.history-link').trigger('click')
    expect(document.activeElement).toBe(wrapper.get('#history-heading').element)
    expect(scroll).toHaveBeenCalledOnce()
  })
  it('shows an honest service failure and offers a retry instead of checking forever', async () => {
    const retry = vi.fn()
    const { wrapper } = await render(Home, { systemStatus: ref(null), systemStatusError: ref(true), refreshSystemStatus: retry })
    expect(wrapper.get('.service-card').text()).toContain(zhTW.settings.unreachable)
    expect(wrapper.get('.service-card').text()).not.toContain(zhTW.studio.checking)
    await wrapper.get('.service-retry').trigger('click')
    expect(retry).toHaveBeenCalledOnce()
  })
  it('opens a useful recovery page for unknown links', async () => {
    const { wrapper, router } = await render(App, {}, '/missing-page')
    expect(wrapper.get('h1').text()).toBe(zhTW.quality.notFoundTitle)
    await wrapper.get('.missing-page a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
  })
  it('returns safely home when settings receives an unknown return path', async () => {
    const { wrapper, router } = await render(Settings, {}, '/settings?from=/does-not-exist')
    await wrapper.get('.settings-back').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
  })
})
