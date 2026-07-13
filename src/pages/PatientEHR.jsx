import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { createApiClient } from '../api/client'
import { useAuth } from '../auth/authState'
import HowItWorks from '../components/HowItWorks'

const MONO = { fontFamily: 'DM Mono, monospace' }

const Icon = ({ children, size = 18 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
)
const HeartIcon = () => <Icon><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z" /></Icon>
const UploadIcon = () => <Icon><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M20 15v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4" /></Icon>
const FileIcon = () => <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="M8 13h8M8 17h6" /></Icon>
const ActivityIcon = () => <Icon><path d="M3 12h4l2-7 4 14 2-7h6" /></Icon>
const ShieldIcon = () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
const CalendarIcon = () => <Icon><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /></Icon>
const TrashIcon = () => <Icon size={16}><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v5M14 11v5" /></Icon>

function fmtDate(value) {
  if (!value) return 'Not recorded'
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function CountCard({ icon, label, value, note }) {
  return (
    <div className="rounded-2xl border border-white/50 p-5" style={{ background: '#A9D1FD', boxShadow: '0 4px 20px rgba(147,197,253,0.32)' }}>
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl text-white" style={{ background: '#3B82F6' }}>{icon}</div>
      <div className="text-3xl font-extrabold text-slate-900">{value ?? 0}</div>
      <div className="mt-1 text-sm font-bold text-slate-800">{label}</div>
      <div className="mt-1 text-xs text-blue-900/70">{note}</div>
    </div>
  )
}

function Panel({ title, eyebrow, action, children, className = '', bottomCircle = false }) {
  return (
    <section className={`relative overflow-hidden rounded-2xl ${className}`} style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.42)' }}>
      <div className="pointer-events-none absolute -right-8 -top-8 h-36 w-36 rounded-full border-[24px] border-white/20" />
      {bottomCircle && <div className="pointer-events-none absolute -bottom-12 -left-8 h-36 w-36 rounded-full border-[24px] border-white/15" />}
      <header className="relative z-10 flex items-center justify-between border-b border-white/40 px-7 py-5">
        <div>
          {eyebrow && <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>{eyebrow}</div>}
          <h2 className="text-lg font-extrabold text-slate-900">{title}</h2>
        </div>
        {action}
      </header>
      <div className="relative z-10 p-7">{children}</div>
    </section>
  )
}

function Empty({ children }) {
  return <div className="rounded-xl border border-white/50 bg-white/35 p-5 text-sm text-slate-600">{children}</div>
}

function RecordAttachment({ document }) {
  return (
    <article className="flex items-center gap-3 rounded-xl border border-white/60 bg-white/40 p-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#3B82F6] text-white"><FileIcon /></span>
      <div className="min-w-0">
        <div className="truncate text-sm font-bold text-slate-900">{document.title}</div>
        <p className="mt-1 text-xs capitalize text-slate-600">Attached document · {document.document_type?.replaceAll('_', ' ')} · {fmtDate(document.created_at)}</p>
      </div>
    </article>
  )
}

function RecordsView({ ehr, documents, onAttach, uploadingSection }) {
  const sections = [
    { title: 'Encounters and diagnoses', documentType: 'discharge_summary', items: ehr.encounters, render: item => (
      <article key={item.id} className="rounded-xl border border-white/60 bg-white/40 p-4">
        <div className="flex justify-between gap-4"><strong>{item.department || item.type}</strong><span className="text-xs font-bold text-blue-700">{item.status}</span></div>
        <p className="mt-1 text-xs text-slate-600">{item.hospital} - {fmtDate(item.created_at)}</p>
        {item.clinical_notes && <p className="mt-3 text-sm text-slate-700">{item.clinical_notes}</p>}
        {(item.diagnoses || []).map(d => <div key={d.id} className="mt-3 rounded-lg bg-blue-50/80 p-3 text-sm"><strong>{d.code || 'Clinical diagnosis'}</strong> - {d.description}</div>)}
      </article>
    ) },
    { title: 'Active allergies', documentType: 'other', items: ehr.allergies, render: item => <div key={item.id} className="rounded-xl border border-red-100 bg-red-50/80 p-4"><strong className="text-red-800">{item.substance}</strong><p className="text-sm text-red-700">{item.severity} - {item.reaction || 'Reaction not recorded'}</p></div> },
    { title: 'Prescriptions', documentType: 'prescription', items: ehr.prescriptions, render: item => <div key={item.id} className="rounded-xl border border-white/60 bg-white/40 p-4"><div className="flex justify-between"><strong>{item.medicine}</strong><span className="text-xs font-bold text-emerald-700">{item.status}</span></div><p className="mt-1 text-sm text-slate-600">{item.dosage} - {item.frequency} - {item.duration}</p></div> },
    { title: 'Vaccinations', documentType: 'vaccination_certificate', items: ehr.vaccinations, render: item => <div key={item.id} className="rounded-xl border border-white/60 bg-white/40 p-4"><strong>{item.vaccine_name}</strong><p className="text-sm text-slate-600">{item.administered_on} - Dose {item.dose_number || 'not specified'}</p></div> },
  ]
  return <div className="grid gap-5 lg:grid-cols-2">{sections.map(section => {
    const attachments = documents.filter(document => document.document_type === section.documentType)
    const hasContent = Boolean(section.items?.length || attachments.length)
    return <Panel bottomCircle key={section.title} title={section.title} eyebrow="Health record" action={<label className={`flex cursor-pointer items-center gap-1.5 rounded-lg bg-white/55 px-3 py-2 text-xs font-bold text-blue-700 transition hover:bg-white/75 ${uploadingSection ? 'pointer-events-none opacity-60' : ''}`}><UploadIcon />{uploadingSection === section.title ? 'Attaching...' : 'Attach file'}<input type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" className="sr-only" onChange={event => { const selected = event.target.files?.[0]; if (selected) onAttach(section, selected); event.target.value = '' }} /></label>}><div className="space-y-3">{section.items?.map(section.render)}{attachments.map(document => <RecordAttachment key={`attachment-${document.id}`} document={document} />)}{!hasContent && <Empty>No records available in this section.</Empty>}</div></Panel>
  })}</div>
}

function AnalysisResult({ analysis }) {
  if (!analysis) return <Empty>Upload a demo report or select a recent document to see its extracted parameters.</Empty>
  const rawBiomarkers = analysis.extracted_biomarkers || {}
  const biomarkers = Array.isArray(rawBiomarkers) ? rawBiomarkers : Object.entries(rawBiomarkers).map(([name, result]) => ({
    canonical_name: name,
    normalised_value: result.value,
    canonical_unit: result.unit,
    flag: result.flag,
    ref_range_low: result.ref_range?.low,
    ref_range_high: result.ref_range?.high,
  }))
  const flagStyle = flag => flag === 'normal' ? 'bg-emerald-100 text-emerald-700' : flag.includes('critical') ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
  const range = b => `${b.ref_range_low ?? 'No lower limit'} - ${b.ref_range_high ?? 'No upper limit'}`
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="rounded-full bg-blue-700 px-3 py-1 text-xs font-bold text-white">Analysis complete</span>
        <span className="rounded-full bg-white/50 px-3 py-1 text-xs font-bold text-slate-700">{Math.round((analysis.confidence_score || 0) * 100)}% extraction confidence</span>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800">Clinician review: {analysis.review_status}</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-white/60 bg-white/40">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead className="border-b border-blue-100 bg-white/35 text-xs uppercase tracking-wider text-blue-800" style={MONO}><tr><th className="px-4 py-3">Parameter</th><th className="px-4 py-3">Value</th><th className="px-4 py-3">Reference range</th><th className="px-4 py-3">Result</th></tr></thead>
          <tbody>{biomarkers.map(b => <tr key={b.canonical_name} className="border-b border-white/50 last:border-0"><td className="px-4 py-3 font-bold text-slate-900">{b.canonical_name}</td><td className="px-4 py-3 text-slate-700">{b.normalised_value} {b.canonical_unit}</td><td className="px-4 py-3 text-slate-600">{range(b)} {b.canonical_unit}</td><td className="px-4 py-3"><span className={`rounded-full px-2.5 py-1 text-xs font-bold ${flagStyle(b.flag)}`}>{b.flag.replaceAll('_', ' ')}</span></td></tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}

function AssistiveSummary({ analysis }) {
  if (!analysis) return <Empty>Upload a laboratory report to generate an AI-assisted interpretation of the extracted parameters.</Empty>
  const rawBiomarkers = analysis.extracted_biomarkers || {}
  const biomarkers = Array.isArray(rawBiomarkers)
    ? rawBiomarkers
    : Object.entries(rawBiomarkers).map(([canonical_name, result]) => ({ canonical_name, normalised_value: result.value, flag: result.flag }))
  const values = Object.fromEntries(biomarkers.map(item => [item.canonical_name, Number(item.normalised_value)]))
  const diabetesPattern = values['Fasting Blood Glucose'] >= 126 && values.HbA1c >= 6.5
  const lipidPattern = values['Total Cholesterol'] > 200 || values['LDL Cholesterol'] > 100 || values['HDL Cholesterol'] < 40 || values.Triglycerides > 150
  const allNormal = biomarkers.length > 0 && biomarkers.every(item => item.flag === 'normal')
  let indication = 'Disease indication: No disease indicated by the configured screening patterns in the uploaded parameters.'
  if (diabetesPattern) {
    indication = `Possible disease indication: The combined glucose and HbA1c pattern may indicate diabetes mellitus or persistent dysglycaemia${lipidPattern ? ', with an accompanying pattern that may indicate dyslipidaemia and increased cardiometabolic risk' : ''}. Clinician confirmation is required.`
  } else if (!allNormal) {
    indication = 'Disease indication: One or more values are outside the reference range, but the configured patterns do not indicate a specific disease. Clinical review is recommended.'
  }
  const summaryWithoutDuplicateIndication = (analysis.summary || '').split('\n').filter(line => !/Screening interpretation:|Possible condition pattern|accompanying cholesterol pattern/i.test(line)).join('\n').replace(/\n{3,}/g, '\n\n')
  return <div className="rounded-xl border border-white/60 bg-white/40 p-5"><div className={`mb-4 rounded-xl border px-4 py-3 text-sm font-bold ${diabetesPattern ? 'border-amber-200 bg-amber-50/85 text-amber-900' : 'border-emerald-200 bg-emerald-50/85 text-emerald-900'}`}>{indication}</div><p className="whitespace-pre-line text-sm leading-6 text-slate-700">{summaryWithoutDuplicateIndication}</p></div>
}

export default function PatientEHR() {
  const auth = useAuth()
  const [searchParams] = useSearchParams()
  const api = useMemo(() => createApiClient(auth), [auth.accessToken]) // eslint-disable-line react-hooks/exhaustive-deps
  const [ehr, setEhr] = useState(null)
  const [documents, setDocuments] = useState([])
  const [alerts, setAlerts] = useState([])
  const [consultations, setConsultations] = useState([])
  const [consents, setConsents] = useState([])
  const requestedTab = searchParams.get('tab')
  const [tab, setTab] = useState(['overview', 'records', 'analysis'].includes(requestedTab) ? requestedTab : 'overview')
  const [file, setFile] = useState(null)
  const [documentType, setDocumentType] = useState('lab_report')
  const [analysis, setAnalysis] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadingSection, setUploadingSection] = useState('')
  const [deletingDocumentId, setDeletingDocumentId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadData = async () => {
    const results = await Promise.allSettled([
      api.get('/api/v1/patients/me/ehr'),
      api.get('/api/v1/patients/me/documents'),
      api.get('/api/v1/patients/me/monitoring/alerts'),
      api.get('/api/v1/patients/me/telemedicine'),
      api.get('/api/v1/patients/me/consent/inbox'),
    ])
    if (results[0].status === 'fulfilled') setEhr(results[0].value)
    else setError(results[0].reason.message)
    if (results[1].status === 'fulfilled') setDocuments(results[1].value || [])
    if (results[2].status === 'fulfilled') setAlerts(results[2].value || [])
    if (results[3].status === 'fulfilled') setConsultations(results[3].value || [])
    if (results[4].status === 'fulfilled') setConsents(results[4].value || [])
  }

  useEffect(() => {
    let active = true
    Promise.allSettled([
      api.get('/api/v1/patients/me/ehr'),
      api.get('/api/v1/patients/me/documents'),
      api.get('/api/v1/patients/me/monitoring/alerts'),
      api.get('/api/v1/patients/me/telemedicine'),
      api.get('/api/v1/patients/me/consent/inbox'),
    ]).then(results => {
      if (!active) return
      if (results[0].status === 'fulfilled') setEhr(results[0].value)
      else setError(results[0].reason.message)
      if (results[1].status === 'fulfilled') setDocuments(results[1].value || [])
      if (results[2].status === 'fulfilled') setAlerts(results[2].value || [])
      if (results[3].status === 'fulfilled') setConsultations(results[3].value || [])
      if (results[4].status === 'fulfilled') setConsents(results[4].value || [])
    })
    return () => { active = false }
  }, [api])

  const viewAnalysis = async documentId => {
    setError(''); setMessage('Loading report analysis...'); setTab('analysis')
    try {
      let rows = await api.get(`/api/v1/patients/me/documents/${documentId}/analyses`)
      if (!rows.length) rows = [await api.post(`/api/v1/patients/me/documents/${documentId}/analyses`)]
      setAnalysis(rows[0]); setMessage('Report analysis loaded.')
    } catch (err) { setError(err.message); setMessage('') }
  }

  const uploadReport = async event => {
    event.preventDefault()
    if (!file) return
    setUploading(true); setError(''); setMessage('Encrypting, extracting, and analyzing the report...')
    try {
      const form = new FormData()
      form.append('document', file)
      form.append('metadata', JSON.stringify({
        document_type: documentType,
        title: file.name.replace(/\.pdf$/i, '').replaceAll('_', ' '),
        document_date: new Date().toISOString().slice(0, 10),
        description: 'Prototype demonstration report uploaded from My Health',
      }))
      const uploaded = await api.upload('/api/v1/patients/me/documents', form)
      await viewAnalysis(uploaded.id)
      await loadData()
      setFile(null)
    } catch (err) { setError(err.message); setMessage('') }
    finally { setUploading(false) }
  }

  const attachRecordFile = async (section, selectedFile) => {
    setUploadingSection(section.title); setError(''); setMessage(`Attaching ${selectedFile.name}...`)
    try {
      const form = new FormData()
      form.append('document', selectedFile)
      form.append('metadata', JSON.stringify({
        document_type: section.documentType,
        title: selectedFile.name.replace(/\.[^.]+$/, '').replaceAll('_', ' '),
        document_date: new Date().toISOString().slice(0, 10),
        description: `Attached to ${section.title} from My Health`,
      }))
      await api.upload('/api/v1/patients/me/documents', form)
      await loadData()
      setMessage(`${selectedFile.name} attached to ${section.title}.`)
    } catch (err) {
      setError(err.message); setMessage('')
    } finally {
      setUploadingSection('')
    }
  }

  const removeDocument = async document => {
    const confirmed = window.confirm(`Remove "${document.title}" permanently? This deletes the report and its stored analysis.`)
    if (!confirmed) return

    setDeletingDocumentId(document.id)
    setError('')
    setMessage(`Removing ${document.title}...`)
    try {
      await api.post(`/api/v1/patients/me/documents/${document.id}/delete`)
      setDocuments(current => current.filter(item => item.id !== document.id))
      setAnalysis(null)
      setMessage(`${document.title} was removed permanently.`)
    } catch (err) {
      setError(err.message)
      setMessage('')
    } finally {
      setDeletingDocumentId('')
    }
  }

  if (!ehr && !error) return <div className="min-h-screen bg-[#f0f5ff] pt-36 text-center font-bold text-slate-600">Loading My Health...</div>
  if (!ehr) return <div className="min-h-screen bg-[#f0f5ff] pt-36 text-center font-bold text-red-600">{error}</div>

  const openAlerts = alerts.filter(a => a.status === 'open')
  const upcoming = consultations.filter(c => ['scheduled', 'confirmed'].includes(c.status)).slice(0, 3)
  const tabs = [['overview', 'Overview'], ['records', 'Health Records'], ['analysis', 'Report Analysis']]

  return (
    <section className="min-h-screen bg-[#f0f5ff] pb-16 pt-[108px]" style={{ fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}>
      <div className="mx-auto max-w-[1360px] px-10">
        <div className="relative mb-7 flex min-h-[180px] items-center justify-between gap-8 overflow-hidden rounded-2xl bg-[#0f1e3d] px-12 py-10">
          <div className="pointer-events-none absolute -top-16 right-48 h-72 w-72 rounded-full border-[50px] border-white/[0.04]" />
          <div className="pointer-events-none absolute -bottom-20 right-12 h-56 w-56 rounded-full border-[36px] border-white/[0.035]" />
          <div className="relative z-10">
            <div className="mb-3 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.2em] text-blue-300" style={MONO}><HeartIcon /> Personal health hub</div>
            <h1 className="text-[34px] font-extrabold leading-tight tracking-tight text-white">My <span className="text-blue-300">Health</span></h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-blue-200">Your health summary, longitudinal records, secure reports, and prototype AI-assisted report analysis in one place.</p>
          </div>
          <div className="relative z-10 rounded-2xl border border-white/15 bg-white/[0.08] px-8 py-4 text-center">
            <div className="text-xs font-bold uppercase tracking-widest text-white/50" style={MONO}>Medical record</div>
            <div className="mt-1 font-extrabold text-white">{ehr.patient.medical_record_number}</div>
          </div>
        </div>

        <div className="mb-6 flex gap-2 rounded-2xl border border-blue-100 bg-white/70 p-2 shadow-sm">
          {tabs.map(([key, label]) => <button key={key} onClick={() => setTab(key)} className={`rounded-xl px-5 py-2.5 text-sm font-bold transition-colors ${tab === key ? 'bg-blue-700 text-white shadow-sm' : 'text-slate-600 hover:bg-blue-50 hover:text-blue-700'}`}>{label}</button>)}
        </div>

        {error && <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700">{error}</div>}
        {message && tab !== 'analysis' && <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm font-bold text-blue-800">{message}</div>}

        {tab === 'overview' && <div className="space-y-6">
          <div className="grid gap-5 lg:grid-cols-2">
            <Panel bottomCircle title="Recent medical reports" eyebrow="Secure documents" action={<button onClick={() => setTab('analysis')} className="text-xs font-bold text-blue-700">Upload report</button>}>
              <div className="space-y-3">
                {documents.slice(0, 4).map(document => (
                  <div key={document.id} className="flex items-center justify-between gap-4 rounded-xl border border-white/60 bg-white/40 p-4">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-bold text-slate-900">{document.title}</div>
                      <div className="mt-1 text-xs text-slate-600">{document.document_type.replaceAll('_', ' ')} - {fmtDate(document.created_at)}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        onClick={() => removeDocument(document)}
                        disabled={deletingDocumentId === document.id}
                        className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs font-bold text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <TrashIcon /> {deletingDocumentId === document.id ? 'Removing...' : 'Remove'}
                      </button>
                      <button type="button" onClick={() => viewAnalysis(document.id)} className="rounded-lg bg-blue-700 px-3 py-2 text-xs font-bold text-white">View analysis</button>
                    </div>
                  </div>
                ))}
                {!documents.length && <Empty>No reports uploaded yet. Use Report Analysis to try a demo PDF.</Empty>}
              </div>
            </Panel>
            <Panel bottomCircle title="Care activity" eyebrow="Meaningful updates">
              <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-white/40 p-4"><div className="text-2xl font-extrabold text-blue-700">{openAlerts.length}</div><div className="text-xs font-bold text-slate-700">Open monitoring alerts</div></div><div className="rounded-xl bg-white/40 p-4"><div className="text-2xl font-extrabold text-blue-700">{upcoming.length}</div><div className="text-xs font-bold text-slate-700">Upcoming consultations</div></div><div className="rounded-xl bg-white/40 p-4"><div className="text-2xl font-extrabold text-blue-700">{consents.length}</div><div className="text-xs font-bold text-slate-700">Consent requests</div></div></div>
              <div className="mt-4 flex flex-wrap gap-3"><Link to="/monitoring" className="rounded-xl bg-white/50 px-4 py-2 text-xs font-bold text-blue-700">View monitoring</Link><Link to="/sharing" className="rounded-xl bg-white/50 px-4 py-2 text-xs font-bold text-blue-700">Manage sharing</Link><Link to="/bookings" className="rounded-xl bg-blue-700 px-4 py-2 text-xs font-bold text-white">Book token</Link></div>
            </Panel>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <CountCard icon={<FileIcon />} label="Clinical encounters" value={ehr.encounters?.length} note="Longitudinal visit history" />
            <CountCard icon={<ActivityIcon />} label="Active prescriptions" value={ehr.meta?.active_prescription_count} note="Current medication plan" />
            <CountCard icon={<ShieldIcon />} label="Recorded allergies" value={ehr.meta?.active_allergy_count} note="Active safety alerts" />
            <CountCard icon={<CalendarIcon />} label="Vaccinations" value={ehr.vaccinations?.length} note="Verified immunization records" />
          </div>
        </div>}

        {tab === 'records' && <RecordsView ehr={ehr} documents={documents} onAttach={attachRecordFile} uploadingSection={uploadingSection} />}

        {tab === 'analysis' && <div>
          <div className="grid gap-5 lg:grid-cols-[0.82fr_1.18fr]">
            <Panel className="h-full" bottomCircle title="Upload medical report" eyebrow="Prototype analysis">
              <form onSubmit={uploadReport} className="space-y-4">
                <div><label className="mb-2 block text-sm font-bold text-slate-900">Report type</label><select value={documentType} onChange={e => setDocumentType(e.target.value)} className="w-full rounded-xl border border-blue-100 bg-white/70 px-4 py-3 text-sm outline-none focus:border-blue-500"><option value="lab_report">Lab report</option><option value="imaging">Imaging report</option><option value="discharge_summary">Discharge summary</option></select></div>
                <label className="flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed border-blue-400 bg-white/35 px-6 py-8 text-center transition-colors hover:bg-white/50"><span className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-blue-700 text-white"><UploadIcon /></span><span className="text-sm font-extrabold text-slate-900">{file ? file.name : 'Choose a PDF report'}</span><span className="mt-1 text-xs text-slate-600">Text-based PDF, up to 20 MB</span><input type="file" accept="application/pdf,.pdf" className="sr-only" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
                <button disabled={!file || uploading} className="w-full rounded-xl bg-blue-700 px-5 py-3 text-sm font-extrabold text-white shadow-md disabled:cursor-not-allowed disabled:opacity-50">{uploading ? 'Analyzing report...' : 'Upload and analyze'}</button>
                {message && <p className="text-xs font-bold text-blue-800">{message}</p>}
              </form>
            </Panel>
            <Panel className="h-full" bottomCircle title="Structured analysis output" eyebrow="Extracted parameters"><AnalysisResult analysis={analysis} /></Panel>
          </div>
          <div className="mt-5"><Panel bottomCircle title="AI Assistive Summary" eyebrow="Clinical decision support"><AssistiveSummary analysis={analysis} /></Panel></div>
        </div>}

        <HowItWorks title="How My Health works" steps={[
          { title: 'Build your health record', description: 'Upload reports and keep encounters, prescriptions, allergies, and vaccinations organized in one secure place.' },
          { title: 'Review meaningful insights', description: 'Open structured report analysis and see important medical parameters in a clear, presentation-ready format.' },
          { title: 'Continue your care', description: 'Use your health information with monitoring, secure sharing, and token booking whenever follow-up care is needed.' },
        ]} />
      </div>
    </section>
  )
}
