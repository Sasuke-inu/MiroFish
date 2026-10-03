<template>
  <section class="replay-briefing" :aria-label="$t('research.briefingView')">
    <header><span>{{ $t('research.briefingView') }}</span><strong v-if="synthetic" class="tag">{{ $t('research.synthetic') }}</strong><strong v-if="run?.status !== 'completed'" class="tag">{{ $t('research.partialRecord') }}</strong></header>
    <p class="boundary">{{ $t('research.briefingBoundary') }}</p>
    <p v-if="run?.status !== 'completed'" class="boundary">{{ $t('research.incompleteRun') }}</p>
    <p v-if="!event" class="briefing-empty">{{ $t('research.briefingChooseEvent') }}</p>
    <div v-else class="briefing-layout">
      <article class="briefing-event"><h4>#{{ event.seq }} · {{ event.kind }}</h4><p>{{ event.platform }} · {{ $t('research.actor') }} {{ event.agent_id ?? '—' }} · {{ $t('research.round') }} {{ event.round ?? '—' }}</p><pre>{{ content }}</pre><dl><dt>{{ $t('research.simulationTime') }}</dt><dd>{{ event.simulation_time || '—' }}</dd><dt>{{ $t('research.observedTime') }}</dt><dd>{{ event.observed_at || '—' }}</dd></dl></article>
      <aside class="briefing-projection"><h4>{{ $t('research.projectionTitle',{seq:event.seq}) }}</h4><p v-if="seeking" role="status">{{ $t('research.loading') }}</p><template v-else-if="currentProjection"><p class="event-count">{{ $t('research.projectionCount',{count:projection.event_count ?? projection.events?.length ?? 0}) }}</p><ul><li v-for="actor in projection.actors || []" :key="`${actor.platform}:${actor.agent_id}`">{{ actor.platform }} · {{ actor.agent_id }} — {{ $t('research.actionCount',{count:actor.actions_count}) }}</li></ul><h5>{{ $t('research.recordedRelationships') }}</h5><p v-if="!projection.relationships?.length">{{ $t('research.noRelationships') }}</p><ul><li v-for="relation in projection.relationships || []" :key="relation.event_id">{{ relation.source_agent_id }} → {{ relation.target_agent_id }} · {{ relation.kind }}</li></ul></template><p v-else>{{ $t('research.briefingProjectionMissing') }}</p></aside>
    </div>
    <footer><p>{{ $t('research.projectionLimit') }}</p><ul><li v-for="item in uniqueLimitations" :key="item">{{ item }}</li></ul></footer>
  </section>
</template>
<script setup>
import {computed} from 'vue'
const props=defineProps({event:Object,projection:Object,run:Object,seeking:Boolean,limitations:{type:Array,default:()=>[]}})
const content=computed(()=>typeof props.event?.content==='string'?props.event.content:JSON.stringify(props.event?.content ?? null,null,2))
const synthetic=computed(()=>props.run?.manifest?.kind==='synthetic_fixture')
const currentProjection=computed(()=>props.projection?.through_seq===props.event?.seq)
const uniqueLimitations=computed(()=>[...new Set([...props.limitations,...(props.projection?.limitations || [])])])
</script>
<style scoped>
.replay-briefing{margin:24px 0;padding:24px;background:var(--studio-paper);border:1px solid var(--studio-line);border-radius:12px}header{display:flex;align-items:center;flex-wrap:wrap;gap:12px;font-size:.875rem}header>span{font-weight:600;color:var(--studio-accent)}.tag{font-size:.75rem;padding:3px 8px;background:var(--studio-surface);border:1px solid var(--studio-line);border-radius:4px}.boundary,footer{font-size:.8125rem;color:var(--studio-muted)}.briefing-layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:24px;margin-top:24px}h4{font-size:1.35rem;margin:0 0 12px}h5{font-size:.875rem;margin:20px 0 8px}p,li{font-size:.875rem;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:1.1rem/1.8 var(--studio-font);margin:24px 0;max-height:55vh;overflow:auto}dl{font-size:.8125rem;color:var(--studio-muted)}dd{margin:0 0 8px}.briefing-projection{padding:20px;border:1px solid var(--studio-line);border-radius:8px;background:var(--studio-surface)}.briefing-projection h4{font-size:1rem}.event-count{font-size:1.1rem}ul{padding-left:20px}footer{border-top:1px solid var(--studio-line);padding-top:12px;margin-top:24px}.briefing-empty{padding:40px 0}@media(max-width:700px){.briefing-layout{grid-template-columns:1fr}.replay-briefing{padding:16px}pre{font-size:1rem}}
</style>
