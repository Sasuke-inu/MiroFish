import axios from 'axios'
import i18n from '../i18n'

// Keep credentials out of the general API interceptor's diagnostic logging.
const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001', timeout: 20000 })
export { client as providerClient }
let csrfToken = ''
async function request(method, url, data) {
  try {
    const response = await client.request({ method, url, data, headers: {
      'Accept-Language': i18n.global.locale.value,
      ...(data ? { 'Content-Type': 'application/json', 'X-MiroFish-CSRF': csrfToken } : {})
    } })
    if (response.data?.success === false) throw new Error(response.data.error || response.data.message)
    if (response.data?.data?.csrf_token) csrfToken = response.data.data.csrf_token
    return response.data.data
  } catch (error) {
    // Never rethrow AxiosError: its request config contains API tokens.
    const message = error.response?.data?.error || error.response?.data?.message
    throw new Error(typeof message === 'string' ? message : i18n.global.t('providers.requestFailed'))
  }
}
export const getProviderSettings = () => request('get', '/api/settings/providers')
export const saveProviderSettings = draft => request('put', '/api/settings/providers', draft)
export const testProviderSettings = draft => request('post', '/api/settings/providers/test', draft)
export const getProviderBalance = () => request('get', '/api/settings/providers/balance')
export const getProviderAccounts = () => request('get', '/api/settings/providers/accounts')
