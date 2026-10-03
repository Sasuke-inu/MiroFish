// Presentation only: the existing workflow still owns all execution checks.
export function sectionLocation(section, panel) {
  const legacy={sources:['data',''],references:['data','references'],runs:['results','process'],reports:['results',''],quality:['results','quality'],plans:['overview','plans']}
  const [main,child]=legacy[section] || [ ['overview','data','results'].includes(section)?section:'overview',panel || '' ]
  return {section:main,panel:child}
}
export function selectRun(runs=[], requested) {
  if(requested) return runs.find(run=>run.simulation_id===requested) || null
  // Old records may have no date. Keep the API order without claiming latest,
  // and never replace an explicit selection based on whether it succeeded.
  return runs[0] || null
}
export function selectReport(reports=[], simulationId, requested) {
  if(!simulationId) return null
  const candidates=reports.filter(report=>report.simulation_id===simulationId)
  if(requested) return candidates.find(report=>report.report_id===requested) || null
  return [...candidates].sort((a,b)=>(Number(b.version)||0)-(Number(a.version)||0)||String(b.created_at||'').localeCompare(a.created_at||''))[0] || null
}
export function reportCompleteness(report,run) {
  if(report?.status!=='completed'||(run && run.status!=='completed') || ['partial','incomplete'].includes(report?.manifest?.completeness)) return 'partial'
  if(run?.legacy || !report?.manifest?.completeness) return 'legacy'
  return 'complete'
}
export function journeyState(detail,run,report,preparation) {
  const project=detail?.project || {},status=preparation?.runner_status && preparation.runner_status!=='idle' ? preparation.runner_status : run?.status
  const synthetic=Boolean(project.demo||run?.manifest?.kind==='synthetic_fixture'||report?.manifest?.kind==='synthetic_fixture')
  const result=kind=>({kind,synthetic,canStop:['starting','running'].includes(status)})
  if(['starting','running','stopping','finalizing'].includes(status)) return result('running')
  const active=(detail?.tasks||[]).filter(task=>['pending','processing'].includes(task.status))
  if(report && !['pending','planning','generating'].includes(report.status)) return result('read')
  if(active.some(task=>task.task_type==='report_generate' && task.metadata?.simulation_id===run?.simulation_id && task.metadata?.simulation_id)) return result('reporting')
  if(['pending','planning','generating'].includes(report?.status)) return result('reporting')
  if(report) return result('read')
  if(active.some(task=>task.metadata?.simulation_id===run?.simulation_id && task.metadata?.simulation_id)) return result('preparing')
  if(active.some(task=>task.metadata?.project_id===project.project_id&&task.task_type==='graph_build')||project.status==='graph_building') return result('relationshipsBusy')
  if(active.some(task=>task.metadata?.project_id===project.project_id)) return result('analysing')
  if(status==='completed') return result(run.graph_ready===true&&run.run_id&&!run.legacy&&!synthetic?'report':'check')
  if(run){
    if(['ready','idle','created','preparing'].includes(status)) {
      if(preparation?.status==='ready'&&preparation.profiles_generated===true&&preparation.config_generated===true&&preparation.graph_namespace_status==='ready'&&preparation.runner_status==='idle') return result('ready')
      if(status==='preparing') return result('preparing')
      if(preparation && (!preparation.profiles_generated || !preparation.config_generated)) return result('prepare')
    }
    return result('check')
  }
  if(project.status==='graph_building') return result('relationshipsBusy')
  if(project.status==='graph_completed') return result('prepare')
  if(project.status==='ontology_generated') return result('relationships')
  if(project.status!=='created') return result('check')
  return result((detail?.sources?.total||project.total_text_length||project.files?.length)?'analyse':'empty')
}
export function researchName(project,t) {
  const name=project?.name?.trim()
  if(name && !['unnamed project','untitled'].includes(name.toLowerCase())) return name
  const date=new Date(project?.created_at)
  const label=Number.isNaN(date.getTime())?t('research.notRecorded'):date.toLocaleString(undefined,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})
  return t('journey.untitled',{date:label})
}
export function simulationName(run,runs,t) {
  if(run?.name) return run.name
  const index=runs.findIndex(item=>item.simulation_id===run?.simulation_id)
  return t('journey.simulationName',{number:index+1})+(run?.created_at?` · ${run.created_at.slice(0,10)}`:'')
}
export function safeWorkbenchReturn(value,fallback='/workbench') {
  return typeof value==='string' && /^\/workbench(?:\/[A-Za-z0-9_-]+)?(?:\?[^#]*)?$/.test(value)?value:fallback
}
