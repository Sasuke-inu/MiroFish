<template>
  <section class="exploration-journey" :aria-labelledby="`${uid}-title`">
    <h2 :id="`${uid}-title`">{{ $t('studio.refined.journeyTitle') }}</h2>
    <figure>
      <img :src="'/assets/visuals/research-journey-v2.webp'" alt="" width="880" height="440" decoding="async" />
      <figcaption>
        <ol class="journey-stages">
          <li v-for="(key, index) in ['sources', 'people', 'report']" :key="key">
            <span class="journey-stage-marker" aria-hidden="true">
              <svg v-if="index < 2" class="journey-connector" viewBox="0 0 100 16" preserveAspectRatio="none"><path d="M0 8H96m-5-4 5 4-5 4" /></svg>
              <svg class="journey-node" viewBox="0 0 16 16"><circle cx="8" cy="8" r="4" /></svg>
            </span>
            <strong>{{ $t(`studio.refined.${key}`) }}</strong>
            <span>{{ $t(`studio.refined.${key}Detail`) }}</span>
          </li>
        </ol>
      </figcaption>
    </figure>
    <p class="journey-caption">{{ $t('studio.refined.journeyNote') }}</p>
  </section>
</template>

<script setup>
import { useId } from 'vue'
const uid = useId()
</script>

<style scoped>
.exploration-journey { color: var(--studio-ink); min-width: 0; }
h2 { margin: 0; font-size: 18px; line-height: 1.5; font-weight: 650; text-wrap: balance; }
figure { margin: 16px 0 0; }
img { display: block; width: 100%; height: auto; }
.journey-stages { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 0; margin: 0; list-style: none; }
.journey-stages li { min-width: 0; display: flex; flex-direction: column; align-items: center; text-align: center; }
.journey-stage-marker { position: relative; display: block; width: 100%; height: 24px; margin-bottom: 8px; }
.journey-node { position: relative; width: 16px; height: 16px; margin-top: 4px; fill: var(--studio-paper); stroke: var(--studio-accent); stroke-width: 1.5; }
.journey-connector { position: absolute; top: 4px; left: calc(50% + 8px); width: calc(100% - 16px); height: 16px; fill: none; stroke: var(--studio-line); stroke-width: 1; }
strong { font-size: 14px; line-height: 1.6; font-weight: 650; }
li > span:last-child { color: var(--studio-muted); font-size: 12px; line-height: 1.65; margin-top: 4px; padding-inline: 4px; text-wrap: balance; }
.journey-caption { color: var(--studio-muted); font-size: 12px; line-height: 1.8; margin: 20px 0 0; }
@media (max-width: 880px) {
  figure { max-width: 460px; margin: 8px auto 0; }
  img { max-height: 150px; object-fit: contain; }
  .journey-caption { margin-top: 14px; }
}
</style>
