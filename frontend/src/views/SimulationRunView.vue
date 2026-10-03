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
        <RouterLink class="research-return" :to="projectData?.project_id ? '/workbench/' + projectData.project_id : '/workbench'">{{ $t('research.backToResearch') }}</RouterLink>
        <LanguageSwitcher />
        <PreferenceControls />
        <div class="step-divider"></div>
        <div class="workflow-step">
          <span class="step-num">Step 3/5</span>
          <span class="step-name">{{ $tm('main.stepNames')[2] }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass" role="status">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>
    <WorkflowProgress :current="3" />

    <p v-if="loadError" class="workflow-error" role="alert">{{ loadError }}</p>

    <!-- Main Content Area -->
    <main id="workspace-content" class="content-area" tabindex="-1">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" v-show="viewMode !== 'workbench'" :inert="viewMode === 'workbench'" :aria-hidden="viewMode === 'workbench'" :style="leftPanelStyle">
        <GraphPanel
          :project-id="projectData?.project_id"
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="3"
          :isSimulating="isSimulating"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step3 开始模拟 -->
      <div class="panel-wrapper right" v-show="viewMode !== 'graph'" :inert="viewMode === 'graph'" :aria-hidden="viewMode === 'graph'" :style="rightPanelStyle">
        <Step3Simulation
          :simulationId="currentSimulationId"
          :maxRounds="maxRounds"
          :minutesPerRound="minutesPerRound"
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step3Simulation from '../components/Step3Simulation.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation, getSimulationConfig } from '../api/simulation'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import PreferenceControls from '../components/PreferenceControls.vue'
import WorkflowProgress from '../components/WorkflowProgress.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
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
let graphBusy = false
const valid = token => mounted && token === generation
// 直接在初始化时从 query 参数获取 maxRounds，确保子组件能立即获取到值
const maxRounds = ref(route.query.maxRounds ? parseInt(route.query.maxRounds) : null)
const minutesPerRound = ref(30) // 默认每轮30分钟
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const loadError = ref('')
const currentStatus = ref('pending') // processing | completed | error

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
  if (['error', 'failed', 'interrupted', 'needs_review', 'stopped'].includes(currentStatus.value)) return t('workbench.' + (currentStatus.value === 'error' ? 'readState' : currentStatus.value))
  if (currentStatus.value === 'completed') return t('common.completed')
  return ['idle', 'pending'].includes(currentStatus.value) ? t('common.pending') : currentStatus.value === 'stopping' ? t('workbench.stopping') : currentStatus.value === 'finalizing' ? t('workbench.finalizing') : t('common.running')
})

const isSimulating = computed(() => ['processing', 'starting', 'running', 'stopping', 'finalizing'].includes(currentStatus.value))

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
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

const handleGoBack = () => router.push({ name: 'Simulation', params: { simulationId: currentSimulationId.value } })

const handleNextStep = () => {
  // Step3Simulation 组件会直接处理报告生成和路由跳转
  // 这个方法仅作为备用
  addLog(t('log.enterStep4'))
}

// --- Data Logic ---
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
      
      // 获取 simulation config 以获取 minutes_per_round
      try {
        const configRes = await getSimulationConfig(currentSimulationId.value)
    if (!valid(token)) return
        if (configRes.success && configRes.data?.time_config?.minutes_per_round) {
          minutesPerRound.value = configRes.data.time_config.minutes_per_round
          addLog(t('log.timeConfig', { minutes: minutesPerRound.value }))
        }
      } catch (configErr) {
        addLog(t('log.timeConfigFetchFailed', { minutes: minutesPerRound.value }))
      }
      
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
  if (graphBusy || !mounted) return
  const token = generation
  graphBusy = true
  // 当正在模拟时，自动刷新不显示全屏 loading，以免闪烁
  // 手动刷新或初始加载时显示 loading
  if (!isSimulating.value) {
    graphLoading.value = true
  }
  
  try {
    const res = await getGraphData(graphId)
    if (!valid(token)) return
    if (res.success) {
      graphData.value = res.data
      if (!isSimulating.value) {
        addLog(t('log.graphDataLoadSuccess'))
      }
    }
  } catch (err) {
    if (!valid(token)) return
    addLog(t('log.graphLoadFailed', { error: err.message }))
  } finally {
    if (valid(token)) { graphLoading.value = false; graphBusy = false }
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    loadGraph(projectData.value.graph_id)
  }
}

// --- Auto Refresh Logic ---
let graphRefreshTimer = null

const startGraphRefresh = () => {
  if (graphRefreshTimer) return
  addLog(t('log.graphRealtimeRefreshStart'))
  // 立即刷新一次，然后每30秒刷新
  graphRefreshTimer = setInterval(refreshGraph, 30000)
}

const stopGraphRefresh = () => {
  if (graphRefreshTimer) {
    clearInterval(graphRefreshTimer)
    graphRefreshTimer = null
    addLog(t('log.graphRealtimeRefreshStop'))
  }
}

watch(isSimulating, (newValue) => {
  if (newValue) {
    startGraphRefresh()
  } else {
    stopGraphRefresh()
  }
}, { immediate: true })

onMounted(() => {
  addLog(t('log.simRunViewInit'))
  
  // 记录 maxRounds 配置（值已在初始化时从 query 参数获取）
  if (maxRounds.value) {
    addLog(t('log.customRounds', { rounds: maxRounds.value }))
  }
  
  loadSimulationData()
})

watch(() => props.simulationId || route.params.simulationId, id => {
  if (!id || id === currentSimulationId.value) return
  generation++
  stopGraphRefresh()
  currentSimulationId.value = id
  maxRounds.value = route.query.maxRounds ? Number.parseInt(route.query.maxRounds) : null
  projectData.value = graphData.value = null
  graphBusy = false
  graphLoading.value = false
  currentStatus.value = 'pending'
  systemLogs.value = []
  loadSimulationData()
})
onUnmounted(() => {
  mounted = false
  generation++
  stopGraphRefresh()
})
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
