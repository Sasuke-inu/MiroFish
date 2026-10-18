<template>
  <div class="evidence-backdrop" @click.self="$emit('close')">
    <section ref="dialog" class="evidence-inspector" role="dialog" aria-modal="true" :aria-labelledby="`${uid}-title`" @keydown="handleKeys">
      <header><div><p class="eyebrow">{{ $t('research.evidence') }}</p><h2 :id="`${uid}-title`">{{ source?.title || $t('research.source') }}</h2></div><button ref="closeButton" type="button" :aria-label="$t('research.close')" @click="$emit('close')">×</button></header>
      <p v-if="error" class="error" role="alert">{{ error }} <button type="button" @click="loadSource">{{ $t('research.retry') }}</button></p>
      <p v-if="loading" role="status">{{ $t('research.loading') }}</p>
      <template v-if="source">
        <dl><dt>{{ $t('research.origin') }}</dt><dd>{{ source.locator || source.identity || $t('research.notRecorded') }}</dd><dt>{{ $t('research.sourceType') }}</dt><dd>{{ source.source_type }}</dd></dl>
        <label :for="`${uid}-version`">{{ $t('research.savedVersion') }}</label>
        <select :id="`${uid}-version`" v-model="versionId" :disabled="loading" @change="loadVersion"><option v-for="item in versions" :key="item.version_id" :value="item.version_id">{{ item.created_at || item.fetched_at || item.version_id }} · {{ item.character_count ?? '—' }} {{ $t('research.characters') }}</option></select>
        <p v-if="versionTotal > versions.length" class="muted">{{ $t('research.showingVersions', { count: versions.length, total: versionTotal }) }}</p>
        <button v-if="versionTotal > versions.length" :disabled="loading || saving" @click="moreVersions">{{ $t('research.loadMoreVersions') }}</button>
        <details v-if="source.source_type === 'web'"><summary>{{ $t('research.updateSource') }}</summary><p>{{ $t('research.updateCost') }}</p><button :disabled="saving || loading" @click="updateSource">{{ $t('research.fetchUpdate') }}</button></details>
        <p v-if="updateResult" role="status">{{ $t('research.webFetchSummary',{count:updateResult.versions?.length || 0,attempts:updateResult.collection?.attempted ?? '—',status:updateResult.collection?.status || '—'}) }}</p><p v-if="updateResult?.collection?.errors?.length" class="error">{{ $t('research.webPartial') }}</p>
        <details v-if="versions.length > 1" class="version-compare"><summary>{{ $t('research.compareVersions') }}</summary><form @submit.prevent="compareVersions"><label :for="`${uid}-before`">{{ $t('research.beforeVersion') }}</label><select :id="`${uid}-before`" v-model="beforeId"><option v-for="item in versions" :key="item.version_id" :value="item.version_id">{{ item.created_at || item.version_id }} · {{ item.version_id }}</option></select><label :for="`${uid}-after`">{{ $t('research.afterVersion') }}</label><select :id="`${uid}-after`" v-model="afterId"><option v-for="item in versions" :key="item.version_id" :value="item.version_id">{{ item.created_at || item.version_id }} · {{ item.version_id }}</option></select><button :disabled="comparing || !beforeId || !afterId || beforeId === afterId">{{ $t('research.compareText') }}</button></form><template v-if="difference"><p class="muted">{{ $t('research.diffHelp') }}</p><p v-if="!difference.changed">{{ $t('research.noTextDifference') }}</p><template v-else><h3>{{ $t('research.beforeVersion') }} · {{ difference.start }}–{{ difference.beforeEnd }}</h3><pre class="diff-before">{{ difference.before.slice(0,20000) || $t('research.emptyTextRange') }}</pre><h3>{{ $t('research.afterVersion') }} · {{ difference.start }}–{{ difference.afterEnd }}</h3><pre class="diff-after">{{ difference.after.slice(0,20000) || $t('research.emptyTextRange') }}</pre><p v-if="difference.before.length > 20000 || difference.after.length > 20000" class="muted">{{ $t('research.diffTruncated') }}</p></template><p class="muted">{{ $t('research.frozenAnalysis') }}</p></template></details>
        <template v-if="version">
          <dl><dt>{{ $t('research.fetchedAt') }}</dt><dd>{{ version.fetched_at || $t('research.notRecorded') }}</dd><dt>{{ $t('research.publishedAt') }}</dt><dd>{{ version.published_at || $t('research.notRecorded') }}</dd><dt>{{ $t('research.fingerprint') }}</dt><dd class="fingerprint">{{ version.sha256 || $t('research.notRecorded') }}</dd></dl>
          <p class="muted">{{ $t('research.sourceSafety') }}</p>
          <template v-if="version.content_available !== false && typeof version.content === 'string'">
            <label :for="`${uid}-content`">{{ $t('research.preservedText') }}</label>
            <textarea ref="contentBox" :id="`${uid}-content`" class="source-content" readonly :value="version.content" spellcheck="false" />
            <button type="button" :disabled="saving" @click="captureSelection">{{ $t('research.useSelection') }}</button>
          </template>
          <p v-else class="error" role="status">{{ $t('research.contentMissing') }}</p>
          <div v-if="spans.length" class="saved-spans"><h3>{{ $t('research.savedQuotes') }}</h3><button v-for="span in spans" :key="span.span_id" class="quote-button" :aria-pressed="selectedSpan?.span_id === span.span_id" @click="chooseSpan(span)"><span>{{ span.quote }}</span><small>{{ span.start }}–{{ span.end }}</small></button></div>
          <button v-if="spanTotal > spans.length" :disabled="loading || saving" @click="moreSpans">{{ $t('research.loadMore') }}</button>
          <form v-if="selectedSpan || selection" class="reference-form" @submit.prevent="addReference">
            <h3>{{ $t('research.addReference') }}</h3>
            <blockquote>{{ selectedSpan?.quote || selection?.quote }}</blockquote>
            <label :for="`${uid}-subject-type`">{{ $t('research.referenceTarget') }}</label><select :id="`${uid}-subject-type`" v-model="targetType"><option v-for="item in ['project','report','report_section','agent','node','edge','event','conclusion']" :key="item" :value="item">{{ $t(`research.targets.${item}`) }}</option></select>
            <label :for="`${uid}-subject-id`">{{ $t('research.targetId') }}</label><input :id="`${uid}-subject-id`" v-model="targetId" required maxlength="200" /><p class="muted">{{ $t('research.targetHelp') }}</p>
            <p>{{ $t('research.declaredRelation') }}</p>
            <label :for="`${uid}-relation`">{{ $t('research.relation') }}</label><select :id="`${uid}-relation`" v-model="relation"><option v-for="item in ['supports', 'contradicts', 'insufficient']" :key="item" :value="item">{{ $t(`research.relations.${item}`) }}</option></select>
            <label :for="`${uid}-note`">{{ $t('research.note') }}</label><textarea :id="`${uid}-note`" v-model="note" rows="3" maxlength="12000" />
            <button class="primary" type="submit" :disabled="saving">{{ saving ? $t('research.saving') : $t('research.saveReference') }}</button>
          </form>
          <p v-if="saved" role="status">{{ $t('research.referenceSaved') }}</p>
        </template>
        <div v-if="reference" class="reference-check"><h3>{{ $t('research.locationCheck') }}</h3><p>{{ $t(`research.locations.${reference.validation?.location_status || 'unverified'}`) }}</p><p>{{ $t('research.semanticNotEvaluated') }}</p><p>{{ reference.note }}</p></div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSource, getVersion, saveSpan, saveReference, refreshSource } from '../api/workbench'
import { sourceDiff } from '../utils/sourceDiff'
const props = defineProps({ sourceId: String, projectId: String, initialVersionId: String, initialSpanId: String, reference: Object, subjectType: { type: String, default: 'project' }, subjectId: String })
const emit = defineEmits(['close', 'saved'])
const { t } = useI18n()
const uid = useId()
const dialog = ref(null), closeButton = ref(null), contentBox = ref(null)
const source = ref(null), versions = ref([]), versionTotal = ref(0), versionOffset = ref(0), versionId = ref(''), version = ref(null), spans = ref([]), spanTotal = ref(0)
const loading = ref(false), error = ref(''), saving = ref(false), saved = ref(false)
const selectedSpan = ref(null), selection = ref(null), relation = ref('supports'), note = ref('')
const targetType=ref(props.subjectType),targetId=ref(props.subjectId || props.projectId)
const updateResult=ref(null)
const beforeId=ref(''),afterId=ref(''),difference=ref(null),comparing=ref(false)
watch([beforeId,afterId],()=>{difference.value=null})
watch(()=>versions.value.map(item=>item.version_id).join(','),()=>{
  if (!versions.value.some(item=>item.version_id===afterId.value)) afterId.value=versions.value[0]?.version_id || ''
  if (!versions.value.some(item=>item.version_id===beforeId.value)) beforeId.value=versions.value.find(item=>item.version_id!==afterId.value)?.version_id || ''
})
const focusReturn = document.activeElement
let mounted = true, requestId = 0
async function loadSource() {
  const request = ++requestId
  loading.value = true; error.value = ''; source.value = version.value = null
  try {
    const data = await getSource(props.sourceId)
    if (!mounted || request !== requestId) return
    source.value = data.source
    versions.value = data.versions?.items || []
    versionOffset.value = versions.value.length
    versionTotal.value = data.versions?.total || versions.value.length
    versionId.value = props.initialVersionId || data.latest_version_id || versions.value[0]?.version_id || ''
    if (versionId.value) await loadVersion()
  } catch (err) { if (mounted && request === requestId) error.value = err.message }
  finally { if (mounted && request === requestId) loading.value = false }
}
async function loadVersion() {
  const request = ++requestId
  loading.value = true; error.value = ''; version.value = null; selectedSpan.value = selection.value = null; saved.value = false
  try {
    const data = await getVersion(versionId.value)
    if (!mounted || request !== requestId) return
    version.value = data
    if (!versions.value.some(item => item.version_id === data.version_id)) versions.value.push(data)
    spans.value = data.spans?.items || []
    spanTotal.value = data.spans?.total || spans.value.length
    selectedSpan.value = spans.value.find(span => span.span_id === props.initialSpanId) || null
  } catch (err) { if (mounted && request === requestId) error.value = err.message }
  finally { if (mounted && request === requestId) loading.value = false }
}
async function moreVersions() {
  const request = requestId; loading.value = true
  try { const data = await getSource(props.sourceId,{offset:versionOffset.value,limit:50}); if (mounted && request === requestId) { versionOffset.value += data.versions.items.length; versions.value.push(...data.versions.items.filter(item => !versions.value.some(existing => existing.version_id === item.version_id))); versionTotal.value = data.versions.total } }
  catch(err) { if (mounted && request === requestId) error.value = err.message }
  finally { if (mounted && request === requestId) loading.value = false }
}
async function moreSpans() {
  const request = requestId; loading.value = true
  try { const data = await getVersion(versionId.value,{offset:spans.value.length,limit:50}); if (mounted && request === requestId) { spans.value.push(...data.spans.items); spanTotal.value = data.spans.total; if (!selectedSpan.value && props.initialSpanId) selectedSpan.value=spans.value.find(span=>span.span_id===props.initialSpanId)||null } }
  catch(err) { if (mounted && request === requestId) error.value = err.message }
  finally { if (mounted && request === requestId) loading.value = false }
}
async function updateSource() {
  if (saving.value) return
  const request = requestId; saving.value = true; error.value = ''
  try { const result=await refreshSource(props.sourceId); if (mounted && request === requestId) { updateResult.value=result; await loadSource(); emit('saved') } }
  catch(err) { if (mounted && request === requestId) error.value = err.message }
  finally { if (mounted) saving.value = false }
}
async function compareVersions() {
  if(comparing.value || !beforeId.value || !afterId.value || beforeId.value===afterId.value)return
  const request=requestId,left=beforeId.value,right=afterId.value
  comparing.value=true;difference.value=null;error.value=''
  try {
    const [before,after]=await Promise.all([getVersion(left),getVersion(right)])
    if(!mounted || request!==requestId || beforeId.value!==left || afterId.value!==right)return
    if(before.content_available===false || after.content_available===false || typeof before.content!=='string' || typeof after.content!=='string') throw new Error(t('research.contentMissing'))
    difference.value=sourceDiff(before.content,after.content)
  } catch(err){if(mounted&&request===requestId)error.value=err.message}
  finally{if(mounted)comparing.value=false}
}
function chooseSpan(span) { selectedSpan.value = span; selection.value = null; saved.value = false }
function captureSelection() {
  const box = contentBox.value
  if (!box || box.selectionStart === box.selectionEnd) { error.value = t('research.selectQuote'); return }
  // Browser selections use UTF-16 offsets; preserved text offsets use Unicode characters.
  selection.value = { start: Array.from(box.value.slice(0, box.selectionStart)).length, end: Array.from(box.value.slice(0, box.selectionEnd)).length, quote: box.value.slice(box.selectionStart, box.selectionEnd) }
  selectedSpan.value = null; saved.value = false; error.value = ''
}
async function addReference() {
  if (saving.value || (!selection.value && !selectedSpan.value)) return
  saving.value = true; error.value = ''
  const request = requestId
  const selectedVersion = versionId.value
  const target = {subject_type:targetType.value,subject_id:targetId.value,relation:relation.value,note:note.value}
  try {
    if (!selectedSpan.value) {
      const span = await saveSpan(selectedVersion, { ...selection.value })
      if (!mounted || request !== requestId) return
      selectedSpan.value = span
      spans.value.push(span)
    }
    await saveReference(props.projectId, { ...target, category: 'source_record', source_id: props.sourceId, version_id: selectedVersion, span_id: selectedSpan.value.span_id })
    if (!mounted || request !== requestId) return
    saved.value = true; emit('saved')
  } catch (err) { if (mounted && request === requestId) error.value = err.message }
  finally { if (mounted) saving.value = false }
}
function handleKeys(event) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('close'); return }
  if (event.key !== 'Tab') return
  event.stopPropagation()
  const items = [...dialog.value.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]')]
  const first = items[0], last = items.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
watch(() => props.sourceId, loadSource)
onMounted(() => { loadSource(); nextTick(() => closeButton.value?.focus()) })
onUnmounted(() => { mounted = false; requestId++; if (focusReturn?.isConnected) focusReturn.focus() })
</script>

<style scoped>
.evidence-backdrop { position: fixed; inset: 0; z-index: 3000; background: rgb(0 0 0 / .35); display: flex; justify-content: flex-end; }
.evidence-inspector { width: min(660px, 100%); height: 100%; overflow: auto; padding: 24px; background: var(--studio-surface); color: var(--studio-ink); box-shadow: -8px 0 40px rgb(0 0 0 / .12); font: 1rem/1.7 var(--studio-font); }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; border-bottom: 1px solid var(--studio-line); padding-bottom: 16px; }
h2 { margin: 0; font-size: 1.35rem; overflow-wrap: anywhere; } h3 { margin: 20px 0 10px; font-size: 1rem; }
.eyebrow, .muted { color: var(--studio-muted); font-size: .875rem; } .eyebrow { margin: 0 0 4px; }
button { min-height: 44px; padding: 8px 14px; border: 1px solid var(--theme-control-line); border-radius: 8px; color: var(--studio-ink); background: var(--studio-paper); }
button:disabled { opacity: .6; } .primary { background: var(--studio-button); color: var(--theme-on-filled); }
header button { font-size: 24px; flex-shrink: 0; } label { display: block; margin: 14px 0 6px; font-weight: 600; }
input, select, textarea { display: block; width: 100%; padding: 10px 12px; border: 1px solid var(--theme-control-line); border-radius: 8px; background: var(--studio-paper); color: var(--studio-ink); font: inherit; }
.source-content { min-height: 260px; resize: vertical; white-space: pre-wrap; line-height: 1.8; margin-bottom: 12px; }
dl { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 8px 16px; font-size: .875rem; margin: 20px 0; } dt { color: var(--studio-muted); } dd { margin: 0; overflow-wrap: anywhere; }
.fingerprint { font-family: Consolas, monospace; font-size: .75rem; }.error { color: var(--studio-error); border-left: 3px solid var(--studio-error); padding: 8px 12px; background: var(--theme-error-surface); }
.quote-button { display: flex; width: 100%; justify-content: space-between; gap: 12px; text-align: left; margin-bottom: 8px; } .quote-button span { overflow-wrap: anywhere; } .quote-button small { flex-shrink: 0; color: var(--studio-muted); } .quote-button[aria-pressed=true] { border-color: var(--studio-accent); background: var(--studio-soft); }
blockquote { margin: 12px 0; border-left: 3px solid var(--studio-accent); padding: 8px 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
.reference-form, .reference-check { border-top: 1px solid var(--studio-line); margin-top: 24px; padding-top: 8px; } .reference-form button { margin-top: 16px; }
.version-compare { margin:20px 0; } summary { cursor:pointer; min-height:44px; padding:8px 0; font-weight:600; } .version-compare button { margin-top:16px; } .version-compare pre { white-space:pre-wrap; overflow-wrap:anywhere; padding:12px; background:var(--studio-paper); font: .875rem/1.7 var(--studio-font); } .diff-before { border-left:3px solid var(--studio-muted); } .diff-after { border-left:3px solid var(--studio-accent); }
@media (max-width: 600px) { .evidence-inspector { padding: 20px 16px; } dl { grid-template-columns: 80px minmax(0, 1fr); } }
</style>
