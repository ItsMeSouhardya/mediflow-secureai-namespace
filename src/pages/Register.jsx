import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authState'
import { AuthCard, Input } from './Login'

export default function Register() {
  const { register } = useAuth(); const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', age: '', gender: 'Other' })
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const submit = async (event) => { event.preventDefault(); setBusy(true); setError(''); try { await register({ ...form, age: form.age ? Number(form.age) : null, phone: form.phone || null }); navigate('/bookings') } catch (err) { setError(err.message) } finally { setBusy(false) } }
  return <AuthCard title="Create patient account" subtitle="Your clinical activity is linked to this protected identity."><form onSubmit={submit} className="space-y-4">
    <Input label="Full name" value={form.name} onChange={(value) => setForm({ ...form, name: value })} />
    <Input label="Email" type="email" value={form.email} onChange={(value) => setForm({ ...form, email: value })} />
    <Input label="Phone (optional)" value={form.phone} onChange={(value) => setForm({ ...form, phone: value })} />
    <Input label="Age (optional)" type="number" min="0" max="130" value={form.age} onChange={(value) => setForm({ ...form, age: value })} />
    <Input label="Password" type="password" value={form.password} onChange={(value) => setForm({ ...form, password: value })} />
    <p className="text-xs text-slate-500">Use 12+ characters with uppercase, lowercase, a number, and a symbol.</p>{error && <p className="text-sm text-red-600">{error}</p>}
    <button disabled={busy} className="w-full rounded-xl bg-blue-700 py-3 font-semibold text-white disabled:opacity-60">{busy ? 'Creating…' : 'Create account'}</button><p className="text-center text-sm">Already registered? <Link className="text-blue-700" to="/login">Sign in</Link></p>
  </form></AuthCard>
}
