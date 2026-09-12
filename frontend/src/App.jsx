import { useEffect, useState } from 'react'
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
  return <div className="field-map">
    <svg viewBox="0 0 520 300" role="img" aria-label="Claimed field and comparison field boundaries">
      <defs><pattern id="field-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#c9d6c8" strokeWidth="1" /></pattern></defs>
      <rect width="520" height="300" fill="#e8eee5" /><rect width="520" height="300" fill="url(#field-grid)" />
      <path d="M-10 243C116 175 222 302 370 225S500 181 540 202" stroke="#f8f7ef" strokeWidth="18" fill="none" />
      {rings.map(({ index, ring }, i) => <polygon key={`${index}-${i}`} points={ring.map(point => `${x(point[0])},${y(point[1])}`).join(' ')}
        fill={index === selectedField ? '#75a580' : '#bfd0b6'} stroke={index === selectedField ? '#28563a' : '#72977a'} strokeWidth="3" />)}
    </svg>
    <span className="map-caption"><span className="legend-dot" /> Claimed field · boundary sketch</span>
  </div>
}

function MiniTrend({ points = [] }) {
  if (points.length < 2) return <p className="muted">No vegetation time series supplied.</p>
  const coords = points.map((point, index) => `${10 + index * (280 / (points.length - 1))},${82 - Math.max(0, Math.min(1, point.ndvi)) * 68}`).join(' ')
  return <div className="mini-trend"><svg viewBox="0 0 300 96" role="img" aria-label="NDVI trend"><line x1="0" y1="83" x2="300" y2="83" stroke="#dce7dc" /><polyline points={coords} fill="none" stroke="#3f8860" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" /></svg><div><span>{dateLabel(points[0].date)}</span><span>{dateLabel(points.at(-1).date)}</span></div></div>
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
      <div className="modal-heading"><div><span className="eyebrow">LOCAL CASE INTAKE</span><h2>Import an evidence package</h2><p>The case is measured locally and saved to MongoDB. GeoTIFFs are discarded after analysis.</p></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={20} /></button></div>
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

export default function App() {
  const [page, setPage] = useState('home')
  const [cases, setCases] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [reviewError, setReviewError] = useState('')
  const [modelStatus, setModelStatus] = useState('not checked')
  const [reportOpen, setReportOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    Promise.all([api('/api/health'), api('/api/cases')])
      .then(([, rows]) => {
        setCases(rows)
        setSelectedId((rows.find(item => item.id === 'CLM-2841') || rows.find(item => item.synthetic_demo) || rows[0])?.id || null)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    let live = true
    const timer = setInterval(() => api('/api/cases').then(rows => { if (live) { setCases(rows); setActionError('') } })
      .catch(err => { if (live) setActionError(err.message) }), 5000)
    return () => { live = false; clearInterval(timer) }
  }, [])

  const selected = cases.find(item => item.id === selectedId) || cases[0]
  const readyCount = cases.filter(item => item.status === 'Evidence ready').length
  const reviewCount = cases.filter(item => item.status !== 'Evidence ready').length
  const demoCase = cases.find(item => item.id === 'CLM-2841') || cases.find(item => item.synthetic_demo) || cases[0]

  function navigate(next) { setPage(next); setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  function openCase(item) { setSelectedId(item.id); setReviewError(''); setReportOpen(false); navigate('claim') }
  function onCreated(item) { setCases(current => [item, ...current]); setSelectedId(item.id); setUploadOpen(false); navigate('claim') }

  async function runReview() {
    if (!selected) return
    const caseId = selected.id
    setReviewing(true); setReviewError(''); setModelStatus('checking')
    try {
      const result = await api(`/api/cases/${encodeURIComponent(caseId)}/ai-review`, { method: 'POST' })
      setCases(current => current.map(item => item.id === caseId ? { ...item, ai_review: result.ai_review } : item))
      setModelStatus('connected')
    } catch (err) { setReviewError(err.message); setModelStatus('unavailable') }
    finally { setReviewing(false) }
  }

  return <div className="site-shell">
    <header className="site-header"><button className="brand" onClick={() => navigate('home')}><span className="brand-icon"><Leaf size={22} /></span><span>FieldTrace<small>LOCAL CROP FORENSICS</small></span></button><nav className={menuOpen ? 'open' : ''} aria-label="Main navigation">{[['home', 'Home'], ['dashboard', 'Dashboard'], ['claim', 'Claim investigation']].map(([key, label]) => <button key={key} className={page === key ? 'active' : ''} onClick={() => navigate(key)}>{label}</button>)}</nav><div className="header-right"><span className="local-badge"><span /> LOCAL SYSTEM</span><button className="menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation"><Menu size={22} /></button></div></header>

    {page === 'home' && <main className="home-page"><section className="home-hero"><div className="home-copy"><span className="eyebrow">DELL × NVIDIA AI HACKATHON</span><h1>Crop-loss evidence,<br /><em>ready for review.</em></h1><p>FieldTrace is a local AI evidence assistant for crop insurance adjusters. It brings weather, crop, vegetation, and neighboring-field signals into one reviewable investigation.</p><div className="hero-actions"><button className="button primary" onClick={() => navigate('dashboard')}>View dashboard <ArrowRight size={18} /></button><button className="button secondary" onClick={() => demoCase && openCase(demoCase)} disabled={!demoCase}>Open demo claim <ChevronRight size={18} /></button></div><div className="hero-note"><ShieldCheck size={19} /><span>Evidence for a human adjuster. No automated claim decisions.</span></div></div><div className="hero-visual"><div className="hero-card-top"><span>DEMO INVESTIGATION</span><span className="signal"><span /> LOCAL DATA</span></div><div className="hero-claim"><span>{demoCase?.id || 'DEMO CASE'}</span><strong>{demoCase?.cause || 'Drought'} · {demoCase?.crop || 'Corn'}</strong><small>{demoCase?.location || 'Synthetic case'}</small></div><div className="hero-flow">{['Claim context', 'Weather & crop', 'Vegetation & neighbors', 'Adjuster report'].map((step, index) => <div key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong><CheckCircle2 size={18} /></div>)}</div><div className="hero-card-bottom"><Sparkles size={17} /> Local Qwen review available through OpenShell when connected</div></div></section><section className="home-section"><div className="section-title"><span className="eyebrow">ONE CLEAR WORKFLOW</span><h2>From claim to evidence package</h2></div><div className="how-grid">{[['01', 'Select a claim', 'Open a saved case or import a field boundary and local evidence files.'], ['02', 'Review measured evidence', 'See rainfall, crop classification, NDVI, and nearby-field checks with sources.'], ['03', 'Ask local Qwen', 'Generate a concise interpretation of structured evidence for the adjuster.']].map(([number, title, copy]) => <div className="how-card" key={title}><span>{number}</span><h3>{title}</h3><p>{copy}</p></div>)}</div></section><section className="value-strip"><div><strong>Faster investigations</strong><span>One place for the evidence package.</span></div><div><strong>Private by design</strong><span>Claims and data stay on the local system.</span></div><div><strong>Human decision making</strong><span>Adjusters decide; FieldTrace prepares evidence.</span></div></section></main>}

    {page !== 'home' && <main className="app-page">{loading ? <div className="page-state">Loading local cases…</div> : error ? <div className="page-state error"><Database size={30} /><h2>Backend unavailable</h2><p>{error}</p><p>Start MongoDB and FastAPI, then refresh.</p></div> : page === 'dashboard' ? <>
      <div className="page-intro"><div><span className="eyebrow">LOCAL CLAIM WORKSPACE</span><h1>Investigation dashboard</h1><p>Saved cases and evidence packages from the local MongoDB.</p></div><button className="button primary" onClick={() => setUploadOpen(true)}><Plus size={18} /> Import case</button></div>
      <div className="metric-grid"><div><span>Local cases</span><strong>{cases.length}</strong><small>Stored in this workspace</small></div><div><span>Evidence ready</span><strong>{readyCount}</strong><small>For adjuster review</small></div><div><span>Need review</span><strong>{reviewCount}</strong><small>Incomplete or inconclusive</small></div></div>
      <div className="dashboard-grid"><section className="surface"><div className="surface-heading"><div><span className="eyebrow">CLAIM QUEUE</span><h2>Open a case</h2></div><span className="count-tag">{cases.length} cases</span></div><div className="claim-list">{[...cases].sort((a, b) => (a.id === demoCase?.id ? -1 : b.id === demoCase?.id ? 1 : 0)).map(item => <button className="claim-row" key={item.id} onClick={() => openCase(item)}><div className="row-main"><span className="claim-id">{item.id} {item.synthetic_demo && <small>SYNTHETIC</small>}</span><strong>{item.farm}</strong><span>{item.cause} · {item.crop} · {item.location}</span></div><div className="row-end"><span className={`case-status ${item.status === 'Evidence ready' ? 'ready' : 'review'}`}>{item.status}</span><ChevronRight size={19} /></div></button>)}</div></section><aside className="dashboard-side"><section className="surface"><span className="eyebrow">SAVED WORKFLOW</span><h2>{demoCase?.id || 'Demo claim'}</h2><p className="muted">These stages are recorded with the case. Qwen review runs when you open the investigation.</p><div className="activity-list">{(demoCase?.workflow || []).map((item, index) => <div key={index}><span className="activity-mark"><Check size={13} /></span><span><strong>{item.stage}</strong><small>{item.detail}</small></span></div>)}</div><button className="text-link" onClick={() => demoCase && openCase(demoCase)}>View investigation <ArrowRight size={16} /></button></section><section className="surface sources-card"><span className="eyebrow">LOCAL EVIDENCE SOURCES</span>{['Weather records', 'Crop classification', 'Satellite vegetation', 'Neighbor fields'].map(source => <div key={source}><CheckCircle2 size={17} /> {source}</div>)}<small>Demo data is synthetic and clearly labeled.</small></section></aside></div>
    </> : selected ? <>
      <div className="claim-topline"><button className="text-link" onClick={() => navigate('dashboard')}>← Dashboard</button><span>{selected.synthetic_demo ? 'SYNTHETIC DEMO DATA' : 'LOCAL CASE FILE'}</span></div>
      <div className="page-intro claim-intro"><div><span className="eyebrow">CLAIM INVESTIGATION · {selected.id}</span><h1>{selected.farm}</h1><p>{selected.cause} · {selected.crop} · {selected.location}</p></div><span className={`case-status large ${selected.status === 'Evidence ready' ? 'ready' : 'review'}`}>{selected.status}</span></div>
      <div className="claim-meta"><div><span>REPORTED LOSS</span><strong>{dateLabel(selected.loss_date)}</strong></div><div><span>FIELD AREA</span><strong>{selected.acreage || '—'} acres</strong></div><div><span>MEASURED CHECKS</span><strong>{selected.report?.findings?.length || 0}</strong></div><div><span>LOCAL QWEN</span><strong>{selected.ai_review ? 'Review saved' : modelStatus}</strong></div></div>
      <div className="claim-layout"><aside className="claim-context"><section className="surface"><div className="surface-heading"><div><span className="eyebrow">FIELD CONTEXT</span><h2>Claimed field</h2></div><MapPin size={19} /></div><FieldMap boundary={selected.boundary} selectedField={selected.selected_field} /><div className="context-facts"><div><span>Reported cause</span><strong>{selected.cause}</strong></div><div><span>Claimed crop</span><strong>{selected.crop}</strong></div><div><span>Loss date</span><strong>{dateLabel(selected.loss_date)}</strong></div></div></section><section className="surface"><span className="eyebrow">VEGETATION TREND</span><h2>Field NDVI</h2><MiniTrend points={selected.ndvi_series} /></section></aside>
        <section className="claim-main"><div className="surface investigation-panel"><span className="eyebrow">LOCAL AI REVIEW</span><h2>Investigation progress</h2><p>The evidence checks below are already measured and saved. Run Qwen to interpret those structured local results; no claim decision is made.</p><div className="progress-list"><div className="progress-item done"><span><Check size={16} /></span><div><strong>Claim and field loaded</strong><small>{selected.id} · {selected.crop} · {selected.cause}</small></div></div><div className="progress-item done"><span><Check size={16} /></span><div><strong>Evidence measured</strong><small>{selected.report.findings.length} source-backed checks available</small></div></div><div className={`progress-item ${reviewing ? 'active' : selected.ai_review ? 'done' : reviewError ? 'failed' : ''}`}><span>{selected.ai_review ? <Check size={16} /> : <Sparkles size={16} />}</span><div><strong>Qwen reviews structured data</strong><small>{reviewing ? 'Analyzing weather, NDVI, crop and neighbor findings through OpenShell…' : selected.ai_review ? 'Local model review saved with this case' : reviewError ? 'Model route unavailable; measured evidence remains available' : 'Ready when the local model route is connected'}</small></div></div><div className={`progress-item ${selected.ai_review ? 'done' : ''}`}><span>{selected.ai_review ? <Check size={16} /> : <FileText size={16} />}</span><div><strong>Adjuster evidence package</strong><small>{selected.ai_review ? 'Measured findings and AI interpretation ready' : 'Measured findings and report are available now'}</small></div></div></div><button className="button primary run-button" onClick={runReview} disabled={reviewing}><Sparkles size={18} /> {reviewing ? 'Qwen reviewing locally…' : selected.ai_review ? 'Run Qwen review again' : 'Run local Qwen review'}</button>{reviewError && <p className="error-message">{reviewError}</p>}</div>
          <section className="surface evidence-section"><div className="surface-heading"><div><span className="eyebrow">SOURCE-BACKED FINDINGS</span><h2>Evidence summary</h2></div><span className="count-tag">{selected.report.findings.length} checks</span></div><div className="evidence-grid">{evidenceOrder.map(({ check, label, key, icon: Icon }) => { const finding = selected.report.findings.find(item => item.check === check); if (!finding) return null; return <div className="evidence-card" key={key}><div className="evidence-card-top"><span className="evidence-icon"><Icon size={20} /></span><span className={`finding-status ${finding.status}`}>{statusLabel(finding.status)}</span></div><h3>{label}</h3><p>{finding.detail}</p>{selected.ai_review?.[key] && <div className="ai-insight"><Sparkles size={15} /><span>{selected.ai_review[key]}</span></div>}<small>Source: {finding.source}</small></div> })}</div></section>
          <section className="surface assessment"><span className="eyebrow">FORENSIC EVIDENCE SUMMARY</span><h2>{selected.report.evidence_summary.supported} of {selected.report.findings.length} checks supported</h2><p>{selected.ai_review?.overall || selected.report.assessment}</p><div className="assessment-note"><ShieldCheck size={18} /> FieldTrace does not approve or deny claims. A qualified adjuster reviews this evidence.</div><div className="report-actions"><button className="button secondary" onClick={() => setReportOpen(!reportOpen)}><FileText size={17} /> {reportOpen ? 'Hide report' : 'View report'}</button><a className="button secondary" href={`/api/cases/${encodeURIComponent(selected.id)}/report.md`} download={`${selected.id}-evidence.md`}><Download size={17} /> Download Markdown</a></div>{reportOpen && <div className="report-details"><h3>Measured findings</h3>{selected.report.findings.map(finding => <div key={finding.check}><strong>{finding.check} · {statusLabel(finding.status)}</strong><p>{finding.detail}</p><small>{finding.source}</small></div>)}<h3>Method</h3><p>{selected.report.method}</p></div>}</section>
        </section></div>
    </> : <div className="page-state">No cases found. Import a case to begin.</div>}</main>}
    <footer className="site-footer"><span>FieldTrace · Crop insurance evidence assistant</span><span>Local data · Human review · {modelStatus === 'connected' ? 'Qwen connected' : 'Qwen route not verified'}</span></footer>
    {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} onCreated={onCreated} />}
  </div>
}
