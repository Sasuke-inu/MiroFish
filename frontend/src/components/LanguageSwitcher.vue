<template>
  <div class="language-switcher" ref="switcherRef" @keydown.esc.stop="closeDropdown(true)" @focusout="onFocusOut">
    <button ref="triggerRef" type="button" class="switcher-trigger" @click="toggleDropdown" :aria-label="`${$t('settings.language')}: ${currentLabel}`" :aria-expanded="open" :aria-controls="dropdownId" @keydown.down.prevent="openAndFocus(0)" @keydown.up.prevent="openAndFocus(availableLocales.length - 1)">
      {{ currentLabel }}
      <span class="caret">{{ open ? '▲' : '▼' }}</span>
    </button>
    <ul v-if="open" :id="dropdownId" class="switcher-dropdown" @keydown="onChoiceKeydown">
      <li
        v-for="loc in availableLocales"
        :key="loc.key"
        class="switcher-option"
        :class="{ active: loc.key === locale }"
      >
        <button type="button" class="locale-choice" @click="switchLocale(loc.key)" :aria-pressed="loc.key === locale">{{ loc.label }}</button>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { availableLocales } from '@/i18n/index.js'

const { locale } = useI18n()
const open = ref(false)
const switcherRef = ref(null)
const triggerRef = ref(null)
const dropdownId = useId()

const currentLabel = computed(() => {
  const found = availableLocales.find(l => l.key === locale.value)
  return found ? found.label : locale.value
})

const toggleDropdown = () => {
  open.value = !open.value
}

const closeDropdown = (restoreFocus = false) => {
  open.value = false
  if (restoreFocus) triggerRef.value?.focus()
}
const openAndFocus = async (index) => {
  open.value = true
  await nextTick()
  switcherRef.value?.querySelectorAll('.locale-choice')[index]?.focus()
}
const onChoiceKeydown = (event) => {
  const choices = Array.from(switcherRef.value?.querySelectorAll('.locale-choice') || [])
  const current = choices.indexOf(document.activeElement)
  let target
  if (event.key === 'ArrowDown') target = (current + 1) % choices.length
  else if (event.key === 'ArrowUp') target = (current - 1 + choices.length) % choices.length
  else if (event.key === 'Home') target = 0
  else if (event.key === 'End') target = choices.length - 1
  else return
  event.preventDefault()
  choices[target]?.focus()
}
const onFocusOut = (event) => {
  if (!switcherRef.value?.contains(event.relatedTarget)) closeDropdown()
}

const switchLocale = (key) => {
  locale.value = key
  try { localStorage.setItem('locale', key) } catch { /* Keep language switching available without storage. */ }
  document.documentElement.lang = key
  closeDropdown(true)
}

const onClickOutside = (e) => {
  if (switcherRef.value && !switcherRef.value.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
  document.documentElement.lang = locale.value
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.language-switcher {
  position: relative;
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
}

/* Light theme (default - for white header backgrounds) */
.switcher-trigger {
  background: transparent;
  color: var(--theme-ink, #333);
  border: 1px solid var(--theme-line, #CCC);
  padding: 4px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: border-color 0.2s, opacity 0.2s;
}

.switcher-trigger:hover {
  border-color: var(--theme-line-strong, #999);
}

.caret {
  font-size: 0.6rem;
}

.switcher-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--theme-surface, #FFFFFF);
  border: 1px solid var(--theme-line, #DDD);
  list-style: none;
  padding: 4px 0;
  min-width: 100%;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.switcher-option {
  padding: 0;
  font-size: 0.8rem;
  color: var(--theme-ink, #333);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.locale-choice {
  color: inherit;
  background: none;
  border: 0;
  padding: 8px 12px;
  width: 100%;
  text-align: left;
  white-space: nowrap;
  font: inherit;
}

.switcher-option:hover {
  background: var(--theme-surface-soft, #F0F0F0);
}

.switcher-option.active {
  color: var(--studio-accent, #b84d28);
}

.switcher-trigger { min-height: 44px; border-radius: 8px; font-family: var(--studio-font, system-ui); font-size: 13px; }
.switcher-dropdown { min-width: 148px; padding: 5px; border-radius: 10px; box-shadow: 0 12px 32px #0002; }
.locale-choice { min-height: 44px; border-radius: 6px; font-family: var(--studio-font, system-ui); font-size: 14px; cursor: pointer; }
.switcher-option.active .locale-choice { background: var(--studio-soft); font-weight: 600; }
.switcher-trigger:focus-visible, .locale-choice:focus-visible { outline: 3px solid var(--studio-accent, #b84d28); outline-offset: 2px; }


</style>
