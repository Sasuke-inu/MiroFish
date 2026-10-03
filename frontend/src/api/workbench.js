import axios from 'axios'
import i18n from '../i18n'

// Research contents and session headers stay on the UI's origin. The local
// Vite/production proxy forwards /api without exposing a remote endpoint option.
export const workbenchClient = axios.create({ baseURL: '/', timeout: 20000 })
const base = '/api/workbench'
const id = value => encodeURIComponent(value)
let csrf = ''
let sessionRequest = null
export function resetWorkbenchSession() { csrf = ''; sessionRequest = null }

async function request(method, path, data, params, prefix = base) {
  try {
    const response = await workbenchClient.request({ method, url: prefix + path, params, data, headers: {
      'Accept-Language': i18n.global.locale.value,
      ...(data !== undefined ? { 'Content-Type': 'application/json', 'X-MiroFish-CSRF': csrf } : {})
    } })
    if (!response.data?.success) throw new Error(response.data?.error || i18n.global.t('research.requestFailed'))
    return response.data.data
  } catch (error) {
    if (error.response?.status === 403) resetWorkbenchSession()
    const message = error.response?.data?.error || error.response?.data?.message || (error.isAxiosError ? '' : error.message)
    // Source bodies and session headers are never included in diagnostics.
    throw new Error(typeof message === 'string' && message ? message : i18n.global.t('research.requestFailed'))
  }
}
async function session() {
  if (csrf) return
  if (!sessionRequest) sessionRequest = request('get', '/session').then(data => {
    if (!data?.csrf_token) throw new Error(i18n.global.t('research.requestFailed'))
    csrf = data.csrf_token
  }).finally(() => { sessionRequest = null })
  await sessionRequest
}
async function change(method, path, data) { await session(); return request(method, path, data) }

export const listProjects = params => request('get', '/projects', undefined, params)
export const getResearch = projectId => request('get', `/projects/${id(projectId)}`)
export const createResearch = data => change('post', '/projects', data)
export const editResearch = (projectId, data) => change('patch', `/projects/${id(projectId)}`, data)
export const cloneResearch = projectId => change('post', `/projects/${id(projectId)}/clone`, {})
export const listSources = (projectId, params) => request('get', `/projects/${id(projectId)}/sources`, undefined, params)
export const listReferences = (projectId, params) => request('get', `/projects/${id(projectId)}/references`, undefined, params)
export const saveSource = (projectId, data) => change('post', `/projects/${id(projectId)}/sources`, data)
export const indexLegacySources = projectId => change('post', `/projects/${id(projectId)}/legacy-index`, {})
export const getSource = (sourceId, params) => request('get', `/sources/${id(sourceId)}`, undefined, params)
export const getVersion = (versionId, params) => request('get', `/versions/${id(versionId)}`, undefined, params)
export const refreshSource = sourceId => change('post', `/sources/${id(sourceId)}/refresh`, {})
export const planWebSources = (projectId, urls) => change('post', `/projects/${id(projectId)}/web-plan`, {urls})
export const fetchWebSources = (projectId, planId) => change('post', `/projects/${id(projectId)}/web-fetch`, {plan_id:planId})
export const previewWebSources = (projectId, planId) => change('post', `/projects/${id(projectId)}/web-preview`, {plan_id:planId})
export const adoptWebSources = (projectId,planId,urls) => change('post',`/projects/${id(projectId)}/web-adopt`,{plan_id:planId,urls})
export const getEvents = (simulationId, params) => request('get', `/simulations/${id(simulationId)}/events`, undefined, params)
export const resolveEventReference = (projectId,runId,eventId) => request('get', `/projects/${id(projectId)}/events/${id(eventId)}`, undefined, {run_id:runId})
export const getProjection = (simulationId, throughSeq) => request('get', `/simulations/${id(simulationId)}/projection`, undefined, {through_seq:throughSeq})
export const compareRuns = (left,right) => request('get', '/compare', undefined, {left,right})
export const saveSpan = (versionId, data) => change('post', `/versions/${id(versionId)}/spans`, data)
export const saveReference = (projectId, data) => change('post', `/projects/${id(projectId)}/references`, data)
export const getQuality = projectId => request('get', `/projects/${id(projectId)}/quality`)
export const getPlans = projectId => request('get', `/projects/${id(projectId)}/plans`)
export const savePlan = (projectId,data) => change('post', `/projects/${id(projectId)}/plans`, data)
export const listTasks = () => request('get', '/tasks')
export const listDemos = () => request('get', '/demos')
export const installDemo = demoId => change('post', `/demos/${id(demoId)}`, {})
export const researchExportUrl = projectId => workbenchClient.getUri({url:`${base}/projects/${id(projectId)}/export`,params:{format:'html'}})
export async function recoverNamespace(simulationId) { await session(); return request('post',`/api/simulation/${id(simulationId)}/recover-namespace`,{},undefined,'') }
export const getSavedModelProfiles = () => request('get','/api/settings/profiles',undefined,undefined,'')
export const verifyReportRun = simulationId => request('get',`/api/simulation/${id(simulationId)}/run-status`,undefined,undefined,'')
export const readReportTask = taskId => request('get',`/api/graph/task/${id(taskId)}`,undefined,undefined,'')
export async function createReportVersion(simulationId) { await session(); return request('post','/api/report/generate',{simulation_id:simulationId,force_regenerate:true},undefined,'') }
export async function downloadResearch(projectId, format) {
  if (!['html', 'md', 'json'].includes(format)) throw new Error(i18n.global.t('research.requestFailed'))
  try {
    const response = await workbenchClient.get(`${base}/projects/${id(projectId)}/export`, { params: { format }, responseType: 'blob' })
    return { blob: response.data, filename: `research-${projectId}.${format}` }
  } catch { throw new Error(i18n.global.t('research.exportFailed')) }
}
