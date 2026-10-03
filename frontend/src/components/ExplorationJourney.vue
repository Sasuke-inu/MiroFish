<template>
  <section class="exploration-journey" :aria-labelledby="`${uid}-title`">
    <h2 :id="`${uid}-title`">{{ $t('studio.refined.journeyTitle') }}</h2>
    <ol class="journey-stages">
      <li v-for="(key, index) in ['sources', 'people', 'report']" :key="key" :style="{ '--stage-index': index }">
        <span class="journey-artwork" aria-hidden="true">
          <img :src="'/assets/visuals/research-journey-v2.webp'" alt="" width="880" height="440" decoding="async" />
        </span>
        <div class="journey-stage-copy">
          <strong>{{ $t(`studio.refined.${key}`) }}</strong>
          <span>{{ $t(`studio.refined.${key}Detail`) }}</span>
        </div>
        <svg v-if="index < 2" class="journey-connector" viewBox="0 0 16 28" aria-hidden="true"><path d="M8 1v24m-4-5 4 5 4-5" /></svg>
      </li>
    </ol>
    <p class="journey-caption">{{ $t('studio.refined.journeyNote') }}</p>
  </section>
</template>

<script setup>
import { useId } from 'vue'
const uid = useId()
</script>

<style scoped>
.exploration-journey { color: var(--studio-ink); min-width: 0; }
h2 { margin: 0; font-size: 1.25rem; line-height: 1.45; font-weight: 700; text-wrap: balance; }
.journey-stages { --artwork-size: 116px; display: grid; gap: 28px; padding: 0; margin: 24px 0 0; list-style: none; }
.journey-stages li { position: relative; min-width: 0; display: grid; grid-template-columns: var(--artwork-size) minmax(0, 1fr); align-items: center; gap: 16px; }
.journey-artwork { position: relative; display: block; width: var(--artwork-size); height: var(--artwork-size); overflow: hidden; }
.journey-artwork img { position: absolute; top: 50%; left: calc(var(--stage-index) * -100%); display: block; width: 300%; max-width: none; height: auto; transform: translateY(-50%); }
.journey-stage-copy { min-width: 0; overflow-wrap: anywhere; }
.journey-stage-copy strong { display: block; font-size: 1rem; line-height: 1.5; font-weight: 600; }
.journey-stage-copy span { display: block; margin-top: 4px; color: var(--studio-muted); font-size: .875rem; line-height: 1.75; }
.journey-connector { position: absolute; top: 100%; left: calc(var(--artwork-size) / 2 - 8px); width: 16px; height: 28px; fill: none; stroke: var(--studio-accent); stroke-width: 1.25; stroke-linecap: round; stroke-linejoin: round; }
.journey-caption { color: var(--studio-muted); font-size: .8125rem; line-height: 1.75; margin: 24px 0 0; max-width: 65ch; }
@media (max-width: 959px) { .journey-stages { --artwork-size: 96px; gap: 28px; margin-top: 20px; } }
</style>
