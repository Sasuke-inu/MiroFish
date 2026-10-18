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
          <span class="step-num">Step 2/5</span>
          <span class="step-name">{{ $tm('main.stepNames')[1] }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass" role="status">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>
    <WorkflowProgress :current="2" />

    <p v-if="loadError" class="workflow-error" role="alert">{{ loadError }}</p>

    <!-- Main Content Area -->
    <main id="workspace-content" class="content-area" tabindex="-1">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" v-show="viewMode !== 'workbench'" :inert="viewMode === 'workbench'" :aria-hidden="viewMode === 'workbench'" :style="leftPanelStyle">
        <GraphPanel
          :project-id="projectData?.project_id"
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="2"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step2 环境搭建 -->
      <div class="panel-wrapper right" v-show="viewMode !== 'graph'" :inert="viewMode === 'graph'" :aria-hidden="viewMode === 'graph'" :style="rightPanelStyle">
        <Step2EnvSetup
          :simulationId="currentSimulationId"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import {safeWorkbenchReturn} from '../utils/workbenchJourney'
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation } from '../api/simulation'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import PreferenceControls from '../components/PreferenceControls.vue'
import WorkflowProgress from '../components/WorkflowProgress.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const returnToResearch=computed(()=>safeWorkbenchReturn(route.query.from,projectData.value?.project_id ? `/workbench/${projectData.value.project_id}?replay=${currentSimulationId.value}` : '/workbench'))
const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  simulationId: String
})

// Layout State
const viewMode = ref('split')

// Data State
const currentSimulationId = ref(props.simulationId || route.params.simulationId)
let mounted = true
let generation = 0
const valid = token => mounted && token === generation
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const loadError = ref('')
const currentStatus = ref('processing') // processing | completed | error

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
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return t('common.error')
  if (currentStatus.value === 'completed') return t('common.ready')
  return t('common.processing')
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleGoBack = () => {
  // 返回到 process 页面
  if (projectData.value?.project_id) {
    router.push({ name: 'Process', params: { projectId: projectData.value.project_id } })
  } else {
    router.push('/')
  }
}

const handleNextStep = (params = {}) => {
  addLog(t('log.enterStep3'))

  // 记录模拟轮数配置
  if (params.maxRounds) {
    addLog(t('log.customRoundsConfig', { rounds: params.maxRounds }))
  } else {
    addLog(t('log.useAutoRounds'))
  }
  
  // 构建路由参数
  const routeParams = {
    name: 'SimulationRun',
    params: { simulationId: currentSimulationId.value },
    query: {from:returnToResearch.value}
  }
  
  // 如果有自定义轮数，通过 query 参数传递
  if (params.maxRounds) {
    routeParams.query = { ...routeParams.query, maxRounds: params.maxRounds }
  }
  
  // 跳转到 Step 3 页面
  router.push(routeParams)
}

// --- Data Logic ---

/**
 * 检查并关闭正在运行的模拟
 * 当用户从 Step 3 返回到 Step 2 时，默认用户要退出模拟
 */
const loadSimulationData = async () => {
  const token = generation
  loadError.value = ''
  try {
    addLog(t('log.loadingSimData', { id: currentSimulationId.value }))

    // 获取 simulation 信息
    const simRes = await getSimulation(currentSimulationId.value)
    if (!valid(token)) return
    if (simRes.success && simRes.data) {
      const simData = simRes.data

      // 获取 project 信息
      if (simData.project_id) {
        const projRes = await getProject(simData.project_id)
          if (!valid(token)) return
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          addLog(t('log.projectLoadSuccess', { id: projRes.data.project_id }))
          
          // 获取 graph 数据
          if (projRes.data.graph_id) {
            await loadGraph(projRes.data.graph_id)
          }
        }
      }
    } else {
      loadError.value = t('log.loadSimDataFailed', { error: simRes.error || t('common.unknownError') })
      currentStatus.value = 'error'
      addLog(loadError.value)
    }
  } catch (err) {
    if (!valid(token)) return
    loadError.value = t('log.loadException', { error: err.message })
    currentStatus.value = 'error'
    addLog(loadError.value)
  }
}

const loadGraph = async (graphId) => {
  const token = generation
  graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (!valid(token)) return
    if (res.success) {
      graphData.value = res.data
      addLog(t('log.graphDataLoadSuccess'))
    }
  } catch (err) {
    if (!valid(token)) return
    addLog(t('log.graphLoadFailed', { error: err.message }))
  } finally {
    if (valid(token)) graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    loadGraph(projectData.value.graph_id)
  }
}

onMounted(loadSimulationData)
watch(() => props.simulationId || route.params.simulationId, id => {
  if (!id || id === currentSimulationId.value) return
  generation++
  currentSimulationId.value = id
  projectData.value = graphData.value = null
  loadError.value = ''
  loadSimulationData()
})
onUnmounted(() => { mounted = false; generation++ })
</script>

<style scoped>
.research-return { color: var(--studio-muted); font-size: .875rem; text-decoration: none; padding: 8px; min-height: 44px; display: inline-flex; align-items: center; }

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

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
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

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--theme-muted, #666);
  font-weight: 500;
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
