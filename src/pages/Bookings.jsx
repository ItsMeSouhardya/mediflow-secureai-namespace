import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authState'

// ── Icons ─────────────────────────────────────────────────────────────────────
const IconPlay = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
  </svg>
)
const IconCalendar = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
)
const IconMapPin = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
    <circle cx="12" cy="10" r="3" />
  </svg>
)
const IconBrain = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.98-3 2.5 2.5 0 0 1-1.32-4.24 3 3 0 0 1 .34-5.58 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 9.5 2Z" />
    <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.98-3 2.5 2.5 0 0 0 1.32-4.24 3 3 0 0 0-.34-5.58 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 14.5 2Z" />
  </svg>
)
const IconStar = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
)
const IconDot = ({ color }) => (
  <span className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />
)

// ── Helpers ───────────────────────────────────────────────────────────────────
const MONO = { fontFamily: 'DM Mono, monospace' }
const LABEL_STYLE = { fontSize: 13, letterSpacing: '1.5px', fontWeight: 700, textTransform: 'uppercase', color: '#94a3b8', ...MONO }
const HERO_LABEL_STYLE = { fontSize: 13, letterSpacing: '2.5px', fontWeight: 700, textTransform: 'uppercase', color: '#93c5fd', ...MONO }

export default function Bookings() {
  const navigate = useNavigate()
  const { user, request } = useAuth()
  const [hospitals, setHospitals] = useState([])
  const [departments, setDepartments] = useState([])
  const [selectedHospital, setSelectedHospital] = useState('')
  const [selectedDept, setSelectedDept] = useState('')
  const [doctorSuggestion, setDoctorSuggestion] = useState(null)
  const [formData, setFormData] = useState({ name: user?.name || '', age: user?.age ?? '', symptoms: '' })
  const [loading, setLoading] = useState(false)
  const [hospitalsLoading, setHospitalsLoading] = useState(true)
  // popup state: { type: 'success'|'error', title, message, token }
  const [popup, setPopup] = useState(null)

  useEffect(() => {
    fetch('/api/hospitals')
      .then(r => r.json())
      .then(data => {
        setHospitals(data)
        setHospitalsLoading(false)
      })
      .catch(() => setHospitalsLoading(false))
  }, [])

  useEffect(() => {
    if (selectedHospital) {
      fetch(`/api/departments?hospital_id=${selectedHospital}`)
        .then(r => r.json())
        .then(data => {
          setDepartments(data)
          setSelectedDept('')
          setDoctorSuggestion(null)
        })
    }
  }, [selectedHospital])

  useEffect(() => {
    if (selectedDept) {
      fetch(`/api/doctor?dept_id=${selectedDept}`)
        .then(r => r.json())
        .then(setDoctorSuggestion)
    }
  }, [selectedDept])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!selectedDept || !formData.name || !formData.age) return
    setLoading(true)

    try {
      const data = await request('/api/v1/tokens/book', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({
        dept_id: selectedDept,
        patient_name: formData.name,
        age: Number(formData.age),
        symptoms: formData.symptoms
      })
      })
      setLoading(false)
      // Store only an opaque public credential and non-clinical identifiers.
      localStorage.setItem('mediflow_last_booking', JSON.stringify({
        trackingCode: data.tracking_code,
        tokenId: data.token_id,
        tokenCode: data.token_code,
        hospitalId: data.hospital_id || selectedHospital,
        hospitalName: data.hospital_name || '',
        deptId: selectedDept,
      }))
      setPopup({ type: 'success', title: 'Token Booked!', message: 'Your token has been confirmed.', token: data.token_code })
    } catch (err) {
      setLoading(false)
      setPopup({ type: 'error', title: 'Booking Failed', message: err.message })
    }
  }

  return (
    <section className="pt-[108px] pb-16 min-h-screen" style={{ background: '#f0f5ff', fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}>
      <div className="max-w-[1360px] mx-auto px-10">

        {/* ── Custom Popup ────────────────────────────────────────────────── */}
        {popup && (
          <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(15,30,61,0.55)', backdropFilter: 'blur(4px)' }}>
            <div className="bg-white rounded-2xl overflow-hidden" style={{ width: 420, boxShadow: '0 24px 64px rgba(15,30,61,0.25)', border: '1px solid #bfdbfe' }}>
              {/* top accent bar */}
              <div style={{ height: 4, background: popup.type === 'success' ? 'linear-gradient(90deg,#2563eb,#3b82f6)' : 'linear-gradient(90deg,#dc2626,#ef4444)' }} />
              <div style={{ padding: '2rem' }}>
                {/* icon + title */}
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: popup.type === 'success' ? '#dbeafe' : '#fee2e2' }}>
                    {popup.type === 'success' ? (
                      <svg viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="20" height="20"><polyline points="20 6 9 17 4 12" /></svg>
                    ) : (
                      <svg viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="20" height="20"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    )}
                  </div>
                  <div>
                    <div className="font-extrabold" style={{ fontSize: 18, color: '#0f172a', letterSpacing: '-0.5px' }}>{popup.title}</div>
                    <div style={{ fontSize: 12, color: '#475569', marginTop: 1 }}>{popup.message}</div>
                  </div>
                </div>

                {/* token display (success only) */}
                {popup.type === 'success' && popup.token && (
                  <div className="rounded-2xl text-center mb-5" style={{ background: '#0f1e3d', padding: '1.25rem' }}>
                    <div className="font-bold font-mono mb-1" style={{ fontSize: 11, letterSpacing: '2px', textTransform: 'uppercase', color: '#93c5fd' }}>Your Token Number</div>
                    <div className="font-extrabold font-mono" style={{ fontSize: 42, letterSpacing: '-2px', color: 'white', lineHeight: 1 }}>{popup.token}</div>
                    <div style={{ fontSize: 11, color: '#bfdbfe', marginTop: 6 }}>Save this number to track your queue position</div>
                  </div>
                )}

                {/* actions */}
                <div className="flex gap-3">
                  {popup.type === 'success' ? (
                    <>
                      <button
                        onClick={() => { setPopup(null); navigate('/queue') }}
                        className="flex-1 font-extrabold"
                        style={{ padding: '11px', borderRadius: 10, background: '#2563eb', color: 'white', fontSize: 13.5, border: 'none', cursor: 'pointer', boxShadow: '0 4px 16px rgba(37,99,235,0.3)' }}
                      >
                        Track Queue →
                      </button>
                      <button
                        onClick={() => setPopup(null)}
                        className="font-bold"
                        style={{ padding: '11px 20px', borderRadius: 10, background: '#f8faff', color: '#475569', fontSize: 13.5, border: '1px solid #bfdbfe', cursor: 'pointer' }}
                      >
                        Stay Here
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setPopup(null)}
                      className="flex-1 font-extrabold"
                      style={{ padding: '11px', borderRadius: 10, background: '#dc2626', color: 'white', fontSize: 13.5, border: 'none', cursor: 'pointer' }}
                    >
                      Try Again
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Hero Banner ─────────────────────────────────────────────────── */}
        <div className="rounded-2xl overflow-hidden mb-7 flex items-center justify-between gap-8 relative" style={{ background: '#0f1e3d', minHeight: 180, padding: '2.5rem 3rem' }}>
          {/* decorative circles — identical to Dashboard/AI Smart Report */}
          <div className="absolute pointer-events-none" style={{ top: -60, right: 200, width: 280, height: 280, borderRadius: '50%', border: '50px solid rgba(255,255,255,0.04)' }} />
          <div className="absolute pointer-events-none" style={{ bottom: -80, right: 60, width: 220, height: 220, borderRadius: '50%', border: '36px solid rgba(255,255,255,0.035)' }} />

          {/* Left content */}
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-3" style={HERO_LABEL_STYLE}>
              <IconPlay />
              <span>Smart Booking</span>
              <span style={{ color: '#4b6fa8' }}>·</span>
              <span>Skip the Queue</span>
            </div>
            <h1 className="font-extrabold text-white mb-2" style={{ fontSize: 34, letterSpacing: '-1.2px', lineHeight: 1.15 }}>
              Book a <span style={{ color: '#93c5fd' }}>Token</span>
            </h1>
            <p style={{ fontSize: 14, color: '#bfdbfe', lineHeight: 1.65, maxWidth: 420 }}>
              Reserve your spot digitally and arrive right on time — AI assigns priority based on symptoms and age.
            </p>
          </div>

          {/* Right — action card */}
          <div className="relative z-10 flex items-center gap-4">
            <div className="rounded-2xl text-center" style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', padding: '1rem 2rem', minWidth: 160 }}>
              <div className="font-bold font-mono mb-1" style={{ fontSize: 13, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)' }}>Available Now</div>
              <div className="font-extrabold" style={{ fontSize: 18, letterSpacing: '-0.5px', color: 'white', lineHeight: 1.2 }}>{hospitals.length} Hospitals</div>
            </div>
          </div>
        </div>

        {/* ── Main Content: Form + Hospital List ─────────────────────────────── */}
        <div className="grid gap-5 mb-6" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>

          {/* ── Left: Booking Form ─────────────────────────────────────────── */}
          <div className="rounded-2xl overflow-hidden relative" style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)' }}>
            <div className="absolute pointer-events-none" style={{ top: -30, right: -30, width: 150, height: 150, borderRadius: '50%', border: '26px solid rgba(255,255,255,0.2)' }} />
            <div className="absolute pointer-events-none" style={{ bottom: -40, left: -20, width: 120, height: 120, borderRadius: '50%', border: '20px solid rgba(255,255,255,0.15)' }} />
            <div className="relative z-10" style={{ padding: '2rem' }}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#1d4ed8', color: 'white' }}>
                <IconCalendar />
              </div>
              <div>
                <div className="font-extrabold" style={{ fontSize: 18, color: '#0f1e3d', letterSpacing: '-0.5px' }}>Booking Form</div>
                <div style={{ fontSize: 12, color: '#1e3a5f' }}>Fill in your details to generate a token</div>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              
              {/* Hospital + Department */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-bold mb-2" style={{ fontSize: 13, color: '#0f172a' }}>Select Hospital</label>
                  <select 
                    className="w-full outline-none"
                    style={{ padding: '11px 14px', borderRadius: 10, background: '#f8faff', border: '1px solid #bfdbfe', fontSize: 13.5, color: '#0f172a', fontWeight: 500 }}
                    value={selectedHospital}
                    onChange={e => setSelectedHospital(e.target.value)}
                    required
                  >
                    <option value="">-- Choose Hospital --</option>
                    {hospitals.map(h => <option key={h.hospital_id} value={h.hospital_id}>{h.name}</option>)}
                  </select>
                </div>
                
                <div>
                  <label className="block font-bold mb-2" style={{ fontSize: 13, color: '#0f172a' }}>Select Department</label>
                  <select 
                    className="w-full outline-none disabled:opacity-50"
                    style={{ padding: '11px 14px', borderRadius: 10, background: '#f8faff', border: '1px solid #bfdbfe', fontSize: 13.5, color: '#0f172a', fontWeight: 500 }}
                    value={selectedDept}
                    onChange={e => setSelectedDept(e.target.value)}
                    disabled={!selectedHospital}
                    required
                  >
                    <option value="">-- Choose Department --</option>
                    {departments.map(d => <option key={d.dept_id} value={d.dept_id}>{d.name}</option>)}
                  </select>
                </div>
              </div>

              {/* AI Doctor Suggestion */}
              {doctorSuggestion && (
                <div className="rounded-2xl flex items-start gap-3" style={{ background: '#eff6ff', border: '1px solid #bfdbfe', padding: '1rem 1.25rem' }}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: '#dbeafe', color: '#2563eb' }}>
                    <IconBrain />
                  </div>
                  <div>
                    <div className="font-bold" style={{ fontSize: 12, color: '#1652cc' }}>AI Smart Assignment</div>
                    <div style={{ fontSize: 11, color: '#3b82f6', marginTop: 2 }}>
                      Based on current load, you will be seen by <strong>{doctorSuggestion.suggested_doctor}</strong>
                    </div>
                  </div>
                </div>
              )}

              {/* Name + Age */}
              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2">
                  <label className="block font-bold mb-2" style={{ fontSize: 13, color: '#0f172a' }}>Patient Name</label>
                  <input 
                    type="text" 
                    className="w-full outline-none"
                    style={{ padding: '11px 14px', borderRadius: 10, background: '#f8faff', border: '1px solid #bfdbfe', fontSize: 13.5, color: '#0f172a', fontWeight: 500 }}
                    value={formData.name}
                    onChange={e => setFormData({...formData, name: e.target.value})}
                    required
                    placeholder="Full Name"
                  />
                </div>
                <div>
                  <label className="block font-bold mb-2" style={{ fontSize: 13, color: '#0f172a' }}>Age</label>
                  <input 
                    type="number" 
                    className="w-full outline-none"
                    style={{ padding: '11px 14px', borderRadius: 10, background: '#f8faff', border: '1px solid #bfdbfe', fontSize: 13.5, color: '#0f172a', fontWeight: 500 }}
                    value={formData.age}
                    onChange={e => setFormData({...formData, age: e.target.value})}
                    required
                    placeholder="Years"
                    min="0"
                    max="120"
                  />
                </div>
              </div>

              {/* Elderly mode indicator */}
              {Number(formData.age) >= 60 && (
                <div className="rounded-2xl flex items-center gap-3" style={{ background: '#fef3c7', border: '1px solid #fde68a', padding: '0.875rem 1.25rem' }}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: '#fde68a', color: '#d97706' }}>
                    <IconStar />
                  </div>
                  <span className="font-bold" style={{ fontSize: 12, color: '#d97706' }}>Elderly Mode Auto-Activated — Priority Handling</span>
                </div>
              )}

              {/* Symptoms */}
              <div>
                <label className="block font-bold mb-2" style={{ fontSize: 13, color: '#0f172a' }}>Symptoms (Briefly)</label>
                <textarea 
                  className="w-full outline-none resize-none"
                  style={{ padding: '11px 14px', borderRadius: 10, background: '#f8faff', border: '1px solid #bfdbfe', fontSize: 13.5, color: '#0f172a', fontWeight: 500, minHeight: 100 }}
                  value={formData.symptoms}
                  onChange={e => setFormData({...formData, symptoms: e.target.value})}
                  placeholder="e.g., Fever and mild chest pain..."
                />
              </div>

              {/* Submit button */}
              <button 
                type="submit" 
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 font-extrabold transition-all disabled:opacity-50"
                style={{ padding: '13px 24px', borderRadius: 12, background: loading ? '#94a3b8' : '#2563eb', color: 'white', fontSize: 14, border: 'none', cursor: loading ? 'not-allowed' : 'pointer', boxShadow: loading ? 'none' : '0 4px 20px rgba(37,99,235,0.35)' }}
              >
                {loading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Booking...
                  </>
                ) : (
                  <>
                    <IconCalendar />
                    Generate Token
                  </>
                )}
              </button>
            </form>
            </div>
          </div>

          {/* ── Right: Hospital List ───────────────────────────────────────── */}
          <div className="rounded-2xl overflow-hidden relative" style={{ background: '#93C5FD', boxShadow: '0 4px 24px rgba(147,197,253,0.5)' }}>
            <div className="absolute pointer-events-none" style={{ top: -30, right: -30, width: 150, height: 150, borderRadius: '50%', border: '26px solid rgba(255,255,255,0.2)' }} />
            <div className="absolute pointer-events-none" style={{ bottom: -40, left: -20, width: 120, height: 120, borderRadius: '50%', border: '20px solid rgba(255,255,255,0.15)' }} />
            <div className="relative z-10">
            <div className="flex items-center justify-between" style={{ padding: '1.25rem 1.75rem', borderBottom: '1px solid rgba(255,255,255,0.3)' }}>
              <div>
                <div className="flex items-center gap-1.5 mb-1" style={{ fontSize: 11, letterSpacing: '2px', fontWeight: 700, color: '#1d4ed8', textTransform: 'uppercase', ...MONO }}>
                  <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: '#1d4ed8' }} />
                  Network View
                </div>
                <div className="font-bold" style={{ fontSize: 17, color: '#0f1e3d' }}>Available Hospitals</div>
                <div style={{ fontSize: 12, color: '#1e3a5f', marginTop: 2 }}>Compare wait times across the network</div>
              </div>
              <span className="font-bold" style={{ fontSize: 11, padding: '4px 12px', borderRadius: 20, background: 'rgba(255,255,255,0.4)', color: '#1d4ed8', ...MONO }}>
                {hospitals.length} active
              </span>
            </div>

            {hospitalsLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <div className="w-10 h-10 border-4 border-white/40 border-t-white rounded-full animate-spin" />
                <p style={{ fontSize: 13, color: '#1e3a5f', ...MONO }}>Loading hospitals...</p>
              </div>
            ) : hospitals.length === 0 ? (
              <div className="text-center py-16" style={{ fontSize: 13, color: '#1e3a5f' }}>No hospitals available</div>
            ) : (
              <div style={{ maxHeight: 520, overflowY: 'auto' }}>
                {hospitals.map((h, i) => (
                  <div 
                    key={h.hospital_id} 
                    className="flex items-center justify-between transition-all cursor-pointer"
                    style={{ 
                      padding: '1.25rem 1.75rem', 
                      borderBottom: i < hospitals.length - 1 ? '1px solid rgba(255,255,255,0.25)' : 'none',
                      background: selectedHospital == h.hospital_id ? 'rgba(255,255,255,0.2)' : 'transparent'
                    }}
                    onClick={() => setSelectedHospital(String(h.hospital_id))}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.2)'}
                    onMouseLeave={e => e.currentTarget.style.background = selectedHospital == h.hospital_id ? 'rgba(255,255,255,0.2)' : 'transparent'}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold" style={{ fontSize: 12.5, color: '#0f1e3d' }}>{h.name}</span>
                        {h.recommended && (
                          <span className="inline-flex items-center gap-1 font-bold" style={{ fontSize: 10, padding: '3px 8px', borderRadius: 20, background: 'rgba(255,255,255,0.4)', color: '#16a34a', border: '1px solid rgba(255,255,255,0.5)', ...MONO }}>
                            <IconDot color="#16a34a" />
                            Fastest
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5" style={{ fontSize: 11.5, color: '#1e3a5f' }}>
                        <IconMapPin />
                        {h.address}
                      </div>
                    </div>

                    <div className="flex items-center gap-6">
                      <div className="text-center">
                        <div style={{ ...LABEL_STYLE, fontSize: 10, marginBottom: 2, color: '#1d4ed8' }}>Waiting</div>
                        <div className="font-extrabold" style={{ fontSize: 20, color: '#0f1e3d', letterSpacing: '-1px', ...MONO }}>{h.total_waiting}</div>
                      </div>
                      <div className="text-center">
                        <div style={{ ...LABEL_STYLE, fontSize: 10, marginBottom: 2, color: '#1d4ed8' }}>Est. Wait</div>
                        <div className="font-extrabold" style={{ 
                          fontSize: 20, 
                          letterSpacing: '-1px', 
                          color: h.status_color === 'green' ? '#16a34a' : (h.status_color === 'yellow' ? '#d97706' : '#dc2626'),
                          ...MONO 
                        }}>
                          ~{h.estimated_wait}<span style={{ fontSize: 12, fontWeight: 500 }}>m</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            </div>
          </div>
        </div>

        {/* ── How it works ───────────────────────────────────────────────────── */}
        <div style={{ ...LABEL_STYLE, marginBottom: '1rem' }}>
          How online booking works
        </div>
        <div className="grid grid-cols-3 gap-5">
          {[
            {
              n: '1',
              title: 'Fill the form',
              desc: 'Select your hospital, department, and provide basic details. AI will suggest the best available doctor.',
            },
            {
              n: '2',
              title: 'Get instant token',
              desc: 'Your token is generated immediately with priority assignment based on age and symptoms.',
            },
            {
              n: '3',
              title: 'Track & arrive',
              desc: 'Use the Queue Tracker to monitor your position in real-time and arrive just when your turn is near.',
            },
          ].map(card => (
            <div key={card.n} className="bg-white rounded-2xl" style={{ border: '1px solid #bfdbfe', boxShadow: '0 1px 3px rgba(37,99,235,0.08),0 4px 16px rgba(37,99,235,0.07)', padding: '1.5rem 1.75rem' }}>
              <div className="flex items-center justify-center font-extrabold font-mono mb-4 rounded-xl" style={{ width: 36, height: 36, background: '#2563eb', color: 'white', fontSize: 16 }}>{card.n}</div>
              <div className="font-bold mb-1.5" style={{ fontSize: 15, color: '#0f172a' }}>{card.title}</div>
              <div style={{ fontSize: 13, color: '#475569', lineHeight: 1.6 }}>{card.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
