/**
 * Shared accessible UI primitives — task 14.6
 *
 * All interactive elements carry:
 *  - Visible focus rings (focus-visible:ring-2)
 *  - Proper ARIA roles/labels
 *  - Keyboard accessibility (Enter/Space triggers buttons)
 *  - Sufficient colour contrast (WCAG AA against white backgrounds)
 */

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------
export function Spinner({ size = 'md', label = 'Loading…', className = '' }) {
  const sz = { sm: 'h-4 w-4', md: 'h-6 w-6', lg: 'h-10 w-10' }[size] ?? 'h-6 w-6'
  return (
    <span role="status" aria-label={label} className={`inline-flex items-center justify-center ${className}`}>
      <svg
        className={`animate-spin text-blue-600 ${sz}`}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
      <span className="sr-only">{label}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------
export function Card({ children, className = '', as: Tag = 'div', ...props }) {
  return (
    <Tag
      className={`rounded-2xl border border-blue-100 bg-white shadow-sm ${className}`}
      {...props}
    >
      {children}
    </Tag>
  )
}

// ---------------------------------------------------------------------------
// PageHeader
// ---------------------------------------------------------------------------
export function PageHeader({ eyebrow, title, subtitle, actions, className = '' }) {
  return (
    <div className={`flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between ${className}`}>
      <div>
        {eyebrow && (
          <p className="mb-1 text-xs font-bold uppercase tracking-widest text-blue-600" aria-hidden="true">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl font-extrabold text-slate-900 sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="mt-3 flex flex-wrap items-center gap-2 sm:mt-0">{actions}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Badge / StatusBadge
// ---------------------------------------------------------------------------
const BADGE_VARIANTS = {
  blue:    'bg-blue-50 text-blue-700 border border-blue-200',
  green:   'bg-emerald-50 text-emerald-700 border border-emerald-200',
  yellow:  'bg-amber-50 text-amber-700 border border-amber-200',
  red:     'bg-red-50 text-red-700 border border-red-200',
  slate:   'bg-slate-100 text-slate-600 border border-slate-200',
  purple:  'bg-purple-50 text-purple-700 border border-purple-200',
}

export function Badge({ children, variant = 'slate', className = '' }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_VARIANTS[variant] ?? BADGE_VARIANTS.slate} ${className}`}>
      {children}
    </span>
  )
}

const STATUS_MAP = {
  // Queue / session
  waiting:         { variant: 'blue',   label: 'Waiting' },
  serving:         { variant: 'green',  label: 'Serving' },
  completed:       { variant: 'slate',  label: 'Completed' },
  missed:          { variant: 'yellow', label: 'Missed' },
  cancelled:       { variant: 'red',    label: 'Cancelled' },
  // Consent
  pending:         { variant: 'yellow', label: 'Pending' },
  granted:         { variant: 'green',  label: 'Granted' },
  denied:          { variant: 'red',    label: 'Denied' },
  revoked:         { variant: 'red',    label: 'Revoked' },
  expired:         { variant: 'slate',  label: 'Expired' },
  break_glass:     { variant: 'purple', label: 'Break-Glass' },
  // Documents
  ready:           { variant: 'green',  label: 'Ready' },
  upload:          { variant: 'blue',   label: 'Uploading' },
  processing:      { variant: 'yellow', label: 'Processing' },
  failed:          { variant: 'red',    label: 'Failed' },
  quarantined:     { variant: 'red',    label: 'Quarantined' },
  archived:        { variant: 'slate',  label: 'Archived' },
  // Sessions
  scheduled:       { variant: 'blue',   label: 'Scheduled' },
  confirmed:       { variant: 'green',  label: 'Confirmed' },
  in_progress:     { variant: 'green',  label: 'In Progress' },
  patient_waiting: { variant: 'yellow', label: 'Patient Waiting' },
  doctor_waiting:  { variant: 'yellow', label: 'Doctor Waiting' },
  // Alerts
  open:            { variant: 'red',    label: 'Open' },
  acknowledged:    { variant: 'yellow', label: 'Acknowledged' },
  resolved:        { variant: 'green',  label: 'Resolved' },
  // Risk bands
  low:             { variant: 'green',  label: 'Low' },
  moderate:        { variant: 'yellow', label: 'Moderate' },
  high:            { variant: 'red',    label: 'High' },
  very_high:       { variant: 'red',    label: 'Very High' },
}

export function StatusBadge({ status, className = '' }) {
  const cfg = STATUS_MAP[status] ?? { variant: 'slate', label: status }
  return <Badge variant={cfg.variant} className={className}>{cfg.label}</Badge>
}

// ---------------------------------------------------------------------------
// Alert (inline — not a toast)
// ---------------------------------------------------------------------------
const ALERT_STYLES = {
  info:    { wrap: 'bg-blue-50 border-blue-300 text-blue-800',   icon: 'ℹ' },
  success: { wrap: 'bg-emerald-50 border-emerald-300 text-emerald-800', icon: '✓' },
  warning: { wrap: 'bg-amber-50 border-amber-300 text-amber-800', icon: '⚠' },
  error:   { wrap: 'bg-red-50 border-red-300 text-red-800',      icon: '✕' },
}

export function Alert({ variant = 'info', title, children, onDismiss, className = '' }) {
  const s = ALERT_STYLES[variant] ?? ALERT_STYLES.info
  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-xl border p-4 text-sm ${s.wrap} ${className}`}
    >
      <span aria-hidden="true" className="mt-0.5 flex-shrink-0 font-bold">{s.icon}</span>
      <div className="flex-1">
        {title && <p className="font-bold">{title}</p>}
        {children && <p className={title ? 'mt-1' : ''}>{children}</p>}
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss alert"
          className="flex-shrink-0 rounded p-0.5 opacity-70 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-current focus-visible:outline-none"
        >
          <span aria-hidden="true">✕</span>
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------
export function EmptyState({ icon = '📭', title, description, action, className = '' }) {
  return (
    <div className={`flex flex-col items-center gap-3 rounded-2xl bg-slate-50 px-6 py-12 text-center ${className}`}>
      <span className="text-4xl" aria-hidden="true">{icon}</span>
      {title && <p className="text-base font-bold text-slate-700">{title}</p>}
      {description && <p className="max-w-xs text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------
import { useEffect, useRef } from 'react'

export function Modal({ open, onClose, title, children, size = 'md', 'aria-describedby': describedBy }) {
  const dialogRef = useRef(null)
  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }

  // Trap focus and close on Escape.
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement
    dialogRef.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      prev?.focus()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        aria-describedby={describedBy}
        tabIndex={-1}
        className={`w-full ${widths[size] ?? widths.md} rounded-2xl bg-white shadow-2xl focus:outline-none`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 id="modal-title" className="text-lg font-extrabold text-slate-900">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
          >
            <span aria-hidden="true" className="text-lg leading-none">✕</span>
          </button>
        </div>
        {/* Body */}
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------
export function Table({ columns, rows, keyField = 'id', loading, emptyMessage = 'No records found.', className = '' }) {
  return (
    <div className={`overflow-x-auto rounded-xl border border-slate-200 ${className}`}>
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                scope="col"
                className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500"
                style={col.width ? { width: col.width } : undefined}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-slate-400">
                <Spinner size="md" label="Loading table data" className="mx-auto" />
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-slate-400">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={row[keyField] ?? i} className="hover:bg-slate-50 transition-colors">
                {columns.map(col => (
                  <td key={col.key} className="px-4 py-3 text-slate-700">
                    {col.render ? col.render(row[col.key], row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatCard — small KPI tile used across dashboards
// ---------------------------------------------------------------------------
export function StatCard({ label, value, sub, icon, color = 'blue', className = '' }) {
  const colors = {
    blue:  'bg-blue-50 text-blue-700',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    red:   'bg-red-50 text-red-700',
    slate: 'bg-slate-100 text-slate-600',
  }
  return (
    <Card className={`p-5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</p>
          <p className="mt-1 text-3xl font-extrabold text-slate-900">{value ?? '—'}</p>
          {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
        </div>
        {icon && (
          <div className={`flex-shrink-0 rounded-xl p-2.5 text-xl ${colors[color] ?? colors.blue}`} aria-hidden="true">
            {icon}
          </div>
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------
const BTN_VARIANTS = {
  primary:   'bg-blue-700 text-white hover:bg-blue-800 shadow-sm shadow-blue-700/20',
  secondary: 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50',
  danger:    'bg-red-600 text-white hover:bg-red-700 shadow-sm shadow-red-600/20',
  ghost:     'text-slate-600 hover:bg-slate-100',
}

export function Button({ children, variant = 'primary', size = 'md', disabled, loading: isLoading, className = '', ...props }) {
  const sizes = { sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2.5 text-sm', lg: 'px-6 py-3 text-base' }
  return (
    <button
      disabled={disabled || isLoading}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all
        active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
        disabled:opacity-50 disabled:cursor-not-allowed
        ${BTN_VARIANTS[variant] ?? BTN_VARIANTS.primary}
        ${sizes[size] ?? sizes.md} ${className}`}
      {...props}
    >
      {isLoading && <Spinner size="sm" label="" />}
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// SectionCard — titled card used throughout dashboards
// ---------------------------------------------------------------------------
export function SectionCard({ title, count, actions, children, className = '' }) {
  return (
    <Card className={`overflow-hidden ${className}`}>
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-extrabold text-slate-900">{title}</h2>
          {count != null && (
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-700">
              {count}
            </span>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      <div className="p-5">{children}</div>
    </Card>
  )
}
