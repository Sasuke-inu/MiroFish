<template>
  <nav class="studio-progress" :aria-label="$t('studio.workflow')">
    <ol>
      <li v-for="(name, index) in $tm('main.stepNames')" :key="index"
        :class="{ current: current === index + 1, passed: current > index + 1 }"
        :aria-current="current === index + 1 ? 'step' : undefined">
        <span class="progress-number">{{ current > index + 1 ? '✓' : String(index + 1).padStart(2, '0') }}</span>
        <span>{{ name }}</span>
      </li>
    </ol>
  </nav>
</template>

<script setup>
defineProps({ current: { type: Number, required: true } })
</script>
