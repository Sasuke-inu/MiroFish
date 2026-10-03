<template>
  <div class="main-view" :data-layout="viewMode">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" role="button" tabindex="0" @click="router.push('/')" @keydown.enter="router.push('/')" @keydown.space.prevent="router.push('/')">MIROFISH</div>
      </div>
      
      <div class="header-center">
        <div class="view-switcher">
          <button 
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }" :aria-pressed="viewMode === mode"
            @click="viewMode = mode"
          >
            {{ { graph: $t('main.layoutGraph'), split: $t('main.layoutSplit'), workbench: $t('main.layoutWorkbench') }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <RouterLink class="research-return" :to="returnToResearch">{{ $t('research.backToResearch') }}</RouterLink>
        <LanguageSwitcher />
        <PreferenceControls />
        <div class="step-divider"></div>
        <div class="workflow-step">
          <span class="step-num">Step {{ currentStep }}/5</span>
          <span class="step-name">{{ $tm('main.stepNames')[currentStep - 1] }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass" role="status">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>
    <WorkflowProgress :current="currentStep" />

    <p v-if="error" class="workflow-error" role="alert">{{ error }} <button class="generation-button" @click="initProject">{{ $t('workbench.refresh') }}</button></p>
    <section v-if="canGenerate" class="generation-controls"><p>{{ $t('workbench.costNotice') }}</p><button class="generation-button" data-testid="start-project" :disabled="generationBusy || loading" @click="startGeneration">{{ $t(currentProjectId === 'new' || projectData?.status === 'created' ? 'workbench.analyze' : 'workbench.build') }}</button></section>

    <!-- Main Content Area -->
    <main id="workspace-content" class="content-area" tabindex="-1">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" v-show="viewMode !== 'workbench'" :inert="viewMode === 'workbench'" :aria-hidden="viewMode === 'workbench'" :style="leftPanelStyle">
        <GraphPanel
          :project-id="currentProjectId === 'new' ? undefined : currentProjectId"
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="currentPhase"
          :awaitingGraphSetup="awaitingGraphSetup"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step Components -->
      <div class="panel-wrapper right" v-show="viewMode !== 'graph'" :inert="viewMode === 'graph'" :aria-hidden="viewMode === 'graph'" :style="rightPanelStyle">
        <!-- Step 1: 图谱构建 -->
        <Step1GraphBuild 
          v-if="currentStep === 1"
          :currentPhase="currentPhase"
          :awaitingGraphSetup="awaitingGraphSetup"
          :projectData="projectData"
          :ontologyProgress="ontologyProgress"
          :buildProgress="buildProgress"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @next-step="handleNextStep"
        />
        <!-- Step 2: 环境搭建 -->
        <Step2EnvSetup
          v-else-if="currentStep === 2"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import {safeWorkbenchReturn} from '../utils/workbenchJourney'
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphPanel from '../components/GraphPanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import PreferenceControls from '../components/PreferenceControls.vue'
import WorkflowProgress from '../components/WorkflowProgress.vue'
import service from '../api'

const returnToResearch=computed(()=>safeWorkbenchReturn(route.query.from,currentProjectId.value !== 'new' ? '/workbench/' + currentProjectId.value : '/workbench'))
const route = useRoute()
const router = useRouter()
const { t, tm } = useI18n()

// Layout State
const viewMode = ref('split') // graph | split | workbench

// Step State
const currentStep = ref(1) // 1: 图谱构建, 2: 环境搭建, 3: 开始模拟, 4: 报告生成, 5: 深度互动
const stepNames = computed(() => tm('main.stepNames'))

// Data State
const currentProjectId = ref(route.params.projectId)
let mounted = true
let generation = 0
let taskBusy = false
let graphBusy = false
const valid = token => mounted && token === generation
const generationBusy = ref(false)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const currentPhase = ref(-1) // -1: Upload, 0: Ontology, 1: Build, 2: Complete
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])
const awaitingGraphSetup = ref(false)
const canGenerate = computed(() => !error.value && (currentProjectId.value === 'new' ? getPendingUpload().isPending : ['created', 'ontology_generated'].includes(projectData.value?.status)))

// Polling timers
let pollTimer = null
let graphPollTimer = null

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return t('common.error')
  if (awaitingGraphSetup.value) return '等待圖譜服務設定'
  if (currentPhase.value >= 2) return t('common.ready')
  if (currentPhase.value === 1) return t('step1.graphRagBuild')
  if (currentPhase.value === 0) return generationBusy.value ? t('step1.ontologyGenerating') : t('common.pending')
  return t('step2.initializing')
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  // Keep last 100 logs
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
  }
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleNextStep = (params = {}) => {
  if (currentStep.value < 5) {
    currentStep.value++
    addLog(t('log.enterStep', { step: currentStep.value, name: stepNames.value[currentStep.value - 1] }))
    
    // 如果是从 Step 2 进入 Step 3，记录模拟轮数配置
    if (currentStep.value === 3 && params.maxRounds) {
      addLog(t('log.customSimRounds', { rounds: params.maxRounds }))
    }
  }
}

const handleGoBack = () => {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(t('log.returnToStep', { step: currentStep.value, name: stepNames.value[currentStep.value - 1] }))
  }
}

// --- Data Logic ---

const initProject = async () => {
  if (!mounted) return
  error.value = ''
  if (currentProjectId.value === 'new') {
    const pending = getPendingUpload()
    if (!pending.isPending || !pending.files.length) error.value = t('workbench.noDraft')
    currentPhase.value = -1
  } else await loadProject()
}
const startGeneration = async () => {
  if (!mounted || generationBusy.value || loading.value || !canGenerate.value) return
  const token = generation
  generationBusy.value = true
  error.value = ''
  try {
    if (currentProjectId.value === 'new') await handleNewProject()
    else if (projectData.value?.status === 'created') await analyzeSavedProject()
    else await startBuildGraph()
  } finally { if (valid(token)) generationBusy.value = false }
}
const analyzeSavedProject = async () => {
  const token = generation
  try {
    ontologyProgress.value = { message: t('workbench.analyzing') }
    const formData = new FormData()
    formData.append('project_id', currentProjectId.value)
    formData.append('simulation_requirement', projectData.value?.simulation_requirement || '')
    const res = await generateOntology(formData)
    if (!valid(token)) return
    if (!res.success || !res.data?.project_id) throw new Error(res.error || t('common.unknownError'))
    await loadProject()
  } catch (err) { if (valid(token)) error.value = err.message }
  finally { if (valid(token)) ontologyProgress.value = null }
}
const handleNewProject = async () => {
  const token = generation
  const pending = getPendingUpload()
  if (!pending.isPending || !pending.files.length) { error.value = t('workbench.noDraft'); return }
  try {
    currentPhase.value = 0
    ontologyProgress.value = { message: t('workbench.analyzing') }
    const formData = new FormData()
    pending.files.forEach(file => formData.append('files', file))
    formData.append('simulation_requirement', pending.simulationRequirement)
    const res = await generateOntology(formData)
    if (!valid(token)) return
    if (!res.success || !res.data?.project_id) throw new Error(res.error || t('common.unknownError'))
    clearPendingUpload()
    projectData.value = res.data
    ontologyProgress.value = null
    // Creation and graph building are distinct explicit actions.
    await router.replace({ name: 'Process', params: { projectId: res.data.project_id } })
  } catch (err) { if (valid(token)) error.value = err.message }
}
const loadProject = async () => {
  const token = generation
  loading.value = true
  try {
    const res = await getProject(currentProjectId.value)
    if (!valid(token)) return
    if (!res.success || !res.data) throw new Error(res.error || t('common.unknownError'))
    projectData.value = res.data
    const status = res.data.status
    currentPhase.value = status === 'graph_completed' ? 2 : status === 'graph_building' ? 1 : 0
    if (['failed', 'interrupted', 'needs_review'].includes(status)) error.value = res.data.error || t('workbench.' + status)
    if (status === 'graph_building' && res.data.graph_build_task_id) startPollingTask(res.data.graph_build_task_id)
    if (res.data.graph_id) await loadGraph(res.data.graph_id)
  } catch (err) { if (valid(token)) error.value = t('workbench.readFailed', { error: err.message }) }
  finally { if (valid(token)) loading.value = false }
}
const startBuildGraph = async () => {
  const token = generation
  try {
    const configuration = await service.get('/api/system/status')
    if (!valid(token)) return
    if (!configuration.data?.graph_configured) {
      awaitingGraphSetup.value = true
      return
    }
    awaitingGraphSetup.value = false
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: t('workbench.building') }
    const res = await buildGraph({ project_id: currentProjectId.value, force: false })
    if (!valid(token)) return
    if (!res.success || !res.data) throw new Error(res.error || t('common.unknownError'))
    if (res.data.reused && res.data.graph_id) await loadProject()
    else if (res.data.task_id) startPollingTask(res.data.task_id)
    else throw new Error(t('workbench.unknownState'))
  } catch (err) { if (valid(token)) error.value = err.message }
}
const startPollingTask = taskId => {
  if (!mounted) return
  stopPolling()
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
  pollTaskStatus(taskId)
}
const pollTaskStatus = async taskId => {
  if (!mounted || taskBusy) return
  const token = generation
  taskBusy = true
  try {
    const res = await getTaskStatus(taskId)
    if (!valid(token)) return
    if (!res.success || !res.data) throw new Error(res.error || t('common.unknownError'))
    const task = res.data
    buildProgress.value = { progress: task.progress || 0, message: task.message }
    error.value = ''
    if (task.status === 'completed') {
      stopPolling()
      await loadProject()
    } else if (['failed', 'interrupted', 'needs_review', 'cancelled'].includes(task.status)) {
      stopPolling()
      error.value = task.error || t('workbench.needs_review')
    }
  } catch (err) { if (valid(token)) error.value = t('workbench.readFailed', { error: err.message }) }
  finally { if (valid(token)) taskBusy = false }
}
const loadGraph = async graphId => {
  if (!mounted || graphBusy) return
  const token = generation
  graphBusy = true
  graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (!valid(token)) return
    if (!res.success) throw new Error(res.error || t('common.unknownError'))
    graphData.value = res.data
  } catch (err) { if (valid(token)) error.value = t('workbench.readFailed', { error: err.message }) }
  finally { if (valid(token)) { graphBusy = false; graphLoading.value = false } }
}
const refreshGraph = () => { if (projectData.value?.graph_id) loadGraph(projectData.value.graph_id) }
const stopPolling = () => { clearInterval(pollTimer); pollTimer = null }
const stopGraphPolling = () => { clearInterval(graphPollTimer); graphPollTimer = null }
onMounted(initProject)
watch(() => route.params.projectId, id => {
  if (!id || id === currentProjectId.value) return
  generation++
  stopPolling(); stopGraphPolling()
  currentProjectId.value = id
  projectData.value = graphData.value = null
  graphBusy = taskBusy = generationBusy.value = loading.value = false
  initProject()
})
onUnmounted(() => { mounted = false; generation++; stopPolling(); stopGraphPolling() })
</script>

<style scoped>
.research-return { color: var(--studio-muted); font-size: .875rem; text-decoration: none; padding: 8px; min-height: 44px; display: inline-flex; align-items: center; }
.generation-controls { padding: 12px 24px; border-bottom: 1px solid var(--studio-line); color: var(--studio-muted); background: var(--studio-surface); font-size: 14px; line-height: 1.7; }
.generation-button { min-height: 44px; padding: 8px 14px; border: 1px solid var(--studio-line); border-radius: 8px; background: var(--studio-button); color: var(--theme-on-filled); font: inherit; }

.workflow-error {
  flex-shrink: 0;
  margin: 12px 24px 0;
  padding: 12px 16px;
  border: 1px solid var(--studio-line, #e3e5e4);
  border-left: 3px solid var(--theme-error-ink, #a63b32);
  border-radius: 8px;
  background: var(--theme-error-surface, #fdf0ee);
  color: var(--theme-error-ink, #a63b32);
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--theme-surface, #FFF);
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid var(--theme-line, #EAEAEA);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--theme-surface, #FFF);
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: var(--theme-surface-soft, #F5F5F5);
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--theme-muted, #666);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: var(--theme-surface, #FFF);
  color: var(--theme-ink, #000);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--theme-muted, #666);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: var(--theme-muted, #999);
}

.step-name {
  font-weight: 700;
  color: var(--theme-ink, #000);
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: var(--theme-surface-raised, #E0E0E0);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--theme-surface-raised, #CCC);
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid var(--theme-line, #EAEAEA);
}
</style>
