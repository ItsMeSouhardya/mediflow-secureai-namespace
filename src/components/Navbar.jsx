/**
 * Role-aware, fully responsive Navbar
 *
 * - Logo + "MediFlow SecureAI" branding
 * - Demo removed from centre links; Demo button lives in the right action area
 * - 3-bar dropdown at far right lists ALL pages + sign-out at bottom
 * - Active route underlined with animated indicator
 * - Focus-visible ring on all interactive elements
 */
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../auth/authState'

const UserIcon = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 flex-shrink-0" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>

export default function Navbar() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [dropOpen, setDropOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const desktopDropRef = useRef(null)
  const mobileDropRef = useRef(null)
  const desktopDropBtnRef = useRef(null)
  const mobileDropBtnRef = useRef(null)
  const profileRef = useRef(null)
  const profileBtnRef = useRef(null)
  const roles = user?.roles ?? []

  const isPatient      = roles.includes('patient')
  const isDoctor       = roles.includes('doctor')
  const isHospitalAdmin = roles.includes('hospital_admin')
  const isSecurityAdmin = roles.includes('security_admin')

  // ── Centre nav links (Demo removed from here) ──────────────────────────────
  const navLinks = [
    { label: 'Home',          to: '/' },
    { label: 'Dashboard',     to: '/dashboard' },
    { label: 'Queue',         to: '/queue' },
    { label: 'Emergency',     to: '/emergency' },
    ...(isPatient ? [
      { label: 'Book Token',  to: '/bookings' },
      { label: 'My Health',   to: '/health-record' },
      { label: 'Monitoring',  to: '/monitoring' },
      { label: 'Sharing',     to: '/sharing' },
      { label: 'Integrity',   to: '/integrity' },
    ] : []),
    ...(isDoctor ? [
      { label: 'My Dashboard',  to: '/doctor-dashboard' },
      { label: 'Clinical',      to: '/clinical-workspace' },
      { label: 'Triage',        to: '/monitoring/triage' },
      { label: 'Shares',        to: '/incoming-shares' },
    ] : []),
    ...(isHospitalAdmin ? [
      { label: 'Queue Admin', to: '/admin-dashboard' },
      { label: 'Shares',      to: '/incoming-shares' },
    ] : []),
    ...(isSecurityAdmin ? [
      { label: 'Security',    to: '/security' },
    ] : []),
  ]

  // ── All pages listed in the 3-bar dropdown ──────────────────────────────────
  // Always-visible public pages first, then role-specific ones
  const dropLinks = [
    { label: 'Home',          to: '/' },
    { label: 'Demo',          to: '/demo' },
    { label: 'Dashboard',     to: '/dashboard' },
    { label: 'Queue',         to: '/queue' },
    { label: 'Emergency',     to: '/emergency' },
    ...(isPatient ? [
      { label: 'Book Token',  to: '/bookings' },
      { label: 'My Health',   to: '/health-record' },
      { label: 'Monitoring',  to: '/monitoring' },
      { label: 'Sharing',     to: '/sharing' },
      { label: 'Integrity',   to: '/integrity' },
    ] : []),
    ...(isDoctor ? [
      { label: 'My Dashboard',  to: '/doctor-dashboard' },
      { label: 'Clinical',      to: '/clinical-workspace' },
      { label: 'Triage',        to: '/monitoring/triage' },
      { label: 'Shares',        to: '/incoming-shares' },
    ] : []),
    ...(isHospitalAdmin ? [
      { label: 'Queue Admin', to: '/admin-dashboard' },
      { label: 'Shares',      to: '/incoming-shares' },
    ] : []),
    ...(isSecurityAdmin ? [
      { label: 'Security',    to: '/security' },
    ] : []),
    ...(user ? [
      { label: 'My Profile',  to: '/profile', icon: <UserIcon /> },
    ] : []),
  ]

  // ── Primary CTA button ──────────────────────────────────────────────────────
  const primaryAction = !user
    ? { label: 'Sign in', to: '/login' }
    : isDoctor
      ? { label: 'Clinical', to: '/clinical-workspace' }
      : isPatient
        ? { label: 'Book Token', to: '/bookings' }
        : isHospitalAdmin
          ? { label: 'Queue Admin', to: '/admin-dashboard' }
          : { label: 'Dashboard', to: '/dashboard' }

  const profileInitial = (user?.name?.trim()?.[0] || user?.email?.trim()?.[0] || 'U').toUpperCase()

  const toggleMenu = () => {
    setDropOpen(current => !current)
    setProfileOpen(false)
  }

  const toggleProfile = () => {
    setProfileOpen(current => !current)
    setDropOpen(false)
  }

  const navigateFromTray = to => {
    setDropOpen(false)
    setProfileOpen(false)
    navigate(to)
  }

  // Desktop and mobile menu variants are both mounted, so each needs its own
  // reference. Otherwise a mouse-down in the visible menu can be mistaken for
  // an outside click when the shared ref points at the hidden variant.
  useEffect(() => {
    function handleOutside(e) {
      const interactiveRegions = [
        desktopDropRef, mobileDropRef, desktopDropBtnRef, mobileDropBtnRef,
        profileRef, profileBtnRef,
      ]
      if (!interactiveRegions.some(ref => ref.current?.contains(e.target))) {
        setDropOpen(false)
        setProfileOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [])

  const handleLogout = () => {
    setDropOpen(false)
    setProfileOpen(false)
    logout()
  }

  return (
    <header className="fixed top-3 left-1/2 -translate-x-1/2 w-[96%] max-w-[1440px] z-50 bg-white/60 backdrop-blur-xl border border-white/60 rounded-2xl shadow-xl shadow-slate-700/10">
      <nav
        className="flex justify-between items-center px-4 sm:px-6 h-16"
        role="navigation"
        aria-label="Main navigation"
      >
        {/* ── Brand ──────────────────────────────────────────────────────── */}
        <Link
          to="/"
          className="flex items-center gap-2.5 flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-lg"
        >
          {/* Logo icon — rounded square card matching screenshot 1 */}
          <div className="w-9 h-9 rounded-xl bg-white shadow-sm border border-slate-100 flex items-center justify-center flex-shrink-0 overflow-hidden">
            <img
              src="/logo.jpg"
              alt="MediFlow SecureAI logo"
              className="w-full h-full object-cover"
              onError={e => {
                // fallback SVG if logo.jpg fails
                e.currentTarget.style.display = 'none'
                e.currentTarget.parentElement.innerHTML =
                  `<svg viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="1.8" class="w-5 h-5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`
              }}
            />
          </div>
          <span className="text-2xl font-extrabold tracking-tight leading-none">
            <span className="text-blue-700">MediFlow </span>
            <span className="text-slate-700">Secure</span><span className="text-blue-700">AI</span>
          </span>
        </Link>

        {/* ── Desktop centre links ────────────────────────────────────────── */}
        <div className="hidden lg:flex items-center gap-5 flex-1 justify-center px-4">
          {navLinks.map(({ label, to }) => (
            <Link
              key={to}
              to={to}
              className={`text-sm font-semibold transition-colors hover:text-blue-700 relative py-1
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded
                ${pathname === to ? 'text-blue-700' : 'text-slate-700'}`}
              aria-current={pathname === to ? 'page' : undefined}
            >
              {label}
              {pathname === to && (
                <span className="absolute bottom-0 left-0 w-full h-0.5 bg-blue-700 rounded-full" aria-hidden="true" />
              )}
            </Link>
          ))}
        </div>

        {/* ── Desktop right actions ───────────────────────────────────────── */}
        <div className="hidden lg:flex items-center gap-2 flex-shrink-0">
          {/* Primary CTA */}
          <Link
            to={primaryAction.to}
            className="bg-blue-700 text-white px-4 py-2 rounded-xl font-semibold text-sm hover:bg-blue-800 transition-all active:scale-95 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {primaryAction.label}
          </Link>

          {/* Demo button — replaces the old Sign out text button; always shown */}
          <Link
            to="/demo"
            className={`text-sm font-semibold px-3 py-2 rounded-xl transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
              ${pathname === '/demo'
                ? 'text-blue-700 bg-blue-50'
                : 'text-slate-600 hover:text-blue-700 hover:bg-blue-50'}`}
          >
            Demo
          </Link>

          {user && <div className="relative">
            <button
              ref={profileBtnRef}
              type="button"
              onClick={toggleProfile}
              aria-expanded={profileOpen}
              aria-haspopup="dialog"
              aria-label="Open profile menu"
              className="flex h-10 w-10 items-center justify-center rounded-full border-2 border-white bg-[#1F5BDD] text-sm font-extrabold text-white shadow-md transition-colors hover:bg-[#1D4ED8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {profileInitial}
            </button>
            {profileOpen && <div ref={profileRef} role="dialog" aria-label="Profile menu" className="absolute right-0 top-[calc(100%+8px)] w-72 overflow-hidden rounded-2xl border border-slate-100 bg-white/95 shadow-2xl shadow-slate-900/15 backdrop-blur-xl">
              <div className="border-b border-slate-100 px-5 py-4">
                <div className="flex items-center gap-3"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#1F5BDD] font-extrabold text-white">{profileInitial}</span><div className="min-w-0"><div className="truncate text-sm font-extrabold text-slate-900">{user.name}</div><div className="mt-0.5 truncate text-xs text-slate-500">{user.email}</div></div></div>
              </div>
              <div className="p-3"><button type="button" onClick={() => navigateFromTray('/profile')} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"><UserIcon /> My Profile</button></div>
            </div>}
          </div>}

          {/* 3-bar dropdown trigger */}
          <div className="relative">
            <button
              ref={desktopDropBtnRef}
              onClick={toggleMenu}
              aria-expanded={dropOpen}
              aria-haspopup="menu"
              aria-controls="nav-dropdown"
              aria-label="All pages menu"
              className="w-10 h-10 flex items-center justify-center rounded-xl bg-white shadow-sm border border-slate-100 text-slate-700 hover:bg-slate-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {dropOpen
                ? <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="h-5 w-5" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
              }
            </button>

            {/* Dropdown panel */}
            {dropOpen && (
              <div
                ref={desktopDropRef}
                id="nav-dropdown"
                role="menu"
                className="absolute right-0 top-[calc(100%+8px)] w-56 rounded-2xl bg-white/90 backdrop-blur-xl border border-slate-100 shadow-2xl shadow-slate-900/15 py-2 flex flex-col"
              >
                {dropLinks.map(({ label, to, icon }) => (
                  <button
                    type="button"
                    key={to}
                    role="menuitem"
                    onClick={() => navigateFromTray(to)}
                    className={`flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm font-semibold transition-colors
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                      ${pathname === to
                        ? 'text-blue-700 bg-blue-50'
                        : 'text-slate-700 hover:bg-slate-50 hover:text-blue-700'}`}
                    aria-current={pathname === to ? 'page' : undefined}
                  >
                    {icon || (pathname === to && (
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-600 flex-shrink-0" aria-hidden="true" />
                    ))}
                    {!icon && pathname !== to && <span className="w-1.5 h-1.5 flex-shrink-0" />}
                    {label}
                    {pathname === to && (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 ml-auto text-blue-600" aria-hidden="true">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </button>
                ))}

                {/* Divider + Sign out / Sign in at bottom */}
                <div className="mt-1 border-t border-slate-100 pb-1 pt-2">
                  {user ? (
                    <button
                      role="menuitem"
                      onClick={handleLogout}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 flex-shrink-0" aria-hidden="true">
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                        <polyline points="16 17 21 12 16 7" />
                        <line x1="21" y1="12" x2="9" y2="12" />
                      </svg>
                      Sign out
                    </button>
                  ) : (
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => navigateFromTray('/login')}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-semibold text-blue-700 transition-colors hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 flex-shrink-0" aria-hidden="true">
                        <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                        <polyline points="10 17 15 12 10 7" />
                        <line x1="15" y1="12" x2="3" y2="12" />
                      </svg>
                      Sign in
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Mobile: 3-bar only (replaces old hamburger) ─────────────────── */}
        <div className="lg:hidden relative">
          <button
            ref={mobileDropBtnRef}
            onClick={toggleMenu}
            aria-expanded={dropOpen}
            aria-haspopup="menu"
            aria-controls="nav-dropdown"
            aria-label="All pages menu"
            className="w-10 h-10 flex items-center justify-center rounded-xl bg-white shadow-sm border border-slate-100 text-slate-700 hover:bg-slate-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {dropOpen
              ? <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="w-5 h-5" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            }
          </button>

          {dropOpen && (
            <div
              ref={mobileDropRef}
              id="nav-dropdown"
              role="menu"
              className="absolute right-0 top-[calc(100%+8px)] w-64 rounded-2xl bg-white/95 backdrop-blur-xl border border-slate-100 shadow-2xl shadow-slate-900/15 py-2 flex flex-col"
            >
              {/* Primary CTA at top of mobile dropdown */}
              <div className="px-3 pb-2 border-b border-slate-100 mb-1">
                <Link
                  to={primaryAction.to}
                  role="menuitem"
                  onClick={() => setDropOpen(false)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-700 text-white text-sm font-semibold hover:bg-blue-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  {primaryAction.label}
                </Link>
              </div>

              {dropLinks.map(({ label, to, icon }) => (
                <button
                  type="button"
                  key={to}
                  role="menuitem"
                  onClick={() => navigateFromTray(to)}
                  className={`flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm font-semibold transition-colors
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                    ${pathname === to
                      ? 'text-blue-700 bg-blue-50'
                      : 'text-slate-700 hover:bg-slate-50 hover:text-blue-700'}`}
                  aria-current={pathname === to ? 'page' : undefined}
                >
                  {icon || (pathname === to && (
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600 flex-shrink-0" aria-hidden="true" />
                  ))}
                  {!icon && pathname !== to && <span className="w-1.5 h-1.5 flex-shrink-0" />}
                  {label}
                  {pathname === to && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 ml-auto text-blue-600" aria-hidden="true">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </button>
              ))}

              <div className="mt-1 border-t border-slate-100 pb-1 pt-2">
                {user ? (
                  <button
                    role="menuitem"
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 flex-shrink-0" aria-hidden="true">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                      <polyline points="16 17 21 12 16 7" />
                      <line x1="21" y1="12" x2="9" y2="12" />
                    </svg>
                    Sign out
                  </button>
                ) : (
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => navigateFromTray('/login')}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-semibold text-blue-700 transition-colors hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 flex-shrink-0" aria-hidden="true">
                      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                      <polyline points="10 17 15 12 10 7" />
                      <line x1="15" y1="12" x2="3" y2="12" />
                    </svg>
                    Sign in
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </nav>
    </header>
  )
}
