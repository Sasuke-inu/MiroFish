<template>
  <section class="report-version-action">
    <button v-if="eligible && !confirming && !taskId" :disabled="busy" data-testid="new-report-version" @click="confirming=true; error=''">{{ $t('research.newReportVersion') }}</button>
    <div v-if="confirming && eligible" class="version-confirm" role="group" :aria-label="$t('research.newReportVersion')"><p>{{ $t('research.reportVersionCost') }}</p><p>{{ $t('research.reportVersionPreserved') }}</p><button type="button" :disabled="busy" @click="confirming=false">{{ $t('research.cancel') }}</button><button type="button" class="primary" :disabled="busy" data-testid="confirm-report-version" @click="createVersion">{{ $t('research.confirmReportVersion') }}</button></div>
    <p v-if="busy" role="status">{{ $t('research.checkingReportVersion') }}</p><p v-if="error" role="alert" class="error">{{ error }}</p>
    <div v-if="taskId" class="saved-task"><p>{{ $t('research.reportTaskCreated',{id:taskId}) }}</p><p v-if="taskMessage">{{ taskMessage }}</p><button v-if="!taskTerminal" :disabled="busy" @click="readTask">{{ $t('research.readSavedTask') }}</button><RouterLink to="/workbench?view=tasks">{{ $t('research.tasks') }}</RouterLink></div>
  </section>
</template>
<script setup>
import {onUnmounted,ref,watch} from 'vue'
import {useRouter} from 'vue-router'
import {useI18n} from 'vue-i18n'
import {verifyReportRun,createReportVersion,readReportTask} from '../api/workbench'
const props=defineProps({simulationId:String,eligible:Boolean})
const emit=defineEmits(['created'])
const router=useRouter(),{t}=useI18n(),confirming=ref(false),busy=ref(false),error=ref(''),taskId=ref(''),taskMessage=ref(''),taskTerminal=ref(false)
let alive=true,generation=0
const valid=token=>alive&&token===generation
async function openResult(result,token){
  if(!valid(token))return
  const reportId=result.report_id || result.metadata?.report_id || result.result?.report_id
  if(reportId){emit('created');await router.push({name:'Report',params:{reportId}});return}
  taskMessage.value=result.error || result.message || ''
  taskTerminal.value=['completed','failed','stopped','interrupted','needs_review'].includes(result.status)
}
async function readTask(){
  if(busy.value||!taskId.value)return
  const token=generation;busy.value=true;error.value=''
  try{await openResult(await readReportTask(taskId.value),token)}catch(err){if(valid(token))error.value=err.message}finally{if(valid(token))busy.value=false}
}
async function createVersion(){
  if(busy.value||!confirming.value||!props.eligible)return
  const token=generation;busy.value=true;error.value='';confirming.value=false
  try{
    const run=await verifyReportRun(props.simulationId)
    if(!valid(token))return
    if(run.runner_status!=='completed'||run.graph_ready!==true){error.value=t('research.reportRunNotReady');return}
    const result=await createReportVersion(props.simulationId)
    if(!valid(token))return
    taskId.value=result.task_id || ''
    if(result.report_id)await openResult(result,token)
    else if(taskId.value)await openResult(await readReportTask(taskId.value),token)
    else throw new Error(t('research.reportResultUnknown'))
  }catch(err){if(valid(token))error.value=err.message+' '+t('research.checkTaskBeforeRetry')}
  finally{if(valid(token))busy.value=false}
}
watch(()=>[props.simulationId,props.eligible],()=>{generation++;confirming.value=false;busy.value=false;taskId.value='';taskMessage.value='';error.value=''})
onUnmounted(()=>{alive=false;generation++})
</script>
<style scoped>
.report-version-action{margin:18px 0}.version-confirm{padding:16px;border:1px solid var(--studio-line);border-radius:8px;background:var(--studio-paper)}p{margin:8px 0;font-size:.875rem;line-height:1.7}button,a{display:inline-flex;align-items:center;min-height:44px;margin:8px 8px 0 0;padding:8px 12px;border:1px solid var(--theme-control-line);border-radius:8px;background:var(--studio-paper);color:var(--studio-ink);font:inherit;font-size:.875rem;text-decoration:none}button:disabled{opacity:.55}.primary{background:var(--studio-button);color:var(--theme-on-filled)}.error{color:var(--studio-error);overflow-wrap:anywhere}.saved-task{overflow-wrap:anywhere}
</style>
