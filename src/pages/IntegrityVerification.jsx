import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/authState'
import HowItWorks from '../components/HowItWorks'

const MONO = { fontFamily: 'DM Mono, monospace' }
const stateStyle = {
  confirmed: 'bg-emerald-100 text-emerald-800',
  pending: 'bg-amber-100 text-amber-800',
  submitted: 'bg-blue-100 text-blue-800',
  retry: 'bg-orange-100 text-orange-800',
  failed: 'bg-red-100 text-red-800',
  not_registered: 'bg-slate-100 text-slate-700',
}

const Icon = ({ children, size = 19 }) => <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
const ShieldIcon = () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
const FileIcon = () => <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></Icon>
const LinkIcon = () => <Icon><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1" /><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1" /></Icon>
const HistoryIcon = () => <Icon><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></Icon>
const LockIcon = () => <Icon><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Icon>
const CheckIcon = () => <Icon><path d="m5 12 4 4L19 6" /></Icon>
const TrashIcon = () => <Icon size={16}><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5" /></Icon>

const ProofState = ({ proof }) => {
  const state = proof?.state || 'not_registered'
  return <span className={`rounded-full px-3 py-1 text-[11px] font-bold capitalize ${stateStyle[state] || stateStyle.not_registered}`}>{state.replace('_', ' ')}</span>
}

function Panel({ title, eyebrow, action, children, className = '' }) {
  return <section className={`relative overflow-hidden rounded-2xl border border-white/50 ${className}`} style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.38)' }}>
    <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full border-[22px] border-white/20" />
    <div className="pointer-events-none absolute -bottom-12 -left-8 h-32 w-32 rounded-full border-[22px] border-white/15" />
    <header className="relative z-10 flex flex-wrap items-center justify-between gap-3 border-b border-white/40 px-7 py-5">
      <div>{eyebrow && <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>{eyebrow}</div>}<h2 className="text-lg font-extrabold text-slate-900">{title}</h2></div>
      {action}
    </header>
    <div className="relative z-10 p-7">{children}</div>
  </section>
}

export default function IntegrityVerification() {
  const { request } = useAuth()
  const [documents, setDocuments] = useState([])
  const [results, setResults] = useState({})
  const [consents, setConsents] = useState([])
  const [auditEvents, setAuditEvents] = useState([])
  const [verifyingId, setVerifyingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    request('/api/v1/patients/me/documents').then(setDocuments).catch((error) => setMessage(error.message))
    request('/api/v1/patients/me/consent/history').then(async (history) => {
      const withProofs = await Promise.all(history.map(async (grant) => {
        try {
          return { ...grant, proof: await request(`/api/v1/patients/me/consent/${grant.id}/blockchain-proof`) }
        } catch {
          return { ...grant, proof: {} }
        }
      }))
      setConsents(withProofs)
    }).catch(() => setConsents([]))
    request('/api/v1/patients/me/audit-events?limit=100').then(setAuditEvents).catch(() => setAuditEvents([]))
  }, [request])

  const verifiedCount = useMemo(() => Object.values(results).filter(result => result.tamper_status === 'verified').length, [results])

  const verify = async (document) => {
    setVerifyingId(document.id)
    setMessage('Re-hashing the encrypted source and checking its proof...')
    try {
      const result = await request(`/api/v1/patients/me/documents/${document.id}/integrity`)
      setResults(current => ({ ...current, [document.id]: result }))
      setMessage(result.tamper_status === 'modified' ? 'Integrity failure detected.' : 'Verification completed.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setVerifyingId(null)
    }
  }

  const removeDocument = async document => {
    if (!window.confirm(`Remove "${document.title}" permanently? This also removes its stored report and analysis.`)) return
    setDeletingId(document.id)
    setMessage(`Removing ${document.title}...`)
    try {
      await request(`/api/v1/patients/me/documents/${document.id}/delete`, { method: 'POST' })
      setDocuments(current => current.filter(item => item.id !== document.id))
      setResults(current => {
        const next = { ...current }
        delete next[document.id]
        return next
      })
      setMessage(`${document.title} was removed permanently.`)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setDeletingId(null)
    }
  }

  return <section className="min-h-screen bg-[#f0f5ff] pb-16 pt-[108px]" style={{ fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}>
    <div className="mx-auto max-w-[1360px] px-10">
      <header className="relative mb-7 flex min-h-[180px] items-center justify-between gap-8 overflow-hidden rounded-2xl bg-[#0f1e3d] px-12 py-10 text-white">
        <div className="pointer-events-none absolute -top-16 right-48 h-72 w-72 rounded-full border-[50px] border-white/[0.04]" />
        <div className="pointer-events-none absolute -bottom-20 right-12 h-56 w-56 rounded-full border-[36px] border-white/[0.035]" />
        <div className="relative z-10">
          <div className="mb-3 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.2em] text-blue-300" style={MONO}><ShieldIcon /> Immutable proof layer</div>
          <h1 className="text-[34px] font-extrabold leading-tight tracking-tight">Integrity <span className="text-blue-300">Verification</span></h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-blue-200">Verify that medical documents and consent records remain unchanged using local cryptographic hashes and registered blockchain proofs.</p>
        </div>
        <div className="relative z-10 rounded-2xl border border-white/15 bg-white/[0.08] px-8 py-4 text-center">
          <div className="text-xs font-bold uppercase tracking-widest text-white/50" style={MONO}>Verification mode</div>
          <div className="mt-1 flex items-center justify-center gap-2 text-lg font-extrabold"><LockIcon /> Patient controlled</div>
        </div>
      </header>

      {message && <div className={`mb-5 rounded-xl border px-5 py-4 text-sm font-bold ${message.includes('failure') ? 'border-red-200 bg-red-50 text-red-800' : 'border-blue-200 bg-blue-50 text-blue-800'}`}>{message}</div>}

      <div className="mb-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: 'Medical documents', value: documents.length, note: 'Available for verification', icon: <FileIcon /> },
          { label: 'Verified now', value: verifiedCount, note: 'Checked this session', icon: <CheckIcon /> },
          { label: 'Consent proofs', value: consents.length, note: 'Recorded permissions', icon: <LinkIcon /> },
          { label: 'Security events', value: auditEvents.length, note: 'Latest audit activity', icon: <HistoryIcon /> },
        ].map(card => <div key={card.label} className="rounded-2xl border border-white/50 p-5" style={{ background: '#A9D1FD', boxShadow: '0 4px 20px rgba(147,197,253,0.32)' }}>
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl text-white" style={{ background: '#3B82F6' }}>{card.icon}</div>
          <div className="text-3xl font-extrabold text-slate-900">{card.value}</div><div className="mt-1 text-sm font-bold text-slate-800">{card.label}</div><div className="mt-1 text-xs text-blue-900/70">{card.note}</div>
        </div>)}
      </div>

      <div className="mb-6 grid gap-5 lg:grid-cols-2">
        <Panel title="Medical document proofs" eyebrow="Cryptographic verification" action={<span className="text-xs font-bold text-blue-700">{documents.length} documents</span>}>
          {documents.length ? <div className="space-y-3">{documents.map(document => {
            const result = results[document.id]
            return <article key={document.id} className="rounded-xl border border-white/60 bg-white/40 p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex min-w-0 gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: '#3B82F6' }}><FileIcon /></span><div><strong className="text-sm text-slate-900">{document.title}</strong><p className="mt-1 text-xs capitalize text-slate-600">{document.document_type?.replaceAll('_', ' ')} · {document.status}</p></div></div>
                <div className="flex flex-wrap items-center justify-end gap-2">{result && <ProofState proof={result.proof} />}<button type="button" onClick={() => removeDocument(document)} disabled={deletingId === document.id || verifyingId === document.id} className="flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50/85 px-3 py-2 text-sm font-bold text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"><TrashIcon />{deletingId === document.id ? 'Removing...' : 'Remove'}</button><button type="button" onClick={() => verify(document)} disabled={verifyingId === document.id || deletingId === document.id} className="rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-blue-800 disabled:cursor-wait disabled:opacity-60">{verifyingId === document.id ? 'Verifying...' : 'Verify integrity'}</button></div>
              </div>
              {result && <div className={`mt-4 rounded-xl border p-4 text-sm ${result.tamper_status === 'modified' ? 'border-red-200 bg-red-50 text-red-800' : result.tamper_status === 'verified' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                <strong>{result.tamper_status === 'modified' ? 'Potential modification detected' : result.tamper_status === 'verified' ? 'Document verified' : 'Local hash valid; chain proof pending'}</strong>
                <p className="mt-1">Local hash: {result.local_hash_verified ? 'matches' : 'does not match'} · Chain hash: {result.chain_hash_verified == null ? 'not confirmed yet' : result.chain_hash_verified ? 'matches' : 'does not match'}</p>
                {result.proof?.transaction_hash && <p className="mt-1 break-all text-xs">Transaction: {result.proof.transaction_hash}</p>}
              </div>}
            </article>
          })}</div> : <div className="rounded-xl border border-white/60 bg-white/35 p-8 text-center"><div className="font-bold text-slate-800">No medical documents available</div><p className="mt-1 text-sm text-slate-600">Upload a report from My Health to make it available for verification.</p><Link to="/health-record" className="mt-4 inline-flex rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white">Open My Health</Link></div>}
        </Panel>

        <Panel title="Consent proofs" eyebrow="Permission history" action={<span className="text-xs font-bold text-blue-700">{consents.length} records</span>}>
          {consents.length ? <div className="space-y-3">{consents.map(grant => <article key={grant.id} className="rounded-xl border border-white/60 bg-white/40 p-4">
            <div className="flex flex-wrap justify-between gap-3"><div><strong className="text-sm capitalize text-slate-900">{grant.operation?.replace('_', ' ')}</strong><p className="mt-1 text-xs text-slate-600">Consent status: {grant.status} · Scopes: {grant.scopes?.join(', ') || 'none'}</p></div><div className="flex flex-wrap items-center gap-2"><span className="text-[11px] font-bold uppercase text-slate-500">Grant</span><ProofState proof={grant.proof?.grant_proof} />{grant.status === 'revoked' && <><span className="text-[11px] font-bold uppercase text-slate-500">Revoke</span><ProofState proof={grant.proof?.revocation_proof} /></>}</div></div>
          </article>)}</div> : <div className="rounded-xl border border-white/60 bg-white/35 p-7 text-center text-sm text-slate-600">No consent history is available.</div>}
        </Panel>
      </div>

      <div className="mb-6">
        <Panel title="Access and security history" eyebrow="Audit trail" action={<span className="text-xs font-bold text-blue-700">Latest {auditEvents.length}</span>}>
          {auditEvents.length ? <div className="max-h-[32rem] space-y-2 overflow-auto pr-1">{auditEvents.map(event => <article key={event.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-white/60 bg-white/40 p-4"><div><strong className="text-sm capitalize text-slate-900">{event.action?.replaceAll('.', ' ')}</strong><p className="mt-1 text-xs text-slate-600">{event.actor} · {event.resource_type?.replaceAll('_', ' ')}</p></div><div className="text-right"><span className={`rounded-full px-2.5 py-1 text-[11px] font-bold capitalize ${event.outcome === 'success' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>{event.outcome}</span><p className="mt-2 text-xs text-slate-500">{new Date(event.created_at).toLocaleString()}</p></div></article>)}</div> : <div className="rounded-xl border border-white/60 bg-white/35 p-7 text-center text-sm text-slate-600">No access events are available yet.</div>}
        </Panel>
      </div>

      <HowItWorks title="How integrity verification works" steps={[
        { title: 'Re-hash the source', description: 'Choose a medical document and the stored encrypted source is hashed again when verification begins.' },
        { title: 'Compare the proof', description: 'The local digest is compared with the opaque registered proof; medical content itself is never placed on the blockchain.' },
        { title: 'Review the result', description: 'Matching hashes confirm integrity, while any mismatch is clearly flagged and retained in the access and security history.' },
      ]} />
    </div>
  </section>
}
