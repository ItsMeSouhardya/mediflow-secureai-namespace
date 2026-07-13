/**
 * Integrated Doctor Dashboard — task 14.9
 *
 * Panels:
 *  - My patient list with quick access to clinical workspace
 *  - Open monitoring alerts requiring acknowledgement
 *  - Pending consent requests from patients (inbox)
 *  - Upcoming telemedicine sessions
 *  - Pending AI analysis reviews
 *  - Queue next-token for the doctor's department
 */
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/authState'
import { createApiClient } from '../api/client'
import { useQuery } from '../api/useQuery'
import {
  Alert, Button, Card, EmptyState, PageHeader,
  SectionCard, Spinner, StatCard, StatusBadge, Table,
} from '../components/ui/index'

function fmt(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

// ---------------------------------------------------------------------------
// Panels
// ---------------------------------------------------------------------------

function PatientListPanel({ api }) {
  const { data, loading } = useQuery(
    'doctor-patients',
    () => api.get('/api/v1/doctors/me/patients'),
    { staleMs: 60_000 },
  )
  const patients = (data ?? []).slice(0, 8)

  const columns = [
    { key: 'name',                  label: 'Patient' },
    { key: 'medical_record_number', label: 'MRN', width: 130 },
    { key: 'age',                   label: 'Age', width: 60 },
    {
      key: 'patient_profile_id',
      label: '',
      width: 60,
      render: (_, row) => (
        <Link
          to={`/clinical-workspace?patient=${row.patient_profile_id}`}
          className="text-xs font-semibold text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
          aria-label={`Open clinical workspace for ${row.name}`}
        >
          Open
        </Link>
      ),
    },
  ]

  return (
    <Table
      columns={columns}
      rows={patients}
      keyField="patient_profile_id"
      loading={loading}
      emptyMessage="No patients assigned yet."
    />
  )
}

function AlertsPanel({ api }) {
  const { data, loading } = useQuery(
    'doctor-monitoring-alerts',
    () => api.get('/api/v1/doctors/me/monitoring/alerts'),
    { staleMs: 20_000 },
  )
  const open = (data ?? []).filter(a => a.status === 'open').slice(0, 5)
  if (loading) return <Spinner label="Loading alerts" className="mx-auto block py-4" />
  if (!open.length) return <EmptyState icon="✅" title="No open alerts" />
  return (
    <ul className="space-y-2" aria-label="Open monitoring alerts">
      {open.map(a => (
        <li key={a.id} className="flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 p-3">
          <span className="mt-0.5 text-xs font-bold uppercase text-red-600">{a.severity}</span>
          <p className="flex-1 text-sm text-red-800">{a.message}</p>
          <Link
            to="/monitoring/triage"
            className="text-xs font-semibold text-red-700 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-500 rounded flex-shrink-0"
            aria-label="Go to alert triage"
          >
            Triage →
          </Link>
        </li>
      ))}
    </ul>
  )
}

function ConsentRequestsPanel({ api }) {
  const { data, loading } = useQuery(
    'doctor-consent-requests',
    () => api.get('/api/v1/doctors/me/consent/requests'),
    { staleMs: 30_000 },
  )
  const pending = (data ?? []).filter(r => r.status === 'pending').slice(0, 5)
  if (loading) return <Spinner label="Loading consent requests" className="mx-auto block py-4" />
  if (!pending.length) return <EmptyState icon="🔒" title="No pending consent requests" />
  return (
    <ul className="space-y-2" aria-label="Pending consent requests">
      {pending.map(r => (
        <li key={r.id} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">Patient #{r.patient_profile_id}</p>
            <p className="text-xs text-slate-500 mt-0.5 truncate max-w-[180px]">{r.purpose}</p>
          </div>
          <StatusBadge status={r.status} />
        </li>
      ))}
    </ul>
  )
}

function TelemedicinePanel({ api }) {
  const { data, loading } = useQuery(
    'doctor-telemedicine',
    () => api.get('/api/v1/doctors/me/telemedicine', { status: 'confirmed' }),
    { staleMs: 30_000 },
  )
  const sessions = (data ?? []).slice(0, 4)
  if (loading) return <Spinner label="Loading sessions" className="mx-auto block py-4" />
  if (!sessions.length) return <EmptyState icon="📹" title="No upcoming telemedicine sessions" />
  return (
    <ul className="space-y-2" aria-label="Upcoming telemedicine sessions">
      {sessions.map(s => (
        <li key={s.id} className="flex items-center justify-between rounded-xl border border-slate-100 px-4 py-3">
          <div>
            <p className="text-sm font-bold text-slate-900">{fmt(s.scheduled_start)} {fmtTime(s.scheduled_start)}</p>
            <p className="text-xs text-slate-500 mt-0.5">Patient #{s.patient_profile_id}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={s.status} />
            <Link
              to={`/telemedicine/${s.id}`}
              className="text-xs font-semibold text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
            >
              Join →
            </Link>
          </div>
        </li>
      ))}
    </ul>
  )
}

function PendingAnalysisPanel({ api }) {
  const { data, loading } = useQuery(
    'doctor-risk-predictions-pending',
    () => api.get('/api/v1/doctors/me/patients'),   // placeholder until direct pending-analyses endpoint
    { staleMs: 60_000, enabled: false },            // disabled — no direct endpoint yet; shown as UI stub
  )
  return (
    <EmptyState
      icon="🔬"
      title="AI analysis review"
      description="Navigate to a patient's record to review and accept pending AI analysis results."
      action={
        <Link to="/clinical-workspace">
          <Button size="sm" variant="secondary">Open clinical workspace</Button>
        </Link>
      }
    />
  )
}

function NextTokenPanel({ api }) {
  // We don't know the doctor's dept_id without an extra call — show a link instead.
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-600">View the priority-ordered queue for your department and call the next patient.</p>
      <Link to="/monitoring/triage">
        <Button variant="secondary" size="sm" aria-label="Open queue triage view">
          Open queue triage →
        </Button>
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function DoctorDashboard() {
  const auth = useAuth()
  const api = useMemo(() => createApiClient(auth), [auth.accessToken]) // eslint-disable-line

  const { data: patients } = useQuery(
    'doctor-patients-count',
    () => api.get('/api/v1/doctors/me/patients'),
    { staleMs: 120_000 },
  )
  const { data: alerts } = useQuery(
    'doctor-alerts-count',
    () => api.get('/api/v1/doctors/me/monitoring/alerts'),
    { staleMs: 20_000 },
  )
  const openAlertCount = (alerts ?? []).filter(a => a.status === 'open').length

  return (
    <main className="min-h-screen bg-slate-50 px-4 pb-16 pt-24 sm:px-6">
      <div className="mx-auto max-w-7xl space-y-6">

        <PageHeader
          eyebrow="Doctor Dashboard"
          title={`Dr. ${auth.user?.name ?? '…'}`}
          subtitle="Clinical overview — decision support only"
          actions={
            <Link to="/clinical-workspace">
              <Button aria-label="Open clinical workspace">Clinical Workspace</Button>
            </Link>
          }
        />

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Assigned patients" value={patients?.length}    icon="👥" color="blue"  />
          <StatCard label="Open alerts"        value={openAlertCount}     icon="🚨" color="red"   />
          <StatCard label="Telemedicine"       value="—"                  icon="📹" color="green" />
          <StatCard label="Pending reviews"    value="—"                  icon="🔬" color="amber" />
        </div>

        {openAlertCount > 0 && (
          <Alert variant="error" title={`${openAlertCount} open monitoring alert${openAlertCount > 1 ? 's' : ''} require your attention`}>
            <Link to="/monitoring/triage" className="font-semibold underline">Go to triage →</Link>
          </Alert>
        )}

        {/* Main grid */}
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <SectionCard
              title="My patients"
              count={patients?.length}
              actions={<Link to="/clinical-workspace" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">Workspace</Link>}
            >
              <PatientListPanel api={api} />
            </SectionCard>
            <SectionCard title="Monitoring alerts" actions={<Link to="/monitoring/triage" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">Triage</Link>}>
              <AlertsPanel api={api} />
            </SectionCard>
            <SectionCard title="AI analysis pending review">
              <PendingAnalysisPanel api={api} />
            </SectionCard>
          </div>

          <div className="space-y-5">
            <SectionCard title="Queue — next patient">
              <NextTokenPanel api={api} />
            </SectionCard>
            <SectionCard title="Upcoming telemedicine">
              <TelemedicinePanel api={api} />
            </SectionCard>
            <SectionCard title="Consent requests" actions={<Link to="/incoming-shares" className="text-xs text-blue-700 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">All shares</Link>}>
              <ConsentRequestsPanel api={api} />
            </SectionCard>
          </div>
        </div>

      </div>
    </main>
  )
}
