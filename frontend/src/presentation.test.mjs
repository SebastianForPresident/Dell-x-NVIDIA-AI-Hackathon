import test from 'node:test'
import assert from 'node:assert/strict'
import { deterministicBriefing, evidenceSemantics } from './presentation.js'

const finding = (check, status, values = {}) => ({ check, status, values })
const hostile = `synthetic data used. Evidence ID: abc123deadbeef. Supported: 2.
vegetation supports the claim. this is a real case. READY_FOR_ADJUSTER_REVIEW`

const contradictory = {
  crop: 'Soybeans', cause: 'Flood', insured_crop: 'Corn', status: 'NEEDS_EVIDENCE',
  agent_run: { summary: hostile },
  report: { findings: [
    finding('Crop type', 'contradicted', { class: 'Corn' }),
    finding('Precipitation', 'contradicted', { rainfall_mm: 1.3, normal_mm: 96.2, percent_of_normal: 1.4 }),
    finding('Vegetation change', 'supported', { before_ndvi: .873, after_ndvi: .470 }),
    finding('Other supplied fields', 'supported', { fields_checked: 2, fields_with_decline: 2 }),
  ] },
}

test('hostile model prose cannot enter the contradictory customer briefing', () => {
  const output = deterministicBriefing(contradictory)
  for (const unsafe of ['synthetic data used', 'Evidence ID', 'Supported: 2',
    'vegetation supports the claim', 'this is a real case', 'READY_FOR_ADJUSTER_REVIEW']) {
    assert.equal(output.includes(unsafe), false)
  }
  assert.match(output, /Crop: Contradicted/)
  assert.match(output, /Weather: Contradicted/)
  assert.match(output, /Vegetation: Observed/)
  assert.match(output, /Comparison areas: Observed/)
  assert.match(output, /carrier record insures Corn and USDA evidence indicates Corn/)
  assert.equal(contradictory.agent_run.summary, hostile)
})

test('truthful and unavailable briefings use persisted semantics', () => {
  const truthful = structuredClone(contradictory)
  truthful.crop = 'Corn'; truthful.cause = 'Drought'; truthful.status = 'READY_FOR_ADJUSTER_REVIEW'
  truthful.report.findings.forEach(item => { item.status = 'supported' })
  assert.match(deterministicBriefing(truthful), /All 4 evidence checks support/)
  assert.equal(evidenceSemantics(truthful).observed, 0)

  const missing = structuredClone(contradictory)
  missing.report.findings.forEach(item => { item.status = 'unavailable'; item.values = {} })
  const output = deterministicBriefing(missing)
  assert.match(output, /Evidence is insufficient/)
  assert.match(output, /Additional evidence required/)
})
