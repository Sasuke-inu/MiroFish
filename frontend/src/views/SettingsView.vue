<template>
  <div class="settings-page">
    <header class="settings-navbar">
      <RouterLink to="/" class="settings-brand"><span aria-hidden="true">≈</span> MIROFISH</RouterLink>
      <button type="button" class="settings-back" @click="goBack">← {{ $t('settings.back') }}</button>
    </header>
    <main class="settings-main" id="settings-content" tabindex="-1">
      <div class="settings-intro">
        <p class="settings-eyebrow">{{ $t('settings.workspace') }}</p>
        <h1>{{ $t('settings.title') }}</h1>
        <p>{{ $t('settings.intro') }}</p>
      </div>
      <div class="settings-layout">
      <nav class="settings-index" :aria-label="$t('settings.title')">
        <p class="index-label">{{ $t('providers.controlPanel') }}</p>
        <button v-for="item in sections" :key="item.id" type="button" :aria-current="activeSection === item.id ? 'page' : undefined" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><span class="nav-icon" aria-hidden="true">{{ item.icon }}</span><span>{{ $t(item.label) }}</span><span v-if="item.id === 'models' && providerDirty" class="nav-dirty" :aria-label="$t('providers.unsaved')">•</span></button>
        <div class="settings-index-note"><span class="local-indicator" aria-hidden="true"></span><strong>{{ $t('providers.localWorkspace') }}</strong><p>{{ $t('providers.preferenceScope') }}</p></div>
      </nav>
      <div class="settings-sections">
      <section v-show="activeSection === 'models'" id="models-panel" aria-labelledby="provider-heading"><ProviderSettings @dirty="providerDirty = $event" /></section>
      <div v-show="activeSection === 'appearance'" id="appearance-panel">
      <section class="settings-card" aria-labelledby="appearance-heading">
        <div class="settings-section-heading"><div><h2 id="appearance-heading">{{ $t('settings.appearance') }}</h2><p>{{ $t('settings.appearanceHelp') }}</p></div><span class="setting-number" aria-hidden="true">01</span></div>
        <fieldset class="theme-choices">
          <legend class="settings-sr-only">{{ $t('settings.appearance') }}</legend>
          <label v-for="mode in modes" :key="mode" class="theme-choice" :class="{ selected: preference === mode }">
            <input type="radio" name="appearance" :value="mode" :checked="preference === mode" @change="setTheme(mode)" />
            <span class="theme-swatch" :class="`swatch-${mode}`" aria-hidden="true"><span class="swatch-sidebar"></span><span class="swatch-content"><i></i><i></i><i></i></span></span>
            <span class="theme-choice-heading">{{ $t(`settings.${mode}`) }}<span class="theme-check" aria-hidden="true">{{ preference === mode ? '✓' : '' }}</span></span>
            <span class="theme-choice-description">{{ $t(`settings.${mode}Help`) }}</span>
          </label>
        </fieldset>
        <p class="settings-saved" role="status">{{ $t(saved ? 'settings.saved' : 'settings.unsaved') }}</p>
      </section>
      <section class="settings-card language-settings" aria-labelledby="language-heading">
        <div class="settings-section-heading"><div><h2 id="language-heading">{{ $t('settings.language') }}</h2><p>{{ $t('settings.languageHelp') }}</p></div><span class="setting-number" aria-hidden="true">02</span></div>
        <LanguageSwitcher />
      </section>
      </div>
      <section v-show="activeSection === 'services'" id="services-panel" class="settings-card" aria-labelledby="services-heading">
        <div class="settings-section-heading"><div><h2 id="services-heading">{{ $t('settings.services') }}</h2><p>{{ $t('settings.servicesHelp') }}</p></div><button type="button" class="settings-refresh" :disabled="busy" @click="refresh">↻ {{ $t(busy ? 'studio.checking' : 'studio.refresh') }}</button></div>
        <p v-if="statusError" class="settings-error" role="alert">{{ $t('studio.serviceError') }}</p>
        <dl class="settings-services">
          <div><dt>{{ $t('studio.modelConnection') }}</dt><dd :class="{ available: status?.llm_configured }">{{ connection(status?.llm_configured) }}</dd></div>
          <div><dt>{{ $t(status?.graph_provider === 'graphiti' ? 'studio.localGraphConnection' : 'studio.graphConnection') }}</dt><dd :class="{ available: status?.graph_configured }">{{ connection(status?.graph_configured) }}</dd></div>
          <div v-if="status?.embedding === 'local'"><dt>{{ $t('settings.embedding') }}</dt><dd class="available">{{ $t('settings.localEmbedding') }}</dd></div>
        </dl>
        <p class="settings-service-note">{{ $t('settings.modelNote') }}</p>
      </section>
      <div v-show="activeSection === 'sources'" id="sources-panel"><div class="source-explanation"><span aria-hidden="true">◎</span><div><h2>{{ $t('providers.dataTitle') }}</h2><p>{{ $t('providers.dataHelp') }}</p></div></div><div id="source-settings"><SourceUsageCard /></div></div>
      </div>
      </div>
      <footer class="settings-footer">{{ $t('settings.localPreferences') }}</footer>
    </main>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import SourceUsageCard from '../components/SourceUsageCard.vue'
import ProviderSettings from '../components/ProviderSettings.vue'
import { useAppearance } from '../store/appearance'
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { preference, saved, setTheme } = useAppearance()
const modes = ['light', 'dark', 'system']
const activeSection = ref('models')
const providerDirty = ref(false)
const sections = [
  { id: 'models', label: 'providers.navTitle', icon: '⤴' },
  { id: 'appearance', label: 'providers.appearanceNav', icon: '◐' },
  { id: 'sources', label: 'providers.dataNav', icon: '◎' },
  { id: 'services', label: 'settings.services', icon: '◉' }
]
async function selectSection(id) {
  activeSection.value = id
  await nextTick()
  const panel = document.getElementById(`${id}-panel`)
  panel?.setAttribute('tabindex', '-1')
  panel?.focus({ preventScroll: true })
}
const removeGuard = router.beforeEach((to, from) => {
  if (from.name === 'Settings' && to.name !== 'Settings' && providerDirty.value) return window.confirm(t('providers.leaveConfirm'))
})
onBeforeUnmount(removeGuard)
const status = inject('systemStatus', ref(null))
const busy = inject('systemStatusBusy', ref(false))
const statusError = inject('systemStatusError', ref(false))
const refresh = inject('refreshSystemStatus', () => {})
const returnPath = computed(() => {
  const from = route.query.from
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) return '/'
  const resolved = router.resolve(from)
  return resolved.matched.length && !['Settings', 'NotFound'].includes(resolved.name) ? resolved.fullPath : '/'
})
const goBack = () => router.push(returnPath.value)
const connection = configured => t(statusError.value ? 'settings.unreachable' : busy.value || !status.value ? 'studio.checking' : configured ? 'studio.connected' : 'studio.needsSetup')
</script>

<style scoped>
.settings-page { min-height: 100dvh; background: var(--studio-paper); color: var(--studio-ink); font-family: var(--studio-font); }
.settings-navbar { padding: 18px max(28px, calc((100vw - 1100px) / 2)); background: var(--studio-surface); border-bottom: 1px solid var(--studio-line); display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.settings-brand { display: flex; gap: 11px; align-items: center; color: var(--studio-ink); text-decoration: none; font-size: 17px; font-weight: 800; letter-spacing: 1.7px; }
.settings-brand > span { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; background: var(--studio-button); color: #fff; font-size: 27px; }
.settings-back, .settings-refresh { border: 1px solid var(--studio-line); background: var(--studio-surface); color: var(--studio-muted); border-radius: 8px; padding: 9px 12px; font-size: 12px; white-space: nowrap; }
.settings-back:hover, .settings-refresh:hover:not(:disabled) { border-color: var(--studio-accent); color: var(--studio-accent); }
.settings-main { max-width: 880px; margin: 0 auto; padding: 36px 24px 28px; }
.settings-intro { margin-bottom: 24px; }
.settings-eyebrow { font-size: 11px; letter-spacing: 1.5px; font-weight: 600; color: var(--studio-accent); }
.settings-intro h1 { font-size: 32px; font-weight: 650; margin: 10px 0; }
.settings-intro > p:last-child { font-size: 14px; line-height: 1.8; color: var(--studio-muted); }
.settings-card { border: 1px solid var(--studio-line); border-radius: 15px; background: var(--studio-surface); padding: 24px; margin-bottom: 18px; }
.settings-section-heading { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 20px; }
.settings-section-heading h2 { font-size: 17px; font-weight: 600; }
.settings-section-heading p { color: var(--studio-muted); font-size: 12px; line-height: 1.8; margin-top: 6px; }
.setting-number { color: var(--studio-line); font-size: 28px; font-weight: 300; }
.theme-choices { border: none; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.theme-choice { position: relative; display: flex; flex-direction: column; padding: 12px; border: 1px solid var(--studio-line); border-radius: 11px; cursor: pointer; min-width: 0; }
.theme-choice.selected { border-color: var(--studio-accent); box-shadow: 0 0 0 1px var(--studio-accent); background: var(--studio-soft); }
.theme-choice:focus-within { outline: 3px solid var(--studio-accent); outline-offset: 3px; }
.theme-choice input, .settings-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.theme-swatch { height: 86px; display: flex; padding: 10px; gap: 8px; border-radius: 7px; border: 1px solid #dce1e4; background: #f7f6f2; }
.swatch-sidebar { background: #e0e7ec; width: 24%; border-radius: 4px; }
.swatch-content { flex: 1; display: flex; flex-direction: column; gap: 6px; padding-top: 2px; }
.swatch-content i { height: 11px; display: block; border-radius: 3px; background: #fff; border: 1px solid #e3e5e4; }
.swatch-content i:first-child { width: 60%; height: 5px; margin-bottom: 3px; background: #536d86; border: none; }
.swatch-dark { background: #101820; border-color: #354757; }
.swatch-dark .swatch-sidebar { background: #293e51; }
.swatch-dark .swatch-content i { background: #192a39; border-color: #354757; }
.swatch-dark .swatch-content i:first-child { background: #b3c7d8; }
.swatch-system { background: linear-gradient(115deg, #f7f6f2 50%, #101820 50%); border-color: #637989; }
.swatch-system .swatch-content i { background: linear-gradient(115deg, #fff 42%, #293e51 42%); border-color: #778896; }
.theme-choice-heading { font-size: 13px; font-weight: 600; margin-top: 13px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.theme-check { width: 18px; color: var(--studio-accent); }
.theme-choice-description { color: var(--studio-muted); font-size: 11px; line-height: 1.7; margin-top: 5px; }
.settings-saved { color: var(--studio-muted); font-size: 11px; margin-top: 18px; }
.language-settings { display: flex; justify-content: space-between; align-items: center; gap: 18px; }
.language-settings .settings-section-heading { margin: 0; }
.language-settings .setting-number { display: none; }
.settings-services > div { display: flex; justify-content: space-between; align-items: center; gap: 18px; padding: 13px 0; border-top: 1px solid var(--studio-line); font-size: 13px; }
.settings-services dd { color: var(--studio-accent); background: var(--studio-soft); border-radius: 6px; font-size: 11px; padding: 5px 9px; text-align: right; }
.settings-services dd.available { color: var(--studio-green); background: var(--studio-success-soft); }
.settings-service-note, .settings-footer { color: var(--studio-muted); font-size: 11px; line-height: 1.8; margin-top: 13px; }
.settings-footer { text-align: center; padding: 8px; }
.settings-error { color: var(--studio-error); margin-bottom: 16px; font-size: 12px; }
@media (max-width: 600px) { .settings-navbar { padding: 14px 18px; } .settings-main { padding: 26px 18px; } .settings-card { padding: 18px; } .theme-choices { gap: 8px; } .theme-choice { padding: 8px; } .theme-swatch { height: 65px; padding: 7px; gap: 5px; } .theme-choice-description { font-size: 10px; } .settings-services > div { font-size: 12px; } }
@media (max-width: 380px) { .theme-choices { grid-template-columns: 1fr; } .theme-choice { display: grid; grid-template-columns: 76px 1fr; column-gap: 12px; } .theme-swatch { grid-row: span 2; } .theme-choice-heading { margin-top: 6px; } .language-settings { align-items: flex-start; flex-direction: column; } }

.settings-main { max-width: 1160px; padding: 36px 28px; }
.settings-intro { margin-bottom: 32px; }
.settings-intro h1 { font-size: clamp(30px, 3vw, 40px); font-weight: 700; letter-spacing: -.8px; }
.settings-eyebrow { font-size: 12px; letter-spacing: .8px; }
.settings-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 40px; align-items: start; }
.settings-index { position: sticky; top: 24px; display: grid; gap: 8px; }
.settings-index a { display: flex; justify-content: space-between; gap: 12px; padding: 13px 14px; min-height: 48px; border-radius: 8px; text-decoration: none; font-size: 14px; color: var(--studio-ink); border: 1px solid var(--studio-line); }
.settings-index a:hover { background: var(--studio-soft); color: var(--studio-accent); border-color: var(--studio-accent); }
.settings-index a span { color: var(--studio-muted); }
.settings-index p { font-size: 12px; line-height: 1.9; color: var(--studio-muted); padding: 12px 2px; }
.settings-card { border-radius: 12px; padding: 26px; }
.settings-section-heading h2 { font-size: 19px; scroll-margin-top: 24px; }
.settings-section-heading p, .theme-choice-description { font-size: 13px; }
.settings-back, .settings-refresh { min-height: 44px; font-size: 13px; }
.theme-choice-heading { font-size: 14px; }
.theme-swatch { height: 94px; }
.settings-services > div { font-size: 14px; padding: 16px 0; }
.settings-services dd, .settings-saved, .settings-service-note, .settings-footer { font-size: 12px; line-height: 1.8; }
.setting-number { color: var(--studio-muted); font-size: 21px; }
#source-settings { scroll-margin-top: 24px; }
@media (max-width: 800px) {
  .settings-layout { grid-template-columns: 1fr; gap: 22px; }
  .settings-index { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .settings-index p { display: none; }
  .settings-main { padding: 26px 18px; }
  .settings-intro { margin-bottom: 24px; }
}
@media (max-width: 520px) {
  .settings-card { padding: 20px 16px; }
  .theme-choices { grid-template-columns: 1fr; gap: 12px; }
  .theme-choice { display: grid; grid-template-columns: 90px minmax(0, 1fr); column-gap: 14px; padding: 12px; }
  .theme-swatch { grid-row: span 2; height: 66px; }
  .theme-choice-heading { margin-top: 3px; }
  .theme-choice-description { font-size: 13px; margin-top: 3px; }
  .settings-section-heading { gap: 12px; flex-wrap: wrap; }
  .language-settings { align-items: flex-start; flex-direction: column; }
}
</style>

<style scoped>
.settings-navbar { padding-inline: max(28px, calc((100vw - 1376px) / 2)); }
.settings-brand > span { color: var(--theme-on-filled); }
.settings-main { max-width: 1440px; padding: 38px 32px 28px; }
.settings-intro { border-bottom: 1px solid var(--studio-line); padding-bottom: 26px; margin-bottom: 32px; }
.settings-intro h1 { font-size: 36px; letter-spacing: -1px; }
.settings-layout { grid-template-columns: 200px minmax(0, 1fr); gap: 40px; }
.settings-index { gap: 6px; }
.settings-index .index-label { padding: 0 14px 12px; font-size: 10px; font-weight: 750; letter-spacing: 1px; margin: 0; }
.settings-index > button { display: flex; align-items: center; gap: 12px; border: 1px solid transparent; background: transparent; color: var(--studio-muted); padding: 14px; min-height: 50px; border-radius: 9px; text-align: left; font-size: 13px; }
.settings-index > button.active { background: var(--studio-surface); border-color: var(--studio-line); color: var(--studio-ink); font-weight: 700; box-shadow: inset 3px 0 var(--studio-accent); }
.settings-index > button:hover { color: var(--studio-ink); background: var(--studio-surface); }
.nav-icon { color: var(--studio-accent); width: 20px; font-size: 18px; text-align: center; font-weight: 400; }
.nav-dirty { margin-left: auto; color: var(--studio-accent); }
.settings-index-note { margin: 30px 12px 0; padding-top: 20px; border-top: 1px solid var(--studio-line); font-size: 12px; line-height: 1.8; }
.settings-index-note strong { font-weight: 500; } .settings-index-note p { padding: 0; margin-top: 10px; font-size: 11px; }
.local-indicator { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 8px; background: var(--studio-green); }
.settings-sections { min-width: 0; } .settings-sections > [tabindex]:focus { outline: none; }
.settings-card { background: var(--studio-surface); }
.source-explanation { display: flex; gap: 18px; border: 1px solid var(--studio-line); background: var(--studio-soft); border-radius: 12px; padding: 24px; margin-bottom: 20px; }
.source-explanation > span { font-size: 25px; color: var(--studio-accent); } .source-explanation h2 { font-size: 19px; margin-bottom: 8px; }
.source-explanation p { font-size: 14px; color: var(--studio-muted); line-height: 1.9; max-width: 680px; }
.theme-swatch { border-color: #aaa392; background: #d5cec1; } .swatch-sidebar { background: #bab39f; } .swatch-content i { background: #e4ded2; border-color: #aaa392; } .swatch-content i:first-child { background: #805014; }
.swatch-dark { background: #1b1d19; border-color: #606154; } .swatch-dark .swatch-sidebar { background: #393c33; } .swatch-dark .swatch-content i { background: #33362e; border-color: #606154; } .swatch-dark .swatch-content i:first-child { background: #e8b869; }
.swatch-system { background: linear-gradient(115deg, #d5cec1 50%, #1b1d19 50%); border-color: #7c7a6a; } .swatch-system .swatch-content i { background: linear-gradient(115deg, #e4ded2 42%, #33362e 42%); border-color: #898674; }
.settings-footer { margin-top: 32px; }
@media(max-width: 900px) { .settings-layout { grid-template-columns: 1fr; gap: 26px; } .settings-index { position: static; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; } .settings-index > button { padding: 12px 9px; justify-content: center; font-size: 12px; } .settings-index > button.active { box-shadow: inset 0 -3px var(--studio-accent); } .settings-index .index-label, .settings-index-note { display: none; } .settings-main { padding: 28px 22px; } .settings-intro { margin-bottom: 20px; padding-bottom: 22px; } }
@media(max-width: 560px) { .settings-navbar { padding: 14px 18px; } .settings-main { padding: 25px 16px; } .settings-index { grid-template-columns: repeat(2, minmax(0, 1fr)); } .settings-index > button { justify-content: flex-start; padding: 10px 12px; font-size: 13px; } .settings-intro h1 { font-size: 30px; } .source-explanation { padding: 20px 16px; } }
</style>
