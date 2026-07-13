import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/authState'

const MONO = { fontFamily: 'DM Mono, monospace' }
const STORAGE_KEY = 'mediflow_patient_demo_completed_v2'

const Icon = ({ children, size = 18 }) => <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
const HospitalIcon = () => <Icon><path d="M3 21h18M5 21V5h14v16M9 9h6M12 6v6M8 15h2M14 15h2" /></Icon>
const AlertIcon = () => <Icon><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></Icon>
const CalendarIcon = () => <Icon><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /></Icon>
const QueueIcon = () => <Icon><path d="M8 6h13M8 12h13M8 18h13" /><circle cx="3" cy="6" r="1" /><circle cx="3" cy="12" r="1" /><circle cx="3" cy="18" r="1" /></Icon>
const BrainIcon = () => <Icon><path d="M9.5 3A3.5 3.5 0 0 1 13 6.5V19a3 3 0 0 1-6 0v-.2A3.5 3.5 0 0 1 4.7 13 3.5 3.5 0 0 1 6 6.3 3.5 3.5 0 0 1 9.5 3Z" /><path d="M14.5 3A3.5 3.5 0 0 0 11 6.5V19a3 3 0 0 0 6 0v-.2a3.5 3.5 0 0 0 2.3-5.8A3.5 3.5 0 0 0 18 6.3 3.5 3.5 0 0 0 14.5 3Z" /></Icon>
const HeartIcon = () => <Icon><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z" /></Icon>
const FileIcon = () => <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></Icon>
const ActivityIcon = () => <Icon><path d="M3 12h4l2-7 4 14 2-7h6" /></Icon>
const ShareIcon = () => <Icon><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4" /></Icon>
const ShieldIcon = () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
const UserIcon = () => <Icon><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Icon>
const ArrowIcon = () => <Icon size={15}><path d="M5 12h14M13 6l6 6-6 6" /></Icon>
const ResetIcon = () => <Icon size={15}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></Icon>

const BASE_STEPS = [
  {
    id: 1, phase: 'Plan the visit', title: 'Compare live hospital conditions',
    description: 'Open the hospital dashboard to compare department waiting counts, estimated waits, crowd levels, and current capacity before choosing where to go.',
    outcome: 'Identify a suitable hospital and department using the current patient-facing operational view.',
    action: 'Open dashboard', to: '/dashboard', icon: <HospitalIcon />,
  },
  {
    id: 2, phase: 'Plan the visit', title: 'Check urgent symptoms when needed',
    description: 'Use Emergency guidance to enter symptoms and review the suggested care direction before continuing with a routine booking.',
    outcome: 'Receive clear urgency guidance and a suggested department without presenting it as a medical diagnosis.',
    action: 'Open emergency guidance', to: '/emergency', icon: <AlertIcon />,
  },
  {
    id: 3, phase: 'Plan the visit', title: 'Book a hospital token',
    description: 'Select a hospital and department, enter patient details and symptoms, then generate a realistic queue token for the visit.',
    outcome: 'A randomized token is confirmed and becomes the shared source for queue tracking, AI timing, and hospital access activity.',
    action: 'Book a token', to: '/bookings', icon: <CalendarIcon />,
  },
  {
    id: 4, phase: 'Follow the visit', title: 'Track the live queue',
    description: 'Open Queue Tracker after booking. The generated token is filled automatically so the patient can review people ahead, wait time, progress, and department conditions.',
    outcome: 'The patient sees a consistent queue position and updated estimated arrival information.',
    action: 'Track the queue', to: '/queue', icon: <QueueIcon />,
  },
  {
    id: 5, phase: 'Follow the visit', title: 'Review the AI Smart Report',
    description: 'From the tracked token, open the personalized report to review the patient name, age, token, estimated journey, visit advice, crowd conditions, and recommended doctor.',
    outcome: 'Visit-now or delay advice is calculated from the complete expected hospital journey.',
    action: 'Open AI Smart Report', to: '/queue', icon: <BrainIcon />, requiresToken: true,
  },
  {
    id: 6, phase: 'Manage health information', title: 'Review My Health',
    description: 'Use the Overview and Health Records tabs to review recent reports, care activity, encounters, prescriptions, allergies, and vaccinations in one patient workspace.',
    outcome: 'Patient health information and attached supporting files remain organized by record category.',
    action: 'Open My Health', to: '/health-record', icon: <HeartIcon />,
  },
  {
    id: 7, phase: 'Manage health information', title: 'Analyze a demonstration report',
    description: 'Upload DEMO REPORT 1 for normal laboratory values or DEMO REPORT 2 for risk indicators. Review extracted parameters and the separate AI Assistive Summary.',
    outcome: 'The normal report shows no disease indication; the risk report identifies a possible disease pattern with a clinical-review warning.',
    action: 'Open Report Analysis', to: '/health-record?tab=analysis', icon: <FileIcon />,
  },
  {
    id: 8, phase: 'Continue patient care', title: 'Record health monitoring values',
    description: 'Enter values for heart rate, blood pressure, blood oxygen, temperature, blood glucose, and respiratory rate to populate trends and meaningful alerts.',
    outcome: 'All six parameter cards update, and out-of-range readings create visible patient alerts that can be cleared for the next demonstration.',
    action: 'Open monitoring', to: '/monitoring', icon: <ActivityIcon />,
  },
  {
    id: 9, phase: 'Continue patient care', title: 'Review booking-linked sharing',
    description: 'Open Sharing after booking to see the selected hospital, token, prepared record categories, and booking-linked access activity.',
    outcome: 'Only the currently booked hospital appears; removing its card clears the view until another token is booked.',
    action: 'Open sharing', to: '/sharing', icon: <ShareIcon />,
  },
  {
    id: 10, phase: 'Continue patient care', title: 'Verify report integrity',
    description: 'Choose an uploaded medical document and run integrity verification, then review the local hash result, proof status, consent history, and access audit trail.',
    outcome: 'Matching document data is confirmed, while modified content would be visibly flagged.',
    action: 'Open integrity', to: '/integrity', icon: <ShieldIcon />,
  },
  {
    id: 11, phase: 'Continue patient care', title: 'Manage the patient profile',
    description: 'Open My Profile from the circular user button or the main menu to update the patient name, email, phone, age, and gender.',
    outcome: 'Updated identity details are saved to the patient account and reused throughout the patient experience.',
    action: 'Open My Profile', to: '/profile', icon: <UserIcon />,
  },
]

const PHASES = ['Plan the visit', 'Follow the visit', 'Manage health information', 'Continue patient care']

const HEALTH_RECORD_FILES = [
  { title: 'DEMO ENCOUNTER', path: '/demo-records/DEMO ENCOUNTER.pdf', destination: 'Encounters and diagnoses', description: 'A simple discharge summary for the encounter attachment workflow.' },
  { title: 'DEMO ALLERGY', path: '/demo-records/DEMO ALLERGY.pdf', destination: 'Active allergies', description: 'A basic allergy record for demonstrating supporting-file storage.' },
  { title: 'DEMO PRESCRIPTION', path: '/demo-records/DEMO PRESCRIPTION.pdf', destination: 'Prescriptions', description: 'A sample prescription document for the medication record section.' },
  { title: 'DEMO VACCINATION', path: '/demo-records/DEMO VACCINATION.pdf', destination: 'Vaccinations', description: 'A sample vaccination certificate for the immunization section.' },
]

function loadCompleted() {
  try { return new Set(JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]')) }
  catch { return new Set() }
}

function WalkthroughCard({ step, completed, onToggle }) {
  return <article className={`relative overflow-hidden rounded-2xl border transition-all ${completed ? 'border-emerald-300 bg-emerald-50/80' : 'border-white/50 bg-[#A9D1FD] hover:-translate-y-0.5 hover:shadow-lg'}`} style={{ boxShadow: completed ? '0 4px 20px rgba(16,185,129,0.12)' : '0 4px 22px rgba(147,197,253,0.34)' }}>
    <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full border-[22px] border-white/20" /><div className="pointer-events-none absolute -bottom-14 -left-10 h-32 w-32 rounded-full border-[22px] border-white/15" />
    <div className="relative z-10 p-6">
      <div className="flex items-start gap-4"><button type="button" onClick={() => onToggle(step.id)} aria-label={completed ? `Mark ${step.title} incomplete` : `Mark ${step.title} complete`} className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-sm font-extrabold text-white shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${completed ? 'bg-emerald-600' : 'bg-[#3B82F6]'}`}>{completed ? <Icon><path d="m5 12 4 4L19 6" /></Icon> : step.id}</button><div className="min-w-0"><div className="mb-1 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700" style={MONO}>{step.icon} Patient walkthrough</div><h3 className="text-lg font-extrabold text-slate-900">{step.title}</h3></div></div>
      <p className="mt-4 text-sm leading-6 text-slate-700">{step.description}</p>
      <div className="mt-4 rounded-xl border border-white/60 bg-white/40 p-4"><div className="text-[10px] font-bold uppercase tracking-[0.16em] text-blue-700" style={MONO}>Expected result</div><p className="mt-1 text-sm leading-5 text-slate-700">{step.outcome}</p></div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3"><Link to={step.to} className="inline-flex items-center gap-2 rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">{step.action}<ArrowIcon /></Link><button type="button" onClick={() => onToggle(step.id)} className={`rounded-lg px-3 py-2 text-xs font-bold transition ${completed ? 'text-emerald-700 hover:bg-emerald-100' : 'text-blue-800 hover:bg-white/35'}`}>{completed ? 'Completed — undo' : 'Mark completed'}</button></div>
    </div>
  </article>
}

function MetricCard({ label, value, note, icon }) {
  return <div className="relative overflow-hidden rounded-2xl border border-white/50 bg-[#A9D1FD] p-5" style={{ boxShadow: '0 4px 20px rgba(147,197,253,0.3)' }}><div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full border-[18px] border-white/20" /><div className="relative z-10"><div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-[#3B82F6] text-white">{icon}</div><div className="text-2xl font-extrabold text-slate-900">{value}</div><div className="mt-1 text-sm font-bold text-slate-800">{label}</div><div className="mt-1 text-xs text-blue-900/65">{note}</div></div></div>
}

export default function DemoPage() {
  const { user } = useAuth()
  const [completed, setCompleted] = useState(loadCompleted)
  const booking = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('mediflow_last_booking') || '{}') }
    catch { return {} }
  }, [])
  const steps = useMemo(() => BASE_STEPS.map(step => step.requiresToken && booking.tokenId ? { ...step, to: `/ai-report?token_id=${encodeURIComponent(booking.tokenId)}` } : step), [booking.tokenId])

  useEffect(() => { sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...completed])) }, [completed])

  const toggle = id => setCompleted(current => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const progress = Math.round((completed.size / steps.length) * 100)

  return <section className="min-h-screen bg-[#f0f5ff] pb-16 pt-[108px]" style={{ fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}><div className="mx-auto max-w-[1360px] px-5 sm:px-10">
    <header className="relative mb-7 flex min-h-[230px] items-center justify-between gap-8 overflow-hidden rounded-2xl bg-[#0f1e3d] px-7 py-10 text-white sm:px-12">
      <div className="pointer-events-none absolute -top-20 right-48 h-80 w-80 rounded-full border-[56px] border-white/[0.04]" /><div className="pointer-events-none absolute -bottom-24 right-8 h-64 w-64 rounded-full border-[42px] border-white/[0.035]" />
      <div className="relative z-10"><div className="mb-3 flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.2em] text-blue-300" style={MONO}><UserIcon /> Patient-only product tour</div><h1 className="text-[34px] font-extrabold leading-tight tracking-tight sm:text-[40px]">Full Patient <span className="text-blue-300">Walkthrough</span></h1><p className="mt-3 max-w-2xl text-sm leading-6 text-blue-200">Follow one complete prototype journey from choosing a hospital and booking a token through queue intelligence, health records, report analysis, monitoring, secure sharing, integrity verification, and profile management.</p><div className="mt-6 flex flex-wrap gap-3"><Link to="/bookings" className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-extrabold text-white shadow-lg shadow-blue-900/20 hover:bg-blue-500">Start with booking<ArrowIcon /></Link><a href="#patient-walkthrough" className="inline-flex items-center rounded-xl border border-white/20 bg-white/[0.08] px-5 py-3 text-sm font-bold text-blue-100 hover:bg-white/[0.12]">View all steps</a></div></div>
      <div className="relative z-10 hidden min-w-[230px] rounded-2xl border border-white/15 bg-white/[0.08] p-6 text-center lg:block"><div className="text-xs font-bold uppercase tracking-widest text-white/50" style={MONO}>Walkthrough progress</div><div className="mt-2 text-4xl font-extrabold">{progress}%</div><div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-blue-400 transition-all" style={{ width: `${progress}%` }} /></div><div className="mt-3 text-xs text-blue-200">{completed.size} of {steps.length} patient steps</div></div>
    </header>

    <div className="mb-7 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="Patient steps" value={steps.length} note="No doctor or admin flow" icon={<UserIcon />} />
      <MetricCard label="Completed" value={`${completed.size}/${steps.length}`} note="Saved for this browser session" icon={<Icon><path d="m5 12 4 4L19 6" /></Icon>} />
      <MetricCard label="Latest token" value={booking.tokenCode || 'Not booked'} note={booking.tokenCode ? 'Ready for queue tracking' : 'Begin from Book Token'} icon={<QueueIcon />} />
      <MetricCard label="Patient" value={user?.name || 'Prototype user'} note="Current patient walkthrough" icon={<HeartIcon />} />
    </div>

    <section className="mb-8 grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
      <div className="relative overflow-hidden rounded-2xl border border-white/50 bg-[#A9D1FD] p-7" style={{ boxShadow: '0 4px 24px rgba(147,197,253,0.34)' }}><div className="pointer-events-none absolute -bottom-14 -left-8 h-32 w-32 rounded-full border-[22px] border-white/15" /><div className="relative z-10"><div className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>Presentation files</div><h2 className="mt-1 text-xl font-extrabold text-slate-900">Report Analysis materials</h2><p className="mt-2 text-sm leading-6 text-slate-700">Download either PDF, then use Step 7 to upload it from My Health.</p><div className="mt-5 grid gap-3 sm:grid-cols-2"><a href="/demo-reports/DEMO REPORT 1.pdf" target="_blank" rel="noreferrer" className="rounded-xl border border-white/70 bg-white/45 p-4 transition hover:bg-white/60"><div className="flex items-center gap-2 font-extrabold text-slate-900"><FileIcon /> DEMO REPORT 1</div><p className="mt-2 text-xs leading-5 text-slate-600">Normal laboratory parameters and no disease indication.</p></a><a href="/demo-reports/DEMO REPORT 2.pdf" target="_blank" rel="noreferrer" className="rounded-xl border border-white/70 bg-white/45 p-4 transition hover:bg-white/60"><div className="flex items-center gap-2 font-extrabold text-slate-900"><FileIcon /> DEMO REPORT 2</div><p className="mt-2 text-xs leading-5 text-slate-600">Risk values with possible diabetes and cardiometabolic indications.</p></a></div></div></div>
      <div className="relative overflow-hidden rounded-2xl border border-white/50 bg-[#A9D1FD] p-7" style={{ boxShadow: '0 4px 24px rgba(147,197,253,0.34)' }}><div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full border-[20px] border-white/20" /><div className="relative z-10"><div className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>Monitoring inputs</div><h2 className="mt-1 text-xl font-extrabold text-slate-900">Three demonstration sets</h2><div className="mt-4 space-y-3 text-xs text-slate-700"><div className="rounded-xl bg-white/40 p-3"><strong className="text-slate-900">Baseline:</strong> HR 74 · BP 118/78 · SpO2 98 · Temp 36.8 · Glucose 96 · RR 16</div><div className="rounded-xl bg-white/40 p-3"><strong className="text-slate-900">Elevated:</strong> HR 102 · BP 148/94 · SpO2 94 · Temp 37.8 · Glucose 168 · RR 22</div><div className="rounded-xl bg-white/40 p-3"><strong className="text-slate-900">Alert:</strong> HR 128 · BP 172/106 · SpO2 88 · Temp 39.4 · Glucose 310 · RR 32</div></div></div></div>
    </section>

    <section className="relative mb-8 overflow-hidden rounded-2xl border border-white/50 bg-[#A9D1FD] p-7" style={{ boxShadow: '0 4px 24px rgba(147,197,253,0.34)' }}>
      <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full border-[24px] border-white/20" /><div className="pointer-events-none absolute -bottom-14 -left-8 h-32 w-32 rounded-full border-[22px] border-white/15" />
      <div className="relative z-10">
        <div><div className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>Health record attachments</div><h2 className="mt-1 text-xl font-extrabold text-slate-900">Four demonstration record PDFs</h2><p className="mt-2 text-sm leading-6 text-slate-700">Open a PDF, then attach it to the matching card in the My Health Records tab.</p></div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{HEALTH_RECORD_FILES.map(record => <a key={record.title} href={record.path} target="_blank" rel="noreferrer" className="rounded-xl border border-white/70 bg-white/45 p-4 transition hover:bg-white/65"><div className="flex items-center gap-2 font-extrabold text-slate-900"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#3B82F6] text-white"><FileIcon /></span>{record.title}</div><div className="mt-3 text-[10px] font-bold uppercase tracking-[0.14em] text-blue-700" style={MONO}>{record.destination}</div><p className="mt-1 text-xs leading-5 text-slate-600">{record.description}</p></a>)}</div>
      </div>
    </section>

    <section id="patient-walkthrough" aria-label="Patient demonstration walkthrough" className="scroll-mt-28">
      {PHASES.map(phase => <div key={phase} className="mb-9"><div className="mb-4 flex items-center gap-3"><span className="h-px flex-1 bg-blue-200" /><h2 className="text-[12px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>{phase}</h2><span className="h-px flex-1 bg-blue-200" /></div><div className="grid gap-5 lg:grid-cols-2">{steps.filter(step => step.phase === phase).map(step => <WalkthroughCard key={step.id} step={step} completed={completed.has(step.id)} onToggle={toggle} />)}</div></div>)}
    </section>

    <section className="relative overflow-hidden rounded-2xl border border-white/50 bg-[#A9D1FD] p-7" style={{ boxShadow: '0 4px 24px rgba(147,197,253,0.32)' }}><div className="pointer-events-none absolute -bottom-16 -left-10 h-36 w-36 rounded-full border-[24px] border-white/15" /><div className="relative z-10 flex flex-col justify-between gap-5 sm:flex-row sm:items-center"><div><div className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>Walkthrough controls</div><h2 className="mt-1 text-xl font-extrabold text-slate-900">Ready for another presentation?</h2><p className="mt-1 text-sm text-slate-600">Reset only the walkthrough checklist. Patient data, bookings, reports, and monitoring records remain unchanged.</p></div><button type="button" onClick={() => setCompleted(new Set())} disabled={!completed.size} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-blue-200 bg-white/55 px-5 py-3 text-sm font-extrabold text-blue-700 transition hover:bg-white/75 disabled:cursor-not-allowed disabled:opacity-40"><ResetIcon /> Reset walkthrough</button></div></section>
  </div></section>
}
