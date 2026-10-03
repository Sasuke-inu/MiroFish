import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initializeAppearance, THEME_STORAGE_KEY, useAppearance } from '../src/store/appearance'

let media
let stop
beforeEach(() => {
  localStorage.clear()
  media = new EventTarget()
  media.matches = false
  vi.stubGlobal('matchMedia', vi.fn(() => media))
})
afterEach(() => {
  stop?.()
  stop = undefined
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.removeProperty('color-scheme')
})
function systemChange(matches) {
  media.matches = matches
  const event = new Event('change')
  Object.defineProperty(event, 'matches', { value: matches })
  media.dispatchEvent(event)
}

describe('Appearance preferences', () => {
  it('keeps the approved light appearance on a first visit, even on a dark system', () => {
    media.matches = true
    stop = initializeAppearance()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })
  it('restores a saved dark appearance on startup', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    stop = initializeAppearance()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(useAppearance().preference.value).toBe('dark')
  })
  it('applies and remembers a choice across a new application instance', () => {
    stop = initializeAppearance()
    useAppearance().setTheme('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    stop()
    document.documentElement.dataset.theme = 'light'
    stop = initializeAppearance()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
  it('follows system changes only when follow-system is selected', () => {
    stop = initializeAppearance()
    useAppearance().setTheme('system')
    systemChange(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    systemChange(false)
    expect(document.documentElement.dataset.theme).toBe('light')
    useAppearance().setTheme('dark')
    systemChange(false)
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
  it('updates another tab when its stored preference changes or is cleared', () => {
    stop = initializeAppearance()
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: 'dark' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    localStorage.clear()
    window.dispatchEvent(new StorageEvent('storage', { key: null }))
    expect(document.documentElement.dataset.theme).toBe('light')
  })
  it('ignores invalid saved values and invalid choices', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'untrusted-value')
    stop = initializeAppearance()
    expect(document.documentElement.dataset.theme).toBe('light')
    useAppearance().setTheme('untrusted-value')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
  it('still applies the appearance and reports unsaved preferences when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked') })
    expect(() => { stop = initializeAppearance(); useAppearance().setTheme('dark') }).not.toThrow()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(useAppearance().saved.value).toBe(false)
  })
  it('removes system and storage listeners when the application closes', () => {
    stop = initializeAppearance()
    useAppearance().setTheme('system')
    stop()
    systemChange(true)
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY }))
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
