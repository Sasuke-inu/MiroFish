<template>
  <div class="home-container">
    <nav class="studio-navbar" :aria-label="$t('studio.navigation')">
      <RouterLink to="/" class="studio-brand"><span class="brand-mark" aria-hidden="true">≈</span><span>MIROFISH<small>{{ $t('studio.brandSubtitle') }}</small></span></RouterLink>
      <div class="studio-nav-links">
        <button @click="scrollToBottom" class="history-link">{{ $t('studio.history') }}</button>
        <LanguageSwitcher />
        <PreferenceControls />
      </div>
    </nav>
    <main class="studio-home-main" id="workspace-content" tabindex="-1">
      <header class="studio-intro">
        <h1>{{ $t('studio.refined.headline') }}</h1>
        <p>{{ $t('studio.refined.intro') }}</p>
      </header>
      <div class="studio-home-grid">
        <section class="new-project-card" aria-labelledby="new-project-heading">
          <h2 id="new-project-heading" class="visually-hidden">{{ $t('studio.newProject') }}</h2>
          <div class="project-inputs">
            <div class="form-section prompt-section">
              <h3 class="form-section-heading"><span aria-hidden="true">1</span><label for="simulation-goal">{{ $t('studio.refined.question') }}</label></h3>
              <textarea id="simulation-goal" v-model="formData.simulationRequirement" class="goal-input" :placeholder="$t('studio.goalPlaceholder')" rows="3" :disabled="loading"></textarea>
              <div v-if="!formData.simulationRequirement.trim()" class="goal-examples">
                <button v-for="(example, index) in $tm('quality.examples')" :key="index" type="button" :disabled="loading" @click="useExample(index)">{{ example.label }}<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 12 12 4M4 4h8v8" /></svg></button>
              </div>
            </div>
            <div class="form-section">
              <h3 class="form-section-heading"><span aria-hidden="true">2</span>{{ $t('studio.uploadTitle') }}</h3>
              <WebSources :collection="sourceCollection" :disabled="loading" />
              <div class="upload-zone" :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }" @dragover.prevent="handleDragOver" @dragleave.prevent="handleDragLeave" @drop.prevent="handleDrop">
                <input ref="fileInput" id="source-files" type="file" multiple accept=".pdf,.md,.markdown,.txt" @change="handleFileSelect" class="visually-hidden" :disabled="loading" :aria-label="$t('studio.uploadTitle')" />
                <button type="button" class="upload-select" @click="triggerFileInput" :disabled="loading">
                  <svg class="upload-symbol" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M8 13V4h8l4 4v6M16 4v5h4M4 14v6h16v-3M8 14l4-4 4 4M12 10v7" /></svg>
                  <span class="upload-title">{{ files.length ? $t('studio.addFiles') : $t('studio.refined.upload') }}</span>
                  <span class="upload-hint">PDF · MD · TXT</span>
                </button>
                <div v-if="files.length" class="file-list" aria-live="polite">
                  <div v-for="(file, index) in files" :key="index" class="file-item">
                    <span class="file-extension">{{ file.name.split('.').pop().toUpperCase() }}</span>
                    <span class="file-meta"><span class="file-name">{{ file.name }}</span><small>{{ formatSize(file.size) }}</small></span>
                    <button type="button" @click.stop="removeFile(index)" class="remove-btn" :disabled="loading" :aria-label="$t('studio.removeFile', { name: file.name })">×</button>
                  </div>
                </div>
              </div>
              <p v-if="fileFeedback" class="file-feedback" role="status">{{ fileFeedback }}</p>
              <p v-if="files.length" class="file-summary" role="status">{{ $t('quality.filesReady', { count: files.length, size: formatSize(totalSize) }) }}</p>
            </div>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <div class="project-submit-row">
            <p aria-live="polite">{{ submitHelp }}</p>
            <div class="submit-actions">
              <button v-if="sourceCollection.errorCode && availableFiles.length" type="button" class="continue-sources-btn" :disabled="loading || !formData.simulationRequirement.trim()" @click="startSimulation(true)">{{ $t('sources.simple.continue', { count: availableFiles.length }) }}</button>
              <button type="button" class="start-engine-btn" @click="startSimulation()" :disabled="!canSubmit || loading"><span>{{ startLabel }}</span><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 10h14m-6-6 6 6-6 6" /></svg></button>
            </div>
          </div>
        </section>
        <aside class="journey-panel">
          <ExplorationJourney />
          <details class="workflow-details">
            <summary>{{ $t('studio.refined.fullWorkflow') }}</summary>
            <WorkflowExplorer />
          </details>
        </aside>
      </div>
      <details class="workspace-details">
        <summary><span>{{ $t('studio.refined.connections') }}</span><span class="readiness-summary"><span class="service-dot" :class="{ connected: systemStatus?.ready }" aria-hidden="true"></span>{{ readinessTitle }}</span></summary>
        <section class="service-card" aria-labelledby="service-heading">
          <h2 id="service-heading">{{ $t('studio.serviceStatus') }}</h2>
          <p>{{ readinessDescription }}</p>
          <div class="service-row"><span>{{ $t('studio.modelConnection') }}</span><strong :class="{ connected: systemStatus?.llm_configured }">{{ connection(systemStatus?.llm_configured) }}</strong></div>
          <div class="service-row"><span>{{ $t(systemStatus?.graph_provider === 'graphiti' ? 'studio.localGraphConnection' : 'studio.graphConnection') }}</span><strong :class="{ connected: systemStatus?.graph_configured }">{{ connection(systemStatus?.graph_configured) }}</strong></div>
          <button v-if="statusError" type="button" class="service-retry" :disabled="statusBusy" @click="refreshStatus">{{ $t('studio.refresh') }}</button>
        </section>
      </details>
      <section id="project-history" class="studio-history"><HistoryDatabase /></section>
      <footer class="studio-footer"><span>MIROFISH / {{ $t('studio.brandSubtitle') }}</span><span>{{ $t('studio.footer') }}</span></footer>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, inject, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import PreferenceControls from '../components/PreferenceControls.vue'
import WebSources from '../components/WebSources.vue'
import WorkflowExplorer from '../components/WorkflowExplorer.vue'
import ExplorationJourney from '../components/ExplorationJourney.vue'
import { setPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { useSourceCollection } from '../composables/useSourceCollection'

const router = useRouter()
const { t, tm } = useI18n()
const systemStatus = inject('systemStatus', ref(null))
const statusError = inject('systemStatusError', ref(false))
const statusBusy = inject('systemStatusBusy', ref(false))
const refreshStatus = inject('refreshSystemStatus', () => {})
const connection = configured => t(statusError.value ? 'settings.unreachable' : !systemStatus.value ? 'studio.checking' : configured ? 'studio.connected' : 'studio.needsSetup')
const readinessTitle = computed(() => {
  if (statusError.value) return t('settings.unreachable')
  if (!systemStatus.value) return t('studio.checkingTitle')
  if (systemStatus.value.ready) return t('home.systemReady')
  return systemStatus.value.llm_configured ? t('studio.analysisReady') : t('studio.modelPending')
})
const readinessDescription = computed(() => {
  if (statusError.value) return t('studio.serviceError')
  if (!systemStatus.value) return t('studio.checkingDesc')
  if (systemStatus.value.ready) return t('home.systemReadyDesc')
  return systemStatus.value.llm_configured
    ? t('studio.analysisReadyDesc')
    : t('studio.modelPendingDesc')
})

// 表单数据
const formData = ref({
  simulationRequirement: ''
})

// 文件列表
const files = ref([])

// 状态
const loading = ref(false)
const sourceCollection = useSourceCollection()
let mounted = true
onUnmounted(() => { mounted = false })
const error = ref('')
const fileFeedback = ref('')
const isDragOver = ref(false)
const totalSize = computed(() => files.value.reduce((sum, file) => sum + file.size, 0))
const formatSize = size => size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`
const availableFiles = computed(() => [...files.value, ...sourceCollection.getFiles()])
const submitHelp = computed(() => {
  if (sourceCollection.busy) return t(`sources.simple.${sourceCollection.phase || 'checking'}`)
  if (!files.value.length && !sourceCollection.urls.length) return t('sources.simple.needSources')
  if (!formData.value.simulationRequirement.trim()) return t('quality.needGoal')
  return t(sourceCollection.urls.length ? 'sources.simple.startHelp' : 'studio.startHelp')
})
const startLabel = computed(() => t(loading.value ? sourceCollection.busy ? 'sources.simple.preparing' : 'home.initializing'
  : sourceCollection.uncertain ? 'sources.simple.checkResult'
  : ['upstream', 'timeout', 'too_large', 'empty', 'page_error', 'storage', 'plan_expired'].includes(sourceCollection.errorCode) && sourceCollection.pendingUrls.length ? 'sources.simple.retry' : 'studio.start'))
const useExample = index => {
  formData.value.simulationRequirement = tm('quality.examples')[index].prompt
  document.getElementById('simulation-goal')?.focus()
}

// 文件输入引用
const fileInput = ref(null)

// 计算属性:是否可以提交
const canSubmit = computed(() => {
  return !sourceCollection.busy && formData.value.simulationRequirement.trim() !== '' && (files.value.length > 0 || sourceCollection.urls.length > 0)
})

// 触发文件选择
const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

// 处理文件选择
const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
  // Allow selecting the same file again after removing it.
  event.target.value = ''
}

// 处理拖拽相关
const handleDragOver = (e) => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = (e) => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  
  const droppedFiles = Array.from(e.dataTransfer.files)
  addFiles(droppedFiles)
}

// 添加文件
const addFiles = (newFiles) => {
  if (loading.value) return
  const messages = new Set()
  for (const file of newFiles) {
    const ext = file.name.match(/^.+\.([^.]+)$/)?.[1].toLowerCase()
    if (!['pdf', 'md', 'markdown', 'txt'].includes(ext)) { messages.add(t('quality.unsupportedFile')); continue }
    if (!file.size) { messages.add(t('quality.emptyFile')); continue }
    if (files.value.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) { messages.add(t('quality.duplicateFile')); continue }
    // Leave room for the form fields within the server's 50 MiB request limit.
    if (totalSize.value + file.size > 49 * 1024 * 1024) { messages.add(t('quality.largeFiles')); continue }
    files.value.push(file)
  }
  fileFeedback.value = [...messages].join(' ')
}

// 移除文件
const removeFile = (index) => {
  files.value.splice(index, 1)
  fileFeedback.value = ''
}

// 滚动到底部
const scrollToBottom = () => {
  document.getElementById('history-heading')?.focus({ preventScroll: true })
  document.getElementById('project-history')?.scrollIntoView({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
}

// One explicit action prepares sources, then enters the existing analysis flow.
const startSimulation = async (useAvailable = false) => {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    if (!useAvailable && !await sourceCollection.prepare()) {
      await nextTick()
      if (mounted && router.currentRoute.value.name === 'Home') document.querySelector('.sources-error')?.focus()
      return
    }
    // Settings keeps this draft mounted. Finishing in the background must not
    // interrupt the user's current page or trigger an analysis behind it.
    if (!mounted || router.currentRoute.value.name !== 'Home') return
    const prepared = availableFiles.value
    if (!prepared.length) return
    if (prepared.reduce((sum, file) => sum + file.size, 0) > 49 * 1024 * 1024) {
      error.value = t('quality.largeFiles')
      return
    }
    setPendingUpload(prepared, formData.value.simulationRequirement)
    const navigationFailure = await router.push({
      name: 'Process',
      params: { projectId: 'new' }
    })
    if (navigationFailure) { clearPendingUpload(); error.value = t('quality.startFailed') }
  } catch {
    clearPendingUpload()
    error.value = t('quality.startFailed')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.home-container { --workspace-gap: 40px; --group-gap: 24px; --control-gap: 8px; min-height: 100dvh; background: var(--studio-paper); color: var(--studio-ink); font-family: var(--studio-font); }
.studio-navbar { display: flex; align-items: center; justify-content: space-between; padding: 14px max(24px, calc((100vw - 1120px) / 2)); gap: 24px; background: var(--studio-surface); border-bottom: 1px solid var(--studio-line); }
.studio-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--studio-ink); font-size: 18px; font-weight: 800; letter-spacing: 1.4px; }
.studio-brand small { display: block; margin-top: 2px; color: var(--studio-muted); font-size: 11px; font-weight: 400; letter-spacing: .4px; }
.brand-mark { display: grid; place-items: center; width: 36px; height: 36px; background: var(--studio-button); color: var(--theme-on-filled); border-radius: 10px; font-size: 29px; letter-spacing: 0; }
.studio-nav-links { display: flex; align-items: center; gap: 16px; }
.history-link { min-height: 44px; display: inline-flex; align-items: center; font-size: .875rem; font-weight: 500; color: var(--studio-muted); text-decoration: none; }
.history-link { border: 0; background: none; padding: 8px 0; }
.history-link:hover { color: var(--studio-accent); }
.studio-home-main { max-width: 1168px; margin: 0 auto; padding: 32px 24px 20px; }
.studio-intro { margin-bottom: 28px; }
.studio-intro h1 { margin: 0; font-size: clamp(2rem, 3.2vw, 2.5rem); line-height: 1.3; letter-spacing: -.02em; font-weight: 700; text-wrap: balance; }
.studio-intro p { margin: 10px 0 0; max-width: 65ch; font-size: 1rem; line-height: 1.75; color: var(--studio-muted); }
.studio-home-grid { display: grid; grid-template-columns: minmax(280px, 320px) minmax(0, 1fr); grid-template-areas: "journey form"; gap: var(--workspace-gap); align-items: start; }
.new-project-card { grid-area: form; min-width: 0; padding: 24px; border: 1px solid var(--studio-line); border-radius: 16px; background: var(--studio-surface); }
.project-inputs { display: grid; gap: var(--group-gap); }
.form-section { min-width: 0; }
.form-section-heading { display: flex; align-items: center; gap: var(--control-gap); margin: 0 0 12px; font-size: 1rem; font-weight: 700; line-height: 1.5; }
.form-section-heading > span { display: grid; place-items: center; width: 24px; height: 24px; flex-shrink: 0; border-radius: 7px; background: var(--studio-paper); color: var(--studio-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.goal-input { display: block; width: 100%; min-height: 112px; resize: vertical; border: 1px solid var(--theme-line-strong); border-radius: 9px; padding: 11px 13px; background: var(--studio-surface); color: var(--studio-ink); font: 1rem/1.7 var(--studio-font); }
.goal-input::placeholder { color: var(--studio-muted); }
.goal-examples { display: flex; flex-wrap: wrap; gap: var(--control-gap); margin-top: var(--control-gap); }
.goal-examples button { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 8px 10px; border: 1px solid var(--studio-line); border-radius: 7px; color: var(--studio-muted); background: transparent; font-size: .875rem; line-height: 1.65; text-align: left; }
.goal-examples button:hover { color: var(--studio-accent); border-color: var(--studio-accent); }
.goal-examples svg { width: 14px; height: 14px; flex-shrink: 0; stroke: currentColor; stroke-width: 1.4; }
.upload-zone { margin-top: 8px; border: 1px dashed var(--theme-line-strong); border-radius: 10px; }
.upload-zone.drag-over, .upload-zone:focus-within { border-color: var(--studio-accent); background: var(--studio-soft); }
.upload-select { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 56px; padding: 12px; border: 0; border-radius: 10px; background: none; color: var(--studio-ink); text-align: left; }
.upload-select:hover { background: var(--theme-surface-soft); }
.upload-symbol { flex: 0 0 24px; width: 24px; height: 24px; stroke: var(--studio-accent); stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.upload-title { font-size: .875rem; line-height: 1.65; font-weight: 600; }
.upload-hint { margin-left: auto; color: var(--studio-muted); font-size: .8125rem; line-height: 1.65; white-space: nowrap; }
.file-list { display: grid; gap: var(--control-gap); padding: 0 12px 12px; }
.file-item { display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--studio-line); padding-top: 6px; font-size: .875rem; }
.file-extension { color: var(--studio-muted); font-size: .75rem; }
.file-meta { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.file-meta small { display: block; color: var(--studio-muted); font-size: .8125rem; font-variant-numeric: tabular-nums; }
.remove-btn { flex-shrink: 0; min-width: 44px; min-height: 44px; border: 0; border-radius: 6px; background: none; color: var(--studio-muted); font-size: 22px; }
.remove-btn:hover { background: var(--studio-soft); color: var(--studio-accent); }
.file-feedback, .file-summary, .form-error { margin: 8px 0 0; font-size: .875rem; line-height: 1.7; }
.file-feedback { color: var(--studio-accent); }
.file-summary { color: var(--studio-green); }
.form-error { color: var(--studio-error); }
.project-submit-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-top: 1px solid var(--studio-line); margin-top: 20px; padding-top: 16px; }
.project-submit-row > p { flex: 1; margin: 0; font-size: .875rem; line-height: 1.7; color: var(--studio-muted); }
.submit-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; max-width: 100%; }
.start-engine-btn { display: inline-flex; justify-content: center; align-items: center; gap: 20px; min-height: 48px; min-width: 145px; padding: 12px 18px; border: 0; border-radius: 9px; background: var(--studio-button); color: var(--theme-on-filled); font-size: 1rem; line-height: 1.5; font-weight: 600; }
.start-engine-btn svg { width: 18px; height: 18px; flex-shrink: 0; stroke: currentColor; stroke-width: 1.5; }
.start-engine-btn:disabled { background: var(--theme-surface-soft); color: var(--studio-muted); }
.continue-sources-btn { min-height: 48px; padding: 10px 12px; border: 1px solid var(--studio-line); border-radius: 9px; color: var(--studio-ink); background: var(--studio-surface); font-size: .875rem; line-height: 1.65; }
.journey-panel { grid-area: journey; min-width: 0; padding: 20px 0 0; }
.workflow-details { margin-top: 20px; border-top: 1px solid var(--studio-line); }
.workflow-details > summary { min-height: 48px; padding: 13px 0; font-size: .875rem; line-height: 1.65; color: var(--studio-ink); cursor: pointer; }
.workflow-details :deep(.workflow-explorer) { border: 0; padding: 8px 0 0; background: transparent; }
.workspace-details { margin-top: 20px; border-bottom: 1px solid var(--studio-line); }
.workspace-details > summary { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; min-height: 52px; padding: 12px 0; cursor: pointer; font-size: 13px; color: var(--studio-muted); list-style: none; }
.workspace-details > summary > span:first-child::before { content: '+'; display: inline-block; width: 22px; color: var(--studio-accent); }
.workspace-details[open] > summary > span:first-child::before { content: '−'; }
.readiness-summary { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; }
.service-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--studio-muted); }
.service-dot.connected { background: var(--studio-green); }
.service-card { max-width: 640px; padding: 8px 0 20px; }
.service-card h2 { margin: 0 0 8px; font-size: 16px; }
.service-card > p { margin-bottom: 12px; font-size: 13px; line-height: 1.8; color: var(--studio-muted); }
.service-row { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; border-top: 1px solid var(--studio-line); padding: 10px 0; font-size: 13px; }
.service-row strong { font-size: 12px; font-weight: 600; color: var(--studio-accent); }
.service-row strong.connected { color: var(--studio-green); }
.service-retry { margin-top: 8px; min-height: 44px; padding: 8px 14px; border: 1px solid var(--studio-line); border-radius: 7px; background: var(--studio-surface); color: var(--studio-ink); }
.studio-history { scroll-margin-top: 20px; }
.studio-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px 20px; border-top: 1px solid var(--studio-line); margin-top: 28px; padding-top: 18px; color: var(--studio-muted); font-size: 11px; line-height: 1.8; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
@media (max-width: 959px) { .studio-home-grid { grid-template-columns: minmax(0, 1fr); grid-template-areas: "form" "journey"; gap: 32px; } .journey-panel { padding-top: 0; max-width: 540px; width: 100%; } .new-project-card { padding: 20px; } }
@media (max-width: 600px) {
  .studio-navbar { padding: 12px 16px; gap: 12px; flex-wrap: wrap; }
  .studio-brand { font-size: 16px; }
  .studio-nav-links { width: 100%; justify-content: space-between; gap: 8px; }
  .studio-home-main { padding: 20px 16px 16px; }
  .studio-intro { margin-bottom: 18px; }
  .new-project-card { padding: 18px 16px; }
  .project-submit-row { align-items: stretch; flex-direction: column; gap: 10px; }
  .submit-actions { flex-direction: column; }
  .upload-select { flex-wrap: wrap; }
  .upload-hint { white-space: normal; }
}
</style>
