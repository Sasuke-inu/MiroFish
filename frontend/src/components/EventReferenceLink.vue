<template>
  <RouterLink v-if="projectId && reference.category === 'simulation_event' && reference.run_id && reference.event_id" class="event-reference-link" :to="{name:'Workbench',params:{projectId},query:{section:'runs',ref_run:reference.run_id,ref_event:reference.event_id}}">{{ $t('research.locateEvent') }}</RouterLink>
</template>
<script setup>
defineProps({projectId:String,reference:{type:Object,required:true}})
</script>
<style scoped>
.event-reference-link{display:inline-flex;align-items:center;min-height:44px;padding:8px 12px;margin:8px 8px 0 0;border:1px solid var(--theme-control-line);border-radius:8px;background:var(--studio-paper);color:var(--studio-ink);font:inherit;font-size:.875rem;text-decoration:none}
</style>
