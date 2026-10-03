<template>
  <section class="home-research-overview" :aria-label="$t('research.resumeOverview')">
    <div v-if="activeWork.length || taskError" class="active-work-summary"><header><h2>{{ $t('research.activeWork') }}</h2><RouterLink to="/workbench?view=tasks">{{ $t('research.tasks') }} →</RouterLink></header><p v-if="taskError" class="error" role="alert">{{ taskError }} <button :disabled="tasksLoading" @click="loadTasks">{{ $t('research.retry') }}</button></p><ul><li v-for="work in activeWork.slice(0,3)" :key="work.task_id || work.run_id || work.simulation_id"><RouterLink to="/workbench?view=tasks"><strong>{{ work.description || work.simulation_id || work.task_type || work.task_id }}</strong><small>{{ status(work.status) }}</small></RouterLink></li></ul></div>
    <article>
      <header><h2>{{ $t('research.continueResearch') }}</h2><RouterLink to="/workbench">{{ $t('research.allResearch') }} →</RouterLink></header>
      <p v-if="loading" role="status">{{ $t('research.loading') }}</p>
      <p v-else-if="error" class="error" role="alert">{{ error }} <button @click="load">{{ $t('research.retry') }}</button></p>
      <p v-else-if="!projects.length" class="muted">{{ $t('research.noRecentResearch') }}</p>
      <ul><li v-for="project in projects" :key="project.project_id"><RouterLink :to="{name:'Workbench',params:{projectId:project.project_id}}"><strong>{{ project.name || project.project_id }}</strong><small>{{ status(project.status) }}<template v-if="project.demo"> · {{ $t('research.synthetic') }}</template></small></RouterLink></li></ul>
    </article>
    <article>
      <header><h2>{{ $t('research.recentResults') }}</h2><button @click="$emit('history')">{{ $t('research.allResults') }} →</button></header>
      <p v-if="historyState.loading" role="status">{{ $t('research.loading') }}</p>
      <p v-else-if="historyState.error" class="muted">{{ $t('research.recentResultsError') }} <button @click="$emit('history')">{{ $t('research.reviewHistory') }}</button></p>
      <p v-else-if="!reports.length" class="muted">{{ $t('research.noRecentResults') }}</p>
      <ul><li v-for="report in reports" :key="report.report_id"><RouterLink :to="{name:'Report',params:{reportId:report.report_id}}"><strong>{{ report.simulation_requirement || report.report_id }}</strong><small>{{ $t('research.savedReport') }} · {{ $t('research.reportRunState',{status:runStatus(report.runner_status)}) }}</small></RouterLink></li></ul>
    </article>
    <article class="demo-entry"><h2>{{ $t('research.demos') }}</h2><p>{{ $t('research.resumeDemoHelp') }}</p><RouterLink to="/workbench?view=demos">{{ $t('research.chooseDemo') }} →</RouterLink><small>{{ $t('research.resumeReadOnly') }}</small></article>
  </section>
</template>
<script setup>
import {computed,onMounted,onUnmounted,ref} from 'vue'
import {useI18n} from 'vue-i18n'
import {listProjects,listTasks} from '../api/workbench'
const props=defineProps({historyState:{type:Object,default:()=>({items:[],loading:false,error:false})}})
defineEmits(['history'])
const {t,te}=useI18n(),projects=ref([]),loading=ref(false),error=ref('')
const taskResponse=ref({items:[],runs:[]}),tasksLoading=ref(false),taskError=ref('')
const activeWork=computed(()=>[...(taskResponse.value.items || []),...(taskResponse.value.runs || [])].filter(item=>['pending','processing','starting','running','stopping','finalizing'].includes(item.status)))
const reports=computed(()=>[...new Map(props.historyState.items.filter(item=>item.report_id&&item.report_status==='completed').map(item=>[item.report_id,item])).values()].slice(0,3))
const status=value=>te(`research.statuses.${value}`)?t(`research.statuses.${value}`):(value || t('research.notRecorded'))
const runStatus=value=>['completed','stopped','failed','interrupted','needs_review','running','stopping','starting','finalizing'].includes(value)&&te(`research.statuses.${value}`)?t(`research.statuses.${value}`):t('research.unknownRunStatus')
let alive=true
async function load(){if(loading.value)return;loading.value=true;error.value='';try{const page=await listProjects({archived:0,offset:0,limit:4});if(alive)projects.value=page.items}catch(err){if(alive)error.value=err.message}finally{if(alive)loading.value=false}}
async function loadTasks(){if(tasksLoading.value)return;tasksLoading.value=true;taskError.value='';try{const response=await listTasks();if(alive)taskResponse.value=response}catch(err){if(alive)taskError.value=err.message}finally{if(alive)tasksLoading.value=false}}
onMounted(()=>{load();loadTasks()})
onUnmounted(()=>{alive=false})
</script>
<style scoped>
.active-work-summary{grid-column:1/-1;border-bottom:1px solid var(--studio-line);padding-bottom:16px}.active-work-summary ul{display:flex;gap:12px;flex-wrap:wrap}.active-work-summary li{flex:1;min-width:160px}.active-work-summary li+li{border-top:0}.home-research-overview{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(180px,.75fr);gap:24px;padding:24px;margin-bottom:36px;background:var(--studio-surface);border:1px solid var(--studio-line);border-radius:14px;color:var(--studio-ink);font:1rem/1.6 var(--studio-font)}article{min-width:0}article+article{border-left:1px solid var(--studio-line);padding-left:24px}header{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:4px 12px}h2{font-size:1rem;margin:0 0 8px;font-weight:600}ul{list-style:none;padding:0;margin:0}li+li{border-top:1px solid var(--studio-line)}a,button{color:var(--studio-ink);font:inherit;font-size:.875rem;text-decoration:none;min-height:44px;display:inline-flex;align-items:center;background:none;border:0;padding:8px 0;cursor:pointer}li a{display:flex;flex-direction:column;align-items:flex-start;gap:2px;width:100%}strong{font-weight:500;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}small,.muted{font-size:.8125rem;color:var(--studio-muted)}small{display:block}p{font-size:.875rem;margin:6px 0}.error{color:var(--studio-error)}.demo-entry>a{color:var(--studio-accent);font-weight:600}@media(max-width:959px){.home-research-overview{grid-template-columns:1fr;gap:16px;padding:20px;margin-bottom:24px}article+article{border-left:0;border-top:1px solid var(--studio-line);padding:16px 0 0}li a{padding-block:6px}h2{margin-bottom:4px}}
</style>
