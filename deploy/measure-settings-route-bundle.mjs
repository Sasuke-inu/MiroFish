import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { gzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'

// Compare production assets from the same source snapshot. Follow static
// manifest imports only: dynamic routes are not part of Home's initial payload.
const [beforeDir, routerOnlyDir, afterDir, outputFile] = process.argv.slice(2)
if (!outputFile) throw new Error('Usage: node measure-settings-route-bundle.mjs BEFORE ROUTER_ONLY AFTER OUTPUT.json')

function measure(directory) {
  const manifest = JSON.parse(readFileSync(resolve(directory, '.vite/manifest.json'), 'utf8'))
  const seen = new Set()
  const files = new Set()
  function visit(key) {
    if (seen.has(key)) return
    seen.add(key)
    const chunk = manifest[key]
    if (!chunk) throw new Error(`Missing manifest entry: ${key}`)
    files.add(chunk.file)
    for (const css of chunk.css ?? []) files.add(css)
    for (const dependency of chunk.imports ?? []) visit(dependency)
  }
  for (const [key, chunk] of Object.entries(manifest)) if (chunk.isEntry) visit(key)
  const assets = [...files].sort().map(file => {
    const content = readFileSync(resolve(directory, file))
    return {
      file,
      type: file.endsWith('.css') ? 'css' : 'js',
      bytes: content.length,
      gzipBytes: gzipSync(content).length,
      sha256: createHash('sha256').update(content).digest('hex'),
    }
  })
  const total = type => assets.filter(asset => !type || asset.type === type).reduce((sum, asset) => ({ bytes: sum.bytes + asset.bytes, gzipBytes: sum.gzipBytes + asset.gzipBytes }), { bytes: 0, gzipBytes: 0 })
  return { initialAssets: assets, totals: { js: total('js'), css: total('css'), combined: total() }, settingsChunk: manifest['src/views/SettingsView.vue'] ?? null }
}

const before = measure(beforeDir)
const routerOnly = measure(routerOnlyDir)
const after = measure(afterDir)
const reduction = Object.fromEntries(['js', 'css', 'combined'].map(type => [type, {
  bytes: before.totals[type].bytes - after.totals[type].bytes,
  percent: Number(((1 - after.totals[type].bytes / before.totals[type].bytes) * 100).toFixed(2)),
  gzipBytes: before.totals[type].gzipBytes - after.totals[type].gzipBytes,
  gzipPercent: Number(((1 - after.totals[type].gzipBytes / before.totals[type].gzipBytes) * 100).toFixed(2)),
}]))
const report = {
  baselineCommit: 'd354592afda283f3aca572f93ac552ad287cbd1a',
  method: 'Vite 7.3.6 production builds from the same archived frontend/locales snapshot; manifest static import closure; Node gzip per asset. Router-only experiment retains the eager App.vue SettingsView import. Final experiment changes SettingsView to dynamic loading in both router and App.',
  excludes: ['HTML, images and fonts', 'dynamic route assets until navigation', 'real network transfer timing', 'LCP, INP, CLS and Lighthouse measurements'],
  before,
  routerOnly,
  after,
  reduction,
}
writeFileSync(outputFile, `${JSON.stringify(report, null, 2)}\n`)
console.log(JSON.stringify({ before: before.totals, routerOnly: routerOnly.totals, after: after.totals, reduction }, null, 2))
