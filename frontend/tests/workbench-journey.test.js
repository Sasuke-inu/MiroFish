import {describe,it,expect} from 'vitest'
import {journeyState,selectRun,selectReport,reportCompleteness,sectionLocation,researchName,safeWorkbenchReturn} from '../src/utils/workbenchJourney'

const base={project:{project_id:'p',status:'created'},sources:{total:0},runs:[],reports:[]}
const state=(changes={},run=null,report=null,preparation=null)=>journeyState({...base,...changes},run,report,preparation)
describe('truthful research next steps',()=>{
 it('asks for sources only when neither indexed nor preserved inputs exist',()=>{expect(state().kind).toBe('empty');expect(state({sources:{total:1}}).kind).toBe('analyse');expect(state({project:{status:'created',total_text_length:20}}).kind).toBe('analyse')})
 it('distinguishes relationships from character preparation',()=>{expect(state({project:{status:'ontology_generated'}}).kind).toBe('relationships');expect(state({project:{status:'graph_completed'}}).kind).toBe('prepare')})
 it('never infers readiness from the graph or a ready label alone',()=>{const run={simulation_id:'s',status:'ready'};expect(state({},run).kind).toBe('check');expect(state({},run,null,{status:'ready',profiles_generated:true,config_generated:true,graph_namespace_status:'ready',runner_status:'idle'}).kind).toBe('ready')})
 it.each(['starting','running','stopping','finalizing'])('shows %s progress without a duplicate start',status=>{const result=state({}, {status});expect(result.kind).toBe('running');expect(result.canStop).toBe(status==='starting'||status==='running')})
 it('requires the existing completion and graph barrier for report generation',()=>{expect(state({},{status:'completed',graph_ready:true,run_id:'r'}).kind).toBe('report');expect(state({},{status:'completed',graph_ready:false}).kind).toBe('check')})
 it.each(['stopped','failed','interrupted','needs_review','unknown','paused'])('does not restart or claim full success for %s',status=>{expect(state({},{status}).kind).toBe('check')})
 it('keeps a saved partial report readable independently of graph readiness',()=>{const run={status:'stopped',graph_ready:false};const report={status:'failed',markdown_content:'saved'};expect(state({},run,report).kind).toBe('read');expect(reportCompleteness(report,run)).toBe('partial')})
 it('does not call a legacy or synthetic result verified model completion',()=>{expect(reportCompleteness({status:'completed'},{status:'completed',legacy:true})).toBe('legacy');expect(state({project:{demo:'story'}},{status:'completed'},{status:'completed'}).synthetic).toBe(true)})
 it('selects the requested interrupted simulation and never substitutes success',()=>{const runs=[{simulation_id:'old',status:'completed'},{simulation_id:'new',status:'interrupted'}];expect(selectRun(runs,'new')).toBe(runs[1]);expect(selectRun(runs,'missing')).toBeNull()})
 it('keeps the exact requested report version, including invalid selections',()=>{const reports=[{report_id:'r1',simulation_id:'s',version:1},{report_id:'r2',simulation_id:'s',version:2}];expect(selectReport(reports,'s','r1').version).toBe(1);expect(selectReport(reports,'s','missing')).toBeNull();expect(selectReport(reports,'other')).toBeNull()})
 it('maps all six old deep links into three first-level locations',()=>{expect(sectionLocation('runs')).toEqual({section:'results',panel:'process'});expect(sectionLocation('sources').section).toBe('data');expect(sectionLocation('references').section).toBe('data');expect(sectionLocation('reports').section).toBe('results');expect(sectionLocation('quality').section).toBe('results');expect(sectionLocation('plans').section).toBe('overview')})
 it('does not use an internal ID as the main unnamed title',()=>{expect(researchName({name:'Unnamed Project',created_at:'2026-10-03',project_id:'secret'},(key,p)=>`${key} ${p?.date||''}`)).not.toContain('secret')})
})


it('keeps safe workspace returns and rejects unrelated or external targets',()=>{expect(safeWorkbenchReturn('/workbench/p?section=results&replay=s')).toContain('replay=s');for(const value of ['https://evil.test','//evil.test','/settings','/workbench/../settings'])expect(safeWorkbenchReturn(value)).toBe('/workbench')})
it('keeps an older saved report readable while another version is generating',()=>{expect(state({tasks:[{status:'processing',task_type:'report_generate',metadata:{simulation_id:'s'}}]},{simulation_id:'s',status:'completed'},{status:'completed'}).kind).toBe('read')})
it('does not treat a pending report as a saved complete result',()=>{expect(state({},{status:'completed'},{status:'generating'}).kind).toBe('reporting')})

it('keeps graph preparation distinct from source analysis',()=>{expect(state({project:{project_id:'p',status:'graph_building'},tasks:[{status:'processing',task_type:'graph_build',metadata:{project_id:'p'}}]}).kind).toBe('relationshipsBusy')})
