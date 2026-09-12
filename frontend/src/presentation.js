export function evidenceSemantics(investigation) {
  const findings = investigation.report?.findings || []
  const contradicted = findings.filter(item => item.status === 'contradicted').length
  const unavailable = findings.filter(item => ['unavailable', 'inconclusive'].includes(item.status)).length
  const displayStatus = finding => contradicted > 0 && finding.status === 'supported' &&
    ['Vegetation change', 'Other supplied fields'].includes(finding.check) ? 'observed' : finding.status
  return { findings, contradicted, unavailable, displayStatus,
    observed: findings.filter(item => displayStatus(item) === 'observed').length }
}

export function presentationCaseStatus(investigation) {
  const { contradicted, unavailable } = evidenceSemantics(investigation)
  if (contradicted > 0 && unavailable === 0) return 'Contradicted — human review required'
  const labels = { NEW: 'Queued', INVESTIGATING: 'Investigating', NEEDS_EVIDENCE: 'Needs evidence',
    READY_FOR_ADJUSTER_REVIEW: 'Ready for adjuster review' }
  return labels[investigation.status] || investigation.status
}

export function hasLocalEvidence(investigation) {
  if (typeof investigation.local_evidence_available === 'boolean') return investigation.local_evidence_available
  const findings = investigation.report?.findings || []
  return findings.some(item => !['unavailable', 'inconclusive'].includes(item.status)) || (investigation.documents?.length || 0) > 1
}

const number = (value, digits = 1) => Number(value).toFixed(digits)

export function deterministicBriefing(investigation) {
  const { findings, contradicted, unavailable, displayStatus } = evidenceSemantics(investigation)
  if (!findings.length) return investigation.status === 'INVESTIGATING'
    ? '## Investigation summary\n\nThe local agent is inspecting the registered evidence package. Persisted findings will appear here as each check completes.'
    : '## Investigation summary\n\nStart the investigation to evaluate the registered evidence package.'

  const crop = findings.find(item => item.check === 'Crop type')
  const rain = findings.find(item => item.check === 'Precipitation')
  const vegetation = findings.find(item => item.check === 'Vegetation change')
  const neighbors = findings.find(item => item.check === 'Other supplied fields')
  const lines = []
  if (crop) {
    const status = displayStatus(crop)
    const observed = crop.values?.class
    const detail = status === 'unavailable' ? 'Local crop-classification evidence was unavailable.'
      : status === 'contradicted' ? `the carrier record insures ${investigation.insured_crop || 'a different crop'} and USDA evidence indicates ${observed}.`
        : `USDA evidence indicates ${observed}, matching the reported crop.`
    lines.push(`- **Crop: ${label(status)}** — ${detail}`)
  }
  if (rain) {
    const status = displayStatus(rain)
    const values = rain.values || {}
    const detail = status === 'unavailable' ? 'Local rainfall evidence was unavailable.'
      : `rainfall was ${number(values.rainfall_mm)} mm versus ${number(values.normal_mm)} mm normal (${number(values.percent_of_normal)}% of normal).`
    lines.push(`- **Weather: ${label(status)}** — ${detail}`)
  }
  if (vegetation) {
    const status = displayStatus(vegetation)
    const values = vegetation.values || {}
    const detail = status === 'unavailable' ? 'Local vegetation imagery was unavailable.'
      : `NDVI declined from ${number(values.before_ndvi, 3)} to ${number(values.after_ndvi, 3)}. ${status === 'observed' ? `Vegetation stress was observed, but it does not support the reported ${String(investigation.cause).toLowerCase()} cause.` : 'The measured decline is consistent with the reported conditions.'}`
    lines.push(`- **Vegetation: ${label(status)}** — ${detail}`)
  }
  if (neighbors) {
    const status = displayStatus(neighbors)
    const values = neighbors.values || {}
    const detail = status === 'unavailable' ? 'Local comparison-area imagery was unavailable.'
      : `${values.fields_with_decline ?? 0} of ${values.fields_checked ?? 0} comparison areas showed similar vegetation decline. ${status === 'observed' ? `This does not validate the reported ${investigation.crop} crop or ${String(investigation.cause).toLowerCase()} cause.` : 'The comparison is consistent with the reported conditions.'}`
    lines.push(`- **Comparison areas: ${label(status)}** — ${detail}`)
  }
  const assessment = contradicted > 0 ? 'Available evidence contradicts important parts of the reported conditions.'
    : unavailable > 0 ? 'Evidence is insufficient to complete the investigation.'
      : `All ${findings.length} evidence checks support the reported conditions.`
  const next = contradicted > 0 ? 'Human review required.' : unavailable > 0 ? 'Additional evidence required.' : 'Ready for adjuster review.'
  return `## Investigation summary\n\n### Reported conditions\n\n- Reported crop: ${investigation.crop}\n- Reported cause: ${investigation.cause}\n\n### Evidence findings\n\n${lines.join('\n')}\n\n### Assessment\n\n${assessment}\n\n### Next step\n\n${next}`
}

function label(status) {
  return status === 'observed' ? 'Observed' : status === 'supported' ? 'Supported' :
    status === 'contradicted' ? 'Contradicted' : 'Unavailable'
}
