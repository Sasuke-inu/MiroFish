import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import {flushPromises,mount} from '@vue/test-utils'
import {createI18n} from 'vue-i18n'
import {createMemoryHistory,createRouter,RouterView} from 'vue-router'
import zhTW from '../../locales/zh-TW.json'
import Workbench from '../src/views/WorkbenchView.vue'
import EventReferenceLink from '../src/components/EventReferenceLink.vue'
import EvidenceLinks from '../src/components/EvidenceLinks.vue'
import * as api from '../src/api/workbench'

const page=items=>({items,total:items.length,has_more:false})
const project={project_id:'p',name:'測試研究',simulation_requirement:'測試问题',status:'created',archived:false}
const event=(seq=1)=>({event_id:`e${seq}`,run_id:'run1',attempt_id:'attempt',seq,platform:'twitter',agent_id:'0',round:seq,kind:'POST',content:`saved ${seq}`,observed_at:'2026-01-01'})
const savedEvent=(seq,simulationId='s1',runId='run1')=>({...event(seq),project_id:'p',simulation_id:simulationId,run_id:runId,event_id:`e${seq}`})
let calls,overrides,wrappers,originalAdapter,detail
function response(config,data) {return {config,status:200,statusText:'OK',headers:{},data:{success:true,data}}}
const writes=()=>calls.filter(c=>['post','patch','delete'].includes(c.method))
const requests=path=>calls.filter(c=>c.url===`/api/workbench${path}`)
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r});return {promise,resolve}}
function button(wrapper,label){const found=wrapper.findAll('button').find(b=>b.text()===label);if(!found)throw new Error(`Missing button: ${label}`);return found}
function buttonContaining(wrapper,label){const found=wrapper.findAll('button').find(b=>b.text().includes(label));if(!found)throw new Error(`Missing button containing: ${label}`);return found}
async function tick(){await flushPromises();await flushPromises()}
beforeEach(()=>{
  sessionStorage.clear();calls=[];overrides=new Map();wrappers=[];api.resetWorkbenchSession();originalAdapter=api.workbenchClient.defaults.adapter
  detail={project:{...project},sources:page([]),references:page([]),runs:[{simulation_id:'s1',run_id:'run1',status:'completed',graph_ready:false,manifest:{kind:'synthetic_fixture'}},{simulation_id:'s2',run_id:'run2',status:'completed',graph_ready:false,manifest:{}}],reports:[{report_id:'older',simulation_id:'s1',status:'completed',version:1,markdown_content:'older text'},{report_id:'newer',simulation_id:'s1',status:'completed',version:2,markdown_content:'newer text'}]}
  api.workbenchClient.defaults.adapter=async config=>{
    calls.push(config)
    if(overrides.has(config.url))return response(config,await overrides.get(config.url)(config))
    const path=config.url.replace('/api/workbench','')
    if(path==='/session')return response(config,{csrf_token:'fixture-session-token'})
    if(path==='/projects'&&config.method==='get')return response(config,page([{...project}]))
    if(/^\/projects\/[^/]+$/.test(path)&&config.method==='get')return response(config,{...detail,project:{...detail.project,project_id:path.split('/').at(-1)}})
    if(path.endsWith('/quality'))return response(config,{source_preservation:{numerator:0,denominator:0,value:null,definition:'保存原文 / 所有版本'},citation_location:{numerator:0,denominator:0,value:null,definition:'可定位 / 来源引用'},run_counts:{total:2,completed:2,incomplete:0},assumptions:[],contradictions:[],limitations:[]})
    if(path.endsWith('/sources')&&config.method==='get')return response(config,page([]))
    if(path.endsWith('/references')&&config.method==='get')return response(config,page([]))
    if(path==='/tasks')return response(config,{items:[],runs:[]})
    if(path==='/demos')return response(config,{items:[]})
    if(path==='/demos/product')return response(config,{project_id:'demo'})
    if(/^\/projects\/[^/]+\/events\//.test(path))throw new Error(`Unexpected event fixture request: ${path}`)
    if(/^\/simulations\/[^/]+\/events$/.test(path))return response(config,{items:[event(1)],next_cursor:'cursor1',has_more:false,capability:'exact_event_projection',limitations:[]})
    if(/^\/simulations\/[^/]+\/projection$/.test(path))return response(config,{through_seq:config.params.through_seq,events:[event(config.params.through_seq)],actors:[],relationships:[],capability:'exact_event_projection',limitations:[]})
    if(/^\/api\/simulation\//.test(config.url))return response(config,{runner_status:'completed'})
    throw new Error(`Unexpected fixture request: ${config.method} ${path}`)
  }
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());api.workbenchClient.defaults.adapter=originalAdapter;document.body.innerHTML='';vi.clearAllTimers();vi.useRealTimers();vi.restoreAllMocks()})
async function render(component=Workbench,props={},path='/workbench/p?section=data') {
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/workbench/:projectId?',name:'Workbench',component:Workbench,props:true},{path:'/report/:reportId',name:'Report',component:{template:'<div />'}},{path:'/settings',name:'Settings',component:{template:'<div />'}},{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
 await router.push(path);await router.isReady()
 const wrapper=mount(component===Workbench?RouterView:component,{props,attachTo:document.body,global:{plugins:[router,createI18n({legacy:false,locale:'zh-TW',messages:{'zh-TW':zhTW}})],stubs:{LanguageSwitcher:true}}})
 wrappers.push(wrapper);await tick();return {wrapper,router}
}

describe('R09: opening a saved example never installs again',()=>{
 it('R09 links an installed example straight to its saved research, even beyond the first project page',async()=>{
   overrides.set('/api/workbench/demos',()=>({items:[{id:'story',title:'保存的故事示範',description:'合成內容',kind:'synthetic_fixture',project_id:'saved-story'},{id:'product',title:'產品示範',description:'合成內容',kind:'synthetic_fixture',project_id:null}]}))
   overrides.set('/api/workbench/projects',()=>({items:Array.from({length:12},(_,index)=>({...project,project_id:`other-${index}`})),has_more:true,total:20}))
   const {wrapper}=await render(Workbench,{},'/workbench?view=demos')
   expect(wrapper.find('a[href="/workbench/saved-story"]').exists()).toBe(true)
   expect(wrapper.findAll('button').filter(item=>item.text()==='安裝示範')).toHaveLength(1)
   expect(writes()).toHaveLength(0)
 })
 it('R09 offers an explicit install for an uninstalled example and never guesses from a research marker',async()=>{
   overrides.set('/api/workbench/demos',()=>({items:[{id:'story',title:'保存的故事示範',description:'合成內容',kind:'synthetic_fixture',project_id:null}]}))
   overrides.set('/api/workbench/projects',()=>({items:[{...project,project_id:'demo-row',demo:'story'}],has_more:false,total:1}))
   const {wrapper}=await render(Workbench,{},'/workbench?view=demos')
   expect(wrapper.find('a[href="/workbench/demo-row"]').exists()).toBe(false)
   expect(button(wrapper,'安裝示範').exists()).toBe(true)
   expect(writes()).toHaveLength(0)
 })
})

describe('R10: partial report bodies stay readable',()=>{
 it('R10 shows every saved section body and marks unsaved sections without inventing text',async()=>{
   detail.reports=[{report_id:'partial-sections',simulation_id:'s1',status:'failed',version:1,markdown_content:'',outline:{title:'保存的報告',summary:'',sections:[{title:'第一節',content:'PRESERVED-SECTION-BODY'},{title:'第二節',content:''}]}}]
   const {wrapper}=await render(Workbench,{},'/workbench/p?replay=s1&report=partial-sections&section=results')
   const report=wrapper.get('.saved-report')
   expect(report.text()).toContain('PRESERVED-SECTION-BODY')
   expect(report.text()).toContain('部分報告')
   expect(report.text()).toContain('第一節')
   expect(report.text()).toContain('第二節')
   expect(report.text()).toContain('此節尚未保存內容。')
   expect(wrapper.findAllComponents(EvidenceLinks).map(item=>item.props('subjectId'))).toEqual(['partial-sections','partial-sections:section:1','partial-sections:section:2'])
   expect(writes()).toHaveLength(0)
 })
 it('R10 does not repeat saved section bodies when the full markdown is displayed',async()=>{
   detail.reports=[{report_id:'partial-markdown',simulation_id:'s1',status:'failed',version:2,markdown_content:'FULL-SAVED-MARKDOWN',outline:{title:'保存的報告',summary:'',sections:[{title:'第一節',content:'FIRST-SECTION-BODY'},{title:'第二節',content:''}]}}]
   const {wrapper}=await render(Workbench,{},'/workbench/p?replay=s1&report=partial-markdown&section=results')
   const text=wrapper.get('.saved-report').text()
   expect(text.split('FULL-SAVED-MARKDOWN')).toHaveLength(2)
   expect(text).not.toContain('FIRST-SECTION-BODY')
   expect(text).toContain('此節尚未保存內容。')
   expect(wrapper.findAllComponents(EvidenceLinks).map(item=>item.props('subjectId'))).toEqual(['partial-markdown','partial-markdown:section:1','partial-markdown:section:2'])
   expect(writes()).toHaveLength(0)
 })
})

describe('R11: locating an event keeps the selected report version',()=>{
 it('R11 preserves the replay and the report when building an event-locating link',async()=>{
   const {wrapper}=await render(EventReferenceLink,{projectId:'p',reference:{reference_id:'ref',category:'simulation_event',relation:'insufficient',run_id:'run1',event_id:'e77'}},'/workbench/p?section=results&panel=process&replay=s1&report=older&seq=3')
   const link=wrapper.get('.event-reference-link')
   const params=new URLSearchParams(link.attributes('href').split('?')[1])
   expect(params.get('replay')).toBe('s1')
   expect(params.get('report')).toBe('older')
   expect(params.get('section')).toBe('runs')
   expect(params.get('ref_run')).toBe('run1')
   expect(params.get('ref_event')).toBe('e77')
   expect(calls).toHaveLength(0)
 })
 it('R11 returns to the same saved version after locating a same-simulation event and survives a remount',async()=>{
   detail.references=page([{reference_id:'ref',category:'simulation_event',relation:'insufficient',run_id:'run1',event_id:'e77',note:'保存的事件引用',validation:{location_status:'valid'}}])
   overrides.set('/api/workbench/projects/p/events/e77',()=>({...savedEvent(77),content:'exact saved event'}))
   const {wrapper,router}=await render(Workbench,{},'/workbench/p?section=results&replay=s1&report=older')
   expect(wrapper.get('.saved-report').text()).toContain('older text')
   await button(wrapper,'研究引用與假設').trigger('click');await tick()
   const href=wrapper.get('.event-reference-link').attributes('href')
   await router.push(href);await tick()
   expect(router.currentRoute.value.query.replay).toBe('s1')
   expect(router.currentRoute.value.query.report).toBe('older')
   expect(router.currentRoute.value.query.ref_event).toBeUndefined()
   await buttonContaining(wrapper,'返回這次報告').trigger('click');await tick()
   expect(wrapper.get('.saved-report').text()).toContain('older text')
   expect(wrapper.get('.saved-report').text()).not.toContain('newer text')
   const restored=await render(Workbench,{},router.currentRoute.value.fullPath)
   expect(restored.wrapper.get('.saved-report').text()).toContain('older text')
   expect(restored.router.currentRoute.value.query.report).toBe('older')
   expect(writes()).toHaveLength(0)
 })
 it('R11 keeps an explicit report passed from a standalone report page',async()=>{
   overrides.set('/api/workbench/projects/p/events/e77',()=>({...savedEvent(77),content:'exact saved event'}))
   const {wrapper,router}=await render(Workbench,{},'/workbench/p?section=runs&ref_run=run1&ref_event=e77&report=older')
   expect(router.currentRoute.value.query.replay).toBe('s1')
   expect(router.currentRoute.value.query.report).toBe('older')
   await buttonContaining(wrapper,'返回這次報告').trigger('click');await tick()
   expect(wrapper.get('.saved-report').text()).toContain('older text')
   expect(writes()).toHaveLength(0)
 })
 it('R11 drops a foreign report instead of pinning it to another simulation event',async()=>{
   overrides.set('/api/workbench/projects/p/events/e99',()=>({...savedEvent(99,'s2','run2')}))
   const {wrapper,router}=await render(Workbench,{},'/workbench/p?section=runs&replay=s2&report=older&ref_run=run2&ref_event=e99')
   expect(router.currentRoute.value.query.replay).toBe('s2')
   expect(router.currentRoute.value.query.report).toBeUndefined()
   expect(wrapper.find('.saved-report').exists()).toBe(false)
   expect(writes()).toHaveLength(0)
 })
})
