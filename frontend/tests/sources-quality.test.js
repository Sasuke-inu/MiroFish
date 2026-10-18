import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent } from 'vue'
import zhTW from '../../locales/zh-TW.json'
import WebSources from '../src/components/WebSources.vue'
import SourceUsageCard from '../src/components/SourceUsageCard.vue'
import { useSourceCollection } from '../src/composables/useSourceCollection'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/index.js', () => ({ default: {
  get: (url, options) => api({ url, ...options }),
  post: (url, data, options) => api({ url, data, ...options })
} }))

const budget = { used: 1, daily_limit: 10, remaining: 9, resets_at: '2026-10-04T00:00:00+10:00', timezone: 'Australia/Sydney' }
const sourceStatus = { enabled: true, configured: true, online: true, max_pages_per_job: 3, max_chars_per_page: 8000, cache_hours: 24, budget }
const makeDocument = id => ({ id, title: `文章 ${id}`, url: `https://example.com/${id}`, filename: `${id}.md`, markdown: `# 文章 ${id}`, chars: 20, fetched_at: '2026-10-03T10:00:00+10:00', cached: false, truncated: false })
const CollectionHarness = defineComponent({
  components: { WebSources }, setup: () => ({ collection: useSourceCollection() }),
  template: '<WebSources :collection="collection" />'
})
let wrappers = []
let result
const success = data => ({ success: true, data })

beforeEach(() => {
  result = { documents: [makeDocument('first')], errors: [], attempted: 1, replayed: false, budget }
  api.mockReset().mockImplementation(async ({ url, data }) => {
    if (url === '/api/sources/status') return success(sourceStatus)
    if (url === '/api/sources/plan') return success({ plan_id: 'reviewed-plan', new_pages: 1, cached_pages: 0, entries: data.urls.map(url => ({ url, cached: false })), budget })
    if (url === '/api/sources/fetch') return success(result)
    throw new Error(`Unexpected request: ${url}`)
  })
})

afterEach(() => { wrappers.forEach(wrapper => wrapper.unmount()); wrappers = []; document.body.innerHTML = '' })

async function render(component = CollectionHarness) {
  const wrapper = mount(component, { attachTo: document.body, global: { plugins: [createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW } })] } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
const requests = url => api.mock.calls.filter(([request]) => request.url === url)

describe('Source collection recovery and accessibility', () => {
  it('keeps successful input when a later request times out without silently retrying', async () => {
    const wrapper = await render()
    await wrapper.get('#web-source-urls').setValue('https://example.com/first')
    expect(await wrapper.vm.collection.prepare()).toBe(true)
    const original = api.getMockImplementation()
    api.mockImplementation(request => request.url === '/api/sources/fetch'
      ? Promise.reject({ code: 'ECONNABORTED' }) : original(request))
    await wrapper.get('#web-source-urls').setValue('https://example.com/first\nhttps://example.com/second')
    expect(await wrapper.vm.collection.prepare()).toBe(false)
    await flushPromises()
    expect(wrapper.vm.collection.getFiles().map(file => file.name)).toEqual(['first.md'])
    expect(wrapper.get('[role=alert]').text()).toBeTruthy()
    expect(requests('/api/sources/fetch')).toHaveLength(2)
  })

  it('has a labeled always-available input and optional read-only document details', async () => {
    const wrapper = await render()
    const input = wrapper.get('#web-source-urls')
    expect(wrapper.find('label[for="web-source-urls"]').exists()).toBe(true)
    expect(input.attributes('disabled')).toBeUndefined()
    await input.setValue('https://example.com/first')
    expect(await wrapper.vm.collection.prepare()).toBe(true)
    await flushPromises()
    expect(wrapper.find('details summary').exists()).toBe(true)
    expect(wrapper.get('pre').text()).toContain('# 文章 first')
    expect(wrapper.findAll('textarea')).toHaveLength(1)
    // Long scraped content must never be announced as a live status region.
    expect(wrapper.get('pre').element.closest('[aria-live], [role="status"], [role="alert"]')).toBeNull()
  })

  it('reports truncation alongside the automatically prepared page', async () => {
    result.documents[0].truncated = true
    const wrapper = await render()
    await wrapper.get('#web-source-urls').setValue('https://example.com/first')
    expect(await wrapper.vm.collection.prepare()).toBe(true)
    await flushPromises()
    expect(wrapper.text()).toContain('8,000')
    expect(wrapper.vm.collection.getFiles()).toHaveLength(1)
  })

  it('does not display a previous connection status as current after a failed refresh', async () => {
    const wrapper = await render(SourceUsageCard)
    expect(wrapper.text()).toContain('已連接本機服務')
    api.mockRejectedValueOnce(new Error('Offline'))
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('已連接本機服務')
    expect(wrapper.find('dl').exists()).toBe(false)
    expect(wrapper.get('[role=alert]').exists()).toBe(true)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已連接本機服務')
  })

  it('shows progress during the initial status check and avoids duplicate refreshes', async () => {
    let finish
    api.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await render(SourceUsageCard)
    expect(wrapper.get('[role=status]').text()).toContain('載入中')
    expect(wrapper.get('section').attributes('aria-busy')).toBe('true')
    await wrapper.get('button').trigger('click')
    expect(api).toHaveBeenCalledTimes(1)
    finish(success(sourceStatus))
    await flushPromises()
    expect(wrapper.get('section').attributes('aria-busy')).toBe('false')
    expect(wrapper.find('[role=status]').exists()).toBe(false)
  })
})
