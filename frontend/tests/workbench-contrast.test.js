import {describe,expect,it} from 'vitest'
import {readFileSync} from 'node:fs'

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8')
const studio=read('../src/styles/studio.css'),theme=read('../src/styles/theme.css')
const declarations=body=>Object.fromEntries([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(match=>[match[1],match[2].trim()]))
const light={...declarations(studio.match(/:root\s*\{([^}]+)\}/)[1]),...declarations(theme.match(/:root\s*\{([^}]+)\}/)[1])}
const dark={...light,...declarations(theme.match(/:root\[data-theme='dark'\]\s*\{([^}]+)\}/)[1])}
function resolve(tokens,name){const value=tokens[name];const variable=value?.match(/^var\((--[\w-]+)\)$/);return variable?resolve(tokens,variable[1]):value}
function luminance(hex){const rgb=hex.slice(1).match(/../g).map(part=>parseInt(part,16)/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]}
function contrast(a,b){const [bright,dark]=[luminance(a),luminance(b)].sort((a,b)=>b-a);return (bright+.05)/(dark+.05)}

describe.each([['light',light],['dark',dark]])('%s research control contrast',(_,tokens)=>{
  it.each(['--studio-paper','--studio-surface'])('keeps control edges distinguishable on %s',background=>{
    expect(contrast(resolve(tokens,'--theme-control-line'),resolve(tokens,background))).toBeGreaterThanOrEqual(3)
  })
  it.each(['--studio-paper','--studio-surface'])('keeps warm labels and ordinary control text readable on %s',background=>{
    for(const text of ['--theme-accent-text','--studio-ink','--studio-muted'])expect(contrast(resolve(tokens,text),resolve(tokens,background))).toBeGreaterThanOrEqual(4.5)
  })
  it('keeps filled action text readable',()=>{expect(contrast(resolve(tokens,'--theme-on-filled'),resolve(tokens,'--studio-button'))).toBeGreaterThanOrEqual(4.5)})
})

it.each(['../src/views/WorkbenchView.vue','../src/components/EvidenceInspector.vue','../src/components/RunReplay.vue','../src/components/StageConnections.vue','../src/components/WorkbenchNavigation.vue','../src/components/ReportVersionAction.vue','../src/components/ReportComparison.vue','../src/components/EvidenceLinks.vue','../src/components/EventReferenceLink.vue'])('applies the tested token to outlined controls in %s',path=>{
  const css=read(path).split('<style scoped>')[1]
  const controls=[...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([,selector,body])=>/\b(button|input|select|textarea)\b|\.button\b|\.event-reference-link\b/.test(selector)&&/border\s*:\s*1px solid/.test(body))
  expect(controls.length).toBeGreaterThan(0)
  for(const [,selector,body] of controls)expect(body,selector).toMatch(/border\s*:\s*1px solid var\(--theme-control-line\)/)
})

it('keeps sidebar labels on the tested warm text token and search text on one line',()=>{
  expect(theme).toContain('#app .project-index { color: var(--theme-accent-text); }')
  const css=read('../src/views/WorkbenchView.vue').split('<style scoped>')[1]
  const button=css.match(/\.search-row\s*>\s*button\s*\{([^}]+)\}/)[1]
  expect(button).toMatch(/white-space:\s*nowrap/)
  expect(button).toMatch(/flex-shrink:\s*0/)
  expect(button).toMatch(/min-width:\s*64px/)
  expect(css).toMatch(/\.record\s*\{[^}]*border-bottom:\s*1px solid var\(--studio-line\)/)
})

it('places primary content above the sidebar at the 390px mobile width',()=>{
  const css=read('../src/views/WorkbenchView.vue').split('<style scoped>')[1]
  const mobile=css.slice(css.indexOf('@media(max-width:959px)'))
  expect(mobile).toMatch(/\.research-layout\s*\{[^}]*grid-template-columns:\s*1fr/)
  expect(mobile).toMatch(/\.research-content\s*\{[^}]*grid-row:\s*1/)
  expect(mobile).toMatch(/\.project-index\s*\{[^}]*grid-row:\s*2/)
})
