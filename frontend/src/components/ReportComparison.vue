<template>
  <section v-if="reportDiff" class="report-comparison">
    <h4>{{ $t('research.reportComparison') }}</h4>
    <p>{{ $t('research.savedComparisonOnly') }}</p>
    <p v-if="reportDiff.status !== 'compared'" class="notice">{{ $t('research.reportComparisonUnavailable') }}</p>
    <div class="sides">
      <article v-for="side in sides" :key="side.key">
        <h5>{{ side.label }} · {{ side.report?.selected_report_id || $t('research.notRecorded') }}</h5>
        <RouterLink v-if="side.report?.selected_report_id" :to="`/report/${encodeURIComponent(side.report.selected_report_id)}`">{{ $t('research.openSavedReport') }}</RouterLink>
        <p v-for="item in side.report?.reports || []" :key="item.report_id" class="muted">{{ item.report_id }} · v{{ item.version }} · {{ item.status }}</p>
        <p v-for="item in side.report?.excluded || []" :key="item.report_id" class="muted">{{ item.report_id }} · {{ exclusion(item.reason) }}</p>
        <pre v-if="side.report?.summary != null">{{ side.report.summary }}</pre>
      </article>
    </div>
    <template v-if="reportDiff.status === 'compared'">
      <p>{{ $t(reportDiff.summary_changed ? 'research.summaryChanged' : 'research.summaryUnchanged') }}</p>
      <details v-for="section in reportDiff.sections || []" :key="section.index" :open="section.changed" class="section-diff">
        <summary>{{ $t('research.sectionNumber',{index:section.index}) }} · {{ $t(section.changed ? 'research.savedTextChanged' : 'research.savedTextUnchanged') }}</summary>
        <div class="sides"><article v-for="key in ['left','right']" :key="key"><h5>{{ key === 'left' ? 'A' : 'B' }} · {{ section[key]?.title || $t('research.notRecorded') }}</h5><pre>{{ section[key]?.content ?? $t('research.notRecorded') }}</pre></article></div>
      </details>
      <p>{{ $t(reportDiff.markdown_changed ? 'research.fullTextChanged' : 'research.fullTextUnchanged') }}</p>
    </template>
    <ul><li v-for="limit in reportDiff.limitations || []" :key="limit">{{ limit }}</li></ul>
    <template v-if="evidenceDiff">
      <h4>{{ $t('research.evidenceComparison') }}</h4><p>{{ $t('research.evidenceComparisonHelp') }}</p>
      <div v-if="evidenceDiff.status === 'compared'" class="table-scroll"><table><thead><tr><th>{{ $t('research.declaredRelation') }}</th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody><tr v-for="key in countKeys" :key="key"><th>{{ countLabel(key) }}</th><td>{{ evidenceDiff.left?.counts?.[key] ?? '—' }}</td><td>{{ evidenceDiff.right?.counts?.[key] ?? '—' }}</td><td>{{ evidenceDiff.delta?.[key] ?? '—' }}</td></tr></tbody></table></div>
      <p v-else>{{ $t('research.reportComparisonUnavailable') }}</p>
      <details v-for="kind in ['added','removed']" :key="kind"><summary>{{ $t(`research.${kind}References`) }} ({{ evidenceDiff[kind]?.length || 0 }})</summary><article v-for="reference in evidenceDiff[kind] || []" :key="reference.reference_id" class="reference-diff"><p>{{ reference.subject_id }} · {{ countLabel(reference.relation) }} · {{ locationLabel(reference.validation?.location_status) }}</p><p>{{ reference.note }}</p><p class="muted">{{ reference.source_id }} · {{ reference.version_id }} · {{ reference.span_id }}</p><EventReferenceLink :project-id="projectId" :reference="reference" /><button v-if="reference.source_id" @click="$emit('inspect',reference)">{{ $t('research.inspect') }}</button></article></details>
      <ul><li v-for="limit in evidenceDiff.limitations || []" :key="limit">{{ limit }}</li></ul>
    </template>
  </section>
</template>
<script setup>
import EventReferenceLink from './EventReferenceLink.vue'
import {computed} from 'vue'
import {useI18n} from 'vue-i18n'
const props=defineProps({reportDiff:Object,evidenceDiff:Object,projectId:String})
defineEmits(['inspect'])
const {t,te}=useI18n()
const sides=computed(()=>[{key:'left',label:'A',report:props.reportDiff?.left},{key:'right',label:'B',report:props.reportDiff?.right}])
const countKeys=['supports','contradicts','insufficient','missing','invalid']
const countLabel=key=>te(`research.relations.${key}`)?t(`research.relations.${key}`):locationLabel(key)
const locationLabel=key=>te(`research.locations.${key}`)?t(`research.locations.${key}`):(key || t('research.notRecorded'))
const exclusion=reason=>reason==='report_incomplete'?t('research.excludedReportIncomplete'):t('research.excludedReportIdentity')
</script>
<style scoped>
.report-comparison{margin-top:24px;padding-top:16px;border-top:1px solid var(--studio-line)}h4{font-size:1rem;margin:16px 0}h5{font-size:.875rem;margin:12px 0;overflow-wrap:anywhere}.sides{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}p,li{font-size:.875rem;overflow-wrap:anywhere}.muted{color:var(--studio-muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;background:var(--studio-paper);font:.875rem/1.7 var(--studio-font);max-height:420px;overflow:auto}summary{min-height:44px;padding:12px 0;cursor:pointer;font-weight:600}.section-diff,.reference-diff{border-top:1px solid var(--studio-line)}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;border:1px solid var(--studio-line)}button,a{display:inline-flex;align-items:center;min-height:44px;padding:8px 12px;color:var(--studio-ink);background:var(--studio-paper);border:1px solid var(--theme-control-line);border-radius:8px;font:inherit;font-size:.875rem;text-decoration:none}@media(max-width:600px){.sides{grid-template-columns:1fr}}
</style>
