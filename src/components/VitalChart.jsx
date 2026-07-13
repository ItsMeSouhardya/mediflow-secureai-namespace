const sourceColors = { manual: '#2563eb', device: '#7c3aed', simulator: '#059669' }

function displayName(value) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

const ClearIcon = () => <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5" /></svg>

export default function VitalChart({ title, observations, onClear, clearing = false }) {
  const rows = [...observations].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at)).slice(-30)
  const allValues = rows.flatMap(item => item.secondary_value == null ? [item.value] : [item.value, item.secondary_value])
  const rawMinimum = allValues.length ? Math.min(...allValues) : 0
  const rawMaximum = allValues.length ? Math.max(...allValues) : 1
  const padding = Math.max((rawMaximum - rawMinimum) * 0.18, rawMaximum * 0.025, 1)
  const minimum = rawMinimum - padding
  const maximum = rawMaximum + padding
  const range = maximum - minimum || 1
  const x = index => 20 + index * (560 / Math.max(rows.length - 1, 1))
  const y = value => 170 - ((value - minimum) / range) * 135
  const primaryPoints = rows.map((item, index) => `${x(index)},${y(item.value)}`).join(' ')
  const secondaryRows = rows.filter(item => item.secondary_value != null)
  const secondaryPoints = secondaryRows.map(item => {
    const index = rows.indexOf(item)
    return `${x(index)},${y(item.secondary_value)}`
  }).join(' ')
  const latest = rows.at(-1)

  return (
    <article className="relative min-h-[390px] overflow-hidden rounded-2xl border border-white/50 p-6" style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.38)' }}>
      <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full border-[22px] border-white/20" />
      <div className="relative z-10 flex h-full flex-col">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-extrabold text-slate-900">{displayName(title)}</h3>
          <span className="text-xs font-medium text-blue-900/70">{latest?.unit}</span>
        </div>
        {rows.length ? <>
          <svg viewBox="0 0 600 190" className="h-48 w-full" role="img" aria-label={`${displayName(title)} history`}>
            <path d="M20 35H580M20 102H580M20 170H580" stroke="rgba(255,255,255,0.65)" />
            <polyline fill="none" stroke="#2563eb" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" points={primaryPoints} />
            {secondaryRows.length > 0 && <polyline fill="none" stroke="#7c3aed" strokeWidth="3" strokeDasharray="7 5" strokeLinejoin="round" points={secondaryPoints} />}
            {rows.map((item, index) => <circle key={item.id} cx={x(index)} cy={y(item.value)} r="5" fill={sourceColors[item.source] || '#334155'}><title>{item.value}{item.secondary_value != null ? `/${item.secondary_value}` : ''} {item.unit} - {item.source}</title></circle>)}
          </svg>
          <div className="flex flex-wrap gap-3 text-xs text-blue-900/65">
            {Object.entries(sourceColors).map(([source, color]) => <span key={source} className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />{source}</span>)}
            {secondaryRows.length > 0 && <span className="font-semibold text-violet-700">Dashed: diastolic</span>}
          </div>
        </> : <div className="flex min-h-[246px] flex-1 flex-col items-center justify-center rounded-xl border border-white/50 bg-white/30 p-6 text-center"><div className="text-sm font-bold text-slate-700">No readings yet</div><div className="mt-1 text-xs text-slate-500">Record a value manually to begin this trend.</div></div>}
        <div className="mt-auto flex items-end justify-between gap-4 pt-3">
          {latest ? <p className="text-xs text-blue-900/65">Latest: <strong className="text-slate-900">{latest.value}{latest.secondary_value != null ? `/${latest.secondary_value}` : ''} {latest.unit}</strong> - {new Date(latest.recorded_at).toLocaleString()}</p> : <span />}
          <button type="button" onClick={() => onClear?.(title)} disabled={!rows.length || clearing} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-blue-200 bg-white/45 px-2.5 py-1.5 text-[11px] font-bold text-blue-700 transition hover:bg-white/70 disabled:cursor-not-allowed disabled:opacity-40"><ClearIcon />{clearing ? 'Clearing...' : 'Clear reading'}</button>
        </div>
      </div>
    </article>
  )
}
