import service from './index'

// Each fetch has a server-issued idempotent plan; there are no automatic retries.
export const getSourceStatus = () => service.get('/api/sources/status', { timeout: 8000 })
export const planSources = urls => service.post('/api/sources/plan', { urls }, { timeout: 10000 })
export const fetchSources = planId => service.post('/api/sources/fetch', { plan_id: planId }, { timeout: 180000 })
