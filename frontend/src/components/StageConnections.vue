<template>
  <section class="stage-connections" aria-labelledby="stage-heading">
    <div><h2 id="stage-heading">{{ t('title') }}</h2><p>{{ t('intro') }}</p></div>
    <p v-if="error" role="alert" class="connection-error">{{ error }} <button @click="load" :disabled="busy">{{ t('reload') }}</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <form @submit.prevent="copyDefault" class="connection-copy">
      <label for="connection-name">{{ t('name') }}<input id="connection-name" v-model="name" maxlength="100" :disabled="busy" required /></label>
      <button :disabled="busy || !name.trim()">{{ t('copy') }}</button>
    </form>
    <ul class="saved-connections">
      <li v-for="item in profiles" :key="item.id">
        <div><strong>{{ item.name }}</strong><span>{{ item.provider }} · {{ item.model }}</span><small>{{ item.base_url }}</small>
          <small>{{ t(item.capabilities.model_list === 'verified' ? 'catalogueRead' : 'catalogueUnknown') }} · {{ t('noGeneration') }}</small></div>
        <div class="connection-actions"><button :disabled="busy" @click="test(item.id)">{{ t('test') }}</button><button :disabled="busy || Object.values(assignments).includes(item.id)" @click="remove(item.id)">{{ t('remove') }}</button></div>
      </li>
    </ul>
    <form @submit.prevent="saveAssignments" class="stage-form">
      <label v-for="stage in stages" :key="stage" :for="`connection-${stage}`">{{ t(stage) }}
        <select :id="`connection-${stage}`" v-model="assignments[stage]" :disabled="busy">
          <option value="default">{{ t('default') }}</option><option v-for="item in profiles" :key="item.id" :value="item.id">{{ item.name }} · {{ item.model }}</option>
        </select>
      </label>
      <div class="assignment-actions"><span v-if="dirty" role="status">{{ t('unsaved') }}</span><button type="button" :disabled="busy || !dirty" @click="restore">{{ t('restore') }}</button><button :disabled="busy || !dirty">{{ t('save') }}</button></div>
    </form>
    <p class="connection-note">{{ t('embedding') }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
const emit = defineEmits(['dirty'])
const chinese = { title:'分階段模型連線', intro:'先在上方設定預設連線，再以名稱保存。各階段可選擇已保存的連線；進行中的工作維持原設定。', name:'連線名稱', copy:'保存目前預設為新連線', reload:'重新讀取', catalogueRead:'已讀模型清單', catalogueUnknown:'模型清單未驗證', noGeneration:'生成及結構化輸出尚未驗證', test:'讀取模型清單', remove:'移除', graph:'圖譜與資料抽取', prepare:'角色準備', simulation:'模擬', report:'報告', default:'沿用預設', unsaved:'尚未儲存', restore:'還原', save:'儲存階段設定', saved:'已保存；只套用於新工作。', tested:'模型清單已讀取，沒有執行生成。', embedding:'Embedding 維持本機獨立配置；切換聊天模型不會變更維度或重建索引。', failure:'無法更新連線，請稍後再試。' }
const { t } = useI18n({ useScope:'local', messages:{ 'zh-TW':chinese, zh:chinese, en:{ title:'Models by stage', intro:'Save the default connection with a name, then assign it to each stage. Active work keeps its original configuration.', name:'Connection name', copy:'Save default as a new connection', reload:'Reload', catalogueRead:'Model list read', catalogueUnknown:'Model list unverified', noGeneration:'Generation and structured output unverified', test:'Read model list', remove:'Remove', graph:'Graph and extraction', prepare:'Role preparation', simulation:'Simulation', report:'Report', default:'Use default', unsaved:'Unsaved changes', restore:'Restore', save:'Save stage settings', saved:'Saved. Applies to new work.', tested:'Model list read. No generation performed.', embedding:'Embedding remains local and separately configured. Changing chat models does not change dimensions or rebuild indexes.', failure:'Unable to update connections. Please try again.' } } })
const profiles=ref([]), assignments=ref({}), saved=ref({}), name=ref(''), busy=ref(false), error=ref(''), notice=ref('')
const stages=['graph','prepare','simulation','report']
let token='', generation=0, disposed=false
const dirty=computed(()=>JSON.stringify(assignments.value)!==JSON.stringify(saved.value) || !!name.value.trim())
watch(dirty,value=>emit('dirty',value))
function apply(data){ profiles.value=data.profiles; assignments.value={...data.assignments}; saved.value={...data.assignments} }
async function request(path,method='GET',data){const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-MiroFish-CSRF':token},...(data===undefined?{}:{body:JSON.stringify(data)})});const result=await response.json();if(!response.ok||!result.success)throw new Error(result.error||t('failure'));return result}
async function load(){ const id=++generation; busy.value=true; error.value=''; try { const response=await request('/api/settings/profiles'); if(disposed||id!==generation)return; token=response.data.csrf_token; apply(response.data) } catch(e){if(!disposed&&id===generation)error.value=e.message||t('failure')}finally{if(!disposed&&id===generation)busy.value=false} }
async function mutate(method,path,data,callback){if(busy.value)return;busy.value=true;error.value='';notice.value='';const id=++generation;try{const result=await request(path,method.toUpperCase(),data);if(disposed||id!==generation)return;callback(result.data)}catch(e){if(!disposed&&id===generation)error.value=e.message||t('failure')}finally{if(!disposed&&id===generation)busy.value=false}}
const copyDefault=()=>mutate('post','/api/settings/profiles',{name:name.value,from_default:true},data=>{apply(data);name.value='';notice.value=t('saved')})
const saveAssignments=()=>mutate('put','/api/settings/profiles/assignments',assignments.value,data=>{apply(data);notice.value=t('saved')})
const remove=id=>mutate('delete',`/api/settings/profiles/${encodeURIComponent(id)}`,{},apply)
const test=id=>mutate('post',`/api/settings/profiles/${encodeURIComponent(id)}/test`,{},data=>{const item=profiles.value.find(item=>item.id===id);if(item)item.capabilities=data.capabilities;notice.value=t('tested')})
const restore=()=>{assignments.value={...saved.value};name.value=''}
onMounted(load)
onBeforeUnmount(()=>{disposed=true;generation++})
</script>

<style scoped>
.stage-connections{margin-top:24px;padding:clamp(18px,3vw,30px);border:1px solid var(--studio-line);background:var(--studio-surface);border-radius:14px;color:var(--studio-ink)}
h2{font-size:1.25rem}p{line-height:1.7;color:var(--studio-muted);margin:10px 0 20px}.connection-copy{display:flex;align-items:end;gap:12px;flex-wrap:wrap}label{display:grid;gap:8px;flex:1;min-width:180px}input,select,button{font:inherit;min-height:44px;border:1px solid var(--theme-control-line);border-radius:7px;padding:9px 12px;background:var(--studio-paper);color:var(--studio-ink);max-width:100%}button{cursor:pointer}button:disabled{opacity:.6;cursor:default}.saved-connections{list-style:none;padding:0;margin:24px 0}.saved-connections li{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:16px 0;border-bottom:1px solid var(--studio-line)}li span,li small{display:block;overflow-wrap:anywhere;line-height:1.6}li small{color:var(--studio-muted)}.connection-actions,.assignment-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stage-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.assignment-actions{grid-column:1/-1;justify-content:flex-end}.connection-error{color:var(--studio-error,#a43120)}.connection-note{margin-bottom:0}input:focus-visible,select:focus-visible,button:focus-visible{outline:3px solid var(--studio-accent);outline-offset:3px}@media(max-width:640px){.stage-form{grid-template-columns:1fr}.connection-copy>*{width:100%}.stage-connections{padding:18px}}
</style>
