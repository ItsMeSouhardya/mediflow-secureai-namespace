import Hero from '../components/Hero'
import { Link } from 'react-router-dom'

const features = [
  {
    n: '1',
    title: 'Live Queue Tracking',
    desc: 'Enter your token and monitor your exact position in real-time. AI predicts your wait time dynamically as the queue moves.',
    link: '/queue',
    linkLabel: 'Track Queue',
  },
  {
    n: '2',
    title: 'AI Smart Report',
    desc: 'Get a personalized AI report for your token — recommended doctor, best time to visit, peak hour status, and hospital alternatives.',
    link: '/queue',
    linkLabel: 'View Report',
  },
  {
    n: '3',
    title: 'Online Token Booking',
    desc: 'Reserve your spot digitally before arriving. AI assigns priority based on your age and symptoms — no physical waiting.',
    link: '/bookings',
    linkLabel: 'Book Token',
  },
  {
    n: '4',
    title: 'My Health',
    desc: 'Keep your health information in one place, upload medical reports, review structured analysis, and access your care history whenever needed.',
    link: '/health-record',
    linkLabel: 'View My Health',
  },
  {
    n: '5',
    title: 'Emergency AI Triage',
    desc: 'Describe symptoms and our AI instantly determines severity, suggests the right department, and activates emergency protocols if needed.',
    link: '/emergency',
    linkLabel: 'Try Triage',
  },
  {
    n: '6',
    title: 'Integrity Verification',
    desc: 'Verify that medical documents and consent records remain unchanged using cryptographic hashes and registered blockchain proofs.',
    link: '/integrity',
    linkLabel: 'Verify Records',
  },
]

export default function Landing() {
  return (
    <>
      <Hero />

      {/* ── Features Section ──────────────────────────────────────────────── */}
      <section style={{ background: '#f0f5ff', padding: '5rem 0 5rem' }}>
        <div className="max-w-[1440px] mx-auto px-8">

          {/* Section header */}
          <div className="mb-10">
            <div className="font-bold font-mono mb-3" style={{ fontSize: 12, letterSpacing: '2.5px', textTransform: 'uppercase', color: '#3B82F6' }}>
              Platform Features
            </div>
            <h2 className="font-extrabold" style={{ fontSize: 36, color: '#0f1e3d', letterSpacing: '-1px', lineHeight: 1.15 }}>
              Everything you need for<br />
              <span style={{ color: '#3B82F6' }}>smarter healthcare</span>
            </h2>
          </div>

          {/* 3-col × 2-row grid */}
          <div className="grid grid-cols-3 gap-5">
            {features.map(card => (
              <div
                key={card.n}
                className="bg-white rounded-2xl flex flex-col gap-4 transition-transform hover:-translate-y-1"
                style={{ border: '1px solid #bfdbfe', boxShadow: '0 1px 3px rgba(37,99,235,0.08),0 4px 16px rgba(37,99,235,0.07)', padding: '1.75rem 2rem' }}
              >
                {/* Number badge */}
                <div
                  className="flex items-center justify-center font-extrabold font-mono rounded-xl flex-shrink-0"
                  style={{ width: 36, height: 36, background: '#3B82F6', color: 'white', fontSize: 16 }}
                >
                  {card.n}
                </div>

                <div className="flex flex-col gap-2 flex-1">
                  <div className="font-bold" style={{ fontSize: 16, color: '#0f1e3d', letterSpacing: '-0.3px' }}>{card.title}</div>
                  <div style={{ fontSize: 13.5, color: '#475569', lineHeight: 1.65 }}>{card.desc}</div>
                </div>

                <Link
                  to={card.link}
                  className="flex items-center gap-1.5 font-bold self-start"
                  style={{ fontSize: 12.5, color: '#3B82F6', textDecoration: 'none', fontFamily: 'DM Mono, monospace', letterSpacing: '0.5px' }}
                >
                  {card.linkLabel}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="13" height="13">
                    <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
                  </svg>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  )
}
