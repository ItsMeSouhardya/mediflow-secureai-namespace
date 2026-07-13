/**
 * Integrated Patient Dashboard — task 14.8
 *
 * Panels:
 *  - Active queue token (live SSE position + wait estimate)
 *  - Upcoming appointments / telemedicine sessions
 *  - EHR summary snapshot (encounters, prescriptions, allergies)
 *  - Monitoring alerts (open/acknowledged)
 *  - Recent documents
 *  - Pending consent requests (inbox count badge)
 *  - Quick links
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/authState'
import { createApiClient } from '../api/client'
import { useQuery, useStream } from '../api/useQuery'
import {
  Alert, Button, Card, EmptyState, PageHeader,
  SectionCard, Spinner, StatCard, StatusBadge,
} from '../components/ui/index'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

// ---------------------------------------------------------------------------
// Sub-panels
// ---------------------------------------------------------------------------

function QueuePanel({ api }) {
  const { data: tokens, loading } = useQuery(
    'patient-tokens',
    () => api.get('/api/v1/patients/me/tokens'),
    { staleMs: 10_000 },
  )
  const active = useMemo(() => tokens?.find(t => t.status === 'waiting'), [tokens])

  // SSE live update for the active token's department.
  const [liveState, setLiveState] = useState(null)
  useStream(
    active ? `/api/v1/queue/live/${active.dept_id}` : null,
    setLiveState,
  )

  if (loading) return <div className="flex justify-center py-8"><Spinner label="Loading queue status" /></div>
  if (!active) return (
    <EmptyState
      icon="🎫"
      title="No active queue token"
      description="Book a token to join a department queue."
      action={<Button as={Link} to="/bookings" size="sm">Book token</Button>}
    />
  )

  const pos = liveState?.position ?? active.position
  const wait = liveState?.estimated_wait_minutes ?? active.estimated_wait_minutes

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-xl bg-blue-700 px-5 py-4 text-white">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-blue-200">Your token</p>
          <p className="mt-1 text-4xl font-extrabold">{active.token_number}</p>
          <p className="mt-1 text-sm text-blue-200">Dept #{active.dept_id} · {fmt(active.queue_date)}</p>
        </div>
        <div className="text-right">
          <p className="text-xs font-bold uppercase tracking-widest text-blue-200">Position</p>
          <p className="mt-1 text-4xl font-extrabold">{pos ?? '—'}</p>
          {wait != null && <p className="mt-1 text-sm text-blue-200">~{wait} min wait</p>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={active.priority === 'emergency' ? 'open' : 'waiting'} />
        <span className="text-xs text-slate-500 capitalize">Priority: {active.priority}</span>
        {liveState && <span className="ml-auto text-xs text-emerald-600">● Live</span>}
      </div>
    </div>
  )
}

function AppointmentsPanel({ api }) {
  const { data, loading } = useQuery(
    'patient-appointments-tele',
    () => api.get('/api/v1/patients/me/telemedicine'),
    { staleMs: 60_000 },
  )
  const upcoming = useMemo(
    () => (data ?? []).filter(s => ['scheduled', 'confirmed'].includes(s.status)).slice(0, 4),
    [data],
  )
  if (loading) return <Spinner label="Loading appointments" className="mx-auto block py-4" />
  if (!upcoming.length) return <EmptyState icon="📅" title="No upcoming consultations" />

  return (
    <ul className="space-y-3" aria-label="Upcoming telemedicine sessions">
      {upcoming.map(s => (
        <li key={s.id} className="flex items-start justify-between rounded-xl border border-slate-100 p-4">
          <div>
            <p className="text-sm font-bold text-slate-900">{fmt(s.scheduled_start)} {fmtTime(s.scheduled_start)}</p>
            <p className="text-xs text-slate-500 mt-0.5">Provider: {s.provider}</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <StatusBadge status={s.status} />
            {s.status === 'confirmed' && (
              <Link to={`/telemedicine/${s.id}`} className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">
                Join →
              </Link>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}

function EhrSnapshotPanel({ ehr }) {
  if (!ehr) return <Spinner label="Loading EHR" className="mx-auto block py-4" />
  return (
    <div className="grid grid-cols-3 gap-3">
      <div className="rounded-xl bg-slate-50 p-4 text-center">
        <p className="text-2xl font-extrabold text-blue-700">{ehr.encounters?.length ?? 0}</p>
        <p className="text-xs text-slate-500 mt-0.5">Encounters</p>
      </div>
      <div className="rounded-xl bg-slate-50 p-4 text-center">
        <p className="text-2xl font-extrabold text-blue-700">{ehr.meta?.active_prescription_count ?? 0}</p>
        <p className="text-xs text-slate-500 mt-0.5">Active Rx</p>
      </div>
      <div className="rounded-xl bg-slate-50 p-4 text-center">
        <p className="text-2xl font-extrabold text-red-600">{ehr.meta?.active_allergy_count ?? 0}</p>
        <p className="text-xs text-slate-500 mt-0.5">Allergies</p>
      </div>
      <Link
        to="/health-record"
        className="col-span-3 text-center text-sm font-semibold text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
      >
        View full health record →
      </Link>
    </div>
  )
}

function AlertsPanel({ api }) {
  const { data, loading } = useQuery(
    'patient-monitoring-alerts',
    () => api.get('/api/v1/patients/me/monitoring/alerts'),
    { staleMs: 30_000 },
  )
  const open = useMemo(() => (data ?? []).filter(a => a.status === 'open').slice(0, 5), [data])
  if (loading) return <Spinner label="Loading alerts" className="mx-auto block py-4" />
  if (!open.length) return <EmptyState icon="✅" title="No open monitoring alerts" />
  return (
    <ul className="space-y-2" aria-label="Open monitoring alerts">
      {open.map(a => (
        <li key={a.id} className="flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 p-3">
          <span className="mt-0.5 text-red-600 font-bold text-xs uppercase">{a.severity}</span>
          <p className="text-sm text-red-800 flex-1">{a.message}</p>
          <StatusBadge status={a.status} />
        </li>
      ))}
    </ul>
  )
}

function DocumentsPanel({ api }) {
  const { data, loading } = useQuery(
    'patient-documents-recent',
    () => api.get('/api/v1/patients/me/documents', { status: 'ready' }),
    { staleMs: 60_000 },
  )
  const docs = useMemo(() => (data ?? []).slice(0, 4), [data])
  if (loading) return <Spinner label="Loading documents" className="mx-auto block py-4" />
  if (!docs.length) return (
    <EmptyState
      icon="📄"
      title="No medical documents"
      action={<Button as={Link} to="/health-record" size="sm" variant="secondary">Upload document</Button>}
    />
  )
  return (
    <ul className="space-y-2" aria-label="Recent documents">
      {docs.map(d => (
        <li key={d.id} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-slate-900 truncate max-w-[160px]">{d.title}</p>
            <p className="text-xs text-slate-500">{d.document_type} · {fmt(d.document_date)}</p>
          </div>
          <StatusBadge status={d.status} />
        </li>
      ))}
    </ul>
  )
}

function ConsentInboxPanel({ api }) {
  const { data, loading } = useQuery(
    'patient-consent-inbox',
    () => api.get('/api/v1/patients/me/consent/inbox'),
    { staleMs: 30_000 },
  )
  const count = data?.length ?? 0
  if (loading) return <Spinner label="Loading consent inbox" className="mx-auto block py-4" />
  if (!count) return <EmptyState icon="🔒" title="No pending consent requests" />
  return (
    <div className="flex flex-col gap-3">
      <Alert variant="warning" title={`${count} access request${count > 1 ? 's' : ''} awaiting your decision`}>
        Review and respond to keep your records secure.
      </Alert>
      <Link
        to="/sharing"
        className="text-sm font-semibold text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
        aria-label={`Review ${count} consent request${count > 1 ? 's' : ''}`}
      >
        Review requests →
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function PatientDashboard() {
  const auth = useAuth()
  const api = useMemo(() => createApiClient(auth), [auth.accessToken]) // eslint-disable-line

  const { data: ehr, loading: ehrLoading } = useQuery(
    'patient-ehr',
    () => api.get('/api/v1/patients/me/ehr'),
    { staleMs: 60_000 },
  )

  return (
    <main className="min-h-screen bg-slate-50 px-4 pb-16 pt-24 sm:px-6">
      <div className="mx-auto max-w-7xl space-y-6">

        {/* Header */}
        <PageHeader
          eyebrow="Patient Dashboard"
          title={ehr?.patient?.name ?? 'Welcome back'}
          subtitle={ehr ? `MRN ${ehr.patient.medical_record_number}` : 'Loading your health summary…'}
          actions={
            <Link to="/bookings">
              <Button aria-label="Book a new hospital token">Book Token</Button>
            </Link>
          }
        />

        {/* Top stat row */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Encounters"   value={ehr?.encounters?.length}              icon="🏥" color="blue" />
          <StatCard label="Active Rx"    value={ehr?.meta?.active_prescription_count} icon="💊" color="green" />
          <StatCard label="Allergies"    value={ehr?.meta?.active_allergy_count}      icon="⚠️" color="red" />
          <StatCard label="Vaccinations" value={ehr?.vaccinations?.length}            icon="💉" color="slate" />
        </div>

        {/* Main grid */}
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <SectionCard title="Queue status">
              <QueuePanel api={api} />
            </SectionCard>
            <SectionCard title="EHR snapshot" actions={<Link to="/health-record" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">View all</Link>}>
              <EhrSnapshotPanel ehr={ehr} />
            </SectionCard>
            <SectionCard title="Monitoring alerts" actions={<Link to="/monitoring" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">View all</Link>}>
              <AlertsPanel api={api} />
            </SectionCard>
          </div>

          <div className="space-y-5">
            <SectionCard title="Pending consent requests">
              <ConsentInboxPanel api={api} />
            </SectionCard>
            <SectionCard title="Upcoming consultations" actions={<Link to="/bookings" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">Book</Link>}>
              <AppointmentsPanel api={api} />
            </SectionCard>
            <SectionCard title="Recent documents" actions={<Link to="/health-record" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">View all</Link>}>
              <DocumentsPanel api={api} />
            </SectionCard>
          </div>
        </div>

      </div>
    </main>
  )
}
