import { createI18n } from 'vue-i18n'
import { watch } from 'vue'
import languages from '../../../locales/languages.json'

const localeFiles = import.meta.glob('../../../locales/!(languages).json', { eager: true })

const messages = {}
const availableLocales = []

for (const path in localeFiles) {
  const key = path.match(/\/([^/]+)\.json$/)[1]
  if (languages[key]) {
    messages[key] = localeFiles[path].default
    availableLocales.push({ key, label: languages[key].label })
  }
}

let preference = null
try { preference = localStorage.getItem('locale') } catch { /* Browser storage can be unavailable. */ }
const savedLocale = messages[preference] ? preference : 'zh-TW'

const i18n = createI18n({
  legacy: false,
  locale: savedLocale,
  fallbackLocale: 'zh-TW',
  messages
})

watch(i18n.global.locale, (locale) => {
  document.documentElement.lang = locale
  document.title = messages[locale]?.meta?.title || messages['zh-TW'].meta.title
}, { immediate: true })

export { availableLocales }
export default i18n
