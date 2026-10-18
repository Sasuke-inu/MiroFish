import {afterEach,beforeEach,describe,expect,it} from 'vitest'
import {flushPromises,mount} from '@vue/test-utils'
import {createI18n} from 'vue-i18n'
import zhTW from '../../locales/zh-TW.json'
import EvidenceInspector from '../src/components/EvidenceInspector.vue'
import * as api from '../src/api/workbench'

let calls, originalAdapter

const versionsPage = items => ({items,total:items.length,has_more:false})
const versionRow = id => ({version_id:id,created_at:`2026-01-0${id==='newer'?2:1}`,character_count:10,status:'saved'})

beforeEach(() => {
  calls = []
  api.resetWorkbenchSession()
  originalAdapter = api.workbenchClient.defaults.adapter
  api.workbenchClient.defaults.adapter = async config => {
    calls.push({method:config.method,url:config.url})
    const response = data => ({config,status:200,statusText:'OK',headers:{},data:{success:true,data}})
    if (config.url === '/api/workbench/session') return response({csrf_token:'fixture'})
    if (config.url === '/api/workbench/sources/src_latest') {
      // 歷史清單維持插入順序：newer 在清單最前，但最新「觀察」是 older（A→B→A 的復原情境）。
      return response({source:{source_id:'src_latest',title:'合成來源',source_type:'document',identity:'x'},
                       versions:versionsPage([versionRow('newer'),versionRow('older')]),
                       latest_version_id:'older'})
    }
    const match = /^\/api\/workbench\/versions\/(.+)$/.exec(config.url)
    if (match) return response({version_id:match[1],content:'保存文字',content_available:true,spans:versionsPage([])})
    throw new Error(`Unexpected request: ${config.method} ${config.url}`)
  }
})

afterEach(() => {
  api.workbenchClient.defaults.adapter = originalAdapter
  document.body.innerHTML = ''
})

async function render() {
  const wrapper = mount(EvidenceInspector, {
    props:{sourceId:'src_latest',projectId:'p'},
    attachTo:document.body,
    global:{plugins:[createI18n({legacy:false,locale:'zh-TW',messages:{'zh-TW':zhTW}})]}
  })
  await flushPromises(); await flushPromises()
  return wrapper
}

describe('R08 follow-up: the inspector opens the latest observed version', () => {
  it('prefers latest_version_id over the newest history row', async () => {
    const wrapper = await render()
    expect(calls.map(call => call.url)).toContain('/api/workbench/versions/older')
    expect(calls.map(call => call.url)).not.toContain('/api/workbench/versions/newer')
    expect(wrapper.find('select').element.value).toBe('older')
    wrapper.unmount()
  })

  it('still prefers an explicitly requested version', async () => {
    const wrapper = mount(EvidenceInspector, {
      props:{sourceId:'src_latest',projectId:'p',initialVersionId:'newer'},
      attachTo:document.body,
      global:{plugins:[createI18n({legacy:false,locale:'zh-TW',messages:{'zh-TW':zhTW}})]}
    })
    await flushPromises(); await flushPromises()
    expect(calls.map(call => call.url)).toContain('/api/workbench/versions/newer')
    expect(calls.map(call => call.url)).not.toContain('/api/workbench/versions/older')
    wrapper.unmount()
  })
})
