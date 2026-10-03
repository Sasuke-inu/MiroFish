import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import StageConnections from '../src/components/StageConnections.vue'

let wrapper
afterEach(()=>{wrapper?.unmount();vi.unstubAllGlobals()})
const config={profiles:[],assignments:{graph:'default',prepare:'default',simulation:'default',report:'default'},csrf_token:'fixture-csrf'}
const response=data=>({ok:true,json:async()=>({success:true,data})})
async function render(fetch){vi.stubGlobal('fetch',fetch);wrapper=mount(StageConnections,{global:{plugins:[createI18n({legacy:false,locale:'en',messages:{en:{}}})]}});await flushPromises();return wrapper}
it('reads only configuration on mount and preserves unsaved assignments',async()=>{
 const fetch=vi.fn(async()=>response(config));const page=await render(fetch)
 expect(fetch).toHaveBeenCalledTimes(1)
 expect(fetch.mock.calls[0][1].method).toBe('GET')
 await page.get('#connection-name').setValue('Report model')
 expect(page.text()).toContain('Unsaved changes')
 expect(fetch).toHaveBeenCalledTimes(1)
})
it('copies the server default explicitly with csrf and no browser credentials',async()=>{
 const fetch=vi.fn(async()=>response(config));const page=await render(fetch)
 await page.get('#connection-name').setValue('Research')
 await page.get('form.connection-copy').trigger('submit');await flushPromises()
 const request=fetch.mock.calls.at(-1)[1]
 expect(request.method).toBe('POST')
 expect(request.headers['X-MiroFish-CSRF']).toBe('fixture-csrf')
 expect(JSON.parse(request.body)).toEqual({name:'Research',from_default:true})
 expect(request.body).not.toContain('api_key')
})
it('shows read failures without inventing connection capability',async()=>{
 const page=await render(vi.fn(async()=>({ok:false,json:async()=>({success:false,error:'Saved settings unavailable'})})))
 expect(page.get('[role="alert"]').text()).toContain('Saved settings unavailable')
 expect(page.text()).not.toContain('Model list read')
})
