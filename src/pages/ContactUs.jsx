export default function ContactUs() {
  return (
    <section
      className="pt-[108px] pb-20 min-h-screen"
      style={{ background: '#f1f5fb', fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}
    >
      <div className="max-w-[720px] mx-auto px-8">

        {/* Simple flat header */}
        <div className="mb-10">
          <p className="font-bold mb-2" style={{ fontSize: 11, letterSpacing: '2.5px', textTransform: 'uppercase', color: '#3b82f6', fontFamily: 'DM Mono, monospace' }}>
            Contact
          </p>
          <h1 className="font-extrabold mb-2" style={{ fontSize: 36, color: '#0f1e3d', letterSpacing: '-1px', lineHeight: 1.15 }}>
            Contact Us
          </h1>
          <p style={{ fontSize: 14.5, color: '#475569', lineHeight: 1.6 }}>
            Reach out for queries, feedback, or collaboration.
          </p>
        </div>

        {/* Content card */}
        <div className="bg-white rounded-2xl" style={{ border: '1px solid #bfdbfe', boxShadow: '0 1px 3px rgba(37,99,235,0.08), 0 4px 24px rgba(37,99,235,0.07)', padding: '2.5rem 3rem' }}>

          {/* Status notice */}
          <div className="rounded-xl mb-8 flex items-start gap-3" style={{ background: '#eff6ff', border: '1px solid #bfdbfe', padding: '1rem 1.25rem' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 flex-shrink-0 mt-0.5" aria-hidden="true">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <p style={{ fontSize: 13.5, color: '#1e40af', lineHeight: 1.6 }}>
              <span className="font-bold">MediFlow SecureAI</span> is currently in active development phase.
            </p>
          </div>

          {/* Message lines */}
          <div className="flex flex-col gap-6">

            <div>
              <div className="font-bold mb-1" style={{ fontSize: 11, letterSpacing: '2px', textTransform: 'uppercase', color: '#94a3b8', fontFamily: 'DM Mono, monospace' }}>Project Status</div>
              <p style={{ fontSize: 15, color: '#0f172a', lineHeight: 1.7 }}>
                MediFlow SecureAI: Application in development phase...
              </p>
            </div>

            <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1.5rem' }}>
              <div className="font-bold mb-3" style={{ fontSize: 11, letterSpacing: '2px', textTransform: 'uppercase', color: '#94a3b8', fontFamily: 'DM Mono, monospace' }}>Created By</div>
              <div className="flex flex-col gap-2">
                {['Souhardya Mridha', 'Sourashree Mukherjee'].map(name => (
                  <div key={name} className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: '#eff6ff', color: '#2563eb' }}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4" aria-hidden="true">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
                      </svg>
                    </div>
                    <span className="font-semibold" style={{ fontSize: 14.5, color: '#0f172a' }}>{name}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1.5rem' }}>
              <div className="font-bold mb-3" style={{ fontSize: 11, letterSpacing: '2px', textTransform: 'uppercase', color: '#94a3b8', fontFamily: 'DM Mono, monospace' }}>Email</div>
              <a
                href="mailto:souhardya2506@gmail.com"
                className="inline-flex items-center gap-2.5 font-semibold transition-colors hover:text-blue-700"
                style={{ fontSize: 14.5, color: '#2563eb', textDecoration: 'none' }}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 flex-shrink-0" aria-hidden="true">
                  <rect x="2" y="4" width="20" height="16" rx="2" /><polyline points="2,4 12,13 22,4" />
                </svg>
                souhardya2506@gmail.com
              </a>
              <p style={{ fontSize: 12.5, color: '#64748b', marginTop: '0.4rem' }}>For any queries.</p>
            </div>

            <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1.5rem', textAlign: 'center' }}>
              <p className="font-bold" style={{ fontSize: 16, color: '#0f172a', letterSpacing: '-0.3px' }}>
                Thank You.
              </p>
            </div>

          </div>
        </div>

      </div>
    </section>
  )
}
