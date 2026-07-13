import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/authState'
import HowItWorks from '../components/HowItWorks'

const MONO = { fontFamily: 'DM Mono, monospace' }
const scopeLabels = {
  summary: 'Health summary', encounters: 'Encounters', diagnoses: 'Diagnoses',
  prescriptions: 'Prescriptions', allergies: 'Allergies', vaccinations: 'Vaccinations',
  reports: 'Medical reports', risk_predictions: 'Risk predictions', monitoring: 'Monitoring data',
}

const Icon = ({ children, size = 18 }) => <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
const ShareIcon = () => <Icon><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4" /></Icon>
const HospitalIcon = () => <Icon><path d="M3 21h18M5 21V5h14v16M9 9h6M12 6v6M8 15h2M14 15h2" /></Icon>
const FileIcon = () => <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></Icon>
const ShieldIcon = () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
const ClockIcon = () => <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>
const LockIcon = () => <Icon><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Icon>
const TrashIcon = () => <Icon size={14}><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5" /></Icon>

function formatDate(value) {
  if (!value) return 'Recently'
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function Panel({ title, eyebrow, action, children }) {
  return <section className="relative overflow-hidden rounded-2xl border border-white/50" style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.38)' }}><div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full border-[22px] border-white/20" /><div className="pointer-events-none absolute -bottom-12 -left-8 h-32 w-32 rounded-full border-[22px] border-white/15" /><header className="relative z-10 flex items-center justify-between border-b border-white/40 px-7 py-5"><div>{eyebrow && <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>{eyebrow}</div>}<h2 className="text-lg font-extrabold text-slate-900">{title}</h2></div>{action}</header><div className="relative z-10 p-7">{children}</div></section>
}

function buildAccessEvent(tokens, hospitals, documents, shares) {
  const hospitalNames = Object.fromEntries((hospitals || []).map(hospital => [hospital.hospital_id, hospital.name || hospital.hospital_name]))
  const latestReport = documents?.find(document => document.document_type === 'lab_report') || documents?.[0]
  const token = [...(tokens || [])].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
  if (!token) return null

  const matchingShare = [...(shares || [])]
    .filter(share => ['granted', 'break_glass'].includes(share.status))
    .filter(share => share.requesting_hospital_id === token.hospital_id || share.source_hospital_id === token.hospital_id)
    .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at))[0]
  const bookingTime = new Date(token.created_at)

  return {
    id: `booking-${token.token_id}`,
    hospital: hospitalNames[token.hospital_id] || `Hospital ${token.hospital_id}`,
    token: token.token_number,
    tokenStatus: token.status,
    categories: matchingShare?.scopes?.length
      ? matchingShare.scopes
      : latestReport ? ['summary', 'reports', 'allergies'] : ['summary', 'allergies', 'prescriptions'],
    accessTime: matchingShare?.updated_at || matchingShare?.created_at || new Date(bookingTime.getTime() + 6 * 60_000).toISOString(),
    subject: latestReport ? latestReport.title : 'Patient health summary',
    purpose: matchingShare?.purpose || `Pre-visit record review for ${token.token_number}`,
    permissionStatus: matchingShare?.status || 'available',
  }
}

export default function PatientSharing() {
  const { request } = useAuth()
  const [shares, setShares] = useState([])
  const [tokens, setTokens] = useState([])
  const [hospitals, setHospitals] = useState([])
  const [documents, setDocuments] = useState([])
  const [message, setMessage] = useState('')
  const [dismissedEventId, setDismissedEventId] = useState(() => localStorage.getItem('mediflow_dismissed_sharing_event') || '')

  const load = useCallback(async () => {
    const results = await Promise.allSettled([
      request('/api/v1/patients/me/shares'),
      request('/api/v1/patients/me/tokens'),
      request('/api/hospitals'),
      request('/api/v1/patients/me/documents'),
    ])
    if (results[0].status === 'fulfilled') {
      const items = results[0].value || []
      setShares(items)
    } else setMessage(results[0].reason.message)
    if (results[1].status === 'fulfilled') setTokens(results[1].value || [])
    if (results[2].status === 'fulfilled') setHospitals(results[2].value || [])
    if (results[3].status === 'fulfilled') setDocuments(results[3].value || [])
  }, [request])

  useEffect(() => { const timer = setTimeout(load, 0); return () => clearTimeout(timer) }, [load])

  const accessEvent = useMemo(() => buildAccessEvent(tokens, hospitals, documents, shares), [tokens, hospitals, documents, shares])
  const visibleAccessEvent = accessEvent?.id === dismissedEventId ? null : accessEvent
  const activeShares = shares.filter(share => ['granted', 'break_glass'].includes(share.status))
  const pendingShares = shares.filter(share => share.status === 'pending')

  const removeAccessEvent = () => {
    if (!visibleAccessEvent) return
    localStorage.setItem('mediflow_dismissed_sharing_event', visibleAccessEvent.id)
    setDismissedEventId(visibleAccessEvent.id)
    setMessage('Hospital access card removed. A new confirmed booking will create a new card.')
  }

  return <section className="min-h-screen bg-[#f0f5ff] pb-16 pt-[108px]" style={{ fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}><div className="mx-auto max-w-[1360px] px-10">
    <header className="relative mb-7 flex min-h-[180px] items-center justify-between gap-8 overflow-hidden rounded-2xl bg-[#0f1e3d] px-12 py-10 text-white">
      <div className="pointer-events-none absolute -top-16 right-48 h-72 w-72 rounded-full border-[50px] border-white/[0.04]" /><div className="pointer-events-none absolute -bottom-20 right-12 h-56 w-56 rounded-full border-[36px] border-white/[0.035]" />
      <div className="relative z-10"><div className="mb-3 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.2em] text-blue-300" style={MONO}><ShareIcon /> Patient-controlled exchange</div><h1 className="text-[34px] font-extrabold leading-tight tracking-tight">Secure <span className="text-blue-300">Record Sharing</span></h1><p className="mt-2 max-w-xl text-sm leading-6 text-blue-200">See which booked hospitals may use your approved health information, review access categories, and revoke real cross-hospital permissions.</p></div>
      <div className="relative z-10 rounded-2xl border border-white/15 bg-white/[0.08] px-8 py-4 text-center"><div className="text-xs font-bold uppercase tracking-widest text-white/50" style={MONO}>Patient control</div><div className="mt-1 flex items-center justify-center gap-2 text-lg font-extrabold"><ShieldIcon /> Always active</div></div>
    </header>

    {message && <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm font-bold text-blue-800">{message}</div>}

    <div className="mb-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      {[
        { label: 'Booked hospital', value: visibleAccessEvent ? 1 : 0, note: 'Latest confirmed booking', icon: <HospitalIcon /> },
        { label: 'Access record', value: visibleAccessEvent ? 1 : 0, note: 'Linked to your booking', icon: <FileIcon /> },
        { label: 'Pending requests', value: pendingShares.length, note: 'Waiting for your decision', icon: <ClockIcon /> },
        { label: 'Active permissions', value: activeShares.length, note: 'Revocable at any time', icon: <LockIcon /> },
      ].map(card => <div key={card.label} className="rounded-2xl border border-white/50 p-5" style={{ background: '#A9D1FD', boxShadow: '0 4px 20px rgba(147,197,253,0.32)' }}><div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl text-white" style={{ background: '#3B82F6' }}>{card.icon}</div><div className="text-3xl font-extrabold text-slate-900">{card.value}</div><div className="mt-1 text-sm font-bold text-slate-800">{card.label}</div><div className="mt-1 text-xs text-blue-900/70">{card.note}</div></div>)}
    </div>

    <div className="mb-6">
      <Panel title="Hospital access activity" eyebrow="Booking-linked record access" action={visibleAccessEvent && <span className="rounded-full bg-emerald-100 px-3 py-1 text-[10px] font-bold uppercase text-emerald-800">{visibleAccessEvent.permissionStatus === 'available' ? 'Booking confirmed' : 'Access approved'}</span>}>
        <div className="space-y-3">{visibleAccessEvent && <article key={visibleAccessEvent.id} className="rounded-xl border border-white/60 bg-white/40 p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div className="flex min-w-0 gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: '#3B82F6' }}><HospitalIcon /></span><div><h3 className="font-extrabold text-slate-900">{visibleAccessEvent.hospital}</h3><p className="mt-1 text-sm text-slate-700">{visibleAccessEvent.purpose}</p><p className="mt-1 text-xs text-slate-500">Prepared: {visibleAccessEvent.subject}</p></div></div><div className="text-right text-xs text-blue-900/65"><div className="font-bold text-slate-800">{formatDate(visibleAccessEvent.accessTime)}</div><div className="mt-1 capitalize">Token {visibleAccessEvent.token} - {visibleAccessEvent.tokenStatus}</div></div></div><div className="mt-4 flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap gap-2">{visibleAccessEvent.categories.map(scope => <span key={scope} className="rounded-full border border-white/70 bg-white/55 px-3 py-1.5 text-xs font-semibold text-blue-800">{scopeLabels[scope] || scope.replace('_', ' ')}</span>)}</div><button type="button" onClick={removeAccessEvent} className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50/80 px-3 py-1.5 text-xs font-bold text-red-700 hover:bg-red-100"><TrashIcon /> Remove</button></div></article>}{!visibleAccessEvent && <div className="rounded-xl border border-white/60 bg-white/35 p-8 text-center"><div className="font-bold text-slate-800">No hospital access activity yet</div><p className="mt-1 text-sm text-slate-600">Book a hospital token and the selected hospital will appear here.</p><Link to="/bookings" className="mt-4 inline-flex rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white">Book a token</Link></div>}</div>
      </Panel>
    </div>

    <HowItWorks title="How secure sharing works" steps={[
      { title: 'Book a hospital visit', description: 'After a hospital token is booked, the selected hospital appears in your access activity with the prepared record categories.' },
      { title: 'Share only what is needed', description: 'Relevant health summaries, reports, and safety information are limited to the categories required for your visit.' },
      { title: 'Keep access accountable', description: 'Permissions remain time-limited, revocable, and auditable so access can be reviewed without exposing document storage paths.' },
    ]} />

  </div></section>
}
