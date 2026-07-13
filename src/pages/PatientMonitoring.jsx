import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/authState'
import VitalChart from '../components/VitalChart'
import HowItWorks from '../components/HowItWorks'

const MONO = { fontFamily: 'DM Mono, monospace' }
const typeConfig = {
  heart_rate: { label: 'Heart Rate', unit: 'bpm', placeholder: 'e.g. 74' },
  blood_pressure: { label: 'Blood Pressure', unit: 'mmHg', placeholder: 'Systolic, e.g. 118' },
  blood_oxygen: { label: 'Blood Oxygen', unit: '%', placeholder: 'e.g. 98' },
  temperature: { label: 'Temperature', unit: 'C', placeholder: 'e.g. 36.8' },
  blood_glucose: { label: 'Blood Glucose', unit: 'mg/dL', placeholder: 'e.g. 105' },
  respiratory_rate: { label: 'Respiratory Rate', unit: 'breaths/min', placeholder: 'e.g. 16' },
}
const types = Object.keys(typeConfig)

const Icon = ({ children, size = 18 }) => <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
const ActivityIcon = () => <Icon><path d="M3 12h4l2-7 4 14 2-7h6" /></Icon>
const PlusIcon = () => <Icon><path d="M12 5v14M5 12h14" /></Icon>
const TrashIcon = () => <Icon size={14}><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5" /></Icon>
const AlertIcon = () => <Icon><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></Icon>

function Panel({ title, eyebrow, action, children, className = '' }) {
  return <section className={`relative overflow-hidden rounded-2xl border border-white/50 ${className}`} style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.38)' }}><div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full border-[22px] border-white/20" /><div className="pointer-events-none absolute -bottom-12 -left-8 h-32 w-32 rounded-full border-[22px] border-white/15" /><header className="relative z-10 flex items-center justify-between border-b border-white/40 px-6 py-5"><div>{eyebrow && <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>{eyebrow}</div>}<h2 className="text-lg font-extrabold text-slate-900">{title}</h2></div>{action}</header><div className="relative z-10 p-6">{children}</div></section>
}

export default function PatientMonitoring() {
  const { request, accessToken } = useAuth()
  const [observations, setObservations] = useState([])
  const [alerts, setAlerts] = useState([])
  const [message, setMessage] = useState('')
  const [clearingType, setClearingType] = useState('')
  const [dismissedAlerts, setDismissedAlerts] = useState(() => {
    try { return JSON.parse(localStorage.getItem('mediflow_dismissed_monitoring_alerts') || '[]') } catch { return [] }
  })
  const [form, setForm] = useState({ observation_type: 'heart_rate', value: '', secondary_value: '', source_reference: '' })

  const load = useCallback(async () => {
    try {
      const [readings, currentAlerts] = await Promise.all([
        request('/api/v1/patients/me/monitoring/observations'),
        request('/api/v1/patients/me/monitoring/alerts'),
      ])
      setObservations(readings || [])
      setAlerts(currentAlerts || [])
    } catch (error) { setMessage(error.message) }
  }, [request])

  useEffect(() => { const timer = setTimeout(load, 0); return () => clearTimeout(timer) }, [load])
  useEffect(() => {
    if (!accessToken) return undefined
    const controller = new AbortController(); let buffer = ''
    fetch('/api/v1/patients/me/monitoring/stream', { headers: { Authorization: `Bearer ${accessToken}` }, signal: controller.signal }).then(async response => {
      const reader = response.body?.getReader(); if (!reader) return
      const decoder = new TextDecoder()
      while (true) {
        const { value, done } = await reader.read(); if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n'); buffer = blocks.pop() || ''
        for (const block of blocks) {
          const line = block.split('\n').find(item => item.startsWith('data: '))
          if (line) { JSON.parse(line.slice(6)); await load() }
        }
      }
    }).catch(() => null)
    return () => controller.abort()
  }, [accessToken, load])

  const grouped = useMemo(() => Object.fromEntries(types.map(type => [type, observations.filter(item => item.type === type)])), [observations])
  const visibleAlerts = alerts.filter(alert => !dismissedAlerts.includes(alert.id))

  const record = async payload => {
    const result = await request('/api/v1/patients/me/monitoring/observations', {
      method: 'POST', body: JSON.stringify(payload),
    })
    if (result?.observation) {
      setObservations(current => [result.observation, ...current.filter(item => item.id !== result.observation.id)])
    }
    if (result?.alerts?.length) {
      setAlerts(current => [...result.alerts, ...current.filter(item => !result.alerts.some(next => next.id === item.id))])
    }
    await load()
  }

  const submit = async event => {
    event.preventDefault(); setMessage('')
    try {
      const payload = {
        observation_type: form.observation_type,
        value: Number(form.value),
        source_reference: form.source_reference || null,
      }
      if (form.observation_type === 'blood_pressure') payload.secondary_value = Number(form.secondary_value)
      await record(payload)
      setMessage('Reading recorded and evaluated against monitoring rules.')
      setForm(current => ({ ...current, value: '', secondary_value: '' }))
    } catch (error) { setMessage(error.message) }
  }

  const clearAlerts = () => {
    const next = [...new Set([...dismissedAlerts, ...visibleAlerts.map(alert => alert.id)])]
    setDismissedAlerts(next)
    localStorage.setItem('mediflow_dismissed_monitoring_alerts', JSON.stringify(next.slice(-500)))
    setMessage('Alerts cleared from this view. The clinical audit history remains preserved.')
  }

  const clearReadings = async type => {
    const count = grouped[type]?.length || 0
    if (!count) return
    if (!window.confirm(`Clear all ${typeConfig[type].label.toLowerCase()} readings? Alerts created by these readings will also be removed.`)) return
    setClearingType(type); setMessage('')
    try {
      const result = await request(`/api/v1/patients/me/monitoring/observations/${type}/clear`, { method: 'POST' })
      setObservations(current => current.filter(item => item.type !== type))
      setAlerts(current => current.filter(alert => alert.observation_type !== type && alert.type !== type))
      await load()
      setMessage(`${typeConfig[type].label} cleared: ${result.deleted_count} reading${result.deleted_count === 1 ? '' : 's'} removed.`)
    } catch (error) { setMessage(error.message) }
    finally { setClearingType('') }
  }

  const config = typeConfig[form.observation_type]

  return <section className="min-h-screen bg-[#f0f5ff] pb-16 pt-[108px]" style={{ fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}><div className="mx-auto max-w-[1360px] px-10">
    <header className="relative mb-7 flex min-h-[180px] items-center justify-between gap-8 overflow-hidden rounded-2xl bg-[#0f1e3d] px-12 py-10 text-white">
      <div className="pointer-events-none absolute -top-16 right-48 h-72 w-72 rounded-full border-[50px] border-white/[0.04]" /><div className="pointer-events-none absolute -bottom-20 right-12 h-56 w-56 rounded-full border-[36px] border-white/[0.035]" />
      <div className="relative z-10"><div className="mb-3 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.2em] text-blue-300" style={MONO}><ActivityIcon /> Realtime health signals</div><h1 className="text-[34px] font-extrabold leading-tight tracking-tight">Patient <span className="text-blue-300">Monitoring</span></h1><p className="mt-2 max-w-xl text-sm leading-6 text-blue-200">Record validated readings, follow six health parameters, and review clinically meaningful alerts as they change.</p></div>
      <div className="relative z-10 rounded-2xl border border-white/15 bg-white/[0.08] px-8 py-4 text-center"><div className="text-xs font-bold uppercase tracking-widest text-white/50" style={MONO}>Signals tracked</div><div className="mt-1 text-2xl font-extrabold">6 parameters</div></div>
    </header>

    {message && <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm font-bold text-blue-800">{message}</div>}

    <div className="grid items-stretch gap-5 lg:grid-cols-[0.82fr_2fr]">
      <div className="grid h-full grid-rows-2 gap-5">
        <Panel className="h-full" title="Manual reading" eyebrow="Record a signal">
          <form onSubmit={submit} className="space-y-3">
            <select value={form.observation_type} onChange={event => setForm({ ...form, observation_type: event.target.value, value: '', secondary_value: '' })} className="w-full rounded-xl border border-blue-100 bg-white/75 p-3 text-sm font-semibold text-slate-800 outline-none focus:border-blue-500">{types.map(type => <option key={type} value={type}>{typeConfig[type].label} ({typeConfig[type].unit})</option>)}</select>
            <input required type="number" step="0.1" placeholder={config.placeholder} value={form.value} onChange={event => setForm({ ...form, value: event.target.value })} className="w-full rounded-xl border border-blue-100 bg-white/75 p-3 text-sm outline-none focus:border-blue-500" />
            {form.observation_type === 'blood_pressure' && <input required type="number" step="0.1" placeholder="Diastolic, e.g. 78" value={form.secondary_value} onChange={event => setForm({ ...form, secondary_value: event.target.value })} className="w-full rounded-xl border border-blue-100 bg-white/75 p-3 text-sm outline-none focus:border-blue-500" />}
            <input placeholder="Device or source reference (optional)" value={form.source_reference} onChange={event => setForm({ ...form, source_reference: event.target.value })} className="w-full rounded-xl border border-blue-100 bg-white/75 p-3 text-sm outline-none focus:border-blue-500" />
            <button className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-700 px-5 py-3 text-sm font-extrabold text-white shadow-md hover:bg-blue-800"><PlusIcon /> Record reading</button>
          </form>
        </Panel>

        <Panel className="h-full" title="My alerts" eyebrow={`${visibleAlerts.length} visible`} action={<button onClick={clearAlerts} disabled={!visibleAlerts.length} className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-white/45 px-2.5 py-1.5 text-[11px] font-bold text-blue-700 disabled:opacity-40"><TrashIcon /> Clear alerts</button>}>
          <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">{visibleAlerts.slice(0, 25).map(alert => <div key={alert.id} className={`rounded-xl border p-3 text-sm ${alert.severity === 'critical' ? 'border-red-100 bg-red-50/90 text-red-800' : 'border-amber-100 bg-amber-50/90 text-amber-800'}`}><div className="flex justify-between gap-2"><strong className="flex items-center gap-1.5 capitalize"><AlertIcon />{alert.severity}</strong><span className="text-xs capitalize">{alert.status}</span></div><p className="mt-1 leading-5">{alert.message}</p></div>)}{!visibleAlerts.length && <div className="rounded-xl border border-white/50 bg-white/30 p-6 text-center text-sm text-slate-600">No visible alerts.</div>}</div>
        </Panel>
      </div>

      <div className="grid gap-5 md:grid-cols-2">{types.map(type => <VitalChart key={type} title={type} observations={grouped[type] || []} onClear={clearReadings} clearing={clearingType === type} />)}</div>
    </div>
    <HowItWorks title="How patient monitoring works" steps={[
      { title: 'Record a health signal', description: 'Choose a parameter and enter a validated reading manually or capture it from a connected device.' },
      { title: 'Follow the trend', description: 'Each reading is added to its parameter graph so recent changes and the recorded source remain easy to review.' },
      { title: 'Respond to alerts', description: 'Out-of-range values create meaningful alerts that can be reviewed and cleared while the clinical audit history remains preserved.' },
    ]} />
  </div></section>
}
