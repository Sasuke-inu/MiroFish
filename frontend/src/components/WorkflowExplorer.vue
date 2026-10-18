<template>
  <section class="workflow-explorer" :aria-labelledby="`${uid}-heading`">
    <div class="explorer-heading">
      <div>
        <h2 :id="`${uid}-heading`">{{ $t('visuals.workflow.title') }}</h2>
      </div>
    </div>
    <p class="explorer-hint">{{ $t('visuals.workflow.hint') }}</p>

    <div class="explorer-steps" role="tablist" aria-orientation="vertical" :aria-labelledby="`${uid}-heading`">
      <button
        v-for="(step, index) in steps"
        :id="`${uid}-step-${index}`"
        :key="step.key"
        :ref="element => { stepButtons[index] = element }"
        class="explorer-step"
        :class="{ selected: activeIndex === index }"
        type="button"
        role="tab"
        :aria-selected="activeIndex === index"
        :aria-controls="`${uid}-detail`"
        :tabindex="activeIndex === index ? 0 : -1"
        @click="activeIndex = index"
        @keydown="moveStep($event, index)"
      >
        <span class="explorer-icon" aria-hidden="true">
          <svg viewBox="0 0 40 40" fill="none" focusable="false">
            <path v-for="(path, pathIndex) in step.paths" :key="pathIndex" :d="path" />
          </svg>
        </span>
        <span class="explorer-step-title">{{ $t(`studio.step${index + 1}Title`) }}</span>
        <span class="explorer-step-number" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
        <svg class="explorer-chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m6 4 4 4-4 4" /></svg>
      </button>
    </div>

    <div
      :id="`${uid}-detail`"
      class="explorer-detail"
      role="tabpanel"
      :aria-labelledby="`${uid}-step-${activeIndex}`"
      tabindex="0"
    >
      <dl aria-live="polite" aria-atomic="true">
        <div><dt>{{ $t('visuals.workflow.input') }}</dt><dd>{{ $t(`visuals.workflow.steps.${activeStep.key}.input`) }}</dd></div>
        <div><dt>{{ $t('visuals.workflow.action') }}</dt><dd>{{ $t(`studio.step${activeIndex + 1}Desc`) }}</dd></div>
        <div class="explorer-result"><dt>{{ $t('visuals.workflow.output') }}</dt><dd>{{ $t(`visuals.workflow.steps.${activeStep.key}.output`) }}</dd></div>
      </dl>
    </div>
    <p class="explorer-note">
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.25" /><path d="M10 9v4m0-7v.1" /></svg>
      <span>{{ $t('visuals.workflow.previewNote') }}</span>
    </p>
  </section>
</template>

<script setup>
import { computed, ref, useId } from 'vue'

const uid = useId()
const activeIndex = ref(0)
const stepButtons = ref([])
const steps = [
  { key: 'graph', paths: ['M11 13 20 9l9 7-3 14-15-3V13m0 0 15 17M20 9l-9 18m18-11L11 27', 'M14 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm9-4a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm9 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm-3 14a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm-15-3a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'] },
  { key: 'setup', paths: ['M8 11h24M8 20h24M8 29h24', 'M14 8v6m12 3v6m-10 3v6'] },
  { key: 'interaction', paths: ['M6 8h20v14H15l-6 5v-5H6V8Z', 'M29 16h5v15h-3v4l-6-4h-8v-5M11 13h10m-10 4h6'] },
  { key: 'report', paths: ['M11 5h13l7 7v23H11V5Zm13 0v8h7', 'M16 18h10m-10 4h6m-6 8v-4m5 4v-6m5 6v-3'] },
  { key: 'followup', paths: ['M6 7h28v20H20l-8 7v-7H6V7Z', 'M16 14a4 4 0 1 1 6 3.5c-1 .5-2 1-2 2.5m0 3v.1'] }
]
const activeStep = computed(() => steps[activeIndex.value])

function moveStep(event, index) {
  let nextIndex
  if (event.key === 'ArrowDown') nextIndex = (index + 1) % steps.length
  else if (event.key === 'ArrowUp') nextIndex = (index + steps.length - 1) % steps.length
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = steps.length - 1
  else return
  event.preventDefault()
  activeIndex.value = nextIndex
  stepButtons.value[nextIndex]?.focus()
}
</script>

<style scoped>
.workflow-explorer { min-width: 0; padding: 22px; border: 1px solid var(--studio-line); border-radius: 16px; background: var(--studio-surface); color: var(--studio-ink); }
.explorer-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.explorer-heading h2 { margin: 0; font-size: 18px; line-height: 1.4; font-weight: 650; }
.explorer-hint { margin: 10px 0 18px; color: var(--studio-muted); font-size: 13px; line-height: 1.65; }
.explorer-steps { position: relative; display: grid; gap: 5px; }
.explorer-steps::before { position: absolute; content: ''; top: 26px; bottom: 26px; left: 28px; width: 1px; background: var(--studio-line); pointer-events: none; }
.explorer-step { position: relative; display: flex; align-items: center; gap: 10px; width: 100%; min-width: 0; min-height: 56px; padding: 7px 10px; border: 1px solid transparent; border-radius: 10px; background: transparent; color: var(--studio-ink); text-align: left; transition: background-color .15s ease, border-color .15s ease; }
.explorer-step:hover { background: var(--theme-surface-soft); }
.explorer-step.selected { background: var(--studio-soft); border-color: var(--theme-accent-line, #ead1c4); }
.explorer-icon { position: relative; display: grid; place-items: center; flex: 0 0 34px; height: 36px; background: var(--studio-surface); border-radius: 7px; color: var(--studio-muted); }
.explorer-step.selected .explorer-icon { background: var(--studio-soft); color: var(--studio-accent); }
.explorer-icon svg { width: 32px; height: 32px; stroke: currentColor; stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
.explorer-step-title { flex: 1; min-width: 0; font-size: 14px; font-weight: 600; line-height: 1.5; overflow-wrap: anywhere; }
.explorer-step-number { color: var(--studio-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.explorer-chevron { width: 12px; height: 12px; flex: 0 0 12px; stroke: var(--studio-muted); stroke-width: 1.4; opacity: .5; }
.explorer-step.selected .explorer-chevron { stroke: var(--studio-accent); opacity: 1; }
.explorer-step:focus-visible, .explorer-detail:focus-visible { outline: 2px solid var(--studio-accent); outline-offset: 3px; }
.explorer-detail { margin-top: 18px; padding: 16px 0 0; border-top: 1px solid var(--studio-line); }
.explorer-detail dl { display: grid; gap: 12px; margin: 0; }
.explorer-detail dl > div { display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 8px; align-items: start; }
.explorer-detail dt { margin: 1px 0 0; font-size: 11px; color: var(--studio-muted); line-height: 1.7; }
.explorer-detail dd { margin: 0; font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; }
.explorer-result dd { color: var(--studio-accent); font-weight: 600; }
.explorer-note { display: flex; align-items: flex-start; gap: 6px; margin: 17px 0 0; color: var(--studio-muted); font-size: 11px; line-height: 1.6; }
.explorer-note svg { flex: 0 0 16px; width: 16px; height: 16px; margin-top: 1px; stroke: currentColor; stroke-width: 1.4; stroke-linecap: round; }
@media (max-width: 980px) { .workflow-explorer { padding: 18px; } .explorer-step { padding-left: 6px; padding-right: 6px; gap: 8px; } .explorer-steps::before { left: 24px; } }
@media (prefers-reduced-motion: reduce) { .explorer-step { transition: none; } }
</style>
