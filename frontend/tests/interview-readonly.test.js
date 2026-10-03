import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import zhTW from '../../locales/zh-TW.json'
import Step5 from '../src/components/Step5Interaction.vue'

const api = vi.hoisted(() => ({ status: vi.fn(), history: vi.fn(), interview: vi.fn() }))
vi.mock('../src/api/simulation', () => ({
  getEnvStatus: api.status, getInterviewHistory: api.history, interviewAgents: api.interview,
  getSimulationProfilesRealtime: vi.fn(async () => ({ success: true, data: { profiles: [{ agent_id: 0, username: '合成角色' }] } }))
}))
vi.mock('../src/api/report', () => ({ getReport: vi.fn(), getAgentLog: vi.fn(), chatWithReport: vi.fn() }))
let wrapper
beforeEach(() => {
  api.status.mockReset().mockResolvedValue({ success: true, data: { env_alive: false } })
  api.history.mockReset().mockResolvedValue({ success: true, data: { history: [{ agent_id: 0, platform: 'reddit', prompt: '已保存問題', response: '<script>fixture()</script>已保存回答', timestamp: '2026-01-01' }] } })
  api.interview.mockReset()
})
afterEach(() => wrapper?.unmount())
async function render() {
  wrapper = mount(Step5, { props: { simulationId: 'sim_saved' }, global: { plugins: [createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW } })] } })
  await flushPromises()
  await wrapper.get('.agent-pill').trigger('click')
  await wrapper.get('.dropdown-item').trigger('click')
}

it('shows saved history and disables new interviews and surveys after the producer ends', async () => {
  await render()
  expect(wrapper.find('.interview-status').text()).toContain('已結束')
  expect(wrapper.find('.interview-history').text()).toContain('已保存回答')
  expect(wrapper.find('.interview-history script').exists()).toBe(false)
  expect(wrapper.get('.chat-input').element.disabled).toBe(true)
  expect(wrapper.get('.send-btn').element.disabled).toBe(true)
  await wrapper.get('.survey-pill').trigger('click')
  expect(wrapper.get('.survey-submit-btn').element.disabled).toBe(true)
  expect(api.interview).not.toHaveBeenCalled()
  expect(api.history).toHaveBeenCalledWith({ simulation_id: 'sim_saved', limit: 100 })
})

it('rechecks immediately before sending and keeps the draft when the producer has ended', async () => {
  api.status.mockResolvedValueOnce({ success: true, data: { env_alive: true } })
  await render()
  await wrapper.get('.chat-input').setValue('尚未送出的問題')
  await wrapper.get('.send-btn').trigger('click')
  await flushPromises()
  expect(api.status).toHaveBeenCalledTimes(2)
  expect(api.interview).not.toHaveBeenCalled()
  expect(wrapper.get('.chat-input').element.value).toBe('尚未送出的問題')
})

it('fails closed when availability cannot be checked while preserving readable history', async () => {
  api.status.mockRejectedValue(new Error('synthetic unavailable'))
  await render()
  expect(wrapper.get('.chat-input').element.disabled).toBe(true)
  expect(wrapper.find('.interview-history').text()).toContain('已保存回答')
  expect(wrapper.find('.interview-status').text()).toContain('無法核對')
  expect(api.interview).not.toHaveBeenCalled()
})

it('permits an explicit interview only while the producer is verified alive', async () => {
  api.status.mockResolvedValue({ success: true, data: { env_alive: true } })
  api.interview.mockResolvedValue({ success: true, data: { result: { results: { reddit_0: { response: '合成回答' } } } } })
  await render()
  await wrapper.get('.chat-input').setValue('明確提出的問題')
  await wrapper.get('.send-btn').trigger('click')
  await flushPromises()
  expect(api.interview).toHaveBeenCalledTimes(1)
  expect(api.status).toHaveBeenCalledTimes(2)
})

it('rechecks before a survey and retains the question if the process has ended', async () => {
  api.status.mockResolvedValueOnce({ success: true, data: { env_alive: true } })
  await render()
  await wrapper.get('.survey-pill').trigger('click')
  await wrapper.get('.agent-checkbox input').setValue(true)
  await wrapper.get('.survey-input').setValue('尚未送出的問卷')
  await wrapper.get('.survey-submit-btn').trigger('click')
  await flushPromises()
  expect(api.status).toHaveBeenCalledTimes(2)
  expect(api.interview).not.toHaveBeenCalled()
  expect(wrapper.get('.survey-input').element.value).toBe('尚未送出的問卷')
  expect(wrapper.get('.survey-submit-btn').element.disabled).toBe(true)
})

it('ignores an old simulation availability response after switching simulation', async () => {
  let finish
  api.status.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  await render()
  await wrapper.setProps({ simulationId: 'sim_other' })
  await flushPromises()
  finish({ success: true, data: { env_alive: true } })
  await flushPromises()
  await wrapper.get('.agent-pill').trigger('click')
  await wrapper.get('.dropdown-item').trigger('click')
  expect(wrapper.get('.chat-input').element.disabled).toBe(true)
  expect(api.interview).not.toHaveBeenCalled()
})
