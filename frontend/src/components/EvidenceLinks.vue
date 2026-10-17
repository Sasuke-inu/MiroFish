<template>
  <div v-if="projectId && subjectId" class="object-evidence">
    <button type="button" :aria-expanded="open" @click="toggle">{{ text.evidence }}</button>
    <section v-if="open" class="object-evidence-content" :aria-label="text.evidence">
      <p>{{ text.boundary }}</p>
      <p v-if="loading" role="status">{{ text.loading }}</p>
      <p v-if="error" role="alert">{{ error }} <button type="button" @click="load()">{{ text.retry }}</button></p>
      <p v-if="!loading && !references.length">{{ text.empty }}</p>
      <article v-for="reference in references" :key="reference.reference_id">
        <strong>{{ $t(`research.relations.${reference.relation}`) }}</strong>
        <span> · {{ $t(`research.categories.${reference.category}`) }}</span>
        <p>{{ reference.note }}</p>
        <small>{{ $t(`research.locations.${reference.validation?.location_status || 'unverified'}`) }}</small>
        <EventReferenceLink :project-id="projectId" :reference="reference" :report-id="reportSubjectId" /><button v-if="reference.source_id" type="button" @click="inspect(reference)">{{ text.inspect }}</button>
      </article>
      <button v-if="hasMore" :disabled="loading" type="button" @click="load(true)">{{ text.more }}</button>
      <label :for="selectId">{{ text.attach }}</label>
      <select :id="selectId" v-model="sourceId"><option value="">{{ text.choose }}</option><option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.title }}</option></select>
      <button v-if="moreSources" type="button" :disabled="loading" @click="loadSources(true)">{{ text.moreSources }}</button>
      <button type="button" :disabled="!sourceId" @click="inspector={sourceId}">{{ text.selectQuote }}</button>
    </section>
    <Teleport to="body"><EvidenceInspector v-if="inspector" v-bind="inspector" :project-id="projectId" :subject-type="subjectType" :subject-id="subjectId" @close="inspector=null" @saved="load()" /></Teleport>
  </div>
</template>

<script setup>
import { computed, ref, watch, onUnmounted, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import EventReferenceLink from './EventReferenceLink.vue'
import EvidenceInspector from './EvidenceInspector.vue'
import { listReferences, listSources } from '../api/workbench'
const props=defineProps({projectId:String,subjectType:String,subjectId:String})
const {locale}=useI18n()
const route=useRoute()
const strings={
  en:{evidence:'Evidence and assumptions',boundary:'Saved references and user annotations. A matching quotation does not prove the claim.',loading:'Loading saved evidence…',retry:'Retry',empty:'No saved reference for this item. Its source has not been verified.',inspect:'Locate source',more:'More references',attach:'Attach a preserved quotation',choose:'Choose a saved source',moreSources:'More sources',selectQuote:'Select quotation'},
  zh:{evidence:'證據與假設',boundary:'這裡保存來源引用及使用者註記。引句定位相符，不代表內容已證實。',loading:'讀取已保存證據…',retry:'重試',empty:'此項目尚無保存的引用，來源未經驗證。',inspect:'定位原文',more:'更多引用',attach:'附上已保存的來源引句',choose:'選擇已保存的來源',moreSources:'更多來源',selectQuote:'選取引句'}
}
const text=computed(()=>strings[locale.value==='en'?'en':'zh'])
// The saved report this evidence object belongs to travels with an event link,
// so a standalone report page keeps its version when returning to the workbench.
const reportSubjectId=computed(()=>props.subjectType==='report'?props.subjectId:(props.subjectType==='report_section'&&props.subjectId?String(props.subjectId).split(':section:')[0]:''))
const selectId=useId(),open=ref(false),loading=ref(false),error=ref(''),references=ref([]),hasMore=ref(false),sources=ref([]),moreSources=ref(false),sourceId=ref(''),inspector=ref(null)
let alive=true,generation=0
async function loadSources(more=false){
  const token=generation
  try{const page=await listSources(props.projectId,{offset:more?sources.value.length:0,limit:50});if(alive&&token===generation){sources.value=more?[...sources.value,...page.items]:page.items;moreSources.value=page.has_more}}
  catch(err){if(alive&&token===generation)error.value=err.message}
}
async function load(more=false){
  const token=++generation;loading.value=true;error.value=''
  try{const page=await listReferences(props.projectId,{subject_type:props.subjectType,subject_id:props.subjectId,offset:more?references.value.length:0,limit:50});if(!alive||token!==generation)return;references.value=more?[...references.value,...page.items]:page.items;hasMore.value=page.has_more;if(!more)await loadSources()}
  catch(err){if(alive&&token===generation)error.value=err.message}
  finally{if(alive&&token===generation)loading.value=false}
}
function toggle(){open.value=!open.value;if(open.value)load()}
function inspect(reference){inspector.value={sourceId:reference.source_id,initialVersionId:reference.version_id,initialSpanId:reference.span_id,reference}}
watch(()=>[props.projectId,props.subjectType,props.subjectId],()=>{generation++;references.value=[];sources.value=[];inspector.value=null;sourceId.value='';if(open.value)load()})
watch(()=>route?.name,name=>{if(name==='Settings')inspector.value=null})
onUnmounted(()=>{alive=false;generation++})
</script>

<style scoped>
.object-evidence{margin-block:1rem;font:inherit;color:var(--studio-ink)}
.object-evidence button,.object-evidence select{font:inherit;color:var(--studio-ink);background:var(--studio-surface);border:1px solid var(--theme-control-line);border-radius:6px;padding:.55rem .7rem;min-height:44px;max-width:100%;cursor:pointer}
.object-evidence-content{padding-block:.8rem;line-height:1.6;overflow-wrap:anywhere}
.object-evidence-content article{border-block-start:1px solid var(--studio-line);padding-block:.7rem}
.object-evidence-content p{margin-block:.5rem}
.object-evidence-content label{display:block;margin-top:1rem}
button:focus-visible,select:focus-visible{outline:3px solid var(--studio-accent);outline-offset:3px}
button:disabled{cursor:default;opacity:.65}
</style>
