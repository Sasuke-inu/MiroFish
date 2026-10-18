import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import WorkflowExplorer from '../src/components/WorkflowExplorer.vue'
import zhTW from '../../locales/zh-TW.json'
import en from '../../locales/en.json'
import zh from '../../locales/zh.json'

const mounted = []
afterEach(() => mounted.splice(0).forEach(wrapper => wrapper.unmount()))
function render(locale = 'zh-TW') {
  const wrapper = mount(WorkflowExplorer, {
    attachTo: document.body,
    global: { plugins: [createI18n({ legacy: false, locale, messages: { 'zh-TW': zhTW, en, zh } })] }
  })
  mounted.push(wrapper)
  return wrapper
}

describe('WorkflowExplorer', () => {
  it('previews the selected step with its inputs and outputs without emitting workflow actions', async () => {
    const wrapper = render()
    const tabs = wrapper.findAll('[role=tab]')
    expect(tabs).toHaveLength(5)
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[role=tabpanel]').text()).toContain('參考資料與你想了解的問題')
    await tabs[3].trigger('click')
    expect(tabs[3].attributes('aria-selected')).toBe('true')
    expect(tabs[0].attributes('aria-selected')).toBe('false')
    expect(wrapper.get('[role=tabpanel]').text()).toContain('有依據的觀察、趨勢與解釋')
    expect(wrapper.get('[role=tabpanel]').attributes('aria-labelledby')).toBe(tabs[3].attributes('id'))
    expect(wrapper.emitted('navigate')).toBeUndefined()
    expect(wrapper.emitted('start')).toBeUndefined()
    expect(wrapper.text()).toContain('點選不會啟動模擬')
  })

  it('supports arrow keys, Home and End while keeping one tab stop', async () => {
    const wrapper = render()
    const tabs = wrapper.findAll('[role=tab]')
    await tabs[0].trigger('keydown', { key: 'ArrowUp' })
    expect(document.activeElement).toBe(tabs[4].element)
    expect(tabs[4].attributes('tabindex')).toBe('0')
    await tabs[4].trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(tabs[0].element)
    await tabs[0].trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(tabs[4].element)
    await tabs[4].trigger('keydown', { key: 'Home' })
    expect(document.activeElement).toBe(tabs[0].element)
    expect(tabs.filter(tab => tab.attributes('tabindex') === '0')).toHaveLength(1)
  })

  it.each(['zh-TW', 'en', 'zh'])('provides all labels and five step details in %s', async locale => {
    const wrapper = render(locale)
    const messages = { 'zh-TW': zhTW, en, zh }[locale]
    const keys = ['graph', 'setup', 'interaction', 'report', 'followup']
    for (const [index, tab] of wrapper.findAll('[role=tab]').entries()) {
      await tab.trigger('click')
      expect(tab.text()).toContain(messages.studio[`step${index + 1}Title`])
      expect(wrapper.get('[role=tabpanel]').text()).toContain(messages.visuals.workflow.steps[keys[index]].input)
      expect(wrapper.get('[role=tabpanel]').text()).toContain(messages.visuals.workflow.steps[keys[index]].output)
    }
    expect(wrapper.text()).not.toContain('visuals.workflow.')
  })
})
