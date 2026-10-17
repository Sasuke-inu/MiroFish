import { beforeEach, describe, expect, it } from 'vitest'
import service, { __resetApiGuard } from '../src/api/index.js'

// Recording adapter: the guard's session fetch and the actual call both land here.
const calls = []
let sessionCalls = 0
let failNextWrite = false

service.defaults.adapter = async config => {
  calls.push({ method: (config.method || 'get').toLowerCase(), url: config.url, headers: config.headers })
  if (config.url === '/api/session') {
    sessionCalls += 1
    return { data: { success: true, data: { csrf_token: `token-${sessionCalls}` } }, status: 200, statusText: 'OK', headers: {}, config }
  }
  if (failNextWrite) {
    failNextWrite = false
    throw Object.assign(new Error('Request failed with status code 403'), {
      response: { status: 403, data: { success: false, error: '操作驗證碼無效，請重新載入頁面後再試。' }, headers: {}, config }
    })
  }
  return { data: { success: true, data: {} }, status: 200, statusText: 'OK', headers: {}, config }
}

const writes = () => calls.filter(call => call.url !== '/api/session')

beforeEach(() => {
  calls.length = 0
  sessionCalls = 0
  failNextWrite = false
  __resetApiGuard()
})

describe('shared api client CSRF guard', () => {
  it('fetches the session token once and carries it on writes', async () => {
    await service.post('/api/graph/build', { project_id: 'p1' })
    expect(sessionCalls).toBe(1)
    expect(writes()[0].headers['X-MiroFish-CSRF']).toBe('token-1')

    await service.post('/api/report/generate', { simulation_id: 's1' })
    expect(sessionCalls).toBe(1) // cached, no second bootstrap
    expect(writes()[1].headers['X-MiroFish-CSRF']).toBe('token-1')
  })

  it('does not fetch the token for reads', async () => {
    await service.get('/api/system/status')
    await service.get('/api/sources/status')
    expect(sessionCalls).toBe(0)
    expect(writes().every(call => !call.headers['X-MiroFish-CSRF'])).toBe(true)
  })

  it('keeps the multipart content type and still adds the token', async () => {
    const body = new FormData()
    body.append('files', new Blob(['doc']), 'source.md')
    await service.post('/api/graph/ontology/generate', body, { headers: { 'Content-Type': 'multipart/form-data' } })
    const write = writes()[0]
    expect(write.headers['Content-Type']).toBe('multipart/form-data')
    expect(write.headers['X-MiroFish-CSRF']).toBe('token-1')
  })

  it('resets the cached token after a 403 so the next write refetches', async () => {
    await service.post('/api/graph/build', {})
    expect(sessionCalls).toBe(1)

    failNextWrite = true
    await expect(service.post('/api/graph/build', {})).rejects.toThrow('操作驗證碼無效')
    expect(sessionCalls).toBe(1) // the 403 itself used the cached token

    await service.post('/api/graph/build', {})
    expect(sessionCalls).toBe(2)
    expect(writes().at(-1).headers['X-MiroFish-CSRF']).toBe('token-2')
  })

  it('truncates concurrent writes behind a single bootstrap', async () => {
    await Promise.all([
      service.post('/api/simulation/start', { simulation_id: 's1' }),
      service.delete('/api/report/report-1')
    ])
    expect(sessionCalls).toBe(1)
    expect(writes().map(call => call.headers['X-MiroFish-CSRF'])).toEqual(['token-1', 'token-1'])
  })
})
