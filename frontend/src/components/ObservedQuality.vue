<template>
  <article class="observed-quality">
    <h4>{{ title }}</h4><p>{{ $t(metric?.status === 'observed' ? 'research.observedCounts' : 'research.notEvaluated') }}</p><p v-if="metric">{{ $t('research.qualitySamples',{count:metric.sample_size || 0}) }}</p><p class="muted">{{ $t('research.observedLimit') }}</p>
    <section v-for="group in metric?.groups || []" :key="group.group_id" class="observed-group"><h5>{{ $t(group.kind === 'synthetic_fixture' ? 'research.synthetic' : 'research.recordedRuns') }} · {{ $t('research.qualitySamples',{count:group.sample_size}) }}</h5><p class="ids">{{ group.simulation_ids.join(' · ') }}</p><div class="table-scroll"><table><thead><tr><th>{{ $t('research.platform') }}</th><th>{{ $t('research.eventKind') }}</th><th>{{ $t('research.minimum') }}</th><th>{{ $t('research.maximum') }}</th></tr></thead><tbody><template v-for="(kinds,platform) in group.kind_counts" :key="platform"><tr v-for="(counts,kind) in kinds" :key="kind"><th>{{ platform }}</th><td>{{ kind }}</td><td>{{ counts.min }}</td><td>{{ counts.max }}</td></tr></template></tbody></table></div><details><summary>{{ $t('research.sampleDetails') }}</summary><div v-for="model in group.models" :key="model.run_id"><p class="ids">{{ model.run_id }}</p><p>{{ model.model?.provider }} · {{ model.model?.model }}</p></div></details></section>
    <details v-if="metric?.excluded?.length"><summary>{{ $t('research.excludedSamples',{count:metric.excluded.length}) }}</summary><ul><li v-for="item in metric.excluded" :key="item.simulation_id" class="ids">{{ item.simulation_id }}：{{ item.message || item.reason }}</li></ul></details><ul class="muted"><li v-for="item in metric?.limitations || []" :key="item">{{ item }}</li></ul>
  </article>
</template>
<script setup>
defineProps({title:String,metric:Object})
</script>
<style scoped>
.observed-quality{border-top:1px solid var(--studio-line);padding:16px 0}.observed-quality h4{margin:0 0 12px}.observed-group{padding:12px 0}.observed-group h5{font-size:.95rem;margin:8px 0}p{margin:8px 0}.muted{color:var(--studio-muted);font-size:.875rem}.ids{overflow-wrap:anywhere;font-size:.875rem}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%}th,td{border:1px solid var(--studio-line);padding:8px;text-align:left;font-size:.875rem}summary{min-height:44px;padding:8px 0;cursor:pointer}ul{padding-left:24px}
</style>
