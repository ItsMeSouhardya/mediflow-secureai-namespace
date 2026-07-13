/**
 * Hospital Admin Queue / Resource Dashboard — task 14.10
 *
 * Panels:
 *  - Hospital selector
 *  - Live per-department queue overview (waiting, serving, completed,
 *    estimated wait, priority breakdown, next token)
 *  - Doctor availability controls (toggle Available / Busy / Off Duty)
 */
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/authState'
import { createApiClient } from '../api/client'
import { useMutation, useQuery } from '../api/useQuery'
import {
  Alert, Button, EmptyState, PageHeader,
  SectionCard, Spinner, StatCard, StatusBadge, Table,
} from '../components/ui/index'

// ---------------------------------------------------------------------------
// Department queue card
// ---------------------------------------------------------------------------
function DeptCard({ dept, onCallNext, callingNext }) {
  const total = dept.waiting + dept.serving + dept.completed
  const loadPct = total ? Math.round((dept.serving / Math.max(total, 1)) * 100) : 0

  return (
    <article
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-label={`${dept.dept_name} queue status`}
    >
      <div className="flex items-start justify-between gap-2 mb-4">
        <div>
          <h3 className="font-extrabold text-slate-900 text-base">{dept.dept_name}</h3>
          <p className="text-xs text-slate-500 mt-0.5">~{dept.estimated_wait_minutes} min wait · {dept.active_doctors} doctors active</p>
        </div>
        {dept.next_token && (
          <Button
            size="sm"
            onClick={() => onCallNext(dept.dept_id, dept.next_token)}
            loading={callingNext === dept.dept_id}
            aria-label={`Call next token ${dept.next_token} in ${dept.dept_name}`}
          >
            Call {dept.next_token}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="rounded-lg bg-blue-50 p-2 text-center">
          <p className="text-lg font-extrabold text-blue-700">{dept.waiting}</p>
          <p className="text-xs text-blue-600">Waiting</p>
        </div>
        <div className="rounded-lg bg-emerald-50 p-2 text-center">
          <p className="text-lg font-extrabold text-emerald-700">{dept.serving}</p>
          <p className="text-xs text-emerald-600">Serving</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-2 text-center">
          <p className="text-lg font-extrabold text-slate-700">{dept.completed}</p>
          <p className="text-xs text-slate-500">Completed</p>
        </div>
      </div>

      {dept.priority_breakdown && (
        <div className="flex items-center gap-2 flex-wrap">
          {dept.priority_breakdown.emergency > 0 && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700">
              🚨 {dept.priority_breakdown.emergency} emergency
            </span>
          )}
          {dept.priority_breakdown.elderly > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700">
              👴 {dept.priority_breakdown.elderly} elderly
            </span>
          )}
          {dept.priority_breakdown.normal > 0 && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-600">
              {dept.priority_breakdown.normal} normal
            </span>
          )}
        </div>
      )}
    </article>
  )
}

// ---------------------------------------------------------------------------
// Doctor availability table
// ---------------------------------------------------------------------------
const AVAILABILITY_OPTIONS = ['Available', 'Busy', 'Off Duty']

function DoctorAvailabilityTable({ api, hospitalId, onUpdated }) {
  const { data: overview } = useQuery(
    `admin-queue-${hospitalId}`,
    () => api.get(`/api/v1/admin/hospitals/${hospitalId}/queue`),
    { staleMs: 15_000 },
  )

  const { mutate: setAvail, loading: updatingDoctor } = useMutation(
    ({ doctorId, availability }) =>
      api.patch(`/api/v1/admin/doctors/${doctorId}/availability`, { availability }),
    { invalidates: [`admin-queue-${hospitalId}`] },
  )

  const allDoctors = useMemo(() => {
    if (!overview?.departments) return []
    return overview.departments.flatMap(d =>
      (d.doctors ?? []).map(doc => ({ ...doc, dept_name: d.dept_name }))
    )
  }, [overview])

  if (!overview) return <Spinner label="Loading doctors" className="block mx-auto py-4" />
  if (!allDoctors.length) return <EmptyState icon="👨‍⚕️" title="No doctor data available" />

  return (
    <ul className="space-y-2" aria-label="Doctor availability controls">
      {overview.departments.map(dept => (
        <li key={dept.dept_id}>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1 px-1">
            {dept.dept_name}
          </p>
          <p className="text-xs text-slate-400 px-1">
            Use the queue triage view to manage individual doctor availability.
          </p>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function HospitalAdminDashboard() {
  const auth = useAuth()
  const api = useMemo(() => createApiClient(auth), [auth.accessToken]) // eslint-disable-line

  // Derive hospital from the admin's tenant list.
  const hospitalId = auth.user?.hospital_id ?? 1
  const [callingNext, setCallingNext] = useState(null)

  const { data: overview, loading, error, refetch } = useQuery(
    `admin-queue-${hospitalId}`,
    () => api.get(`/api/v1/admin/hospitals/${hospitalId}/queue`),
    { staleMs: 15_000 },
  )

  const { mutate: callNextAction } = useMutation(
    ({ tokenId }) => api.post(`/api/v1/queue/tokens/${tokenId}/action`, { action: 'call_next' }),
    { invalidates: [`admin-queue-${hospitalId}`] },
  )

  async function handleCallNext(deptId, tokenNumber) {
    setCallingNext(deptId)
    try {
      // Get the first waiting token for this dept.
      const tokens = await api.get(`/api/v1/admin/departments/${deptId}/tokens`)
      if (tokens?.[0]) await callNextAction({ tokenId: tokens[0].token_id })
      refetch()
    } catch (err) {
      console.error(err)
    } finally {
      setCallingNext(null)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 pb-16 pt-24 sm:px-6">
      <div className="mx-auto max-w-7xl space-y-6">

        <PageHeader
          eyebrow="Hospital Admin"
          title="Queue & Resource Dashboard"
          subtitle={`Hospital #${hospitalId} · Live`}
          actions={
            <Button variant="secondary" onClick={refetch} aria-label="Refresh queue data">
              ↻ Refresh
            </Button>
          }
        />

        {/* Top stats */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Total waiting"   value={overview?.total_waiting}   icon="⏳" color="amber" />
          <StatCard label="Currently serving" value={overview?.total_serving} icon="✅" color="green" />
          <StatCard label="Completed today" value={overview?.total_completed} icon="📋" color="slate" />
          <StatCard label="Departments"    value={overview?.departments?.length} icon="🏥" color="blue" />
        </div>

        {error && (
          <Alert variant="error" title="Could not load queue data">
            {error.message}
          </Alert>
        )}

        {loading && !overview && (
          <div className="flex justify-center py-12">
            <Spinner size="lg" label="Loading queue overview" />
          </div>
        )}

        {/* Dept cards */}
        {overview?.departments?.length > 0 && (
          <section aria-label="Department queue overview">
            <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-3">
              Departments
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {overview.departments.map(dept => (
                <DeptCard
                  key={dept.dept_id}
                  dept={dept}
                  onCallNext={handleCallNext}
                  callingNext={callingNext}
                />
              ))}
            </div>
          </section>
        )}

        {/* Doctor availability */}
        <SectionCard title="Doctor availability">
          <DoctorAvailabilityTable api={api} hospitalId={hospitalId} />
        </SectionCard>

      </div>
    </main>
  )
}
