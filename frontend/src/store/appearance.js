import { computed, readonly, ref } from 'vue'

export const THEME_STORAGE_KEY = 'mirofish.theme'
const choices = ['light', 'dark', 'system']
const preference = ref('light')
const systemDark = ref(false)
const saved = ref(true)
const theme = computed(() => preference.value === 'system'
  ? (systemDark.value ? 'dark' : 'light') : preference.value)

function applyTheme() {
  document.documentElement.dataset.theme = theme.value
  document.documentElement.style.colorScheme = theme.value
}

function readPreference() {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY)
    return choices.includes(value) ? value : 'light'
  } catch {
    saved.value = false
    return 'light'
  }
}

export function initializeAppearance() {
  saved.value = true
  preference.value = readPreference()
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  systemDark.value = media?.matches ?? false
  const onSystemChange = event => {
    systemDark.value = event.matches
    applyTheme()
  }
  const onStorageChange = event => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) {
      preference.value = readPreference()
      applyTheme()
    }
  }
  media?.addEventListener('change', onSystemChange)
  window.addEventListener('storage', onStorageChange)
  applyTheme()
  return () => {
    media?.removeEventListener('change', onSystemChange)
    window.removeEventListener('storage', onStorageChange)
  }
}

function setTheme(value) {
  if (!choices.includes(value)) return
  preference.value = value
  applyTheme()
  try {
    localStorage.setItem(THEME_STORAGE_KEY, value)
    saved.value = true
  } catch {
    saved.value = false
  }
}

export function useAppearance() {
  return { preference: readonly(preference), theme, saved: readonly(saved), setTheme }
}
