import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import ProviderSettings from '../src/components/ProviderSettings.vue'
import SettingsView from '../src/views/SettingsView.vue'
import zhTW from '../../locales/zh-TW.json'
import { createFixtureAdapter } from './fixtures/api'

const { transport } = vi.hoisted(() => ({ transport: vi.fn() }))
vi.mock('axios', async importOriginal => {
  const original = await importOriginal()
  return { ...original, default: Object.assign({}, original.default, {
    create: config => {
      const client = original.default.create(config)
      client.defaults.adapter = transport
      return client
    }
  }) }
})

const settingsUrl = '/api/settings/providers'
const wrappers = []
let overrides
let refreshStatus
const body = request => typeof request.data === 'string' ? JSON.parse(request.data) : request.data
const calls = (url, method) => transport.mock.calls.map(([request]) => request).filter(request => request.url === url && (!method || request.method === method))
const answer = data => request => ({ data: { success: true, data }, status: 200, statusText: 'OK', headers: {}, config: request })
const failure = message => request => { throw Object.assign(new Error('Private transport failure'), { config: request, response: { data: { success: false, error: message }, status: 503 } }) }
const defer = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }

beforeEach(() => {
  localStorage.clear()
  overrides = new Map()
  refreshStatus = vi.fn()
  const fixture = createFixtureAdapter()
  transport.mockReset().mockImplementation(async request => {
    const override = overrides.get(`${request.method} ${request.url}`)
    return override ? override(request) : fixture(request)
  })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  localStorage.clear()
})

async function render({ page = false } = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', name: 'Home', component: { template: '<h1>工作室</h1>' } },
    { path: '/settings', name: 'Settings', component: SettingsView }
  ] })
  await router.push(page ? '/settings' : '/')
  const wrapper = mount(page ? { template: '<RouterView />' } : ProviderSettings, {
    attachTo: document.body,
    global: { plugins: [router, createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW } })],
      provide: { refreshSystemStatus: refreshStatus }, stubs: { SourceUsageCard: true, LanguageSwitcher: true } }
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
function button(wrapper, text) {
  const found = wrapper.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error(`Missing button: ${text}`)
  return found
}
const save = async wrapper => { await wrapper.get('form').trigger('submit'); await flushPromises() }
const testConnection = async wrapper => { await button(wrapper, zhTW.providers.loadModels).trigger('click'); await flushPromises() }

describe('Provider settings privacy and workflow', () => {
  it('keeps saved keys blank and never copies entered credentials into browser storage or logs', async () => {
    const store = vi.spyOn(Storage.prototype, 'setItem')
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { wrapper } = await render()
    expect(wrapper.get('#provider-key').element.value).toBe('')
    expect(wrapper.get('#provider-key').attributes('type')).toBe('password')
    expect(wrapper.get('.key-stored').text()).toBe(zhTW.providers.keyStored)
    await wrapper.get('#provider-key').setValue('fixture-secret-never-persist-in-browser')
    await button(wrapper, zhTW.providers.show).trigger('click')
    expect(wrapper.get('#provider-key').attributes('type')).toBe('text')
    await save(wrapper)
    expect(wrapper.get('#provider-key').element.value).toBe('')
    expect(wrapper.get('#provider-key').attributes('type')).toBe('password')
    expect(wrapper.text()).not.toContain('fixture-secret')
    expect(store).not.toHaveBeenCalled()
    expect(log).not.toHaveBeenCalled()
  })

  it('requires a new key for another endpoint and never forwards the saved key', async () => {
    const { wrapper } = await render()
    await wrapper.get('#provider-endpoint').setValue('https://another.example/v1')
    expect(wrapper.find('.key-stored').exists()).toBe(false)
    expect(wrapper.text()).toContain(zhTW.providers.changedEndpoint)
    expect(button(wrapper, zhTW.providers.loadModels).attributes('disabled')).toBeDefined()
    expect(button(wrapper, zhTW.providers.save).attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(calls(settingsUrl, 'put')).toHaveLength(0)
    await wrapper.get('#provider-key').setValue('fixture-key-for-new-endpoint')
    await testConnection(wrapper)
    expect(body(calls(`${settingsUrl}/test`, 'post')[0])).toMatchObject({ base_url: 'https://another.example/v1', api_key: 'fixture-key-for-new-endpoint' })
  })

  it('clears an entered key when its endpoint changes before testing', async () => {
    const { wrapper } = await render()
    await wrapper.get('#provider-key').setValue('fixture-key-meant-for-original-host')
    await wrapper.get('#provider-endpoint').setValue('https://different.example/v1')
    expect(wrapper.get('#provider-key').element.value).toBe('')
    expect(button(wrapper, zhTW.providers.loadModels).attributes('disabled')).toBeDefined()
  })

  it('discards edits to provider, endpoint and model without a save request', async () => {
    const { wrapper } = await render()
    await wrapper.get('#provider-choice').setValue('openrouter')
    await wrapper.get('#provider-model').setValue('fixture-new-model')
    await wrapper.get('#provider-key').setValue('fixture-new-key')
    await button(wrapper, zhTW.providers.show).trigger('click')
    await button(wrapper, zhTW.providers.discard).trigger('click')
    expect(wrapper.get('#provider-choice').element.value).toBe('ninerouter')
    expect(wrapper.get('#provider-endpoint').element.value).toBe('http://host.docker.internal:20128/v1')
    expect(wrapper.get('#provider-model').element.value).toBe('fixture-model')
    expect(wrapper.get('#provider-key').element.value).toBe('')
    expect(wrapper.get('#provider-key').attributes('type')).toBe('password')
    expect(button(wrapper, zhTW.providers.save).attributes('disabled')).toBeDefined()
    expect(calls(settingsUrl, 'put')).toHaveLength(0)
  })

  it('tests only the draft through the test endpoint and does not save or generate content', async () => {
    const { wrapper } = await render()
    const before = transport.mock.calls.length
    await testConnection(wrapper)
    const requests = transport.mock.calls.slice(before).map(([request]) => ({ method: request.method, url: request.url }))
    expect(requests).toEqual([{ method: 'post', url: `${settingsUrl}/test` }])
    const request = calls(`${settingsUrl}/test`, 'post')[0]
    expect(request.headers.get('X-MiroFish-CSRF')).toBe('fixture-csrf-token')
    expect(body(request)).not.toHaveProperty('api_key')
    expect(wrapper.get('.connection-result').text()).toContain(zhTW.providers.testScope)
    expect(wrapper.findAll('#provider-models option').map(option => option.attributes('value'))).toEqual(['fixture-model', 'fixture-chat-small'])
  })

  it('preserves the model list during selection, but invalidates it after changing credentials', async () => {
    const { wrapper } = await render()
    await testConnection(wrapper)
    expect(wrapper.findAll('#provider-models option')).toHaveLength(2)
    await wrapper.get('#provider-model').setValue('manually-entered-model')
    expect(wrapper.get('.connection-result').text()).toContain(zhTW.providers.modelMissing)
    expect(wrapper.findAll('#provider-models option')).toHaveLength(2)
    await wrapper.get('#provider-model').setValue('fixture-chat-small')
    expect(wrapper.get('.connection-result').text()).not.toContain(zhTW.providers.modelMissing)
    await wrapper.get('#provider-key').setValue('fixture-replacement-key')
    expect(wrapper.find('.connection-result').exists()).toBe(false)
    expect(wrapper.findAll('#provider-models option')).toHaveLength(0)
  })

  it('retains an edited draft after a failed save and supports a successful retry', async () => {
    overrides.set(`put ${settingsUrl}`, failure('儲存空間暫時無法使用'))
    const { wrapper } = await render()
    await wrapper.get('#provider-model').setValue('fixture-chat-small')
    await save(wrapper)
    expect(wrapper.get('#provider-model').element.value).toBe('fixture-chat-small')
    expect(wrapper.get('form [role=alert]').text()).toBe('儲存空間暫時無法使用')
    expect(button(wrapper, zhTW.providers.save).attributes('disabled')).toBeUndefined()
    expect(refreshStatus).not.toHaveBeenCalled()
    overrides.delete(`put ${settingsUrl}`)
    await save(wrapper)
    expect(calls(settingsUrl, 'put')).toHaveLength(2)
    expect(wrapper.get('.saved-message').text()).toBe(zhTW.providers.saved)
    expect(button(wrapper, zhTW.providers.save).attributes('disabled')).toBeDefined()
    expect(refreshStatus).toHaveBeenCalledOnce()
  })

  it('replaces transport errors with a safe message instead of exposing a credential-bearing Axios error', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    overrides.set(`post ${settingsUrl}/test`, request => { throw Object.assign(new Error('Network failure fixture-private-api-key'), { config: request }) })
    const { wrapper } = await render()
    await wrapper.get('#provider-key').setValue('fixture-private-api-key')
    await testConnection(wrapper)
    expect(wrapper.get('form [role=alert]').text()).toBe(zhTW.providers.requestFailed)
    expect(wrapper.text()).not.toContain('fixture-private-api-key')
    expect(log).not.toHaveBeenCalled()
  })

  it('loads 9Router accounts only after authorization is saved and then saves the chosen account', async () => {
    const { wrapper } = await render()
    expect(calls(`${settingsUrl}/accounts`)).toHaveLength(0)
    await wrapper.get('#router-balance-key').setValue('fixture-management-authorization')
    expect(button(wrapper, zhTW.providers.loadAccounts).attributes('disabled')).toBeDefined()
    await save(wrapper)
    expect(body(calls(settingsUrl, 'put')[0]).balance_api_key).toBe('fixture-management-authorization')
    expect(wrapper.get('#router-balance-key').element.value).toBe('')
    expect(calls(`${settingsUrl}/accounts`)).toHaveLength(1)
    expect(wrapper.get('#router-account').text()).toContain('測試用 OpenCode 帳戶')
    expect(wrapper.get('#router-account').text()).toContain(zhTW.providers.inactive)
    await wrapper.get('#router-account').setValue('account_fixture')
    await save(wrapper)
    const saved = body(calls(settingsUrl, 'put')[1])
    expect(saved.balance_account_id).toBe('account_fixture')
    expect(saved).not.toHaveProperty('balance_api_key')
    expect(wrapper.get('.balance-value').text()).toContain('12.34')
    expect(wrapper.get('.balance-warning').text()).toBe(zhTW.providers.stale)
    expect(wrapper.get('.quota-row strong').text()).toBe('76%')
  })

  it('disconnects balance authorization without changing the model connection', async () => {
    const { wrapper } = await render()
    await wrapper.get('#router-balance-key').setValue('fixture-management-authorization')
    await save(wrapper)
    await wrapper.get('#router-account').setValue('account_fixture')
    await save(wrapper)
    await button(wrapper, zhTW.providers.disconnectBalance).trigger('click')
    await flushPromises()
    expect(body(calls(settingsUrl, 'put').at(-1))).toEqual({ clear_balance_authorization: true, expected_provider: 'ninerouter', expected_base_url: 'http://host.docker.internal:20128/v1' })
    expect(wrapper.get('#provider-model').element.value).toBe('fixture-model')
    expect(wrapper.get('.key-stored').exists()).toBe(true)
    expect(wrapper.get('#router-account').element.value).toBe('')
    expect(wrapper.find('.balance-value').exists()).toBe(false)
    expect(wrapper.get('.balance-card').text()).toContain(zhTW.providers.authorizationRequired)
  })
})

describe('Provider balance honesty and recovery', () => {
  it('shows a balance error with a retry and never invents zero', async () => {
    overrides.set(`get ${settingsUrl}/balance`, failure('餘額服務暫時無法使用'))
    const { wrapper } = await render()
    expect(wrapper.get('.balance-card [role=alert]').text()).toBe('餘額服務暫時無法使用')
    expect(wrapper.find('.balance-value').exists()).toBe(false)
    overrides.set(`get ${settingsUrl}/balance`, answer({ supported: true, kind: 'wallet', status: 'available', remaining: 0, currency: 'USD' }))
    await wrapper.get('.balance-heading button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.balance-value').text()).toMatch(/USD\s*0(?:\.00)?/)
  })

  it('distinguishes an uncapped OpenRouter key from an unlimited wallet', async () => {
    overrides.set(`get ${settingsUrl}/balance`, answer({ supported: true, kind: 'key_allowance', status: 'available', remaining: null, currency: 'USD' }))
    const { wrapper } = await render()
    expect(wrapper.get('.balance-value').text()).toBe('—')
    expect(wrapper.text()).toContain(zhTW.providers.noLimit)
    expect(wrapper.get('.balance-label').text()).toBe(zhTW.providers.allowance)
    expect(wrapper.find('progress').exists()).toBe(false)
  })

  it('shows quota percentages separately from unavailable money balances', async () => {
    overrides.set(`get ${settingsUrl}/balance`, answer({ supported: true, kind: 'subscription_quota', status: 'available', quotas: [{ id: 'rolling', remaining_percent: 64 }, { id: 'weekly', remaining_percent: null }] }))
    const { wrapper } = await render()
    expect(wrapper.find('.balance-value').exists()).toBe(false)
    expect(wrapper.findAll('.quota-row strong').map(item => item.text())).toEqual(['64%', '—'])
    expect(wrapper.findAll('progress')).toHaveLength(1)
  })

  it('can recover when loading settings initially fails', async () => {
    overrides.set(`get ${settingsUrl}`, failure('本機設定服務暫時無法使用'))
    const { wrapper } = await render()
    expect(wrapper.get('[role=alert]').text()).toBe('本機設定服務暫時無法使用')
    expect(wrapper.find('form').exists()).toBe(false)
    overrides.delete(`get ${settingsUrl}`)
    await button(wrapper, zhTW.providers.retry).trigger('click')
    await flushPromises()
    expect(wrapper.get('#provider-model').element.value).toBe('fixture-model')
    expect(calls(settingsUrl, 'get')).toHaveLength(2)
  })

  it('makes the form usable while the balance service is still responding', async () => {
    const pending = defer()
    overrides.set(`get ${settingsUrl}/balance`, request => pending.promise.then(data => answer(data)(request)))
    const { wrapper } = await render()
    expect(wrapper.get('#provider-model').element.value).toBe('fixture-model')
    expect(wrapper.get('.balance-card [role=status]').text()).toBe(zhTW.providers.loading)
    await wrapper.get('#provider-model').setValue('fixture-chat-small')
    expect(button(wrapper, zhTW.providers.save).attributes('disabled')).toBeUndefined()
    pending.resolve({ supported: false, status: 'authorization_required', quotas: [] })
    await flushPromises()
  })

  it('does not display a late balance from the previous saved provider', async () => {
    const pending = defer()
    let balanceCalls = 0
    overrides.set(`get ${settingsUrl}/balance`, request => {
      balanceCalls += 1
      return balanceCalls === 1 ? pending.promise.then(data => answer(data)(request)) : answer({ supported: false, status: 'unsupported', quotas: [] })(request)
    })
    const { wrapper } = await render()
    await wrapper.get('#provider-choice').setValue('openai')
    await wrapper.get('#provider-model').setValue('fixture-openai-model')
    await wrapper.get('#provider-key').setValue('fixture-openai-key')
    await save(wrapper)
    pending.resolve({ supported: true, kind: 'wallet', status: 'available', remaining: 87.65, currency: 'USD' })
    await flushPromises()
    expect(wrapper.find('.balance-value').exists()).toBe(false)
    expect(wrapper.get('.balance-card').text()).toContain(zhTW.providers.balanceUnsupported)
  })

  it('blocks overlapping saves while the first request is pending', async () => {
    const pending = defer()
    overrides.set(`put ${settingsUrl}`, request => pending.promise.then(data => answer(data)(request)))
    const { wrapper } = await render()
    await wrapper.get('#provider-model').setValue('fixture-chat-small')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    expect(calls(settingsUrl, 'put')).toHaveLength(1)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    pending.resolve({ config: { provider: 'ninerouter', base_url: 'http://host.docker.internal:20128/v1', model: 'fixture-chat-small', has_api_key: true, has_balance_api_key: false, balance_account_id: '' } })
    await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
  })
})

describe('Unsaved settings navigation', () => {
  it('keeps drafts while browsing settings sections and confirms before leaving the page', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { wrapper, router } = await render({ page: true })
    await wrapper.get('#provider-model').setValue('fixture-unsaved-model')
    const appearance = wrapper.findAll('.settings-index > button').find(item => item.text().includes(zhTW.providers.appearanceNav))
    await appearance.trigger('click')
    expect(wrapper.get('#provider-model').element.value).toBe('fixture-unsaved-model')
    expect(confirm).not.toHaveBeenCalled()
    await router.push('/')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Settings')
    expect(confirm).toHaveBeenCalledWith(zhTW.providers.leaveConfirm)
    confirm.mockReturnValue(true)
    await router.push('/')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Home')
    expect(wrapper.find('#provider-key').exists()).toBe(false)
  })

  it('warns on browser close only while dirty and removes the listener after leaving', async () => {
    const { wrapper } = await render()
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)
    await wrapper.get('#provider-model').setValue('fixture-unsaved-model')
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
    await button(wrapper, zhTW.providers.discard).trigger('click')
    const restored = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(restored)
    expect(restored.defaultPrevented).toBe(false)
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    const closed = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(closed)
    expect(closed.defaultPrevented).toBe(false)
  })
})
