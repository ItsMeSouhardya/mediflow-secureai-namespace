import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authState'

// ── Icons ─────────────────────────────────────────────────────────────────────
const IconArrowLeft = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <line x1="19" y1="12" x2="5" y2="12" />
    <polyline points="12 19 5 12 12 5" />
  </svg>
)
const IconBrain = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.98-3 2.5 2.5 0 0 1-1.32-4.24 3 3 0 0 1 .34-5.58 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 9.5 2Z" />
    <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.98-3 2.5 2.5 0 0 0 1.32-4.24 3 3 0 0 0-.34-5.58 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 14.5 2Z" />
  </svg>
)
const IconClock = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
)
const IconUser = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
)
const IconAlertTriangle = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
)
const IconStethoscope = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6 6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3" />
    <path d="M8 15v1a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6v-4" />
    <circle cx="20" cy="10" r="2" />
  </svg>
)
const IconStar = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
)
const IconPlay = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-2.5 h-2.5">
    <polygon points="5 3 19 12 5 21 5 3" />
  </svg>
)
const IconDot = ({ style }) => (
  <span className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0" style={style} />
)
const IconHospital = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
  </svg>
)

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, accent }) {
  return (
    <div className="rounded-2xl flex flex-col gap-2" style={{ background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)', padding: '1.25rem 1.5rem' }}>
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.5)', color: accent }}>
          {icon}
        </div>
        <span className="font-bold font-mono" style={{ fontSize: 13, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#1d4ed8' }}>{label}</span>
      </div>
      <div className="font-bold" style={{ fontSize: 14, color: '#0f1e3d', lineHeight: 1.4 }}>{value}</div>
    </div>
  )
}

export default function AISmartReport() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user, request } = useAuth()

  const tokenId = searchParams.get('token_id') || ''
  const token = tokenId
  const bookingInfo = (() => {
    try {
      const value = JSON.parse(localStorage.getItem('mediflow_last_booking') || '{}')
      return String(value.tokenId) === tokenId ? value : {}
    } catch { return {} }
  })()

  const [report, setReport]   = useState(null)
  const [loading, setLoading] = useState(Boolean(token))
  const [error, setError]     = useState(token ? '' : 'No token provided.')
  const displayToken = report?.token_number || bookingInfo.tokenCode || ''
  const age = report?.age ?? user?.age ?? 30
  const patientName = report?.patient_name || user?.name || ''

  useEffect(() => {
    if (!token) return
    request(`/api/v1/patients/me/tokens/${encodeURIComponent(tokenId)}/ai-report`)
      .then(data => {
        setReport(data)
        setLoading(false)
      })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [token, tokenId, request])

  // crowd label cleanup (strip emoji)
  const cleanCrowd = (str = '') => str.replace(/[\u{1F000}-\u{1FFFF}]|[\u2600-\u27FF]|\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDE4F]/gu, '').trim()

  const crowdLevel = (str = '') => {
    const s = str.toLowerCase()
    if (s.includes('high') || s.includes('crowded')) return 'high'
    if (s.includes('moderate')) return 'medium'
    return 'low'
  }
  const crowdColors = { high: '#dc2626', medium: '#d97706', low: '#16a34a' }
  const crowdBg     = { high: '#fee2e2', medium: '#fef3c7', low: '#dcfce7' }

  return (
    <section className="pt-[108px] pb-16 min-h-screen" style={{ background: '#f0f5ff', fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}>
      <div className="max-w-[1360px] mx-auto px-10">

        {/* ── Hero Banner ───────────────────────────────────────────────────── */}
        <div
          className="rounded-2xl overflow-hidden mb-7 flex items-center justify-between gap-8 relative"
          style={{ background: '#0f1e3d', minHeight: 180, padding: '2.5rem 3rem' }}
        >
          <div className="absolute pointer-events-none" style={{ top: -60, right: 200, width: 280, height: 280, borderRadius: '50%', border: '50px solid rgba(255,255,255,0.04)' }} />
          <div className="absolute pointer-events-none" style={{ bottom: -80, right: 60, width: 220, height: 220, borderRadius: '50%', border: '36px solid rgba(255,255,255,0.035)' }} />

          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-3" style={{ fontSize: 13, letterSpacing: '2.5px', fontWeight: 700, textTransform: 'uppercase', color: '#93c5fd', fontFamily: 'DM Mono, monospace' }}>
              <IconPlay />
              <span>AI Analysis</span>
              <span style={{ color: '#4b6fa8' }}>·</span>
              <span>Smart Report</span>
            </div>
            <h1 className="font-extrabold text-white mb-2" style={{ fontSize: 34, letterSpacing: '-1.2px', lineHeight: 1.15 }}>
              AI <span style={{ color: '#93c5fd' }}>Smart Report</span>
            </h1>
            <p style={{ fontSize: 14, color: '#bfdbfe', lineHeight: 1.65, maxWidth: 420 }}>
              Personalized AI predictions for your token — wait time, doctor assignment, journey estimate, and hospital alternatives.
            </p>
          </div>

          <div className="relative z-10 flex items-center gap-4">
            {displayToken && (
              <div className="rounded-2xl text-center" style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', padding: '1rem 2rem' }}>
                <div className="font-bold font-mono mb-1" style={{ fontSize: 13, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)' }}>Token</div>
                <div className="font-extrabold font-mono" style={{ fontSize: 32, letterSpacing: '-2px', color: 'white' }}>{displayToken}</div>
              </div>
            )}
            <button
              onClick={() => navigate('/queue')}
              className="flex items-center gap-2 font-bold"
              style={{ padding: '11px 20px', borderRadius: 12, background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: 'white', fontSize: 13, cursor: 'pointer' }}
            >
              <IconArrowLeft />
              Back to Queue
            </button>
          </div>
        </div>

        {/* ── Loading ───────────────────────────────────────────────────────── */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            <p className="font-bold font-mono" style={{ fontSize: 13, color: '#94a3b8', letterSpacing: '1px' }}>Generating AI report...</p>
          </div>
        )}

        {/* ── Error ─────────────────────────────────────────────────────────── */}
        {error && !loading && (
          <div className="bg-white rounded-2xl flex flex-col items-center gap-3 py-16" style={{ border: '1px solid #bfdbfe' }}>
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-red-500" style={{ background: '#fee2e2' }}>
              <IconAlertTriangle />
            </div>
            <p className="font-bold" style={{ fontSize: 15, color: '#0f172a' }}>Could not generate report</p>
            <p style={{ fontSize: 13, color: '#475569' }}>{error}</p>
            <button onClick={() => navigate('/queue')} className="flex items-center gap-2 font-bold mt-2" style={{ padding: '10px 20px', borderRadius: 12, background: '#2563eb', color: 'white', fontSize: 13, border: 'none', cursor: 'pointer' }}>
              <IconArrowLeft /> Back to Queue
            </button>
          </div>
        )}

        {/* ── Report ────────────────────────────────────────────────────────── */}
        {report && !loading && (
          <>
            <div className="grid gap-5 mb-6" style={{ gridTemplateColumns: '340px 1fr' }}>

              {/* ── Left: Token summary card ─────────────────────────────── */}
              <div className="rounded-2xl overflow-hidden relative flex flex-col gap-5" style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)', padding: '2rem' }}>
                <div className="absolute pointer-events-none" style={{ top: -30, right: -30, width: 150, height: 150, borderRadius: '50%', border: '26px solid rgba(255,255,255,0.2)' }} />
                <div className="absolute pointer-events-none" style={{ bottom: -40, left: -20, width: 120, height: 120, borderRadius: '50%', border: '20px solid rgba(255,255,255,0.15)' }} />
                <div className="relative z-10 flex flex-col gap-5">

                <div>
                  <div className="font-bold font-mono mb-1" style={{ fontSize: 13, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#1d4ed8' }}>Token Number</div>
                  <div className="font-extrabold font-mono" style={{ fontSize: 42, letterSpacing: '-2.5px', color: '#0f1e3d', lineHeight: 1 }}>{displayToken || '—'}</div>
                </div>

                <div style={{ borderTop: '1px solid rgba(255,255,255,0.4)', paddingTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
                  <div className="flex justify-between items-center">
                    <span style={{ fontSize: 13, color: '#1e3a5f' }}>Position</span>
                    <span className="font-bold font-mono" style={{ fontSize: 13, color: '#0f1e3d' }}>
                      #{report.position != null && report.position >= 0 ? report.position : (report.queue_length ?? '—')} ahead
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span style={{ fontSize: 13, color: '#1e3a5f' }}>Wait Time</span>
                    <span className="font-bold font-mono" style={{ fontSize: 13, color: '#1d4ed8' }}>{report.wait_time} mins</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span style={{ fontSize: 13, color: '#1e3a5f' }}>Department</span>
                    <span className="font-bold" style={{ fontSize: 12, padding: '3px 10px', borderRadius: 20, background: 'rgba(255,255,255,0.5)', color: '#1d4ed8' }}>{report.booked_department || report.department}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span style={{ fontSize: 13, color: '#1e3a5f' }}>Priority</span>
                    <span className="font-bold font-mono" style={{
                      fontSize: 11, padding: '3px 10px', borderRadius: 20,
                      background: report.is_emergency ? '#fee2e2' : (report.emergency === 'Urgent' ? '#fef9c3' : '#dcfce7'),
                      color:      report.is_emergency ? '#dc2626' : (report.emergency === 'Urgent' ? '#d97706' : '#16a34a'),
                    }}>
                      {report.emergency || (report.is_emergency ? 'Emergency' : 'Normal')}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span style={{ fontSize: 13, color: '#1e3a5f' }}>Crowd Level</span>
                    <span className="font-bold font-mono" style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: crowdBg[crowdLevel(report.crowd)], color: crowdColors[crowdLevel(report.crowd)] }}>
                      {cleanCrowd(report.crowd)}
                    </span>
                  </div>
                  {report.priority_score != null && (
                    <div className="flex justify-between items-center">
                      <span style={{ fontSize: 13, color: '#1e3a5f' }}>Priority Score</span>
                      <span className="font-bold font-mono" style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: report.priority_score >= 50 ? '#fee2e2' : report.priority_score >= 25 ? '#fef3c7' : '#dcfce7', color: report.priority_score >= 50 ? '#dc2626' : report.priority_score >= 25 ? '#d97706' : '#16a34a' }}>
                        {report.priority_score} pts
                      </span>
                    </div>
                  )}
                </div>

                {/* ETA mini block — uses total_time (full journey) not just wait_time */}
                <div className="rounded-2xl" style={{ background: '#0f1e3d', padding: '1rem 1.25rem' }}>
                  <div className="font-bold font-mono mb-1" style={{ fontSize: 13, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#93c5fd' }}>Estimated Departure</div>
                  <div className="font-extrabold font-mono" style={{ fontSize: 22, letterSpacing: '-1px', color: 'white' }}>
                    {(() => { const d = new Date(); d.setMinutes(d.getMinutes() + (report.total_time || report.wait_time || 0)); return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) })()}
                  </div>
                  <div style={{ fontSize: 11, color: '#bfdbfe', marginTop: 2 }}>AI predicted · {report.total_time} min total journey</div>
                  {report.explanation && (
                    <div style={{ fontSize: 10, color: 'rgba(191,219,254,0.7)', marginTop: 4, fontFamily: 'DM Mono, monospace' }}>{report.explanation}</div>
                  )}
                </div>

                {/* Elderly mode */}
                {report.elderly_mode?.enabled && (
                  <div className="rounded-2xl flex items-start gap-3" style={{ background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)', padding: '1rem 1.25rem' }}>
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(255,255,255,0.5)', color: '#1d4ed8' }}>
                      <IconStar />
                    </div>
                    <div>
                      <div className="font-bold" style={{ fontSize: 12, color: '#0f1e3d' }}>Elderly Priority Active</div>
                      <div style={{ fontSize: 11, color: '#1e3a5f', marginTop: 2 }}>{report.elderly_mode.benefits?.join(' · ')}</div>
                    </div>
                  </div>
                )}
                </div>
              </div>

              {/* ── Right: AI Report card ─────────────────────────────────── */}
              <div className="rounded-2xl overflow-hidden relative flex flex-col gap-6" style={{ background: '#93C5FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)', padding: '2rem' }}>
                <div className="absolute pointer-events-none" style={{ top: -30, right: -30, width: 160, height: 160, borderRadius: '50%', border: '28px solid rgba(255,255,255,0.2)' }} />
                <div className="absolute pointer-events-none" style={{ bottom: -40, left: -20, width: 130, height: 130, borderRadius: '50%', border: '22px solid rgba(255,255,255,0.15)' }} />
                <div className="relative z-10 flex flex-col gap-6">

                {/* Header */}
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#1d4ed8', color: 'white' }}>
                    <IconBrain />
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5" style={{ fontSize: 11, letterSpacing: '2px', fontWeight: 700, color: '#1d4ed8', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace' }}>
                      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: '#1d4ed8' }} />
                      AI Analysis
                    </div>
                    <div className="font-extrabold" style={{ fontSize: 18, color: '#0f1e3d', letterSpacing: '-0.5px' }}>AI Smart Report</div>
                    <div style={{ fontSize: 12, color: '#1e3a5f' }}>Powered by MediFlow AI prediction engine</div>
                  </div>
                </div>

                {/* Patient name + age — only shown when name is known (own booking) */}
                {patientName && (
                  <div className="w-full flex items-center gap-3 rounded-2xl" style={{
                    padding: '1rem 1.5rem',
                    background: 'rgba(255,255,255,0.45)',
                    border: '1px solid rgba(255,255,255,0.6)',
                  }}>
                    <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: '#1d4ed8', color: 'white' }}>
                      <IconUser />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div style={{ fontSize: 13, fontWeight: 500, color: '#0f1e3d' }}>
                        {patientName}
                      </div>
                      <div className="font-mono" style={{ fontSize: 11, fontWeight: 500, opacity: 0.75, color: '#1e3a5f' }}>
                        Age: {age}
                        {Number(age) >= 60 && (
                          <span className="ml-2 font-bold" style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20, background: '#fde68a', color: '#d97706' }}>Elderly Priority</span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* 4-grid stat cards */}
                <div className="grid grid-cols-2 gap-3">
                  <StatCard icon={<IconClock />}       label="AI Advice"           value={report.advice}    accent="#2563eb" />
                  <StatCard icon={<IconStethoscope />} label="Recommended Doctor"  value={report.doctor}    accent="#7c3aed" />
                  <StatCard icon={<IconAlertTriangle />} label="Peak Hour Status"  value={`${report.peak_hour} (${cleanCrowd(report.crowd)})`} accent="#d97706" />
                  <StatCard icon={<IconStar />}        label="Best Time to Visit"  value={report.best_time} accent="#16a34a" />
                </div>

                {/* Journey */}
                <div>
                  <div className="font-bold mb-3" style={{ fontSize: 13, color: '#0f1e3d' }}>Your Estimated Journey</div>
                  <div className="flex flex-col gap-2">
                    {(report.journey || []).map((step, i) => (
                      <div key={i} className="flex items-center gap-3 rounded-xl" style={{ padding: '10px 14px', background: i === (report.journey.length - 1) ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.3)', border: `1px solid rgba(255,255,255,${i === (report.journey.length - 1) ? '0.7' : '0.4'})` }}>
                        <IconDot style={{ background: i === (report.journey.length - 1) ? '#1d4ed8' : 'rgba(29,78,216,0.4)' }} />
                        <span style={{ fontSize: 13, color: i === (report.journey.length - 1) ? '#0f1e3d' : '#1e3a5f', fontWeight: i === (report.journey.length - 1) ? 700 : 500 }}>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Hospital alternative */}
                {report.hospital_alternative && (
                  <div className="rounded-2xl" style={{ background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)', padding: '1.25rem 1.5rem' }}>
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.5)', color: '#16a34a' }}>
                        <IconHospital />
                      </div>
                      <span className="font-bold font-mono" style={{ fontSize: 13, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#1d4ed8' }}>Hospital Alternative</span>
                    </div>
                    <p style={{ fontSize: 13, color: '#0f1e3d', lineHeight: 1.6 }}>
                      If you are in a hurry,{' '}
                      <strong>{report.hospital_alternative.recommended}</strong>{' '}
                      has a shorter wait time of ~{report.hospital_alternative.options?.find(o => o.name === report.hospital_alternative.recommended)?.wait_time ?? '—'} mins.
                    </p>
                    <div className="flex gap-2 mt-3 flex-wrap">
                      {(report.hospital_alternative.options || []).map((opt, i) => (
                        <div key={i} className="flex items-center gap-2 rounded-xl" style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)' }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: opt.name === report.hospital_alternative.recommended ? '#16a34a' : '#1e3a5f' }}>{opt.name}</span>
                          <span className="font-mono" style={{ fontSize: 11, color: '#1d4ed8' }}>{opt.wait_time} min</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                </div>
              </div>
            </div>

            {/* ── Emergency / Urgent banner ─────────────────────────────── */}
            {(report.is_emergency || report.emergency === 'Urgent') && (
              <div className="rounded-2xl flex items-center gap-4 mb-6" style={{
                background: '#0f1e3d',
                border: `1px solid ${report.is_emergency ? 'rgba(220,38,38,0.3)' : 'rgba(217,119,6,0.3)'}`,
                padding: '1.25rem 1.75rem'
              }}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{
                  background: report.is_emergency ? 'rgba(220,38,38,0.2)' : 'rgba(217,119,6,0.2)',
                  color: report.is_emergency ? '#fca5a5' : '#fcd34d'
                }}>
                  <IconAlertTriangle />
                </div>
                <div>
                  <div className="font-bold" style={{ fontSize: 14, color: 'white' }}>
                    {report.is_emergency ? 'Emergency Priority Active' : 'Urgent — Elevated Symptoms Detected'}
                  </div>
                  <div style={{ fontSize: 12, color: '#bfdbfe' }}>
                    {report.is_emergency
                      ? `${report.emergency} — You have been flagged for priority handling. Please proceed to the emergency counter.`
                      : 'Please visit soon and inform the reception about your condition for faster attention.'}
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-2 rounded-lg" style={{
                  background: report.is_emergency ? 'rgba(220,38,38,0.15)' : 'rgba(217,119,6,0.15)',
                  border: `1px solid ${report.is_emergency ? 'rgba(220,38,38,0.3)' : 'rgba(217,119,6,0.3)'}`,
                  padding: '8px 14px'
                }}>
                  <span className="inline-block w-2 h-2 rounded-full" style={{
                    background: report.is_emergency ? '#ef4444' : '#f59e0b',
                    animation: 'blink 1s infinite'
                  }} />
                  <span className="font-bold font-mono" style={{ fontSize: 12, color: report.is_emergency ? '#fca5a5' : '#fcd34d' }}>
                    {report.is_emergency ? 'Emergency' : 'Urgent'}
                  </span>
                </div>
              </div>
            )}

            {/* ── Bottom action ─────────────────────────────────────────────── */}
            <div className="flex justify-center">
              <button
                onClick={() => navigate('/queue')}
                className="flex items-center gap-2 font-bold"
                style={{ padding: '13px 28px', borderRadius: 12, background: '#2563eb', color: 'white', fontSize: 14, border: 'none', cursor: 'pointer', boxShadow: '0 4px 16px rgba(37,99,235,0.35)' }}
              >
                <IconArrowLeft />
                Back to Queue Tracker
              </button>
            </div>
          </>
        )}
      </div>

      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0.35}}`}</style>
    </section>
  )
}
