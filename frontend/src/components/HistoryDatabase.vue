<template>
  <section ref="historyContainer" class="history-database" aria-labelledby="history-heading">
    <header class="section-header">
      <h2 id="history-heading" tabindex="-1">{{ $t('history.title') }}</h2>
      <p v-if="projects.length" class="history-count" role="status" aria-live="polite">{{ total === null ? $t('history.list.shown', { count: projects.length }) : $t('history.list.count', { count: projects.length, total }) }}</p>
    </header>

    <div v-if="loadError" class="history-error" role="alert">
      <p>{{ $t(loadError === 'more' ? 'history.list.moreFailed' : 'history.loadFailed') }}</p>
      <button type="button" @click="retryHistory" :disabled="loading || loadingMore">{{ $t('common.retry') }}</button>
    </div>

    <div v-if="!loading && !loadError && projects.length === 0" class="history-empty">
      <img class="history-empty-art" :src="'/assets/visuals/first-connection.webp'" alt="" width="480" height="320" loading="lazy" decoding="async" />
      <p>{{ $t('studio.noHistory') }}</p>
      <span>{{ $t('studio.historyHelp') }}</span>
    </div>

    <div v-if="projects.length" class="history-list">
      <div v-for="project in projects" :key="project.simulation_id" class="project-card" role="button" tabindex="0" aria-haspopup="dialog"
        :aria-label="historyLabel(project)" @click="navigateToProject(project, $event)"
        @keydown.enter.prevent="navigateToProject(project, $event)" @keydown.space.prevent="navigateToProject(project, $event)">
        <div class="record-content">
          <h3 class="card-title">{{ getSimulationTitle(project.simulation_requirement) }}</h3>
          <div class="record-meta">
            <time :datetime="project.created_at"><span class="card-date">{{ formatDate(project.created_at) }}</span> {{ formatTime(project.created_at) }}</time>
            <span class="card-progress" :class="getProgressClass(project)">{{ progressLabel(project) }}<template v-if="project.total_rounds"> · {{ formatRounds(project) }}</template></span>
            <span v-if="project.report_id" class="report-available">{{ $t('history.list.reportReady') }}</span>
          </div>
          <p class="record-files">{{ fileSummary(project) }}</p>
        </div>
        <span class="record-open" aria-hidden="true">{{ $t('history.list.open') }} <span>→</span></span>
      </div>
    </div>

    <p v-if="loading" class="loading-state" role="status">{{ $t('history.loadingText') }}</p>
    <div v-if="hasMore && loadError !== 'more'" class="history-pagination">
      <button type="button" class="load-more" :disabled="loading || loadingMore" @click="loadHistory({ append: true })">{{ $t(loadingMore ? 'history.loadingText' : 'history.list.loadMore') }}</button>
    </div>

    <Teleport to="body">
      <Transition name="modal">
        <div v-if="selectedProject" class="modal-overlay" @click.self="closeModal">
          <div ref="modalContent" class="modal-content" role="dialog" aria-modal="true" :aria-label="$t('history.replayTitle')" tabindex="-1" @keydown="handleModalKeydown">
            <header class="modal-header">
              <div class="modal-title-section">
                <span class="modal-id">{{ selectedProject.simulation_id }}</span>
                <span class="modal-progress" :class="getProgressClass(selectedProject)">{{ progressLabel(selectedProject) }}<template v-if="selectedProject.total_rounds"> · {{ formatRounds(selectedProject) }}</template></span>
                <time class="modal-create-time" :datetime="selectedProject.created_at">{{ formatDate(selectedProject.created_at) }} {{ formatTime(selectedProject.created_at) }}</time>
              </div>
              <button class="modal-close" type="button" @click="closeModal" :aria-label="$t('common.close')">×</button>
            </header>
            <div class="modal-body">
              <section class="modal-section">
                <h3 class="modal-label">{{ $t('history.list.question') }}</h3>
                <p class="modal-requirement">{{ selectedProject.simulation_requirement || $t('common.none') }}</p>
              </section>
              <section class="modal-section">
                <h3 class="modal-label">{{ $t('history.relatedFiles') }}</h3>
                <ul v-if="selectedProject.files?.length" class="modal-files">
                  <li v-for="(file, index) in selectedProject.files" :key="index" class="modal-file-item">
                    <span class="file-tag">{{ getFileTypeLabel(file.filename) }}</span>
                    <span class="modal-file-name">{{ file.filename }}</span>
                  </li>
                </ul>
                <p v-else class="modal-empty">{{ $t('history.noRelatedFiles') }}</p>
              </section>
            </div>
            <div class="modal-actions">
              <button type="button" class="modal-btn btn-project" @click="goToProject" :disabled="!selectedProject.project_id">{{ $t('history.list.graph') }}</button>
              <button type="button" class="modal-btn btn-simulation" @click="goToSimulation">{{ $t('history.list.simulation') }}</button>
              <button type="button" class="modal-btn btn-report" @click="goToReport" :disabled="!selectedProject.report_id">{{ $t('history.list.report') }}</button>
            </div>
            <p class="modal-playback-hint">{{ $t('history.list.savedContent') }}</p>
          </div>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getSimulationHistory } from '../api/simulation'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

// 状态
const projects = ref([])
const loading = ref(true)
const loadingMore = ref(false)
const hasMore = ref(false)
const total = ref(null)
const nextOffset = ref(0)
const pageSize = 20
const historyContainer = ref(null)
const selectedProject = ref(null)
const modalContent = ref(null)
const loadError = ref(null)
let opener = null
let previousOverflow = null
let appWasInert = false
let appRoot = null
let mounted = true
let historyRequest = 0

const restoreModalPage = () => {
  if (previousOverflow !== null) document.body.style.overflow = previousOverflow
  previousOverflow = null
  if (appRoot) appRoot.inert = appWasInert
  appRoot = null
}

watch(selectedProject, async (project) => {
  if (project) {
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    appRoot = document.getElementById('app')
    appWasInert = appRoot?.inert || false
    if (appRoot) appRoot.inert = true
    await nextTick()
    modalContent.value?.querySelector('.modal-close')?.focus()
  } else {
    restoreModalPage()
    await nextTick()
    if (opener?.isConnected) opener.focus()
    opener = null
  }
})

const handleModalKeydown = (event) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeModal()
    return
  }
  if (event.key !== 'Tab') return
  const controls = Array.from(modalContent.value?.querySelectorAll('button:not(:disabled), [href], [tabindex="0"]') || [])
  const first = controls[0]
  const last = controls[controls.length - 1]
  if (event.shiftKey && (document.activeElement === first || document.activeElement === modalContent.value)) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

// 根据轮数进度获取样式类
const getProgressClass = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  
  if (total === 0 || current === 0) {
    // 未开始
    return 'not-started'
  } else if (current >= total) {
    // 已完成
    return 'completed'
  } else {
    // 进行中
    return 'in-progress'
  }
}

// 格式化日期（只显示日期部分）
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    if (Number.isNaN(date.getTime())) return '—'
    // Use local date components (like formatTime below) so the displayed day
    // matches the displayed time. toISOString() converts to UTC and can show
    // the wrong day for non-UTC clients near midnight.
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  } catch {
    return dateStr?.slice(0, 10) || ''
  }
}

// 格式化时间（显示时:分）
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    if (Number.isNaN(date.getTime())) return '—'
    const hours = date.getHours().toString().padStart(2, '0')
    const minutes = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${minutes}`
  } catch {
    return ''
  }
}

const getSimulationTitle = requirement => requirement?.trim() || t('history.untitledSimulation')
const historyLabel = project => `${getSimulationTitle(project.simulation_requirement)} — ${formatDate(project.created_at)} ${formatTime(project.created_at)}`
const fileSummary = project => {
  const files = project.files || []
  if (!files.length) return t('history.noFiles')
  const first = files[0].filename || t('history.unknownFile')
  return files.length > 1 ? t('history.list.fileSummary', { name: first, count: files.length - 1 }) : first
}
const progressLabel = project => {
  const state = project.runner_status || project.status
  if (['failed', 'stopped', 'paused', 'stopping', 'running'].includes(state)) return t(`history.list.${state}`)
  return getProgressClass(project) === 'completed' || state === 'completed' ? t('history.list.completed') : t('history.notStarted')
}

// 格式化轮数显示（当前轮/总轮数）
const formatRounds = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  if (total === 0) return t('history.notStarted')
  return t('history.roundsProgress', { current, total })
}

// 获取文件类型标签文本
const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

// 打开项目详情弹窗
const navigateToProject = (simulation, event) => {
  opener = event?.currentTarget || document.activeElement
  selectedProject.value = simulation
}

// 关闭弹窗
const closeModal = () => {
  selectedProject.value = null
}

// 导航到图谱构建页面（Project）
const goToProject = () => {
  if (selectedProject.value?.project_id) {
    router.push({
      name: 'Process',
      params: { projectId: selectedProject.value.project_id }
    })
    closeModal()
  }
}

// 导航到环境配置页面（Simulation）
const goToSimulation = () => {
  if (selectedProject.value?.simulation_id) {
    router.push({
      name: 'Simulation',
      params: { simulationId: selectedProject.value.simulation_id }
    })
    closeModal()
  }
}

// 导航到分析报告页面（Report）
const goToReport = () => {
  if (selectedProject.value?.report_id) {
    router.push({
      name: 'Report',
      params: { reportId: selectedProject.value.report_id }
    })
    closeModal()
  }
}

// Fetch bounded pages and keep earlier rows available when a later page fails.
const loadHistory = async ({ append = false } = {}) => {
  if (append && (loading.value || loadingMore.value || !hasMore.value)) return
  const request = ++historyRequest
  const offset = append ? nextOffset.value : 0
  const previousCount = projects.value.length
  if (append) loadingMore.value = true
  else loading.value = true
  loadError.value = null
  try {
    const response = await getSimulationHistory(pageSize, offset)
    if (!mounted || request !== historyRequest) return
    if (!response.success || !Array.isArray(response.data)) throw new Error('Invalid history response')
    const existing = new Set(append ? projects.value.map(project => project.simulation_id) : [])
    const rows = response.data.filter(project => {
      if (existing.has(project.simulation_id)) return false
      existing.add(project.simulation_id)
      return true
    })
    if (append && response.data.length && !rows.length) throw new Error('History page did not advance')
    const pagination = response.pagination
    projects.value = append ? [...projects.value, ...rows] : rows
    nextOffset.value = pagination?.next_offset ?? offset + response.data.length
    hasMore.value = pagination?.has_more ?? response.data.length === pageSize
    total.value = Number.isInteger(pagination?.total) ? pagination.total : null
    if (append && rows.length) {
      await nextTick()
      if (mounted && request === historyRequest) historyContainer.value?.querySelectorAll('.project-card')[previousCount]?.focus()
    }
  } catch {
    if (mounted && request === historyRequest) loadError.value = append ? 'more' : 'initial'
  } finally {
    if (mounted && request === historyRequest) {
      loading.value = false
      loadingMore.value = false
    }
  }
}
const retryHistory = () => loadHistory({ append: loadError.value === 'more' })

watch(() => route.path, (newPath) => {
  if (newPath === '/') loadHistory()
})

onMounted(loadHistory)
onUnmounted(() => {
  mounted = false
  restoreModalPage()
})
</script>

<style scoped>
.history-database { width: 100%; padding-block: 28px 12px; color: var(--studio-ink); font-family: var(--studio-font); }
.section-header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-header h2 { margin: 0; font-size: 20px; font-weight: 650; line-height: 1.5; }
.history-count { margin: 0; font-size: 12px; color: var(--studio-muted); }
.history-list { border-block: 1px solid var(--studio-line); }
.project-card { display: flex; align-items: center; gap: 24px; min-height: 100px; padding: 18px 12px; cursor: pointer; transition: background-color .15s ease; }
.project-card + .project-card { border-top: 1px solid var(--studio-line); }
.project-card:hover { background: var(--theme-surface-soft); }
.record-content { flex: 1; min-width: 0; }
.card-title { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; margin: 0 0 7px; font-size: 16px; line-height: 1.65; font-weight: 600; overflow-wrap: anywhere; }
.record-meta { display: flex; flex-wrap: wrap; gap: 4px 14px; color: var(--studio-muted); font-size: 12px; line-height: 1.8; }
.record-meta time { font-variant-numeric: tabular-nums; }
.report-available, .completed { color: var(--studio-green); }
.in-progress { color: var(--theme-warning-ink); }
.record-files { margin: 5px 0 0; color: var(--studio-muted); font-size: 12px; line-height: 1.6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.record-open { display: inline-flex; align-items: center; gap: 12px; flex-shrink: 0; min-height: 44px; color: var(--studio-accent); font-size: 13px; }
.history-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 16px; text-align: center; }
.history-empty-art { width: 160px; max-width: 100%; height: auto; }
.history-empty p { margin: 0; font-size: 16px; }
.history-empty > span, .loading-state { color: var(--studio-muted); font-size: 13px; line-height: 1.7; }
.loading-state { padding: 24px 0; text-align: center; }
.history-error { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; padding: 16px; border: 1px solid var(--theme-error-line); border-radius: 8px; background: var(--theme-error-surface); font-size: 14px; }
.history-error p { margin: 0; line-height: 1.7; }
.history-pagination { display: flex; justify-content: center; padding-top: 20px; }
.history-error button, .load-more, .modal-btn { min-height: 44px; padding: 10px 16px; border: 1px solid var(--theme-line-strong); border-radius: 8px; background: var(--studio-surface); color: var(--studio-ink); font: 14px/1.6 var(--studio-font); cursor: pointer; }
.history-error button:hover, .load-more:hover, .modal-btn:hover:not(:disabled) { border-color: var(--studio-accent); background: var(--studio-soft); }
button:disabled { opacity: .6; cursor: not-allowed; }
.project-card:focus-visible, button:focus-visible, #history-heading:focus-visible { outline: 3px solid var(--studio-accent); outline-offset: 3px; }
.modal-overlay { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 20px; background: rgb(20 22 18 / .55); }
.modal-content { width: 680px; max-width: 100%; max-height: calc(100dvh - 40px); overflow-y: auto; overscroll-behavior: contain; border: 1px solid var(--studio-line); border-radius: 12px; background: var(--studio-surface); color: var(--studio-ink); font-family: var(--studio-font); box-shadow: 0 20px 60px rgb(0 0 0 / .18); }
.modal-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 20px 24px; border-bottom: 1px solid var(--studio-line); }
.modal-title-section { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 14px; min-width: 0; }
.modal-id { width: 100%; font-size: 13px; overflow-wrap: anywhere; }
.modal-progress, .modal-create-time { font-size: 12px; line-height: 1.7; }
.modal-create-time { color: var(--studio-muted); }
.modal-close { display: grid; place-items: center; flex-shrink: 0; width: 44px; height: 44px; border: 0; border-radius: 8px; background: transparent; color: var(--studio-ink); font-size: 26px; cursor: pointer; }
.modal-close:hover { background: var(--theme-surface-soft); }
.modal-body { display: grid; gap: 20px; padding: 24px; }
.modal-label { margin: 0 0 8px; color: var(--studio-muted); font-size: 13px; font-weight: 600; }
.modal-requirement { margin: 0; font-size: 15px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.modal-files { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.modal-file-item { display: flex; align-items: baseline; gap: 10px; font-size: 13px; line-height: 1.7; }
.file-tag { color: var(--studio-muted); font-size: 11px; flex-shrink: 0; }
.modal-file-name { min-width: 0; overflow-wrap: anywhere; }
.modal-empty { margin: 0; color: var(--studio-muted); font-size: 13px; }
.modal-actions { display: flex; flex-wrap: wrap; gap: 10px; padding: 0 24px; }
.modal-btn { flex: 1; }
.modal-playback-hint { margin: 16px 0 0; padding: 0 24px 24px; color: var(--studio-muted); font-size: 12px; line-height: 1.7; }
.modal-enter-active, .modal-leave-active { transition: opacity .15s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
@media (max-width: 540px) {
  .section-header { flex-wrap: wrap; }
  .project-card { align-items: flex-start; gap: 10px; padding: 16px 4px; }
  .record-open { font-size: 12px; gap: 4px; }
  .card-title { font-size: 15px; }
  .modal-overlay { padding: 12px; }
  .modal-content { max-height: calc(100dvh - 24px); }
  .modal-header, .modal-body { padding: 16px; }
  .modal-actions { flex-direction: column; padding-inline: 16px; }
  .modal-playback-hint { padding: 0 16px 16px; }
}
@media (prefers-reduced-motion: reduce) { .project-card, .modal-enter-active, .modal-leave-active { transition: none; } }
</style>
