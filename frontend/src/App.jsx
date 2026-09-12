import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import fieldTraceLogo from './assets/fieldtrace-logo.png'
import {
  Activity, ArrowRight, Check, CheckCircle2, ChevronRight, CloudRain,
  Database, Download, FileText, Leaf, MapPin, Menu, Plus, ShieldCheck,
  Sparkles, UploadCloud, X,
} from 'lucide-react'

const evidenceOrder = [
  { check: 'Precipitation', label: 'Weather', key: 'weather', icon: CloudRain },
  { check: 'Vegetation change', label: 'Vegetation', key: 'vegetation', icon: Activity },
  { check: 'Crop type', label: 'Crop', key: 'crop', icon: Leaf },
  { check: 'Other supplied fields', label: 'Neighbor fields', key: 'neighbors', icon: MapPin },
]

async function api(path, options) {
  const response = await fetch(path, options)
  const data = await response.json()
  if (!response.ok) {
    const detail = data.detail || `Request failed (${response.status})`
    throw new Error(Array.isArray(detail) ? detail.map(item => item.msg).join(', ') : detail)
  }
  return data
}

function dateLabel(value) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusLabel(status) {
  return status === 'supported' ? 'Supported' : status === 'contradicted' ? 'Contradicted' :
    status === 'inconclusive' ? 'Inconclusive' : 'Unavailable'
}

function caseStatus(status) {
  return ({ NEW: 'Queued', INVESTIGATING: 'Investigating', NEEDS_EVIDENCE: 'Needs evidence',
    READY_FOR_ADJUSTER_REVIEW: 'Evidence ready' })[status] || status
}

const workflowLabels = {
  get_claim: 'Claim loaded',
  check_crop_classification: 'Crop classification checked',
  check_rainfall: 'Rainfall evidence checked',
  check_vegetation_change: 'Vegetation change measured',
  compare_neighboring_fields: 'Neighboring fields compared',
  save_investigation_report: 'Investigation report saved',
  create_follow_up_task: 'Follow-up requested',
  set_case_status: 'Case status updated',
  openclaw_run: 'Local agent completed',
}

function workflowLabel(name) {
  return workflowLabels[name] || name.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase())
}

function isRegressionCase(item) {
  if (item.origin === 'demo' || item.synthetic_demo) return true
  const identity = [item.claim_id, item.farm, item.claim_description].filter(Boolean).join(' ')
  return /(browser[ -]?verification|missing evidence browser|final regression|\bregression\b|\bqa\b|\btest\b|\bsmoke\b|\brehearsal\b)/i.test(identity)
}

function FieldMap({ boundary, selectedField = 0 }) {
  const features = boundary?.features || []
  const rings = features.flatMap((feature, index) => {
    const geometry = feature.geometry
    const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : geometry?.type === 'MultiPolygon' ? geometry.coordinates : []
    return polygons.map(polygon => ({ index, ring: polygon[0] }))
  })
  const points = rings.flatMap(item => item.ring)
  if (!points.length) return <div className="map-empty">No boundary supplied</div>
  const west = Math.min(...points.map(point => point[0]))
  const east = Math.max(...points.map(point => point[0]))
  const south = Math.min(...points.map(point => point[1]))
  const north = Math.max(...points.map(point => point[1]))
  const x = longitude => 35 + ((longitude - west) / Math.max(east - west, 0.000001)) * 450
  const y = latitude => 260 - ((latitude - south) / Math.max(north - south, 0.000001)) * 215
  const labels = rings.map(({ index, ring }) => ({ index,
    cx: ring.reduce((sum, point) => sum + x(point[0]), 0) / ring.length,
    cy: ring.reduce((sum, point) => sum + y(point[1]), 0) / ring.length }))
  return <div className="field-map technical-map">
    <svg viewBox="0 0 520 300" role="img" aria-label="Claimed field and comparison field boundaries">
      <defs><pattern id="field-grid" width="26" height="26" patternUnits="userSpaceOnUse"><path d="M26 0H0V26" fill="none" stroke="#d8dfda" strokeWidth="0.7" /></pattern></defs>
      <rect width="520" height="300" fill="#f4f6f4" /><rect width="520" height="300" fill="url(#field-grid)" />
      {rings.map(({ index, ring }, i) => <polygon key={`${index}-${i}`} points={ring.map(point => `${x(point[0])},${y(point[1])}`).join(' ')}
        fill={index === selectedField ? '#8cb99a' : '#d1ddd3'} stroke={index === selectedField ? '#174f32' : '#789080'} strokeWidth="1.8" />)}
      {labels.map(label => <g key={`label-${label.index}`}><circle cx={label.cx} cy={label.cy} r="3" fill="#173c29" /><text x={label.cx + 7} y={label.cy - 5}>{label.index === selectedField ? 'Analysis area' : `Comparison ${label.index}`}</text></g>)}
      <text className="coordinate" x="12" y="20">{north.toFixed(4)}° N</text><text className="coordinate" x="12" y="290">{south.toFixed(4)}° N</text>
    </svg>
    <span className="map-caption"><span><span className="legend-dot" /> Selected crop analysis area</span><small>{Math.abs(west).toFixed(4)}° W to {Math.abs(east).toFixed(4)}° W · USDA CDL-derived regions, not cadastral parcels</small></span>
  </div>
}

function NdviComparison({ points = [], provenance }) {
  if (points.length < 2) return <p className="muted">No vegetation time series supplied.</p>
  const before = points[0], after = points.at(-1), delta = after.ndvi - before.ndvi
  const y = value => 96 - Math.max(0, Math.min(1, value)) * 78
  return <div className="ndvi-comparison"><svg viewBox="0 0 320 112" role="img" aria-label={`NDVI before ${before.ndvi.toFixed(3)}, after ${after.ndvi.toFixed(3)}`}>
    {[0, .5, 1].map(value => <g key={value}><line x1="34" y1={y(value)} x2="305" y2={y(value)} stroke="#dce4de" /><text x="4" y={y(value) + 4}>{value.toFixed(1)}</text></g>)}
    <line x1="90" y1={y(before.ndvi)} x2="250" y2={y(after.ndvi)} stroke="#316e4a" strokeWidth="2.5" />
    {[[90, before], [250, after]].map(([cx, point]) => <g key={point.date}><circle cx={cx} cy={y(point.ndvi)} r="5" fill="#174f32" /><text className="value" x={cx} y={y(point.ndvi) - 11} textAnchor="middle">{point.ndvi.toFixed(3)}</text></g>)}
  </svg><div className="ndvi-labels"><span>Before<br /><strong>{dateLabel(before.date)}</strong></span><span>After<br /><strong>{dateLabel(after.date)}</strong></span></div><p className="ndvi-delta">Change <strong>{delta.toFixed(3)}</strong> ({before.ndvi ? `${((delta / before.ndvi) * 100).toFixed(1)}%` : 'percent unavailable'})</p><small>{provenance?.before?.provider || 'Registered imagery'} · {provenance?.before?.product || 'red/NIR bands'}</small></div>
}

function UploadModal({ onClose, onCreated }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [files, setFiles] = useState({})
  const fileFields = [
    ['boundary', 'Field boundary', '.geojson,.json', true],
    ['weather', 'Weather CSV', '.csv', false],
    ['crop_layer', 'Crop layer GeoTIFF', '.tif,.tiff', false],
    ['before_image', 'Before image', '.tif,.tiff', false],
    ['after_image', 'After image', '.tif,.tiff', false],
    ['claim_pdf', 'Claim PDF', '.pdf', false],
  ]
  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const result = await api('/api/cases/analyze', { method: 'POST', body: new FormData(event.currentTarget) })
      onCreated(result)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="upload-modal" role="dialog" aria-modal="true" aria-label="Import a case">
      <div className="modal-heading"><div><span className="eyebrow">LOCAL CASE INTAKE</span><h2>Import an evidence package</h2><p>The case is measured locally and saved to MongoDB. Evidence assets are retained for investigation.</p></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={20} /></button></div>
      <form onSubmit={submit}><div className="modal-scroll">
        <div className="form-grid">
          <label>Claim ID<input name="claim_id" required placeholder="CLM-2842" /></label>
          <label>Farm / policyholder<input name="farm" required placeholder="Farm name" /></label>
          <label>Location<input name="location" placeholder="County, State" /></label>
          <label>Loss date<input name="loss_date" type="date" required defaultValue="2026-07-18" /></label>
          <label>Reported cause<select name="cause" defaultValue="Drought"><option>Drought</option><option>Flood</option><option>Other</option></select></label>
          <label>Claimed crop<select name="crop" defaultValue="Corn"><option>Corn</option><option>Soybeans</option><option>Winter wheat</option><option>Other</option></select></label>
          <label>Field area, acres<input name="acreage" type="number" min="0" defaultValue="0" /></label>
        </div>
        <h3 className="form-subtitle">Evidence files <small>Boundary required · remaining files optional</small></h3>
        <div className="file-grid">{fileFields.map(([name, label, accept, required]) => <label className={`file-input ${files[name] ? 'chosen' : ''}`} key={name}><UploadCloud size={18} /><span><strong>{label}</strong><small>{files[name] || (required ? 'Required' : 'Optional')}</small></span><input name={name} type="file" accept={accept} required={required} onChange={event => setFiles(current => ({ ...current, [name]: event.target.files?.[0]?.name }))} /></label>)}</div>
        <details className="advanced"><summary>Image dates and band settings</summary><div className="form-grid"><label>Before image date<input name="before_date" type="date" required defaultValue="2026-05-30" /></label><label>After image date<input name="after_date" type="date" required defaultValue="2026-08-12" /></label><label>Red band<input name="red_band" type="number" min="1" defaultValue="1" /></label><label>NIR band<input name="nir_band" type="number" min="1" defaultValue="2" /></label><label>Weather units<select name="weather_unit" defaultValue="mm"><option value="mm">Millimeters</option><option value="inches">Inches</option></select></label></div></details>
        <input type="hidden" name="selected_field" value="0" />
        <label className="check-label"><input type="checkbox" name="synthetic_demo" value="true" /> Mark this as synthetic demo data</label>
        {error && <p className="error-message">{error}</p>}
      </div><div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy}>{busy ? 'Analyzing files…' : 'Save evidence package'} <ArrowRight size={17} /></button></div></form>
    </div>
  </div>
}

function ClaimModal({ onClose, onCreated, onAdvanced }) {
  const [fields, setFields] = useState([])
  const [fieldId, setFieldId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { api('/api/local-fields').then(setFields).catch(err => setError(err.message)) }, [])
  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError('')
    const body = Object.fromEntries(new FormData(event.currentTarget))
    try {
      onCreated(await api('/api/claims', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }))
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const field = fields.find(item => item.id === fieldId)
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="upload-modal" role="dialog" aria-modal="true" aria-label="New claim">
      <div className="modal-heading"><div><span className="eyebrow">NEW INVESTIGATION</span><h2>Tell us about the claim</h2><p>Describe the loss. The agent will inspect evidence already available for the selected field.</p></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={20} /></button></div>
      <form onSubmit={submit}><div className="modal-scroll">
        <label className="claim-input">Farmer or farm name<input name="farm" required maxLength={200} placeholder="Enter the claimant’s name" /></label>
        <label className="claim-input">Claim statement<textarea name="description" required minLength={10} maxLength={2000} rows={4} placeholder="Describe what happened, when the damage was noticed, and what the farmer is claiming." /></label>
        <label className="claim-input" htmlFor="claim-field">Field<select id="claim-field" name="field_id" required value={fieldId} onChange={event => setFieldId(event.target.value)}><option value="" disabled>Select a field</option>{fields.map(item => <option key={item.id} value={item.id}>{item.name}{item.synthetic ? ' · synthetic fixture' : ' · public evidence'}</option>)}<option value="unregistered">Another field — no local evidence registered</option></select></label>
        {field && <div className="coverage-note"><strong>Local evidence available · {field.synthetic ? 'synthetic regression fixture' : 'cached public datasets'}</strong><p>{field.location}. {field.coverage}</p><small>Rainfall: {field.weather_start} to {field.weather_end}. Imagery: {field.before_date} and {field.after_date}.</small></div>}
        {fieldId === 'unregistered' && <><label className="claim-input">Field location<input name="location" required maxLength={200} placeholder="County, state or field reference" /></label><p className="coverage-note">No matching field data is registered. The agent can identify missing evidence and request follow-up; it cannot measure an unregistered field.</p></>}
        <div className="form-grid"><label>Loss date<input key={field?.default_loss_date || fieldId} name="loss_date" type="date" required defaultValue={field?.default_loss_date || ''} /></label><label>Reported cause<select name="cause" defaultValue="Drought"><option>Drought</option><option>Flood</option><option>Other</option></select></label><label>Claimed crop<select name="crop" defaultValue="Corn"><option>Corn</option><option>Soybeans</option><option>Winter wheat</option><option>Other</option></select></label><label>Claim reference (optional)<input name="claim_id" maxLength={100} placeholder="Generated if left blank" /></label></div>
        {error && <p className="error-message">{error}</p>}
        <button type="button" className="text-link intake-advanced" onClick={onAdvanced}>Advanced: import your own evidence files</button>
      </div><div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy}>{busy ? 'Creating claim…' : 'Create claim'} <ArrowRight size={17} /></button></div></form>
    </div>
  </div>
}

function useReceivedText(text, streaming) {
  const [displayed, setDisplayed] = useState(text)
  const target = useRef(text)
  const current = useRef(text)
  const active = useRef(streaming)
  useEffect(() => { target.current = text; active.current = streaming }, [text, streaming])
  useEffect(() => {
    let frame
    let last = 0
    function render(now) {
      if (now - last >= 16 && current.current !== target.current) {
        const next = target.current
        // Only reveal text already received. Revisions and saved reports apply immediately.
        current.current = !active.current || !next.startsWith(current.current)
          ? next : next.slice(0, current.current.length + Math.max(2, Math.ceil((next.length - current.current.length) / 5)))
        setDisplayed(current.current)
        last = now
      }
      frame = requestAnimationFrame(render)
    }
    frame = requestAnimationFrame(render)
    return () => cancelAnimationFrame(frame)
  }, [])
  return displayed
}

function BriefingText({ text }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ({ children }) => <div className="markdown-table"><table>{children}</table></div> }}>{text}</ReactMarkdown>
}

function AgentReport({ investigation }) {
  const [live, setLive] = useState(null)
  useEffect(() => {
    setLive(null)
    const source = new EventSource(`/api/cases/${encodeURIComponent(investigation.id)}/agent-stream`)
    source.onmessage = event => setLive(JSON.parse(event.data))
    return () => source.close()
  }, [investigation.id])
  const running = live?.state === 'running'
  const completed = live?.state === 'complete' || !!investigation.agent_run
  const text = live?.text || (!running && investigation.agent_run?.summary) || ''
  const displayedText = useReceivedText(text, running)

  return <section className="surface agent-report" aria-label="GPT-OSS live report">
    <div className="surface-heading"><div><span className="eyebrow">GPT-OSS · LOCAL ON GB10</span><h2>Investigation briefing</h2></div><span className={`count-tag ${running ? 'streaming' : ''}`}>{running ? (text ? 'Writing briefing' : 'Inspecting evidence') : live?.state === 'failed' ? 'Run interrupted' : text ? 'Saved briefing' : completed ? 'No briefing returned' : 'Awaiting investigation'}</span></div>
    <p className="muted">Live model output and measured tool results. {investigation.synthetic_demo ? 'This case uses synthetic evidence.' : 'Human adjuster review required.'}</p>
    <div className="agent-report-text" aria-live="polite">{displayedText ? <BriefingText text={displayedText} /> : (running ? 'The local model is reviewing the claim and selecting evidence checks…' : completed ? 'The investigation completed without a model briefing. Review the measured findings and follow-up tasks below.' : 'Start the investigation below to receive a briefing from the local model.')}</div>
    {running && <div className="live-progress"><Activity size={15} /><span>{live.tools?.find(tool => tool.state === 'running')?.name.replaceAll('_', ' ') || `${live.tools?.filter(tool => tool.state === 'complete').length || 0} evidence actions completed`}</span></div>}
    {!!live?.tools?.length && <details className="agent-live-tools"><summary>Evidence inspected · {live.tools.filter(tool => tool.state === 'complete').length} completed actions</summary>{live.tools.map(tool => <div key={tool.id}><strong>{tool.name.replaceAll('_', ' ')}</strong><span>{tool.state === 'running' ? 'Measuring…' : tool.finding?.detail || (tool.state === 'failed' ? 'Could not complete this check' : 'Saved')}</span>{tool.finding && <small>Source: {tool.finding.source}</small>}</div>)}</details>}
    <div className="assessment-note"><ShieldCheck size={18} /> Evidence briefing only. The human adjuster makes the decision.</div>
  </section>
}

export default function App() {
  const [page, setPage] = useState('home')
  const [cases, setCases] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [claimOpen, setClaimOpen] = useState(false)
  const [showTestHistory, setShowTestHistory] = useState(false)
  const [investigating, setInvestigating] = useState(false)
  const [actionError, setActionError] = useState('')
  const [reportOpen, setReportOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    api('/api/cases').then(setCases)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    let live = true
    const timer = setInterval(() => api('/api/cases').then(rows => { if (live) { setCases(rows); setActionError('') } })
      .catch(err => { if (live) setActionError(err.message) }), 5000)
    return () => { live = false; clearInterval(timer) }
  }, [])

  const sortedCases = [...cases].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
  const defaultCases = sortedCases.filter(item => !isRegressionCase(item)).slice(0, 5)
  const regressionCases = sortedCases.filter(isRegressionCase)
  const visibleCases = showTestHistory ? [...defaultCases, ...regressionCases] : defaultCases
  const selected = cases.find(item => item.id === selectedId) || visibleCases[0]
  const readyCount = defaultCases.filter(item => item.status === 'READY_FOR_ADJUSTER_REVIEW').length
  const reviewCount = defaultCases.filter(item => item.status === 'NEEDS_EVIDENCE').length
  const demoCase = visibleCases[0]

  function navigate(next) { setPage(next); setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  function openCase(item) { setSelectedId(item.id); setReportOpen(false); navigate('claim') }
  function onCreated(item) { setCases(current => [item, ...current]); setSelectedId(item.id); setUploadOpen(false); setClaimOpen(false); navigate('claim') }

  async function loadExample() {
    try {
      const item = await api('/api/demo/reset', { method: 'POST' })
      setShowExamples(true)
      onCreated(item)
    } catch (err) { setActionError(err.message) }
  }

  async function runInvestigation() {
    if (!selected) return
    let caseId = selected.id
    setInvestigating(true); setActionError('')
    try {
      if (selected.report_saved && selected.origin === 'demo') {
        const fresh = await api('/api/demo/reset', { method: 'POST' })
        caseId = fresh.id
        setCases(current => [fresh, ...current])
        setSelectedId(caseId)
      }
      const result = await api(`/api/cases/${encodeURIComponent(caseId)}/investigate`, { method: 'POST' })
      setCases(current => current.map(item => item.id === caseId ? result : item))
    } catch (err) { setActionError(err.message) }
    finally { setInvestigating(false) }
  }


  return <div className="site-shell">
    <header className="site-header"><button className="brand" onClick={() => navigate('home')}><span className="brand-icon"><img src={fieldTraceLogo} alt="" /></span><span>FieldTrace<small>LOCAL CROP FORENSICS</small></span></button><nav className={menuOpen ? 'open' : ''} aria-label="Main navigation">{[['home', 'Home'], ['dashboard', 'Dashboard'], ['claim', 'Claim investigation']].map(([key, label]) => <button key={key} className={page === key ? 'active' : ''} onClick={() => navigate(key)}>{label}</button>)}</nav><div className="header-right"><span className="local-badge"><span /> LOCAL SYSTEM</span><button className="menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation"><Menu size={22} /></button></div></header>

    {page === 'home' && <main className="home-page"><section className="home-hero"><div className="home-copy"><span className="eyebrow">DELL × NVIDIA AI HACKATHON</span><h1>Crop-loss evidence,<br /><em>ready for review.</em></h1><p>FieldTrace is a local AI evidence assistant for crop insurance adjusters. It brings weather, crop, vegetation, and neighboring-field signals into one reviewable investigation.</p><div className="hero-actions"><button className="button primary" onClick={() => setClaimOpen(true)}>New claim <ArrowRight size={18} /></button><button className="button secondary" onClick={loadExample}>Try a synthetic example <ChevronRight size={18} /></button></div><div className="hero-note"><ShieldCheck size={19} /><span>Evidence for a human adjuster. No automated claim decisions.</span></div></div><div className="hero-visual"><div className="hero-card-top"><span>LOCAL EVIDENCE LIBRARY</span><span className="signal"><span /> CACHED LOCALLY</span></div><div className="hero-claim"><span>DEWITT CROP ANALYSIS AREA</span><strong>Fictional claim · real public evidence</strong><small>USDA · NOAA · Copernicus Sentinel-2</small></div><div className="hero-flow">{['Claim context', 'Weather & crop', 'Vegetation & neighbors', 'Adjuster report'].map((step, index) => <div key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong><CheckCircle2 size={18} /></div>)}</div><div className="hero-card-bottom"><Sparkles size={17} /> Local autonomous investigation · gpt-oss:20b</div></div></section><section className="home-section"><div className="section-title"><span className="eyebrow">ONE CLEAR WORKFLOW</span><h2>From claim to evidence package</h2></div><div className="how-grid">{[['01', 'Select a claim', 'Write a claim and select a field with locally available evidence.'], ['02', 'Review measured evidence', 'See rainfall, crop classification, NDVI, and nearby-field checks with sources.'], ['03', 'Run the local agent', 'Let the agent choose evidence checks and prepare a report for the adjuster.']].map(([number, title, copy]) => <div className="how-card" key={title}><span>{number}</span><h3>{title}</h3><p>{copy}</p></div>)}</div></section><section className="value-strip"><div><strong>Faster investigations</strong><span>One place for the evidence package.</span></div><div><strong>Private by design</strong><span>Claims and data stay on the local system.</span></div><div><strong>Human decision making</strong><span>Adjusters decide; FieldTrace prepares evidence.</span></div></section></main>}

    {page !== 'home' && <main className="app-page">{loading ? <div className="page-state">Loading local cases…</div> : error ? <div className="page-state error"><Database size={30} /><h2>Backend unavailable</h2><p>{error}</p><p>Start MongoDB and FastAPI, then refresh.</p></div> : page === 'dashboard' ? <>
      <div className="page-intro"><div><span className="eyebrow">LOCAL CLAIM WORKSPACE</span><h1>Investigation dashboard</h1><p>Saved cases and evidence packages from the local MongoDB.</p></div><button className="button primary" onClick={() => setClaimOpen(true)}><Plus size={18} /> New claim</button></div>
      <div className="metric-grid"><div><span>Active claims</span><strong>{defaultCases.length}</strong><small>In the working queue</small></div><div><span>Evidence ready</span><strong>{readyCount}</strong><small>For adjuster review</small></div><div><span>Need review</span><strong>{reviewCount}</strong><small>Incomplete or inconclusive</small></div></div>
      <div className="dashboard-grid"><section className="surface"><div className="surface-heading"><div><span className="eyebrow">CLAIM QUEUE</span><h2>Open a case</h2></div><span className="count-tag">{defaultCases.length} active claims</span></div><label className="check-label history-toggle"><input type="checkbox" checked={showTestHistory} onChange={event => setShowTestHistory(event.target.checked)} /> Show test / regression history ({regressionCases.length})</label><div className="claim-list">{!visibleCases.length && <div className="empty-claims"><h3>Your claims start here</h3><p>Create a claim in your own words. Evidence for the DeWitt analysis area is already on this machine.</p><button className="button primary" onClick={() => setClaimOpen(true)}>New claim</button></div>}{visibleCases.map(item => <button className={`claim-row ${isRegressionCase(item) ? 'regression-row' : ''}`} key={item.id} onClick={() => openCase(item)}><div className="row-main"><span className="claim-id">{item.claim_id || item.id} {item.synthetic_demo && <small>SYNTHETIC</small>}{isRegressionCase(item) && <small>TEST HISTORY</small>}</span><strong>{item.farm}</strong><span>{item.cause} · {item.crop} · {item.location}</span></div><div className="row-end"><span className={`case-status ${item.status === 'READY_FOR_ADJUSTER_REVIEW' ? 'ready' : 'review'}`}>{caseStatus(item.status)}</span><ChevronRight size={19} /></div></button>)}</div></section><aside className="dashboard-side"><section className="surface"><span className="eyebrow">RECENT WORKFLOW</span><h2>{demoCase?.claim_id || 'No claim selected'}</h2><p className="muted">Completed investigation milestones for the newest visible claim.</p><div className="activity-list">{(demoCase?.workflow || []).map((item, index) => <div key={index}><span className="activity-mark"><Check size={13} /></span><span><strong>{workflowLabel(item.stage)}</strong><small>{item.state === 'error' ? 'Needs technical review' : 'Completed'}</small></span></div>)}</div><button className="text-link" onClick={() => demoCase && openCase(demoCase)}>View investigation <ArrowRight size={16} /></button></section><section className="surface sources-card"><span className="eyebrow">LOCAL EVIDENCE SOURCES</span>{['Weather records', 'Crop classification', 'Satellite vegetation', 'Neighbor fields'].map(source => <div key={source}><CheckCircle2 size={17} /> {source}</div>)}<small>Public evidence and synthetic fixtures are labeled in each case.</small></section></aside></div>
    </> : selected ? <>
      <div className="claim-topline"><button className="text-link" onClick={() => navigate('dashboard')}>← Dashboard</button><span>{selected.synthetic_demo ? 'SYNTHETIC DEMO DATA' : 'LOCAL CASE FILE'}</span></div>
      <div className="page-intro claim-intro"><div><span className="eyebrow">CLAIM INVESTIGATION · {selected.claim_id || selected.id}</span><h1>{selected.farm}</h1><p>{selected.cause} · {selected.crop} · {selected.location}</p></div><span className={`case-status large ${selected.status === 'READY_FOR_ADJUSTER_REVIEW' ? 'ready' : 'review'}`}>{caseStatus(selected.status)}</span></div>
      <div className="claim-meta"><div><span>REPORTED LOSS</span><strong>{dateLabel(selected.loss_date)}</strong></div><div><span>FIELD AREA</span><strong>{selected.acreage || '—'} acres</strong></div><div><span>MEASURED CHECKS</span><strong>{selected.report?.findings?.length || 0}</strong></div><div><span>LOCAL AGENT</span><strong>{investigating ? 'Investigating…' : selected.agent_run ? 'Run saved' : 'Ready to run'}</strong></div></div>
      <div className="claim-layout"><aside className="claim-context"><section className="surface"><div className="surface-heading"><div><span className="eyebrow">FIELD CONTEXT</span><h2>Crop analysis areas</h2></div><MapPin size={19} /></div><FieldMap boundary={selected.boundary} selectedField={selected.selected_field} /><div className="context-facts"><div><span>Reported cause</span><strong>{selected.cause}</strong></div><div><span>Claimed crop</span><strong>{selected.crop}</strong></div><div><span>Loss date</span><strong>{dateLabel(selected.loss_date)}</strong></div></div></section><section className="surface"><span className="eyebrow">VEGETATION COMPARISON</span><h2>Before and after NDVI</h2><NdviComparison points={selected.ndvi_series} provenance={selected.provenance} /></section></aside>
        <section className="claim-main"><AgentReport key={selected.id} investigation={selected} />{selected.claim_description && <details className="surface claim-statement-panel"><summary>Claimant statement</summary><p className="claim-statement">{selected.claim_description}</p><small>Reported statement, pending evidence review.</small></details>}{selected.tasks?.length > 0 && <section className="surface"><span className="eyebrow">FOLLOW-UP EVIDENCE</span><h2>What is still needed</h2>{selected.tasks.map(task => <div className="followup-item" key={task._id}><strong>{task.title}</strong><p>{task.reason}</p><small>{task.status === 'OPEN' ? 'Awaiting evidence' : 'Resolved'}</small></div>)}</section>}<div className="surface investigation-panel">
          <span className="eyebrow">INVESTIGATION WORKFLOW</span><h2>Evidence progress</h2>
          <p>The local agent chooses crop, rainfall, vegetation, and neighbor checks, then prepares the evidence report for human review. {selected.synthetic_demo ? 'This regression fixture uses synthetic assets.' : 'Measurements come from the registered local evidence package.'}</p>
          <div className="progress-list">
            <div className="progress-item done"><span><Check size={16} /></span><div><strong>Claim and field loaded</strong><small>{selected.claim_id || selected.id} · {selected.crop} · {selected.cause}</small></div></div>
            {selected.workflow.map((step, index) => <div className={`progress-item ${step.state === 'error' ? 'failed' : 'done'}`} key={`${step.stage}-${index}`}><span>{step.state === 'error' ? <X size={16} /> : <Check size={16} />}</span><div><strong>{workflowLabel(step.stage)}</strong><small>{step.state === 'error' ? 'Needs technical review' : 'Completed'}</small></div></div>)}
            {!selected.report_saved && <div className={`progress-item ${investigating ? 'active' : ''}`}><span><Activity size={16} /></span><div><strong>Complete measured checks</strong><small>{investigating ? 'Running the next local evidence check…' : 'Ready to run the demo investigation'}</small></div></div>}
          </div>
          {<button className="button primary run-button" onClick={runInvestigation} disabled={investigating}><Activity size={18} /> {investigating ? 'Running investigation…' : selected.report_saved ? (selected.origin === 'demo' ? 'Run fresh investigation' : 'Investigate again') : 'Run investigation'}</button>}
          {actionError && <p className="error-message">{actionError}</p>}
        </div>
          <section className="surface evidence-section"><div className="surface-heading"><div><span className="eyebrow">SOURCE-BACKED FINDINGS</span><h2>Evidence summary</h2></div><span className="count-tag">{selected.report.findings.length} checks</span></div><div className="evidence-grid">{evidenceOrder.map(({ check, label, key, icon: Icon }) => { const finding = selected.report.findings.find(item => item.check === check); if (!finding) return null; return <div className="evidence-card" key={key}><div className="evidence-card-top"><span className="evidence-icon"><Icon size={20} /></span><span className={`finding-status ${finding.status}`}>{statusLabel(finding.status)}</span></div><h3>{label}</h3><p>{finding.detail}</p><small>Source: {finding.source}</small>{finding.provenance?.datasets?.map((dataset, index) => <div className="provenance-line" key={`${dataset.product}-${index}`}><strong>{dataset.provider}</strong><span>{dataset.product}{dataset.station_id ? ` · ${dataset.station_id}` : ''}{dataset.item_id ? ` · ${dataset.item_id}` : ''}{dataset.date ? ` · ${dataset.date}` : ''}</span></div>)}</div> })}</div></section>
          <section className="surface assessment"><span className="eyebrow">FORENSIC EVIDENCE SUMMARY</span><h2>{selected.report.evidence_summary.supported} of {selected.report.findings.length} checks supported</h2><p>{selected.report.assessment}</p><div className="assessment-note"><ShieldCheck size={18} /> FieldTrace does not approve or deny claims. A qualified adjuster reviews this evidence.</div><div className="report-actions"><button className="button secondary" onClick={() => setReportOpen(!reportOpen)}><FileText size={17} /> {reportOpen ? 'Hide report' : 'View report'}</button>{selected.report_saved && <a className="button secondary" href={`/api/cases/${encodeURIComponent(selected.id)}/report.md`} download={`${selected.id}-evidence.md`}><Download size={17} /> Download Markdown</a>}</div>{reportOpen && <div className="report-details"><h3>Measured findings</h3>{selected.report.findings.map(finding => <div key={finding.check}><strong>{finding.check} · {statusLabel(finding.status)}</strong><p>{finding.detail}</p><small>{finding.source}</small></div>)}<h3>Agent response</h3><p>{selected.agent_run?.summary || 'No completed agent run saved yet.'}</p><h3>Method</h3><p>{selected.report.method}</p><details className="technical-audit"><summary>Technical audit</summary><pre>{JSON.stringify(selected.actions, null, 2)}</pre></details></div>}</section>
        </section></div>
    </> : <div className="page-state">No claim selected. Create a new claim from the dashboard to begin.</div>}</main>}
    <footer className="site-footer"><span>FieldTrace · Crop insurance evidence assistant</span><span>Local data · Human review · OpenClaw · Ollama · gpt-oss:20b</span></footer>
    {claimOpen && <ClaimModal onClose={() => setClaimOpen(false)} onCreated={onCreated} onAdvanced={() => { setClaimOpen(false); setUploadOpen(true) }} />}
    {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} onCreated={onCreated} />}
  </div>
}
