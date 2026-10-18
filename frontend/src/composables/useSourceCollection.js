import { computed, reactive, watch } from 'vue'
import { getSourceStatus, planSources, fetchSources } from '../api/sources'

// The server independently validates public DNS and enforces usage limits.
export function sourceUrl(value) {
  try {
    const url = new URL(value.trim())
    url.hash = ''
    return url.href
  } catch { return typeof value === 'string' ? value.trim() : '' }
}

const codes = new Set(['disabled', 'configuration', 'invalid_url', 'documents', 'page_limit', 'daily_limit', 'busy', 'plan_expired', 'upstream', 'timeout', 'too_large', 'empty', 'page_error', 'storage', 'origin', 'invalid_request'])
const errorCode = error => {
  const code = error?.response?.data?.code || (error?.code === 'ECONNABORTED' ? 'timeout' : 'upstream')
  return codes.has(code) ? code : 'upstream'
}

export function useSourceCollection() {
  const saved = new Map()
  let pendingPlan = null
  const state = reactive({
    urlText: '', busy: false, checking: false, status: null, statusError: false,
    phase: '', errorCode: '', uncertain: false, revision: 0,
    urls: computed(() => [...new Set(state.urlText.split(/\r?\n/).map(sourceUrl).filter(Boolean))]),
    documents: computed(() => {
      void state.revision
      return state.urls.map(url => saved.get(url)).filter(Boolean)
    }),
    pendingUrls: computed(() => state.urls.filter(url => !state.documents.some(doc => sourceUrl(doc.url) === url))),
    maxPages: computed(() => state.status?.max_pages_per_job ?? 3),
    refreshStatus, prepare, getFiles,
  })

  watch(() => state.urlText, () => {
    // Uncertain requests keep their original plan even if a caller edits the
    // draft programmatically. The UI locks the field until they are resolved.
    if (!pendingPlan) state.errorCode = ''
  }, { flush: 'sync' })

  async function refreshStatus() {
    if (state.checking) return
    state.checking = true
    try {
      const response = await getSourceStatus()
      if (!response?.success || !response.data?.budget) throw new Error('Invalid status')
      state.status = response.data
      state.statusError = false
    } catch { state.status = null; state.statusError = true }
    finally { state.checking = false }
  }

  async function prepare() {
    if (state.busy) return false
    state.errorCode = ''
    if (!pendingPlan && !state.pendingUrls.length) return true
    if (!pendingPlan && state.urls.length > state.maxPages) {
      state.errorCode = 'page_limit'
      return false
    }
    state.busy = true
    try {
      if (!pendingPlan) {
        state.phase = 'checking'
        const response = await planSources([...state.pendingUrls])
        const plan = response?.data
        if (!response?.success || !plan?.plan_id || !Array.isArray(plan.entries) || !plan.entries.length) throw new Error('Invalid plan')
        const requested = new Set(state.pendingUrls)
        if (plan.entries.some(entry => !requested.has(sourceUrl(entry.url)))) throw new Error('Unexpected plan URL')
        pendingPlan = { id: plan.plan_id, urls: plan.entries.map(entry => sourceUrl(entry.url)) }
        if (state.status && plan.budget) state.status.budget = plan.budget
      }
      state.phase = state.uncertain ? 'checkingResult' : 'collecting'
      // A dropped response is never retried automatically or given a new plan.
      state.uncertain = true
      const response = await fetchSources(pendingPlan.id)
      const result = response?.data
      if (!response?.success || !Array.isArray(result?.documents) || !Array.isArray(result?.errors)) throw new Error('Invalid collection result')
      if (result.documents.some(doc => !pendingPlan.urls.includes(sourceUrl(doc.url)) ||
        typeof doc.markdown !== 'string' || !doc.markdown.trim() || typeof doc.filename !== 'string' || !doc.filename.endsWith('.md'))) throw new Error('Invalid document')
      for (const doc of result.documents) saved.set(sourceUrl(doc.url), doc)
      state.revision++
      pendingPlan = null
      state.uncertain = false
      if (state.status && result.budget) state.status.budget = result.budget
      if (state.pendingUrls.length) {
        state.errorCode = errorCode({ response: { data: result.errors[0] } })
        return false
      }
      return true
    } catch (error) {
      state.errorCode = errorCode(error)
      if (['plan_expired', 'disabled', 'configuration', 'origin', 'invalid_request', 'daily_limit'].includes(state.errorCode)) {
        pendingPlan = null
        state.uncertain = false
      }
      return false
    } finally { state.busy = false; state.phase = '' }
  }

  function getFiles() {
    return state.documents.map(doc => new File([doc.markdown], doc.filename, {
      type: 'text/markdown', lastModified: Date.parse(doc.fetched_at) || 0,
    }))
  }
  return state
}
