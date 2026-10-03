<template>
  <a class="skip-link" :href="isSettings ? '#settings-content' : '#workspace-content'" @click.prevent="focusContent">{{ $t('quality.skipContent') }}</a>
  <aside v-if="statusError" class="setup-notice" role="alert">
    {{ $t('studio.serviceError') }}
  </aside>
  <aside v-else-if="status && !status.ready" class="setup-notice" role="status">
    <template v-if="!status.llm_configured">{{ $t('studio.modelNotice') }}</template>
    <template v-else>{{ $t('studio.serviceStarted') }}</template>
    <template v-if="!status.graph_configured">
      {{ $t('studio.graphNotice') }}
    </template>
  </aside>
  <RouterView v-if="workspaceRoute" :route="workspaceRoute" v-slot="{ Component }">
    <component :is="Component" :key="workspaceKey" v-show="!isSettings" />
  </RouterView>
  <SettingsView v-if="isSettings" />
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, ref, shallowRef, watch, onMounted, onUnmounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import service from './api'
import { initializeAppearance } from './store/appearance'

const SettingsView = defineAsyncComponent(() => import('./views/SettingsView.vue'))
const status = ref(null)
const statusError = ref(false)
const statusBusy = ref(false)
const route = useRoute()
const { t, locale } = useI18n()
const isSettings = computed(() => route.name === 'Settings')
const focusContent = () => {
  const content = document.getElementById(isSettings.value ? 'settings-content' : 'workspace-content')
  content?.focus({ preventScroll: true })
  content?.scrollIntoView({ block: 'start' })
}
const workspaceRoute = shallowRef(null)
const workspaceKey = computed(() => `${workspaceRoute.value?.name || ''}:${JSON.stringify(workspaceRoute.value?.params || {})}`)
let workspaceScroll = 0
let settingsWereOpen = false
// Settings keep the current workspace mounted, including uploads and chats.
watch(() => [route.fullPath, route.name], () => {
  if (isSettings.value) {
    if (!settingsWereOpen) {
      workspaceScroll = window.scrollY
      nextTick(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    }
  } else {
    workspaceRoute.value = { ...route }
    if (settingsWereOpen) nextTick(() => window.scrollTo({ top: workspaceScroll, behavior: 'instant' }))
  }
  settingsWereOpen = isSettings.value
}, { immediate: true })
const stopAppearance = initializeAppearance()
onUnmounted(stopAppearance)
provide('systemStatus', status)
provide('systemStatusBusy', statusBusy)
provide('systemStatusError', statusError)
provide('refreshSystemStatus', refreshSystemStatus)
async function refreshSystemStatus() {
  if (statusBusy.value) return
  statusBusy.value = true
  statusError.value = false
  try {
    const response = await service.get('/api/system/status', { timeout: 10000 })
    status.value = response.data
  } catch {
    statusError.value = true
    status.value = null
  } finally {
    statusBusy.value = false
  }
}
onMounted(refreshSystemStatus)
watch([() => route.name, locale], () => {
  const names = { Home: 'studio.workspace', Workbench: 'research.title', Settings: 'settings.title', Process: 'studio.step1Title', Simulation: 'studio.step2Title', SimulationRun: 'studio.step3Title', Report: 'studio.step4Title', Interaction: 'studio.step5Title', NotFound: 'quality.notFoundTitle' }
  document.title = `${t(names[route.name] || 'studio.workspace')} · MiroFish`
}, { immediate: true })
</script>

<style>
.setup-notice {
  padding: 14px 24px;
  background: var(--theme-warning-surface, #fff4db);
  border-bottom: 1px solid var(--theme-warning-line, #dbaf64);
  color: var(--theme-warning-ink, #543707);
  font-family: system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.7;
}
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'Segoe UI', 'Microsoft JhengHei', 'PingFang TC', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--theme-ink, #000000);
  background-color: var(--theme-surface, #ffffff);
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--theme-surface-soft, #f1f1f1);
}

::-webkit-scrollbar-thumb {
  background: var(--theme-surface-filled, #000000);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--theme-surface-filled, #333333);
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}
</style>
