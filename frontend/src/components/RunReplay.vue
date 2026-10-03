<template>
  <section class="run-replay">
    <h3>{{ $t('research.replay') }}</h3><p>{{ $t('research.replayHelp') }}</p>
    <label for="replay-run">{{ $t('research.chooseRun') }}</label><select id="replay-run" v-model="simulationId" @change="resetRun"><option value="">{{ $t('research.chooseRun') }}</option><option v-for="run in runs" :key="run.simulation_id" :value="run.simulation_id">{{ run.simulation_id }} · {{ run.status }}</option></select>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="simulationId">
      <div class="replay-view-switch" role="group" :aria-label="$t('research.replayView')"><button :aria-pressed="replayView === 'events'" @click="setReplayView('events')">{{ $t('research.eventListView') }}</button><button :aria-pressed="replayView === 'briefing'" @click="setReplayView('briefing')">{{ $t('research.briefingView') }}</button></div><form v-if="replayView === 'events'" class="filters" @submit.prevent="loadEvents(false)"><label>{{ $t('research.platform') }}<select v-model="platform"><option value="">{{ $t('research.allPlatforms') }}</option><option value="twitter">Twitter</option><option value="reddit">Reddit</option></select></label><label>{{ $t('research.actor') }}<input v-model="agentId" :placeholder="$t('research.allActors')" /></label><button :disabled="loading">{{ $t('research.applyFilters') }}</button></form>
      <p v-if="loading" role="status">{{ $t('research.loading') }}</p>
      <p class="muted">{{ $t(capability === 'exact_event_projection' ? 'research.eventProjection' : 'research.eventListOnly') }}</p><ul class="muted"><li v-for="item in limitations" :key="item">{{ item }}</li></ul><p class="muted">{{ $t('research.unknownCost') }}</p>
      <p v-if="!events.length && !loading">{{ $t('research.noEvents') }}</p>
      <ol v-if="replayView === 'events'" class="event-list"><li v-for="event in events" :key="event.event_id"><button :aria-pressed="selected?.event_id === event.event_id" :disabled="loading || seeking" @click="selectEvent(event)"><span>#{{ event.seq }} · {{ event.platform }} · {{ event.kind }}</span><small>{{ $t('research.actor') }} {{ event.agent_id ?? '—' }} · {{ $t('research.round') }} {{ event.round ?? '—' }}</small><span class="excerpt">{{ displayContent(event.content) }}</span></button></li></ol>
      <button :disabled="loading" @click="loadEvents(true)">{{ $t(hasMore ? 'research.loadMore' : 'research.checkNewEvents') }}</button>
      <article v-if="selected && replayView === 'events'" class="event-detail"><h4>{{ $t('research.eventDetail') }} #{{ selected.seq }}</h4><dl><dt>{{ $t('research.simulationTime') }}</dt><dd>{{ selected.simulation_time || '—' }}</dd><dt>{{ $t('research.observedTime') }}</dt><dd>{{ selected.observed_at || '—' }}</dd></dl><pre>{{ displayContent(selected.content) }}</pre><form @submit.prevent="referenceEvent"><label for="event-note">{{ $t('research.note') }}</label><textarea id="event-note" v-model="note" rows="2" /><p class="muted">{{ $t('research.eventReferenceHelp') }}</p><button :disabled="saving || !selected.run_id">{{ $t('research.saveEventReference') }}</button><p v-if="saved" role="status">{{ $t('research.referenceSaved') }}</p></form></article>
      <div class="play-controls"><button :disabled="loading || seeking || !events.length" @click="playing ? pause() : play()">{{ $t(playing ? 'research.pause' : 'research.play') }}</button><button :disabled="seeking || !events.some(e=>e.seq &lt; throughSeq)" @click="step(-1)">{{ $t('research.previousEvent') }}</button><button :disabled="seeking || !events.some(e=>e.seq > throughSeq)" @click="step(1)">{{ $t('research.nextEvent') }}</button><button :disabled="seeking || !events.some(e=>e.seq > throughSeq)" @click="nextRound">{{ $t('research.nextRound') }}</button><label for="playback-speed">{{ $t('research.playbackSpeed') }}</label><select id="playback-speed" v-model.number="speed"><option :value="0.5">0.5×</option><option :value="1">1×</option><option :value="2">2×</option></select></div><p v-if="pageEnd" role="status">{{ $t('research.replayPageEnd') }}</p><form class="seek-form" @submit.prevent="pause(); seek(seekTarget)"><label for="replay-sequence">{{ $t('research.throughSequence') }}</label><input id="replay-sequence" v-model.number="seekTarget" :disabled="loading || seeking" @input="pause" type="number" min="0" step="1" required /><button :disabled="seeking">{{ $t('research.viewProjection') }}</button></form>
      <ReplayBriefing v-if="replayView === 'briefing'" :event="selected" :projection="projection" :run="selectedRun" :seeking="seeking" :limitations="limitations" /><p v-if="projectionError" class="error" role="alert">{{ projectionError }}</p><div v-if="projection && replayView === 'events'" class="projection"><h4>{{ $t('research.projectionTitle', {seq:projection.through_seq}) }}</h4><p class="muted">{{ $t('research.projectionLimit') }}</p><p>{{ $t('research.projectionCount', {count:projection.event_count ?? projection.events.length}) }}</p><ul><li v-for="actor in projection.actors" :key="`${actor.platform}:${actor.agent_id}`">{{ actor.platform }} · {{ actor.agent_id }} — {{ $t('research.actionCount', {count:actor.actions_count}) }}</li></ul><h4>{{ $t('research.recordedRelationships') }}</h4><p v-if="!projection.relationships.length">{{ $t('research.noRelationships') }}</p><ul><li v-for="relation in projection.relationships" :key="relation.event_id">{{ relation.platform }}: {{ relation.source_agent_id }} → {{ relation.target_agent_id }} · {{ relation.kind }}</li></ul></div>
    </template>
    <details class="compare"><summary>{{ $t('research.compare') }}</summary><p v-if="runs.some(run=>run.legacy || !run.run_id || !run.manifest)" class="muted">{{ $t('research.legacyCompareUnavailable') }}</p><p>{{ $t('research.compareHelp') }}</p><form @submit.prevent="compare"><label for="compare-left">{{ $t('research.leftRun') }}</label><select id="compare-left" v-model="left"><option value="">{{ $t('research.chooseRun') }}</option><option v-for="run in completedRuns" :key="run.simulation_id" :value="run.simulation_id">{{ run.simulation_id }}</option></select><label for="compare-right">{{ $t('research.rightRun') }}</label><select id="compare-right" v-model="right"><option value="">{{ $t('research.chooseRun') }}</option><option v-for="run in completedRuns" :key="run.simulation_id" :value="run.simulation_id">{{ run.simulation_id }}</option></select><button :disabled="comparing || !left || !right || left === right">{{ $t('research.compareSaved') }}</button></form><p v-if="compareError" class="error" role="alert">{{ compareError }}</p><template v-if="comparison"><p class="notice">{{ $t(comparison.non_single_variable ? 'research.multipleVariables' : 'research.noCausality') }}</p><div class="table-scroll"><table><caption>{{ $t('research.settingsDifferences') }}</caption><thead><tr><th>{{ $t('research.setting') }}</th><th>A</th><th>B</th></tr></thead><tbody><tr v-for="difference in comparison.manifest_diff" :key="difference.path"><th>{{ difference.path }}</th><td>{{ difference.left_present ? displayContent(difference.left) : $t('research.notRecorded') }}</td><td>{{ difference.right_present ? displayContent(difference.right) : $t('research.notRecorded') }}</td></tr></tbody></table></div><EventCountComparison :counts="comparison.kind_counts" /><h4>{{ $t('research.firstDifference') }}</h4><template v-if="comparison.first_difference"><p>#{{ comparison.first_difference.index }}</p><pre>A: {{ displayContent(comparison.first_difference.left?.content) }}</pre><pre>B: {{ displayContent(comparison.first_difference.right?.content) }}</pre></template><p v-else>{{ $t('research.noDifference') }}</p><ReportComparison :project-id="projectId" :report-diff="comparison.report_diff" :evidence-diff="comparison.evidence_diff" @inspect="emit('inspect',$event)" /><ul><li v-for="item in comparison.limitations" :key="item">{{ item }}</li></ul><p>{{ $t('research.unknownCost') }}</p></template></details>
  </section>
</template>
<script setup>
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useI18n} from 'vue-i18n'
import {useRoute,useRouter} from 'vue-router'
import ReplayBriefing from './ReplayBriefing.vue'
import EventCountComparison from './EventCountComparison.vue'
import ReportComparison from './ReportComparison.vue'
import {getEvents,getProjection,compareRuns,saveReference,resolveEventReference} from '../api/workbench'
const props = defineProps({runs:{type:Array,default:()=>[]},projectId:String})
const emit = defineEmits(['saved','inspect'])
const route=useRoute(),router=useRouter(),{t}=useI18n()
let restoring=false
function preservePosition(){if(restoring || route.name!=='Workbench')return;router.replace({query:{...route.query,section:'runs',replay_view:replayView.value==='briefing'?'briefing':undefined,ref_run:undefined,ref_event:undefined,replay:simulationId.value,seq:String(throughSeq.value),...(platform.value?{replay_platform:platform.value}:{replay_platform:undefined}),...(agentId.value?{replay_actor:agentId.value}:{replay_actor:undefined})}})}
const simulationId=ref(''),platform=ref(''),agentId=ref(''),events=ref([]),selected=ref(null),cursor=ref(null),hasMore=ref(false),capability=ref('event_list'),limitations=ref([]),loading=ref(false),error=ref(''),projection=ref(null),throughSeq=ref(0),seeking=ref(false),projectionError=ref(''),note=ref(''),saving=ref(false),saved=ref(false)
const left=ref(''),right=ref(''),comparison=ref(null),comparing=ref(false),compareError=ref(''),completedRuns=computed(()=>props.runs.filter(run=>run.status==='completed' && run.run_id && !run.legacy && run.manifest))
const replayView=ref(route.query.replay_view==='briefing'?'briefing':'events')
function setReplayView(value){pause();replayView.value=value;preservePosition()}
watch(()=>route.query.replay_view,value=>{replayView.value=value==='briefing'?'briefing':'events'})
const selectedRun=computed(()=>props.runs.find(run=>run.simulation_id===simulationId.value))
const playing=ref(false),speed=ref(1),pageEnd=ref(false),seekTarget=ref(0)
watch(throughSeq,value=>{seekTarget.value=value})
let playTimer=null
let alive=true,generation=0,eventRequest=0,projectionRequest=0,comparisonRequest=0,restoreRequest=0,filterScope=''
function displayContent(value) {return typeof value==='string'?value:JSON.stringify(value??null,null,2)}
function resetRun(){pause();restoreRequest++;restoring=false;generation++;eventRequest++;projectionRequest++;events.value=[];selected.value=null;projection.value=null;cursor.value=null;platform.value='';agentId.value='';throughSeq.value=0;seekTarget.value=0;loading.value=false;seeking.value=false;saved.value=false;if(simulationId.value)loadEvents(false)}
async function loadEvents(more=false){if(loading.value)return;const token=++eventRequest,run=generation;const scope=JSON.stringify([platform.value,agentId.value]);if(scope!==filterScope)more=false;if(!more){pause();projection.value=null;selected.value=null;}pageEnd.value=false;filterScope=scope;loading.value=true;error.value='';try{const data=await getEvents(simulationId.value,{limit:50,...(more&&cursor.value?{cursor:cursor.value}:{}),...(platform.value?{platform:platform.value}:{}),...(agentId.value.trim()?{agent_id:agentId.value.trim()}:{})});if(!alive||token!==eventRequest||run!==generation)return;events.value=more?[...events.value,...data.items]:data.items;cursor.value=data.next_cursor;hasMore.value=data.has_more;capability.value=data.capability;limitations.value=data.limitations; if(!more){selected.value=null;throughSeq.value=0;seekTarget.value=0}preservePosition()}catch(err){if(alive&&token===eventRequest&&run===generation)error.value=err.message}finally{if(alive&&token===eventRequest)loading.value=false}}
async function seek(sequence=throughSeq.value){
  if(loading.value||seeking.value||!Number.isInteger(sequence)||sequence<0)return
  const token=++projectionRequest,run=generation
  throughSeq.value=sequence;seeking.value=true;projectionError.value='';projection.value=null
  selected.value=events.value.find(event=>event.seq===sequence)||null
  try{const data=await getProjection(simulationId.value,sequence);if(alive&&token===projectionRequest&&run===generation){projection.value=data;selected.value=data.events?.find(event=>event.seq===sequence) || selected.value;preservePosition()}}
  catch(err){if(alive&&token===projectionRequest){projectionError.value=err.message;pause()}}
  finally{if(alive&&token===projectionRequest)seeking.value=false}
}
function pause(){playing.value=false;if(playTimer!==null)clearTimeout(playTimer);playTimer=null}
async function advance(){
  if(!playing.value||!alive)return
  const next=events.value.find(event=>event.seq>throughSeq.value)
  if(!next){pause();pageEnd.value=true;return}
  await seek(next.seq)
  if(playing.value&&alive)playTimer=setTimeout(advance,1000/speed.value)
}
function play(){if(playing.value||seeking.value||route.name!=='Workbench'||document.visibilityState==='hidden')return;playing.value=true;pageEnd.value=false;advance()}
function selectEvent(event){pause();seek(event.seq)}
function step(direction){pause();const next=direction>0?events.value.find(event=>event.seq>throughSeq.value):events.value.findLast(event=>event.seq<throughSeq.value);if(next)seek(next.seq)}
function nextRound(){pause();const current=events.value.findLast(event=>event.seq<=throughSeq.value);const next=events.value.find(event=>event.seq>throughSeq.value&&(!current||event.round!==current.round));if(next)seek(next.seq);else pageEnd.value=true}
async function referenceEvent(){if(saving.value||!selected.value?.run_id)return;const token=generation,event=selected.value;saving.value=true;error.value='';try{await saveReference(props.projectId,{subject_type:'project',subject_id:props.projectId,category:'simulation_event',relation:'insufficient',run_id:event.run_id,event_id:event.event_id,note:note.value});if(alive&&token===generation){saved.value=true;emit('saved')}}catch(err){if(alive&&token===generation)error.value=err.message}finally{if(alive)saving.value=false}}
async function compare(){if(comparing.value||!left.value||!right.value||left.value===right.value)return;const token=++comparisonRequest;comparing.value=true;compareError.value='';comparison.value=null;try{const data=await compareRuns(left.value,right.value);if(alive&&token===comparisonRequest)comparison.value=data}catch(err){if(alive&&token===comparisonRequest)compareError.value=err.message}finally{if(alive&&token===comparisonRequest)comparing.value=false}}
watch(selected,()=>{saved.value=false;note.value=''})
watch([left,right],()=>{comparisonRequest++;comparison.value=null;comparing.value=false})
async function restoreFromRoute(){
  const requestedRun=route.query.ref_run,requestedEvent=route.query.ref_event
  let saved=route.query.replay,sequence=Number(route.query.seq || 0),resolved=null
  const token=++restoreRequest
  pause();generation++;eventRequest++;projectionRequest++;loading.value=false;seeking.value=false;error.value='';restoring=true
  try{
    if(typeof requestedRun==='string'&&typeof requestedEvent==='string'){
      resolved=await resolveEventReference(props.projectId,requestedRun,requestedEvent)
      if(!alive||token!==restoreRequest)return
      if(resolved.project_id!==props.projectId||resolved.run_id!==requestedRun||resolved.event_id!==requestedEvent)throw new Error(t('research.eventReferenceMissing'))
      saved=resolved.simulation_id;sequence=resolved.seq
    }
    if(typeof saved!=='string'||!props.runs.some(run=>run.simulation_id===saved)){
      if(resolved)throw new Error(t('research.eventReferenceMissing'))
      return
    }
    if(!Number.isSafeInteger(sequence)||sequence<0)throw new Error(t('research.eventReferenceMissing'))
    simulationId.value=saved
    platform.value=resolved?'':(['twitter','reddit'].includes(route.query.replay_platform)?route.query.replay_platform:'')
    agentId.value=resolved?'':(typeof route.query.replay_actor==='string'?route.query.replay_actor:'')
    await loadEvents(false)
    if(!alive||token!==restoreRequest)return
    await seek(sequence)
    if(alive&&token===restoreRequest&&resolved&&!projectionError.value)selected.value=resolved
  }catch(err){if(alive&&token===restoreRequest)error.value=err.message}
  finally{if(alive&&token===restoreRequest){restoring=false;if(simulationId.value&&!error.value&&!projectionError.value)preservePosition()}}
}
function pauseWhenHidden(){if(document.visibilityState==='hidden')pause()}
watch(()=>route.name,name=>{if(name!=='Workbench')pause()})
watch(()=>[route.query.ref_run,route.query.ref_event],([run,event])=>{if(route.name==='Workbench'&&typeof run==='string'&&typeof event==='string')restoreFromRoute()})
onMounted(()=>{document.addEventListener('visibilitychange',pauseWhenHidden);if(route.query.replay||route.query.ref_event)restoreFromRoute()})
onUnmounted(()=>{pause();document.removeEventListener('visibilitychange',pauseWhenHidden);restoreRequest++;alive=false;generation++;eventRequest++;projectionRequest++;comparisonRequest++})
</script>
<style scoped>
.replay-view-switch{display:flex;gap:8px;margin-top:16px}.replay-view-switch button[aria-pressed=true]{background:var(--studio-button);color:var(--theme-on-filled)}.play-controls{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:24px}.play-controls label{margin:0}.play-controls select{width:85px}.run-replay{border-bottom:1px solid var(--studio-line);padding-bottom:24px;margin-bottom:24px}h3{font-size:1.1rem}h4{margin:20px 0 8px}p{margin:12px 0}label{display:block;margin:14px 0 6px;font-weight:600}select,input,textarea{display:block;width:100%;padding:10px;border:1px solid var(--theme-control-line);border-radius:8px;background:var(--studio-paper);color:var(--studio-ink);font:inherit}button{min-height:44px;padding:8px 14px;border:1px solid var(--theme-control-line);border-radius:8px;background:var(--studio-paper);color:var(--studio-ink);font:inherit}button:disabled{opacity:.55}form>button{margin-top:16px}.filters{display:flex;align-items:end;gap:12px}.filters label{flex:1;min-width:0}.filters button{margin-bottom:6px;flex-shrink:0}.muted,small{color:var(--studio-muted);font-size:.875rem}.error{color:var(--studio-error);padding:12px;border-left:3px solid var(--studio-error)}.notice{padding:12px;background:var(--studio-paper)}.event-list{padding:0;list-style:none;max-height:480px;overflow:auto}.event-list button{display:flex;flex-direction:column;gap:4px;width:100%;margin:6px 0;text-align:left}.event-list button[aria-pressed=true]{border-color:var(--studio-accent)}.excerpt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;font-size:.875rem}.event-detail,.projection{margin:20px 0;padding:16px;border:1px solid var(--studio-line);border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--studio-paper);padding:12px;font:.875rem/1.7 var(--studio-font)}dl{display:grid;grid-template-columns:auto 1fr;gap:8px;font-size:.875rem}dd{margin:0;overflow-wrap:anywhere}.seek-form{display:flex;align-items:center;gap:12px;margin-top:24px}.seek-form label{margin:0}.seek-form input{width:100px}.seek-form button{margin:0}.compare{margin-top:32px}summary{cursor:pointer;font-weight:600;padding:10px 0;min-height:44px}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;margin:20px 0}caption{text-align:left;font-weight:600}th,td{padding:10px;border:1px solid var(--studio-line);text-align:left;overflow-wrap:anywhere;max-width:260px;vertical-align:top}.counts{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:600px){.filters,.seek-form{flex-wrap:wrap}.filters label{flex-basis:100%}.counts{grid-template-columns:1fr}dl{grid-template-columns:1fr}.event-detail{padding:12px}}
</style>
