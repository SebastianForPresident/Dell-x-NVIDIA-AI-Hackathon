import { useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowRight, ArrowUpRight, CalendarDays, Check, CheckCircle2,
  ChevronRight, CircleHelp, CloudRain, Cpu, Database, Download, FileText,
  FolderOpen, Layers, Leaf, MapPin, Menu, Minus, Plus, Radar, Search,
  ShieldCheck, SlidersHorizontal, Sparkles, UploadCloud, X,
} from 'lucide-react'

const statusMeta = {
  supported: { label: 'Supported', icon: Check, tone: 'green' },
  contradicted: { label: 'Contradicted', icon: X, tone: 'red' },
  inconclusive: { label: 'Inconclusive', icon: Minus, tone: 'amber' },
  unavailable: { label: 'Unavailable', icon: CircleHelp, tone: 'gray' },
}

const checkIcons = {
  'Crop type': Leaf,
  Precipitation: CloudRain,
  'Vegetation change': Activity,
  'Other supplied fields': Layers,
}

async function api(path, options) {
  const response = await fetch(path, options)
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof data === 'object' ? data.detail : data
    throw new Error(Array.isArray(detail) ? detail.map(item => item.msg).join(', ') : (typeof detail === 'object' ? JSON.stringify(detail) : detail) || `Request failed (${response.status})`)
  }
  return data
}

function formatDate(value, options = { month: 'short', day: 'numeric', year: 'numeric' }) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', options)
}

function StatusPill({ status }) {
  const meta = statusMeta[status] || statusMeta.unavailable
  const Icon = meta.icon
  return <span className={`status-pill ${meta.tone}`}><Icon size={13} strokeWidth={2.5} />{meta.label}</span>
}

function CasePill({ status }) {
  return <span className={`case-pill ${status === 'READY_FOR_ADJUSTER_REVIEW' ? 'ready' : 'review'}`}>
    <span className="pulse-dot" />{status.replaceAll("_", " ")}
  </span>
}

function SectionHeading({ eyebrow, title, action }) {
  return <div className="section-heading"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2></div>{action}</div>
}

function FieldMap({ boundary, selectedField = 0 }) {
  const features = boundary?.features || []
  const rings = features.flatMap((feature, index) => {
    const geometry = feature.geometry
    const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : geometry?.type === 'MultiPolygon' ? geometry.coordinates : []
    return polygons.map(polygon => ({ index, ring: polygon[0] }))
  })
  const points = rings.flatMap(item => item.ring)
  if (!points.length) return <div className="empty-visual">No field boundary supplied</div>
  const west = Math.min(...points.map(point => point[0]))
  const east = Math.max(...points.map(point => point[0]))
  const south = Math.min(...points.map(point => point[1]))
  const north = Math.max(...points.map(point => point[1]))
  const dx = Math.max(east - west, 0.000001)
  const dy = Math.max(north - south, 0.000001)
  const xy = ([x, y]) => [38 + ((x - west) / dx) * 444, 255 - ((y - south) / dy) * 205]
  return <div className="map-visual">
    <svg viewBox="0 0 520 290" role="img" aria-label="Field boundary sketch">
      <defs>
        <pattern id="field-rows" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(28)"><line x1="0" y1="0" x2="0" y2="10" stroke="#789a71" strokeOpacity=".14" strokeWidth="3" /></pattern>
        <pattern id="map-grid" width="42" height="42" patternUnits="userSpaceOnUse"><path d="M 42 0 L 0 0 0 42" fill="none" stroke="#8ca392" strokeOpacity=".18" strokeWidth="1" /></pattern>
      </defs>
      <rect width="520" height="290" fill="#dfe8d9" />
      <rect width="520" height="290" fill="url(#map-grid)" />
      <path d="M -20 232 C 105 183, 200 302, 350 243 S 460 178, 540 210" fill="none" stroke="#f4f1e6" strokeWidth="18" strokeOpacity=".75" />
      {rings.map(({ index, ring }, i) => {
        const coords = ring.map(point => xy(point).join(',')).join(' ')
        return <g key={`${index}-${i}`}>
          <polygon points={coords} fill={index === selectedField ? '#80a873' : '#b8c6a8'} fillOpacity={index === selectedField ? '.86' : '.73'} stroke="#f7f9ef" strokeWidth="4" />
          <polygon points={coords} fill="url(#field-rows)" stroke={index === selectedField ? '#2d6848' : '#789477'} strokeWidth="1.5" />
        </g>
      })}
      {rings.map(({ index, ring }, i) => {
        const center = xy([ring.reduce((sum, p) => sum + p[0], 0) / ring.length, ring.reduce((sum, p) => sum + p[1], 0) / ring.length])
        return <g key={`label-${index}-${i}`}>
          <circle cx={center[0]} cy={center[1]} r="12" fill={index === selectedField ? '#234d37' : '#fff'} stroke="#fff" strokeWidth="2" />
          <text x={center[0]} y={center[1] + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill={index === selectedField ? '#fff' : '#2a4937'}>{index + 1}</text>
        </g>
      })}
    </svg>
    <div className="map-floating"><span className="map-key" /> Claimed field <span className="map-scale">Geometry preview · no basemap</span></div>
  </div>
}

function NdviChart({ data, lossDate }) {
  if (!data?.length) return <div className="empty-visual">Upload before and after imagery to see vegetation change.</div>
  const width = 620, height = 228, left = 36, right = 20, top = 20, bottom = 30
  const plotWidth = width - left - right, plotHeight = height - top - bottom
  const y = value => top + ((0.9 - value) / 0.9) * plotHeight
  const x = index => left + (index / Math.max(data.length - 1, 1)) * plotWidth
  const path = data.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.ndvi)}`).join(' ')
  const area = `${path} L ${x(data.length - 1)} ${top + plotHeight} L ${x(0)} ${top + plotHeight} Z`
  const start = new Date(`${data[0].date}T00:00:00`).getTime()
  const end = new Date(`${data[data.length - 1].date}T00:00:00`).getTime()
  const loss = new Date(`${lossDate}T00:00:00`).getTime()
  const lossX = end > start ? left + Math.max(0, Math.min(1, (loss - start) / (end - start))) * plotWidth : null
  return <div className="chart-wrap"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Vegetation index over time">
    <defs><linearGradient id="ndvi-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#4e996d" stopOpacity=".23" /><stop offset="100%" stopColor="#4e996d" stopOpacity="0" /></linearGradient></defs>
    {[0.2, 0.4, 0.6, 0.8].map(tick => <g key={tick}><line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} stroke="#e8ede6" /><text x="4" y={y(tick) + 4} fill="#8a998d" fontSize="11">{tick.toFixed(1)}</text></g>)}
    {lossX !== null && <g><line x1={lossX} x2={lossX} y1={top} y2={top + plotHeight} stroke="#d6a15c" strokeDasharray="4 5" strokeWidth="1.5" /><text x={Math.min(lossX + 7, width - 105)} y="16" fill="#a37036" fontSize="10" fontWeight="700">REPORTED LOSS</text></g>}
    <path d={area} fill="url(#ndvi-fill)" /><path d={path} fill="none" stroke="#43845c" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
    {data.map((point, index) => <circle key={index} cx={x(index)} cy={y(point.ndvi)} r="5" fill="#fff" stroke="#43845c" strokeWidth="2.5" />)}
    <text x={left} y={height - 3} fill="#8a998d" fontSize="11">{formatDate(data[0].date, { month: 'short', day: 'numeric' })}</text>
    <text x={width - right} y={height - 3} textAnchor="end" fill="#8a998d" fontSize="11">{formatDate(data[data.length - 1].date, { month: 'short', day: 'numeric' })}</text>
  </svg></div>
}

function RainChart({ data }) {
  if (!data?.length) return <div className="empty-visual">Upload daily weather records to see precipitation.</div>
  const weeks = []
  for (let i = 0; i < data.length; i += 7) {
    const rows = data.slice(i, i + 7)
    weeks.push({ label: `W${weeks.length + 1}`, actual: rows.reduce((sum, row) => sum + (row.rainfall || 0), 0), normal: rows.some(row => row.normal == null) ? null : rows.reduce((sum, row) => sum + row.normal, 0) })
  }
  const max = Math.max(1, ...weeks.map(week => Math.max(week.actual, week.normal || 0))) * 1.1
  return <div className="rain-chart"><div className="rain-bars">
    {weeks.map(week => <div className="rain-group" key={week.label}>
      <div className="rain-bar-pair">
        <div className="rain-bar actual" title={`Rainfall ${week.actual.toFixed(1)} mm`} style={{ height: `${Math.max(4, week.actual / max * 100)}%` }} />
        {week.normal !== null && <div className="rain-bar normal" title={`Normal ${week.normal.toFixed(1)} mm`} style={{ height: `${Math.max(4, week.normal / max * 100)}%` }} />}
      </div><span>{week.label}</span>
    </div>)}
  </div><div className="chart-legend"><span><i className="legend-square actual" /> Rainfall</span><span><i className="legend-square normal" /> Normal</span></div></div>
}

function EvidenceCard({ finding }) {
  const Icon = checkIcons[finding.check] || Radar
  const meta = statusMeta[finding.status] || statusMeta.unavailable
  return <div className="evidence-card">
    <div className="evidence-top"><div className={`evidence-icon ${meta.tone}`}><Icon size={20} /></div><StatusPill status={finding.status} /></div>
    <h3>{finding.check}</h3><p>{finding.detail}</p>
    <div className="evidence-footer"><span>Source</span><strong>{finding.source}</strong></div>
  </div>
}

function UploadModal({ onClose, onCreated }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [files, setFiles] = useState({})
  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const body = new FormData(event.currentTarget)
      const result = await api('/api/cases/analyze', { method: 'POST', body })
      onCreated(result)
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }
  const fileFields = [
    ['boundary', 'Field boundary', '.geojson,.json', true],
    ['weather', 'Weather history', '.csv', false],
    ['crop_layer', 'USDA crop layer', '.tif,.tiff', false],
    ['before_image', 'Before imagery', '.tif,.tiff', false],
    ['after_image', 'After imagery', '.tif,.tiff', false],
    ['claim_pdf', 'Claim document', '.pdf', false],
  ]
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="upload-modal" role="dialog" aria-modal="true" aria-label="New investigation">
      <div className="modal-header"><div><div className="eyebrow">NEW INVESTIGATION</div><h2>Import a claim package</h2><p>Evidence files stay on the application host. Evidence files are retained locally so investigation tools can inspect them again.</p></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={20} /></button></div>
      <form onSubmit={submit}>
        <div className="modal-scroll">
          <div className="form-section-title">Claim details</div>
          <div className="form-grid">
            <label>Claim ID<input name="claim_id" placeholder="CI-2026-0421" required /></label>
            <label>Farm / policyholder<input name="farm" placeholder="Farm name" required /></label>
            <label>Location<input name="location" placeholder="County, State" /></label>
            <label>Reported loss date<input name="loss_date" type="date" required /></label>
            <label>Reported cause<select name="cause" defaultValue="Drought"><option>Drought</option><option>Flood</option><option>Other</option></select></label>
            <label>Claimed crop<select name="crop" defaultValue="Corn"><option>Corn</option><option>Soybeans</option><option>Winter wheat</option><option>Other</option></select></label>
            <label>Acreage<input name="acreage" type="number" min="0" defaultValue="0" /></label>
            <label>Weather units<select name="weather_unit" defaultValue="mm"><option value="mm">Millimeters</option><option value="inches">Inches</option></select></label>
            <label>Before image date<input name="before_date" type="date" required /></label>
            <label>After image date<input name="after_date" type="date" required /></label>
            <label>Red band<input name="red_band" type="number" min="1" defaultValue="1" /></label>
            <label>NIR band<input name="nir_band" type="number" min="1" defaultValue="2" /></label>
          </div>
          <input type="hidden" name="selected_field" value="0" />
          <div className="form-section-title files-title">Evidence files <span>GeoJSON is required; all other files are optional</span></div>
          <div className="file-grid">{fileFields.map(([name, label, accept, required]) => <label className={`file-drop ${files[name] ? 'filled' : ''}`} key={name}>
            <input type="file" name={name} accept={accept} required={required} onChange={event => setFiles(current => ({ ...current, [name]: event.target.files?.[0]?.name }))} />
            <UploadCloud size={19} /><span><strong>{label}</strong><small>{files[name] || (required ? 'Choose a file · required' : 'Choose a file · optional')}</small></span>
            {files[name] && <Check size={17} className="file-check" />}
          </label>)}</div>
          <label className="synthetic-checkbox"><input type="checkbox" name="synthetic_demo" value="true" /> This is synthetic demonstration data</label>
          {error && <div className="form-error">{error}</div>}
        </div>
        <div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" type="submit" disabled={busy}>{busy ? 'Analyzing evidence…' : 'Analyze evidence (deterministic)'}<ArrowRight size={16} /></button></div>
      </form>
    </div>
  </div>
}

export default function App() {
  const [cases, setCases] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [activeTab, setActiveTab] = useState('Overview')
  const [section, setSection] = useState('Investigations')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All cases')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [runningDemo, setRunningDemo] = useState(false)
  const [actionError, setActionError] = useState('')
  const [mobileMenu, setMobileMenu] = useState(false)

  useEffect(() => {
    Promise.all([api('/api/health'), api('/api/cases')])
      .then(async ([, rows]) => { const items = rows.length ? rows : [await api('/api/demo', { method: 'POST' })]; setCases(items); setSelectedId(items[0].id) })
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
  const filtered = useMemo(() => cases.filter(item => {
    const matchesText = `${item.claim_id} ${item.farm} ${item.location} ${item.crop}`.toLowerCase().includes(query.toLowerCase())
    const matchesFilter = filter === 'All cases' || item.status === filter
    return matchesText && matchesFilter
  }), [cases, query, filter])
  const readyCount = cases.filter(item => item.status === 'READY_FOR_ADJUSTER_REVIEW').length
  const checksCount = cases.reduce((sum, item) => sum + (item.report?.findings?.length || 0), 0)

  function navigate(next) {
    setSection(next); setMobileMenu(false)
    if (next === 'Evidence library') setActiveTab('Evidence')
    if (next === 'Investigations' || next === 'Dashboard') setActiveTab('Overview')
  }

  function onCreated(item) {
    setCases(current => [item, ...current]); setSelectedId(item.id); setActiveTab('Overview'); setSection('Investigations'); setUploadOpen(false)
  }

  function updateCase(updated) {
    setCases(current => current.map(item => item.id === updated.id ? updated : item))
  }

  async function loadDemo(fresh = false) {
    try {
      const item = await api(fresh ? '/api/demo/reset' : '/api/demo', { method: 'POST' })
      setCases(current => [item, ...current.filter(row => row.id !== item.id)])
      setSelectedId(item.id); setActiveTab('Overview'); setSection('Investigations')
    } catch (err) { setActionError(err.message) }
  }

  async function runDemo() {
    if (!selected) return
    setRunningDemo(true); setActionError('')
    try {
      for (let step = 0; step < 6; step++) {
        const updated = await api(`/api/cases/${selected.id}/demo-step`, { method: 'POST' })
        updateCase(updated)
        if (['READY_FOR_ADJUSTER_REVIEW', 'NEEDS_EVIDENCE'].includes(updated.status)) break
        await new Promise(resolve => setTimeout(resolve, 350))
      }
    } catch (err) { setActionError(err.message) }
    finally { setRunningDemo(false) }
  }

  async function resolveTask(taskId, resolution) {
    try {
      updateCase(await api(`/api/cases/${selected.id}/tasks/${taskId}/resolve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resolution }),
      }))
    } catch (err) { setActionError(err.message) }
  }

  const menu = [
    { label: 'Dashboard', icon: Radar },
    { label: 'Investigations', icon: FolderOpen },
    { label: 'Evidence library', icon: Layers },
    { label: 'System status', icon: SlidersHorizontal },
  ]

  return <div className="app-shell">
    <aside className={`sidebar ${mobileMenu ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Leaf size={23} strokeWidth={2.4} /></div><div><strong>fieldnote<span>.</span></strong><small>FORENSICS PLATFORM</small></div></div>
      <div className="sidebar-label">WORKSPACE</div>
      <nav>{menu.map(({ label, icon: Icon }) => <button key={label} className={`nav-item ${section === label ? 'active' : ''}`} onClick={() => navigate(label)}><Icon size={18} strokeWidth={1.9} />{label}{section === label && <span className="nav-active-dot" />}</button>)}</nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-context"><div className="context-icon"><ShieldCheck size={17} /></div><strong>Local by design</strong><p>Evidence and claim data remain on the GB10. Human adjusters make every decision.</p></div>
      <div className="sidebar-footer"><div className="team-avatar">KC</div><div><strong>Adjuster workspace</strong><span>Dell × NVIDIA hackathon</span></div><ChevronRight size={16} /></div>
    </aside>

    <main className="main-area">
      <div className="topbar"><button className="mobile-menu" onClick={() => setMobileMenu(!mobileMenu)}><Menu size={21} /></button><div className="breadcrumbs">Workspace <ChevronRight size={14} /> <strong>{section}</strong></div><div className="topbar-right"><span className="local-pill"><span /> LOCAL-FIRST SYSTEM</span><button className="top-help" onClick={() => navigate('System status')} title="System status"><CircleHelp size={18} /></button><div className="top-avatar">KC</div></div></div>

      {loading ? <div className="loading-state"><div className="loading-ring" /><p>Loading local investigations…</p></div> : error ? <div className="offline-state"><Database size={36} /><h1>Local database is not connected</h1><p>{error}</p><p>Start MongoDB and the Python API using the commands in the README, then refresh this page.</p><button className="button primary" onClick={() => window.location.reload()}>Try again <ArrowRight size={16} /></button></div> : <div className="content-wrap">
        {section === 'System status' ? <>
          <div className="page-heading"><div><div className="eyebrow">INFRASTRUCTURE</div><h1>System status</h1><p>All services are designed to run on the local GB10.</p></div></div>
          <div className="system-grid"><div className="system-card"><div className="system-icon green"><Database size={23} /></div><h3>MongoDB</h3><p>Local case records and evidence packages</p><span className="system-state green"><CheckCircle2 size={15} /> Connected</span></div><div className="system-card"><div className="system-icon amber"><Cpu size={23} /></div><h3>Local agent runtime</h3><p>OpenClaw ? Ollama ? gpt-oss:20b</p><span className="system-state amber">Integration pending</span><small className="system-message">No inference runs in this milestone. Demo controls execute deterministic tools.</small></div><div className="system-card"><div className="system-icon blue"><ShieldCheck size={23} /></div><h3>Evidence tools</h3><p>Raster, weather, crop, and comparison checks</p><span className="system-state green"><CheckCircle2 size={15} /> Available</span></div></div>
          <div className="info-banner"><ShieldCheck size={20} /><div><strong>Review boundary</strong><p>Findings are screening evidence. They do not determine coverage, causation, or claim outcome.</p></div></div>
        </> : <>
          <div className="page-heading"><div><div className="eyebrow">FIELD INTELLIGENCE / 2026 SEASON</div><h1>{section === 'Dashboard' ? 'Good morning, adjuster.' : section === 'Evidence library' ? 'Evidence library' : 'Investigations'}<span className="heading-spark">✳</span></h1><p>{section === 'Dashboard' ? 'A clear view of the cases waiting for your review.' : section === 'Evidence library' ? 'Trace every finding back to the source and measurement.' : 'Turn geospatial data into a reviewable evidence package.'}</p></div><button className="button primary new-case" onClick={() => setUploadOpen(true)}><Plus size={18} /> New investigation</button><button className="button secondary" onClick={() => loadDemo()}>Load DeWitt demo</button></div>

          <div className="stats-grid"><div className="stat-card"><div className="stat-label">TOTAL INVESTIGATIONS <FolderOpen size={18} /></div><div className="stat-number">{cases.length.toString().padStart(2, '0')}</div><div className="stat-foot">Cases in local workspace <ArrowUpRight size={15} /></div></div><div className="stat-card"><div className="stat-label">EVIDENCE PACKAGES <FileText size={18} /></div><div className="stat-number">{readyCount.toString().padStart(2, '0')}</div><div className="stat-foot">Ready for human review <ArrowUpRight size={15} /></div></div><div className="stat-card highlighted"><div className="stat-label">CHECKS COMPLETED <Activity size={18} /></div><div className="stat-number">{checksCount.toString().padStart(2, '0')}</div><div className="stat-foot">Across all local cases <span className="stat-mini-line" /></div></div></div>

          <div className="workspace-grid"><section className="case-list-card"><div className="list-header"><div><div className="eyebrow">YOUR WORKSPACE</div><h2>Case queue <span>{cases.length}</span></h2></div><button className="tiny-icon" onClick={() => setUploadOpen(true)} aria-label="New case"><Plus size={18} /></button></div><div className="search-box"><Search size={17} /><input placeholder="Search claims, farms, locations…" value={query} onChange={event => setQuery(event.target.value)} /></div><div className="filter-row">{['All cases', 'READY_FOR_ADJUSTER_REVIEW', 'NEEDS_EVIDENCE', 'NEW', 'INVESTIGATING'].map(value => <button key={value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(value)}>{value === 'All cases' ? 'All' : value === 'READY_FOR_ADJUSTER_REVIEW' ? 'Ready' : value === 'NEEDS_EVIDENCE' ? 'Review' : value === 'NEW' ? 'New' : 'Active'}</button>)}</div><div className="case-list">{filtered.map(item => <button className={`case-row ${selected?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => { setSelectedId(item.id); setActiveTab(section === 'Evidence library' ? 'Evidence' : 'Overview') }}><div className="case-row-top"><span className="case-id">{item.claim_id}</span><ChevronRight size={16} /></div><strong>{item.farm}</strong><span className="case-location"><MapPin size={13} />{item.location}</span><div className="case-row-bottom"><span className={`cause-tag ${item.cause.toLowerCase()}`}>{item.cause}</span><span>{formatDate(item.loss_date, { month: 'short', day: 'numeric' })}</span></div></button>)}{filtered.length === 0 && <div className="list-empty">No cases match this search.</div>}</div><div className="list-footer"><span><span className="small-dot" /> Local database synced</span><Database size={15} /></div></section>

            {selected && <section className="case-detail"><div className="case-hero"><div className="case-hero-top"><div className="case-breadcrumb">CASE FILE <span>/</span> {selected.claim_id}</div><div className="case-hero-badges">{selected.synthetic_demo && <span className="demo-pill">SYNTHETIC DEMO</span>}<CasePill status={selected.status} /></div></div><div className="case-title-row"><div><h2>{selected.farm}</h2><p><MapPin size={15} />{selected.location} <span className="meta-separator">·</span> {selected.acreage || '—'} acres <span className="meta-separator">·</span> {selected.crop}</p></div><a className="button outline export-button" href={selected.report_saved ? `/api/cases/${encodeURIComponent(selected.id)}/report.md` : undefined} download={`${selected.id}-evidence.md`}><Download size={16} /> {selected.report_saved ? "Export report" : "Report not saved"}</a></div><div className="case-hero-metrics"><div><span>REPORTED CAUSE</span><strong>{selected.cause}</strong></div><div><span>LOSS DATE</span><strong>{formatDate(selected.loss_date)}</strong></div><div><span>EVIDENCE SIGNALS</span><strong>{selected.report.evidence_summary.supported} supported <span>/ {selected.report.findings.length} checks</span></strong></div></div></div>

              <div className="tabs">{['Overview', 'Evidence', 'Report'].map(tab => <button key={tab} className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)}>{tab}{tab === 'Evidence' && <span>{selected.report.findings.length}</span>}</button>)}</div>

              <div className="review-note"><div><strong>{selected.status}</strong><p>{selected.report_saved ? 'Final evidence report saved.' : 'Investigation in progress ? findings below are a working preview.'}</p>{selected.origin === 'demo' && <><p>Synthetic DeWitt data ? scripted deterministic demo ? no autonomous AI inference.</p><button className="button secondary" onClick={runDemo} disabled={runningDemo || selected.status === 'READY_FOR_ADJUSTER_REVIEW'}>{runningDemo ? 'Inspecting evidence?' : 'Run deterministic demo checks'}</button><button className="button ghost" onClick={() => loadDemo(true)} disabled={runningDemo}>New demo run</button></>}{actionError && <p className="inline-error">{actionError}</p>}{selected.asset_error && <p className="inline-error">{selected.asset_error}</p>}</div></div>
              {(selected.tasks || []).map(task => <div className="review-note" key={task._id}><div><strong>{task.status}: {task.title}</strong><p>{task.reason}</p>{task.status === 'OPEN' ? <form onSubmit={event => { event.preventDefault(); resolveTask(task._id, new FormData(event.currentTarget).get('resolution')) }}><input name="resolution" placeholder="Human resolution note" required /><button className="button secondary" type="submit">Resolve follow-up</button></form> : <p>{task.resolution}</p>}</div></div>)}
              <details className="review-note"><summary>Audit details and status transitions</summary><pre style={{whiteSpace:'pre-wrap', overflowWrap:'anywhere'}}>{JSON.stringify({ actions: selected.actions, transitions: selected.transitions }, null, 2)}</pre></details>

              {activeTab === 'Overview' && <div className="detail-body"><div className="visual-grid"><div className="panel map-panel"><div className="panel-heading"><div><div className="eyebrow">GEOSPATIAL CONTEXT</div><h3>Field footprint</h3></div><span className="panel-corner"><MapPin size={14} /> WGS84</span></div><FieldMap boundary={selected.boundary} selectedField={selected.selected_field} /><div className="panel-note"><span><span className="legend-dot claimed" /> Claimed field</span><span><span className="legend-dot comparison" /> Comparison fields</span></div></div><div className="panel weather-panel"><div className="panel-heading"><div><div className="eyebrow">WEATHER HISTORY</div><h3>Precipitation</h3></div><CloudRain size={19} className="muted-icon" /></div><div className="weather-highlight"><strong>{selected.report.findings.find(f => f.check === 'Precipitation')?.values?.rainfall_mm ?? '—'} <small>mm</small></strong><span>30-day total before reported loss</span></div><RainChart data={selected.weather_series} /></div></div><div className="visual-grid bottom"><div className="panel vegetation-panel"><div className="panel-heading"><div><div className="eyebrow">SATELLITE VEGETATION</div><h3>Field health over time</h3></div><span className="chart-unit">NDVI</span></div><NdviChart data={selected.ndvi_series} lossDate={selected.loss_date} /><div className="chart-bottom-note"><span><i /> Vegetation index</span><span>Before and after imagery comparison</span></div></div><div className="panel workflow-panel"><div className="panel-heading"><div><div className="eyebrow">EVIDENCE WORKFLOW</div><h3>Investigation trail</h3></div><Sparkles size={18} className="muted-icon" /></div><div className="workflow-list">{selected.workflow.map((step, index) => <div className="workflow-step" key={index}><div className="step-marker">{step.state === "error" ? <X size={12} /> : <Check size={12} />}</div><div><strong>{step.stage}</strong><p>{step.detail}</p></div></div>)}</div></div></div><div className="review-note"><ShieldCheck size={18} /><span>This package is evidence for an adjuster. No claim approval, denial, or coverage decision is made.</span></div></div>}

              {activeTab === 'Evidence' && <div className="detail-body"><div className="evidence-intro"><div><div className="eyebrow">STRUCTURED FINDINGS</div><h3>Evidence, with provenance</h3><p>Each finding links a measured signal to its source. Missing or incomplete data stays visible.</p></div><span className="evidence-count">{selected.report.findings.length} CHECKS</span></div><div className="evidence-grid">{selected.report.findings.map((finding, index) => <EvidenceCard key={`${finding.check}-${index}`} finding={finding} />)}</div><div className="source-panel"><div className="source-title"><FileText size={18} /><strong>Source files</strong><span>{selected.documents.length} items</span></div><div className="source-items">{selected.documents.map((name, index) => <div key={`${name}-${index}`}><FileText size={15} /><span>{name}</span>{selected.synthetic_demo && <em>SYNTHETIC</em>}</div>)}</div></div></div>}

              {activeTab === 'Report' && <div className="detail-body"><div className="report-sheet"><div className="report-sheet-top"><div className="report-brand"><Leaf size={20} /> fieldnote.</div><span>FORENSIC EVIDENCE PACKAGE</span></div><div className="report-kicker">CLAIM {selected.claim_id} · {formatDate(selected.created_at)}</div><h2>{selected.farm}</h2><p className="report-subtitle">{selected.crop} · {selected.cause} reported {formatDate(selected.loss_date)} · {selected.location}</p>{selected.synthetic_demo && <div className="report-demo">Synthetic demonstration data — no real NOAA, USDA, or satellite observations</div>}<h3>Evidence summary</h3><div className="report-summary-row">{Object.entries(selected.report.evidence_summary).map(([key, value]) => <div key={key}><strong>{value}</strong><span>{key}</span></div>)}</div><div className="report-findings">{selected.report.findings.map((finding, index) => <div key={index}><div className="report-finding-title"><span>{String(index + 1).padStart(2, '0')}</span><strong>{finding.check}</strong><StatusPill status={finding.status} /></div><p>{finding.detail}</p><small>Source: {finding.source}</small></div>)}</div><h3>Human review</h3><p>AI does the detective work; the human adjuster makes the decision. Local agent runtime integration is pending. This report contains deterministic evidence, not a coverage decision.</p><div className="report-disclaimer"><ShieldCheck size={17} /><p>{selected.report.assessment} {selected.report.method}</p></div></div></div>}
            </section>}
          </div>
        </>}
      </div>}
    </main>
    {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} onCreated={onCreated} />}
  </div>
}
