import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authState'

const MONO = { fontFamily: 'DM Mono, monospace' }
const Icon = ({ children, size = 18 }) => <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
const UserIcon = () => <Icon size={24}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Icon>
const ShieldIcon = () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>
const SaveIcon = () => <Icon><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" /><path d="M17 21v-8H7v8M7 3v5h8" /></Icon>
const TrashIcon = () => <Icon><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5" /></Icon>

function Panel({ title, eyebrow, children }) {
  return <section className="relative overflow-hidden rounded-2xl border border-white/50" style={{ background: '#A9D1FD', boxShadow: '0 4px 24px rgba(147,197,253,0.38)' }}><div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full border-[22px] border-white/20" /><div className="pointer-events-none absolute -bottom-12 -left-8 h-32 w-32 rounded-full border-[22px] border-white/15" /><header className="relative z-10 border-b border-white/40 px-7 py-5"><div className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-blue-700" style={MONO}>{eyebrow}</div><h2 className="text-lg font-extrabold text-slate-900">{title}</h2></header><div className="relative z-10 p-7">{children}</div></section>
}

export default function Profile() {
  const { user, request, updateUser, logout } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState(() => ({ name: user?.name || '', email: user?.email || '', phone: user?.phone || '', age: user?.age ?? '', gender: user?.gender || '' }))
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteForm, setDeleteForm] = useState({ password: '', confirmation: '' })

  const updateField = event => setForm(current => ({ ...current, [event.target.name]: event.target.value }))

  const save = async event => {
    event.preventDefault(); setSaving(true); setMessage(''); setError('')
    try {
      const updated = await request('/api/v1/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({
          name: form.name,
          email: form.email,
          ...(form.phone ? { phone: form.phone } : {}),
          ...(form.age !== '' ? { age: Number(form.age) } : {}),
          ...(form.gender ? { gender: form.gender } : {}),
        }),
      })
      updateUser(updated)
      setMessage('Profile information updated successfully.')
    } catch (requestError) { setError(requestError.message) }
    finally { setSaving(false) }
  }

  const deleteAccount = async event => {
    event.preventDefault(); setMessage(''); setError('')
    if (deleteForm.confirmation !== 'DELETE') { setError('Type DELETE to confirm account deletion.'); return }
    if (!window.confirm('Delete and deactivate this account? You will be signed out immediately.')) return
    setDeleting(true)
    try {
      await request('/api/v1/auth/me/delete', { method: 'POST', body: JSON.stringify(deleteForm) })
      await logout()
      navigate('/login', { replace: true, state: { message: 'Your account has been deleted.' } })
    } catch (requestError) { setError(requestError.message); setDeleting(false) }
  }

  return <section className="min-h-screen bg-[#f0f5ff] pb-16 pt-[108px]" style={{ fontFamily: "'Plus Jakarta Sans', Inter, sans-serif" }}><div className="mx-auto max-w-[1360px] px-10">
    <header className="relative mb-7 flex min-h-[180px] items-center justify-between gap-8 overflow-hidden rounded-2xl bg-[#0f1e3d] px-12 py-10 text-white"><div className="pointer-events-none absolute -top-16 right-48 h-72 w-72 rounded-full border-[50px] border-white/[0.04]" /><div className="pointer-events-none absolute -bottom-20 right-12 h-56 w-56 rounded-full border-[36px] border-white/[0.035]" /><div className="relative z-10"><div className="mb-3 flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.2em] text-blue-300" style={MONO}><UserIcon /> Account settings</div><h1 className="text-[34px] font-extrabold leading-tight tracking-tight">My <span className="text-blue-300">Profile</span></h1><p className="mt-2 max-w-xl text-sm leading-6 text-blue-200">Review and update the identity information connected to your MediFlow SecureAI account.</p></div><div className="relative z-10 rounded-2xl border border-white/15 bg-white/[0.08] px-8 py-4 text-center"><div className="text-xs font-bold uppercase tracking-widest text-white/50" style={MONO}>Account status</div><div className="mt-1 flex items-center justify-center gap-2 text-lg font-extrabold"><ShieldIcon /> {user?.is_active ? 'Active' : 'Inactive'}</div></div></header>

    {message && <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm font-bold text-emerald-800">{message}</div>}
    {error && <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-800">{error}</div>}

    <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
      <Panel title="Personal information" eyebrow="Account details"><form onSubmit={save} className="grid gap-5 sm:grid-cols-2"><label className="text-sm font-bold text-slate-800">Full name<input required name="name" value={form.name} onChange={updateField} className="mt-2 w-full rounded-xl border border-blue-100 bg-white/75 px-4 py-3 font-normal outline-none focus:border-blue-500" /></label><label className="text-sm font-bold text-slate-800">Email address<input required type="email" name="email" value={form.email} onChange={updateField} className="mt-2 w-full rounded-xl border border-blue-100 bg-white/75 px-4 py-3 font-normal outline-none focus:border-blue-500" /></label><label className="text-sm font-bold text-slate-800">Phone number<input name="phone" value={form.phone} onChange={updateField} className="mt-2 w-full rounded-xl border border-blue-100 bg-white/75 px-4 py-3 font-normal outline-none focus:border-blue-500" /></label><label className="text-sm font-bold text-slate-800">Age<input type="number" min="0" max="130" name="age" value={form.age} onChange={updateField} className="mt-2 w-full rounded-xl border border-blue-100 bg-white/75 px-4 py-3 font-normal outline-none focus:border-blue-500" /></label><label className="text-sm font-bold text-slate-800 sm:col-span-2">Gender<select name="gender" value={form.gender} onChange={updateField} className="mt-2 w-full rounded-xl border border-blue-100 bg-white/75 px-4 py-3 font-normal outline-none focus:border-blue-500"><option value="">Prefer not to say</option><option value="Female">Female</option><option value="Male">Male</option><option value="Other">Other</option></select></label><button disabled={saving} className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-700 px-5 py-3 text-sm font-extrabold text-white shadow-md hover:bg-blue-800 disabled:opacity-60 sm:col-span-2"><SaveIcon /> {saving ? 'Saving...' : 'Save changes'}</button></form></Panel>

      <Panel title="Account overview" eyebrow="Identity record"><dl className="space-y-4 text-sm"><div className="rounded-xl border border-white/60 bg-white/40 p-4"><dt className="font-bold text-slate-500">Account ID</dt><dd className="mt-1 break-all font-semibold text-slate-900">{user?.id}</dd></div><div className="rounded-xl border border-white/60 bg-white/40 p-4"><dt className="font-bold text-slate-500">Member since</dt><dd className="mt-1 font-semibold text-slate-900">{user?.created_at ? new Date(user.created_at).toLocaleDateString() : 'Available after refresh'}</dd></div><div className="rounded-xl border border-white/60 bg-white/40 p-4"><dt className="font-bold text-slate-500">Role</dt><dd className="mt-1 capitalize font-semibold text-slate-900">{user?.roles?.join(', ').replaceAll('_', ' ') || 'User'}</dd></div><div className="rounded-xl border border-white/60 bg-white/40 p-4"><dt className="font-bold text-slate-500">Verification</dt><dd className="mt-1 font-semibold text-slate-900">Email {user?.email_verified ? 'verified' : 'not verified'} · Phone {user?.phone_verified ? 'verified' : 'not verified'}</dd></div></dl></Panel>
    </div>

    <div className="mt-6"><section className="relative overflow-hidden rounded-2xl border border-red-200 bg-red-50/80 p-7"><div className="pointer-events-none absolute -bottom-14 -left-10 h-36 w-36 rounded-full border-[22px] border-red-100" /><div className="relative z-10"><div className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-red-700" style={MONO}>Danger zone</div><h2 className="text-lg font-extrabold text-slate-900">Delete account</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Deleting your account immediately revokes access and removes personal sign-in information. Healthcare and security audit records may be retained in de-identified form to preserve clinical and legal integrity.</p><form onSubmit={deleteAccount} className="mt-5 grid max-w-3xl gap-3 sm:grid-cols-[1fr_1fr_auto]"><input required type="password" placeholder="Current password" value={deleteForm.password} onChange={event => setDeleteForm(current => ({ ...current, password: event.target.value }))} className="rounded-xl border border-red-200 bg-white px-4 py-3 text-sm outline-none focus:border-red-500" /><input required placeholder="Type DELETE" value={deleteForm.confirmation} onChange={event => setDeleteForm(current => ({ ...current, confirmation: event.target.value }))} className="rounded-xl border border-red-200 bg-white px-4 py-3 text-sm outline-none focus:border-red-500" /><button disabled={deleting} className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-red-700 disabled:opacity-60"><TrashIcon /> {deleting ? 'Deleting...' : 'Delete account'}</button></form></div></section></div>
  </div></section>
}
