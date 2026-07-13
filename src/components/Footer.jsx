/**
 * Footer — updated branding, removed Emergency Triage link, added Contact Us
 */
import { Link } from 'react-router-dom'

const footerLinks = {
  Platform: [
    { label: 'Queue Tracker',       to: '/queue' },
    { label: 'Book a Token',        to: '/bookings' },
    { label: 'My Health Record',    to: '/health-record' },
  ],
  Safety: [
    { label: 'Emergency Guidance',  to: '/emergency-guidance' },
    { label: 'AI Limitations',      to: '/ai-limitations' },
    { label: 'Consent Explained',   to: '/consent-explanation' },
  ],
  Legal: [
    { label: 'Privacy Policy',      to: '/privacy' },
    { label: 'Terms of Service',    to: '/terms', disabled: true },
    { label: 'Contact Us',          to: '/contact' },
  ],
}

const IconTwitter = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="15" height="15" aria-hidden="true">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.737-8.835L1.254 2.25H8.08l4.253 5.622 5.911-5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
)

const IconLinkedIn = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" width="15" height="15" aria-hidden="true">
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
  </svg>
)

const IconMail = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="15" height="15" aria-hidden="true">
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <polyline points="2,4 12,13 22,4" />
  </svg>
)

export default function Footer() {
  return (
    <footer className="bg-slate-50 border-t border-slate-200">
      <div className="max-w-[1440px] mx-auto py-10 px-4 sm:px-8">
        {/* Top grid */}
        <div className="grid grid-cols-2 gap-8 mb-8 sm:grid-cols-4 lg:grid-cols-5">
          {/* Brand */}
          <div className="col-span-2">
            <Link to="/" className="font-bold text-slate-900 text-base block mb-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded w-fit">
              MediFlow <span className="text-blue-700">SecureAI</span>
            </Link>
            <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
              A secure, privacy-first healthcare platform with consent-based access,
              encrypted records, and AI decision support diagnosis.
            </p>
          </div>

          {/* Link columns */}
          {Object.entries(footerLinks).map(([heading, links]) => (
            <div key={heading}>
              <h2 className="text-xs font-semibold text-slate-900 mb-4 tracking-wide uppercase">
                {heading}
              </h2>
              <ul className="flex flex-col gap-3">
                {links.map(({ label, to, disabled }) => (
                  <li key={label}>
                    {disabled ? (
                      <span className="text-xs font-medium text-slate-400 cursor-not-allowed" aria-disabled="true">
                        {label}
                      </span>
                    ) : (
                      <Link
                        to={to}
                        className="text-xs font-medium text-slate-500 hover:text-blue-600 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
                      >
                        {label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col sm:flex-row justify-between items-center pt-6 border-t border-slate-200 gap-4">
          <p className="text-xs text-slate-400">
            © {new Date().getFullYear()} MediFlow Secure. All rights reserved.
          </p>
          <p className="text-xs text-slate-400 text-center sm:text-left">
            AI outputs are decision support only — not medical diagnoses.{' '}
            <Link to="/ai-limitations" className="underline hover:text-blue-600 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded">
              Learn more
            </Link>
          </p>
          <div className="flex items-center gap-4">
            <a
              href="https://twitter.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="MediFlow on Twitter / X"
              className="text-slate-400 hover:text-blue-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded p-1"
            >
              <IconTwitter />
            </a>
            <a
              href="https://linkedin.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="MediFlow on LinkedIn"
              className="text-slate-400 hover:text-blue-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded p-1"
            >
              <IconLinkedIn />
            </a>
            <a
              href="mailto:support@mediflow.example"
              aria-label="Email MediFlow support"
              className="text-slate-400 hover:text-blue-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded p-1"
            >
              <IconMail />
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
