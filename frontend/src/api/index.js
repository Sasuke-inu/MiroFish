import axios from 'axios'
import i18n from '../i18n'

// 创建axios实例
const service = axios.create({
  // 同源相對路徑：由 vite 代理或 nginx 轉發 /api。直連 localhost:5001 會讓
  // 以 127.0.0.1:3000 開啟的頁面被判為 cross-site，遭本機來源政策拒絕。
  baseURL: import.meta.env.VITE_API_BASE_URL || '/',
  timeout: 300000, // 5分钟超时（本体生成可能需要较长时间）
  headers: {
    'Content-Type': 'application/json'
  }
})

// Legacy graph/simulation/report/sources routes share one session CSRF token,
// bootstrapped once from GET /api/session and re-fetched after a 403 reset.
// workbench.js/providers.js keep their own session handling.
let csrfToken = ''
let sessionRequest = null

export function __resetApiGuard() {
  csrfToken = ''
  sessionRequest = null
}

async function session() {
  if (csrfToken) return csrfToken
  if (!sessionRequest) {
    sessionRequest = service.get('/api/session').then(res => {
      csrfToken = res?.data?.csrf_token || ''
      return csrfToken
    }).finally(() => { sessionRequest = null })
  }
  return sessionRequest
}

// 请求拦截器
service.interceptors.request.use(
  async config => {
    config.headers['Accept-Language'] = i18n.global.locale.value
    const method = (config.method || 'get').toUpperCase()
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const token = await session()
      if (token) config.headers['X-MiroFish-CSRF'] = token
    }
    // FormData keeps its existing multipart content type.
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器（容错重试机制）
service.interceptors.response.use(
  response => {
    const res = response.data
    
    // 如果返回的状态码不是success，则抛出错误
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    
    return res
  },
  error => {
    console.error('Response error:', error)
    const apiError = error.response?.data?.error || error.response?.data?.message

    // A rejected token is dropped so the next write bootstraps a fresh one.
    if (error.response?.status === 403) {
      __resetApiGuard()
    }
    
    // 处理超时
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }
    
    // 处理网络错误
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }

    // Axios rejects non-2xx responses before the success interceptor can
    // surface the backend's safe, actionable error message.
    if (typeof apiError === 'string' && apiError) {
      error.message = apiError
    }
    
    return Promise.reject(error)
  }
)

export default service
