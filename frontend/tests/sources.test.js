import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, ref } from 'vue'
import en from '../../locales/en.json'
import zhTW from '../../locales/zh-TW.json'
import Home from '../src/views/Home.vue'
import WebSources from '../src/components/WebSources.vue'
import SourceUsageCard from '../src/components/SourceUsageCard.vue'
import App from '../src/App.vue'
import productionRouter from '../src/router'
import { useSourceCollection } from '../src/composables/useSourceCollection'
import { providerClient } from '../src/api/providers'
import { createFixtureAdapter } from './fixtures/api'
import { clearPendingUpload, getPendingUpload } from '../src/store/pendingUpload'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/index.js', () => ({ default: Object.assign(api, {
  get: (url, options = {}) => api({ url, method: 'get', ...options }),
  post: (url, data, options = {}) => api({ url, method: 'post', data, ...options })
}) }))
const budget = { used: 1, daily_limit: 10, remaining: 9, resets_at: '2026-10-04T00:00:00+10:00', timezone: 'Australia/Sydney' }
const initialStatus = { enabled: true, configured: true, online: true, mode: 'local', cloud_credits: 0,
  max_pages_per_job: 3, max_chars_per_page: 8000, cache_hours: 24, budget }
const sourceDocument = { id: 'source_1', title: '來源文章', url: 'https://example.com/article',
  filename: 'web-example-com.md', markdown: '# 來源文章\n來源：https://example.com/article\n擷取時間：2026-10-03T10:00:00+10:00\n\n<script>alert(1)</script>\nUseful article.',
  chars: 150, fetched_at: '2026-10-03T10:00:00+10:00', cached: false, truncated: false }
const secondDocument = { ...sourceDocument, id: 'source_2', title: '第二篇來源', url: 'https://example.com/second', filename: 'second.md', markdown: '# 第二篇\n來源：https://example.com/second\n\nSecond article.' }
const CollectionHarness = defineComponent({ components: { WebSources }, setup: () => ({ collection: useSourceCollection() }), template: '<WebSources :collection="collection" />' })
let wrappers = [], state
const success = data => ({ success: true, data })
beforeEach(() => {
  localStorage.clear()
  clearPendingUpload()
  providerClient.defaults.adapter = createFixtureAdapter()
  state = { status: structuredClone(initialStatus), result: { documents: [structuredClone(sourceDocument)], errors: [], attempted: 1, replayed: false, budget }, newPages: 1 }
  api.mockReset().mockImplementation(async request => {
    if (request.url === '/api/sources/status') return success(state.status)
    if (request.url === '/api/sources/plan') return success({ plan_id: 'approved_plan', new_pages: state.newPages,
      cached_pages: state.newPages ? 0 : 1, entries: request.data.urls.map(url => ({ url, cached: state.newPages === 0 })), budget })
    if (request.url === '/api/sources/fetch') return success(state.result)
    if (request.url === '/api/system/status') return success({ ready: true, llm_configured: true, graph_configured: true })
    throw new Error('Unexpected request: ' + request.url)
  })
})
afterEach(() => { wrappers.forEach(wrapper => wrapper.unmount()); wrappers = []; document.body.innerHTML = '' })
async function render(component = CollectionHarness) {
  const router = createRouter({ history: createMemoryHistory(), routes: productionRouter.options.routes })
  await router.push('/')
  const i18n = createI18n({ legacy: false, locale: 'zh-TW', fallbackLocale: 'en', messages: { 'zh-TW': zhTW, en } })
  const wrapper = mount(component, { attachTo: document.body, global: {
    plugins: [router, i18n], provide: { systemStatus: ref({ ready: true, llm_configured: true, graph_configured: true }) }, stubs: { HistoryDatabase: true }
  } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router, collection: wrapper.vm.collection }
}
const requests = url => api.mock.calls.map(([request]) => request).filter(request => request.url === url)
const readFile = file => new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(file) })
async function fillHome(wrapper, urls = sourceDocument.url) {
  await wrapper.get('#web-source-urls').setValue(urls)
  await wrapper.get('#simulation-goal').setValue('探索來源文章的影響')
}
async function chooseFile(wrapper, file = new File(['本機來源'], 'notes.md', { type: 'text/markdown' })) {
  Object.defineProperty(wrapper.get('#source-files').element, 'files', { value: [file], configurable: true })
  await wrapper.get('#source-files').trigger('change')
  return file
}

describe('Seamless bounded web input collection', () => {
  it('never scrapes while entering URLs and has no separate review or add operation', async () => {
    const { wrapper } = await render()
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(requests('/api/sources/plan')).toHaveLength(0)
    expect(requests('/api/sources/fetch')).toHaveLength(0)
    expect(wrapper.find('.sources-toggle').exists()).toBe(false)
    expect(wrapper.find('.sources-add').exists()).toBe(false)
    expect(wrapper.find('.source-plan').exists()).toBe(false)
  })
  it('allows local-only input without contacting Firecrawl', async () => {
    const { collection } = await render()
    api.mockClear()
    expect(await collection.prepare()).toBe(true)
    expect(collection.getFiles()).toEqual([])
    expect(api).not.toHaveBeenCalled()
  })
  it('normalizes and deduplicates equivalent URLs before planning', async () => {
    const { wrapper, collection } = await render()
    await wrapper.get('#web-source-urls').setValue('  HTTPS://EXAMPLE.COM:443/article#first\nhttps://example.com/article#second\n\nhttps://example.com/article  ')
    expect(await collection.prepare()).toBe(true)
    expect(requests('/api/sources/plan')[0].data).toEqual({ urls: [sourceDocument.url] })
    expect(requests('/api/sources/fetch')).toHaveLength(1)
    expect(collection.getFiles()).toHaveLength(1)
  })
  it('turns fetched text into analysis files with provenance and safe read-only previews', async () => {
    const { wrapper, collection } = await render()
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(true)
    await flushPromises()
    expect(requests('/api/sources/fetch')[0].data).toEqual({ plan_id: 'approved_plan' })
    const [file] = collection.getFiles()
    expect(file.name).toBe(sourceDocument.filename)
    expect(file.type).toBe('text/markdown')
    expect(await readFile(file)).toBe(sourceDocument.markdown)
    expect(wrapper.get('pre').text()).toContain('<script>alert(1)</script>')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.findAll('input[type=checkbox]')).toHaveLength(0)
    expect(wrapper.emitted('add')).toBeUndefined()
  })
  it('reuses prepared pages, excludes removed URLs and restores them without another fetch', async () => {
    const { wrapper, collection } = await render()
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(true)
    expect(await collection.prepare()).toBe(true)
    await wrapper.get('#web-source-urls').setValue('')
    expect(collection.documents).toHaveLength(0)
    expect(collection.getFiles()).toEqual([])
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(true)
    expect(collection.getFiles()).toHaveLength(1)
    expect(requests('/api/sources/plan')).toHaveLength(1)
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
  it('accepts cached text while the fetch service is offline', async () => {
    state.status.online = false
    state.newPages = 0
    state.result.documents[0].cached = true
    state.result.attempted = 0
    const { wrapper, collection } = await render()
    await collection.refreshStatus()
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(true)
    expect(collection.documents[0].cached).toBe(true)
    expect(collection.errorCode).toBeFalsy()
  })
  it('keeps partial successes and retries only missing pages after an explicit retry', async () => {
    state.result.errors = [{ url: secondDocument.url, code: 'timeout', error: 'timeout' }]
    const { wrapper, collection } = await render()
    await wrapper.get('#web-source-urls').setValue(`${sourceDocument.url}\n${secondDocument.url}`)
    expect(await collection.prepare()).toBe(false)
    expect(collection.getFiles().map(file => file.name)).toEqual([sourceDocument.filename])
    expect(collection.pendingUrls).toEqual([secondDocument.url])
    expect(requests('/api/sources/fetch')).toHaveLength(1)
    state.result = { ...state.result, documents: [secondDocument], errors: [] }
    expect(await collection.prepare()).toBe(true)
    expect(requests('/api/sources/plan').at(-1).data).toEqual({ urls: [secondDocument.url] })
    expect(collection.getFiles().map(file => file.name)).toEqual([sourceDocument.filename, secondDocument.filename])
  })
  it('shows the server budget limit without sending a scrape', async () => {
    const { wrapper, collection } = await render()
    const original = api.getMockImplementation()
    api.mockImplementation(request => request.url === '/api/sources/plan' ? Promise.reject({ response: { data: { code: 'daily_limit' } } }) : original(request))
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(false)
    expect(collection.errorCode).toBe('daily_limit')
    expect(requests('/api/sources/fetch')).toHaveLength(0)
    expect(collection.getFiles()).toEqual([])
  })
  it.each(['daily_limit', 'disabled', 'configuration', 'origin', 'invalid_request', 'plan_expired'])(
    'unlocks the URL draft after a definite %s rejection and plans edited input afresh', async code => {
      const { wrapper, collection } = await render()
      const original = api.getMockImplementation()
      let rejectFirstFetch = true
      api.mockImplementation(request => {
        if (request.url === '/api/sources/fetch' && rejectFirstFetch) {
          rejectFirstFetch = false
          return Promise.reject({ response: { status: 400, data: { code } } })
        }
        return original(request)
      })
      await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
      expect(await collection.prepare()).toBe(false)
      await flushPromises()
      expect(collection.errorCode).toBe(code)
      expect(collection.uncertain).toBe(false)
      expect(collection.busy).toBe(false)
      expect(wrapper.get('#web-source-urls').attributes('disabled')).toBeUndefined()
      expect(collection.getFiles()).toEqual([])
      state.result = { ...state.result, documents: [secondDocument] }
      await wrapper.get('#web-source-urls').setValue(secondDocument.url)
      expect(await collection.prepare()).toBe(true)
      expect(requests('/api/sources/plan')).toHaveLength(2)
      expect(requests('/api/sources/plan').at(-1).data).toEqual({ urls: [secondDocument.url] })
      expect(collection.getFiles().map(file => file.name)).toEqual([secondDocument.filename])
    }
  )
  it('removes a successful page from a partial draft and restores it without another fetch', async () => {
    state.result.errors = [{ url: secondDocument.url, code: 'timeout', error: 'timeout' }]
    const { wrapper, collection } = await render()
    await wrapper.get('#web-source-urls').setValue(`${sourceDocument.url}\n${secondDocument.url}`)
    expect(await collection.prepare()).toBe(false)
    expect(collection.getFiles().map(file => file.name)).toEqual([sourceDocument.filename])
    await wrapper.get('#web-source-urls').setValue(secondDocument.url)
    expect(collection.getFiles()).toEqual([])
    expect(collection.pendingUrls).toEqual([secondDocument.url])
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(true)
    expect(collection.getFiles().map(file => file.name)).toEqual([sourceDocument.filename])
    expect(collection.pendingUrls).toEqual([])
    expect(requests('/api/sources/plan')).toHaveLength(1)
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
  it.each([
    ['a transport timeout', { code: 'ECONNABORTED' }],
    ['a busy server', { response: { status: 409, data: { code: 'busy' } } }]
  ])('checks the same plan after %s without reserving another batch', async (_label, failure) => {
    const { wrapper, collection } = await render()
    const original = api.getMockImplementation()
    let first = true
    api.mockImplementation(request => {
      if (request.url === '/api/sources/fetch' && first) { first = false; return Promise.reject(failure) }
      return original(request)
    })
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(false)
    expect(collection.uncertain).toBe(true)
    expect(requests('/api/sources/fetch')).toHaveLength(1)
    expect(await collection.prepare()).toBe(true)
    expect(requests('/api/sources/plan')).toHaveLength(1)
    expect(requests('/api/sources/fetch').map(request => request.data.plan_id)).toEqual(['approved_plan', 'approved_plan'])
    expect(collection.uncertain).toBe(false)
  })
  it.each([
    ['missing document list', { errors: [], attempted: 1, budget }],
    ['an empty document', { documents: [{ ...sourceDocument, markdown: '   ' }], errors: [], budget }],
    ['a document without a filename', { documents: [{ ...sourceDocument, filename: undefined }], errors: [], budget }]
  ])('does not mark %s as ready for analysis', async (_label, malformed) => {
    state.result = malformed
    const { wrapper, collection } = await render()
    await wrapper.get('#web-source-urls').setValue(sourceDocument.url)
    expect(await collection.prepare()).toBe(false)
    expect(collection.getFiles()).toEqual([])
    expect(collection.errorCode).toBeTruthy()
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
})

describe('One-action Home handoff', () => {
  it('starts with URLs and a goal and automatically passes web files to analysis', async () => {
    const { wrapper, router } = await render(Home)
    await fillHome(wrapper)
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeUndefined()
    expect(getPendingUpload().isPending).toBe(false)
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/process/new'))
    expect(getPendingUpload().files).toHaveLength(1)
    expect(await readFile(getPendingUpload().files[0])).toBe(sourceDocument.markdown)
    expect(getPendingUpload().simulationRequirement).toBe('探索來源文章的影響')
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
  it('deduplicates repeated start clicks while collection is running', async () => {
    const { wrapper, router } = await render(Home)
    await fillHome(wrapper)
    let finish
    const original = api.getMockImplementation()
    api.mockImplementation(request => request.url === '/api/sources/fetch' ? new Promise(resolve => { finish = resolve }) : original(request))
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeDefined()
    await wrapper.get('.start-engine-btn').trigger('click')
    expect(requests('/api/sources/plan')).toHaveLength(1)
    expect(requests('/api/sources/fetch')).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('Home')
    expect(getPendingUpload().isPending).toBe(false)
    finish(success(state.result))
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/process/new'))
  })
  it('keeps partial results and can continue with them plus local files without another fetch', async () => {
    state.result.errors = [{ url: secondDocument.url, code: 'timeout', error: 'timeout' }]
    const { wrapper, router } = await render(Home)
    const file = await chooseFile(wrapper)
    await fillHome(wrapper, `${sourceDocument.url}\n${secondDocument.url}`)
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(getPendingUpload().isPending).toBe(false)
    expect(wrapper.get('#simulation-goal').element.value).toBe('探索來源文章的影響')
    expect(wrapper.get('pre').text()).toContain('Useful article.')
    expect(wrapper.get('.continue-sources-btn').attributes('disabled')).toBeUndefined()
    await wrapper.get('.continue-sources-btn').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/process/new'))
    expect(getPendingUpload().files.map(item => item.name)).toEqual([file.name, sourceDocument.filename])
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
  it('analyses local files even if the Firecrawl status check fails', async () => {
    const original = api.getMockImplementation()
    api.mockImplementation(request => request.url.startsWith('/api/sources/') ? Promise.reject(new Error('Offline')) : original(request))
    const { wrapper, router } = await render(Home)
    const file = await chooseFile(wrapper)
    await wrapper.get('#simulation-goal').setValue('分析文件')
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/process/new'))
    expect(getPendingUpload().files).toEqual([file])
    expect(requests('/api/sources/plan')).toHaveLength(0)
    expect(requests('/api/sources/fetch')).toHaveLength(0)
  })
  it('keeps prepared pages when combined files exceed 49 MiB and resumes without fetching again', async () => {
    const { wrapper, router } = await render(Home)
    const largeFile = new File(['Size-only fixture; no large allocation.'], 'large-notes.md', { type: 'text/markdown' })
    Object.defineProperty(largeFile, 'size', { value: 49 * 1024 * 1024 - 1 })
    await chooseFile(wrapper, largeFile)
    expect(wrapper.findAll('.upload-zone .file-item')).toHaveLength(1)
    await fillHome(wrapper)
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(getPendingUpload().isPending).toBe(false)
    expect(getPendingUpload().files).toEqual([])
    expect(wrapper.get('.form-error').text()).toBe(zhTW.quality.largeFiles)
    expect(wrapper.get('pre').text()).toContain('Useful article.')
    expect(requests('/api/sources/fetch')).toHaveLength(1)
    await wrapper.get('.upload-zone .remove-btn').trigger('click')
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/process/new'))
    expect(getPendingUpload().files.map(file => file.name)).toEqual([sourceDocument.filename])
    expect(requests('/api/sources/plan')).toHaveLength(1)
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
  it('preserves the draft and prepared pages when settings opens during collection', async () => {
    const { wrapper, router } = await render(App)
    await fillHome(wrapper)
    let finish
    const original = api.getMockImplementation()
    api.mockImplementation(request => request.url === '/api/sources/fetch' ? new Promise(resolve => { finish = resolve }) : original(request))
    await wrapper.get('.start-engine-btn').trigger('click')
    await flushPromises()
    await router.push('/settings?from=/')
    await flushPromises()
    finish(success(state.result))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Settings')
    expect(getPendingUpload().isPending).toBe(false)
    await wrapper.get('.settings-back').trigger('click')
    await flushPromises()
    expect(wrapper.get('#web-source-urls').element.value).toBe(sourceDocument.url)
    expect(wrapper.get('#simulation-goal').element.value).toBe('探索來源文章的影響')
    expect(wrapper.get('pre').text()).toContain('Useful article.')
    expect(wrapper.get('.start-engine-btn').attributes('disabled')).toBeUndefined()
    expect(requests('/api/sources/fetch')).toHaveLength(1)
  })
  it('shows persistent limits and the reset time in settings without scraping', async () => {
    const { wrapper } = await render(SourceUsageCard)
    expect(wrapper.text()).toContain('1 / 10 次')
    expect(wrapper.text()).toContain('3 頁')
    expect(wrapper.text()).toContain('24 小時')
    expect(wrapper.text()).toContain('Australia/Sydney')
    expect(requests('/api/sources/fetch')).toHaveLength(0)
  })
})
