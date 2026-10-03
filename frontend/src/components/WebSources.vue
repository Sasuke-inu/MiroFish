<template>
  <section class="web-sources" :aria-busy="collection.busy">
    <label class="sources-label" for="web-source-urls">{{ $t('sources.simple.urls') }}</label>
    <textarea id="web-source-urls" v-model="collection.urlText" rows="2" :placeholder="$t('sources.placeholder')"
      :disabled="disabled || collection.busy || collection.uncertain" :aria-invalid="collection.errorCode === 'invalid_url' || collection.errorCode === 'page_limit'"
      aria-describedby="web-source-help web-source-progress" spellcheck="false" autocapitalize="off" />
    <p id="web-source-help" class="sources-help">{{ $t('sources.simple.help', { pages: collection.maxPages }) }}</p>
    <p id="web-source-progress" class="sources-progress" role="status" aria-atomic="true">
      <template v-if="collection.busy">{{ $t(`sources.simple.${collection.phase || 'checking'}`) }}</template>
      <template v-else-if="collection.documents.length">{{ $t('sources.simple.ready', { count: collection.documents.length, total: collection.urls.length }) }}</template>
      <template v-else-if="collection.urls.length">{{ $t('sources.simple.queued', { count: collection.urls.length }) }}</template>
    </p>
    <div v-if="collection.errorCode" class="sources-error" role="alert" tabindex="-1">
      <p>{{ $t(collection.uncertain ? 'sources.simple.uncertain' : `sources.errors.${collection.errorCode}`) }}</p>
      <p v-if="!collection.uncertain && collection.documents.length">{{ $t('sources.simple.partial') }}</p>
      <ul v-if="!collection.uncertain && collection.pendingUrls.length" class="pending-sources"><li v-for="url in collection.pendingUrls" :key="url">{{ url }}</li></ul>
    </div>
    <details v-if="collection.documents.length" class="source-results">
      <summary>{{ $t('sources.simple.details', { count: collection.documents.length }) }}</summary>
      <article v-for="doc in collection.documents" :key="doc.id" class="source-document">
        <h4>{{ doc.title }}</h4>
        <a :href="safeUrl(doc.url)" target="_blank" rel="noopener noreferrer">{{ doc.url }} ↗</a>
        <p class="sources-help">{{ $t('sources.documentInfo', { chars: (doc.chars ?? doc.markdown.length).toLocaleString(), time: formatTime(doc.fetched_at) }) }} <span v-if="doc.cached">· {{ $t('sources.cache') }}</span></p>
        <p v-if="doc.truncated" class="sources-help">{{ $t('sources.truncated', { count: (collection.status?.max_chars_per_page ?? 8000).toLocaleString() }) }}</p>
        <details><summary>{{ $t('sources.showText') }}</summary><pre tabindex="0">{{ doc.markdown }}</pre></details>
      </article>
    </details>
    <details class="collection-policy">
      <summary>{{ $t('sources.simple.protection') }}</summary>
      <p class="sources-help">{{ $t('sources.simple.policy') }}</p>
      <p v-if="collection.status" class="sources-help">{{ $t('sources.limits', { pages: collection.maxPages, daily: collection.status.budget.daily_limit, remaining: collection.status.budget.remaining }) }}</p>
      <p v-if="collection.status && !collection.status.online" class="sources-help">{{ $t(collection.status.enabled && collection.status.configured ? 'sources.offlineCache' : 'sources.unavailable') }}</p>
      <button v-if="collection.statusError" type="button" class="sources-status-retry" :disabled="collection.checking" @click="collection.refreshStatus">{{ $t('sources.simple.retryStatus') }}</button>
    </details>
  </section>
</template>

<script setup>
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
const props = defineProps({ collection: { type: Object, required: true }, disabled: Boolean })
const { locale, t } = useI18n()
const formatTime = value => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? t('common.unknown') : date.toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' })
}
const safeUrl = value => /^https?:\/\//i.test(value) ? value : undefined
onMounted(() => props.collection.refreshStatus())
</script>

<style scoped>
.web-sources { min-width: 0; }
.sources-label { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; font-size: .875rem; line-height: 1.65; font-weight: 600; margin-bottom: 8px; }
textarea { display: block; width: 100%; resize: vertical; min-height: 80px; padding: 10px 13px; border: 1px solid var(--theme-line-strong); border-radius: 9px; background: var(--studio-surface); color: var(--studio-ink); font: 1rem/1.7 var(--studio-font); }
textarea::placeholder { color: var(--studio-muted); }
textarea:focus-visible, summary:focus-visible, button:focus-visible, pre:focus-visible { outline: 2px solid var(--studio-accent); outline-offset: 3px; }
textarea:disabled { opacity: .7; }
.sources-help { font-size: .875rem; color: var(--studio-muted); line-height: 1.75; margin-top: 7px; }
.sources-progress { font-size: .875rem; color: var(--studio-green); line-height: 1.75; }
.sources-progress:not(:empty) { margin-top: 8px; }
.sources-error { font-size: .875rem; line-height: 1.75; color: var(--studio-error); background: var(--theme-error-surface); border-radius: 8px; padding: 12px; margin-top: 12px; }
.pending-sources { padding-left: 18px; font-size: .8125rem; overflow-wrap: anywhere; }
summary { cursor: pointer; font-size: .875rem; line-height: 1.65; min-height: 44px; padding-block: 11px; color: var(--studio-muted); }
.source-results { margin-top: 12px; }
.source-document { padding: 12px; border: 1px solid var(--studio-line); border-radius: 8px; margin-top: 8px; }
h4 { font-size: 1rem; line-height: 1.5; overflow-wrap: anywhere; }
a { display: block; font-size: .875rem; line-height: 1.75; color: var(--studio-accent); overflow-wrap: anywhere; margin-top: 6px; }
pre { max-height: 240px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: .875rem/1.75 var(--studio-font); padding: 12px; background: var(--studio-paper); border-radius: 6px; }
.collection-policy { margin-top: 3px; }
button { min-height: 44px; color: var(--studio-ink); background: var(--studio-paper); border: 1px solid var(--studio-line); border-radius: 6px; padding: 8px 12px; }
</style>
