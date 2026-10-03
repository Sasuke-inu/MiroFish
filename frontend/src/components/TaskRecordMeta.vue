<template>
  <dl class="task-record-meta"><dt>{{ $t('research.lastHeartbeat') }}</dt><dd>{{ record.heartbeat || $t('research.notRecorded') }}</dd><dt>{{ $t('research.lastUpdated') }}</dt><dd>{{ record.updated_at || $t('research.notRecorded') }}</dd><dt>{{ $t('research.attemptIdentity') }}</dt><dd>{{ record.attempt_id || $t('research.notRecorded') }}</dd><template v-if="completedUnits != null"><dt>{{ $t('research.completedUnits') }}</dt><dd>{{ completedUnits }}<template v-if="totalUnits != null"> / {{ totalUnits }}</template></dd></template></dl>
</template>
<script setup>
import {computed} from 'vue'
const props=defineProps({record:{type:Object,required:true}})
const completedUnits=computed(()=>props.record.progress_detail?.completed_units ?? props.record.detail?.completed_units ?? props.record.completed_units)
const totalUnits=computed(()=>props.record.progress_detail?.total_units ?? props.record.detail?.total_units ?? props.record.total_units)
</script>
<style scoped>
.task-record-meta{display:grid;grid-template-columns:minmax(90px,auto) minmax(0,1fr);gap:6px 16px;margin:14px 0;font-size:.875rem}.task-record-meta dt{color:var(--studio-muted)}.task-record-meta dd{margin:0;overflow-wrap:anywhere}
</style>
