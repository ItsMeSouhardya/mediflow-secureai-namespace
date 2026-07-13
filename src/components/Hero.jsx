import { Link } from 'react-router-dom'

const trustPoints = [
  { label: '1200+ Patients Served', icon: 'groups' },
  { label: 'Security Ready Features', icon: 'verified_user' },
  { label: 'Government\nReady\nProduction', icon: 'language' },
]

export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center pt-28 pb-12 overflow-hidden">
      <div className="absolute inset-0 z-0">
        <div className="hero-bg-image absolute inset-0 scale-105" />
        <div className="absolute inset-0 bg-white/40" />
      </div>

      <div className="relative z-10 max-w-[1440px] mx-auto px-8 w-full grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        <div className="flex flex-col gap-7">
          <div className="inline-flex items-center gap-3 px-4 py-2 bg-white/70 backdrop-blur-md border border-white/80 rounded-full self-start shadow-lg">
            <span className="text-[10px] font-black text-blue-600 px-2 py-0.5 rounded bg-blue-50 border border-blue-100 uppercase tracking-widest">New</span>
            <span className="text-sm font-semibold text-slate-700">Secure AI Powered Healthcare Solution</span>
          </div>

          <h1 className="font-black text-[56px] md:text-[68px] leading-[0.98] tracking-tight" style={{ color: '#0f1e3d' }}>
            Reduce <span style={{ color: '#3B82F6' }}>Hospital</span>
            <br />
            <span style={{ color: '#3B82F6' }}>Waiting</span> Time
          </h1>

          <p className="text-xl leading-relaxed text-slate-700 max-w-2xl">
            Book tokens online, track queues live, and prioritize urgent care with AI-powered patient flow management.
          </p>

          <div className="flex flex-wrap gap-4 items-center">
            <Link to="/dashboard" className="flex items-center justify-center px-7 py-3.5 font-bold text-lg rounded-2xl transition-all shadow-xl" style={{ background: '#3B82F6', color: 'white', boxShadow: '0 8px 24px rgba(59,130,246,0.35)' }}>
              Get Started
            </Link>
            <a
              href="https://drive.google.com/file/d/1HiO7Cr18ykhF7igzQjkcgPk7rtssUK-z"
              target="_blank"
              rel="noopener noreferrer"
              className="px-7 py-3.5 bg-white/85 backdrop-blur-md border border-white text-slate-900 font-bold text-lg rounded-2xl hover:bg-white transition-all flex items-center gap-2 shadow-xl"
            >
              <span className="material-symbols-outlined text-blue-600 text-xl">play_circle</span>
              Watch Demo
            </a>
          </div>

          <div className="pt-2">
            <p className="text-[28px] font-semibold text-slate-800 mb-4">Trust and Impact</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {trustPoints.map((point) => (
                <div key={point.label} className="glass-card rounded-2xl px-4 py-4 flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-blue-50 text-blue-700 flex items-center justify-center flex-shrink-0">
                    <span className="material-symbols-outlined text-lg">{point.icon}</span>
                  </div>
                  <p className="text-slate-800 font-semibold leading-snug text-sm flex-1 whitespace-pre-line" style={{ fontFamily: 'DM Mono, monospace' }}>{point.label}</p>
                  <span className="material-symbols-outlined text-green-500 text-xl flex-shrink-0">check_circle</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="relative flex justify-center lg:justify-end">
          <div className="absolute top-[56%] -left-2 glass-card px-4 py-3 rounded-2xl shadow-xl z-20 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-green-100 text-green-600 flex items-center justify-center">
              <span className="material-symbols-outlined">bolt</span>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 font-semibold">Avg Wait Reduced</p>
              <p className="text-3xl font-black text-slate-900 leading-none">25%</p>
            </div>
          </div>

          <div className="glass-card w-full max-w-[520px] rounded-[30px] p-6 sm:p-7 flex flex-col gap-5 shadow-2xl border-white/80 relative">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-4xl font-black text-slate-900 tracking-tight">City Hospital</h3>
                <p className="text-xl text-slate-500">OPD • Live</p>
              </div>
              <div className="w-28 h-16 rounded-xl overflow-hidden border border-white shadow-md">
                <img src="/hero-bg.jpg" alt="Hospital building" className="w-full h-full object-cover" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-white bg-white/70 p-4">
                <p className="text-xs text-slate-500 mb-1">NOW SERVING</p>
                <p className="text-4xl font-black text-slate-900">A-43</p>
              </div>
              <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-xs text-slate-500 mb-1">YOUR TOKEN</p>
                <p className="text-4xl font-black" style={{ color: '#3B82F6' }}>A-52</p>
              </div>
            </div>

            <div className="bg-slate-800 rounded-2xl p-4 text-white flex items-center justify-between">
              <div>
                <p className="text-[11px] text-slate-300 mb-1">ESTIMATED ARRIVAL TIME</p>
                <p className="text-4xl font-black leading-none">12 <span className="text-xl font-semibold text-slate-300">min wait</span></p>
              </div>
              <div className="px-4 py-2 rounded-xl bg-red-100 text-red-700 font-bold text-sm flex items-center gap-1">
                <span className="material-symbols-outlined text-base">emergency</span>
                Emergency Priority Active
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between">
                <p className="text-sm font-semibold text-slate-600">QUEUE STATUS</p>
                <p className="text-sm font-semibold text-slate-600">9 People Ahead</p>
              </div>
              <div className="h-2.5 w-full rounded-full bg-slate-200 overflow-hidden">
                <div className="h-full w-[70%] rounded-full bg-blue-500" />
              </div>
              <div className="flex justify-between text-xs text-slate-500">
                <span>A-44</span>
                <span>A-52</span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-xl bg-red-50 border border-red-100 text-center py-2">
                <p className="text-xs text-red-500 font-semibold">DENTAL</p>
                <p className="text-sm font-bold text-red-700">Crowded</p>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 text-center py-2">
                <p className="text-xs text-slate-500 font-semibold">CARDIO</p>
                <p className="text-sm font-bold text-slate-700">Fast</p>
              </div>
              <div className="rounded-xl bg-green-50 border border-green-100 text-center py-2">
                <p className="text-xs text-green-500 font-semibold">14 Doctors</p>
                <p className="text-sm font-bold text-green-700">Active</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
