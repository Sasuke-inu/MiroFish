<template>
  <div class="provider-settings" :aria-busy="loading">
    <div v-if="loading" class="provider-placeholder" role="status">{{ $t('providers.loading') }}</div>
    <div v-else-if="!snapshot" class="provider-placeholder">
      <p role="alert">{{ error }}</p><button type="button" @click="load">{{ $t('providers.retry') }}</button>
    </div>
    <template v-else>
      <div class="provider-heading"><div><p class="eyebrow">{{ $t('providers.connectionEyebrow') }}</p><h2 id="provider-heading">{{ $t('providers.title') }}</h2><p>{{ $t('providers.description') }}</p></div><span class="state-pill" :class="{ ready: snapshot.has_api_key }">{{ $t(snapshot.has_api_key ? 'providers.configured' : 'providers.needsSetup') }}</span></div>
      <div class="provider-layout">
        <form class="provider-form" aria-labelledby="provider-heading" @submit.prevent="save">
          <fieldset :disabled="working"><legend class="sr-only">{{ $t('providers.title') }}</legend>
            <label class="field-label" for="provider-choice">{{ $t('providers.provider') }}</label>
            <select id="provider-choice" v-model="draft.provider" @change="changeProvider"><option v-for="preset in presets" :key="preset.id" :value="preset.id">{{ preset.id === 'custom' ? $t('providers.customProvider') : preset.label }}</option></select>
            <p class="field-help">{{ $t(draft.provider === 'ninerouter' ? 'providers.routerHelp' : draft.provider.startsWith('opencode') ? 'providers.opencodeHelp' : 'providers.compatibleHelp') }}</p>

            <label class="field-label" for="provider-endpoint">{{ $t('providers.endpoint') }}</label>
            <input id="provider-endpoint" v-model.trim="draft.base_url" type="url" spellcheck="false" autocomplete="off" required placeholder="https://api.example.com/v1" />
            <p class="field-help">{{ $t('providers.endpointHelp') }}</p>

            <div class="field-heading"><label class="field-label" for="provider-key">{{ $t('providers.apiKey') }}</label><span v-if="canReuseKey" class="key-stored">{{ $t('providers.keyStored') }}</span></div>
            <div class="secret-field"><input id="provider-key" v-model="draft.api_key" :type="showKey ? 'text' : 'password'" autocomplete="off" data-1p-ignore data-lpignore="true" data-form-type="other" spellcheck="false" :placeholder="$t(canReuseKey ? 'providers.keepKey' : 'providers.enterKey')" /><button type="button" :aria-pressed="showKey" @click="showKey = !showKey">{{ $t(showKey ? 'providers.hide' : 'providers.show') }}</button></div>
            <p class="field-help" :class="{ warning: endpointChanged }">{{ $t(endpointChanged ? 'providers.changedEndpoint' : 'providers.keyHelp') }}</p>

            <div class="field-heading"><label class="field-label" for="provider-model">{{ $t('providers.model') }}</label><button type="button" class="text-button" :disabled="!canTest" @click="testConnection">{{ $t(testing ? 'providers.testing' : 'providers.loadModels') }}</button></div>
            <input id="provider-model" v-model.trim="draft.model" list="provider-models" required spellcheck="false" autocomplete="off" :placeholder="$t('providers.modelPlaceholder')" />
            <datalist id="provider-models"><option v-for="model in usableModels" :key="model.id" :value="model.id" /></datalist>
            <p class="field-help">{{ $t('providers.modelHelp') }}</p>
            <div v-if="testResult" class="connection-result" role="status"><strong>{{ $t('providers.testConnected', { count: testResult.models?.length || 0 }) }}</strong><p>{{ $t('providers.testScope') }}</p><p v-if="modelAvailable === false" class="warning">{{ $t('providers.modelMissing') }}</p><p v-if="blockedModels">{{ $t('providers.filteredModels', { count: blockedModels }) }}</p></div>

            <details v-if="draft.provider === 'ninerouter'" class="router-auth" :open="authExpanded">
              <summary>{{ $t('providers.routerBalanceTitle') }}<span>{{ $t(snapshot.has_balance_api_key && canReuseKey ? 'providers.linked' : 'providers.optional') }}</span></summary>
              <p class="field-help">{{ $t('providers.routerBalanceHelp') }}</p>
              <label class="field-label" for="router-balance-key">{{ $t('providers.balanceKey') }}</label>
              <input id="router-balance-key" v-model="draft.balance_api_key" type="password" autocomplete="off" data-1p-ignore data-lpignore="true" data-form-type="other" spellcheck="false" :placeholder="$t(snapshot.has_balance_api_key && canReuseKey ? 'providers.keepKey' : 'providers.enterBalanceKey')" />
              <p class="field-help">{{ $t('providers.balanceKeyHelp') }}</p>
              <div class="field-heading"><label class="field-label" for="router-account">{{ $t('providers.account') }}</label><button type="button" class="text-button" :disabled="dirty || accountsBusy || !snapshot.has_balance_api_key" @click="loadAccounts">{{ $t(accountsBusy ? 'providers.loading' : 'providers.loadAccounts') }}</button></div>
              <select id="router-account" v-model="draft.balance_account_id"><option value="">{{ $t('providers.chooseAccount') }}</option><option v-if="draft.balance_account_id && !accounts.some(a => a.id === draft.balance_account_id)" :value="draft.balance_account_id">{{ $t('providers.savedAccount') }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name || account.id }}{{ account.is_active === false ? ` · ${$t('providers.inactive')}` : '' }}</option></select>
              <p class="field-help">{{ $t('providers.saveBeforeAccounts') }}</p>
              <p v-if="accountsLoaded && !accounts.length" class="field-help">{{ $t('providers.noAccounts') }}</p>
              <button v-if="snapshot.has_balance_api_key && !endpointChanged" type="button" class="text-button disconnect-button" :disabled="dirty || working" @click="disconnectBalance">{{ $t('providers.disconnectBalance') }}</button>
            </details>
          </fieldset>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <p v-if="savedMessage" class="saved-message" role="status">{{ $t('providers.saved') }}</p>
          <footer class="save-bar"><div><span class="change-dot" :class="{ changed: dirty }" aria-hidden="true"></span>{{ $t(dirty ? 'providers.unsaved' : 'providers.upToDate') }}</div><div class="save-actions"><button type="button" :disabled="!dirty || working" @click="resetDraft">{{ $t('providers.discard') }}</button><button class="primary" type="submit" :disabled="!dirty || working || !validDraft">{{ $t(saving ? 'providers.saving' : 'providers.save') }}</button></div></footer>
        </form>
        <aside class="provider-aside" :aria-label="$t('providers.balanceTitle')">
          <section class="balance-card"><div class="balance-heading"><span class="eyebrow">{{ $t('providers.balanceEyebrow') }}</span><button type="button" class="icon-button" :disabled="balanceBusy || dirty" :aria-label="$t('providers.refreshBalance')" @click="refreshBalance">↻</button></div><h3>{{ $t('providers.balanceTitle') }}</h3><p class="field-help">{{ $t('providers.balanceSavedOnly') }}</p>
            <p v-if="balanceBusy" class="balance-placeholder" role="status">{{ $t('providers.loading') }}</p>
            <p v-else-if="balanceError" class="form-error" role="alert">{{ balanceError }}</p>
            <template v-else-if="balance">
              <template v-if="balance.supported && ['wallet','key_allowance'].includes(balance.kind)"><p class="balance-value">{{ money(balance.remaining, balance.currency) }}</p><p class="balance-label">{{ $t(balance.kind === 'wallet' ? 'providers.wallet' : 'providers.allowance') }}</p><p v-if="balance.kind === 'key_allowance' && balance.remaining == null" class="field-help">{{ $t('providers.noLimit') }}</p><p v-if="balance.status === 'stale'" class="balance-warning">{{ $t('providers.stale') }}</p></template>
              <p v-else-if="!balance.supported" class="balance-placeholder">{{ $t(balance.status === 'authorization_required' ? 'providers.authorizationRequired' : balance.status === 'account_required' ? 'providers.accountRequired' : 'providers.balanceUnsupported') }}</p>
              <div v-for="quota in balance.quotas || []" :key="quota.id" class="quota-row"><div><span>{{ quotaLabel(quota.id) }}</span><strong>{{ quota.remaining_percent == null ? '—' : `${Math.round(quota.remaining_percent)}%` }}</strong></div><progress v-if="quota.remaining_percent != null" max="100" :value="Math.max(0, Math.min(100, quota.remaining_percent))" :aria-label="`${quotaLabel(quota.id)} ${$t('providers.remaining')}`"></progress><p v-if="quota.resets_at" class="field-help">{{ $t('providers.resetsAt', { time: formatTime(quota.resets_at) }) }}</p></div>
              <p v-if="balance.supported && balance.message" class="field-help balance-message">{{ balance.message }}</p>
              <p v-if="balance.supported && balance.checked_at" class="balance-timestamp">{{ $t('providers.updatedAt', { time: formatTime(balance.checked_at) }) }}</p>
            </template>
            <p v-if="dirty" class="balance-warning">{{ $t('providers.saveBeforeBalance') }}</p>
          </section>
          <section class="connection-guide"><span class="guide-icon" aria-hidden="true">↗</span><h3>{{ $t('providers.guideTitle') }}</h3><p>{{ $t('providers.guideBody') }}</p><div class="mini-flow" aria-hidden="true"><span>01</span><i></i><span>02</span><i></i><span>03</span></div><p class="field-help">{{ $t('providers.guideSteps') }}</p></section>
          <p class="provider-privacy">{{ $t('providers.storageNote') }}</p>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getProviderSettings, saveProviderSettings, testProviderSettings, getProviderBalance, getProviderAccounts } from '../api/providers'
const emit = defineEmits(['dirty'])
const { t, locale } = useI18n()
const refreshStatus = inject('refreshSystemStatus', () => {})
const loading = ref(true), saving = ref(false), testing = ref(false), error = ref(''), savedMessage = ref(false)
const snapshot = ref(null), presets = ref([]), showKey = ref(false), testResult = ref(null), testedSignature = ref('')
const balance = ref(null), balanceBusy = ref(false), balanceError = ref('')
const accounts = ref([]), accountsBusy = ref(false), accountsLoaded = ref(false), authExpanded = ref(false)
let balanceGeneration = 0, accountsGeneration = 0
const draft = reactive({ provider: '', base_url: '', model: '', api_key: '', balance_api_key: '', balance_account_id: '' })
const canonical = url => String(url || '').trim().replace(/\/+$/, '')
const signature = () => JSON.stringify(draft)
const connectionSignature = () => JSON.stringify([draft.provider, draft.base_url, draft.api_key])
const savedDraft = computed(() => ({ provider: snapshot.value?.provider || '', base_url: snapshot.value?.base_url || '', model: snapshot.value?.model || '', api_key: '', balance_api_key: '', balance_account_id: snapshot.value?.balance_account_id || '' }))
const dirty = computed(() => !!snapshot.value && signature() !== JSON.stringify(savedDraft.value))
const endpointChanged = computed(() => !!snapshot.value && (draft.provider !== snapshot.value.provider || canonical(draft.base_url) !== canonical(snapshot.value.base_url)))
const canReuseKey = computed(() => !!snapshot.value?.has_api_key && !endpointChanged.value)
const validDraft = computed(() => !!draft.provider && !!draft.base_url && !!draft.model && (!!draft.api_key.trim() || canReuseKey.value))
const working = computed(() => saving.value || testing.value)
const canTest = computed(() => !!draft.base_url && (!!draft.api_key.trim() || canReuseKey.value) && !working.value)
const usableModels = computed(() => (testResult.value?.models || []).filter(m => m.compatible !== false))
const blockedModels = computed(() => (testResult.value?.models || []).length - usableModels.value.length)
const modelAvailable = computed(() => testResult.value && draft.model ? usableModels.value.some(m => m.id === draft.model) : null)
function resetDraft() { Object.assign(draft, savedDraft.value); error.value = ''; savedMessage.value = false; showKey.value = false }
function apply(data) {
  balanceGeneration++; accountsGeneration++
  balanceBusy.value = false; accountsBusy.value = false; balance.value = null; balanceError.value = ''
  accounts.value = []; accountsLoaded.value = false
  snapshot.value = data.config; if (data.presets) presets.value = data.presets; resetDraft()
}
async function load() {
  loading.value = true; error.value = ''
  try { apply(await getProviderSettings()); loading.value = false; await Promise.all([refreshBalance(), snapshot.value.has_balance_api_key ? loadAccounts() : Promise.resolve()]) }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}
function changeProvider() {
  const preset = presets.value.find(p => p.id === draft.provider)
  draft.base_url = preset?.base_url || ''; draft.model = ''; draft.api_key = ''; draft.balance_api_key = ''; draft.balance_account_id = ''
  showKey.value = false; accounts.value = []; accountsLoaded.value = false
}
function payload() {
  return { provider: draft.provider, base_url: draft.base_url, model: draft.model, ...(draft.api_key ? { api_key: draft.api_key } : {}), ...(draft.provider === 'ninerouter' ? { balance_account_id: draft.balance_account_id, ...(draft.balance_api_key ? { balance_api_key: draft.balance_api_key } : {}) } : {}) }
}
async function testConnection() {
  if (!canTest.value) return
  testing.value = true; error.value = ''; testResult.value = null; const sent = connectionSignature()
  try { const result = await testProviderSettings(payload()); if (sent === connectionSignature()) { testResult.value = result; testedSignature.value = sent } }
  catch (e) { error.value = e.message }
  finally { testing.value = false }
}
async function save() {
  if (working.value || !validDraft.value || !dirty.value) return
  saving.value = true; error.value = ''; savedMessage.value = false
  try { apply(await saveProviderSettings(payload())); savedMessage.value = true; await Promise.all([refreshBalance(), Promise.resolve(refreshStatus()), snapshot.value.has_balance_api_key ? loadAccounts() : Promise.resolve()]) }
  catch (e) { error.value = e.message }
  finally { saving.value = false }
}
async function refreshBalance() {
  if (balanceBusy.value || dirty.value) return
  const generation = ++balanceGeneration
  balanceBusy.value = true; balanceError.value = ''
  try { const result = await getProviderBalance(); if (generation === balanceGeneration) balance.value = result }
  catch (e) { if (generation === balanceGeneration) { balance.value = null; balanceError.value = e.message } }
  finally { if (generation === balanceGeneration) balanceBusy.value = false }
}
async function loadAccounts() {
  if (accountsBusy.value || dirty.value || !snapshot.value?.has_balance_api_key) return
  const generation = ++accountsGeneration
  accountsBusy.value = true
  try { const result = await getProviderAccounts(); if (generation === accountsGeneration) { accounts.value = result.accounts || []; accountsLoaded.value = true } }
  catch (e) { if (generation === accountsGeneration) error.value = e.message }
  finally { if (generation === accountsGeneration) accountsBusy.value = false }
}
async function disconnectBalance() {
  if (dirty.value || working.value) return
  saving.value = true; error.value = ''
  try {
    apply(await saveProviderSettings({ clear_balance_authorization: true, expected_provider: snapshot.value.provider, expected_base_url: snapshot.value.base_url }))
    accounts.value = []; accountsLoaded.value = false; savedMessage.value = true
    await refreshBalance()
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}
function money(value, currency = 'USD') {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  try { return new Intl.NumberFormat(locale.value, { style: 'currency', currency: currency || 'USD', currencyDisplay: 'code', maximumFractionDigits: 2 }).format(value) } catch { return '—' }
}
function formatTime(value) {
  const date = new Date(typeof value === 'number' ? value * 1000 : value)
  return Number.isNaN(date.getTime()) ? t('common.unknown') : new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
const quotaLabel = id => ['rolling', 'weekly', 'monthly'].includes(id) ? t(`providers.quota.${id}`) : id
function beforeUnload(event) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
watch(dirty, value => emit('dirty', value))
watch(() => [draft.provider, canonical(draft.base_url)], () => {
  draft.api_key = ''; draft.balance_api_key = ''; draft.balance_account_id = ''; showKey.value = false
  accountsGeneration++; accountsBusy.value = false
  accounts.value = []; accountsLoaded.value = false
}, { flush: 'sync' })
watch(signature, () => { savedMessage.value = false }, { flush: 'sync' })
watch(connectionSignature, () => { if (testedSignature.value !== connectionSignature()) testResult.value = null }, { flush: 'sync' })
onMounted(() => { load(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { window.removeEventListener('beforeunload', beforeUnload); draft.api_key = ''; draft.balance_api_key = '' })
defineExpose({ dirty })
</script>

<style scoped>
.provider-settings { min-width: 0; }
.provider-heading { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 24px; }
.eyebrow { font-size: 11px; font-weight: 750; letter-spacing: 1.5px; color: var(--studio-accent); }
h2 { font-size: 25px; letter-spacing: -.5px; margin: 8px 0; } h3 { font-size: 17px; line-height: 1.5; }
.provider-heading > div > p:last-child { color: var(--studio-muted); line-height: 1.8; font-size: 14px; max-width: 560px; }
.state-pill { flex-shrink: 0; font-size: 12px; border: 1px solid var(--studio-line); border-radius: 20px; padding: 7px 12px; margin-top: 10px; }
.state-pill.ready { color: var(--studio-green); background: var(--studio-success-soft); }
.provider-layout { display: grid; grid-template-columns: minmax(0, 1fr) 255px; gap: 22px; align-items: start; }
.provider-form, .balance-card { border: 1px solid var(--studio-line); background: var(--studio-surface); border-radius: 14px; overflow: hidden; }
fieldset { border: 0; min-width: 0; padding: 24px; }
.sr-only { position: absolute; width: 1px; height: 1px; clip-path: inset(50%); overflow: hidden; }
.field-label { display: block; font-size: 13px; font-weight: 700; margin: 22px 0 9px; } fieldset > .field-label:first-of-type { margin-top: 0; }
input, select { width: 100%; min-width: 0; border: 1px solid var(--theme-line-strong, var(--studio-line)); border-radius: 8px; background: var(--studio-paper); color: var(--studio-ink); padding: 12px; font-size: 14px; min-height: 46px; }
input::placeholder { color: var(--studio-muted); opacity: 1; } select { padding-right: 28px; }
.field-help { font-size: 12px; line-height: 1.85; color: var(--studio-muted); margin-top: 8px; overflow-wrap: anywhere; }
.field-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.key-stored { font-size: 11px; color: var(--studio-green); }
.secret-field { display: flex; align-items: center; border: 1px solid var(--theme-line-strong, var(--studio-line)); border-radius: 8px; background: var(--studio-paper); }
.secret-field input { border: none; background: transparent; }
.secret-field button { border: 0; background: transparent; flex-shrink: 0; color: var(--studio-muted); padding: 12px; font-size: 12px; min-height: 44px; }
button { border: 1px solid var(--studio-line); border-radius: 8px; background: var(--studio-surface); color: var(--studio-ink); padding: 11px 14px; min-height: 44px; font-size: 13px; }
button:disabled { opacity: .5; } .text-button { padding: 7px 0; border: 0; background: transparent; color: var(--studio-accent); font-size: 12px; }
.primary { background: var(--studio-button); border-color: var(--studio-button); color: var(--theme-on-filled); font-weight: 650; }
.primary:hover:not(:disabled) { background: var(--studio-button-hover); }
.connection-result { background: var(--studio-success-soft); color: var(--studio-green); padding: 14px; border-radius: 8px; font-size: 12px; line-height: 1.8; margin-top: 15px; }
.router-auth { margin-top: 25px; border-top: 1px solid var(--studio-line); padding-top: 17px; }
.disconnect-button { color: var(--studio-error); margin-top: 8px; }
summary { cursor: pointer; font-size: 13px; font-weight: 650; line-height: 1.8; padding: 6px 0; } summary span { float: right; color: var(--studio-muted); font-size: 11px; font-weight: 400; }
.save-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 17px 22px; border-top: 1px solid var(--studio-line); background: var(--studio-paper); font-size: 12px; color: var(--studio-muted); }
.save-bar > div:first-child { display: flex; align-items: center; gap: 7px; } .save-actions { display: flex; gap: 8px; }
.change-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--studio-muted); } .change-dot.changed { background: var(--studio-accent); }
.form-error, .saved-message { padding: 0 24px 16px; font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; } .form-error { color: var(--studio-error); } .saved-message { color: var(--studio-green); }
.provider-aside { min-width: 0; display: grid; gap: 18px; }
.balance-card { padding: 20px; } .balance-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.icon-button { font-size: 20px; padding: 4px 8px; min-width: 36px; min-height: 36px; border: 0; background: transparent; }
.balance-value { margin: 24px 0 5px; font-size: clamp(22px, 2vw, 30px); font-weight: 650; letter-spacing: -1px; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.balance-label { font-size: 12px; color: var(--studio-muted); } .balance-placeholder { font-size: 14px; line-height: 1.9; padding: 22px 0; color: var(--studio-muted); }
.balance-timestamp { font-size: 11px; border-top: 1px solid var(--studio-line); padding-top: 14px; margin-top: 18px; color: var(--studio-muted); line-height: 1.8; }
.balance-warning, .warning { color: var(--studio-accent); font-size: 12px; line-height: 1.8; margin-top: 12px; }
.balance-card .form-error { padding: 16px 0 0; }
.quota-row { margin-top: 20px; } .quota-row > div { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
progress { width: 100%; height: 6px; margin-top: 10px; accent-color: var(--studio-accent); border: 0; border-radius: 6px; overflow: hidden; } progress::-webkit-progress-bar { background: var(--studio-line); } progress::-webkit-progress-value { background: var(--studio-accent); }
.connection-guide { padding: 20px; background: var(--studio-soft); border: 1px solid var(--studio-line); border-radius: 14px; }
.guide-icon { display: inline-grid; place-items: center; width: 30px; height: 30px; border: 1px solid var(--studio-accent); color: var(--studio-accent); border-radius: 50%; margin-bottom: 16px; }
.connection-guide > p { font-size: 12px; line-height: 1.85; color: var(--studio-muted); margin-top: 9px; }
.mini-flow { display: flex; align-items: center; gap: 7px; margin-top: 22px; } .mini-flow span { display: grid; place-items: center; border: 1px solid var(--studio-line); background: var(--studio-surface); width: 30px; height: 30px; border-radius: 8px; font-size: 11px; color: var(--studio-accent); } .mini-flow i { flex: 1; height: 1px; background: var(--studio-line); }
.provider-privacy { color: var(--studio-muted); font-size: 11px; line-height: 1.9; padding: 0 5px; }
.provider-placeholder { border: 1px solid var(--studio-line); border-radius: 14px; padding: 32px; background: var(--studio-surface); line-height: 1.9; } .provider-placeholder button { margin-top: 16px; }
@media(max-width: 1150px) { .provider-layout { grid-template-columns: minmax(0, 1fr); } .provider-aside { grid-template-columns: repeat(2, minmax(0, 1fr)); } .provider-privacy { grid-column: 1 / -1; } }
@media(max-width: 560px) { .provider-heading { gap: 12px; flex-wrap: wrap; } h2 { font-size: 23px; } .provider-aside { grid-template-columns: 1fr; } fieldset { padding: 20px 16px; } .save-bar { flex-wrap: wrap; padding: 16px; } .save-actions { margin-left: auto; } .field-heading { flex-wrap: wrap; gap: 0 10px; } .key-stored { margin-bottom: 8px; } }
</style>
