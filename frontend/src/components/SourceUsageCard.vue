<template>
  <section class="settings-card source-usage" aria-labelledby="sources-settings-heading" :aria-busy="busy">
    <div class="usage-heading"><div><h2 id="sources-settings-heading">{{ $t('sources.settingsTitle') }}</h2><p>{{ $t('sources.settingsHelp') }}</p></div><button type="button" :disabled="busy" @click="refresh">↻ {{ $t(busy ? 'studio.checking' : 'studio.refresh') }}</button></div>
    <p v-if="error" class="usage-error" role="alert">{{ $t('sources.errors.upstream') }}</p>
    <p v-if="busy" class="usage-note" role="status">{{ $t('common.loading') }}</p>
    <dl v-if="status">
      <div><dt>Firecrawl</dt><dd :class="{ online: status.online }">{{ $t(status.online ? 'sources.localConnected' : 'sources.offline') }}</dd></div>
      <div><dt>{{ $t('sources.cloudUsage') }}</dt><dd class="online">{{ $t('sources.zeroCredits') }}</dd></div>
      <div><dt>{{ $t('sources.jobLimit') }}</dt><dd>{{ $t('sources.pages', { count: status.max_pages_per_job }) }}</dd></div>
      <div><dt>{{ $t('sources.dailyUsage') }}</dt><dd>{{ $t('sources.usage', { used: status.budget.used, limit: status.budget.daily_limit, remaining: status.budget.remaining }) }}</dd></div>
      <div><dt>{{ $t('sources.cachePolicy') }}</dt><dd>{{ $t('sources.cacheHours', { count: status.cache_hours }) }}</dd></div>
    </dl>
    <p v-if="status" class="usage-note">{{ $t('sources.reset', { time: formatTime(status.budget.resets_at), zone: status.budget.timezone }) }}</p>
    <p class="usage-note">{{ $t('sources.scopeNote') }}</p>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSourceStatus } from '../api/sources'
const { locale, t } = useI18n()
const status = ref(null)
const busy = ref(false)
const error = ref(false)
const formatTime = time => {
  const date = new Date(time)
  if (Number.isNaN(date.getTime())) return t('common.unknown')
  try {
    return new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short', timeZone: status.value.budget.timezone }).format(date)
  } catch {
    return t('common.unknown')
  }
}
async function refresh() {
  if (busy.value) return
  busy.value = true
  error.value = false
  try { status.value = (await getSourceStatus()).data }
  catch { status.value = null; error.value = true }
  finally { busy.value = false }
}
onMounted(refresh)
</script>

<style scoped>
.source-usage { border: 1px solid var(--studio-line); border-radius: 15px; background: var(--studio-surface); padding: 24px; margin-bottom: 18px; }
.usage-heading { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 20px; }
h2 { font-size: 17px; font-weight: 600; }
.usage-heading p { color: var(--studio-muted); font-size: 14px; line-height: 1.8; margin-top: 6px; }
button { min-height: 44px; border: 1px solid var(--studio-line); background: var(--studio-surface); color: var(--studio-ink); border-radius: 8px; padding: 10px 13px; font-size: 13px; white-space: nowrap; }
button:focus-visible { outline: 2px solid var(--studio-accent); outline-offset: 3px; }
button:disabled { opacity: .55; cursor: wait; }
dl > div { display: flex; justify-content: space-between; align-items: baseline; gap: 18px; padding: 15px 0; border-top: 1px solid var(--studio-line); font-size: 14px; }
dt { flex-shrink: 0; }
dd { color: var(--studio-muted); font-size: 13px; text-align: right; line-height: 1.8; overflow-wrap: anywhere; }
dd.online { color: var(--studio-green); }
.usage-note { color: var(--studio-muted); font-size: 13px; line-height: 1.8; margin-top: 13px; }
.usage-error { color: var(--studio-error); font-size: 14px; margin-bottom: 12px; }
@media (max-width: 600px) { .source-usage { padding: 18px; } .usage-heading { flex-wrap: wrap; gap: 12px; } dl > div { flex-wrap: wrap; gap: 4px 14px; } dd { text-align: left; } }
</style>
