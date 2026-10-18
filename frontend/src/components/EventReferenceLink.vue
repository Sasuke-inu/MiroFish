<template>
  <RouterLink v-if="projectId && reference.category === 'simulation_event' && reference.run_id && reference.event_id" class="event-reference-link" :to="{name:'Workbench',params:{projectId},query:locateQuery}">{{ $t('research.locateEvent') }}</RouterLink>
</template>
<script setup>
import {computed} from 'vue'
import {useRoute} from 'vue-router'
const props=defineProps({projectId:String,reference:{type:Object,required:true},reportId:String,simulationId:String})
const route=useRoute()
// Locating an event overrides only the locating fields. The current replay and
// report selection survive, so returning to the report keeps its version.
const locateQuery=computed(()=>({...route.query,...(props.simulationId?{replay:props.simulationId}:{}),...(props.reportId?{report:props.reportId}:{}),section:'runs',ref_run:props.reference.run_id,ref_event:props.reference.event_id}))
</script>
<style scoped>
.event-reference-link{display:inline-flex;align-items:center;min-height:44px;padding:8px 12px;margin:8px 8px 0 0;border:1px solid var(--theme-control-line);border-radius:8px;background:var(--studio-paper);color:var(--studio-ink);font:inherit;font-size:.875rem;text-decoration:none}
</style>
