import { useState } from 'react'

// ── Icons ─────────────────────────────────────────────────────────────────────
const IconPlay = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
)
const IconAlertTriangle = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
)
const IconCheck = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)
const IconBrain = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.98-3 2.5 2.5 0 0 1-1.32-4.24 3 3 0 0 1 .34-5.58 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 9.5 2Z" />
    <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.98-3 2.5 2.5 0 0 0 1.32-4.24 3 3 0 0 0-.34-5.58 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 14.5 2Z" />
  </svg>
)
const IconPhone = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.61 3.41A2 2 0 0 1 3.6 1.22h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.96a16 16 0 0 0 6 6l.92-.92a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21.73 16.92z" />
  </svg>
)
const IconActivity = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
)
const IconDot = ({ color }) => (
  <span className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />
)

// ── Helpers ───────────────────────────────────────────────────────────────────
const MONO = { fontFamily: 'DM Mono, monospace' }
const LABEL_STYLE = { fontSize: 13, letterSpacing: '1.5px', fontWeight: 700, textTransform: 'uppercase', color: '#94a3b8', ...MONO }
const HERO_LABEL_STYLE = { fontSize: 13, letterSpacing: '2.5px', fontWeight: 700, textTransform: 'uppercase', color: '#93c5fd', ...MONO }

export default function Emergency() {
  const [symptoms, setSymptoms] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleAnalyze = (e) => {
    e.preventDefault()
    if (!symptoms.trim()) return
    setLoading(true)

    fetch(`/api/analyze?symptoms=${encodeURIComponent(symptoms)}&dept_id=1`)
    .then(r => r.json())
    .then(data => {
      setAnalysis(data)
      setLoading(false)
    })
    .catch(() => setLoading(false))
  }

  return (
    <section className="pt-[108px] pb-16 min-h-screen" style={{ background: '#f0f5ff', fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}>
      <div className="max-w-[1360px] mx-auto px-10">

        {/* ── Hero Banner ─────────────────────────────────────────────────── */}
        <div className="rounded-2xl overflow-hidden mb-7 flex items-center justify-between gap-8 relative" style={{ background: '#0f1e3d', minHeight: 180, padding: '2.5rem 3rem' }}>
          {/* decorative circles */}
          <div className="absolute pointer-events-none" style={{ top: -60, right: 200, width: 280, height: 280, borderRadius: '50%', border: '50px solid rgba(255,255,255,0.04)' }} />
          <div className="absolute pointer-events-none" style={{ bottom: -80, right: 60, width: 220, height: 220, borderRadius: '50%', border: '36px solid rgba(255,255,255,0.035)' }} />

          {/* Left content */}
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-3" style={HERO_LABEL_STYLE}>
              <IconPlay />
              <span>AI Triage</span>
              <span style={{ color: '#4b6fa8' }}>·</span>
              <span>Emergency Analysis</span>
            </div>
            <h1 className="font-extrabold text-white mb-2" style={{ fontSize: 34, letterSpacing: '-1.2px', lineHeight: 1.15 }}>
              Emergency <span style={{ color: '#93c5fd' }}>Analyzer</span>
            </h1>
            <p style={{ fontSize: 14, color: '#bfdbfe', lineHeight: 1.65, maxWidth: 420 }}>
              AI-powered symptom analysis to determine severity, suggest departments, and activate emergency protocols instantly.
            </p>
          </div>

          {/* Right — emergency hotline card */}
          <div className="relative z-10 flex items-center gap-4">
            <div className="rounded-xl" style={{ background: 'rgba(220,38,38,0.15)', border: '1px solid rgba(220,38,38,0.3)', padding: '0.75rem 1.5rem' }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500" style={{ animation: 'blink 1s infinite' }} />
                <div className="font-bold font-mono" style={{ fontSize: 11, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#fca5a5' }}>Emergency Hotline</div>
              </div>
              <div className="font-extrabold" style={{ fontSize: 20, letterSpacing: '-1px', color: 'white', lineHeight: 1.2 }}>102</div>
            </div>
          </div>
        </div>

        {/* ── Main Content ───────────────────────────────────────────────────── */}
        <div className="grid gap-5 mb-6" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', alignItems: 'stretch' }}>

          {/* ── Left: Input Form ───────────────────────────────────────────── */}
          <div className="rounded-2xl overflow-hidden relative flex flex-col" style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)' }}>
            <div className="absolute pointer-events-none" style={{ top: -30, right: -30, width: 150, height: 150, borderRadius: '50%', border: '26px solid rgba(255,255,255,0.2)' }} />
            <div className="absolute pointer-events-none" style={{ bottom: -40, left: -20, width: 120, height: 120, borderRadius: '50%', border: '20px solid rgba(255,255,255,0.15)' }} />
            <div className="relative z-10 flex flex-col flex-1" style={{ padding: '2rem' }}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#FEE2E2', color: '#dc2626' }}>
                <IconAlertTriangle />
              </div>
              <div>
                <div className="font-extrabold" style={{ fontSize: 18, color: '#0f1e3d', letterSpacing: '-0.5px' }}>Describe Symptoms</div>
                <div style={{ fontSize: 12, color: '#1e3a5f' }}>AI will analyze severity and route appropriately</div>
              </div>
            </div>

            <form onSubmit={handleAnalyze} className="flex flex-col gap-5">
              <div>
                <label className="block font-bold mb-2" style={{ fontSize: 13, color: '#0f1e3d' }}>Patient Symptoms</label>
                <textarea 
                  className="w-full outline-none resize-none"
                  style={{ padding: '11px 14px', borderRadius: 10, background: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.6)', fontSize: 13.5, color: '#0f1e3d', fontWeight: 500, minHeight: 180 }}
                  value={symptoms}
                  onChange={e => setSymptoms(e.target.value)}
                  placeholder="e.g., Severe chest pain, shortness of breath, left arm numbness, dizziness..."
                  required
                />
              </div>

              <button 
                type="submit" 
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 font-extrabold transition-all disabled:opacity-50"
                style={{ padding: '13px 24px', borderRadius: 12, background: loading ? '#94a3b8' : '#FEE2E2', color: loading ? 'white' : '#dc2626', fontSize: 14, border: 'none', cursor: loading ? 'not-allowed' : 'pointer', boxShadow: loading ? 'none' : '0 4px 20px rgba(220,38,38,0.2)' }}
              >
                {loading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <IconBrain />
                    Analyze Symptoms
                  </>
                )}
              </button>
            </form>

            {/* Emergency contacts */}
            <div className="mt-6 pt-6" style={{ borderTop: '1px solid rgba(255,255,255,0.3)' }}>
              <div className="font-bold mb-3" style={{ fontSize: 13, color: '#0f1e3d' }}>Emergency Contacts</div>
              <div className="flex flex-col gap-2">
                {[
                  { label: 'Ambulance', number: '102', icon: <IconActivity /> },
                  { label: 'Emergency Helpline', number: '112', icon: <IconPhone /> },
                ].map((contact, i) => (
                  <div key={i} className="flex items-center justify-between rounded-xl" style={{ padding: '10px 14px', background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)' }}>
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: '#fee2e2', color: '#dc2626' }}>
                        {contact.icon}
                      </div>
                      <span style={{ fontSize: 13, color: '#0f1e3d', fontWeight: 500 }}>{contact.label}</span>
                    </div>
                    <span className="font-bold font-mono" style={{ fontSize: 13, color: '#dc2626' }}>{contact.number}</span>
                  </div>
                ))}
              </div>
            </div>
            </div>
          </div>

          {/* ── Right: Analysis Results ────────────────────────────────────── */}
          <div className="flex flex-col gap-5" style={{ height: '100%', minHeight: 0 }}>
            {analysis ? (
              <>
                {/* Severity Alert */}
                <div className="rounded-2xl" style={{ 
                  background: analysis.is_emergency ? '#fee2e2' : (analysis.emergency === 'Urgent' ? '#fef9c3' : '#dcfce7'), 
                  border: `1px solid ${analysis.is_emergency ? '#fecaca' : (analysis.emergency === 'Urgent' ? '#fde68a' : '#bbf7d0')}`,
                  boxShadow: analysis.is_emergency ? '0 4px 20px rgba(220,38,38,0.2)' : (analysis.emergency === 'Urgent' ? '0 2px 8px rgba(217,119,6,0.15)' : '0 2px 8px rgba(22,163,74,0.15)'),
                  padding: '2rem'
                }}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ 
                      background: analysis.is_emergency ? '#fca5a5' : (analysis.emergency === 'Urgent' ? '#fde68a' : '#86efac'), 
                      color: analysis.is_emergency ? '#7f1d1d' : (analysis.emergency === 'Urgent' ? '#92400e' : '#14532d')
                    }}>
                      {analysis.is_emergency ? <IconAlertTriangle /> : <IconCheck />}
                    </div>
                    <div>
                      <div style={{ ...LABEL_STYLE, fontSize: 11, color: analysis.is_emergency ? '#991b1b' : (analysis.emergency === 'Urgent' ? '#92400e' : '#166534'), marginBottom: 2 }}>
                        {analysis.is_emergency ? 'Critical Emergency' : (analysis.emergency === 'Urgent' ? 'Urgent' : 'Non-Critical')}
                      </div>
                      <div className="font-extrabold" style={{ fontSize: 20, color: analysis.is_emergency ? '#7f1d1d' : (analysis.emergency === 'Urgent' ? '#78350f' : '#14532d'), letterSpacing: '-0.5px' }}>
                        {analysis.emergency}
                      </div>
                    </div>
                  </div>
                  <p style={{ fontSize: 13, color: analysis.is_emergency ? '#991b1b' : (analysis.emergency === 'Urgent' ? '#92400e' : '#166534'), lineHeight: 1.6 }}>
                    {analysis.is_emergency 
                      ? 'Critical symptoms detected. Bypassing normal queue. Proceed immediately to emergency ward.'
                      : analysis.emergency === 'Urgent'
                        ? 'Elevated symptoms detected. Please visit soon and inform the reception about your condition.'
                        : 'No critical keywords detected. Standard OPD queue applies. You can book a token normally.'}
                  </p>
                </div>

                {/* AI Routing */}
                <div className="rounded-2xl overflow-hidden relative flex-1" style={{ background: '#93C5FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)' }}>
                  <div className="absolute pointer-events-none" style={{ top: -20, right: -20, width: 120, height: 120, borderRadius: '50%', border: '22px solid rgba(255,255,255,0.2)' }} />
                  <div className="absolute pointer-events-none" style={{ bottom: -30, left: -15, width: 100, height: 100, borderRadius: '50%', border: '18px solid rgba(255,255,255,0.15)' }} />
                  <div className="relative z-10" style={{ padding: '2rem' }}>
                    <div style={{ ...LABEL_STYLE, marginBottom: 8, color: '#1d4ed8' }}>AI Routing Suggestion</div>
                    <div className="font-extrabold mb-4" style={{ fontSize: 22, color: '#0f1e3d', letterSpacing: '-0.5px' }}>
                      {analysis.recommended_department}
                    </div>
                    
                    <div className="flex flex-col gap-3">
                      <div className="flex items-center justify-between rounded-xl" style={{ padding: '10px 14px', background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)' }}>
                        <span style={{ fontSize: 13, color: '#0f1e3d' }}>Hospital Status</span>
                        <span className="font-bold" style={{ fontSize: 12, padding: '3px 10px', borderRadius: 20, background: 'rgba(255,255,255,0.6)', color: '#1d4ed8' }}>
                          {analysis.hospital_status}
                        </span>
                      </div>
                      <div className="flex items-center justify-between rounded-xl" style={{ padding: '10px 14px', background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)' }}>
                        <span style={{ fontSize: 13, color: '#0f1e3d' }}>Priority Level</span>
                        <span className="inline-flex items-center gap-1.5 font-bold" style={{ 
                          fontSize: 12, 
                          padding: '3px 10px', 
                          borderRadius: 20, 
                          background: analysis.is_emergency ? '#fee2e2' : (analysis.emergency === 'Urgent' ? '#fef9c3' : '#dcfce7'), 
                          color: analysis.is_emergency ? '#dc2626' : (analysis.emergency === 'Urgent' ? '#d97706' : '#16a34a'),
                          border: `1px solid ${analysis.is_emergency ? '#fecaca' : (analysis.emergency === 'Urgent' ? '#fde68a' : '#bbf7d0')}`
                        }}>
                          <IconDot color={analysis.is_emergency ? '#dc2626' : (analysis.emergency === 'Urgent' ? '#d97706' : '#16a34a')} />
                          {analysis.is_emergency ? 'Emergency' : (analysis.emergency === 'Urgent' ? 'Urgent' : 'Normal')}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Hospital Status */}
                <div className="rounded-2xl overflow-hidden relative" style={{ background: '#93C5FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)' }}>
                  <div className="absolute pointer-events-none" style={{ top: -20, right: -20, width: 100, height: 100, borderRadius: '50%', border: '18px solid rgba(255,255,255,0.2)' }} />
                  <div className="relative z-10" style={{ padding: '1.5rem' }}>
                    <div style={{ ...LABEL_STYLE, fontSize: 11, marginBottom: 8, color: '#1d4ed8' }}>Current Hospital Status</div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="inline-block w-2 h-2 rounded-full bg-green-500" style={{ animation: 'blink 1.6s infinite' }} />
                      <span className="font-bold" style={{ fontSize: 13, color: '#16a34a' }}>All departments operational</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { label: 'ER Beds', value: '12 available' },
                        { label: 'Avg Response', value: '< 5 min' },
                      ].map((stat, i) => (
                        <div key={i} className="rounded-lg" style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.5)' }}>
                          <div style={{ fontSize: 10, color: '#1d4ed8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', ...MONO }}>{stat.label}</div>
                          <div className="font-bold" style={{ fontSize: 13, color: '#0f1e3d', marginTop: 2 }}>{stat.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="rounded-2xl flex flex-col items-center justify-center text-center flex-1" style={{ background: '#93C5FD', border: '2px dashed rgba(255,255,255,0.4)', padding: '4rem 2rem', boxShadow: '0 4px 24px rgba(147,197,253,0.5)', position: 'relative', overflow: 'hidden' }}>
                <div className="absolute pointer-events-none" style={{ top: -30, right: -30, width: 150, height: 150, borderRadius: '50%', border: '26px solid rgba(255,255,255,0.2)' }} />
                <div className="absolute pointer-events-none" style={{ bottom: -40, left: -20, width: 120, height: 120, borderRadius: '50%', border: '20px solid rgba(255,255,255,0.15)' }} />
                <div className="relative z-10 flex flex-col items-center">
                  <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4" style={{ background: 'rgba(255,255,255,0.4)', color: '#1d4ed8' }}>
                    <IconBrain />
                  </div>
                  <div className="font-bold mb-2" style={{ fontSize: 15, color: '#0f1e3d' }}>Awaiting Analysis</div>
                  <p style={{ fontSize: 13, color: '#1e3a5f', maxWidth: 280 }}>
                    Enter symptoms and click "Analyze Symptoms" to get AI-powered triage results.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── How it works ───────────────────────────────────────────────────── */}
        <div style={{ ...LABEL_STYLE, marginBottom: '1rem' }}>
          How AI Triage Works
        </div>
        <div className="grid grid-cols-3 gap-5">
          {[
            {
              n: '1',
              title: 'Describe symptoms',
              desc: 'Enter patient symptoms in natural language. Our AI understands medical terminology and common descriptions.',
            },
            {
              n: '2',
              title: 'AI analyzes severity',
              desc: 'Advanced algorithms scan for critical keywords and patterns to determine if emergency protocols should be activated.',
            },
            {
              n: '3',
              title: 'Get instant routing',
              desc: 'Receive department recommendations, priority level, and direct emergency token generation if needed.',
            },
          ].map(card => (
            <div key={card.n} className="bg-white rounded-2xl" style={{ border: '1px solid #bfdbfe', boxShadow: '0 1px 3px rgba(37,99,235,0.08),0 4px 16px rgba(37,99,235,0.07)', padding: '1.5rem 1.75rem' }}>
              <div className="flex items-center justify-center font-extrabold font-mono mb-4 rounded-xl" style={{ width: 36, height: 36, background: '#dc2626', color: 'white', fontSize: 16 }}>{card.n}</div>
              <div className="font-bold mb-1.5" style={{ fontSize: 15, color: '#0f172a' }}>{card.title}</div>
              <div style={{ fontSize: 13, color: '#475569', lineHeight: 1.6 }}>{card.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0.35}}`}</style>
    </section>
  )
}
