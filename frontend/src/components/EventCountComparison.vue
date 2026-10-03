<template>
  <section class="event-count-comparison">
    <h4>{{ $t('research.eventCounts') }}</h4>
    <p v-if="!rows.length">{{ $t('research.noData') }}</p>
    <div v-else class="counts-table-scroll" tabindex="0" role="region" :aria-label="$t('research.eventCounts')">
      <table><caption>{{ $t('research.countDifferenceHelp') }}</caption><thead><tr><th scope="col">{{ $t('research.platform') }}</th><th scope="col">{{ $t('research.actionKind') }}</th><th scope="col">A</th><th scope="col">B</th><th scope="col">{{ $t('research.countDifference') }}</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="`${row.platform}:${row.kind}`"><th scope="row">{{ platformLabel(row.platform) }}</th><td>{{ actionLabel(row.kind) }}<small v-if="actionLabel(row.kind) !== row.kind">{{ row.kind }}</small></td><td>{{ row.left ?? '—' }}</td><td>{{ row.right ?? '—' }}</td><td>{{ row.delta ?? '—' }}</td></tr></tbody>
        <tfoot><tr><th colspan="2" scope="row">{{ $t('research.countTotal') }}</th><td>{{ totals.left ?? '—' }}</td><td>{{ totals.right ?? '—' }}</td><td>{{ totals.delta ?? '—' }}</td></tr></tfoot>
      </table>
    </div>
  </section>
</template>
<script setup>
import {computed} from 'vue'
import {useI18n} from 'vue-i18n'
const props=defineProps({counts:Object})
const {t,te}=useI18n()
const isMap=value=>value!==null&&typeof value==='object'&&!Array.isArray(value)
function savedCount(side,platform,kind){
  if(!isMap(side))return null
  if(!Object.hasOwn(side,platform))return 0
  if(!isMap(side[platform]))return null
  const value=Object.hasOwn(side[platform],kind)?side[platform][kind]:0
  return Number.isSafeInteger(value)&&value>=0?value:null
}
const rows=computed(()=>{
  const left=props.counts?.left,right=props.counts?.right
  return [...new Set([...Object.keys(isMap(left)?left:{}),...Object.keys(isMap(right)?right:{})])].sort().flatMap(platform=>{
    const kinds=[...new Set([...Object.keys(isMap(left?.[platform])?left[platform]:{}),...Object.keys(isMap(right?.[platform])?right[platform]:{})])].sort()
    return kinds.map(kind=>{const a=savedCount(left,platform,kind),b=savedCount(right,platform,kind);return {platform,kind,left:a,right:b,delta:a!==null&&b!==null?b-a:null}})
  })
})
const totals=computed(()=>{
  const sum=side=>rows.value.every(row=>row[side]!==null)?rows.value.reduce((total,row)=>total+row[side],0):null
  const left=sum('left'),right=sum('right')
  return {left,right,delta:left!==null&&right!==null?right-left:null}
})
const platformLabel=key=>te(`research.platformNames.${key}`)?t(`research.platformNames.${key}`):key
const actionLabel=key=>te(`research.actionKinds.${key}`)?t(`research.actionKinds.${key}`):key
</script>
<style scoped>
.event-count-comparison{min-width:0;max-width:100%;margin-top:20px}h4{font-size:1rem;margin:0 0 8px}.counts-table-scroll{max-width:100%;overflow-x:auto;overscroll-behavior-x:contain}table{width:100%;min-width:420px;border-collapse:collapse;font-size:.875rem}caption{text-align:left;padding:8px 0;color:var(--studio-muted)}th,td{text-align:left;vertical-align:top;padding:10px;border:1px solid var(--studio-line)}th,td:nth-child(2){overflow-wrap:anywhere;max-width:200px}td:nth-child(n+3){white-space:nowrap;font-variant-numeric:tabular-nums}small{display:block;color:var(--studio-muted);font-size:.75rem}tfoot{font-weight:600;background:var(--studio-paper)}
</style>
