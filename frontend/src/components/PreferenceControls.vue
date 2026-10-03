<template>
  <div class="preference-controls">
    <button type="button" class="appearance-toggle" :aria-label="toggleLabel" :title="toggleLabel"
      :aria-pressed="theme === 'dark'" @click="setTheme(theme === 'dark' ? 'light' : 'dark')">
      <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5" />
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <path d="M20.2 15.4A9 9 0 0 1 8.6 3.8 9 9 0 1 0 20.2 15.4Z" />
      </svg>
    </button>
    <RouterLink class="settings-link" :to="{ name: 'Settings', query: { from: route.fullPath } }" :title="$t('settings.title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <path d="m9.5 3-.6 2.1-2 .9-2-.6-2.4 4.2L4 11v2l-1.5 1.4L5 18.6l2-.6 2 .9.6 2.1h4.8l.6-2.1 2-.9 2 .6 2.4-4.2L20 13v-2l1.5-1.4L19 5.4l-2 .6-2-.9-.6-2.1Z" /><circle cx="12" cy="12" r="3" />
      </svg>
      <span>{{ $t('settings.title') }}</span>
    </RouterLink>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAppearance } from '../store/appearance'
const route = useRoute()
const { t } = useI18n()
const { theme, setTheme } = useAppearance()
const toggleLabel = computed(() => t(theme.value === 'dark' ? 'settings.switchLight' : 'settings.switchDark'))
</script>

<style scoped>
.preference-controls { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.appearance-toggle, .settings-link { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 36px; padding: 8px 10px; border: 1px solid var(--studio-line); border-radius: 8px; background: var(--studio-surface); color: var(--studio-muted); text-decoration: none; font-size: 12px; white-space: nowrap; }
.appearance-toggle { width: 44px; padding: 10px; }
.appearance-toggle, .settings-link { min-height: 44px; font-size: 13px; }
svg { width: 17px; height: 17px; flex-shrink: 0; }
.appearance-toggle:hover, .settings-link:hover { color: var(--studio-accent); border-color: var(--studio-accent); background: var(--studio-soft); }
@media (max-width: 500px) { .settings-link span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); } .settings-link { width: 44px; padding: 10px; } }
</style>
