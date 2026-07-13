import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authState'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ identifier: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await login(form.identifier, form.password); navigate(location.state?.from?.pathname || '/', { replace: true }) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <AuthCard title="Welcome back" subtitle="Sign in to your secure MediFlow account">
    <form onSubmit={submit} className="space-y-4">
      <Input label="Email or phone" value={form.identifier} onChange={(value) => setForm({ ...form, identifier: value })} />
      <Input label="Password" type="password" value={form.password} onChange={(value) => setForm({ ...form, password: value })} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button disabled={busy} className="w-full rounded-xl bg-blue-700 py-3 font-semibold text-white disabled:opacity-60">{busy ? 'Signing in…' : 'Sign in'}</button>
      <div className="flex justify-between text-sm"><Link className="text-blue-700" to="/forgot-password">Forgot password?</Link><Link className="text-blue-700" to="/register">Create account</Link></div>
    </form>
  </AuthCard>
}

export function AuthCard({ title, subtitle, children }) { return <section className="min-h-screen bg-slate-50 px-4 pb-16 pt-32"><div className="mx-auto max-w-md rounded-2xl border border-blue-100 bg-white p-8 shadow-xl shadow-blue-900/10"><h1 className="text-2xl font-extrabold text-slate-900">{title}</h1><p className="mb-6 mt-2 text-sm text-slate-600">{subtitle}</p>{children}</div></section> }
export function Input({ label, type = 'text', value, onChange, ...props }) { return <label className="block text-sm font-semibold text-slate-700">{label}<input {...props} type={type} value={value} onChange={(event) => onChange(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500" /></label> }
